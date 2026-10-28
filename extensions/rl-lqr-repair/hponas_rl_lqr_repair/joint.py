"""Bounded BG-PBT comparison with protected incumbents and archived best states."""
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import numpy as np
from hponas_rl_bgpbt.explorer import sample_config
from hponas_rl_bgpbt.explorer_v2 import JointExplorer
from .adapter import SACMember
from .diagnostics import evaluate,replace
from .transfer import distill
from .experiments import CONFIG,BASE,ROOT,read,write,binding

def work_units(transitions,sac,distill_steps,critic_steps):
    return dict(transitions=transitions,sac_updates=sac,distillation_updates=distill_steps,
        critic_updates=critic_steps,gradient_components=4*sac+3*distill_steps+2*critic_steps)

def choose(rows):
    eligible=[r for r in rows if r['trained']]
    if not eligible:raise ValueError('No genuinely trained candidates')
    return min(eligible,key=lambda r:(r['cost'],r['label']))

def procedure(args):
    label,seed,out=args;out=Path(out);out.mkdir()
    static=label=='repaired_static';method='plain' if label=='plain_bgpbt' else read(BASE/'review-result.json')['selected_method']
    rng=np.random.default_rng(seed)
    configs=[deepcopy(CONFIG)]+[sample_config(rng) for _ in range(2)]
    members=[SACMember(c,seed*10+i,method=method) for i,c in enumerate(configs)]
    explorer=JointExplorer(seed+1);rows=[];events=[];population=[];counter=dict(transitions=0,sac=0,distill_steps=0,critic_steps=0)
    best_state=None;best_cost=float('inf');best_label=None
    def train(member,n,extra=0):
        previous=member.updates;member.train(n,extra_updates=extra)
        counter['transitions']+=n;counter['sac']+=member.updates-previous
    def record(member,name,trained=True):
        nonlocal best_state,best_cost,best_label
        score=evaluate(member);row=dict(label=name,cost=score['cost'],score=score,config=deepcopy(member.config),trained=trained)
        rows.append(row)
        if trained and (row['cost'],name)<(best_cost,best_label or ''):
            best_state=member.state();best_cost=row['cost'];best_label=name
        return row
    for round_id in range(3):
        latest=[]
        for i,m in enumerate(members):
            before=evaluate(m)['cost'];train(m,2048);row=record(m,f'r{round_id}-m{i}');latest.append(row)
            if not static:explorer.observe(m.config,round_id,before,row['cost'])
        population.append(dict(round=round_id,costs=[r['cost'] for r in latest],configs=[r['config'] for r in latest]))
        if static:continue
        explorer.finish_round(round_id,[r['cost'] for r in latest]);ranking=sorted(range(3),key=lambda i:(latest[i]['cost'],i));donor=members[ranking[0]]
        if round_id==0:
            proposal,receipt=explorer.propose(donor.config,.5,latest[ranking[0]]['cost'])
            child=donor.compatible_copy(proposal[0],seed*100);row=record(child,'compatible-copy',trained=False)
            recipient=ranking[-1];accepted=replace(latest[recipient]['cost'],row['cost'])
            if accepted:members[recipient]=child
            events.append(dict(kind='compatible',recipient=recipient,incumbent_cost=latest[recipient]['cost'],child_cost=row['cost'],accepted=accepted,proposal=receipt))
        if round_id==1:
            proposals,receipt=explorer.propose(donor.config,1.5,latest[ranking[0]]['cost'],architecture=True,count=2)
            original=SACMember.identity(donor.state())
            for j,(config,recipient) in enumerate(zip(proposals,ranking[-2:])):
                child,transfer=distill(donor,config,seed*1000+j,steps=128,adapt_steps=128)
                counter['distill_steps']+=128;counter['critic_steps']+=128
                before=evaluate(child)['cost'];train(child,1024);row=record(child,f'architecture-{j}')
                explorer.observe(child.config,1.5,before,row['cost'])
                accepted=replace(latest[recipient]['cost'],row['cost'],latest[ranking[0]]['cost'])
                if accepted:members[recipient]=child
                events.append(dict(kind='architecture',recipient=recipient,incumbent_cost=latest[recipient]['cost'],donor_cost=latest[ranking[0]]['cost'],child_cost=row['cost'],accepted=accepted,transfer=transfer,proposal=receipt,candidate_index=j))
            assert original==SACMember.identity(donor.state())
    if static:
        for i,(n,extra) in enumerate(((684,108),(684,108),(680,104))):
            train(members[i],n,extra);record(members[i],f'static-extra-{i}')
    work=work_units(**counter);allocation=read(BASE/'joint-allocation.json')['per_method_per_seed']
    for key in ('transitions','gradient_components'):
        if work[key]!=allocation[key]:raise ValueError('Matched procedure work differs: '+str(work))
    winner=choose(rows)
    assert winner['label']==best_label and best_state is not None
    m=SACMember.restore(best_state);m.save(out/'selected.pt')
    freeze=dict(method=label,representation=method,seed=seed,initial_configs=configs,rows=rows,events=events,population=population,
        selected=winner,checkpoint=binding(out/'selected.pt'),work=work,qualification='Bounded three-member procedure, not global search optimum')
    write(out/'selection-freeze.json',freeze)
    return freeze

def main(out):
    review=read(BASE/'review-result.json')
    if not review['joint_eligible']:
        write(out/'joint-result.json',dict(passed=True,executed=False,reason='Fixed learner gate failed',new_training=0));return
    allocation=read(BASE/'joint-allocation.json')
    args=[(method,seed,str(out/f'{method}-{seed}')) for seed in allocation['seeds'] for method in allocation['methods']]
    with ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:rows=list(pool.map(procedure,args))
    # All procedure winners are sealed before any test path is evaluated.
    sealed=[binding((ROOT/row['checkpoint']['path']).parent/'selection-freeze.json') for row in rows]
    write(out/'all-selection-freezes.json',sealed)
    tested=[]
    for row in rows:
        member=SACMember.restore(ROOT/row['checkpoint']['path'])
        tested.append(dict(method=row['method'],seed=row['seed'],selected=row['selected'],checkpoint=row['checkpoint'],
            test=evaluate(member,allocation['test_paths'],allocation['test_seed']),work=row['work']))
    write(out/'joint-result.json',dict(passed=True,executed=True,rows=tested,selection_freezes=sealed,
        all_freezes_before_testing=True,qualification='Fixture-specific repaired representation; finite three-seed comparison and selected policies only.'))
