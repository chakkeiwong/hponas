"""Known-answer repeated training at common barriers, with protected finals."""
from contextlib import closing
from copy import deepcopy
import json
import math
from statistics import mean

import pytest

from hponas import (Study, StudyDeclaration, EvaluationFold, EvaluationObjective, StudyBudget,
                    SearchSpace, Knob, RandomSearcher, LocalExecutor, IncompleteStudyError,
                    MultiObjectiveStudy, MultiObjectiveRandomSearcher, MultiObjectiveScheduler)
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.store import Store
from hponas.searchers_tpe import TPESearcher


def declaration(**changes):
    values = dict(objective_id='quadratic-barrier:v1', model_id='scalar-descent:v1',
        data_id='known-initial-states:v1', protocol_id='repeated-stream:v1',
        objectives=(EvaluationObjective('loss', 'min', 'squared_units'),),
        tuning_folds=(EvaluationFold('a', ('train-a',), ('score-a',)),
                      EvaluationFold('b', ('train-b',), ('score-b',))),
        final_folds=(EvaluationFold('final', ('train-final',), ('score-final',)),),
        tuning_seeds=(0, 2), final_seeds=(10, 12), streaming_steps=(1., 2., 4.))
    values.update(changes)
    return StudyDeclaration(**values)


def space():
    return SearchSpace([Knob('eta', 'categorical', [.25, .5])])


def objective(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
    identity = [seed, evaluation.fold.name, evaluation.role]
    theta = 8. + seed + (3 if evaluation.fold.name == 'b' else 0)
    if resume_from:
        assert checkpoint['identity'] == identity and checkpoint['step'] == resume_from
        theta = checkpoint['theta']
    for step in range(int(resume_from)+1, int(fidelity)+1):
        theta *= 1-config['eta']
        checkpoint = {'theta': theta, 'step': step, 'identity': identity}
        work = step-resume_from
        reporter(step, theta**2, cost=work, checkpoint=checkpoint,
                 metadata={'resource': {'work': work, 'unit': 'gradient_updates'}})
    return {'value': theta**2, 'cost': work, 'checkpoint': checkpoint,
            'metadata': {'resource': {'work': work, 'unit': 'gradient_updates'}}}


def make(fn=objective, **kwargs):
    options = dict(budget=4, maximize=False, study_name='repeated', continuation='resume',
        declaration=declaration(), scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=4, eta=2,
                                                          promotion_policy='legacy_bootstrap')))
    options.update(kwargs)
    return Study(RandomSearcher(space(), seed=1), options.pop('executor', LocalExecutor()), fn, **options)


@pytest.mark.parametrize('steps', [(1., 4.), (1., 2.)])
def test_declared_barriers_must_include_interior_and_final_scheduler_rungs(steps):
    with pytest.raises(ValueError) as raised:
        make(declaration=declaration(streaming_steps=steps))
    assert str(raised.value) == 'Declared streaming barriers must contain all scheduler endpoints'


def test_unscheduled_streaming_declares_the_unit_fidelity_endpoint():
    run = make(scheduler=None, declaration=declaration(streaming_steps=(1.,)))
    assert run.scheduler is None
    with pytest.raises(ValueError) as raised:
        make(scheduler=None, declaration=declaration(streaming_steps=(2.,)))
    assert str(raised.value) == 'Declared streaming barriers must contain all scheduler endpoints'


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_every_scheduler_score_uses_all_repetitions_at_the_same_fidelity_and_final_is_sealed(tmp_path, mode):
    with closing(Store(tmp_path/'stream.db')) as store:
        source = make(executor=LocalExecutor(mode=mode), store=store, max_concurrent=1)
        result = source.run()
        assert result.status == 'completed' and result.evaluation['outcome'] == 'completed'
        for record in source.get_history():
            eta = source.trials[record.trial_id].config['eta']
            exact = mean((8+seed+offset)**2*(1-eta)**(2*record.fidelity)
                         for seed in (0, 2) for offset in (0, 3))
            assert record.objective_value == pytest.approx(exact)
            assert len(record.metadata['evaluation']['records']) == 4
        progress = [e['data'] for e in source._events if e['kind'] == 'progress']
        assert progress and len(progress) == len(source.get_history())
        assert all(row['normalized_value'] < 100 for row in progress)
        assert {r.trial_id for r in source.searcher.history} == set(source.results)
        assert all('_final_' not in r.trial_id for r in source.searcher.history)
        final = result.evaluation['final'][0]
        eta = result.best_config['eta']
        assert final['objectives']['loss']['mean'] == pytest.approx(mean((8+s)**2*(1-eta)**8 for s in (10, 12)))
        segments = source._evaluation.resource_records()
        assert result.total_cost == sum(row['cost'] for _, row in segments.values())
        restored = make(store=store)
        restored.load_checkpoint()
        assert restored.run().evaluation == result.evaluation


def test_barriers_stop_later_work_and_never_average_a_failed_repetition():
    calls = []
    def failed(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
        calls.append((fidelity, seed, evaluation.fold.name))
        if seed == 2:
            raise ValueError('Deliberate replica failure')
        return objective(config, fidelity, seed, evaluation, reporter, checkpoint, resume_from)
    source = make(failed, budget=1)
    with pytest.raises(IncompleteStudyError):
        source.run()
    assert len(calls) == 2 and all(step == 1 for step, _, _ in calls)
    assert not any(e['kind'] == 'progress' for e in source._events)
    assert source.get_history()[0].status == 'failed'
    assert math.isnan(source.get_history()[0].objective_value)
    assert not source._evaluation.state['final']


def test_crash_retains_paid_prefix_and_replays_each_repetition_from_its_own_state(tmp_path):
    calls = []
    def interrupted(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
        result = objective(config, fidelity, seed, evaluation, reporter, checkpoint, resume_from)
        calls.append((seed, evaluation.fold.name, fidelity))
        if len(calls) == 2:
            raise KeyboardInterrupt('After acknowledged work, before endpoint commit')
        return result
    budget = StudyBudget(2, 'gradient_updates', 80, 12, 2)
    source = make(interrupted, budget=2, resource_budget=budget, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt):
        source.run()
    restored = make(budget=2, resource_budget=budget)
    restored.load_checkpoint(tmp_path/'repeated_checkpoint.json')
    result = restored.run()
    assert result.resources['tuning']['lost_attempts'] == 1
    assert result.resources['tuning']['work_exact'] is False
    assert result.evaluation['uncertain_evaluations']
    assert result.history[0].cost == 5.  # Four updates plus the acknowledged lost update.
    assert result.history[0].metadata['execution']['accounting'] == 'lower_bound_after_interruption'
    saved = restored._snapshot()
    path = tmp_path/'finished.json'
    path.write_text(json.dumps(saved))
    replay = make(budget=2, resource_budget=budget)
    replay.load_checkpoint(path)
    assert replay.run().evaluation == result.evaluation


@pytest.mark.parametrize('damage', ['missing', 'order', 'aggregate', 'barrier', 'final_control', 'work',
                                  'past_terminal', 'missing_prior_barrier', 'false_failure'])
def test_raw_segment_corruption_refused_before_replacing_study_state(tmp_path, damage):
    source = make(budget=2)
    source.run()
    saved = deepcopy(source._snapshot())
    state = saved['evaluation']
    group = next(g for g in state['streaming'].values() if g['role'] == 'tuning')
    if damage == 'missing': group['segments'].pop()
    if damage == 'order': group['segments'][0]['index'] = 1
    if damage == 'aggregate': state['tuning'][group['parent']][0]['result']['objective_value'] += 1
    if damage == 'barrier': group['barriers'][0]['value'] += 1
    if damage == 'work': group['segments'][0]['result']['cost'] += 1
    if damage in ('past_terminal', 'missing_prior_barrier'):
        group = next(g for g in state['streaming'].values() if len(g['barriers']) > 1)
        if damage == 'past_terminal':
            group['barriers'][0]['decision'] = {'action': 'stop', 'reason': 'fabricated'}
        else:
            group['barriers'].pop(0)
    if damage == 'false_failure':
        group['control'] = {'action': 'failed', 'reason': 'fabricated', 'step': group['segments'][-1]['step']}
    if damage == 'final_control':
        final = next(g for g in state['streaming'].values() if g['role'] == 'final')
        final['barriers'][0]['decision'] = {'action': 'stop', 'reason': 'leaked'}
    path = tmp_path/'bad.json'
    path.write_text(json.dumps(saved))
    target = make(budget=2)
    before = target._snapshot()
    with pytest.raises(ValueError): target.load_checkpoint(path)
    assert target._snapshot() == before


def test_cancellation_preserves_acknowledged_work_without_dispatching_the_rest():
    def cancelled(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
        source.cancel_trial('repeated_trial_0')
        return objective(config, fidelity, seed, evaluation, reporter, checkpoint, resume_from)
    source = make(cancelled, budget=1)
    with pytest.raises(IncompleteStudyError) as caught:
        source.run()
    assert caught.value.result.total_cost == 1.
    assert source.get_history()[0].status == 'cancelled'
    assert len(source._evaluation.resource_records()) == 1


def test_complete_repetition_barrier_can_prune_before_any_later_training():
    scheduler = ASHAScheduler(ASHAConfig(r_min=4, r_max=4, median_stopping=True, report_grid=(1, 2, 4)))
    for i in range(5):
        for step in (1, 2, 4): scheduler.report('reference'+str(i), step, .001, is_progress=True)
        scheduler.finish('reference'+str(i), 'completed')
    source = make(budget=1, scheduler=scheduler)
    with pytest.raises(IncompleteStudyError) as caught: source.run()
    assert caught.value.result.history[0].status == 'pruned'
    assert caught.value.result.total_cost == 4.
    group = source._evaluation.state['streaming']['tuning:repeated_trial_0']
    assert len(group['segments']) == 4 and group['barriers'][0]['decision']['action'] == 'stop'
    assert all(row['step'] == 1. for row in group['segments'])


def test_lost_prefix_remains_accounted_when_no_retry_reservation_remains(tmp_path):
    def crash(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
        objective(config, fidelity, seed, evaluation, reporter, checkpoint, resume_from)
        raise KeyboardInterrupt('Paid prefix before crash')
    budget = StudyBudget(1, 'gradient_updates', 2, 12, 2)
    source = make(crash, budget=1, resource_budget=budget, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt): source.run()
    restored = make(budget=1, resource_budget=budget)
    restored.load_checkpoint(tmp_path/'repeated_checkpoint.json')
    with pytest.raises(IncompleteStudyError) as caught: restored.run()
    result = caught.value.result
    assert result.total_cost == 1. and result.total_elapsed_seconds > 0
    assert result.total_elapsed_seconds == result.history[0].metadata['execution']['elapsed_seconds']
    assert result.resources['tuning']['charged_work'] == 2.
    path = tmp_path/'stopped.json'; path.write_text(json.dumps(restored._snapshot()))
    replay = make(budget=1, resource_budget=budget)
    replay.load_checkpoint(path)
    with pytest.raises(IncompleteStudyError) as again: replay.run()
    assert again.value.result.total_cost == result.total_cost


VECTOR = [{'name': 'loss', 'direction': 'min', 'lower': 0., 'upper': 1000.},
          {'name': 'size', 'direction': 'min', 'lower': 0., 'upper': 4.}]


def vector_objective(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
    theta = checkpoint['theta'] if resume_from else 8+seed+(3 if evaluation.fold.name == 'b' else 0)
    for step in range(int(resume_from)+1, int(fidelity)+1):
        theta *= 1-config['eta']
        row = {'objectives': {'loss': theta**2, 'size': 1/config['eta']},
               'constraints': {'eta': config['eta']}, 'work': int(step-resume_from),
               'cost': step-resume_from, 'checkpoint': {'theta': theta}}
        reporter(step, **{k: row[k] for k in ('objectives', 'constraints', 'work', 'cost', 'checkpoint')})
    return row


def test_named_vector_progress_preserves_constraints_and_protected_pareto_evaluation(tmp_path):
    contract = dict(objectives=VECTOR, constraints={'eta': .5}, work_unit='gradient_updates')
    declared = declaration(objectives=(EvaluationObjective('loss', 'min', 'squared_units'),
                                       EvaluationObjective('size', 'min', 'parameters')), streaming_steps=(1., 2.))
    def build():
        return MultiObjectiveStudy(MultiObjectiveRandomSearcher(space(), seed=1, **contract), LocalExecutor(),
            vector_objective, **contract, budget=2, declaration=declared, continuation='resume',
            scheduler=MultiObjectiveScheduler(**contract, r_min=1, r_max=2), study_name='vector-stream')
    source = build()
    result = source.run()
    assert result.front and result.evaluation['outcome'] == 'completed'
    for record in result.history:
        vector = record.metadata['multi_objective']
        eta = source.trials[record.trial_id].config['eta']
        assert vector['objectives']['loss'] == pytest.approx(mean((8+s+o)**2*(1-eta)**(2*record.fidelity)
                                                                 for s in (0, 2) for o in (0, 3)))
        assert vector['constraints'] == {'eta': eta}
        assert vector['work'] == 4  # Each promotion pays one additional update per repetition.
    path = tmp_path/'vector.json'
    path.write_text(json.dumps(source._snapshot()))
    resumed = build()
    resumed.load_checkpoint(path)
    assert resumed.run().evaluation == result.evaluation


def test_repeated_streaming_tpe_asha_recovery_trains_only_complete_tuning_endpoints(tmp_path):
    import optuna

    def build(fn=objective, **options):
        return Study(TPESearcher(space(), seed=4, model_fidelity=4), LocalExecutor(), fn,
            scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=4, eta=2,
                                              promotion_policy='legacy_bootstrap')),
            budget=8, maximize=False, declaration=declaration(), continuation='resume',
            study_name='tpe-repeated', **options)

    full = build()
    expected = full.run()
    calls = []
    def interrupted(config, fidelity, seed, evaluation, reporter, checkpoint=None, resume_from=0.):
        calls.append((seed, evaluation.fold.name, fidelity))
        if len(calls) == 6:
            raise KeyboardInterrupt('Between repetitions after one complete barrier')
        return objective(config, fidelity, seed, evaluation, reporter, checkpoint, resume_from)
    source = build(interrupted, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt):
        source.run()
    resumed = build()
    resumed.load_checkpoint(tmp_path/'tpe-repeated_checkpoint.json')
    actual = resumed.run()
    project = lambda s: [(r.trial_id, s.trials[r.trial_id].config, r.fidelity,
                          r.objective_value, r.status) for r in s.get_history()]
    assert project(resumed) == project(full)
    assert actual.evaluation['selection'] == expected.evaluation['selection']
    vendor = resumed.searcher.searcher
    assert vendor.state_dict() == full.searcher.searcher.state_dict()
    assert not vendor._pending
    assert any(r.fidelity < 4 for r in resumed.get_history())
    for record in resumed.get_history():
        eta = resumed.trials[record.trial_id].config['eta']
        exact = mean((8+s+o)**2*(1-eta)**(2*record.fidelity)
                     for s in (0, 2) for o in (0, 3))
        assert record.objective_value == pytest.approx(exact)
        assert record.metadata['evaluation']['role'] == 'tuning'
        assert len(record.metadata['evaluation']['records']) == 4
    complete = [t for t in vendor._study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    endpoints = [r.objective_value for r in resumed.get_history() if r.fidelity == 4]
    assert complete and sorted(t.value for t in complete) == sorted(endpoints)
    assert len(resumed.searcher.history) == len(resumed.get_history())
    final = actual.evaluation['final'][0]
    eta = actual.best_config['eta']
    assert final['objectives']['loss']['mean'] == pytest.approx(mean((8+s)**2*(1-eta)**8 for s in (10, 12)))
    assert {row['seed'] for row in final['records']} == {10, 12}
    for group in resumed._evaluation.state['streaming'].values():
        if group['role'] == 'final':
            assert group['control'] is None
            assert all(row['decision'] == {'action': 'continue', 'reason': 'protected_final_evaluation'}
                       for row in group['barriers'])
