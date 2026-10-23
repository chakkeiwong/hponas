"""Public Study registers a vector batch before any interrupted dispatch."""
from statistics import mean

import pytest
from hponas import (Knob, SearchSpace, MultiObjectiveBayesSearcher, MultiObjectiveStudy,
                    LocalExecutor, StudyDeclaration, EvaluationFold, EvaluationObjective)
from hponas.store import Store


def test_vector_batch_budget_and_crash_resume(tmp_path):
    objectives=[dict(name='a',direction='min',lower=0.,upper=10.),
                dict(name='b',direction='max',lower=0.,upper=10.)]
    def objective(config):
        x=config['x']
        return dict(objectives={'a':float(x*x),'b':float(x)},constraints={},work=1,cost=1.)
    def make(fn,name):
        searcher=MultiObjectiveBayesSearcher(SearchSpace([Knob('x','ordinal',(0,3))]),
            objectives=objectives,seed=4,n_initial=2,candidate_count=4,mc_samples=8,fit_maxiter=4)
        return MultiObjectiveStudy(searcher,LocalExecutor(),fn,objectives=objectives,
            max_concurrent=2,budget=5,study_name=name,store=Store(tmp_path/(name+'.db')), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    calls=[]
    def interrupted(config):
        calls.append(config)
        if len(calls)==3:raise KeyboardInterrupt('joint batch dispatch')
        return objective(config)
    first=make(interrupted,'resume')
    with pytest.raises(KeyboardInterrupt):first.run()
    assert len(first._pending)==2
    pending=[first.trials[t].config for t in first._pending]
    restored=make(objective,'resume');restored.load_checkpoint()
    assert [restored.trials[t].config for t in restored._pending]==pending
    actual=restored.run();full=make(objective,'full');expected=full.run()
    assert actual.n_trials==expected.n_trials==5
    assert [t.config for t in restored.trials.values()]==[t.config for t in full.trials.values()]
    assert [r.metadata['multi_objective'] for r in actual.history]==[r.metadata['multi_objective'] for r in expected.history]
    assert any(row['q']==2 for row in restored.searcher.acquisition_trace)


def test_joint_batch_recovery_with_repeated_tuning_and_sealed_final(tmp_path):
    objectives = [dict(name='a', direction='min', lower=0., upper=200.),
                  dict(name='b', direction='max', lower=0., upper=30.)]
    declaration = StudyDeclaration(
        objective_id='vector-arithmetic:v1', model_id='integer:v1', data_id='finite:v1',
        protocol_id='joint-repeated:v1',
        objectives=(EvaluationObjective('a', 'min', 'squared_units'),
                    EvaluationObjective('b', 'max', 'units')),
        tuning_folds=(EvaluationFold('a', ('train-a',), ('score-a',)),
                      EvaluationFold('b', ('train-b',), ('score-b',))),
        final_folds=(EvaluationFold('holdout', ('refit',), ('sealed',)),),
        tuning_seeds=(0, 2), final_seeds=(10, 12))

    def objective(config, seed, evaluation):
        x = config['x']
        offset = 3 if evaluation.fold.name == 'b' else 0
        return dict(objectives={'a': float(x*x+seed+offset+(100 if evaluation.role == 'final' else 0)),
                                'b': float(x+seed)}, constraints={}, work=1, cost=1.)

    def make(fn, name):
        searcher = MultiObjectiveBayesSearcher(SearchSpace([Knob('x', 'ordinal', (0, 5))]),
            objectives=objectives, seed=4, n_initial=2, candidate_count=6,
            mc_samples=8, fit_maxiter=4)
        return MultiObjectiveStudy(searcher, LocalExecutor(), fn, objectives=objectives,
            max_concurrent=2, budget=5, declaration=declaration, study_name='joint-declared',
            store=Store(tmp_path/(name+'.db')))

    calls = []
    def interrupted(config, seed, evaluation):
        calls.append((seed, evaluation.fold.name, evaluation.role))
        if len(calls) == 9:
            raise KeyboardInterrupt('Before first repetition of third candidate')
        return objective(config, seed, evaluation)

    source = make(interrupted, 'resume-declared')
    with pytest.raises(KeyboardInterrupt):
        source.run()
    assert len(source._pending) == 2
    pending = [(tid, source.trials[tid].config) for tid in source._pending]
    resumed = make(objective, 'resume-declared')
    resumed.load_checkpoint()
    assert [(tid, resumed.trials[tid].config) for tid in resumed._pending] == pending
    actual = resumed.run()
    full = make(objective, 'full-declared')
    expected = full.run()

    def projection(study):
        return [(tid, trial.config, study.results[tid].metadata['multi_objective'])
                for tid, trial in study.trials.items()]
    assert projection(resumed) == projection(full)
    assert actual.n_trials == expected.n_trials == 5
    assert actual.evaluation['selection'] == expected.evaluation['selection']
    assert any(row['q'] == 2 for row in resumed.searcher.acquisition_trace)
    for record in actual.history:
        x = resumed.trials[record.trial_id].config['x']
        vector = record.metadata['multi_objective']['objectives']
        assert vector == {'a': mean(x*x+s+o for s in (0, 2) for o in (0, 3)),
                          'b': mean(x+s for s in (0, 2) for _ in (0, 3))}
        assert len(record.metadata['evaluation']['records']) == 4
    assert len(resumed.searcher.history) == 5
    assert all(row.metadata['evaluation']['role'] == 'tuning' for row in resumed.searcher.history)
    for final in actual.evaluation['final']:
        x = resumed.trials[final['trial_id']].config['x']
        assert final['objectives']['a']['mean'] == x*x+111.
        assert final['objectives']['b']['mean'] == x+11.
        assert {row['seed'] for row in final['records']} == {10, 12}
