from fractions import Fraction
import math

import numpy as np
import pytest
from scipy.linalg import solve_discrete_are

from hponas_rl_lqr.reference import (LQRSpec, enumerate_policy, numerical_tolerance,
                                     oracle_report, paths, rational_reference, riccati)
from hponas_rl_lqr.environment import FiniteLQREnv


def test_rational_optimum_all_paths_and_feasibility():
    s = LQRSpec()
    report = oracle_report(s)
    assert report['path_count'] == 512
    assert report['max_oracle_action'] < s.action_limit
    assert report['numeric_rational_error'] < numerical_tolerance(s, report['optimal_cost'])
    assert report['oracle_identity_error'] < numerical_tolerance(s, report['optimal_cost'])
    assert report['zero_action_cost'] > report['optimal_cost']


def test_one_step_reference_by_independent_quadratic_minimization():
    s = LQRSpec(horizon=1)
    # Minimize x^2+.1*u^2+.99*E[(.8*x+u+w)^2] directly.
    u = -Fraction(99, 100)*Fraction(4, 5)/(Fraction(1, 10)+Fraction(99, 100))
    cost = 1 + Fraction(1, 10)*u*u + Fraction(99, 100)*((Fraction(4, 5)+u)**2+Fraction(1, 400))
    assert rational_reference(s)['optimal_cost'] == cost


def test_discounted_dare_agrees_with_finite_recursion_limit():
    s = LQRSpec(horizon=12)
    dare = solve_discrete_are([[math.sqrt(s.gamma)*s.a]], [[math.sqrt(s.gamma)*s.b]], [[s.q]], [[s.r]])[0, 0]
    assert abs(riccati(s)['P'][0]-dare) < numerical_tolerance(s, dare)


@pytest.mark.parametrize('gain', [0., .2, .6, -.4])
def test_policy_cost_gap_matches_independent_advantage_identity(gain):
    s = LQRSpec()
    result = enumerate_policy(lambda x, t: np.tanh(-gain*x), s)
    assert result['gap'] >= -result['tolerance']
    assert abs(result['gap']-result['advantage_gap']) <= result['tolerance']
    assert np.allclose(result['states'][:, 1:], s.a*result['states'][:, :-1]+result['actions']+result['noise'])


def test_complete_noise_law_and_no_anticipating_policy_input():
    s = LQRSpec(horizon=3)
    initial, noise = paths(s)
    assert len(initial) == 16
    assert len(set(map(tuple, np.column_stack([initial, noise])))) == 16
    assert np.allclose(noise.sum(axis=0), np.zeros(3), atol=numerical_tolerance(s))
    assert np.isclose(np.mean(noise[:, 0]*noise[:, 1]), 0.)


def test_terminal_cost_and_discount_match_environment():
    s = LQRSpec()
    env = FiniteLQREnv()
    obs, _ = env.reset(seed=81)
    x = float(obs[0])
    rewards, independently_accumulated = [], 0.
    for t in range(s.horizon):
        action = np.array([.1], dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        independently_accumulated += s.gamma**t*(s.q*x*x+s.r*float(action[0])**2)
        x = s.a*x+s.b*float(action[0])+info['noise']
        rewards.append(reward)
        assert terminated == (t == s.horizon-1)
        assert not truncated
        assert obs[1] == np.float32((s.horizon-t-1)/s.horizon)
    independently_accumulated += s.gamma**s.horizon*s.terminal_q*x*x
    discounted = -sum(s.gamma**t*r for t, r in enumerate(rewards))
    assert abs(discounted-independently_accumulated) < numerical_tolerance(s, discounted)
    with pytest.raises(ValueError, match='reset'):
        env.step(np.array([0.]))


def test_seed_and_gymnasium_contract():
    from gymnasium.utils.env_checker import check_env
    check_env(FiniteLQREnv(), skip_render_check=True)
    env = FiniteLQREnv()
    def trace(seed):
        first, _ = env.reset(seed=seed)
        return [first.tolist()]+[env.step(np.array([0.], dtype=np.float32))[0].tolist() for _ in range(8)]
    assert trace(91) == trace(91)
    assert trace(91) != trace(92)


@pytest.mark.parametrize('bad', [np.nan, np.inf, 1.01, -1.01])
def test_invalid_policy_and_environment_actions_fail(bad):
    with pytest.raises(ValueError):
        enumerate_policy(lambda x, t: np.full_like(x, bad))
    env = FiniteLQREnv()
    env.reset(seed=0)
    with pytest.raises(ValueError):
        env.step(np.array([bad]))


def test_wrong_terminal_reference_cannot_certify_policy():
    actual = oracle_report()
    wrong = oracle_report(LQRSpec(terminal_q=0))
    assert abs(actual['optimal_cost']-wrong['optimal_cost']) > numerical_tolerance(LQRSpec())
