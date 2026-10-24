#!/usr/bin/python3 -I
"""Fixed DOC-01 operations: one CPU, no GPU, bounded and immutable receipts."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path('/home/ubuntu/workspace/hponas')
PYTHON='/home/ubuntu/miniforge3/bin/python'
EXAMPLES=ROOT/'hpo-survey/examples'
BASE=ROOT/'docs/program/evidence/2026-10-24/doc-01'
OPERATIONS={'audit','test','response','equilibrium','verify','smoke','render-results','runtime','build'}


def identity():
    spec=importlib.util.spec_from_file_location('source_identity',ROOT/'tools/source_identity.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.source_digest(ROOT)


def bound(path):return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in OPERATIONS:
        print('Choose exactly one fixed operation: '+', '.join(sorted(OPERATIONS)));return 2
    operation=sys.argv[1];BASE.mkdir(parents=True,exist_ok=True)
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        output=BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+operation+'-'+uuid4().hex[:8]);output.mkdir()
        source=identity();inputs=[bound(p) for p in sorted(EXAMPLES.glob('*')) if p.is_file()]
        env=os.environ.copy()
        env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',
                   CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',MPLBACKEND='Agg')
        env['PYTHONPATH']=os.pathsep.join(str(ROOT/p) for p in ('.hponas-runtime/postgres-deps','.hponas-runtime/spec-deps',''))
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        if operation=='audit':commands=[([PYTHON,str(EXAMPLES/'audit_features.py'),str(output/'feature-ledger.json')],300,ROOT)]
        elif operation=='test':commands=[([PYTHON,str(EXAMPLES/'test_application_examples.py')],300,ROOT)]
        elif operation in ('response','equilibrium'):
            existing=list(BASE.glob('*-'+operation+'-*/receipt.json'))
            if any(json.loads(p.read_text()).get('passed') for p in existing):
                print('A passing allocation already exists; no automatic rerun');return 2
            commands=[([PYTHON,str(EXAMPLES/'application_examples.py'),operation,str(output/'results')],1200,ROOT)]
        elif operation=='verify':
            commands=[]
            for name in ('response','equilibrium'):
                eligible=[p.parent for p in BASE.glob('*-'+name+'-*/receipt.json') if json.loads(p.read_text()).get('passed')]
                if len(eligible)!=1:raise ValueError('Need exactly one successful '+name+' allocation')
                commands.append(([PYTHON,str(EXAMPLES/'independent_checks.py'),str(eligible[0]/'results')],300,ROOT))
        elif operation=='smoke':
            commands=[([PYTHON,'-m','hponas.quickstart','--model',name,'--output',str(output/name)],300,ROOT) for name in ('hinge','allocation')]
            commands.append(([PYTHON,'-m','hponas.quickstart','--model','hinge','--output',str(output/'hinge'),'--resume'],300,ROOT))
            commands.append(([PYTHON,str(EXAMPLES/'manual_user_example.py'),str(output/'manual-caller')],300,ROOT))
        elif operation=='render-results':
            commands=[([PYTHON,str(EXAMPLES/'render_results.py'),str(output)],300,ROOT)]
        elif operation=='runtime':
            commands=[([PYTHON,str(EXAMPLES/'inspect_runtime.py'),str(output/'runtime.json')],300,ROOT)]
        else:
            commands=[(['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex'],300,ROOT/'hpo-survey'),
                      (['/usr/bin/bibtex','main'],300,ROOT/'hpo-survey')]+[(['/usr/bin/pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex'],300,ROOT/'hpo-survey')]*2
        receipt={'operation':operation,'inputs':inputs,'runner':bound(Path(__file__)), 'source_digest':source,
                 'limits':{'cpu_count':1,'gpu':False,'network':False},'checks':[],'passed':False}
        (output/'intent.json').write_text(json.dumps(receipt,indent=2)+'\n')
        for index,(command,limit,cwd) in enumerate(commands):
            logfile=output/f'check-{index:02d}.log';start=time.monotonic();timeout=False
            with logfile.open('w') as log:
                process=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=process.wait(timeout=limit)
                except subprocess.TimeoutExpired:
                    timeout=True;os.killpg(process.pid,signal.SIGTERM)
                    try:code=process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait()
            receipt['checks'].append({'command':command,'seconds_limit':limit,'returncode':code,'timed_out':timeout,
                                      'seconds':time.monotonic()-start,'log':bound(logfile)})
            (output/'progress.json').write_text(json.dumps(receipt,indent=2)+'\n')
            if code or timeout:break
        receipt['end_source_digest']=identity()
        receipt['passed']=len(receipt['checks'])==len(commands) and all(c['returncode']==0 and not c['timed_out'] for c in receipt['checks']) and receipt['end_source_digest']==source
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'passed':receipt['passed'],'operation':operation,'directory':str(output),'seconds':sum(c['seconds'] for c in receipt['checks'])}))
        return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
