from copy import deepcopy
import json
import os
import time
import pytest
from hponas import Study, ResourceExecutor, StudyBudget
from tests.integration.test_declared_evaluation import Sequence, space, declaration


def objective(config, seed, evaluation, execution):
    time.sleep(.025)
    return {'value':config['x']+seed+(100 if evaluation.role=='final' else 0),'cost':1.,
        'metadata':{'resource':{'unit':'updates','work':1},'pid':os.getpid(),
                    'device':execution.device,'role':evaluation.role}}


def make(executor, tmp_path, **changes):
    args=dict(searcher=Sequence(space(),seed=0),executor=executor,objective_fn=objective,
        declaration=declaration(),maximize=False,study_name='parallel',checkpoint_dir=tmp_path,
        max_concurrent=2,evaluation_workers=2,
        resource_budget=StudyBudget(3,'updates',20,4,1,worker_capacity=2))
    args.update(changes)
    return Study(**args)


def test_parallel_known_answer_final_barrier_and_resume(tmp_path):
    with ResourceExecutor(2,timeout=40) as executor:
        study=make(executor,tmp_path)
        result=study.run()
        assert result.best_value==3 and result.best_config.values=={'x':0}
        state=study._snapshot()
        assert state['evaluation']['selection']==['parallel_trial_0']
        assert state['resources']['attempts'][-1]['role']=='final'
        assert sum(a['work'] for a in state['resources']['attempts'])==14
        tuning=[row for rows in state['evaluation']['tuning'].values() for row in rows]
        assert len({row['result']['metadata']['pid'] for row in tuning})==2
        checkpoint=tmp_path/'saved.json';checkpoint.write_text(json.dumps(state))
        restored=make(executor,tmp_path)
        restored.load_checkpoint(checkpoint)
        assert restored.run().to_dict()==result.to_dict()


def test_crash_after_reservation_retains_and_charges_lost_calls(tmp_path,monkeypatch):
    class Crash(BaseException):pass
    with ResourceExecutor(2,timeout=40) as executor:
        study=make(executor,tmp_path)
        original=study.save_checkpoint
        saved={}
        def save():
            original()
            if len(study._evaluation.state['inflight'])==2:
                saved.update(deepcopy(study._snapshot()));raise Crash()
        monkeypatch.setattr(study,'save_checkpoint',save)
        with pytest.raises(Crash):study.run()
        checkpoint=tmp_path/'crash.json';checkpoint.write_text(json.dumps(saved))
        with ResourceExecutor(2,timeout=40) as replacement:
            restored=make(replacement,tmp_path)
            restored.load_checkpoint(checkpoint)
            result=restored.run()
            assert result.best_value==3
            assert result.resources['tuning']['lost_attempts']==2
            assert result.resources['tuning']['charged_work']==14
            assert len(restored._evaluation.state['uncertain'])==2


def test_capacity_and_mode_refused_before_work(tmp_path):
    with ResourceExecutor(1,timeout=40) as executor:
        with pytest.raises(ValueError,match='capacity'):make(executor,tmp_path)


@pytest.mark.parametrize('failure', ['seconds', 'breach', 'lost'])
def test_concurrent_resource_admission_replays_before_failure(failure):
    from hponas.budgets import ResourceController
    from hponas.types import Result
    budget = StudyBudget(2, 'updates', 4, 2, 1, worker_capacity=2, tuning_seconds=.1)
    controller = ResourceController(budget)
    controller.begin('a', 'tuning'); controller.begin('b', 'tuning')
    records = {}
    class Evaluation:
        state = {'inflight': [], 'uncertain': ['a', 'b'] if failure == 'lost' else []}
        def resource_records(self): return records
        def resource_role(self, tid): return 'tuning'
    if failure == 'lost':
        controller.abandon_inflight()
    else:
        for tid in ('a', 'b'):
            result = Result(tid, 1., 1., 1., {'resource': {'unit': 'updates', 'work': 2 if failure == 'breach' and tid == 'a' else 1},
                'execution': {'elapsed_seconds': .2, 'accounting': 'measured'}})
            controller.complete(result, None)
            records[tid] = ('tuning', result.to_dict())
    restored = ResourceController(budget)
    restored.restore(deepcopy(controller.state), Evaluation(), None)
    assert restored.state == controller.state and restored.refusal('tuning')
    bad = deepcopy(controller.state)
    bad['events'][1], bad['events'][2] = bad['events'][2], bad['events'][1]
    with pytest.raises(ValueError): ResourceController(budget).restore(bad, Evaluation(), None)


def test_legacy_resource_snapshot_migrates_without_reexecuting():
    from hponas.budgets import ResourceController
    from hponas.types import Result
    budget = StudyBudget(1, 'updates', 2, 1, 1)
    controller = ResourceController(budget); controller.begin('a', 'tuning')
    result = Result('a', 1., 1., 1., {'resource': {'unit': 'updates', 'work': 1},
        'execution': {'elapsed_seconds': .1, 'accounting': 'measured'}})
    controller.complete(result, None)
    class Evaluation:
        state = {'inflight': None, 'uncertain': []}
        def resource_records(self): return {'a': ('tuning', result.to_dict())}
        def resource_role(self, tid): return 'tuning'
    old = deepcopy(controller.state); old.pop('events'); old['version'] = 1
    restored = ResourceController(budget); restored.restore(old, Evaluation(), None)
    assert restored.state == controller.state
