"""Independent power, Gaussian-conditioning, acquisition and recovery checks."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest

from hponas import RobustGPSearcher, SearchSpace, Knob, Result
from hponas.gp_robustness import fit_output_power, noisy_ensemble, nondominated_indices


@pytest.mark.parametrize('values', [[2., 2., 2.], [-3., -1., 0., 1., 8.], [0., .01, .1, 1e6]])
def test_output_power_matches_piecewise_formula_and_preserves_order(values):
    transformed, spec = fit_output_power(values)
    expected = []
    for raw in values:
        x, p = (raw-spec['center'])/spec['scale'], spec['power']
        if x >= 0:
            value = math.log1p(x) if abs(p) < 1e-14 else math.expm1(p*math.log1p(x))/p
        else:
            value = -math.log1p(-x) if abs(p-2) < 1e-14 else -math.expm1((2-p)*math.log1p(-x))/(2-p)
        expected.append(value)
    np.testing.assert_allclose(transformed, expected, rtol=1e-12, atol=1e-12)
    assert np.array_equal(np.argsort(values), np.argsort(transformed))


def test_noisy_improvement_integrates_uncertain_incumbent_and_preserves_tradeoffs():
    # In one posterior draw the incumbent beats every candidate; in the other
    # candidate 1 improves by 4. Fixing the incumbent to its mean gives another EI.
    draws = [[0., -1., 4.], [10., 3., 4.]]
    scores = noisy_ensemble(draws, [5., 1., 4.], np.diag([25., 9., 0.]), 1)
    np.testing.assert_allclose(scores, [[0., 0., 7.], [2., .5, 4.]])
    assert nondominated_indices(scores).tolist() == [0, 1]
    assert nondominated_indices([[0, 0, 1], [1, 1, 2], [1, 1, 2]]).tolist() == [1, 2]


def space():
    return SearchSpace([Knob('x', 'continuous', (0., 1.))])


def populated():
    obj = RobustGPSearcher(space(), seed=7, initial_random_samples=3,
                          candidate_count=8, posterior_samples=16, fit_iterations=10)
    for index, value in enumerate([0., .2, .6, 1.]):
        from hponas import Config
        obj.trials[str(index)] = Config({'x': value})
        obj.observe(Result(str(index), (value-.3)**2, 1.))
    return obj


def dense_reference(row):
    train = np.array(row['train_x'])
    query = np.concatenate((train, row['candidates']))
    eps = row['warp_eps']
    def warp(x):
        z = eps+(1-2*eps)*x
        return 1-(1-z**np.array(row['warp_a']))**np.array(row['warp_b'])
    a, b = warp(train), warp(query)
    def kernel(left, right):
        distance = np.sqrt(np.sum(((left[:, None]-right[None, :])/row['lengthscale'])**2, axis=-1))
        return row['outputscale']*(1+np.sqrt(5)*distance+5*distance**2/3)*np.exp(-np.sqrt(5)*distance)
    c = kernel(a, a)+row['noise']*np.eye(len(a))
    cross = kernel(b, a)
    mean = row['constant_mean'] + cross@np.linalg.solve(c, np.array(row['normalized_targets'])-row['constant_mean'])
    cov = kernel(b, b)-cross@np.linalg.solve(c, cross.T)
    return row['outcome_mean']+row['outcome_std']*mean, row['outcome_std']**2*cov


@pytest.fixture(scope='module')
def fitted():
    obj = populated()
    config = obj.suggest()
    return obj, config, obj.last_diagnostics


def test_learned_warp_gp_posterior_matches_dense_matern_conditioning(fitted):
    _, _, row = fitted
    mean, covariance = dense_reference(row)
    np.testing.assert_allclose(row['mean'], mean, rtol=2e-8, atol=2e-9)
    np.testing.assert_allclose(row['covariance'], covariance, rtol=2e-8, atol=2e-9)
    transformed, spec = fit_output_power(row['raw_y'])
    assert row['power'] == spec
    np.testing.assert_allclose(row['warped_y'], -transformed)
    assert any(abs(a-1) > 1e-6 for a in row['warp_a']+row['warp_b'])


def test_joint_draws_scores_and_selection_are_reconstructable(fitted):
    obj, config, row = fitted
    z = np.array(row['normal_draws']).reshape(len(row['draws']), -1)
    root = np.array(row['sampling_root'])
    np.testing.assert_allclose(root@root.T, row['covariance'], atol=2e-9, rtol=2e-8)
    np.testing.assert_allclose(z@root.T+row['mean'], row['draws'], atol=2e-9, rtol=2e-8)
    expected = []
    n = len(row['train_x'])
    for index in range(n, len(row['mean'])):
        diffs = [draw[index]-max(draw[:n]) for draw in row['draws']]
        expected.append([sum(max(0., d) for d in diffs)/len(diffs),
            sum(d>0 for d in diffs)/len(diffs), row['mean'][index]+2*math.sqrt(row['covariance'][index][index])])
    np.testing.assert_allclose(row['scores'], expected, atol=1e-12)
    front = [i for i, x in enumerate(expected) if not any(
        all(y[k]>=x[k] for k in range(3)) and any(y[k]>x[k] for k in range(3)) for y in expected)]
    assert row['front'] == front and row['selected'] in front
    assert config.values == {'x': row['candidates'][row['selected']][0]}


def test_json_recovery_preserves_fitted_suggestion_and_pending_mapping():
    first = populated()
    restored = populated()
    restored.load_state_dict(json.loads(json.dumps(first.state_dict())))
    a, b = first.suggest(), restored.suggest()
    assert a.to_dict() == b.to_dict()
    assert first.last_diagnostics == restored.last_diagnostics
    restored.trials['pending'] = b
    state = json.loads(json.dumps(restored.state_dict()))
    again = populated()
    again.load_state_dict(state)
    assert again.state_dict() == state


def test_failed_fit_cannot_advance_suggestion_or_rng(monkeypatch):
    import hponas.searchers.robust_gp_searcher as module
    obj = populated()
    before = obj.state_dict()
    def broken(*a, **k): raise RuntimeError('forced fit failure')
    monkeypatch.setattr(module, 'fit_gpytorch_mll_scipy', broken)
    with pytest.raises(RuntimeError, match='forced'): obj.suggest()
    assert obj.state_dict() == before


def test_corrupt_or_wrong_contract_checkpoint_is_refused_atomically():
    obj = populated()
    before = obj.state_dict()
    broken = deepcopy(before)
    broken['payload']['base']['history'][0]['objective_value'] += 1
    with pytest.raises(ValueError): obj.load_state_dict(broken)
    other = RobustGPSearcher(space(), seed=8)
    with pytest.raises(ValueError): other.load_state_dict(before)
    assert obj.state_dict() == before


@pytest.mark.parametrize('kwargs', [{'seed': True}, {'candidate_count': 100000},
    {'posterior_samples': 1}, {'fit_iterations': 0}, {'maximize': 'yes'}])
def test_unsupported_envelope_refused(kwargs):
    with pytest.raises(ValueError): RobustGPSearcher(space(), **kwargs)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 1e200])
def test_invalid_observations_cannot_enter_fit_or_change_state(value):
    obj = populated()
    before = obj.state_dict()
    with pytest.raises(ValueError): obj.observe(Result('0', value, 1.))
    assert obj.state_dict() == before


def test_study_cannot_change_direction_implicitly():
    from hponas import Study, LocalExecutor
    with pytest.raises(ValueError, match='direction'):
        Study(RobustGPSearcher(space()), LocalExecutor(), lambda x: 1., maximize=True)


def test_study_refuses_unsupported_batch_and_scheduler_before_work():
    from hponas import Study, LocalExecutor
    from hponas.schedulers import ASHAScheduler, ASHAConfig
    for controls in [{'max_concurrent': 2}, {'scheduler': ASHAScheduler(ASHAConfig())}]:
        searcher = RobustGPSearcher(space())
        before = searcher.state_dict()
        with pytest.raises(ValueError, match='serial'):
            Study(searcher, LocalExecutor(), lambda x: 1., maximize=False, **controls)
        assert searcher.state_dict() == before


def test_checkpoint_cannot_bypass_serial_study_contract(tmp_path):
    from hponas import Study, LocalExecutor
    study = Study(RobustGPSearcher(space()), LocalExecutor(), lambda x: 1., maximize=False)
    before = deepcopy(study._snapshot())
    changed = deepcopy(before)
    changed['max_concurrent'] = 2
    path = tmp_path/'unsupported.json'
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='serial'):
        study.load_checkpoint(path)
    assert study._snapshot() == before


@pytest.mark.parametrize('constant', [False, True])
def test_duplicate_noisy_and_constant_reports_have_finite_conditioned_predictions(constant):
    from hponas import Config
    obj = populated()
    obj.trials['1'] = Config({'x': 0.})
    for index, result in enumerate(obj.history):
        result.objective_value = 2. if constant else [-1., 1., 0., 3.][index]
    obj.suggest()
    row = obj.last_diagnostics
    mean, covariance = dense_reference(row)
    np.testing.assert_allclose(row['mean'], mean, atol=2e-9, rtol=2e-8)
    np.testing.assert_allclose(row['covariance'], covariance, atol=2e-9, rtol=2e-8)
    assert np.isfinite(row['draws']).all() and row['noise'] > 0
