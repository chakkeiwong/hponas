#!/usr/bin/python3 -I
"""Fixed SCI-03 saved-artifact analysis. No arbitrary command, environment or path arguments."""
import fcntl,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-delivery-03'
OPS={'wallet3':'WALLET','delivery':'DELIVERY','verify':'DELIVERY','audit':'AUDIT'}
def binding(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+chr(10))
def identity():
    spec=importlib.util.spec_from_file_location('identity',ROOT/'tools/source_identity.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod.source_digest(ROOT)
def owned(group):
    pids=[];rss=0
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if os.getpgid(int(path.name))==group:pids.append(int(path.name));rss+=int((path/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except (ProcessLookupError,PermissionError,FileNotFoundError):pass
    return pids,rss
def main():
    if len(sys.argv)!=2 or sys.argv[1] not in OPS:raise ValueError('One exact SCI-03 operation required')
    op=sys.argv[1];mp=BASE/(op+'-manifest.json');manifest=json.loads(mp.read_text())
    stage='SCI-03/'+OPS[op];p=json.loads((ROOT/'docs/program/program.json').read_text())
    if p['active_work_item']!='SCI-03' or not any(s['id']==stage and s['state']=='in_progress' for s in p['continuation']['steps']):raise ValueError('Stage inactive')
    if manifest['stage']!=stage or manifest['operation']!=op:raise ValueError('Manifest/stage mismatch')
    script=ROOT/'hpo-survey/repairs/sci03'/('run_'+op+'.py')
    if binding(script) not in manifest['inputs'] or binding(Path(__file__)) not in manifest['inputs']:raise ValueError('Unbound executable')
    for row in manifest['inputs']:
        if binding(ROOT/row['path'])!=row:raise ValueError('Changed input: '+row['path'])
    if identity()!=manifest['source_digest']:raise ValueError('Changed qualified core')
    for row in manifest.get('prerequisites',[]):
        if binding(ROOT/row['path'])!=row or not json.loads((ROOT/row['path']).read_text())['passed']:raise ValueError('Prerequisite failed')
    for row in manifest.get('runtime_inputs',[]):
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Changed interval runtime')
    limits=manifest['limits']
    if not 0<limits['seconds']<=600 or limits['rss_bytes']>4*1024**3 or limits['output_bytes']>64*1024**2:raise ValueError('Out-of-plan allocation')
    if shutil.disk_usage(ROOT).free<2*1024**3:raise ValueError('Disk floor')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if list(BASE.glob('*-'+op+'-*/intent.json')):raise ValueError('Allocation consumed; requires reviewed successor')
        out=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+op+'-'+uuid4().hex[:8]);out.mkdir()
        receipt={'passed':False,'stage':stage,'operation':op,'manifest':binding(mp),'inputs':manifest['inputs'],'runtime_inputs':manifest.get('runtime_inputs',[]),'source_digest':identity(),'directory':str(out.relative_to(ROOT))}
        write(out/'intent.json',receipt)
        env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',MPLBACKEND='Agg')
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/x) for x in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});start=time.monotonic();peak=0;reason=None
        with (out/'execution.log').open('w') as log:
            child=subprocess.Popen(['/home/ubuntu/miniforge3/bin/python',str(script),str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            write(out/'process.json',{'pid':child.pid,'limit':limits})
            while child.poll() is None:
                pids,rss=owned(child.pid);peak=max(peak,rss);elapsed=time.monotonic()-start;size=sum(x.stat().st_size for x in out.rglob('*') if x.is_file())
                write(out/'progress.json',{'seconds':elapsed,'rss_bytes':rss,'owned_pids':pids,'output_bytes':size})
                if elapsed>limits['seconds']:reason='timeout'
                elif rss>limits['rss_bytes']:reason='rss_limit'
                elif size>limits['output_bytes']:reason='output_limit'
                elif shutil.disk_usage(ROOT).free<1024**3:reason='disk_floor'
                if reason:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                    break
                time.sleep(.5)
            code=child.wait()
        pids,_=owned(child.pid)
        if pids:
            os.killpg(child.pid,signal.SIGKILL);reason=reason or 'owned_children'
        unchanged=all(binding(ROOT/x['path'])==x for x in manifest['inputs'])
        result=json.loads((out/'result.json').read_text()) if (out/'result.json').is_file() else {}
        receipt.update(returncode=code,stop_reason=reason,seconds=time.monotonic()-start,peak_rss_bytes=peak,inputs_unchanged=unchanged,end_source_digest=identity(),remaining_owned_pids=pids,outputs=[binding(x) for x in sorted(out.rglob('*')) if x.is_file() and x.name not in ('intent.json','progress.json','process.json')])
        receipt['passed']=code==0 and reason is None and unchanged and not pids and all(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'] for row in manifest.get('runtime_inputs',[])) and result.get('mechanics_passed') is True and receipt['end_source_digest']==receipt['source_digest']
        write(out/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('passed','operation','directory','seconds','stop_reason')}));return 0 if receipt['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
