#!/usr/bin/python3 -I
"""Fixed bounded RL-LQR-03 operations, with source and resource admission."""
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
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03'
EXT=ROOT/'extensions/rl-lqr5-bgpbt'
STAGES={'engineering':'ENGINEERING','calibration':'CALIBRATION','search':'SEARCH',
        'confirmation':'CONFIRMATION','hardware':'HARDWARE','documentation':'DOCUMENTATION','audit':'AUDIT',
        'hardware-documentation':'HARDWARE-DOCUMENTATION','master-audit':'GAP-01/FINAL-AUDIT',
        'repair-engineering':'REPAIR-ENGINEERING','procedure-check':'PROCEDURE-CHECK',
        'selection-reconciliation':'SELECTION-RECONCILIATION','device-repair':'DEVICE-REPAIR'}


def binding(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path,value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n'); tmp.replace(path)


def helpers():
    spec=importlib.util.spec_from_file_location('owned_processes',ROOT/'program_operations/rl_lqr_ops.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in STAGES: raise ValueError('One fixed operation required')
    op=sys.argv[1]; utility=helpers(); stage=STAGES[op]
    if '/' not in stage: stage='RL-LQR-03/'+stage
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    steps={s['id']:s for s in program['continuation']['steps']}
    if program['active_work_item']!=stage.split('/')[0] or steps[stage]['state']!='in_progress':
        raise ValueError('Operation is not the active reviewed stage')
    if any(steps[x]['state']!='complete' for x in steps[stage]['dependencies']):
        raise ValueError('Operation predecessor incomplete')
    manifest_path=BASE/(op+'-manifest.json'); manifest=json.loads(manifest_path.read_text())
    bound=[manifest['runner'],*manifest['inputs']]
    if manifest['operation']!=op or manifest['runner']!=binding(Path(__file__)):
        raise ValueError('Reviewed operation/runner differs')
    if manifest['core_source']!=utility.source() or any(binding(ROOT/b['path'])!=b for b in bound):
        raise ValueError('Reviewed source/input differs')
    for previous in BASE.glob('*-'+op+'-*/receipt.json'):
        if op not in ('engineering','repair-engineering','device-repair') and json.loads(previous.read_text())['passed']:
            raise ValueError('Successful stage allocation already consumed; replay its evidence')
    if shutil.disk_usage(ROOT).free<8*1024**3: raise ValueError('Insufficient disk headroom')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+op+'-'+uuid4().hex[:8])
        out.mkdir(); shutil.copyfile(manifest_path,out/'manifest.json')
        for b in bound:
            dest=out/'inputs'/b['path']; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/b['path'],dest)
        env={k:os.environ[k] for k in ('HOME','USER','LOGNAME','LANG') if k in os.environ}
        env.update(PATH='/home/ubuntu/miniforge3/bin:/usr/bin:/bin',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
            MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',
            PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',RLLIB_TEST_NO_TF_IMPORT='1',RLLIB_TEST_NO_JAX_IMPORT='1',
            RAY_ENABLE_AUTO_CONNECT='0',
            MPLBACKEND='Agg',CUDA_VISIBLE_DEVICES='',
            HPONAS_SAC_WORK_LEDGER=str(out/'work.jsonl'),HPONAS_SAC_WORK_LIMITS=json.dumps(manifest['work_limits']))
        if op=='hardware': env['HPONAS_SAC_GPU_ALLOCATOR_BYTES']=str(1024**3)
        env['PYTHONPATH']=os.pathsep.join(str(p) for p in (EXT,ROOT/'extensions/rl-lqr5',ROOT/'extensions/rl-lqr',
            ROOT/'.hponas-runtime/rl-lqr-deps',ROOT/'.hponas-runtime/spec-deps',ROOT/'.hponas-runtime/postgres-deps',ROOT))
        cpus=sorted(os.sched_getaffinity(0))[-3:]
        if len(cpus)<3: raise ValueError('Three available CPUs required')
        os.sched_setaffinity(0,set(cpus))
        limits=manifest['limits']; start=time.monotonic(); peak=0; reason=None; gpu_peak={}; last_gpu_check=0.
        command=['/home/ubuntu/miniforge3/bin/python',str(EXT/'run_operation.py'),op,str(out)]
        receipt={'operation':op,'stage':stage,'passed':False,'core_source':utility.source(),
            'directory':str(out.relative_to(ROOT)),'manifest':binding(manifest_path),'limits':limits,
            'work_limits':manifest['work_limits']}
        write(out/'intent.json',receipt)
        with (out/'execution.log').open('x') as log:
            child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            table=utility.process_table(); owned={child.pid:table[child.pid][1]} if child.pid in table else {}
            write(out/'process.json',{'pid':child.pid,'command':command,'epoch':time.time()})
            while child.poll() is None:
                live=utility.tracked(owned); rss=sum(r[3] for r in live.values()); peak=max(peak,rss)
                elapsed=time.monotonic()-start; size=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
                write(out/'progress.json',{'seconds':elapsed,'owned_pids':sorted(live),'rss_bytes':rss,'bytes':size})
                if op=='hardware' and elapsed-last_gpu_check>=2:
                    query=subprocess.run(['/usr/bin/nvidia-smi','--query-compute-apps=pid,used_memory',
                        '--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=10)
                    if query.returncode: reason='gpu_memory_monitor_failed'
                    else:
                        for row in query.stdout.splitlines():
                            fields=[x.strip() for x in row.split(',')]
                            if len(fields)==2 and fields[0].isdigit() and int(fields[0]) in live:
                                if not fields[1].isdigit(): reason='gpu_memory_measurement_unavailable'
                                else:
                                    pid=fields[0]; used=int(fields[1]); gpu_peak[pid]=max(used,gpu_peak.get(pid,0))
                                    if used>2048: reason='owned_gpu_memory_limit'
                    last_gpu_check=elapsed
                if elapsed>limits['seconds']: reason='wall_time_limit'
                elif rss>limits['host_rss_bytes']: reason='owned_rss_limit'
                elif size>limits['output_bytes']: reason='output_size_limit'
                elif shutil.disk_usage(ROOT).free<8*1024**3: reason='disk_floor'
                if reason:
                    for pid in live:
                        try: os.kill(pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: pass
                    for pid in utility.tracked(owned):
                        try: os.kill(pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                    break
                time.sleep(.5)
            code=child.wait()
        survivors=utility.tracked(owned)
        for pid in survivors:
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        same=all(binding(ROOT/b['path'])==b for b in bound)
        receipt.update(returncode=code,stop_reason=reason,seconds=time.monotonic()-start,
            peak_rss_bytes=peak,remaining_children=sorted(survivors),inputs_unchanged=same,
            end_core_source=utility.source(),log=binding(out/'execution.log'),owned_gpu_peak_mib=gpu_peak)
        if (out/'work.jsonl').exists():
            rows=[json.loads(l) for l in (out/'work.jsonl').read_text().splitlines()]
            receipt['charged_work']={k:sum(r.get('work',{}).get(k,0) for r in rows if r['event']=='reserve')
                                     for k in manifest['work_limits']}
            receipt['work_ledger']=binding(out/'work.jsonl')
        receipt['passed']=code==0 and reason is None and not survivors and same and receipt['end_core_source']==receipt['core_source']
        write(out/'receipt.json',receipt); print(json.dumps(receipt,indent=2))
        return 0 if receipt['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
