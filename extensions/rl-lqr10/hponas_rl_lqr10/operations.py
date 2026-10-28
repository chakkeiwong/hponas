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
EXT=ROOT/'extensions/rl-lqr10'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-04'
SEEDS=(10301,10302,10303)
EXPECTED=dict(transitions=466944,sac_updates=115776,distillation_updates=768,gradient_components=465408)


def score_actor(path,count=16384,seed=1030002,arrays=False):
    actor=torch.jit.load(str(path),map_location='cpu').eval()
    return sample_policy(lambda x,t:action_rows(actor,x,t),count=count,seed=seed,return_arrays=arrays)


def bind(path):
    path=Path(path)
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path))


def evidence(role):
    b=read(EXT/'results-index.json')[role];p=ROOT/b['path']
    if sha(p)!=b['sha256']:raise ValueError('Evidence index changed: '+role)
    return p


def study(out):
    oracle=oracle_report();write(out/'oracle.json',oracle)
    reports=[]
    with ResourceExecutor(2,resources=ResourceSpec(),cpu_ids=sorted(os.sched_getaffinity(0))[:2],timeout=600) as pool:
        for seed in SEEDS:
            report=population_search_v2(out/f'seed-{seed}',pool,seed,segment=4096)
            reports.append(report)
            print(json.dumps(dict(seed=seed,selected=report['selected'],work=report['work'])),flush=True)
    # Selection freezes for all three pairs exist before any test outcomes are read.
    freezes=[bind(out/f'seed-{seed}/selection-freeze.json') for seed in SEEDS]
    write(out/'all-selections-frozen.json',dict(seeds=SEEDS,selection_bindings=freezes,test_seed=1030002,test_paths=16384))
    tests=[]
    for report in reports:
        pair={}
        arrays={}
        for method in ('bgpbt','baseline'):
            chosen=report['selected'][method];path=Path(chosen['task'])/'actor.pt'
            result=score_actor(path,arrays=True)
            arrays[method]=result.pop('path_gaps')
            result.pop('path_costs');result.pop('regret_by_time')
            result.update(config=chosen['config'],actor=bind(path),validation_cost=chosen['cost'],selection_task=chosen['task'])
            pair[method]=result
        delta=arrays['bgpbt']-arrays['baseline'];mean=float(delta.mean());se=float(delta.std(ddof=1)/np.sqrt(len(delta)))
        row=dict(seed=report['seed'],methods=pair,paired_test_difference=mean,paired_test_standard_error=se,
            paired_test_normal95=[mean-1.959963984540054*se,mean+1.959963984540054*se])
        tests.append(row);print(json.dumps(dict(seed=report['seed'],test_costs={m:r['cost'] for m,r in pair.items()},paired_difference=mean)),flush=True)
    differences=[r['paired_test_difference'] for r in tests];statistic=abs(float(np.mean(differences)))
    null=[abs(float(np.mean(np.array(s)*differences))) for s in product((-1,1),repeat=3)]
    work={k:sum(r['work'][m][k] for r in reports for m in ('bgpbt','baseline')) for k in EXPECTED}
    if work!=EXPECTED:raise ValueError('Actual study work differs from frozen allocation')
    result=dict(passed=True,engineering_execution=True,states=10,horizon=30,oracle=oracle,
        seeds=SEEDS,selection_bindings=freezes,tests=tests,work=work,
        mean_paired_test_difference=float(np.mean(differences)),
        sign_randomization_diagnostic_p=sum(v>=statistic-1e-15 for v in null)/8,
        global_optimum=False,convergence_established=False,superiority_established=False,
        limitations=['Sampled nonlinear-policy expectations; exact analytical LQR reference only.',
            'Normal intervals describe finite test-path uncertainty conditional on each frozen policy.',
            'Three optimizer seeds do not prove general superiority or reliable convergence.',
            'Selected architecture/rates belong to training lineages, not validated fresh static recipes.',
            'Equal transitions/component minibatches do not imply equal FLOPs or wall time.'])
    write(out/'study-result.json',result)


def verify_task(path,reevaluate=True):
    path=Path(path);r=read(path/'result.json')
    if not r['passed']:raise ValueError('Task failed')
    for name,digest in r['artifacts'].items():
        if sha(path/name)!=digest:raise ValueError('Task artifact hash mismatch')
    state=torch.load(path/'checkpoint.pt',map_location='cpu',weights_only=False)
    if state['contract']!=LQRSpec().contract():raise ValueError('Checkpoint environment mismatch')
    if r['score']['paths']!=1024 or r['score']['evaluation_seed']!=1030001 or r['score']['exact_policy_expectation']:
        raise ValueError('Invalid selection evaluation')
    updates=r['after']['sac_updates']-r['before']['sac_updates']
    if updates!=r['work']['sac_updates'] or r['work']['transitions']!=r['task']['transitions']:
        raise ValueError('Task work mismatch')
    if reevaluate:
        actual=score_actor(path/'actor.pt',1024,1030001)
        if abs(actual['cost']-r['score']['cost'])>1e-10:raise ValueError('Saved policy score mismatch')
    return r


def audit(out):
    result_path=evidence('study');result=read(result_path);directory=result_path.parent
    fresh=oracle_report()
    if fresh!=result['oracle']:raise ValueError('Analytical reference differs')
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
        test=next(t for t in result['tests'] if t['seed']==report['seed']);deltas={}
        for method in ('bgpbt','baseline'):
            r=test['methods'][method];p=ROOT/r['actor']['path']
            if sha(p)!=r['actor']['sha256'] or str(p.parent)!=report['selected'][method]['task']:
                raise ValueError('Test policy differs from frozen winner')
            actual=score_actor(p,arrays=True);deltas[method]=actual.pop('path_gaps')
            actual.pop('path_costs');actual.pop('regret_by_time')
            if any(actual[k]!=r[k] for k in actual):raise ValueError('Test reconstruction differs')
        difference=float((deltas['bgpbt']-deltas['baseline']).mean())
        if difference!=test['paired_test_difference']:raise ValueError('Paired holdout difference differs')
        recomputed_tests.append(difference)
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
    report=dict(passed=True,tasks=len(task_results),work=work,oracle=fresh,
        reconstructed_test_differences=recomputed_tests,source_bindings=len(manifest['inputs'])+1,
        engineering_complete=True,convergence_established=False,global_optimum=False,
        scientific_outcome='Measured nonzero sampled regret; see all three frozen-policy test results.')
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
    false=deepcopy(p);next(w for w in false['work_items'] if w['id']=='RL-LQR-04')['state']='complete'
    next(s for s in false['continuation']['steps'] if s['id']=='RL-LQR-04/AUDIT')['state']='planned'
    if not validate(ROOT,program=false)[0]:raise ValueError('False-completion negative control accepted')
    write(out/'master-audit-result.json',dict(passed=True,work_items=len(p['work_items']),stages=len(stages),
        requirements=len(p['requirements']),core_source=source_digest(ROOT),false_completion_rejected=True,
        qualification='Bounded ten-state experiment; no analytical-optimum attainment or general superiority asserted.'))
