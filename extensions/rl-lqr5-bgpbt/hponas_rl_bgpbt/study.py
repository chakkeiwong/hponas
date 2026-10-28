"""Synchronous four-member BG-PBT with auditable generations and work."""
from copy import deepcopy
from pathlib import Path

import numpy as np

from .explorer import Explorer, sample_config
from .tasks import read, run_task, sha, task, write

CALIBRATION_CONFIG={'actor_hiddens':[32,32],'critic_hiddens':[32,32],
                    'actor_lr':.001,'critic_lr':.001}
CONFIRMATION_SEEDS=[801,802,803]


def checkpoint(result):
    return Path(result['task']['directory'])/'checkpoint.pt'


def total_work(results):
    return {k:sum(r['work'][k] for r in results) for k in
            ('transitions','sac_updates','distillation_updates','gradient_components')}


def population_search(out,executor,budget,seed=211):
    """Replay committed tasks by deterministic ID; uncertain tasks fail closed.

    Rebuilding the controller from its seed and committed task results is exact;
    GP randomness and every proposal are recomputed and compared with the
    frozen controller record. No training is repeated on committed task replay.
    """
    if budget not in (1024,4096,8192): raise ValueError('Reviewed finite member budget required')
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(seed)
    initial=[deepcopy(CALIBRATION_CONFIG)]+[sample_config(rng) for _ in range(3)]
    seeds=[seed*10+i for i in range(4)]
    explorer=Explorer(seed+1); latest=[None]*4; results=[]; events=[]; snapshots=[]
    for segment in range(4):
        requests=[]
        for i,previous in enumerate(latest):
            config=initial[i] if previous is None else previous['task']['config']
            requests.append(task(out/f'population-r{segment}-m{i}',
                'fresh' if previous is None else 'train',config,seeds[i],budget//4,
                input_path=None if previous is None else checkpoint(previous)))
        latest=executor.map(run_task,requests); results.extend(latest)
        for result in latest:
            explorer.observe(result['task']['config'],segment,
                             result['before_score']['cost'],result['score']['cost'])
        ranking=sorted(range(4),key=lambda i:(latest[i]['score']['cost'],i))
        snapshots.append({'segment':segment,'members':[r['task']['directory'] for r in latest],
                          'costs':[r['score']['cost'] for r in latest],'ranking':ranking})
        if segment in (0,2):
            donor,worst=ranking[0],ranking[-1]; teacher=latest[donor]
            configs,record=explorer.propose(teacher['task']['config'],segment+.5,teacher['score']['cost'])
            request=task(out/f'copy-r{segment}','copy',configs[0],seed*100+segment,0,
                         input_path=checkpoint(teacher))
            child=executor.map(run_task,[request])[0]; results.append(child); latest[worst]=child
            events.append({'kind':'compatible_exploit','segment':segment,'donor':donor,'recipient':worst,
                           'proposal':record,'result':child['task']['directory']})
        if segment==1:
            donor=ranking[0]; teacher=latest[donor]
            configs,record=explorer.propose(teacher['task']['config'],segment+.5,
                                           teacher['score']['cost'],architecture=True,count=4)
            candidates=executor.map(run_task,[task(out/f'generation-c{i}-rung0','distill',c,
                seed*1000+i,0,input_path=checkpoint(teacher),distillation_steps=16)
                for i,c in enumerate(configs)])
            results.extend(candidates)
            order=sorted(range(4),key=lambda i:(sum(candidates[i]['transfer']['final_losses']),i))
            kept=order[:2]
            students=executor.map(run_task,[task(out/f'generation-c{i}-rung1','distill',configs[i],
                seed*1000+i,0,input_path=checkpoint(teacher),student=str(checkpoint(candidates[i])),
                distillation_steps=48) for i in kept])
            results.extend(students)
            for recipient,student in zip(ranking[-2:],students): latest[recipient]=student
            events.append({'kind':'architecture_generation','trigger':'maximum_age_two_segments',
                'segment':segment,'donor':donor,'recipients':ranking[-2:],'proposal':record,
                'candidate_results':[r['task']['directory'] for r in candidates],
                'halving_order':order,'kept':kept,'student_results':[r['task']['directory'] for r in students]})
        write(out/'controller-progress.json',{'last_segment':segment,'explorer':explorer.state(),
            'members':[r['task']['directory'] for r in latest],'events':events,'snapshots':snapshots})
    selected=min(range(4),key=lambda i:(latest[i]['score']['cost'],i))
    # Baseline starts with identical initial configurations/seeds, without transfers.
    # 120 additional SAC updates match 160*3 distillation component minibatches.
    baseline=executor.map(run_task,[task(out/f'baseline-m{i}','fresh',c,seeds[i],budget,extra_updates=30)
                                   for i,c in enumerate(initial)])
    base_selected=min(range(4),key=lambda i:(baseline[i]['score']['cost'],i))
    result={'passed':True,'budget_per_initial_member':budget,'seed':seed,'initial_configs':initial,
        'initial_seeds':seeds,'population_results':[r['task']['directory'] for r in results],
        'baseline_results':[r['task']['directory'] for r in baseline], 'events':events,'snapshots':snapshots,
        'selected':{'bgpbt':{'config':latest[selected]['task']['config'],
                            'task':latest[selected]['task']['directory'],'cost':latest[selected]['score']['cost']},
                    'baseline':{'config':baseline[base_selected]['task']['config'],
                                'task':baseline[base_selected]['task']['directory'],
                                'cost':baseline[base_selected]['score']['cost']}},
        'work':{'bgpbt':total_work(results),'baseline':total_work(baseline)},
        'confirmation':{'seeds':CONFIRMATION_SEEDS,'estimand':'fresh_training_of_final_static_config',
                        'budget':budget,'lineage_replay':False},
        'global_optimum':False,'all_attempts_retained':True}
    if result['work']['bgpbt']['transitions']!=result['work']['baseline']['transitions']:
        raise ValueError('Baseline transition budget differs')
    if result['work']['bgpbt']['gradient_components']!=result['work']['baseline']['gradient_components']:
        raise ValueError('Baseline component-minibatch budget differs')
    freeze=out/'selection-freeze.json'
    if freeze.exists():
        if read(freeze)!=result: raise ValueError('Replayed selection/controller differs')
    else: write(freeze,result)
    return result
