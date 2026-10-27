"""SCI-02 versioned repair of the retained finite ifBO reconstruction.

The original validation module and its failed campaign remain unchanged.
Only the PI arithmetic delegates to the explicitly reviewed companion.
"""
import hashlib
import math
from pathlib import Path

import numpy as np
from pi_float32 import probability_of_improvement


def close(actual,expected,atol=2e-12,rtol=2e-10):
    a,b=np.asarray(actual,dtype=float),np.asarray(expected,dtype=float)
    if a.shape!=b.shape or not np.all(np.isfinite(a)) or not np.allclose(a,b,atol=atol,rtol=rtol):
        raise ValueError('Independent numerical reconstruction differs')


def exact(initial,x,step):
    eta=1/40+3*x/5
    a,b=initial[0]*(1-eta)**step,initial[1]*(1-3*eta)**step
    return [3*a/5-4*b/5,4*a/5+3*b/5],(a*a+b*b)/sum(v*v for v in initial)


def optimum(initial):
    r=(initial[0]**2/(3*initial[1]**2))**(1/15)
    eta=(1+r)/(3+r)
    return eta,exact(initial,(eta-1/40)*5/3,8)[1]


def verify_updates(initial,arm):
    if len(arm['trace'])!=24 or arm['gradient_updates']!=32 or len(arm['certification'])!=8:
        raise ValueError('Fixed physical update allocation differs')
    latest={}
    for record in arm['trace']:
        i,row=record['id'],record['update']
        if type(i) is not int or i<0 or not 0<=row['x']<=1:
            raise ValueError('Invalid configuration coordinate/ID')
        previous=latest.get(i)
        if row['step']!=(1 if previous is None else previous['step']+1) or not 1<=row['step']<=8:
            raise ValueError('Resume fidelity differs')
        if previous is not None and row['x']!=previous['x']:
            raise ValueError('Resumed coordinate changed')
        state,loss=exact(initial,row['x'],row['step'])
        close(row['state'],state);close(row['loss'],loss)
        latest[i]=row
    selected=min(latest,key=lambda i:(latest[i]['loss'],i))
    if arm['selected_id']!=selected:
        raise ValueError('Recommendation is not minimum latest observed loss')
    for step,row in enumerate(arm['certification'],1):
        if row['step']!=step or row['x']!=latest[selected]['x']:
            raise ValueError('Certification used another configuration or skipped work')
        state,loss=exact(initial,row['x'],step)
        close(row['state'],state);close(row['loss'],loss)
    return arm['certification'][-1]['loss']


def verify_asha(initial,seed,arm):
    latest,active,populations,paused={},{},{r:{} for r in (1,2,4,8)},{}
    rng=np.random.RandomState(seed)
    running=None
    for record in arm['trace']:
        expected_action=None
        if running is None:
            eligible=[]
            for rung in (4,2,1):
                pop=populations[rung]
                if len(pop)<2:continue
                values=sorted(pop.values());n=len(values)
                cutoff=values[n//2] if n%2 else sum(values[n//2-1:n//2+1])/2
                eligible=[i for i in sorted(pop,key=pop.get) if pop[i]<=cutoff and paused.get(i)==rung]
                if eligible:
                    i=eligible[0];running=(i,rung*2);paused.pop(i)
                    expected_action={'kind':'promote','id':i,'target':rung*2}
                    break
            if not eligible:
                i=len(latest);x=float(rng.uniform());running=(i,1)
                latest[i]={'x':x,'step':0}
                expected_action={'kind':'new','id':i,'target':1}
        if record['action']!=expected_action or record['id']!=running[0]:
            raise ValueError('ASHA promotion/new allocation differs')
        i,target=running;row=record['update']
        close(row['x'],latest[i]['x'],atol=0,rtol=0)
        latest[i]=row
        expected_decision=None
        if row['step']==target:
            populations[target][i]=row['loss'];paused[i]=target
            expected_decision='stop' if target==8 else 'pause'
            running=None
        if record['decision']!=expected_decision:
            raise ValueError('ASHA rung report differs')


def verify_ifbo(initial,seed,arm,directory):
    latest,history={},[]
    rng=np.random.RandomState(seed)
    initial_x=float(rng.uniform())
    close(arm['trace'][0]['update']['x'],initial_x,atol=0,rtol=0)
    for index,record in enumerate(arm['trace']):
        row,i=record['update'],record['id']
        previous=latest.get(i)
        ident=f"{i}_{row['step']-1}"
        parent=None if previous is None else f"{i}_{row['step']-2}"
        if record['ident']!=ident or record['parent']!=parent:
            raise ValueError('ifBO resume IDs differ')
        if index:
            acq_rng=np.random.RandomState(42)
            for _ in range(index):acq_rng.uniform(-4,-1);acq_rng.randint(1,51)
            threshold=min(h[2] for h in history)*(1-10**acq_rng.uniform(-4,-1))
            horizon=int(acq_rng.randint(1,9))
            new_start=max(latest)+1
            candidates=[(k,v['x'],min(v['step']+horizon,8)) for k,v in sorted(latest.items()) if v['step']<8]
            candidates += [(new_start+k,float(rng.uniform()),horizon) for k in range(100)]
            expected=[[k,{'x':x,'fidelity':t}] for k,x,t in candidates]
            if record['queries']!=expected:
                raise ValueError('Upstream uniform candidate/horizon trace differs')
            binding=record['tensors'];path=(Path(directory)/binding['path']).resolve()
            if not path.is_relative_to(Path(directory).resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=binding['sha256']:
                raise ValueError('ifBO raw tensors changed')
            with np.load(path,allow_pickle=False) as tensors:
                borders=np.asarray(tensors['borders'],dtype=float)
                logits=np.asarray(tensors['logits'],dtype=float)
                if logits.shape!=(len(candidates),len(borders)-1) or not np.isfinite(logits).all() or not np.all(np.diff(borders)>0):
                    raise ValueError('Invalid pretrained probabilities')
                close(tensors['train_x'],[[k+1,t/8,x] for k,t,loss,x in sorted(history,key=lambda h:(h[0],h[1]))],atol=1e-7,rtol=1e-6)
                close(tensors['train_y'],[1-loss for k,t,loss,x in sorted(history,key=lambda h:(h[0],h[1]))],atol=1e-7,rtol=1e-6)
                close(tensors['test_x'],[[k+1 if k in latest else 0,t/8,x] for k,x,t in candidates],atol=1e-7,rtol=1e-6)
                pi=probability_of_improvement(logits.astype(np.float32),borders.astype(np.float32),threshold)
                close(record['probabilities'],pi,atol=5e-6,rtol=0)
            # Original pandas tie order is checked separately by exact replay.
            selected=[j for j,(k,x,t) in enumerate(candidates) if x==row['x'] and (k==i if k in latest else i==new_start)]
            if len(selected)!=1 or record['probabilities'][selected[0]]!=max(record['probabilities']):
                raise ValueError('ifBO did not execute the acquisition maximizer')
        elif i!=0 or row['step']!=1:
            raise ValueError('ifBO initial design differs')
        latest[i]=row
        history.append((i,row['step'],row['loss'],row['x']))


def verify_case(raw,directory):
    initial,seed=raw['slot']['initial'],raw['slot']['seed']
    duration=raw['ifbo']['optimization_seconds']
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<0:
        raise ValueError('Invalid optimization duration')
    if raw['ifbo']['method']!='original_ifbo_component_harness' or raw['asha']['method']!='ASHA_syne_tune_0_13_0_promotion':
        raise ValueError('Reference method identity differs')
    a=verify_updates(initial,raw['ifbo']);b=verify_updates(initial,raw['asha'])
    verify_asha(initial,seed,raw['asha']);verify_ifbo(initial,seed,raw['ifbo'],directory)
    eta,best=optimum(initial)
    if min(a,b)<best-2e-12:
        raise ValueError('Reported loss is below the known global optimum')
    passes=a<=b+2e-12+2e-10*abs(b)
    return {'id':raw['slot']['id'],'ifbo_loss':a,'asha_loss':b,'gap':a-b,
            'optimal_eta':eta,'optimal_loss':best,'passes':passes,'gradient_updates':64}
