from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import hashlib,json,time
import numpy as np
import torch
from .adapter import SACMember,Actor,digest
from .reference import LQRSpec,oracle_report
from .diagnostics import evaluate,greedy_report,probes
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-09'
CONFIG=dict(actor_hiddens=[32,32],critic_hiddens=[32,32],actor_lr=.001,critic_lr=.001)
METHODS=('matrix','symmetric')
CASES=[f's{d}a{m}' for d in (1,10) for m in range(5,11)]
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def read(p):return json.loads(Path(p).read_text())
def bind(p):
    p=Path(p);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def task(args):
    case,method,seed,path,confirm=args;out=Path(path);out.mkdir();start=time.monotonic()
    member=SACMember(CONFIG,seed,case=case,method=method);initial=digest(Actor(member.module).state_dict());curves=[]
    for endpoint in (2048,4096,8192):
        member.train(endpoint-member.transitions)
        row=dict(transitions=endpoint,score=evaluate(member),counters=member.counters(),seconds=time.monotonic()-start)
        curves.append(row);write(out/'progress.json',row)
    member.save(out/'checkpoint.pt');actor=Actor(member.module).eval();torch.jit.save(torch.jit.trace(actor,torch.zeros(1,member.specification.states+1)),str(out/'actor.pt'))
    result=dict(case=case,method=method,seed=seed,initial_actor_hash=initial,curves=curves,checkpoint=bind(out/'checkpoint.pt'),actor=bind(out/'actor.pt'),greedy=greedy_report(member),probes=probes(member),seconds=time.monotonic()-start)
    # Fixed endpoint is written before opening test paths. No test checkpoint selection.
    write(out/'endpoint-freeze.json',result)
    if confirm:result['test']=evaluate(member,count=16384,seed=1099001)
    write(out/'result.json',result);return result

def execute(op,out):
    if op=='actions':cases=[c for c in CASES if c.startswith('s1a')];seeds=(10901,10902)
    elif op=='states':cases=[c for c in CASES if c.startswith('s10a')];seeds=(10911,10912)
    elif op=='confirm':cases=CASES;seeds=(10921,10922,10923)
    else:raise ValueError(op)
    args=[(case,method,seed,str(out/f'{case}-{method}-{seed}'),op=='confirm') for case in cases for seed in seeds for method in METHODS]
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:
        futures=[pool.submit(task,a) for a in args];rows=[]
        for future in futures:
            rows.append(future.result());write(out/'completed.json',dict(completed=len(rows),total=len(args)))
    write(out/(op+'-result.json'),dict(passed=True,operation=op,rows=rows,method_order=list(METHODS),fixed_endpoint=8192,selection_uses_test=False))

def review(out):
    rows=read(BASE/'actions-result.json')['rows'];summary=[]
    for c in CASES[:6]:
        means={m:float(np.mean([r['curves'][-1]['score']['gap'] for r in rows if r['case']==c and r['method']==m])) for m in METHODS}
        summary.append(dict(case=c,mean_gaps=means))
    write(out/'review-result.json',dict(passed=True,new_training=0,summary=summary,next_stage='RL-LQR-09/STATES',state_design_changed=False,reason='Continue prespecified coupled-state comparison, retaining all scalar results.'))

def freeze(out):
    rows=read(BASE/'actions-result.json')['rows']+read(BASE/'states-result.json')['rows'];choices=[]
    for c in CASES:
        means={m:float(np.mean([r['curves'][-1]['score']['gap'] for r in rows if r['case']==c and r['method']==m])) for m in METHODS}
        choices.append(dict(case=c,mean_validation_gaps=means,selected=min(METHODS,key=lambda m:(means[m],METHODS.index(m)))))
    write(out/'freeze-result.json',dict(passed=True,new_training=0,choices=choices,confirmation_seeds=[10921,10922,10923],test_seed=1099001,both_methods_confirmed=True))
