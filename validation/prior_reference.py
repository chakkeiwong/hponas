"""Independent rational reconstruction of the one-coordinate PriorBand example.

This verifier does not import the prior sampler, policy or scheduler. Its fixed
fixture has 25 categories, medium confidence, eta=2 and fidelities 1,2,4,8.
The optimizer executes numerical gradient updates; the verifier uses the closed
form solution and finite probability algebra.
"""
from collections import Counter
from fractions import Fraction as Q

from validation.multifidelity_reference import checkpoint, close, value


def mixture(context, events, trials, default):
    rows, latest = {}, {}
    for event in events[:context['policy_events']]:
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
    incumbent=min(current,key=lambda row:row['value'])['root'] if current else None
    center=trials[incumbent]['config']['values']['eta_index'] if incumbent else default
    prior=[Q(4 if i==default else 1,28) for i in range(1,26)]
    inc_prior=[Q(4 if i==center else 1,28) for i in range(1,26)]
    a,b=Q(2,3),Q(1,3)
    for rung in [8,4,2,1]:
        candidates=[row for row in completed if row['rung']==rung]
        if len(candidates)<2:
            continue
        selected=sorted(candidates,key=lambda row:row['value'])[:max(len(candidates)//2,2)]
        a=b=Q(0)
        for weight,row in zip(range(len(selected),0,-1),selected):
            index=trials[row['root']]['config']['values']['eta_index']-1
            a+=weight*prior[index]
            b+=weight*inc_prior[index]
        a,b=a/(a+b),b/(a+b)
        break
    # First bracket continuation work: 8*1 + 4*(2-1) + 2*(4-2) + (8-4).
    if not (any(row['rung']==8 for row in completed) and sum(row['rung'] for row in current)>=20):
        a,b=Q(1),Q(0)
    random=Q(1,1+2**context['rung_index'])
    expected={'random':random,'prior':(1-random)*a,'inc':(1-random)*b}
    if {k:Q(v) for k,v in context['mixture'].items()}!=expected or context['incumbent']!=incumbent:
        raise ValueError('Reference portfolio or incumbent differs')
    # A single coordinate fails to mutate with probability 1/2 per attempt.
    unchanged=Q(1,2)**50
    mutation=[unchanged if i==center else (1-unchanged)/24 for i in range(1,26)]
    scores=[expected['prior']*p+expected['inc']*m for p,m in zip(prior,mutation)]
    if [Q(x) for x in context['weights']]!=scores or Q(context['alpha'])!=1-random:
        raise ValueError('Frozen rejection law differs from the exact portfolio')
    masses=[random/25+score for score in scores]
    if sum(masses)!=1 or any(mass<random/25 for mass in masses):
        raise ValueError('Invalid normalized law or uniform guard')
    return list(map(str,masses))


def verify(raw, *, reconstruct_mixtures=True):
    summary,snapshot=raw['summary'],raw['snapshot']
    trials=snapshot['trials']
    results={row['trial']['trial_id']:row['result'] for row in raw['endpoints']}
    roots=[tid for tid in trials if snapshot['roots'][tid]==tid]
    if len(roots)!=21 or len(results)!=33 or set(results)!=set(trials):
        raise ValueError('Incomplete single-cycle fixture')
    if [trials[tid]['fidelity'] for tid in roots]!=[8]+[1]*8+[2]*4+[4]*4+[8]*4:
        raise ValueError('Initial default/bracket allocation differs')
    counts=Counter()
    steps={tid:[] for tid in trials}
    for update in raw['updates']:
        tid,index,step=update['trial_id'],update['eta_index'],update['step']
        if index!=trials[tid]['config']['values']['eta_index']:
            raise ValueError('Physical update configuration differs')
        close(update['value'],value(index,step))
        checkpoint(update['checkpoint'],index,step)
        counts[tid]+=1
        steps[tid].append(step)
    for tid,trial in trials.items():
        start=int(trial['resume_from'])
        target=int(trial['fidelity'])
        if steps[tid]!=list(range(start+1,target+1)):
            raise ValueError('Missing or duplicated physical training update')
        result=results[tid]
        if result['status']!=('completed' if target==8 else 'paused') or result['fidelity']!=target:
            raise ValueError('Endpoint status or fidelity differs')
        close(result['cost'],counts[tid])
        close(result['objective_value'],value(trial['config']['values']['eta_index'],target))
        parent=trial['parent_trial_id']
        expected_start=trials[parent]['fidelity'] if parent and summary['continuation']=='resume' else 0
        if start!=expected_start:
            raise ValueError('Continuation prefix differs')
    expected_work=128 if summary['continuation']=='restart' else 100
    if sum(counts.values())!=expected_work:
        raise ValueError('One-cycle physical work differs from derived allocation')
    close(summary['physical_updates'],expected_work)
    close(summary['accounted_cost'],expected_work)
    brackets=snapshot['scheduler_state']['brackets']
    if len(brackets)!=4:
        raise ValueError('Incomplete Hyperband cycle')
    offset=1
    for start,widths in enumerate([[8,4,2,1],[4,2,1],[4,2],[4]]):
        bracket=brackets[start]
        members=roots[offset:offset+widths[0]]
        offset+=widths[0]
        if bracket['roots']!=members or bracket['widths']!=widths or bracket['start']!=start:
            raise ValueError('Bracket allocation differs from pinned floor rule')
        expected={}
        for rung in range(start,3):
            members=sorted(members,key=lambda tid:value(trials[tid]['config']['values']['eta_index'],2**rung))[:widths[rung-start+1]]
            expected[str(rung)]=members
        if bracket['selected']!=expected:
            raise ValueError('Promotion winners differ from exact quadratic ranking')
    full=sorted({trials[tid]['config']['values']['eta_index'] for tid,result in results.items()
                 if result['status']=='completed'})
    optimum=min(range(1,26),key=lambda i:value(i,8))
    best=min(full,key=lambda i:value(i,8))
    if (summary['full_fidelity_indices']!=full or summary['exact_optimal_index']!=optimum
            or summary['best_index']!=best or summary['optimum_reached']!=(optimum in full)):
        raise ValueError('Tuning summary differs from exact full-domain optimum')
    close(summary['best_value'],value(best,8))
    laws=[]
    if not summary['uniform']:
        searcher=snapshot['searcher_state']
        default=summary['default']
        if trials[roots[0]]['config']['values']['eta_index']!=default:
            raise ValueError('First default was not evaluated at full fidelity')
        if len(searcher['contexts'])!=21 or searcher['contexts'][0]!={'default_at_target':True}:
            raise ValueError('Missing proposal laws')
        if reconstruct_mixtures:
            for context in searcher['contexts'][1:]:
                laws.append(mixture(context,searcher['policy']['events'],trials,default))
    trace=[(trials[tid]['config']['values']['eta_index'],result['fidelity'],result['objective_value'])
           for tid,result in results.items()]
    return {'name':summary['name'],'physical_updates':expected_work,'evaluations':len(results),
            'mixtures_reconstructed':len(laws),'laws':laws,'trace':trace,
            'best_index':best,'exact_optimal_index':optimum,'optimum_reached':optimum in full}
