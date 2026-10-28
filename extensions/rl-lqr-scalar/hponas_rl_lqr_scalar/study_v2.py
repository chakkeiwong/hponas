"""Bounded full-procedure replications with objective-based joint candidate trials."""
from copy import deepcopy
from pathlib import Path
import numpy as np

from hponas_rl_bgpbt.explorer import sample_config
from hponas_rl_bgpbt.explorer_v2 import JointExplorer
from hponas_rl_bgpbt.study import CALIBRATION_CONFIG, checkpoint, total_work
from .tasks import run_task, task, read, write


def objective_order(results):
    return sorted(range(len(results)),key=lambda i:(results[i]['score']['cost'],i))


def selection(results):
    eligible=[r for r in results if r['work']['sac_updates']>0]
    if not eligible: raise ValueError('No trained checkpoint eligible for selection')
    winner=min(eligible,key=lambda r:(r['score']['cost'],r['task']['directory']))
    return {'config':winner['task']['config'],'task':winner['task']['directory'],
            'cost':winner['score']['cost']}


def population_search_v2(out,executor,seed,segment=4096,case='scalar3'):
    if segment not in (256,4096): raise ValueError('Reviewed segment size required')
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    initial=[deepcopy(CALIBRATION_CONFIG)]+[sample_config(rng) for _ in range(3)]
    seeds=[seed*10+i for i in range(4)]
    explorer=JointExplorer(seed+1); latest=[None]*4; results=[]; events=[]; snapshots=[]
    for round_id in range(4):
        latest=executor.map(run_task,[task(out/f'population-r{round_id}-m{i}',
            'fresh' if old is None else 'train',initial[i] if old is None else old['task']['config'],
            seeds[i],segment,case=case,input_path=None if old is None else checkpoint(old))
            for i,old in enumerate(latest)])
        results.extend(latest)
        for r in latest: explorer.observe(r['task']['config'],round_id,r['before_score']['cost'],r['score']['cost'])
        explorer.finish_round(round_id,[r['score']['cost'] for r in latest])
        ranking=objective_order(latest); teacher=latest[ranking[0]]
        snapshots.append({'segment':round_id,'members':[r['task']['directory'] for r in latest],
                          'costs':[r['score']['cost'] for r in latest],'ranking':ranking})
        if round_id in (0,2):
            configs,proposal=explorer.propose(teacher['task']['config'],round_id+.5,teacher['score']['cost'])
            child=executor.map(run_task,[task(out/f'copy-r{round_id}','copy',configs[0],seed*100+round_id,
                case=case,input_path=checkpoint(teacher))])[0]
            results.append(child); latest[ranking[-1]]=child
            events.append({'kind':'compatible_exploit','segment':round_id,'donor':ranking[0],
                'recipient':ranking[-1],'proposal':proposal,'result':child['task']['directory']})
        if round_id==1:
            configs,proposal=explorer.propose(teacher['task']['config'],1.5,teacher['score']['cost'],architecture=True,count=4)
            # Each joint configuration receives the same transfer and real SAC work.
            candidates=executor.map(run_task,[task(out/f'generation-c{i}-rung0','distill',c,
                seed*1000+i,segment//2,case=case,input_path=checkpoint(teacher),distillation_steps=64)
                for i,c in enumerate(configs)])
            results.extend(candidates)
            for r in candidates: explorer.observe(r['task']['config'],1.5,r['before_score']['cost'],r['score']['cost'])
            order=objective_order(candidates); kept=order[:2]
            students=executor.map(run_task,[task(out/f'generation-c{i}-rung1','train',configs[i],
                seed*1000+i,segment//2,case=case,input_path=checkpoint(candidates[i])) for i in kept])
            results.extend(students)
            for r in students: explorer.observe(r['task']['config'],1.75,r['before_score']['cost'],r['score']['cost'])
            for recipient,student in zip(ranking[-2:],students): latest[recipient]=student
            events.append({'kind':'architecture_generation','segment':1,'donor':ranking[0],
                'recipients':ranking[-2:],'proposal':proposal,'candidate_results':[r['task']['directory'] for r in candidates],
                'halving_order':order,'kept':kept,'criterion':'fixed_validation_regret_after_sac',
                'student_results':[r['task']['directory'] for r in students]})
    # Static search receives equal transitions and gradient-component work, and
    # retains intermediate checkpoints too. Transfer initialization is not repeated.
    baseline=[]; base_latest=[None]*4
    for round_id,length in enumerate([segment]*4+[3*segment//4]):
        base_latest=executor.map(run_task,[task(out/f'baseline-r{round_id}-m{i}',
            'fresh' if old is None else 'train',c,seeds[i],length,case=case,
            input_path=None if old is None else checkpoint(old),extra_updates=48 if round_id==4 else 0)
            for i,(c,old) in enumerate(zip(initial,base_latest))])
        baseline.extend(base_latest)
    result={'schema':3,'passed':True,'seed':seed,'case':case,'segment_transitions':segment,'initial_configs':initial,
        'initial_seeds':seeds,'population_results':[r['task']['directory'] for r in results],
        'baseline_results':[r['task']['directory'] for r in baseline],'events':events,'snapshots':snapshots,
        'selected':{'bgpbt':selection(results),'baseline':selection(baseline),'default':selection(baseline[::4])},
        'selection_rule':'best_evaluated_trained_checkpoint','work':{'bgpbt':total_work(results),'baseline':total_work(baseline)},
        'estimand':'complete_tuning_procedure','global_optimum':False,'all_attempts_retained':True}
    for key in ('transitions','gradient_components'):
        if result['work']['bgpbt'][key]!=result['work']['baseline'][key]: raise ValueError('Budget mismatch')
    path=out/'selection-freeze.json'
    if path.exists() and read(path)!=result: raise ValueError('Replayed procedure differs')
    write(path,result)
    return result
