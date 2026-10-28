"""Frozen bounded operations; training and actor-oracle diagnostic are separate."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import hashlib,json
import numpy as np
import torch
from .adapter import SACMember,Actor,MID,digest
from .diagnostics import evaluate,diagnostics,replace
from hponas_rl_lqr_scalar.reference import LQRSpec,riccati
from hponas_rl_bgpbt.work import charge
ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-08'
CONFIG=dict(actor_hiddens=[32,32],critic_hiddens=[32,32],actor_lr=.001,critic_lr=.001)
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def read(path):return json.loads(Path(path).read_text())
def binding(path):
    p=Path(path);return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def train_task(args):
    method,seed,out,count,eval_seed=args;out=Path(out);out.mkdir()
    m=SACMember(CONFIG,seed,method=method);initial=digest(Actor(m.module).state_dict());curves=[]
    for stop in (2048,4096,8192):
        m.train(stop-m.transitions)
        curves.append(dict(transitions=stop,score=evaluate(m,count if stop==8192 else 4096,eval_seed if stop==8192 else 1080001),diagnostics=diagnostics(m),counters=m.counters()))
        write(out/'progress.json',curves[-1])
    m.save(out/'checkpoint.pt')
    result=dict(method=method,seed=seed,initial_actor_hash=initial,curves=curves,checkpoint=binding(out/'checkpoint.pt'))
    write(out/'result.json',result);return result

def parallel(args):
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:return list(pool.map(train_task,args))

def oracle_actor(out):
    m=SACMember(CONFIG,10800);actor=Actor(m.module);opt=torch.optim.Adam(actor.parameters(),lr=.001)
    obs=torch.tensor([[x,(30-t)/30] for t in range(30) for x in np.linspace(-.5,.5,33)],dtype=torch.float32)
    r=riccati(LQRSpec());ks=torch.tensor(np.repeat(r['K'][:,:,0],33,axis=0),dtype=torch.float32)
    ss=torch.tensor(np.repeat(r['S'],33,axis=0),dtype=torch.float32)
    def loss():
        delta=actor(obs)+obs[:,0,None]*ks
        return torch.einsum('bi,bij,bj->b',delta,ss,delta).mean()
    before=float(loss().detach())
    with charge(dict(actor_updates=2048),'exact_Q_actor_diagnostic'):
        for _ in range(2048):opt.zero_grad();v=loss();v.backward();opt.step()
    after=float(loss().detach());torch.save(actor.state_dict(),out/'oracle-actor.pt')
    from hponas_rl_lqr_scalar.reference import sample_policy
    from hponas_rl_lqr_scalar.scoring import action_rows
    return dict(before=before,after=after,updates=2048,score=sample_policy(lambda x,t:action_rows(actor,x,t),count=4096,seed=1080001),qualification='Exact optimal-Q diagnostic only; no SAC claim.')

def learner(out):
    rows=parallel([(method,seed,str(out/f'{method}-{seed}'),4096,1080001) for seed in (10801,10802,10803) for method in ('plain','quadratic','informed')])
    result=dict(passed=True,rows=rows,oracle_actor=oracle_actor(out),qualification='Prospective fixed-critic comparison; all endpoints retained.')
    write(out/'learner-result.json',result)

def review(out):
    source=read(BASE/'learner-result.json');rows=source['rows']
    means={method:float(np.mean([r['curves'][-1]['score']['gap'] for r in rows if r['method']==method])) for method in ('plain','quadratic','informed')}
    chosen=min(('quadratic','informed'),key=lambda k:(means[k],k!='quadratic'))
    paired=[next(r for r in rows if r['method']==chosen and r['seed']==s)['curves'][-1]['score']['gap']-next(r for r in rows if r['method']=='plain' and r['seed']==s)['curves'][-1]['score']['gap'] for s in (10801,10802,10803)]
    result=dict(passed=True,selected_method=chosen,mean_gaps=means,paired_validation_gap_differences=paired,joint_eligible=all(x<0 for x in paired),confirmation_seeds=[10811,10812,10813],learner_source=binding(BASE/'learner-result.json'),qualification='Model-informed/structured effect remains distinct from generic SAC; three seeds descriptive.')
    allocation=dict(seeds=[10821,10822,10823],initial_population=3,segment_transitions=2048,
        architecture_candidates=2,distillation_steps=128,critic_adaptation_steps=128,candidate_transitions=1024,
        methods=['repaired_bgpbt','repaired_static','plain_bgpbt'],
        per_method_per_seed=dict(transitions=20480,gradient_components=20992),
        work_limits=dict(transitions=184320,sac_updates=45312,distillation_updates=1536,critic_updates=1536,actor_updates=0),
        validation_paths=4096,validation_seed=1080001,test_paths=16384,test_seed=1089002,
        selection='best historical trained validation checkpoint; frozen before testing',
        qualification='Structured adapter comparison; no generic SAC or global NAS optimum')
    result['joint_allocation']=allocation
    write(out/'review-result.json',result)
    write(BASE/'joint-allocation.json',allocation if result['joint_eligible'] else dict(work_limits={}))

def confirm(out):
    selected=read(BASE/'review-result.json')['selected_method']
    rows=parallel([(m,s,str(out/f'{m}-{s}'),16384,1089001) for s in (10811,10812,10813) for m in ('plain',selected)])
    write(out/'confirm-result.json',dict(passed=True,selected_method=selected,rows=rows,endpoint_only=True,selection_uses_confirmation=False))


def handoff_task(args):
    seed,chosen,source,out=args;out=Path(out);out.mkdir()
    from .transfer import distill
    donor=SACMember.restore(ROOT/source['checkpoint']['path']);before=evaluate(donor)
    original=SACMember.identity(donor.state());continued=SACMember.restore(donor.state())
    continued.train(1024);continued_score=evaluate(continued);continued.save(out/'donor-continued.pt')
    results=[]
    for i,shape in enumerate(([16,16],[32,32,32])):
        config=dict(CONFIG,actor_hiddens=shape,critic_hiddens=shape)
        student,receipt=distill(donor,config,seed*10+i)
        after_adaptation=evaluate(student);student.train(1024);after=evaluate(student)
        accepted=replace(before['cost'],after['cost'],continued_score['cost'])
        path=out/f'child-{i}.pt';student.save(path)
        results.append(dict(config=config,transfer=receipt,after_adaptation=after_adaptation,after_sac=after,
            diagnostics=diagnostics(student),accepted=accepted,checkpoint=binding(path),retained_cost=after['cost'] if accepted else continued_score['cost']))
    assert original==SACMember.identity(donor.state())
    result=dict(seed=seed,method=chosen,donor_source=source['checkpoint'],before=before,continued_score=continued_score,
        donor_unchanged=True,children=results,continued_checkpoint=binding(out/'donor-continued.pt'))
    write(out/'result.json',result);return result

def handoff(out):
    chosen=read(BASE/'review-result.json')['selected_method'];pilot=read(BASE/'learner-result.json')
    args=[(s,chosen,next(r for r in pilot['rows'] if r['seed']==s and r['method']==chosen),str(out/f'seed-{s}')) for s in (10801,10802,10803)]
    with ProcessPoolExecutor(max_workers=3,mp_context=mp.get_context('spawn')) as pool:rows=list(pool.map(handoff_task,args))
    write(out/'handoff-result.json',dict(passed=True,rows=rows,accepted=sum(c['accepted'] for r in rows for c in r['children']),
        qualification='Only validation-nonworsening children admitted; rejection is safe behavior, not transfer success.'))
