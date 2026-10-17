"""Mixed product PriorBand training, Store recovery and complete event replay."""
from copy import deepcopy
import json

import pytest

from hponas import (Knob, LocalExecutor, PriorBandScheduler, ProductPriorBandSearcher,
                    SearchSpace, Study)
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.store import Store
from validation.multifidelity_reference import value
from workloads.streaming_quadratic import StreamingQuadratic


def searcher(seed=0, transform='none'):
    space=SearchSpace([Knob('eta_index','integer',(1,25),transform=transform)])
    return ProductPriorBandSearcher(space,{'eta_index':18},rungs=[1,2,4,8],eta=2,seed=seed)


def scheduler():
    return PriorBandScheduler(rungs=[1,2,4,8],eta=2,default_at_target=True)


@pytest.mark.parametrize('transform', ['none','log'])
def test_actual_integer_training_and_full_replay(tmp_path,transform):
    store=Store(tmp_path/'store.sqlite')
    events=EventLog(tmp_path/'events.jsonl')
    workload=StreamingQuadratic()
    study=Study(searcher(transform=transform),LocalExecutor(),workload,budget=21,
                 study_name='product',maximize=False,scheduler=scheduler(),continuation='resume',
                 store=store,event_log=events)
    result=study.run()
    assert result.n_trials==33 and len(workload.updates)==result.total_cost==100
    for row in result.history:
        index=study.trials[row.trial_id].config['eta_index']
        assert row.objective_value==pytest.approx(float(value(index,int(row.fidelity))),abs=1e-12)
    restored=Study(searcher(seed=9,transform=transform),LocalExecutor(),workload,budget=21,
        study_name='product',maximize=False,scheduler=scheduler(),continuation='resume',store=store)
    restored.load_checkpoint()
    assert restored.searcher.get_state()==study.searcher.get_state()
    assert restored.run().total_cost==100 and len(workload.updates)==100
    engine=ReplayEngine(searcher(transform=transform),events,seed=0,scheduler=scheduler())
    passed,message,_,_=engine.verify_determinism(21)
    assert passed,message
    assert engine.searcher.get_state()==study.searcher.get_state()
    store.close()


@pytest.mark.parametrize('damage', ['weights','draw','rng','event','direction','policy','integer_bounds'])
def test_recovery_reconstructs_all_draws_and_policy_atomically(tmp_path,damage):
    study=Study(searcher(),LocalExecutor(),StreamingQuadratic(),budget=21,
                maximize=False,scheduler=scheduler(),continuation='resume')
    study.run()
    before=study._snapshot()
    bad=deepcopy(before)
    inner=bad['searcher_state']
    if damage=='weights': inner['contexts'][-1]['mixture']['prior']='1'
    elif damage=='draw': inner['draws'][1]['eta_index']=0
    elif damage=='rng': inner['rng'][1][1]^=1
    elif damage=='event': inner['events'].pop()
    elif damage=='direction': inner['maximize']=True
    elif damage=='policy': inner['policy']['events'][1]['value']+=1
    elif damage=='integer_bounds': inner['contract']['distribution']['space']['knobs'][0]['bounds'][0]=0
    path=tmp_path/'bad.json'
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        study.load_checkpoint(path)
    assert study._snapshot()==before


def test_mixed_product_recovery_retains_exact_next_draw():
    space=SearchSpace([Knob('x','continuous',(.01,1.),transform='log'),
                      Knob('n','integer',(1,10),transform='log'),Knob('c','categorical',['a','b'])])
    source=ProductPriorBandSearcher(space,{'x':.1,'n':4,'c':'a'},rungs=[1,3,9])
    source.set_scheduler_context(PriorBandScheduler(rungs=[1,3,9],eta=3,default_at_target=True))
    for _ in range(4):
        source.suggest()
    snapshot=source.get_state()
    expected=[source.suggest().values for _ in range(5)]
    restored=ProductPriorBandSearcher(space,{'x':.1,'n':4,'c':'a'},rungs=[1,3,9],seed=91)
    restored.set_state(snapshot)
    assert [restored.suggest().values for _ in range(5)]==expected
