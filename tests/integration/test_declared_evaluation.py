"""Independent aggregation, leakage, frozen-selection and crash counterexamples."""

from copy import deepcopy
from contextlib import closing
import json
import math

import pytest

from hponas import (Study, StudyDeclaration, EvaluationFold, EvaluationObjective, LocalExecutor,
                    SearchSpace, Knob, Config, RandomSearcher, MultiObjectiveStudy,
                    MultiObjectiveRandomSearcher, IncompleteStudyError)
from hponas import StudyBudget
from hponas.store import Store
from hponas.schedulers import ASHAConfig, ASHAScheduler


def declaration(**changes):
    values = dict(objective_id='squared-error:v1', model_id='linear:v1', data_id='finite:v1', protocol_id='eval:v1',
        objectives=(EvaluationObjective('loss', 'min', 'squared_units'),),
        tuning_folds=(EvaluationFold('fold-a', ('train-a',), ('score-a',)),
                      EvaluationFold('fold-b', ('train-b',), ('score-b',))),
        final_folds=(EvaluationFold('holdout', ('train-a', 'train-b', 'score-a', 'score-b'), ('sealed',)),),
        tuning_seeds=(2, 4), final_seeds=(12, 14))
    values.update(changes)
    return StudyDeclaration(**values)


def space():
    return SearchSpace([Knob('x', 'ordinal', (0, 2))])


class Sequence(RandomSearcher):
    def suggest(self):
        # One distinct configuration per candidate; no tuning result is needed.
        return Config({'x': len(self.trials)})


def objective(config, seed, evaluation, fidelity=1., trial_id=None):
    if evaluation.role == 'final':
        return {'value': 100. - config['x'] + seed, 'cost': 3.}
    offset = 0 if evaluation.fold.name == 'fold-a' else 10
    return {'value': config['x'] + seed + offset, 'cost': 2.}


def study(**changes):
    args = dict(searcher=Sequence(space(), seed=0), executor=LocalExecutor(), objective_fn=objective,
                declaration=declaration(), budget=3, maximize=False, study_name='declared')
    args.update(changes)
    return Study(**args)


def checkpoint(tmp_path, state):
    p = tmp_path / 'state.json'
    p.write_text(json.dumps(state))
    return p


@pytest.mark.parametrize('case,message', [
    ('legacy_into_declared', 'Checkpoint declaration/evaluation policy differs; explicit migration required'),
    ('declared_into_legacy', 'Checkpoint declaration/evaluation policy differs; explicit migration required'),
    ('declared_schema', 'Checkpoint declaration schema differs'),
    ('legacy_schema', 'Checkpoint declaration schema differs'),
    ('resource_into_plain', 'Checkpoint resource policy differs'),
    ('plain_into_resource', 'Checkpoint resource policy differs'),
    ('resource_schema', 'Checkpoint resource policy differs'),
    ('direction', 'Checkpoint evaluation direction differs'),
    ('admission', 'Checkpoint capability or architecture declaration differs'),
])
def test_checkpoint_policy_mismatches_have_precise_atomic_refusals(tmp_path, case, message):
    import re
    source = study()
    target = study()
    if case in {'resource_into_plain', 'resource_schema'}:
        source = study(objective_fn=metered_objective, resource_budget=budgeted())
    if case in {'plain_into_resource', 'resource_schema'}:
        target = study(objective_fn=metered_objective, resource_budget=budgeted())
    if case == 'legacy_into_declared': source = study(declaration=None, objective_fn=lambda c: 0.)
    if case in {'declared_into_legacy', 'legacy_schema'}:
        target = study(declaration=None, objective_fn=lambda c: 0.)
    if case == 'legacy_schema': source = study(declaration=None, objective_fn=lambda c: 0.)
    state = source._snapshot()
    if case == 'declared_schema': state['schema_version'] = 3
    if case == 'legacy_schema': state['schema_version'] = 4
    if case == 'resource_schema': state['schema_version'] = 4
    if case == 'direction': state['maximize'] = True
    if case == 'admission': state['admission']['architecture_coordinates'] = ['x']
    before = deepcopy(target._snapshot())
    with pytest.raises(ValueError, match='^'+re.escape(message)+'$'):
        target.load_checkpoint(checkpoint(tmp_path, state))
    assert target._snapshot() == before


@pytest.mark.parametrize('field', ['status', 'cost', 'fidelity', 'value'])
def test_trial_accounting_must_agree_with_independently_reconstructed_evaluation(tmp_path, field):
    source = study(); source.run()
    state = deepcopy(source._snapshot())
    state['trials']['declared_trial_0'][field] = {
        'status':'failed', 'cost':999., 'fidelity':2., 'value':math.nan}[field]
    target = study(); before = deepcopy(target._snapshot())
    # Fidelity also participates in raw evaluation reconstruction and may be
    # rejected there before the cross-ledger check.
    message = '^Declared result and trial accounting differ$' if field != 'fidelity' else None
    with pytest.raises(ValueError, match=message):
        target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot() == before


def test_checkpoint_searcher_observation_ledger_cannot_diverge_from_committed_results(tmp_path):
    source=study(); source.run()
    state=deepcopy(source._snapshot())
    state['searcher_state']['history'][0]['cost'] += 1.
    target=study(); before=deepcopy(target._snapshot())
    with pytest.raises(ValueError, match='^Declared searcher and Study observation ledgers differ$'):
        target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot() == before


@pytest.mark.parametrize('field,value', [('budget',4), ('compute_budget_seconds',11.)])
def test_checkpoint_resource_controls_are_checked_independently(tmp_path,field,value):
    source=study(objective_fn=metered_objective,resource_budget=budgeted(tuning_seconds=10.))
    state=source._snapshot(); state[field]=value
    target=study(objective_fn=metered_objective,resource_budget=budgeted(tuning_seconds=10.))
    before=deepcopy(target._snapshot())
    with pytest.raises(ValueError,match='^Checkpoint controls differ from resource contract$'):
        target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot()==before


def test_older_checkpoint_optional_admission_and_cancellation_fields_restore(tmp_path):
    source=study(); state=source._snapshot()
    for key in ('admission','finished','cancel_requested'):
        state.pop(key)
    target=study()
    target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot()==source._snapshot()
    assert target.run().best_value==8.


def test_final_evaluation_requires_an_explicit_completed_tuning_checkpoint(tmp_path):
    source=study(); source.run()
    state=source._snapshot(); state.pop('finished')
    target=study(); before=deepcopy(target._snapshot())
    with pytest.raises(ValueError,match='^Final evaluation began before tuning finished$'):
        target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot()==before


@pytest.mark.parametrize('field', ['partial_fidelity', 'failed_observations'])
def test_recovery_rechecks_current_method_support_before_admitting_checkpoint(tmp_path,field):
    from dataclasses import replace
    class ChangedSupport(Sequence):
        def set_state(self,state):
            super().set_state(state)
            self.support=replace(self.support, **{field:False})
    options = {'searcher':ChangedSupport(space(),seed=0)}
    if field=='partial_fidelity': options['scheduler']=ASHAScheduler(ASHAConfig(r_min=1,r_max=2))
    source=study(**options)
    state=source._snapshot(); state.pop('admission')
    target=study(**{**options, 'searcher':ChangedSupport(space(),seed=0)})
    before=deepcopy(target._snapshot())
    message=('Searcher does not support partial-fidelity Study observations' if field=='partial_fidelity'
        else 'Declared Study requires retained failed-observation support')
    with pytest.raises(ValueError,match='^'+message+'$'):
        target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot()==before


def test_architecture_coordinates_round_trip_through_declared_checkpoint(tmp_path):
    source=study(architecture_coordinates=('x',))
    target=study(architecture_coordinates=('x',))
    target.load_checkpoint(checkpoint(tmp_path,source._snapshot()))
    assert target._snapshot()['admission']['architecture_coordinates']==['x']


def test_vector_recovery_reserves_final_work_for_every_possible_selected_candidate(tmp_path):
    from dataclasses import replace
    budget=budgeted(configurations=6,work_unit='integer_operations',final_work=36.)
    source=vector_study(resource_budget=budget)
    target=vector_study(resource_budget=budget)
    # An edited live resource policy must be revalidated for a vector study;
    # enough reserve for a scalar winner is insufficient for a Pareto front.
    target._resources.budget=replace(budget,final_work=6.)
    before=deepcopy(target._snapshot())
    with pytest.raises(ValueError,match='^Final work reserve cannot cover the maximum frozen selection$'):
        target.load_checkpoint(checkpoint(tmp_path,source._snapshot()))
    assert target._snapshot()==before


def test_progressive_scheduler_checkpoint_uses_its_current_endpoint_for_selection(tmp_path):
    from hponas.schedulers import PASHAConfig, PASHAScheduler
    def make():
        # PASHA needs two observations before its first quantile promotion.
        return study(budget=2,scheduler=PASHAScheduler(PASHAConfig(r_min=1,r_max=8,eta=2)),
            declaration=declaration(tuning_folds=(declaration().tuning_folds[0],),tuning_seeds=(2,)))
    source=make(); expected=source.run()
    assert source.scheduler.current_max_fidelity < source.scheduler.config.r_max
    assert expected.best_value is not None
    target=make(); target.load_checkpoint(checkpoint(tmp_path,source._snapshot()))
    assert target.run().evaluation==expected.evaluation


def test_aggregate_then_select_and_report_sealed_results(tmp_path):
    with closing(Store(tmp_path / 'store.db')) as store:
        run = study(store=store)
        result = run.run()
        # Arithmetic oracle: mean of x+2,x+4,x+12,x+14 is x+8.
        assert [r.objective_value for r in run.searcher.history] == [8., 9., 10.]
        assert result.best_config.values == {'x': 0}
        assert result.best_value == 8.
        first = result.evaluation['tuning'][0]
        assert first['objectives']['loss'] == {'mean':8., 'sample_std':math.sqrt(104/3), 'n':4}
        assert first['expected_repetitions'] == first['recorded_repetitions'] == 4
        assert first['status'] == 'completed'
        assert store.read_report('declared')['evaluation']['tuning'] == result.evaluation['tuning']
        final = result.evaluation['final'][0]
        assert final['objectives']['loss'] == {'mean': 113., 'sample_std': math.sqrt(2.), 'n': 2}
        assert result.total_cost == 3 * 4 * 2 + 2 * 3
        assert len(result.history) == 3
        assert all(r.metadata['evaluation']['role'] == 'tuning' for r in result.history)
        assert store.read_evaluation('declared')['phase'] == 'reported'
        assert len(store.read_trials('declared')) == 3
        # Final's reversed ranking cannot reselect x=2 or enter the searcher.
        assert len(run.searcher.history) == 3 and result.evaluation['selection'] == ['declared_trial_0']
        result.evaluation['selection'].clear()
        assert run.evaluation_report()['selection'] == ['declared_trial_0']


@pytest.mark.parametrize('call', [2, 5, 13, 14])
@pytest.mark.parametrize('backend', ['file', 'store'])
def test_resume_at_tuning_and_final_boundaries_repeats_only_uncommitted_call(tmp_path, call, backend):
    seen = []
    def interrupted(config, seed, evaluation, trial_id):
        seen.append(trial_id)
        if len(seen) == call:
            raise KeyboardInterrupt('simulated crash')
        return objective(config, seed, evaluation)
    with closing(Store(tmp_path / 'store.db')) as store:
        original = study(objective_fn=interrupted, store=store, checkpoint_dir=tmp_path)
        with pytest.raises(KeyboardInterrupt):
            original.run()
        raw = store.load_study_snapshot('declared')
        committed = {r['result']['trial_id'] for role in ('tuning', 'final') for rows in raw['evaluation'][role].values() for r in rows}
        resumed_calls = []
        def resumed_objective(config, seed, evaluation, trial_id):
            resumed_calls.append(trial_id)
            return objective(config, seed, evaluation)
        restored = study(objective_fn=resumed_objective, store=store)
        restored.load_checkpoint(None if backend == 'store' else tmp_path / 'declared_checkpoint.json')
        result = restored.run()
        assert not set(resumed_calls) & committed
        assert resumed_calls[0] == seen[-1]
        assert result.evaluation['uncertain_evaluations'] == [seen[-1]]
        assert result.best_value == 8.
        assert result.evaluation['final'][0]['objectives']['loss']['mean'] == 113.
        assert len(restored.searcher.history) == 3


def test_checkpoint_after_final_commit_does_not_reevaluate_or_reselect(tmp_path):
    source = study()
    expected = source.run()
    def forbidden(config, seed, evaluation):
        pytest.fail('committed objective reran')
    target = study(objective_fn=forbidden)
    target.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    target.budget = 100  # An accidental edit cannot reopen frozen selection.
    actual = target.run()
    assert actual.best_value == expected.best_value
    assert actual.evaluation == expected.evaluation
    assert len(target.searcher.history) == 3


@pytest.mark.parametrize('field,value', [('objective_id','other:v1'),('model_id','other'),('data_id','other'),
                                       ('protocol_id','other'),('tuning_seeds',(2,5)),('final_seeds',(99,))])
def test_changed_identity_refused_without_modifying_live_study(tmp_path, field, value):
    original = study(); original.run()
    target = study(declaration=declaration(**{field:value}))
    before = deepcopy(target._snapshot())
    with pytest.raises(ValueError, match='identity differs'):
        target.load_checkpoint(checkpoint(tmp_path, original._snapshot()))
    assert target._snapshot() == before


@pytest.mark.parametrize('case', ['aggregate', 'raw_seed', 'selection', 'final_in_tuning', 'missing_final',
                                'unknown_final', 'reported_inflight', 'raw_vector', 'direction', 'elapsed',
                                'aggregate_elapsed', 'searcher_final', 'uncertainty', 'boolean_seed'])
def test_corrupt_evaluation_checkpoint_is_refused_atomically(tmp_path, case):
    original = study(); original.run()
    state = deepcopy(original._snapshot())
    e = state['evaluation']
    if case == 'aggregate': state['results']['declared_trial_0']['objective_value'] = -99.
    elif case == 'raw_seed': e['tuning']['declared_trial_0'][0]['seed'] = 999
    elif case == 'selection': e['selection'] = ['declared_trial_2']
    elif case == 'final_in_tuning': e['phase'] = 'tuning'
    elif case == 'missing_final': e['final']['declared_trial_0'].pop()
    elif case == 'unknown_final': e['final']['declared_trial_2'] = deepcopy(e['final']['declared_trial_0'])
    elif case == 'reported_inflight': e['inflight'] = {'role':'final','parent':'declared_trial_0','index':2,'trial_id':'uncommitted'}
    elif case == 'raw_vector': e['tuning']['declared_trial_0'][0]['result']['cost'] = -1.
    elif case == 'direction': state['maximize'] = True
    elif case == 'elapsed': e['final']['declared_trial_0'][0]['result']['metadata']['execution']['elapsed_seconds'] = -1.
    elif case == 'aggregate_elapsed': state['results']['declared_trial_0']['metadata']['execution']['elapsed_seconds'] += 10
    elif case == 'searcher_final': state['searcher_state']['history'].append(e['final']['declared_trial_0'][0]['result'])
    elif case == 'uncertainty': e['uncertain'] = [e['tuning']['declared_trial_0'][0]['result']['trial_id']]
    elif case == 'boolean_seed': e['tuning']['declared_trial_0'][0]['seed'] = True
    target = study(); before = deepcopy(target._snapshot())
    with pytest.raises(ValueError): target.load_checkpoint(checkpoint(tmp_path,state))
    assert target._snapshot() == before


@pytest.mark.parametrize('bad', [
    lambda: EvaluationFold('overlap', ('a',), ('a',)),
    lambda: EvaluationFold('entities', ('a',), ('b',), mode='grouped', train_groups=('g',), score_groups=('g',)),
    lambda: EvaluationFold('future', ('a',), ('b',), mode='temporal', train_until=10, score_from=9),
    lambda: EvaluationFold('gap', ('a',), ('b',), mode='temporal', train_until=10, score_from=11, gap=2),
    lambda: declaration(final_seeds=(2,)),
    lambda: declaration(final_folds=(EvaluationFold('holdout', ('new',), ('score-a',)),)),
    lambda: declaration(final_folds=()),
    lambda: declaration(tuning_seeds=(True,)),
])
def test_leakage_and_missing_roles_refused_before_execution(bad):
    with pytest.raises(ValueError): bad()


def test_final_entity_and_temporal_exposure_are_checked():
    tune = EvaluationFold('tune', ('a',), ('b',), mode='grouped', train_groups=('alice',), score_groups=('bob',))
    final = EvaluationFold('final', ('a',), ('new-bob-row',), mode='grouped', train_groups=('alice',), score_groups=('bob',))
    with pytest.raises(ValueError, match='entities were exposed'):
        declaration(tuning_folds=(tune,), final_folds=(final,))
    tune = EvaluationFold('tune', ('a',), ('b',), mode='temporal', train_until=5, score_from=10, score_until=12)
    final = EvaluationFold('final', ('a',), ('c',), mode='temporal', train_until=6, score_from=11, score_until=13)
    with pytest.raises(ValueError, match='follow tuning'):
        declaration(tuning_folds=(tune,), final_folds=(final,))


def test_failed_repetition_is_retained_and_never_dropped_from_average(tmp_path):
    def failed(config, seed, evaluation):
        if config['x'] == 0 and seed == 4:
            return {'value': math.nan, 'cost': 5.}
        return objective(config, seed, evaluation)
    source = study(objective_fn=failed)
    result = source.run()
    assert result.best_config.values == {'x':1}
    assert result.history[0].status == 'failed'
    assert math.isnan(result.history[0].objective_value)
    assert result.history[0].cost == 14.
    assert len(result.history[0].metadata['evaluation']['records']) == 4
    summary = result.evaluation['tuning'][0]
    assert summary['status'] == 'failed' and summary['recorded_repetitions'] == 4
    assert summary['objectives']['loss'] == {'mean':None,'sample_std':None,'n':0}
    target = study(objective_fn=failed)
    target.load_checkpoint(checkpoint(tmp_path,source._snapshot()))
    assert target.run().best_config.values == {'x':1}


def test_failed_final_cannot_fall_back_to_a_different_candidate(tmp_path):
    def failed(config, seed, evaluation):
        return {'value':math.nan,'cost':5.} if evaluation.role == 'final' else objective(config,seed,evaluation)
    with closing(Store(tmp_path / 'failed.db')) as store:
        source = study(objective_fn=failed, store=store)
        result = source.run()
        assert store.read_study('declared').status == 'evaluation_failed'
    assert result.best_config.values == {'x':0}
    assert result.evaluation['final'][0]['status'] == 'failed'
    assert result.evaluation['outcome'] == 'failed'
    assert result.status == 'final_evaluation_failed'
    assert result.evaluation['final'][0]['objectives']['loss']['mean'] is None
    assert len(source.searcher.history) == 3


def test_opt_out_and_legacy_are_explicit_and_not_upgradeable(tmp_path):
    d = declaration(final_folds=(),final_seeds=(),opt_out_reason='Exposed deterministic arithmetic fixture')
    source = study(declaration=d)
    assert source.run().evaluation['status'] == 'opted_out'
    assert source.evaluation_report()['opt_out_reason'] == d.opt_out_reason
    legacy = study(declaration=None, objective_fn=lambda c: c['x'])
    assert legacy.run().evaluation['status'] == 'legacy_unqualified'
    with pytest.raises(ValueError, match='explicit migration'):
        study().load_checkpoint(checkpoint(tmp_path,legacy._snapshot()))
    with pytest.raises(ValueError, match='explicit migration'):
        legacy.load_checkpoint(checkpoint(tmp_path,source._snapshot()))


@pytest.mark.parametrize('fn', [lambda c: 0., lambda c, evaluation:0., lambda c, seed, evaluation, reporter:0.])
def test_missing_role_seed_or_streaming_is_explicitly_refused(fn):
    with pytest.raises(ValueError): study(objective_fn=fn)


OBJECTIVES = [{'name':'error','direction':'min','lower':0.,'upper':200.},
              {'name':'size','direction':'min','lower':0.,'upper':10.}]


def vector_declaration():
    return declaration(objectives=(EvaluationObjective('error','min','squared_units'), EvaluationObjective('size','min','parameters')))


def vector_objective(config, seed, evaluation):
    x = config['x']
    return {'objectives':{'error': (2-x)**2 + (100 if evaluation.role == 'final' else seed), 'size':x+1.},
            'constraints':{'residual':0.1 if x != 2 or seed != 4 else 0.9}, 'work':2, 'cost':1.}


def vector_study(**changes):
    args = dict(searcher=MultiObjectiveRandomSearcher(space(),objectives=OBJECTIVES,constraints={'residual':.5},seed=4),
                executor=LocalExecutor(),objective_fn=vector_objective,objectives=OBJECTIVES,constraints={'residual':.5},
                declaration=vector_declaration(),budget=6,study_name='vector')
    args.update(changes)
    return MultiObjectiveStudy(**args)


def test_vector_aggregation_requires_every_constraint_and_keeps_frozen_front(tmp_path):
    source = vector_study(); result = source.run()
    assert {row['config']['x'] for row in result.front} == {0,1}
    assert all(row['constraints']['residual'] <= .5 for row in result.front)
    for row in result.evaluation['tuning']:
        x = source.trials[row['trial_id']].config['x']
        assert row['objectives']['error'] == {'mean':(2-x)**2+3., 'sample_std':math.sqrt(4/3), 'n':4}
        assert row['objectives']['size'] == {'mean':x+1., 'sample_std':0., 'n':4}
        assert row['feasible'] is (x != 2)
    for tid, trial in source.trials.items():
        if trial.config['x']==2:
            assert source.results[tid].metadata['multi_objective']['constraints']['residual']==.9
    assert result.metrics['total_work'] == 6*4*2
    assert len(source.searcher.history) == 6
    assert all(row['objectives']['error']['mean'] >=100 for row in result.evaluation['final'])
    target = vector_study()
    target.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    assert target.run().evaluation == result.evaluation


def test_endpoint_promotions_resume_each_repetitions_own_checkpoint(tmp_path):
    calls=[]
    def endpoint(config,seed,evaluation,fidelity,checkpoint=None,resume_from=0.):
        calls.append((evaluation.role,seed,evaluation.fold.name,fidelity,resume_from,checkpoint))
        if resume_from:
            assert checkpoint == {'seed':seed,'fold':evaluation.fold.name,'fidelity':resume_from}
        return {'value':config['x']+seed, 'cost':fidelity-resume_from,
                'checkpoint':{'seed':seed,'fold':evaluation.fold.name,'fidelity':fidelity}}
    scheduler=ASHAScheduler(ASHAConfig(eta=2,r_min=1,r_max=2,promotion_policy='legacy_bootstrap'))
    run = study(objective_fn=endpoint,scheduler=scheduler,continuation='resume',budget=2)
    run.run()
    assert any(row[4] > 0 for row in calls if row[0]=='tuning')
    assert all(row[4]==0 and row[5] is None for row in calls if row[0]=='final')


def test_partial_final_has_no_premature_average():
    count = 0
    def interrupted(config, seed, evaluation):
        nonlocal count
        if evaluation.role == 'final':
            count += 1
            if count == 2:
                raise KeyboardInterrupt
        return objective(config, seed, evaluation)
    run = study(objective_fn=interrupted)
    with pytest.raises(KeyboardInterrupt): run.run()
    report = run.evaluation_report()
    assert report['status'] == 'final_evaluation'
    assert report['final'][0]['status'] == 'incomplete'
    assert report['final'][0]['recorded_repetitions'] == 1
    assert report['final'][0]['objectives']['loss']['mean'] is None


def test_partial_tuning_summary_does_not_drop_unfinished_repetitions(tmp_path):
    calls = 0
    def interrupted(config, seed, evaluation):
        nonlocal calls
        calls += 1
        if calls == 2: raise KeyboardInterrupt
        return objective(config, seed, evaluation)
    source = study(objective_fn=interrupted, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt): source.run()
    row = source.evaluation_report()['tuning'][0]
    assert row['status'] == 'incomplete'
    assert (row['recorded_repetitions'],row['expected_repetitions']) == (1,4)
    assert row['objectives']['loss'] == {'mean':None,'sample_std':None,'n':0}
    restored = study(); restored.load_checkpoint(tmp_path/'declared_checkpoint.json')
    assert restored.evaluation_report()['tuning'] == [row]
    result = restored.run()
    assert result.evaluation['tuning'][0]['objectives']['loss'] == {
        'mean':8.,'sample_std':math.sqrt(104/3),'n':4}


def test_single_repetition_reports_no_sample_spread():
    contract = declaration(tuning_folds=(EvaluationFold('single',('train',),('score',)),),
                           tuning_seeds=(2,))
    source = study(declaration=contract, budget=1)
    result = source.run()
    assert result.evaluation['tuning'][0]['objectives']['loss'] == {
        'mean':12.,'sample_std':None,'n':1}


@pytest.mark.parametrize('boundary', ['aggregate', 'freeze', 'final_complete', 'reported'])
def test_crash_after_committed_boundaries_never_repeats_measurements(tmp_path, boundary):
    calls = []
    def measured(config, seed, evaluation, trial_id):
        calls.append(trial_id)
        return objective(config, seed, evaluation)
    source = study(objective_fn=measured, checkpoint_dir=tmp_path)
    save = source.save_checkpoint
    def crash():
        save()
        e = source._evaluation.state
        condition = {
            'aggregate': len(e['tuning'].get('declared_trial_0', [])) == 4 and not source.results,
            'freeze': e['phase'] == 'selection_frozen',
            'final_complete': e['phase'] == 'final_evaluation' and len(e['final'].get('declared_trial_0', [])) == 2,
            'reported': e['phase'] == 'reported',
        }[boundary]
        if condition: raise KeyboardInterrupt
    source.save_checkpoint = crash
    with pytest.raises(KeyboardInterrupt): source.run()
    target = study(objective_fn=measured)
    target.load_checkpoint(tmp_path / 'declared_checkpoint.json')
    assert target.run().best_value == 8.
    assert len(calls) == len(set(calls)) == 14


def test_async_executor_uses_declared_roles():
    result = study(executor=LocalExecutor(mode='async', max_workers=2)).run()
    assert result.best_value == 8.
    assert result.evaluation['outcome'] == 'completed'


@pytest.mark.parametrize('last', [False, True])
def test_cancelled_repetitions_are_accounted_and_restore(tmp_path, last):
    calls = []
    def cancel(config, seed, evaluation):
        calls.append((config['x'], seed))
        if config['x'] == 0 and (not last or len(calls) == 4):
            source.cancel_trial('declared_trial_0')
        return objective(config, seed, evaluation)
    source = study(objective_fn=cancel)
    result = source.run()
    assert result.best_config.values == {'x': 1}
    assert result.history[0].status == 'cancelled'
    assert result.history[0].cost == (8. if last else 2.)
    target = study()
    target.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    assert target.run().evaluation == result.evaluation


@pytest.mark.parametrize('vector', [False, True])
def test_cancellation_after_aggregation_preserves_raw_work_and_recoverable_selection(tmp_path, vector):
    source = vector_study() if vector else study()
    tid = ('vector' if vector else 'declared') + '_trial_0'
    aggregate = source._evaluation.aggregate
    reached = []

    def cancel_at_accept_boundary(trial, rows, **kwargs):
        value = aggregate(trial, rows, **kwargs)
        if trial.trial_id == tid and not reached:
            # A cancellation may arrive after the aggregate was computed, before
            # the coordinator accepts it. Use the public request at that boundary.
            reached.append(deepcopy(value.to_dict()))
            source.cancel_trial(tid)
        return value

    source._evaluation.aggregate = cancel_at_accept_boundary
    result = source.run()
    assert len(reached) == 1 and reached[0]['status'] == 'completed'
    cancelled = source.results[tid]
    assert cancelled.status == 'cancelled' and math.isnan(cancelled.objective_value)
    assert cancelled.cost == reached[0]['cost'] == (4. if vector else 8.)
    assert cancelled.metadata['execution'] == reached[0]['metadata']['execution']
    assert cancelled.metadata['evaluation']['records'] == reached[0]['metadata']['evaluation']['records']
    assert all(r['result']['status'] == 'completed' for r in cancelled.metadata['evaluation']['records'])
    assert tid not in result.evaluation['selection']
    assert result.evaluation['outcome'] == 'completed'
    if vector:
        payload = cancelled.metadata['multi_objective']
        assert payload['status'] == 'failed' and payload['work'] == 8.
        assert cancelled.metadata['multi_objective_context'] == {
            'root_trial_id': tid, 'endpoint_fidelity': 1.}
        assert all(row['trial_id'] != tid for row in result.front)
    else:
        assert result.best_config.values == {'x': 1}
    saved = source._snapshot()
    restored = vector_study() if vector else study()
    restored.load_checkpoint(checkpoint(tmp_path, saved))
    actual = restored.run()
    assert actual.evaluation == result.evaluation
    assert actual.total_cost == result.total_cost
    assert restored.results[tid].status == 'cancelled'


def test_time_cap_accounts_for_partial_group_without_double_counting(tmp_path):
    class Metered(LocalExecutor):
        def execute(self, trial, fn, **kwargs):
            result = super().execute(trial, fn, **kwargs)
            result.metadata['execution']['elapsed_seconds'] = 2.
            return result
    source = study(executor=Metered(), compute_budget_seconds=5)
    with pytest.raises(IncompleteStudyError) as exc: source.run()
    assert source._elapsed() == 6.
    assert source.results['declared_trial_0'].cost == 6.
    assert exc.value.result.evaluation['outcome'] == 'no_selection'
    target = study(executor=Metered(), compute_budget_seconds=5)
    target.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    with pytest.raises(IncompleteStudyError): target.run()
    assert target._elapsed() == 6.


def test_vector_interrupted_repetition_restores_accounting(tmp_path):
    calls = []
    def interrupted(config, seed, evaluation, trial_id):
        calls.append(trial_id)
        if len(calls) == 2: raise KeyboardInterrupt
        return vector_objective(config, seed, evaluation)
    source = vector_study(objective_fn=interrupted, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt): source.run()
    target = vector_study()
    target.load_checkpoint(tmp_path / 'vector_checkpoint.json')
    result = target.run()
    assert result.metrics['exact_work'] is False
    restored = vector_study()
    restored.load_checkpoint(checkpoint(tmp_path, target._snapshot()))
    assert restored.run().evaluation == result.evaluation


def test_declared_resume_signature_refused_before_any_dispatch():
    with pytest.raises(ValueError, match='checkpoint and resume_from'):
        study(continuation='resume')


def test_documented_example_recovers_and_matches_analytic_reference(tmp_path):
    from examples.declared_tuning import run, make_study
    report = run(tmp_path)
    x = report['best_config']['values']['x']
    assert report['best_value'] == (x - 2.) ** 2
    assert report['evaluation']['final'][0]['objectives']['loss']['mean'] == (x - 2.) ** 2
    restored = make_study(tmp_path)
    restored.load_checkpoint(tmp_path / 'declared_example_checkpoint.json')
    assert restored.run().evaluation == report['evaluation']


def budgeted(**changes):
    args = dict(configurations=3, work_unit='operations', tuning_work=100., final_work=6.,
                max_work_per_call=3., full_run_work=12.)
    args.update(changes)
    return StudyBudget(**args)


def metered_objective(config, seed, evaluation):
    assert evaluation.work_limit == 3. and evaluation.work_unit == 'operations'
    row = objective(config, seed, evaluation)
    row['metadata'] = {'resource':{'work':2. if evaluation.role == 'tuning' else 3., 'unit':'operations'}}
    return row


def test_work_reserve_separates_roles_and_counts_every_repetition(tmp_path):
    budget = budgeted(tuning_work=12.)
    source = study(objective_fn=metered_objective, resource_budget=budget)
    result = source.run()
    # Four calls complete candidate 0 (8 work); candidate 1 spends 2 before
    # the next 3-unit reservation is refused. The independent final pool is 6.
    assert result.best_value == 8.
    assert result.reason == 'tuning_work_exhausted'
    assert result.resources['tuning']['measured_work'] == 10.
    assert result.resources['final']['measured_work'] == 6.
    assert result.resources['final']['full_run_equivalents'] == .5
    assert result.resources['tuning']['attempts'] == 5
    assert result.resources['configurations_proposed'] == 2
    target = study(objective_fn=metered_objective, resource_budget=budget)
    target.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    assert target.run().resources == result.resources


def test_exhaustion_between_complete_candidates_does_not_propose_undispatchable_work(tmp_path):
    # One full candidate costs 8; the next 3-unit call cannot fit in a 10-unit pool.
    budget = budgeted(tuning_work=10.)
    source = study(objective_fn=metered_objective, resource_budget=budget, checkpoint_dir=tmp_path)
    result = source.run()
    assert result.reason == 'tuning_work_exhausted'
    assert result.n_trials == result.resources['configurations_proposed'] == 1
    assert result.resources['tuning']['attempts'] == 4
    assert result.resources['tuning']['measured_work'] == 8.
    assert result.resources['final']['measured_work'] == 6.
    assert len(result.evaluation['tuning']) == 1
    saved = json.loads((tmp_path / 'declared_checkpoint.json').read_text())
    assert set(saved['trials']) == set(saved['results']) == {'declared_trial_0'}
    restored = study(objective_fn=metered_objective, resource_budget=budget)
    restored.load_checkpoint(tmp_path / 'declared_checkpoint.json')
    assert restored.run().resources == result.resources


@pytest.mark.parametrize('call', [2, 13])
def test_unknown_attempt_consumes_reservation_and_cannot_spend_twice(tmp_path, call):
    seen = []
    def crash(config, seed, evaluation, trial_id):
        seen.append(trial_id)
        if len(seen) == call: raise KeyboardInterrupt
        return metered_objective(config, seed, evaluation)
    budget = budgeted()
    source = study(objective_fn=crash, resource_budget=budget, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt): source.run()
    target = study(objective_fn=metered_objective, resource_budget=budget)
    target.load_checkpoint(tmp_path/'declared_checkpoint.json')
    result = target.run()
    role = 'tuning' if call == 2 else 'final'
    usage = result.resources[role]
    assert usage['charged_work'] == usage['measured_work'] + 3.
    assert usage['work_exact'] is False and usage['lost_attempts'] == 1
    if role == 'final':
        assert result.evaluation['outcome'] == 'failed'
        assert result.evaluation['final'][0]['records'][1]['result']['metadata']['stop_reason'] == 'final_work_exhausted'
    again = study(objective_fn=metered_objective, resource_budget=budget)
    again.load_checkpoint(checkpoint(tmp_path, target._snapshot()))
    assert again.run().resources == result.resources


@pytest.mark.parametrize('bad_meter', ['missing', 'wrong_unit', 'overrun', 'nan'])
def test_bad_meter_cannot_create_unreported_free_work(bad_meter):
    calls = []
    def bad(config, seed, evaluation):
        calls.append(seed)
        row = metered_objective(config, seed, evaluation)
        if bad_meter == 'missing': row.pop('metadata')
        elif bad_meter == 'wrong_unit': row['metadata']['resource']['unit'] = 'seconds'
        elif bad_meter == 'overrun': row['metadata']['resource']['work'] = 4.
        else: row['metadata']['resource']['work'] = math.nan
        return row
    run = study(objective_fn=bad, resource_budget=budgeted())
    with pytest.raises(IncompleteStudyError) as exc: run.run()
    assert len(calls) == 1
    usage = exc.value.result.resources['tuning']
    assert usage['contract_breaches'] == 1
    assert usage['charged_work'] == (4. if bad_meter == 'overrun' else 3.)
    assert exc.value.result.reason == 'tuning_resource_contract_breach'


def test_elapsed_limits_have_explicit_overshoot_and_independent_final_cap():
    class Clocked(LocalExecutor):
        def execute(self, trial, fn, **kwargs):
            result = super().execute(trial, fn, **kwargs)
            result.metadata['execution']['elapsed_seconds'] = 2.
            return result
    result = study(objective_fn=metered_objective, executor=Clocked(),
                   resource_budget=budgeted(tuning_seconds=9., final_seconds=3.)).run()
    assert result.resources['tuning']['elapsed_seconds'] == 10.
    assert result.resources['tuning']['seconds_overshoot'] == 1.
    assert result.resources['final']['elapsed_seconds'] == 4.
    assert result.resources['final']['seconds_overshoot'] == 1.


def test_resource_declaration_conflicts_refused_before_execution():
    cases = [dict(resource_budget=budgeted(configurations=2)),
             dict(resource_budget=budgeted(configurations=1),budget=True),
             dict(resource_budget=budgeted(tuning_seconds=1),compute_budget_seconds=True),
             dict(resource_budget=budgeted(final_work=5.)),
             dict(resource_budget=budgeted(worker_capacity=1),max_concurrent=2),
             dict(resource_budget=budgeted(),compute_budget_seconds=2.),
             dict(resource_budget=budgeted(),declaration=None)]
    for change in cases:
        with pytest.raises(ValueError): study(**change)
    with pytest.raises(ValueError, match='maximum frozen selection'):
        vector_study(resource_budget=budgeted(configurations=6,work_unit='integer_operations',final_work=6.))


@pytest.mark.parametrize('field', ['contract', 'measured_work', 'elapsed', 'attempt_id', 'missing', 'raw_index', 'admission'])
def test_resource_ledger_corruption_refused_atomically(tmp_path, field):
    source = study(objective_fn=metered_objective, resource_budget=budgeted()); source.run()
    state = deepcopy(source._snapshot())
    r = state['resources']
    if field == 'contract': r['contract']['tuning_work'] += 1
    elif field == 'measured_work': r['attempts'][0]['work'] = 0.
    elif field == 'elapsed': r['attempts'][0]['elapsed'] = -1.
    elif field == 'attempt_id': r['attempts'][0]['trial_id'] = 'unknown'
    elif field == 'missing': r['attempts'].pop()
    elif field == 'raw_index': state['evaluation']['final']['declared_trial_0'][0]['result']['metadata']['resource_attempt'] = True
    else: state['admission']['contract']['partial_fidelity'] = False
    target = study(objective_fn=metered_objective, resource_budget=budgeted())
    before = deepcopy(target._snapshot())
    with pytest.raises(ValueError): target.load_checkpoint(checkpoint(tmp_path, state))
    assert target._snapshot() == before


def test_vector_work_meter_charges_raw_repetitions_and_final_front():
    result = vector_study(resource_budget=budgeted(configurations=6,work_unit='integer_operations',final_work=36.)).run()
    assert result.resources['tuning']['measured_work'] == 6*4*2
    assert result.resources['final']['measured_work'] == len(result.front)*2*2


def test_budgeted_promotion_charges_incremental_work_and_restarts_final():
    def endpoint(config, seed, evaluation, fidelity, checkpoint=None, resume_from=0.):
        return {'value':config['x']+seed, 'cost':fidelity-resume_from,
                'metadata':{'resource':{'work':fidelity-resume_from,'unit':'operations'}},
                'checkpoint':{'seed':seed,'fidelity':fidelity}}
    scheduler = ASHAScheduler(ASHAConfig(eta=2,r_min=1,r_max=2,promotion_policy='legacy_bootstrap'))
    result = study(objective_fn=endpoint,scheduler=scheduler,continuation='resume',budget=2,
                   resource_budget=budgeted(configurations=2)).run()
    assert result.resources['tuning']['measured_work'] == sum(r.cost for r in result.history)
    assert result.resources['tuning']['measured_work'] == 4*len(result.history)
    assert result.resources['final']['measured_work'] == 4.


def test_interrupted_elapsed_cannot_be_assumed_zero_under_time_cap(tmp_path):
    def crash(config, seed, evaluation): raise KeyboardInterrupt
    budget = budgeted(tuning_seconds=100.)
    source = study(objective_fn=crash, resource_budget=budget, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt): source.run()
    calls = []
    def forbidden(config, seed, evaluation):
        calls.append(seed)
        return metered_objective(config, seed, evaluation)
    target = study(objective_fn=forbidden, resource_budget=budget)
    target.load_checkpoint(tmp_path/'declared_checkpoint.json')
    with pytest.raises(IncompleteStudyError) as exc: target.run()
    assert calls == []
    assert exc.value.result.resources['tuning']['elapsed_exact'] is False
    assert exc.value.result.reason == 'tuning_elapsed_unknown'
    final = study(objective_fn=forbidden, resource_budget=budget)
    final.load_checkpoint(checkpoint(tmp_path, target._snapshot()))
    with pytest.raises(IncompleteStudyError): final.run()


def test_budgeted_vector_final_failure_preserves_measured_work(tmp_path):
    def failed(config, seed, evaluation):
        if evaluation.role == 'final':
            return {'objectives':None,'constraints':None,'work':2,'status':'failed','cost':3.}
        return vector_objective(config, seed, evaluation)
    budget = budgeted(configurations=6,work_unit='integer_operations',final_work=36.)
    source = vector_study(objective_fn=failed, resource_budget=budget)
    result = source.run()
    assert result.status == 'final_evaluation_failed'
    assert result.resources['final']['measured_work'] == 4*len(result.front)
    restored = vector_study(objective_fn=failed, resource_budget=budget)
    restored.load_checkpoint(checkpoint(tmp_path, source._snapshot()))
    assert restored.run().resources == result.resources


@pytest.mark.parametrize('cap', [100, 100.])
def test_matching_explicit_and_declared_time_caps_preserve_resource_budget(cap):
    source = study(objective_fn=metered_objective,
                   resource_budget=budgeted(tuning_seconds=100.), compute_budget_seconds=cap)
    result = source.run()
    assert result.status == 'completed'
    assert result.resources['tuning']['seconds_limit'] == 100.
    assert result.resources['tuning']['measured_work'] == 24.
    assert result.resources['configurations_proposed'] == 3


def test_declared_maximization_selects_largest_tuning_mean_before_final(tmp_path):
    contract = declaration(objectives=(EvaluationObjective('loss', 'max', 'squared_units'),))
    source = study(declaration=contract, maximize=True, checkpoint_dir=tmp_path)
    result = source.run()
    assert result.best_config.values == {'x': 2} and result.best_value == 10.
    assert result.evaluation['selection'] == ['declared_trial_2']
    assert result.evaluation['final'][0]['objectives']['loss']['mean'] == 111.
    target = study(declaration=contract, maximize=True)
    target.load_checkpoint(tmp_path/'declared_checkpoint.json')
    assert target.run().evaluation == result.evaluation


def test_declared_searcher_must_retain_failed_observations_before_any_work():
    from dataclasses import replace

    search = Sequence(space(), seed=0)
    search.support = replace(search.support, failed_observations=False)
    with pytest.raises(ValueError, match='retained failed-observation support'):
        study(searcher=search, objective_fn=lambda config, seed, evaluation:
              pytest.fail('Unsupported searcher executed objective work'))
    assert search.history == [] and search.trials == {}


def test_vector_work_unit_disagreement_refuses_before_proposal_or_dispatch():
    search = MultiObjectiveRandomSearcher(space(), objectives=OBJECTIVES,
                                         constraints={'residual': .5}, seed=4)
    with pytest.raises(ValueError, match='Vector work unit differs from resource budget'):
        vector_study(searcher=search, resource_budget=budgeted(configurations=6,
            work_unit='different_operations', final_work=36.))
    assert search.history == [] and search.trials == {}


def test_final_vector_infeasibility_is_a_durable_outcome_without_reselection(tmp_path):
    def endpoint(config, seed, evaluation):
        row = vector_objective(config, seed, evaluation)
        if evaluation.role == 'final':
            row['constraints']['residual'] = 1.
        return row

    source = vector_study(objective_fn=endpoint, checkpoint_dir=tmp_path)
    result = source.run()
    assert result.status == result.reason == 'final_evaluation_infeasible'
    assert result.evaluation['outcome'] == 'infeasible'
    assert {row['config']['x'] for row in result.front} == {0, 1}
    assert result.evaluation['selection'] == [row['trial_id'] for row in result.front]
    assert all(row['feasible'] is False for row in result.evaluation['final'])
    assert len(source.searcher.history) == 6
    target = vector_study(objective_fn=endpoint)
    target.load_checkpoint(tmp_path/'vector_checkpoint.json')
    recovered = target.run()
    assert recovered.status == recovered.reason == 'final_evaluation_infeasible'
    assert recovered.evaluation == result.evaluation
