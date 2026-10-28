"""Independent multidimensional score, controller and evidence reconstruction."""
from copy import deepcopy
from pathlib import Path
import json,hashlib,math
import numpy as np
import torch
from .experiments import ROOT,BASE,CASES,METHODS,read,write,bind
from .adapter import SACMember,Actor
from .reference import LQRSpec,riccati,condensed_reference,sample_paths
from hponas_rl_lqr_scalar.scoring import action_rows

def forbid(*a,**k):raise RuntimeError('Audit cannot train')
def bound(b):
    if bind(ROOT/b['path'])!=b:raise ValueError('Artifact changed: '+b['path'])

def verify_score(reconstructed, stored, label=''):
    for actual, reported, tolerance in [('cost','cost',1e-9),
            ('se','gap_standard_error',1e-10),('direct','direct_rollout_mean',1e-9)]:
        a,b=reconstructed[actual],stored[reported]
        if not math.isfinite(a) or not math.isfinite(b) or abs(a-b)>=tolerance:
            raise ValueError(f'Score reconstruction mismatch {label}: {actual} {a!r} != {b!r}')

def independent_cost(actor,spec,count,seed):
    ref=riccati(spec);x,w=sample_paths(spec,count,seed);total=np.zeros(count);regret=np.zeros(count)
    for t in range(spec.horizon):
        u=np.asarray(action_rows(actor,x,t),dtype=np.float64);assert np.isfinite(u).all() and abs(u).max()<=1
        total+=spec.gamma**t*(np.sum(x*x,axis=1)+.1*np.sum(u*u,axis=1))
        d=u+x@ref['K'][t].T;chol=np.linalg.cholesky(ref['S'][t])
        regret+=spec.gamma**t*np.sum((d@chol)**2,axis=1)
        x=x@spec.A.T+u@spec.B.T+w[:,t]
    total+=spec.gamma**spec.horizon*np.sum(x*x,axis=1)
    return dict(cost=float(ref['optimal_cost']+regret.mean()),gap=float(regret.mean()),se=float(regret.std(ddof=1)/math.sqrt(count)),
        direct=float(total.mean()),path_gaps=regret)

def linear_backward(gains,spec):
    p=spec.Q.copy();constant=0.
    for k in reversed(gains):
        f=spec.A-spec.B@k
        constant=spec.gamma*(constant+spec.noise_vector@p@spec.noise_vector)
        p=spec.Q+k.T@spec.R@k+spec.gamma*f.T@p@f
    return float(spec.initial_scale**2*np.trace(p)+constant)

def audit(out):
    SACMember.train=forbid;SACMember._update=forbid
    import pytest
    if pytest.main([str(ROOT/'extensions/rl-lqr-scale/tests/test_controller.py'),str(ROOT/'extensions/rl-lqr-scale/tests/test_audit.py'),'-q','--disable-warnings','--basetemp',str(out/'pytest')]):raise RuntimeError('Controller or audit rejection contracts failed')
    receipts=[];totals={};snapshots=0;failed_attempts=[]
    for op in ['engineering','actions','review','states','freeze','confirm']:
        passed=[]
        for file in BASE.glob('*/receipt.json'):
            receipt=read(file)
            if receipt.get('operation')!=op:continue
            if receipt['passed']:passed.append(file)
            else:failed_attempts.append(bind(file))
        assert len(passed)==1,(op,passed)
        path=passed[0];r=read(path);directory=path.parent;m=read(directory/'manifest.json')
        assert hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()==r['manifest']['sha256']
        assert r['inputs_unchanged'] and r['core_source']==r['end_core_source'] and not r['remaining_children'] and r['stop_reason'] is None
        for b in [m['runner'],*m['inputs']]:
            assert hashlib.sha256((directory/'inputs'/b['path']).read_bytes()).hexdigest()==b['sha256'];snapshots+=1
        bound(r['log']);assert (directory/(op+'-result.json')).read_bytes()==(BASE/(op+'-result.json')).read_bytes()
        if 'work_ledger' in r:
            bound(r['work_ledger']);ledger=[json.loads(x) for x in (ROOT/r['work_ledger']['path']).read_text().splitlines()]
            reserves={x['id']:x for x in ledger if x['event']=='reserve'};completed=[x['id'] for x in ledger if x['event']=='complete']
            assert len(completed)==len(set(completed)) and set(reserves)==set(completed)
            assert not any(x['event']=='failed' for x in ledger)
            total={k:sum(x.get('work',{}).get(k,0) for x in reserves.values()) for k in r['work_limits']}
            assert total==r['charged_work'] and all(total[k]<=r['work_limits'][k] for k in total)
        else:total={k:0 for k in r['work_limits']}
        totals[op]=total;receipts.append(bind(path))
    for op,t,u in [('actions',196608,47616),('states',196608,47616),('confirm',589824,142848)]:
        assert totals[op]['transitions']==t and totals[op]['sac_updates']==u
    references={}
    for case in CASES:
        spec=LQRSpec.from_case(case);a=riccati(spec);b=condensed_reference(spec)
        assert abs(a['optimal_cost']-b['optimal_cost'])<1e-10
        assert abs(a['optimal_cost']-linear_backward(a['K'],spec))<1e-10
        references[case]=a['optimal_cost']
    sources={op:read(BASE/(op+'-result.json')) for op in ['actions','states','confirm']}
    choices=read(BASE/'freeze-result.json')['choices'];rows=sources['actions']['rows']+sources['states']['rows']
    for choice in choices:
        means={m:float(np.mean([r['curves'][-1]['score']['gap'] for r in rows if r['case']==choice['case'] and r['method']==m])) for m in METHODS}
        assert means==choice['mean_validation_gaps'] and choice['selected']==min(METHODS,key=lambda m:(means[m],METHODS.index(m)))
    cached={};controller_count=0;frozen=0;recon=[]
    for op in ['actions','states','confirm']:
        data=sources[op]
        assert len(data['rows'])==(72 if op=='confirm' else 24)
        for row in data['rows']:
            case,method,seed=row['case'],row['method'],row['seed'];spec=LQRSpec.from_case(case)
            bound(row['checkpoint']);bound(row['actor']);directory=(ROOT/row['checkpoint']['path']).parent
            sealed=read(directory/'endpoint-freeze.json');assert sealed=={k:v for k,v in row.items() if k!='test'};frozen+=1
            actor=torch.jit.load(str(ROOT/row['actor']['path'])).eval();score=row['test'] if op=='confirm' else row['curves'][-1]['score']
            z=independent_cost(actor,spec,score['paths'],score['evaluation_seed'])
            verify_score(z,score,(case,method,seed))
            member=SACMember.restore(ROOT/row['checkpoint']['path']);assert member.counters()==row['curves'][-1]['counters']
            assert member.transitions==8192 and member.updates==1984
            # Export equivalence, oddness and normal-distribution symmetry checked on independent states.
            rng=np.random.default_rng(109999);obs=torch.tensor(np.column_stack((rng.uniform(-.5,.5,(128,spec.states)),rng.uniform(1/30,1,128))),dtype=torch.float32)
            with torch.no_grad():assert torch.equal(actor(obs),Actor(member.module)(obs))
            if method=='symmetric':
                neg=obs.clone();neg[:,:-1]*=-1
                with torch.no_grad():assert torch.equal(actor(obs),-actor(neg))
                assert row['probes']['zero_action_max_abs']==0
            for saved,encoder in zip(row['greedy'],[member.module.qf_encoder,member.module.qf_twin_encoder]):
                with torch.no_grad():mat,c=encoder.continuation(torch.tensor([[(30-t)/30] for t in range(30)],dtype=torch.float32))
                matrices=mat.numpy().astype(float);gains=np.array(saved['gains']);oracle_k=riccati(spec)['K']
                for t,k in enumerate(gains):
                    normal=spec.R+spec.gamma*spec.B.T@matrices[t]@spec.B
                    rhs=spec.gamma*spec.B.T@matrices[t]@spec.A
                    assert np.max(abs(normal@k-rhs))<1e-9
                coeff=spec.initial_scale*np.eye(spec.states);bounds=[]
                for k in gains:
                    bounds.append(float(np.linalg.norm(k@coeff,ord=1,axis=1).max()))
                    coeff=np.column_stack(((spec.A-spec.B@k)@coeff,spec.noise_vector))
                assert abs(max(bounds)-saved['max_action_bound'])<1e-12
                assert saved['feasible']==(max(bounds)<=1)
                if saved['feasible']:
                    expected=linear_backward(gains,spec);assert abs(expected-saved['exact_cost'])<1e-9
                    assert expected>=references[case]-1e-10
                else:assert saved['exact_cost'] is None
                controller_count+=1
            if op=='confirm':cached[(case,method,seed)]=z
            recon.append(dict(operation=op,case=case,method=method,seed=seed,cost=z['cost']))
            write(out/'progress-audit.json',dict(endpoints=len(recon),total=120))
        for case in {r['case'] for r in data['rows']}:
            for seed in {r['seed'] for r in data['rows'] if r['case']==case}:
                assert len({r['initial_actor_hash'] for r in data['rows'] if r['case']==case and r['seed']==seed})==1
    summary=[];paired=[]
    confirmed=sources['confirm']['rows']
    for case in CASES:
        entry=dict(case=case,optimal_cost=references[case],selected=next(x['selected'] for x in choices if x['case']==case),methods={})
        for method in METHODS:
            group=[r for r in confirmed if r['case']==case and r['method']==method]
            percentages=[100*r['test']['gap']/references[case] for r in group]
            gs=[g['relative_gap_percent'] for r in group for g in r['greedy'] if g['feasible']]
            entry['methods'][method]=dict(mean_cost=float(np.mean([r['test']['cost'] for r in group])),mean_gap_percent=float(np.mean(percentages)),min_gap_percent=min(percentages),max_gap_percent=max(percentages),greedy_feasible=len(gs),greedy_count=6,greedy_mean_gap_percent=float(np.mean(gs)) if gs else None,greedy_max_gap_percent=max(gs) if gs else None)
        summary.append(entry)
        for seed in [10921,10922,10923]:
            diff=cached[(case,'symmetric',seed)]['path_gaps']-cached[(case,'matrix',seed)]['path_gaps']
            paired.append(dict(case=case,seed=seed,symmetry_minus_matrix=float(diff.mean()),paired_path_standard_error=float(diff.std(ddof=1)/math.sqrt(len(diff)))))
    # Score/artifact corruption and infeasible-controller rejection ran above.
    result=dict(passed=True,new_training=0,receipts=receipts,failed_attempts=failed_attempts,source_snapshots_verified=snapshots,work=totals,
        reconstructed_endpoints=len(recon),reconstructed_linear_controllers=controller_count,endpoint_freezes=frozen,controller_tests=5,audit_rejection_tests=10,
        summary=summary,confirmation_pairs=paired,independent_reconstructions=recon,
        limitations=['Known linear dynamics/quadratic reward and sign symmetry are fixture assumptions.',
        'Full quadratic continuation approximates bounded-action soft values; generic SAC is unqualified.',
        'Three fresh training seeds give descriptive replication, not population-wide significance.',
        'Neural actor regret remains measured; exact cost of a learned feasible linear controller does not prove neural optimality.',
        'No new BG-PBT/NAS comparison is allocated; architecture is held fixed to isolate dimensional learning.'])
    write(out/'audit-result.json',result)
    lines=['# RL-LQR-09: actions5–10, then10active states','',
        'This extension tests every action count5–10 in both the normalized scalar family and the coupled ten-state family. Both use horizon30. The full-matrix critic learns a continuation value from SAC targets with known one-step dynamics/reward. The symmetric actor adds odd means and even log standard deviations; neither receives Riccati labels.','',
        '## Fresh confirmation','',
        'Three fresh training seeds per case/method;8,192transitions each,1,984SACupdates. Fixed endpoint,16,384fresh evaluation paths. Percentages are excess expected cost relative to the attainable Riccati reference.','',
        '| States | Actions | Optimum | Matrix actor mean gap | Symmetric actor mean gap | Symmetric range | Learned greedy mean gap |','| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in summary:
        spec=LQRSpec.from_case(row['case']);a=row['methods']['matrix'];b=row['methods']['symmetric'];g=b['greedy_mean_gap_percent'];label=f'{g:.5f}%' if g is not None else 'not certified feasible'
        if b['greedy_feasible']!=6:label+=f" ({b['greedy_feasible']}/6 feasible)"
        lines.append(f"| {spec.states} | {spec.actions} | {row['optimal_cost']:.9f} | {a['mean_gap_percent']:.4f}% | {b['mean_gap_percent']:.4f}% | {b['min_gap_percent']:.4f}–{b['max_gap_percent']:.4f}% | {label} |")
    lines+=['','The learned greedy column evaluates each twin critic separately, using its learned matrix to solve a small positive-definite control system. A covariance recurrence gives exact expected cost of those gains when the all-sign action bound is feasible. This is a separate controller diagnostic, not the neural actor, and no better twin is selected from test results.','',
        '## Method selection and evidence','',
        'Two pilot seeds choose methods by mean final validation regret; every choice is sealed before confirmation. Both methods are confirmed to retain the paired effect. Same base actor parameters and random streams start each pair. Actor symmetry changes the policy function and costs two forward evaluations; matched optimizer/environment counts do not imply equal FLOPs.','',
        'The scalar family retains one common optimum as redundant actions grow. Ten-state dynamics are A=0.8I+0.12cyclic-shift,B=first m columns of I,Q=I,R=0.1I. All ten states affect reward and dynamics; this is not a padded scalar case. Analytical optima change with the number of independently actuated coordinates.','',
        '## Verification','',
        f'{len(recon)} frozen endpoints and{controller_count} learned linear controllers independently reconstructed;{snapshots}retained source snapshots verified. Oracle Riccati values agree with condensed quadratic solves and a backward policy-value calculation. All scientific allocations are once-only;983,040transitions and238,080SACupdates total. The initial engineering test incorrectly required arbitrary early learned gains to be feasible; repaired to test refusal instead,with the failed receipt retained. No scientific result was recycled.','',
        '## Limits','']
    lines+=['- '+x for x in result['limitations']]
    (ROOT/'extensions/rl-lqr-scale/RESULTS.md').write_text('\n'.join(lines)+'\n')

def master_audit(out):
    from tools.program_state import check,validate
    errors,view=check(ROOT)
    if errors:raise ValueError(errors)
    p=read(ROOT/'docs/program/program.json');assert all(s['state']=='complete' for s in p['continuation']['steps'] if s['id']!='GAP-01/FINAL-AUDIT')
    bad=deepcopy(p);next(s for s in bad['continuation']['steps'] if s['id']=='RL-LQR-09/AUDIT')['state']='planned';assert validate(ROOT,program=bad)[0]
    write(out/'master-audit-result.json',dict(passed=True,new_training=0,false_completion_rejected=True,work_items=len(p['work_items']),stages=len(p['continuation']['steps']),qualification='Dimensional study complete; neural performance and exact learned-controller costs remain distinct.'))
