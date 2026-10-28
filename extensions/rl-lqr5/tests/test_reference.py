import numpy as np
import pytest

from hponas_rl_lqr5.reference import (LQR5Spec, riccati, condensed_reference,
                                     enumerate_policy, oracle_report, paths)
from hponas_rl_lqr5.environment import FiniteLQR5Env


def test_matrix_reference_matches_independent_condensed_quadratic():
    s = LQR5Spec(); ref = riccati(s); other = condensed_reference(s)
    np.testing.assert_allclose(ref['P'], other['P'], atol=1e-12, rtol=1e-12)
    np.testing.assert_allclose(ref['K'], other['K'], atol=1e-12, rtol=1e-12)
    assert abs(ref['optimal_cost']-other['optimal_cost']) < 1e-12
    # At the final step independently complete the square in one action.
    expected = s.gamma*(s.B.T@s.A)/(.1+s.gamma)
    np.testing.assert_allclose(ref['K'][-1], expected, atol=1e-14, rtol=0)
    report = oracle_report(s)
    assert report['controllability_rank'] == 5
    assert report['max_oracle_action'] <= s.action_limit
    assert report['optimal_cost'] < report['zero_action_cost']
    assert report['path_count'] == 8192


def test_complete_law_has_correct_initial_covariance_and_noise_independence():
    s = LQR5Spec(); x, w = paths(s)
    assert x.shape == (8192, 5) and w.shape == (8192, 8, 5)
    np.testing.assert_allclose(x.T@x/len(x), .25*np.eye(5), atol=1e-14)
    np.testing.assert_allclose(w[:, 0].T@w[:, 0]/len(x), np.outer(s.noise_vector, s.noise_vector), atol=1e-14)
    np.testing.assert_allclose(x.T@w[:, 0]/len(x), 0, atol=1e-14)
    np.testing.assert_allclose(w[:, 0].T@w[:, 1]/len(x), 0, atol=1e-14)


@pytest.mark.parametrize('gain', [0., .25, 1., 1.25])
def test_complete_policy_gap_identity(gain):
    ref = riccati()
    result = enumerate_policy(lambda x, t: -gain*x@ref['K'][t].T)
    assert result['identity_error'] <= result['tolerance']
    assert result['gap'] >= -result['tolerance']
    if gain == 1:
        assert abs(result['gap']) <= result['tolerance']
    else:
        assert result['gap'] > 0


def test_environment_observation_dynamics_terminal_cost_and_seed():
    env = FiniteLQR5Env(); s = env.specification
    first, _ = env.reset(seed=47)
    second, _ = env.reset(seed=47)
    assert np.array_equal(first, second) and first.shape == (6,)
    total = direct = 0.
    for t in range(8):
        old = env._state.copy(); action = np.array([.2], dtype=np.float32)
        obs, reward, done, truncated, info = env.step(action)
        np.testing.assert_allclose(env._state, s.A@old+s.B[:, 0]*float(action[0])+info['noise'])
        assert env.observation_space.contains(obs)
        assert obs[-1] == (7-t)/8 and done == (t == 7) and not truncated
        total -= s.gamma**t*reward
        direct += s.gamma**t*(old@old+.1*float(action[0])**2)
    direct += s.gamma**8*(env._state@env._state)
    assert abs(total-direct) < 1e-12
    with pytest.raises(ValueError, match='Episode ended'):
        env.step([0.])


@pytest.mark.parametrize('bad', [np.nan, 1.001])
def test_infeasible_policy_and_environment_action_refused(bad):
    with pytest.raises(ValueError, match='feasible'):
        enumerate_policy(lambda x, t: np.full((len(x), 1), bad))
    env = FiniteLQR5Env(); env.reset(seed=3)
    with pytest.raises(ValueError, match='feasible'):
        env.step([bad])


def test_oracle_feasibility_is_checked_not_assumed():
    with pytest.raises(ValueError, match='feasible'):
        oracle_report(LQR5Spec(action_limit=.01))
