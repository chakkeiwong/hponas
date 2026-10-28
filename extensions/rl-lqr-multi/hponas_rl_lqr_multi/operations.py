"""Fixed three-pair allocation and reconstruction without retraining."""
from pathlib import Path
from itertools import product
import hashlib
import json
import os
import numpy as np
import torch
from hponas.executors.resource_executor import ResourceExecutor
from hponas.executors.resources import ResourceSpec
from hponas_rl_bgpbt.study import total_work
from .reference import LQRSpec,oracle_report,sample_policy
from .scoring import action_rows
from .study_v2 import population_search_v2,selection,objective_order
from .tasks import read,write,sha

ROOT=Path(__file__).resolve().parents[3]
EXT=ROOT/'extensions/rl-lqr-multi'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-05'
SEEDS=(10501,10502,10503)
ACTIONS=(2,3,4,5)
METHODS=("bgpbt","baseline","default")
EXPECTED=dict(transitions=1867776,sac_updates=463104,distillation_updates=3072,gradient_components=1861632)


def score_actor(path,count=16384,seed=1050002,arrays=False,actions=2):
    actor=torch.jit.load(str(path),map_location='cpu').eval()
    return sample_policy(lambda x,t:action_rows(actor,x,t),spec=LQRSpec(actions=actions),count=count,seed=seed,return_arrays=arrays)


def bind(path):
    path=Path(path)
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path))


def evidence(role):
    b=read(EXT/'results-index.json')[role];p=ROOT/b['path']
    if sha(p)!=b['sha256']:raise ValueError('Evidence index changed: '+role)
    return p


def study(out):
    oracles={str(m):oracle_report(LQRSpec(actions=m)) for m in ACTIONS}
    write(out/'oracles.json',oracles);reports=[];freezes=[]
    with ResourceExecutor(4,resources=ResourceSpec(),cpu_ids=sorted(os.sched_getaffinity(0))[:4],timeout=600) as pool:
        for m in ACTIONS:
            for seed in SEEDS:
                directory=out/f'actions-{m}'/f'seed-{seed}'
                report=population_search_v2(directory,pool,seed,segment=4096,actions=m)
                reports.append(report);freezes.append(bind(directory/'selection-freeze.json'))
                print(json.dumps(dict(actions=m,seed=seed,selected=report['selected'],work=report['work'])),flush=True)
    write(out/'all-selections-frozen.json',dict(actions=ACTIONS,seeds=SEEDS,selection_bindings=freezes,test_seed=1050002,test_paths=16384))
    tests=[]
    for report in reports:
        pair={};arrays={};m=report['actions'];oracle=oracles[str(m)]
        for method in METHODS:
            chosen=report['selected'][method];path=Path(chosen['task'])/'actor.pt'
            result=score_actor(path,arrays=True,actions=m)
            arrays[method]=result.pop('path_gaps');result.pop('path_costs');result.pop('regret_by_time')
            result.update(config=chosen['config'],actor=bind(path),validation_cost=chosen['cost'],selection_task=chosen['task'],
                relative_optimality_gap=result['gap']/oracle['optimal_cost'],
                available_improvement_recovered=(oracle['zero_action_cost']-result['cost'])/(oracle['zero_action_cost']-oracle['optimal_cost']))
            pair[method]=result
        contrasts={}
        for comparator in ('baseline','default'):
            delta=arrays['bgpbt']-arrays[comparator];mean=float(delta.mean());se=float(delta.std(ddof=1)/np.sqrt(len(delta)))
            contrasts[comparator]=dict(mean=mean,standard_error=se,normal95=[mean-1.959963984540054*se,mean+1.959963984540054*se])
        tests.append(dict(actions=m,seed=report['seed'],methods=pair,contrasts=contrasts))
        print(json.dumps(dict(actions=m,seed=report['seed'],test_costs={k:v['cost'] for k,v in pair.items()},contrasts=contrasts)),flush=True)
    work={k:sum(r['work'][m][k] for r in reports for m in ('bgpbt','baseline')) for k in EXPECTED}
    if work!=EXPECTED:raise ValueError('Actual study work differs from frozen allocation')
    result=dict(passed=True,engineering_execution=True,states=10,horizon=30,actions=ACTIONS,oracles=oracles,
        seeds=SEEDS,selection_bindings=freezes,tests=tests,work=work,
        global_optimum=False,convergence_established=False,superiority_established=False,
        limitations=['Sampled nonlinear-policy expectations; exact attainable analytical LQR reference only.',
            'Normal intervals describe test-path uncertainty conditional on each frozen policy, not optimizer randomness.',
            'Three optimizer seeds per dimension do not prove general superiority or reliable convergence.',
            'Selected architecture/rates belong to training lineages, not validated fresh static recipes.',
            'Equal transitions/component minibatches do not imply equal FLOPs or wall time.',
            'Default comparator reuses its static lineage and best validation checkpoint without additional training.',
            'Adjacent input columns and rank-one process noise are a fixed model family, not all multi-input systems.'])
    write(out/'study-result.json',result)


def verify_task(path,reevaluate=True):
    path=Path(path);r=read(path/'result.json')
    if not r['passed']:raise ValueError('Task failed')
    for name,digest in r['artifacts'].items():
        if sha(path/name)!=digest:raise ValueError('Task artifact hash mismatch')
    state=torch.load(path/'checkpoint.pt',map_location='cpu',weights_only=False)
    if state['contract']!=LQRSpec(actions=r['task']['actions']).contract():raise ValueError('Checkpoint environment mismatch')
    if r['score']['paths']!=1024 or r['score']['evaluation_seed']!=1050001 or r['score']['exact_policy_expectation']:
        raise ValueError('Invalid selection evaluation')
    updates=r['after']['sac_updates']-r['before']['sac_updates']
    if updates!=r['work']['sac_updates'] or r['work']['transitions']!=r['task']['transitions']:
        raise ValueError('Task work mismatch')
    if reevaluate:
        actual=score_actor(path/'actor.pt',1024,1050001,actions=r['task']['actions'])
        if abs(actual['cost']-r['score']['cost'])>1e-10:raise ValueError('Saved policy score mismatch')
    return r


def audit(out):
    result_path=evidence('study');result=read(result_path);directory=result_path.parent
    fresh={str(m):oracle_report(LQRSpec(actions=m)) for m in ACTIONS}
    if fresh!=result['oracles']:raise ValueError('Analytical reference differs')
    task_results=[];recomputed_tests=[]
    for frozen in result['selection_bindings']:
        path=ROOT/frozen['path']
        if sha(path)!=frozen['sha256']:raise ValueError('Selection changed after test')
        report=read(path);groups={}
        for method,key in [('bgpbt','population_results'),('baseline','baseline_results')]:
            rows=[verify_task(t) for t in report[key]];groups[method]=rows;task_results.extend(rows)
            if selection(rows)!=report['selected'][method]:raise ValueError('Winner not selected by training validation')
            if total_work(rows)!=report['work'][method]:raise ValueError('Procedure work mismatch')
        for event in report['events']:
            if event['kind']=='architecture_generation':
                candidates=[read(Path(p)/'result.json') for p in event['candidate_results']]
                if objective_order(candidates)!=event['halving_order']:raise ValueError('Halving selection differs')
                if any(r['work']['sac_updates']==0 for r in candidates):raise ValueError('Untrained joint candidate')
        if selection(groups['baseline'][::4])!=report['selected']['default']:raise ValueError('Default selection differs')
        test=next(t for t in result['tests'] if t['seed']==report['seed'] and t['actions']==report['actions']);deltas={}
        for method in METHODS:
            r=test['methods'][method];p=ROOT/r['actor']['path']
            if sha(p)!=r['actor']['sha256'] or str(p.parent)!=report['selected'][method]['task']:
                raise ValueError('Test policy differs from frozen winner')
            actual=score_actor(p,arrays=True,actions=report['actions']);deltas[method]=actual.pop('path_gaps')
            actual.pop('path_costs');actual.pop('regret_by_time')
            if any(actual[k]!=r[k] for k in actual):raise ValueError('Test reconstruction differs')
        difference=float((deltas['bgpbt']-deltas['baseline']).mean())
        if difference!=test['contrasts']['baseline']['mean']:raise ValueError('Paired holdout difference differs')
        default_difference=float((deltas['bgpbt']-deltas['default']).mean())
        if default_difference!=test['contrasts']['default']['mean']:raise ValueError('Default contrast differs')
        recomputed_tests.append(dict(actions=report['actions'],seed=report['seed'],baseline=difference,default=default_difference))
    work=total_work(task_results)
    if work!=EXPECTED or work!=result['work']:raise ValueError('Work total differs')
    ledger=[json.loads(line) for line in (directory/'work.jsonl').read_text().splitlines()]
    reservations=[r for r in ledger if r['event']=='reserve'];completions={r['id'] for r in ledger if r['event']=='complete'}
    if any(r['id'] not in completions for r in reservations):raise ValueError('Incomplete charged task')
    if any(sum(r['work'][k] for r in reservations)!=work[k] for k in ('transitions','sac_updates','distillation_updates')):
        raise ValueError('Ledger allocation mismatch')
    receipt=read(directory/'receipt.json');manifest=read(directory/'manifest.json')
    if not receipt['passed'] or receipt['remaining_children']:raise ValueError('Study runner not clean')
    for b in [manifest['runner'],*manifest['inputs']]:
        if sha(ROOT/b['path'])!=b['sha256']:raise ValueError('Study source changed')
    # Exact first paired configurations must produce identical CPU states at equal work.
    for frozen in result['selection_bindings']:
        p=(ROOT/frozen['path']).parent
        for i in range(4):
            a=read(p/f'population-r0-m{i}/result.json');b=read(p/f'baseline-r0-m{i}/result.json')
            if a['checkpoint_identity']!=b['checkpoint_identity']:raise ValueError('Paired initial conditions differ')
    if {(t['actions'],t['seed']) for t in result['tests']}!={(m,s) for m in ACTIONS for s in SEEDS}:raise ValueError('Missing dimension or seed')
    endpoints=sorted([(r['training_started_epoch'],1) for r in task_results if r['work']['transitions']]+[(r['training_finished_epoch'],-1) for r in task_results if r['work']['transitions']])
    active=0;peak=0
    for _,delta in endpoints:active+=delta;peak=max(peak,active)
    if peak<2 or peak>4:raise ValueError('Observed concurrency outside reviewed bound')
    report=dict(passed=True,observed_training_concurrency=peak,tasks=len(task_results),work=work,oracle=fresh,
        reconstructed_test_differences=recomputed_tests,source_bindings=len(manifest['inputs'])+1,
        engineering_complete=True,convergence_established=False,global_optimum=False,
        scientific_outcome='Measured nonzero sampled regret; see all twelve paired frozen-policy test results.')
    write(out/'audit-result.json',report)
    print(json.dumps(dict(passed=True,tasks=report['tasks'],work=work)),flush=True)


def master_audit(out):
    from tools.program_state import check,source_digest
    p=read(ROOT/'docs/program/program.json');errors,view=check(ROOT)
    if errors:raise ValueError(errors)
    stages=p['continuation']['steps'];final=next(s for s in stages if s['id']=='GAP-01/FINAL-AUDIT')
    if any(s['state']!='complete' for s in stages if s['id']!=final['id']):raise ValueError('Other required stages unfinished')
    if not read(evidence('audit'))['passed']:raise ValueError('Missing extension audit')
    from copy import deepcopy
    from tools.program_state import validate
    false=deepcopy(p);next(w for w in false['work_items'] if w['id']=='RL-LQR-05')['state']='complete'
    next(s for s in false['continuation']['steps'] if s['id']=='RL-LQR-05/AUDIT')['state']='planned'
    if not validate(ROOT,program=false)[0]:raise ValueError('False-completion negative control accepted')
    write(out/'master-audit-result.json',dict(passed=True,work_items=len(p['work_items']),stages=len(stages),
        requirements=len(p['requirements']),core_source=source_digest(ROOT),false_completion_rejected=True,
        qualification='Bounded ten-state experiment; no analytical-optimum attainment or general superiority asserted.'))
