"""Write-ahead per-task ledger; committed work replays, uncertain work refuses."""
import hashlib
import json
import os
from pathlib import Path
import time


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path); tmp=path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,indent=2,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def verify_result(directory,task):
    directory=Path(directory); result=read(directory/'result.json')
    if result['task'] != task: raise ValueError('Committed task specification differs')
    for name,hash_value in result['artifacts'].items():
        if sha(directory/name) != hash_value: raise ValueError('Committed artifact differs')
    if not result['passed']: raise ValueError('Committed task failed')
    return result


def run_task(task,execution=None):
    # Worker environment/affinity is already installed before these heavy imports.
    import torch
    import ray
    from .adapter import SACMember
    from .transfer import distill
    if execution is not None and not isinstance(execution,dict): execution=execution.to_dict()
    directory=Path(task['directory']); directory.mkdir(parents=True,exist_ok=True)
    if (directory/'result.json').exists(): return verify_result(directory,task)
    intent=directory/'intent.json'
    try:
        with intent.open('x') as f:
            json.dump({'task':task,'reserved_transitions':task.get('transitions',0),
                       'reserved_distillation_updates':task.get('distillation_steps',0),
                       'reserved_extra_updates':task.get('extra_updates',0),
                       'status':'reserved_before_dispatch','epoch':time.time()},f,indent=2)
            f.flush(); os.fsync(f.fileno())
    except FileExistsError:
        raise RuntimeError('Uncertain interrupted task: charge reservation; explicit repair required') from None
    device=(execution or {}).get('device','cpu')
    gpu_memory=None
    if device != 'cpu':
        limit=int(os.environ.get('HPONAS_SAC_GPU_ALLOCATOR_BYTES',1024**3))
        total=torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.,limit/total),0)
        torch.cuda.reset_peak_memory_stats(0)
        gpu_memory={'allocator_limit_bytes':limit}
    start=time.time(); member=None
    try:
        transfer=None; restore=None
        if task.get('input'):
            if sha(task['input']) != task['input_sha256']: raise ValueError('Input checkpoint changed')
            teacher=SACMember.restore(task['input'],device,actions=task['actions'])
            restore=teacher.identity(teacher.state())
            if task['kind']=='copy':
                member=teacher.compatible_copy(task['config'],task['seed'])
                transfer={'kind':'compatible_copy','donor_identity':restore,
                          'rates':member.config,'adam_policy':'copy','target_policy':'copy',
                          'randomness':'fork_after_exact_copy'}
            elif task['kind']=='distill':
                student=None
                if task.get('student'):
                    if sha(task['student']) != task['student_sha256']: raise ValueError('Student checkpoint changed')
                    student=SACMember.restore(task['student'],device,actions=task['actions'])
                member,transfer=distill(teacher,task['config'],task['seed'],task['distillation_steps'],student)
            elif task['kind']=='train':
                member=teacher
                if member.config != task['config']: raise ValueError('Unrecorded configuration change')
            else: raise ValueError('Unknown task kind')
        elif task['kind']=='fresh':
            member=SACMember(task['config'],task['seed'],device,actions=task['actions'])
        else: raise ValueError('Input checkpoint required')
        before=member.counters(); before_score=member.score()
        if task.get('barrier'):
            barrier=Path(task['barrier']); barrier.mkdir(exist_ok=True)
            write(barrier/(str(os.getpid())+'.json'),{'pid':os.getpid(),'device':device})
            deadline=time.monotonic()+120
            while len(list(barrier.glob('*.json'))) < 2:
                if time.monotonic()>deadline: raise TimeoutError('Training barrier timed out')
                time.sleep(.05)
        if device != 'cpu': torch.cuda.synchronize()
        training_start=time.time()
        member.train(task.get('transitions',0),task.get('extra_updates',0))
        if device != 'cpu': torch.cuda.synchronize()
        training_end=time.time()
        after=member.counters()
        score=member.score(directory/'actor.pt')
        checkpoint_identity=member.save(directory/'checkpoint.pt')
        if ray.is_initialized(): raise ValueError('Standalone worker unexpectedly initialized Ray')
        if gpu_memory is not None:
            gpu_memory.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
                              peak_reserved_bytes=torch.cuda.max_memory_reserved(0))
            if gpu_memory['peak_reserved_bytes']>gpu_memory['allocator_limit_bytes']:
                raise ValueError('Owned GPU allocator limit exceeded')
        artifacts={name:sha(directory/name) for name in ('actor.pt','checkpoint.pt')}
        result={'passed':True,'task':task,'pid':os.getpid(),'cpu_affinity':sorted(os.sched_getaffinity(0)),
            'execution':execution,'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES',''),
            'gpu_memory':gpu_memory,
            'ray_initialized':ray.is_initialized(),
            'started_epoch':start,'finished_epoch':time.time(),
            'training_started_epoch':training_start,'training_finished_epoch':training_end,
            'before':before,'after':after,'before_score':before_score,'score':score,
            'restore_identity':restore,'checkpoint_identity':checkpoint_identity,'transfer':transfer,
            'work':{'transitions':after['transitions']-before['transitions'],
                    'sac_updates':after['sac_updates']-before['sac_updates'],
                    'distillation_updates':task.get('distillation_steps',0),
                    'gradient_components':4*(after['sac_updates']-before['sac_updates'])+3*task.get('distillation_steps',0)},
            'artifacts':artifacts}
        write(directory/'result.json',result)
        return result
    except BaseException as exc:
        write(directory/'failure.json',{'error':repr(exc),'finished_epoch':time.time(),
            'actual_counters':member.counters() if member is not None else None,
            'accounting':'reservation remains charged; no automatic retry'})
        raise


def task(directory,kind,config,seed,transitions=0,input_path=None,actions=2,**extra):
    row={'directory':str(Path(directory).resolve()),'kind':kind,'config':config,'seed':int(seed),
         'transitions':transitions,'actions':actions,**extra}
    if input_path:
        row.update(input=str(Path(input_path).resolve()),input_sha256=sha(input_path))
    if row.get('student'): row['student_sha256']=sha(row['student'])
    return row
