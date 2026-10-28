"""Shared append-only actual-attempt ledger with pre-dispatch allocation checks."""
from contextlib import contextmanager
from functools import wraps
import fcntl
import json
import os
from pathlib import Path
import time
from uuid import uuid4


@contextmanager
def charge(work,kind):
    path=os.environ.get('HPONAS_SAC_WORK_LEDGER')
    if path is None:
        yield
        return
    limits=json.loads(os.environ['HPONAS_SAC_WORK_LIMITS']); path=Path(path)
    ident=uuid4().hex
    def append(row,check=False):
        with path.open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
            rows=[json.loads(line) for line in f if line.strip()]
            if check:
                for key,value in work.items():
                    used=sum(r.get('work',{}).get(key,0) for r in rows if r['event']=='reserve')
                    if used+value>limits[key]: raise ValueError('Reviewed work allocation exceeded: '+key)
            f.seek(0,2); f.write(json.dumps(row,allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())
    append({'event':'reserve','id':ident,'kind':kind,'work':work,'pid':os.getpid(),'epoch':time.time()},True)
    try:
        yield
    except BaseException as exc:
        append({'event':'failed','id':ident,'error':repr(exc),'epoch':time.time()})
        raise
    else:
        append({'event':'complete','id':ident,'epoch':time.time()})


def charged_training(fn):
    @wraps(fn)
    def wrapped(self,transitions,extra_updates=0):
        updates=(max(0,self.transitions+transitions-256)//4-max(0,self.transitions-256)//4)+extra_updates
        with charge({'transitions':transitions,'sac_updates':updates,'distillation_updates':0},'sac'):
            return fn(self,transitions,extra_updates)
    return wrapped


def charged_distillation(fn):
    @wraps(fn)
    def wrapped(teacher,config,seed,steps,student=None):
        with charge({'transitions':0,'sac_updates':0,'distillation_updates':steps},'distillation'):
            return fn(teacher,config,seed,steps,student)
    return wrapped
