"""Quadrature and exact-trajectory oracle for retained numerical PriorBand runs."""
from collections import Counter
from fractions import Fraction as Q
import math

from scipy.integrate import quad

from validation.multifidelity_reference import close
from validation.prior_reference import verify as verify_integer_training


def trajectory(eta, step):
    eta=Q(eta)
    return (1-eta)**(2*step)/100+(1-3*eta)**(2*step)


def verify_continuous(raw):
    summary,snapshot=raw['summary'],raw['snapshot']
    trials=snapshot['trials']
    results={row['trial']['trial_id']:row['result'] for row in raw['endpoints']}
    roots=[tid for tid in trials if snapshot['roots'][tid]==tid]
    if len(roots)!=21 or len(results)!=33 or set(results)!=set(trials):
        raise ValueError('Incomplete continuous Hyperband cycle')
    if [trials[tid]['fidelity'] for tid in roots]!=[8]+[1]*8+[2]*4+[4]*4+[8]*4:
        raise ValueError('Initial continuous bracket allocation differs')
    if trials[roots[0]]['config']['values']['eta']!=summary['default']:
        raise ValueError('Default-at-target configuration differs')
    counts=Counter()
    steps={tid:[] for tid in trials}
    for update in raw['updates']:
        tid,eta,step=update['trial_id'],update['eta'],update['step']
        if eta!=trials[tid]['config']['values']['eta']:
            raise ValueError('Training update changed its learning rate')
        close(update['value'],trajectory(eta,step))
        state=update['checkpoint']
        if state['iterations']!=step or state['gradient_steps']!=step or state['eta']!=eta:
            raise ValueError('Training checkpoint identity or work differs')
        a,b=(1-Q(eta))**step/10,(1-3*Q(eta))**step
        close(state['state'][0],Q(3,5)*a-Q(4,5)*b)
        close(state['state'][1],Q(4,5)*a+Q(3,5)*b)
        counts[tid]+=1
        steps[tid].append(step)
    for tid,trial in trials.items():
        target=int(trial['fidelity'])
        parent=trial['parent_trial_id']
        start=int(trials[parent]['fidelity']) if parent else 0
        if trial['resume_from']!=start or steps[tid]!=list(range(start+1,target+1)):
            raise ValueError('Continuation duplicated or omitted work')
        close(results[tid]['cost'],counts[tid])
        close(results[tid]['objective_value'],trajectory(trial['config']['values']['eta'],target))
        if results[tid]['status']!=('completed' if target==8 else 'paused'):
            raise ValueError('Wrong endpoint status')
    if sum(counts.values())!=100:
        raise ValueError('Continuous physical update total differs')
    close(summary['accounted_cost'],100)
    close(summary['physical_updates'],100)
    offset=1
    brackets=snapshot['scheduler_state']['brackets']
    if len(brackets)!=4:
        raise ValueError('Missing bracket')
    for start,widths in enumerate([[8,4,2,1],[4,2,1],[4,2],[4]]):
        members=roots[offset:offset+widths[0]]
        offset+=widths[0]
        bracket=brackets[start]
        if bracket['roots']!=members or bracket['widths']!=widths or bracket['start']!=start:
            raise ValueError('Numerical bracket allocation differs')
        expected={}
        for rung in range(start,3):
            members=sorted(members,key=lambda tid:trajectory(trials[tid]['config']['values']['eta'],2**rung))[:widths[rung-start+1]]
            expected[str(rung)]=members
        if bracket['selected']!=expected:
            raise ValueError('Promotions differ from exact continuous trajectories')
    best=min(trajectory(trials[tid]['config']['values']['eta'],8) for tid in results if trials[tid]['fidelity']==8)
    close(summary['best_value'],best)
    # J8 is strictly convex: J8''=240*.01*(1-eta)^14 + 2160*(1-3*eta)^14 > 0.
    # J8'=0 implies (3*eta-1)/(1-eta) = (1/300)^(1/15).
    ratio=(1/300)**(1/15)
    optimum=(1+ratio)/(3+ratio)
    derivative=-.16*(1-optimum)**15-48*(1-3*optimum)**15
    if abs(derivative)>1e-15 or not .025<optimum<.625 or float(best)<float(trajectory(optimum,8))-1e-15:
        raise ValueError('Analytic outer optimum is inconsistent')
    return {'name':summary['name'],'physical_updates':100,'evaluations':33,
            'analytic_optimal_eta':optimum,'analytic_optimal_value':float(trajectory(optimum,8)),
            'observed_best_value':float(best)}


def verify_portfolio(raw):
    summary,snapshot=raw['summary'],raw['snapshot']
    searcher=snapshot['searcher_state']
    trials=snapshot['trials']
    continuous=summary['distribution'].startswith('continuous-')
    key='eta' if continuous else 'eta_index'
    low,high=(.025,.625) if continuous else (1,25)
    logarithmic='log' in summary['distribution']
    trans=math.log if logarithmic else float
    lo,hi=trans(low),trans(high)
    sigma=(hi-lo)/4
    default=summary['default']

    def score(value,center):
        mu=trans(center)
        a,b=(lo-mu)/sigma,(hi-mu)/sigma
        normalizer=quad(lambda z:math.exp(-z*z/2),a,b,epsabs=1e-13,epsrel=1e-13)[0]
        return math.exp(-.5*((trans(value)-mu)/sigma)**2)/normalizer

    maximum_error=0.0
    if len(searcher['contexts'])!=21 or searcher['contexts'][0]!={'default_at_target':True}:
        raise ValueError('Missing full-cycle proposal contexts')
    for context in searcher['contexts'][1:]:
        rows,latest={},{}
        for event in searcher['policy']['events'][:context['policy_events']]:
            tid=event['trial_id']
            if event['action']=='begin':
                rows[tid]={'root':event['root'],'rung':event['rung'],'status':'pending'}
                latest[event['root']]=tid
            elif event['action']=='observe':
                rows[tid].update(status=event['status'],value=event['value'])
            else:
                raise ValueError('Unknown policy event')
        completed=[row for row in rows.values() if row['status']=='completed']
        current=[rows[tid] for tid in latest.values() if rows[tid]['status']=='completed']
        root=min(current,key=lambda row:row['value'])['root'] if current else None
        if context['incumbent']!=root:
            raise ValueError('Numerical incumbent differs')
        center=trials[root]['config']['values'][key] if root else default
        a,b=2/3,1/3
        for rung in [8,4,2,1]:
            candidates=[row for row in completed if row['rung']==rung]
            if len(candidates)<2:
                continue
            top=sorted(candidates,key=lambda row:row['value'])[:max(len(candidates)//2,2)]
            totals=[sum((len(top)-i)*score(trials[row['root']]['config']['values'][key],c)
                        for i,row in enumerate(top)) for c in [default,center]]
            a,b=[t/sum(totals) for t in totals]
            break
        if not (any(row['rung']==8 for row in completed) and sum(row['rung'] for row in current)>=20):
            a,b=1.,0.
        random=1/(1+2**context['rung_index'])
        expected={'random':random,'prior':(1-random)*a,'inc':(1-random)*b}
        for key_weight,value in expected.items():
            actual=float(Q(context['mixture'][key_weight]))
            maximum_error=max(maximum_error,abs(actual-value))
            if abs(actual-value)>5e-14:
                raise ValueError('Numerical mixture differs from direct quadrature reference')
    return {'mixtures_reconstructed':20,'maximum_weight_error':maximum_error}


def verify(raw):
    if raw['summary']['distribution'].startswith('continuous-'):
        result=verify_continuous(raw)
    else:
        result=verify_integer_training(raw,reconstruct_mixtures=False)
        result.pop('trace')
        result.pop('laws')
    return {**result,**verify_portfolio(raw)}
