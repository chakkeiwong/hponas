"""Single-CPU grouped endpoint contracts; physical workers are tested separately."""
from copy import deepcopy
import json
import threading

import pytest

from hponas import LocalExecutor, Study, StudyBudget
from tests.integration.test_declared_evaluation import Sequence, declaration, space


def endpoint(config, seed, evaluation):
    offset = 100 if evaluation.role == 'final' else 0
    return {'value': config['x'] + seed + offset, 'cost': 1.,
            'metadata': {'resource': {'unit': 'updates', 'work': 1}}}


def make(tmp_path, objective=endpoint, **changes):
    declared = declaration(tuning_folds=declaration().tuning_folds[:1],
                           tuning_seeds=(2,), final_seeds=(12,))
    args = dict(searcher=Sequence(space(), seed=0),
                executor=LocalExecutor(mode='async', max_workers=2),
                objective_fn=objective, declaration=declared, maximize=False,
                study_name='grouped', checkpoint_dir=tmp_path,
                max_concurrent=2, evaluation_workers=2,
                resource_budget=StudyBudget(2, 'updates', 8, 2, 1, worker_capacity=2))
    args.update(changes)
    return Study(**args)


def test_grouped_candidates_overlap_commit_in_order_and_freeze_selection(tmp_path):
    admitted = threading.Barrier(2, timeout=2)
    second_finished = threading.Event()
    finished, final_calls = [], []

    def objective(config, seed, evaluation):
        if evaluation.role == 'tuning':
            admitted.wait()
            if config['x'] == 0:
                assert second_finished.wait(2), 'second candidate was not dispatched'
            finished.append(config['x'])
            if config['x'] == 1:
                second_finished.set()
        else:
            final_calls.append(config['x'])
        return endpoint(config, seed, evaluation)

    study = make(tmp_path, objective)
    result = study.run()
    assert finished == [1, 0]
    assert list(study.results) == ['grouped_trial_0', 'grouped_trial_1']
    assert [r.objective_value for r in study.results.values()] == [2., 3.]
    assert result.best_value == 2. and result.best_config.values == {'x': 0}
    state = study._snapshot()
    assert state['evaluation']['selection'] == ['grouped_trial_0']
    assert state['evaluation']['inflight'] == []
    assert final_calls == [0]
    assert state['evaluation']['final']['grouped_trial_0'][0]['result']['objective_value'] == 112.
    assert state['resources']['events'] == [
        {'kind': 'begin', 'index': 0}, {'kind': 'begin', 'index': 1},
        {'kind': 'complete', 'index': 0}, {'kind': 'complete', 'index': 1},
        {'kind': 'begin', 'index': 2}, {'kind': 'complete', 'index': 2}]
    assert [a['work'] for a in state['resources']['attempts']] == [1, 1, 1]
    assert [a['role'] for a in state['resources']['attempts']] == ['tuning', 'tuning', 'final']

    saved = tmp_path / 'completed.json'
    saved.write_text(json.dumps(state))
    def forbidden(config, seed, evaluation):
        raise AssertionError('completed resume must not reevaluate objectives')
    restored = make(tmp_path, forbidden)
    restored.load_checkpoint(saved)
    assert restored.run().to_dict() == result.to_dict()


def test_cancellation_after_admission_keeps_paid_endpoints_but_excludes_parent(tmp_path):
    admitted = threading.Barrier(2, timeout=2)
    cancelled = threading.Event()
    def objective(config, seed, evaluation):
        if evaluation.role == 'tuning':
            admitted.wait()
            if config['x'] == 0:
                study.cancel_trial('grouped_trial_0')
                cancelled.set()
            else:
                assert cancelled.wait(2)
        return endpoint(config, seed, evaluation)
    study = make(tmp_path, objective)
    result = study.run()
    assert study.results['grouped_trial_0'].status == 'cancelled'
    assert study.results['grouped_trial_0'].cost == 1.
    assert study.results['grouped_trial_1'].status == 'completed'
    assert result.best_config.values == {'x': 1} and result.best_value == 3.
    saved = study._snapshot()
    assert saved['evaluation']['selection'] == ['grouped_trial_1']
    assert saved['evaluation']['tuning']['grouped_trial_0'][0]['result']['status'] == 'completed'
    restored = make(tmp_path)
    checkpoint = tmp_path / 'cancelled.json'
    checkpoint.write_text(json.dumps(saved))
    restored.load_checkpoint(checkpoint)
    # JSON preserves the NaN cancellation marker; direct NaN equality is false.
    assert json.dumps(restored.run().to_dict(), sort_keys=True) == json.dumps(result.to_dict(), sort_keys=True)


def test_parallel_repetition_mean_uses_all_folds_and_seeds(tmp_path):
    def objective(config, seed, evaluation):
        result = endpoint(config, seed, evaluation)
        result['value'] += 10 if evaluation.fold.name == 'fold-b' else 0
        return result
    study = make(tmp_path, objective, declaration=declaration(),
                 resource_budget=StudyBudget(2, 'updates', 8, 2, 1, worker_capacity=2))
    result = study.run()
    assert result.best_value == 8.
    assert [r.objective_value for r in study.results.values()] == [8., 9.]
    assert [r.cost for r in study.results.values()] == [4., 4.]
    state = study._snapshot()['evaluation']
    assert [r['result']['objective_value'] for r in state['tuning']['grouped_trial_0']] == [2., 4., 12., 14.]
    assert [r['result']['objective_value'] for r in state['final']['grouped_trial_0']] == [112., 114.]


def test_vector_cancellation_normalizes_before_pareto_observation(tmp_path):
    from dataclasses import replace
    from tests.integration.test_declared_evaluation import vector_study, vector_declaration, vector_objective
    admitted = threading.Barrier(2, timeout=2)
    cancelled = threading.Event()
    calls = []
    def objective(config, seed, evaluation, trial_id):
        if evaluation.role == 'tuning':
            admitted.wait()
            if trial_id.startswith('vector_trial_0_'):
                study.cancel_trial('vector_trial_0')
                cancelled.set()
            else:
                assert cancelled.wait(2)
        calls.append(trial_id)
        return vector_objective(config, seed, evaluation)
    declared = replace(vector_declaration(), tuning_folds=vector_declaration().tuning_folds[:1],
                       tuning_seeds=(2,), final_seeds=(12,))
    options = dict(declaration=declared, budget=2, max_concurrent=2, evaluation_workers=2,
                   checkpoint_dir=tmp_path)
    study = vector_study(executor=LocalExecutor(mode='async', max_workers=2), objective_fn=objective, **options)
    result = study.run()
    cancelled_result = study.results['vector_trial_0']
    assert cancelled_result.status == 'cancelled' and cancelled_result.cost == 1.
    assert cancelled_result.metadata['multi_objective']['status'] == 'failed'
    assert cancelled_result.metadata['multi_objective_context']['root_trial_id'] == 'vector_trial_0'
    assert result.front and {r['trial_id'] for r in result.front} == {'vector_trial_1'}
    assert study._evaluation.state['selection'] == ['vector_trial_1']
    assert len(study.searcher.history) == 2
    checkpoint = tmp_path / 'vector-completed.json'
    checkpoint.write_text(json.dumps(study._snapshot()))
    restored = vector_study(executor=LocalExecutor(mode='async', max_workers=2), objective_fn=objective, **options)
    restored.load_checkpoint(checkpoint)
    before = list(calls)
    assert json.dumps(restored.run().to_dict(), sort_keys=True) == json.dumps(result.to_dict(), sort_keys=True)
    assert calls == before


def test_lost_parallel_reservations_remain_charged_on_resume(tmp_path, monkeypatch):
    class SimulatedCrash(BaseException):
        pass
    study = make(tmp_path)
    saved = {}
    original = study.save_checkpoint
    def crash_after_reservation():
        original()
        if len(study._evaluation.state['inflight']) == 2:
            saved.update(deepcopy(study._snapshot()))
            raise SimulatedCrash()
    monkeypatch.setattr(study, 'save_checkpoint', crash_after_reservation)
    with pytest.raises(SimulatedCrash):
        study.run()
    checkpoint = tmp_path / 'reserved.json'
    checkpoint.write_text(json.dumps(saved))
    restored = make(tmp_path)
    restored.load_checkpoint(checkpoint)
    result = restored.run()
    assert result.best_value == 2.
    assert result.resources['tuning']['lost_attempts'] == 2
    assert result.resources['tuning']['charged_work'] == 4
    assert len(restored._evaluation.state['uncertain']) == 2
    assert [a['state'] for a in restored._resources.state['attempts']] == [
        'lost', 'lost', 'committed', 'committed', 'committed']


@pytest.mark.parametrize('workers', [0, -1, True, 1.5])
def test_invalid_parallel_worker_count_refused(tmp_path, workers):
    executor = LocalExecutor(mode='async', max_workers=2)
    try:
        with pytest.raises(ValueError, match='evaluation_workers must be a positive integer'):
            make(tmp_path, executor=executor, evaluation_workers=workers)
    finally:
        executor.shutdown()


@pytest.mark.parametrize('case', ['executor', 'budget', 'legacy', 'streaming'])
def test_parallel_capacity_and_mode_refused_before_dispatch(tmp_path, case):
    executor = LocalExecutor(mode='async', max_workers=1 if case == 'executor' else 2)
    changes = dict(executor=executor)
    message = 'Parallel repetitions exceed worker capacity'
    if case == 'budget':
        changes.update(max_concurrent=1, resource_budget=StudyBudget(2, 'updates', 8, 2, 1))
    elif case == 'legacy':
        changes.update(declaration=None, resource_budget=None, budget=2, legacy_reason='explicit legacy refusal')
        message = 'Parallel repetitions currently require an endpoint declaration'
    elif case == 'streaming':
        changes.update(declaration=declaration(streaming_steps=(1.,)))
        message = 'Parallel repetitions currently require an endpoint declaration'
    try:
        with pytest.raises(ValueError, match=message):
            make(tmp_path, **changes)
    finally:
        executor.shutdown()
