"""Independent exact references for shipped, plain caller-owned objectives."""
import ast
from contextlib import closing
from copy import deepcopy
from fractions import Fraction as Q
import inspect
from itertools import product
import json
from pathlib import Path

import pytest

from hponas import EvaluationContext
from hponas import quickstart as app
from hponas.store import Store


def configurations(name):
    keys = ('width', 'ridge') if name == 'hinge' else ('step_eighths', 'iterations')
    values = ((1, 2), (0, 1)) if name == 'hinge' else ((1, 2), (1, 2))
    return [dict(zip(keys, row)) for row in product(*values)]


def oracle(name, config, role):
    """Literal datasets, rational elimination and scalar update recurrence.

    This never invokes the example's fitting, prediction or data helpers.
    """
    if name == 'hinge':
        training = [(-2, 1), (-1, 1), (0, 1), (1, 3), (2, 4)]
        validation = [(Q(-1, 2), 1), (Q(1, 2), 2), (Q(3, 2), Q(7, 2))]
        final = [(Q(-3, 2), 1), (Q(1, 4), Q(3, 2)), (Q(7, 4), Q(15, 4))]
        scoring = validation if role == 'tuning' else final
        if role == 'final':
            training += validation
        width = config['width']
        def features(x):
            return [Q(1)] + [max(Q(x) - k, 0) for k in range(width)]
        matrix = []
        for i in range(width + 1):
            row = [sum(features(x)[i] * features(x)[j] for x, _ in training)
                   + (config['ridge'] if i == j and i > 0 else 0) for j in range(width + 1)]
            matrix.append(row + [sum(features(x)[i] * y for x, y in training)])
        # Rational Gauss-Jordan with row pivoting; independent of NumPy solve.
        for column in range(width + 1):
            pivot = next(k for k in range(column, width + 1) if matrix[k][column])
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            scale = matrix[column][column]
            matrix[column] = [x / scale for x in matrix[column]]
            for k in range(width + 1):
                if k != column:
                    multiplier = matrix[k][column]
                    matrix[k] = [a - multiplier * b for a, b in zip(matrix[k], matrix[column])]
        coefficients = [row[-1] for row in matrix]
        predictions = [sum(a * b for a, b in zip(coefficients, features(x))) for x, _ in scoring]
        loss = sum((predicted - y) ** 2 for predicted, (_, y) in zip(predictions, scoring)) / len(scoring)
        fitted = {'coefficients': [float(x) for x in coefficients]}
        updates = 1
    else:
        # Four training scenarios, four independent validation/final identities.
        training = [Q(1), Q(5), Q(1), Q(5)] * (2 if role == 'final' else 1)
        scoring = [Q(1), Q(5), Q(1), Q(5)]
        weight = Q(0)
        trace = [weight]
        # J'(w) = 4w-3, known independently from the exact scenario moments.
        for _ in range(config['iterations']):
            weight = min(Q(1), max(Q(0), weight - Q(config['step_eighths'], 8) * (4 * weight - 3)))
            trace.append(weight)
        predictions = [weight * value for value in scoring]
        loss = 2 * weight ** 2 - 3 * weight
        fitted = {'weights': [float(weight), float(1 - weight)], 'updates': [float(x) for x in trace]}
        updates = config['iterations']
    return {'loss': float(loss), 'predictions': [float(x) for x in predictions],
            'work': len(training) + len(scoring) + updates, 'model': fitted}


@pytest.mark.parametrize('name', ['hinge', 'allocation'])
def test_every_configuration_role_and_seed_matches_independent_math(tmp_path, name):
    model = app.MODELS[name](tmp_path)
    assert set(model.declaration.tuning_seeds).isdisjoint(model.declaration.final_seeds)
    for role in ('tuning', 'final'):
        fold, = getattr(model.declaration, role + '_folds')
        assert set(fold.train_ids).isdisjoint(fold.score_ids)
        seeds = getattr(model.declaration, role + '_seeds')
        for index, config in enumerate(configurations(name)):
            expected = oracle(name, config, role)
            for seed in seeds:
                result = model(config, seed, EvaluationContext(role, fold, model.declaration.identity),
                               f'{role}-{index}-{seed}')
                assert result['value'] == pytest.approx(expected['loss'], abs=1e-12)
                saved = app.load_model(result['artifacts']['model'])
                assert saved['config'] == config
                assert saved['role'] == role and saved['seed'] == seed
                assert saved['train_ids'] == list(fold.train_ids)
                assert saved['score_ids'] == list(fold.score_ids)
                assert saved['predictions'] == pytest.approx(expected['predictions'], abs=1e-12)
                for key, values in expected['model'].items():
                    assert saved['model'][key] == pytest.approx(values, abs=1e-12)
                assert saved['work'] == expected['work']
                assert result['metadata']['resource'] == {'work': expected['work'], 'unit': app.WORK_UNIT}
                scoring = [model.records[i] for i in fold.score_ids]
                points = [row[0] for row in scoring] if name == 'hinge' else scoring
                assert model.predict(saved['model'], points) == saved['predictions']
    optimum = min(oracle(name, c, 'tuning')['loss'] for c in configurations(name))
    assert optimum == (0 if name == 'hinge' else -9 / 8)


@pytest.mark.parametrize('name', ['hinge', 'allocation'])
def test_public_search_covers_domain_and_reports_raw_means_work_and_artifacts(tmp_path, name):
    with closing(Store(tmp_path / 'study.sqlite')) as store:
        study = app.make_study(name, tmp_path, store)
        result = study.run()
        actual = [study.trials[item.trial_id].config.values for item in result.history]
        assert len(actual) == 4
        assert {tuple(sorted(c.items())) for c in actual} == {
            tuple(sorted(c.items())) for c in configurations(name)}
        expected = [oracle(name, c, 'tuning')['loss'] for c in actual]
        assert [item.objective_value for item in study.searcher.history] == pytest.approx(expected, abs=1e-12)
        assert result.best_value == pytest.approx(min(expected), abs=1e-12)
        best = actual[expected.index(min(expected))]
        assert result.best_config.values == best
        assert result.evaluation['outcome'] == 'completed'
        assert result.evaluation['selection'] == [result.history[expected.index(min(expected))].trial_id]
        for summary, value in zip(result.evaluation['tuning'], expected):
            assert summary['objectives']['loss'] == {'mean': pytest.approx(value, abs=1e-12),
                                                    'sample_std': 0., 'n': 2}
        assert result.evaluation['final'][0]['objectives']['loss']['mean'] == pytest.approx(
            oracle(name, best, 'final')['loss'], abs=1e-12)
        report = study.report()
        assert report == store.read_report(study.study_name)
        assert report['resources']['tuning']['measured_work'] == 2 * sum(
            oracle(name, c, 'tuning')['work'] for c in actual)
        assert report['resources']['final']['measured_work'] == 2 * oracle(name, best, 'final')['work']
        assert report['resources']['tuning']['work_exact']
        assert report['resources']['final']['work_exact']
        assert len(report['artifacts']) == 10
        raw = store.load_study_snapshot(study.study_name)['evaluation']
        for role in ('tuning', 'final'):
            for tid, repetitions in raw[role].items():
                reference = oracle(name, study.trials[tid].config.values, role)
                assert len(repetitions) == 2
                assert {r['seed'] for r in repetitions} == set(getattr(study.objective_fn.declaration, role + '_seeds'))
                assert [r['result']['objective_value'] for r in repetitions] == pytest.approx(
                    [reference['loss']] * 2, abs=1e-12)
        assert study._snapshot()['admission']['architecture_coordinates'] == (['width'] if name == 'hinge' else [])


@pytest.mark.parametrize('name', ['hinge', 'allocation'])
def test_final_sentinel_cannot_change_selection_or_searcher_feedback(tmp_path, name):
    with closing(Store(tmp_path / 'study.sqlite')) as store:
        study = app.make_study(name, tmp_path, store)
        model = study.objective_fn
        def sentinel(config, seed, evaluation, trial_id):
            result = model(config, seed, evaluation, trial_id)
            if evaluation.role == 'final':
                result['value'] = -1e12
            return result
        study.objective_fn = sentinel
        result = study.run()
        assert result.evaluation['final'][0]['objectives']['loss']['mean'] == -1e12
        assert result.best_value == pytest.approx(model.reference['loss'], abs=1e-12)
        assert len(study.searcher.history) == 4
        assert all(item.metadata['evaluation']['role'] == 'tuning' for item in study.searcher.history)
        assert all(item.objective_value > -1e10 for item in study.searcher.history)


@pytest.mark.parametrize('name', ['hinge', 'allocation'])
@pytest.mark.parametrize('role', ['tuning', 'final'])
def test_interrupt_after_artifact_recovers_only_uncommitted_work_and_keeps_frozen_selection(tmp_path, name, role):
    with closing(Store(tmp_path / 'study.sqlite')) as store:
        original = app.make_study(name, tmp_path, store)
        objective = original.objective_fn
        calls = []
        def interrupted(config, seed, evaluation, trial_id):
            calls.append(trial_id)
            result = objective(config, seed, evaluation, trial_id)
            if (role == 'tuning' and len(calls) == 2) or (role == 'final' and evaluation.role == 'final'):
                raise KeyboardInterrupt('interruption after artifact publication, before acknowledgement')
            return result
        original.objective_fn = interrupted
        with pytest.raises(KeyboardInterrupt):
            original.run()
        saved = store.load_study_snapshot(original.study_name)
        committed = {row['result']['trial_id'] for part in ('tuning', 'final')
                     for rows in saved['evaluation'][part].values() for row in rows}
        selection = deepcopy(saved['evaluation']['selection'])
        artifact = tmp_path / 'models' / (calls[-1] + '.json')
        retained = artifact.read_bytes()
        restored = app.make_study(name, tmp_path, store)
        restored.load_checkpoint()
        resumed_calls = []
        objective = restored.objective_fn
        def record(config, seed, evaluation, trial_id):
            resumed_calls.append(trial_id)
            return objective(config, seed, evaluation, trial_id)
        restored.objective_fn = record
        result = restored.run()
        assert result.evaluation['outcome'] == 'completed'
        assert resumed_calls[0] == calls[-1]
        assert not committed.intersection(resumed_calls)
        assert artifact.read_bytes() == retained
        assert result.evaluation['uncertain_evaluations'] == [calls[-1]]
        assert result.resources[role]['lost_attempts'] == 1
        assert result.resources[role]['charged_work'] == result.resources[role]['measured_work'] + 16
        assert not result.resources[role]['work_exact']
        assert len(restored.searcher.history) == 4
        if role == 'final':
            assert result.evaluation['selection'] == selection


@pytest.mark.parametrize('name', ['hinge', 'allocation'])
def test_completed_cli_workflow_resume_is_unchanged_and_new_run_refuses_existing_output(tmp_path, name):
    first = app.run(name, tmp_path)
    before = {p.name: p.read_bytes() for p in (tmp_path / 'models').iterdir()}
    report_bytes = (tmp_path / 'report.json').read_bytes()
    second = app.run(name, tmp_path, resume=True)
    assert second == first
    assert (tmp_path / 'report.json').read_bytes() == report_bytes
    assert {p.name: p.read_bytes() for p in (tmp_path / 'models').iterdir()} == before
    assert abs(first['reference']['search_regret']) < 1e-12
    assert not first['limits']['empirical_bank_usefulness_established']
    assert not first['limits']['posterior_convergence_established']
    with pytest.raises(ValueError, match='explicit resume'):
        app.run(name, tmp_path)
    with pytest.raises(ValueError, match='No existing study'):
        app.run(name, tmp_path / 'absent', resume=True)
    (tmp_path / 'report.json').write_text('{}\n')
    with pytest.raises(ValueError, match='differs'):
        app.run(name, tmp_path, resume=True)
    assert (tmp_path / 'report.json').read_bytes() == b'{}\n'


def test_resume_after_report_publication_interruption_keeps_completed_work(tmp_path, monkeypatch):
    original_link = app.os.link
    def interrupted_report(source, destination):
        if Path(destination).name == 'report.json':
            raise KeyboardInterrupt('interrupted before report publication')
        return original_link(source, destination)
    monkeypatch.setattr(app.os, 'link', interrupted_report)
    with pytest.raises(KeyboardInterrupt):
        app.run('hinge', tmp_path)
    assert not (tmp_path / 'report.json').exists()
    before = {p.name: p.read_bytes() for p in (tmp_path / 'models').iterdir()}
    monkeypatch.setattr(app.os, 'link', original_link)
    result = app.run('hinge', tmp_path, resume=True)
    assert result['result']['evaluation']['outcome'] == 'completed'
    assert {p.name: p.read_bytes() for p in (tmp_path / 'models').iterdir()} == before
    assert json.loads((tmp_path / 'report.json').read_text()) == result['report']


def test_other_model_checkpoint_is_refused_atomically(tmp_path):
    app.run('hinge', tmp_path)
    with closing(Store(tmp_path / 'study.sqlite')) as store:
        other = app.make_study('allocation', tmp_path, store)
        before = deepcopy(other._snapshot())
        with pytest.raises(ValueError, match='differs'):
            other.load_checkpoint(tmp_path / 'caller_hinge_checkpoint.json')
        assert other._snapshot() == before


def test_model_publish_integrity_nonoverwrite_and_interrupted_publish(tmp_path, monkeypatch):
    payload = {'model': {'weights': [.75, .25]}, 'loss': -9 / 8}
    path = tmp_path / 'model.json'
    original_link = app.os.link
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt('interrupted before atomic publication')
    monkeypatch.setattr(app.os, 'link', interrupted)
    with pytest.raises(KeyboardInterrupt):
        app._save_model(path, payload)
    assert not path.exists() and not list(tmp_path.glob('.model-*'))
    monkeypatch.setattr(app.os, 'link', original_link)
    app._save_model(path, payload)
    retained = path.read_bytes()
    assert app.load_model(path) == payload
    app._save_model(path, payload)
    with pytest.raises(ValueError, match='differs'):
        app._save_model(path, {**payload, 'loss': 1.})
    assert path.read_bytes() == retained
    alias = tmp_path / 'alias.json'
    alias.symlink_to(path)
    with pytest.raises(ValueError, match='differs'):
        app._save_model(alias, payload)
    document = json.loads(retained)
    document['payload']['loss'] = -999
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='digest'):
        app.load_model(path)
    document['schema'] = 'unknown'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='schema'):
        app.load_model(path)


def test_objectives_are_independent_plain_callers_and_refuse_wrong_context(tmp_path):
    tree = ast.parse(inspect.getsource(app))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not node.module.startswith(('workloads', 'validation', 'examples', 'FinMarketing', 'MacroFinance'))
    for cls in app.MODELS.values():
        assert cls.__bases__ == (object,)
        model = cls(tmp_path)
        fold, = model.declaration.tuning_folds
        config = configurations('hinge' if cls is app.HingeRegressor else 'allocation')[0]
        with pytest.raises(ValueError, match='declaration differs'):
            model(config, 0, EvaluationContext('tuning', fold, 'other'), 'bad-identity')
        with pytest.raises(ValueError, match='role or fold'):
            model(config, 0, EvaluationContext('final', fold, model.declaration.identity), 'bad-role')
    assert not (tmp_path / 'models').exists()
