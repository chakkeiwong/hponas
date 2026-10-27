#!/usr/bin/python3 -I
"""One fixed two-GPU PAR-01 development allocation; no arbitrary options."""
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-26/parallel-critical-coverage-repair-01'


def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    if sys.argv[1:]:raise ValueError('This hardware operation accepts no arguments')
    manifest=json.loads((BASE/'hardware-manifest.json').read_text())
    if bind(Path(__file__))!=manifest['runner']:raise ValueError('Unreviewed hardware runner')
    for item in manifest['inputs']:
        if bind(ROOT/item['path'])!=item:raise ValueError('Changed hardware input: '+item['path'])
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    steps={s['id']:s for s in program['continuation']['steps']}
    stage=steps['PAR-QUAL-01/EXECUTE']
    if (program['active_work_item']!='PAR-QUAL-01' or stage['state']!='in_progress'
            or any(steps[d]['state']!='complete' for d in stage['dependencies'])):
        raise ValueError('Hardware stage is inactive')
    if program['review_register']['source_frozen_by_active_run']:
        raise ValueError('Scientific source is frozen by an active run')
    if shutil.disk_usage(ROOT).free<2*1024**3:raise ValueError('Insufficient disk headroom')
    gpu_ids=manifest['gpu_ids']
    used=subprocess.run(['/usr/bin/nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader'],capture_output=True,text=True,check=True,timeout=10).stdout
    if any(gpu in used for gpu in gpu_ids):raise ValueError('Selected GPU has another compute job; refuse overlap')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-hardware-'+uuid4().hex[:8]);out.mkdir()
        shutil.copyfile(BASE/'hardware-manifest.json',out/'manifest.json')
        env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',HPONAS_PARALLEL_GPU_IDS=','.join(gpu_ids),HPONAS_PARALLEL_OUTPUT=str(out))
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/x) for x in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[:4]))
        command=['/home/ubuntu/miniforge3/bin/python','-m','pytest','-q','-p','no:cacheprovider','--junitxml='+str(out/'tests.xml'),'tests/integration/test_parallel_hardware.py']
        receipt={'passed':False,'manifest':bind(BASE/'hardware-manifest.json'),'command':command,'limits':{'seconds':600,'cpu_cores':4,'gpus':2,'rss_bytes':8*1024**3},'scientific_acceptance':False}
        (out/'intent.json').write_text(json.dumps(receipt,indent=2))
        start=time.monotonic()
        with (out/'execution.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            owned={process.pid:Path('/proc/'+str(process.pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]};reason=None;peak=0
            while process.poll() is None:
                processes={}
                for p in Path('/proc').iterdir():
                    if not p.name.isdigit():continue
                    try:
                        stat=(p/'stat').read_text().rsplit(')',1)[1].split()
                        processes[int(p.name)]=(int(stat[1]),int((p/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'),stat[19])
                    except (OSError,ProcessLookupError):pass
                while True:
                    new={pid:born for pid,(parent,rss,born) in processes.items() if parent in owned and parent in processes and processes[parent][2]==owned[parent] and pid not in owned}
                    if not new:break
                    owned.update(new)
                live={pid for pid,born in owned.items() if pid in processes and processes[pid][2]==born}
                rss=sum(processes[pid][1] for pid in live);peak=max(peak,rss)
                if time.monotonic()-start>600:reason='timeout'
                if rss>8*1024**3:reason='rss_limit'
                if reason:
                    for pid in live:
                        try:os.kill(pid,9)
                        except ProcessLookupError:pass
                    break
                time.sleep(.2)
            code=process.wait()
        surviving=[]
        for pid in set(owned)-{process.pid}:
            try:
                stat=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
                if stat[19]!=owned[pid] or stat[0]=='Z':continue
                os.kill(pid,0);surviving.append(pid);os.kill(pid,9)
            except (ProcessLookupError,FileNotFoundError):pass
        unchanged=all(bind(ROOT/x['path'])==x for x in manifest['inputs'])
        receipt.update(passed=code==0 and not reason and not surviving and unchanged,returncode=code,stop_reason=reason,remaining_children=surviving,inputs_unchanged=unchanged,peak_rss_bytes=peak,seconds=time.monotonic()-start,log=bind(out/'execution.log'))
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
        print(json.dumps({'passed':receipt['passed'],'directory':str(out.relative_to(ROOT))}));return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
