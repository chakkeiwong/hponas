#!/usr/bin/python3 -I
"""Exact bounded APP-01 commands; one owned subprocess, immutable inputs."""
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
BASE=ROOT/'docs/program/evidence/2026-10-24/app-01'
SOURCE=ROOT/'hpo-survey/applications'
PYTHON='/home/ubuntu/miniforge3/bin/python'
OPS=('controls','forecast','wallet','policy','nas','transport','verify','synthesis','audit')

def binding(path):return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def write(path,value):path.write_text(json.dumps(value,indent=2)+chr(10))
def identity():
    spec=importlib.util.spec_from_file_location('core_identity',ROOT/'tools/source_identity.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod.source_digest(ROOT)
def bytes_used(path):return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
def group_rss(group):
    total=0;owned=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if os.getpgid(int(path.name))!=group:continue
            fields=(path/'statm').read_text().split();total+=int(fields[1])*os.sysconf('SC_PAGE_SIZE');owned.append(int(path.name))
        except (ProcessLookupError,PermissionError,FileNotFoundError):pass
    return total,owned

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in OPS:
        print('Exactly one fixed APP-01 operation required: '+', '.join(OPS));return 2
    operation=sys.argv[1];BASE.mkdir(parents=True,exist_ok=True)
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((BASE/'manifest-current.json').read_text())
        for row in manifest['inputs']:
            if binding(ROOT/row['path'])!=row:raise ValueError('Reviewed input differs: '+row['path'])
        if identity()!=manifest['source_digest']:raise ValueError('Core differs from reviewed source')
        if operation in ('forecast','wallet','policy','nas','transport'):
            passed=[p for p in BASE.glob('*-'+operation+'-*/receipt.json') if json.loads(p.read_text())['passed']]
            if passed:raise ValueError('Successful allocation exists; no automatic repeat')
        if shutil.disk_usage(ROOT).free<2147483648:raise ValueError('Less than 2 GiB free')
        out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+operation+'-'+uuid4().hex[:8]);out.mkdir()
        source=identity();receipt={'operation':operation,'passed':False,'manifest':binding(BASE/'manifest-current.json'),'inputs':manifest['inputs'],'source_digest':source,'directory':str(out.relative_to(ROOT))}
        write(out/'intent.json',receipt)
        env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',MPLBACKEND='Agg')
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/p) for p in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        command=[PYTHON,str(SOURCE/'execute.py'),operation,str(out)];limit=1200 if operation in ('forecast','wallet','policy','nas','transport') else 300
        begin=time.monotonic();peak=0;reason=None;logfile=out/'execution.log'
        with logfile.open('w') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);write(out/'process.json',{'pid':process.pid,'group':process.pid,'command':command,'seconds_limit':limit})
            while process.poll() is None:
                rss,owned=group_rss(process.pid);peak=max(peak,rss);elapsed=time.monotonic()-begin;size=bytes_used(out)
                write(out/'progress.json',{'seconds':elapsed,'rss_bytes':rss,'peak_rss_bytes':peak,'output_bytes':size,'owned_pids':owned})
                if elapsed>limit:reason='wall_time_limit'
                elif rss>4294967296:reason='owned_rss_limit'
                elif size>268435456:reason='output_size_limit'
                elif shutil.disk_usage(ROOT).free<1073741824:reason='disk_floor'
                if reason:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    break
                time.sleep(.5)
            code=process.wait()
        _,remaining=group_rss(process.pid)
        if remaining:
            os.killpg(process.pid,signal.SIGTERM);reason=reason or 'unexpected_owned_children'
        unchanged=all(binding(ROOT/r['path'])==r for r in manifest['inputs'])
        receipt.update(returncode=code,stop_reason=reason,seconds=time.monotonic()-begin,peak_rss_bytes=peak,output_bytes=bytes_used(out),end_source_digest=identity(),inputs_unchanged=unchanged,log=binding(logfile),remaining_owned_pids=remaining)
        receipt['passed']=code==0 and reason is None and not remaining and unchanged and receipt['end_source_digest']==source
        write(out/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('passed','operation','directory','seconds','peak_rss_bytes','stop_reason')}));return 0 if receipt['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
