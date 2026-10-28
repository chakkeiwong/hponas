from copy import deepcopy
import os
from pathlib import Path

import pytest

from hponas.executors.resource_executor import ResourceExecutor
from hponas.executors.resources import ResourceSpec
from hponas_rl_bgpbt.explorer import Explorer
from hponas_rl_bgpbt.explorer_v2 import JointExplorer
from hponas_rl_bgpbt.hardware import shared_admission
from hponas_rl_bgpbt.study import CALIBRATION_CONFIG
from hponas_rl_bgpbt.study_v2 import objective_order, selection, population_search_v2
from hponas_rl_bgpbt.tasks import read


def test_shared_busy_devices_admitted_but_insufficient_memory_refused():
    query='GPU-a, 100, 5000, 24000\nGPU-b, 97, 10000, 24000\nGPU-c, 0, 2048, 24000\n'
    report=shared_admission(query,'GPU-a, 111, 9000\nGPU-b, 222, 8000\n')
    assert report['passed'] and not report['idle_required']
    assert report['selected_gpu_ids']==['GPU-b','GPU-a']
    assert not shared_admission('GPU-a, 0, 4095, 24000\nGPU-b, 100, 8000, 24000','')['passed']


def test_round_region_independent_of_member_order_and_objective_scale():
    c=CALIBRATION_CONFIG
    # Demonstrate the predecessor's order dependence using the same observations.
    outcomes=[(4.,3.),(4.,3.),(4.,5.),(4.,5.)]
    a,b=Explorer(1),Explorer(1)
    for before,after in outcomes: a.observe(c,0,before,after)
    for before,after in outcomes[::2]+outcomes[1::2]: b.observe(c,0,before,after)
    assert (a.radius,a.successes,a.failures)!=(b.radius,b.successes,b.failures)
    a,b=JointExplorer(1),JointExplorer(1)
    for time,costs in enumerate(([3,4,5,6],[2,3,6,8],[1,4,7,9])):
        for v in costs: a.observe(c,time,4.,v)
        for v in reversed(costs): b.observe(c,time,4.,v)
        a.finish_round(time,list(costs)); b.finish_round(time,list(reversed(costs)))
    assert a.radius==b.radius==1.
    assert a.propose(c,3,1.)==b.propose(c,3,1.)
    with pytest.raises(ValueError,match='consecutive'): a.finish_round(2,[1.])


def test_objective_halving_and_best_checkpoint_survive_adverse_imitation_and_late_regression():
    def row(cost,loss,name):
        return {'score':{'cost':cost},'transfer':{'final_losses':[loss]},
                'work':{'sac_updates':1},
                'task':{'config':CALIBRATION_CONFIG,'directory':name}}
    rows=[row(8,.001,'a'),row(3,100,'b'),row(4,.5,'c')]
    assert objective_order(rows)==[1,2,0]
    assert selection(rows+[row(5,.01,'later')])['task']=='b'
    clone=row(3,.001,'a-copy'); clone['work']['sac_updates']=0
    assert selection(rows+[clone])['task']=='b'
    with pytest.raises(ValueError,match='No trained'): selection([clone])


def test_architecture_model_uses_objective_and_global_restart_resets_local_history():
    e=JointExplorer(17); c=CALIBRATION_CONFIG
    for time in range(13):
        e.observe(c,time,4.,4.+time)
        e.finish_round(time,[4.+time])
    assert e.radius<.03125
    _,record=e.propose(c,14,4.)
    assert record['restart'] and not record['observed_points']
    assert record['restart']['observed_points'] and e.local_start==13
    _,record=e.propose(c,14,4.,architecture=True,count=4)
    assert record['response']=='negative_log1p_best_objective'
    assert len(record['bo_indices'])==len(record['random_indices'])==2
    assert not set(record['bo_indices'])&set(record['random_indices'])


def test_actual_candidate_sac_objective_halving_procedure_and_exact_replay(tmp_path):
    from hponas_rl_bgpbt.audit import verify_selection_v2
    with ResourceExecutor(2,resources=ResourceSpec(),cpu_ids=sorted(os.sched_getaffinity(0))[:2],timeout=180) as pool:
        result=population_search_v2(tmp_path/'study',pool,47,segment=256)
        ledger=Path(os.environ['HPONAS_SAC_WORK_LEDGER']); before=ledger.read_bytes()
        assert population_search_v2(tmp_path/'study',pool,47,segment=256)==result
        assert ledger.read_bytes()==before
    event=result['events'][1]
    candidates=[read(Path(d)/'result.json') for d in event['candidate_results']]
    assert all(r['work']['transitions']==128 and r['work']['sac_updates']==32 for r in candidates)
    assert all(r['work']['distillation_updates']==64 for r in candidates)
    assert event['halving_order']==objective_order(candidates)
    assert result['work']['bgpbt']['transitions']==result['work']['baseline']['transitions']==4864
    verify_selection_v2(result)
    bad=deepcopy(result); bad['selected']['bgpbt']['cost']=0.
    with pytest.raises(ValueError): verify_selection_v2(bad)
    bad=deepcopy(result); bad['estimand']='fresh_training_of_final_static_config'
    with pytest.raises(ValueError): verify_selection_v2(bad)
