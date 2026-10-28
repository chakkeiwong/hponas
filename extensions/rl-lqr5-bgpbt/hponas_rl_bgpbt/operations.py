"""Reviewed stage allocations; no adaptive expansion of scientific budget."""
import os
from pathlib import Path
import subprocess

import numpy as np

from hponas.executors.resource_executor import ResourceExecutor
from hponas.executors.resources import ResourceSpec
from .study import CALIBRATION_CONFIG, CONFIRMATION_SEEDS, checkpoint, population_search, total_work
from .tasks import read, run_task, sha, task, write

ROOT=Path(__file__).resolve().parents[3]
EXT=ROOT/'extensions/rl-lqr5-bgpbt'
BASE=ROOT/'docs/program/evidence/2026-10-27/rl-lqr-03'


def evidence(role):
    record=read(EXT/'results-index.json')[role]; path=ROOT/record['path']
    if sha(path)!=record['sha256']: raise ValueError('Evidence index binding differs: '+role)
    return path


def executor(gpu_ids=()):
    return ResourceExecutor(2,resources=ResourceSpec(gpus=int(bool(gpu_ids))),
        cpu_ids=sorted(os.sched_getaffinity(0))[:2],gpu_ids=gpu_ids,timeout=600)


def calibration(out):
    seeds=[101,102]; curves=[]; latest=[None,None]; results=[]
    with executor() as pool:
        for budget in (0,2048,4096,8192):
            requests=[task(out/f'seed{s}-n{budget}','fresh' if previous is None else 'train',
                CALIBRATION_CONFIG,s,budget-(0 if previous is None else previous['after']['transitions']),
                input_path=None if previous is None else checkpoint(previous)) for s,previous in zip(seeds,latest)]
            latest=pool.map(run_task,requests); results.extend(latest)
            curves.append({'transitions':budget,'costs':[r['score']['cost'] for r in latest],
                           'sac_updates':[r['after']['sac_updates'] for r in latest]})
    chosen=8192 if np.median(curves[-1]['costs'])<np.median(curves[-2]['costs']) else 4096
    result={'passed':True,'config':CALIBRATION_CONFIG,'seeds':seeds,'curves':curves,
        'budget_per_member':chosen,'rule':'8192 if final median improves from 4096; else 4096',
        'confirmation_seeds':CONFIRMATION_SEEDS,'work':total_work(results),
        'tasks':[r['task']['directory'] for r in results],
        'success_threshold':None,'scientific_claim':'learning curves only; no universal guarantee'}
    write(out/'calibration-result.json',result)
    print(result,flush=True)


def search(out):
    cal=evidence('calibration'); budget=read(cal)['budget_per_member']
    with executor() as pool: result=population_search(out/'study',pool,budget)
    result['calibration_binding']={'path':str(cal.relative_to(ROOT)),'sha256':sha(cal)}
    write(out/'search-result.json',result)
    print({'selected':result['selected'],'work':result['work']},flush=True)


def confirmation(out):
    frozen=evidence('search'); selection=read(frozen)
    if selection['confirmation']['seeds']!=CONFIRMATION_SEEDS: raise ValueError('Reserved seeds changed')
    budget=selection['confirmation']['budget']
    with executor() as pool:
        results=pool.map(run_task,[task(out/f'{method}-{seed}','fresh',selection['selected'][method]['config'],
            seed,budget) for seed in CONFIRMATION_SEEDS for method in ('bgpbt','baseline')])
    costs={method:[r['score']['cost'] for r in results if Path(r['task']['directory']).name.startswith(method+'-')]
           for method in ('bgpbt','baseline')}
    differences=[a-b for a,b in zip(costs['bgpbt'],costs['baseline'])]
    result={'passed':True,'selection_binding':{'path':str(frozen.relative_to(ROOT)),'sha256':sha(frozen)},
        'estimand':'fresh_training_of_final_static_config','seeds':CONFIRMATION_SEEDS,'budget':budget,
        'costs':costs,'paired_cost_differences_bgpbt_minus_baseline':differences,
        'means':{k:float(np.mean(v)) for k,v in costs.items()},
        'standard_deviations':{k:float(np.std(v,ddof=1)) for k,v in costs.items()},
        'work':total_work(results),'tasks':[r['task']['directory'] for r in results],
        'universal_reliability_established':False,'global_optimum':False}
    write(out/'confirmation-result.json',result); print(result,flush=True)


def hardware(out):
    from .hardware import admit
    admission=admit()
    write(out/'hardware-admission.json',admission)
    if not admission['passed']: raise RuntimeError('Two GPUs with 4 GiB free memory unavailable')
    gpu_ids=admission['selected_gpu_ids']
    with executor(tuple(gpu_ids)) as pool:
        results=pool.map(run_task,[task(out/f'gpu-{i}','fresh',CALIBRATION_CONFIG,611+i,512,
                             barrier=str(out/'barrier')) for i in range(2)])
        from .explorer import Explorer
        explorer=Explorer(615)
        for r in results:
            explorer.observe(r['task']['config'],0,r['before_score']['cost'],r['score']['cost'])
        teacher=min(results,key=lambda r:r['score']['cost'])
        rates,rate_proposal=explorer.propose(teacher['task']['config'],1,teacher['score']['cost'])
        shapes,shape_proposal=explorer.propose(teacher['task']['config'],1,teacher['score']['cost'],architecture=True)
        if all(shapes[0][k]==teacher['task']['config'][k] for k in ('actor_hiddens','critic_hiddens')):
            raise ValueError('GPU changed-shape witness did not change shape')
        descendants=pool.map(run_task,[
            task(out/'gpu-compatible','copy',rates[0],621,256,input_path=checkpoint(teacher),
                 barrier=str(out/'transfer-barrier')),
            task(out/'gpu-distilled','distill',shapes[0],622,256,input_path=checkpoint(teacher),
                 distillation_steps=64,barrier=str(out/'transfer-barrier'))])
    # Restore the first GPU checkpoint on CPU and continue; exact cross-device RNG
    # continuation is deliberately not claimed (CPU/CUDA kernels differ).
    with executor() as pool:
        restored=pool.map(run_task,[task(out/'cpu-resume','train',CALIBRATION_CONFIG,611,256,
                                          input_path=checkpoint(results[0]))])[0]
    overlap=min(r['training_finished_epoch'] for r in results)-max(r['training_started_epoch'] for r in results)
    if overlap<=0 or results[0]['pid']==results[1]['pid']: raise ValueError('No simultaneous GPU training')
    if any(r['after']['device']!='cuda:0' for r in results): raise ValueError('Learner not on assigned GPU')
    transfer_overlap=min(r['training_finished_epoch'] for r in descendants)-max(r['training_started_epoch'] for r in descendants)
    if transfer_overlap<=0 or any(r['after']['device']!='cuda:0' for r in descendants):
        raise ValueError('Transferred GPU members did not train concurrently')
    if not any(r['cuda_visible_devices']!=teacher['cuda_visible_devices'] for r in descendants):
        raise ValueError('No cross-GPU checkpoint transfer witnessed')
    result={'passed':True,'admission':admission,'training_overlap_seconds':overlap,
        'physical_gpu_ids':gpu_ids,'results':[r['task']['directory'] for r in results],
        'descendants':[r['task']['directory'] for r in descendants],
        'transfer_training_overlap_seconds':transfer_overlap,
        'rate_proposal':rate_proposal,'shape_proposal':shape_proposal,
        'cpu_resume':restored['task']['directory'],'work':total_work(results+descendants+[restored]),
        'cross_device_random_trajectory_equivalence':False}
    write(out/'hardware-result.json',result); print(result,flush=True)


def procedure_check(out):
    from itertools import product
    from .study_v2 import population_search_v2
    reports=[]
    with executor() as pool:
        for seed in (9211,9212,9213):
            report=population_search_v2(out/f'seed-{seed}',pool,seed)
            reports.append(report)
            print({'seed':seed,'selected':report['selected'],'work':report['work']},flush=True)
    differences=[r['selected']['bgpbt']['cost']-r['selected']['baseline']['cost'] for r in reports]
    statistic=abs(float(np.mean(differences)))
    null=[abs(float(np.mean(np.array(sign)*differences))) for sign in product((-1,1),repeat=3)]
    result={'passed':True,'estimand':'complete_tuning_procedure','seeds':[9211,9212,9213],
        'studies':[str(out/f'seed-{seed}/selection-freeze.json') for seed in (9211,9212,9213)],
        'paired_cost_differences_bgpbt_minus_baseline':differences,
        'mean_difference':float(np.mean(differences)),
        'difference_range':[min(differences),max(differences)],
        'paired_sign_randomization_two_sided_p':sum(v>=statistic-1e-15 for v in null)/8,
        'inference_limit':'Three paired search seeds; sign-exchangeability diagnostic, no universal superiority claim.',
        'new_architecture_winners':[not any(all(r['selected']['bgpbt']['config'][k]==c[k]
            for k in ('actor_hiddens','critic_hiddens')) for c in r['initial_configs']) for r in reports],
        'global_optimum':False,'superiority_established':False}
    write(out/'procedure-check-result.json',result)
    print(result,flush=True)


def documentation(out):
    from .delivery import build
    build(out)


def audit(out):
    from .audit import audit as run
    run(out)


def master_audit(out):
    from .audit import master_audit as run
    run(out)


def selection_reconciliation(out):
    from .reconciliation import run
    run(out)


OPERATIONS={'calibration':calibration,'search':search,'confirmation':confirmation,'hardware':hardware,
            'documentation':documentation,'hardware-documentation':documentation,
            'audit':audit,'master-audit':master_audit,'procedure-check':procedure_check,
            'selection-reconciliation':selection_reconciliation}
