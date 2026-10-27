#!/usr/bin/python3 -I
"""Fixed PAR-01 development operations; no arbitrary commands or environments."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path('/home/ubuntu/workspace/hponas')
BASE = ROOT/'docs/program/evidence/2026-10-26/parallel-repair-01'
PYTHON = '/home/ubuntu/miniforge3/bin/python'
ROSTERS = {
    'resources': ['tests/unit/test_parallel_resources.py'],
    'executors': ['tests/integration/test_resource_executor.py', 'tests/conformance/test_executor_contract.py', 'tests/unit/test_ray_control_paths.py', 'tests/unit/test_ray_streaming_accounting.py'],
    'study': ['tests/integration/test_parallel_study.py', 'tests/integration/test_declared_evaluation.py', 'tests/integration/test_multi_objective_study.py'],
    'population': ['tests/integration/test_parallel_population.py', 'tests/unit/test_population_checkpoint.py', 'tests/unit/test_bg_population.py', 'tests/unit/test_pb2_mix.py', 'tests/unit/test_generational_transfer.py'],
    'adapter': ['tests/integration/test_parallel_population.py::test_parallel_caller_adapter_known_answer_and_resume', 'tests/integration/test_parallel_population.py::test_parallel_adapter_failed_calls_are_charged', 'tests/integration/test_population_adapter.py'],
    'methods': ['tests/integration/test_parallel_methods.py'],
    'ray': ['tests/integration/test_parallel_ray.py'],
    'streaming': ['tests/integration/test_declared_streaming.py', 'tests/integration/test_streaming_scheduler.py', 'tests/unit/test_ray_cancellation_boundary.py'],
    'audit-controls': ['tests/unit/test_parallel_program_boundary.py', 'tests/unit/test_gap_trace.py'],
}
STAGES = {'resources': 'RESOURCES', 'executors': 'EXECUTORS', 'study': 'STUDY',
          'population': 'POPULATION', 'adapter': 'POPULATION', 'methods': 'CONFORMANCE',
          'ray': 'HARDWARE', 'streaming': 'HARDWARE', 'audit-controls': 'HARDWARE',
          'build': 'DOCUMENTATION'}


def binding(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, data):
    path.write_text(json.dumps(data, indent=2)+chr(10))


def source():
    spec = importlib.util.spec_from_file_location('identity', ROOT/'tools/source_identity.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.source_digest(ROOT)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {*ROSTERS, 'build'}:
        raise ValueError('One exact reviewed PAR-01 operation required')
    op = sys.argv[1]
    if op not in ('population', 'build'): raise ValueError('Only reviewed repair population/build operations are admitted')
    program = json.loads((ROOT/'docs/program/program.json').read_text())
    if program['active_work_item'] != 'PAR-QUAL-01':
        raise ValueError('PAR-QUAL-01 is not active')
    steps = {s['id']: s for s in program['continuation']['steps']}
    stage = steps['PAR-QUAL-01/PREPARE']
    if stage['state'] not in ('in_progress', 'complete') or any(steps[d]['state'] != 'complete' for d in stage['dependencies']):
        raise ValueError('Operation stage or dependency is not eligible')
    manifest = json.loads((BASE/(op+'-manifest.json')).read_text())
    if manifest['operation'] != op or manifest['runner'] != binding(Path(__file__)):
        raise ValueError('Operation manifest or reviewed runner differs')
    for item in manifest['inputs']:
        if binding(ROOT/item['path']) != item:
            raise ValueError('Reviewed input changed: '+item['path'])
    if shutil.disk_usage(ROOT).free < 2*1024**3:
        raise ValueError('Insufficient disk headroom')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+op+'-'+uuid4().hex[:8]);out.mkdir()
        shutil.copyfile(BASE/(op+'-manifest.json'), out/'manifest.json')
        env=os.environ.copy()
        env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',
                   CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/x) for x in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[:4]))
        if op == 'build':
            cwd=ROOT/'hpo-survey'
            latex=['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','-output-directory='+str(out),'main-app03.tex']
            env['BIBINPUTS']=str(cwd)+os.pathsep;env['BSTINPUTS']=str(cwd)+os.pathsep
            commands=[latex,['/usr/bin/bibtex','main-app03'],latex,latex]
        else:
            cwd=ROOT
            commands=[[PYTHON,'-m','pytest','-q','-p','no:cacheprovider','--junitxml='+str(out/'tests.xml'),*ROSTERS[op]]]
        receipt={'operation':op,'manifest':binding(BASE/(op+'-manifest.json')),'source_digest':source(),
                 'checks':[],'passed':False,'scientific_acceptance':False,'limits':{'cpu_cores':4,'gpus':0,'seconds':300,'owned_rss_bytes':8*1024**3}}
        write(out/'intent.json',receipt)
        for i,command in enumerate(commands):
            log=out/('check-%02d.log'%i);start=time.monotonic();reason=None
            with log.open('x') as handle:
                child=subprocess.Popen(command,cwd=out if op=='build' and i==1 else cwd,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                # /proc descendants include worker-owned sessions, not unrelated processes.
                owned={child.pid: Path('/proc/'+str(child.pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]};peak=0
                while child.poll() is None:
                    processes={}
                    for path in Path('/proc').iterdir():
                        if not path.name.isdigit():continue
                        try:
                            stat=(path/'stat').read_text().rsplit(')',1)[1].split()
                            processes[int(path.name)]=(int(stat[1]),int((path/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'),stat[19])
                        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
                    changed=True
                    while changed:
                        added={pid:born for pid,(parent,rss,born) in processes.items() if parent in owned and parent in processes and processes[parent][2]==owned[parent] and pid not in owned}
                        changed=bool(added);owned.update(added)
                    live={pid for pid,born in owned.items() if pid in processes and processes[pid][2]==born}
                    rss=sum(processes[pid][1] for pid in live);peak=max(peak,rss)
                    if time.monotonic()-start>300:reason='timeout'
                    if rss>8*1024**3:reason='rss_limit'
                    if reason:
                        for pid in live:
                            try:os.kill(pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                        break
                    time.sleep(.1)
                code=child.wait()
            # Clean only observed owned children; no orphan work survives a failed test.
            survivors=[]
            for pid in set(owned)-{child.pid}:
                try:
                    stat=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
                    if stat[19]!=owned[pid] or stat[0]=='Z':continue
                    os.kill(pid,0);survivors.append(pid);os.kill(pid,signal.SIGKILL)
                except (ProcessLookupError,FileNotFoundError):pass
            receipt['checks'].append({'command':command,'returncode':code,'stop_reason':reason,'remaining_children':survivors,
                                      'seconds':time.monotonic()-start,'peak_rss_bytes':peak,'log':binding(log)})
            if code or reason or survivors:break
        receipt['end_source_digest']=source()
        receipt['passed']=(len(receipt['checks'])==len(commands) and all(c['returncode']==0 and not c['stop_reason'] and not c['remaining_children'] for c in receipt['checks']) and receipt['source_digest']==receipt['end_source_digest'])
        write(out/'receipt.json',receipt)
        print(json.dumps({'passed':receipt['passed'],'operation':op,'directory':str(out.relative_to(ROOT))}))
        return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
