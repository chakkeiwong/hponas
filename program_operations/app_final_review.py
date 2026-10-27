#!/usr/bin/python3 -I
"""One fixed APP-02 final independent evidence audit; no arbitrary CLI."""
import fcntl
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
BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'
spec=importlib.util.spec_from_file_location('app_ops',ROOT/'program_operations/app_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)

def main():
    if len(sys.argv)!=1:raise ValueError('No arguments accepted')
    manifest_path=BASE/'final-audit-manifest-01.json';manifest=json.loads(manifest_path.read_text())
    program=json.loads((ROOT/'docs/program/program.json').read_text())
    if program['active_work_item']!='APP-02' or not any(s['id']=='APP-02/FINAL-REVIEW' and s['state']=='in_progress' for s in program['continuation']['steps']):raise ValueError('APP-02 final review not active')
    for row in manifest['inputs']:
        if ops.binding(ROOT/row['path'])!=row:raise ValueError('Changed diagnostic input '+row['path'])
    if ops.identity()!=manifest['source_digest']:raise ValueError('Qualified core changed')
    if shutil.disk_usage(ROOT).free<2*1024**3:raise ValueError('Disk floor')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if any(json.loads(p.read_text())['passed'] for p in BASE.glob('final-review-*/receipt.json')):raise ValueError('Successful diagnosis already consumed')
        out=BASE/('final-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);out.mkdir()
        receipt={'passed':False,'operation':'final-review','manifest':ops.binding(manifest_path),'source_digest':ops.identity(),'inputs':manifest['inputs']}
        ops.write(out/'intent.json',receipt);env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0')
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/p) for p in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});start=time.monotonic();peak=0;reason=None
        command=['/home/ubuntu/miniforge3/bin/python',str(ROOT/'hpo-survey/investigations/app02_final_audit.py'),str(out)]
        with (out/'execution.log').open('w') as log:
            proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            ops.write(out/'process.json',{'pid':proc.pid,'command':command})
            while proc.poll() is None:
                rss,owned=ops.group_rss(proc.pid);peak=max(peak,rss);elapsed=time.monotonic()-start;size=ops.bytes_used(out)
                ops.write(out/'progress.json',{'seconds':elapsed,'rss_bytes':rss,'output_bytes':size,'owned_pids':owned})
                if elapsed>300:reason='timeout'
                elif rss>2*1024**3:reason='rss_limit'
                elif size>8*1024**2:reason='output_limit'
                elif shutil.disk_usage(ROOT).free<1024**3:reason='disk_floor'
                if reason:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    break
                time.sleep(.5)
            code=proc.wait()
        _,remaining=ops.group_rss(proc.pid)
        if remaining:os.killpg(proc.pid,signal.SIGTERM);reason=reason or 'owned_children'
        unchanged=all(ops.binding(ROOT/r['path'])==r for r in manifest['inputs'])
        receipt.update(returncode=code,stop_reason=reason,seconds=time.monotonic()-start,peak_rss_bytes=peak,
                       inputs_unchanged=unchanged,log=ops.binding(out/'execution.log'),remaining_owned_pids=remaining,
                       end_source_digest=ops.identity(),directory=str(out.relative_to(ROOT)))
        audit_path=out/'audit.json'
        audit_passed=audit_path.is_file() and json.loads(audit_path.read_text()).get('passed') is True
        receipt['passed']=code==0 and reason is None and not remaining and unchanged and audit_passed and receipt['end_source_digest']==receipt['source_digest']
        ops.write(out/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('passed','directory','seconds','stop_reason')}))
        return 0 if receipt['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
