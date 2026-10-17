from copy import deepcopy
from fractions import Fraction
from itertools import product
import json
import math

import numpy as np
import pytest

from hponas.population_bandit import TimeVaryingExp3, dependent_round, inclusion_probabilities
from hponas.population import _digest


class Draws:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


def test_truncation_exact_threshold_and_nonclipped_probabilities():
    p, w, clipped = inclusion_probabilities([10, 1, 1], 2, 0.25)
    # eta=5/9, cap=eta*(cap+2) => cap=5/2. The implementation
    # rescales weights by max=10 without changing their normalized law.
    assert w.tolist() == pytest.approx([0.25, 0.1, 0.1])
    assert p.tolist() == pytest.approx([1, 0.5, 0.5])
    assert clipped == [0]
    p2, _, _ = inclusion_probabilities([1, 1, 1], 2, 0.25)
    assert p2.tolist() == pytest.approx([2/3]*3)


def test_dependent_rounding_exact_marginals_without_monte_carlo():
    # Two fair pairs have four equiprobable leaves; every selected batch has
    # cardinality two and all arm marginals are exactly one half.
    outcomes = [dependent_round([0.5]*4, Draws(draws)) for draws in product([0.25, 0.75], repeat=2)]
    assert sorted(outcomes) == [[0, 2], [0, 3], [1, 2], [1, 3]]
    assert [sum(i in outcome for outcome in outcomes) for i in range(4)] == [2]*4
    # Fractional pair with certain and impossible arms: exact probability 1/3
    # chooses arm 1, 2/3 chooses arm 2, preserving the original marginals.
    assert dependent_round([1, 1/3, 2/3, 0], Draws([0])) == [0, 1]
    assert dependent_round([1, 1/3, 2/3, 0], Draws([0.9])) == [0, 2]
    expected = [Fraction(1), Fraction(1, 3), Fraction(2, 3), Fraction(0)]
    assert sum(expected) == 2


def test_algorithm_five_update_shares_to_unselected_arms():
    bandit = TimeVaryingExp3(3, 1, 10, seed=4, gamma=0.3, sharing=0.1)
    choice = bandit.ask()
    arm = choice['selected'][0]
    bandit.tell({arm: 1})
    unnormalized = np.array([1+math.e/10]*3)
    unnormalized[arm] = math.exp(0.3)+math.e/10
    np.testing.assert_allclose(bandit.weights, unnormalized/unnormalized.sum(), rtol=0, atol=1e-15)


def test_capped_arm_reward_is_not_exponentiated():
    bandit = TimeVaryingExp3(3, 2, 10, seed=3, gamma=0.25, sharing=0.1)
    bandit.weights = np.array([10, 1, 1])/12
    choice = bandit.ask()
    assert 0 in choice['selected'] and choice['clipped'] == [0]
    w = np.array(choice['clipped_weights'])
    expected = w+math.e*0.1*w.sum()/3
    bandit.tell({arm: int(arm == 0) for arm in choice['selected']})
    np.testing.assert_allclose(bandit.weights, expected/expected.sum(), rtol=0, atol=1e-15)


@pytest.mark.parametrize('batch', [1, 2, 3])
def test_bandit_resume_at_every_ask_tell_boundary(batch):
    bandit = TimeVaryingExp3(3, batch, 4, seed=7)
    for _ in range(4):
        before = bandit.state_dict()
        copy = TimeVaryingExp3(3, batch, 4, seed=7)
        copy.load_state_dict(json.loads(json.dumps(before)))
        assert copy.ask() == bandit.ask()
        pending = bandit.state_dict()
        copy.load_state_dict(json.loads(json.dumps(pending)))
        assert copy.ask() == bandit.ask()
        rewards = {arm: (arm+1)/4 for arm in bandit.ask()['selected']}
        copy.tell(rewards)
        bandit.tell(rewards)
        assert copy.state_dict() == bandit.state_dict()
    with pytest.raises(ValueError, match='exhausted'):
        bandit.ask()
    wrong = deepcopy(bandit.state_dict())
    wrong['payload']['weights'] = [1/3]*3
    wrong['sha256'] = _digest(wrong['payload'])
    if batch != 3:
        with pytest.raises(ValueError, match='replay'):
            copy.load_state_dict(wrong)


@pytest.mark.parametrize('weights', [[0, 1], [-1, 1], [float('inf'), 1]])
def test_invalid_weights_refused(weights):
    with pytest.raises(ValueError):
        inclusion_probabilities(weights, 1, 0.1)


def test_bad_feedback_does_not_mutate_pending_state():
    bandit = TimeVaryingExp3(3, 2, 5)
    choice = bandit.ask()
    before = bandit.state_dict()
    for rewards in [{}, {arm: float('nan') for arm in choice['selected']}, {arm: 2 for arm in choice['selected']}]:
        with pytest.raises(ValueError):
            bandit.tell(rewards)
        assert bandit.state_dict() == before


def test_distribution_covers_extremes_and_dynamic_range():
    for weights, batch, gamma in product([[1, 1, 1, 1], [1e-12, 1e-8, 1, 10], [1, 2, 3, 4]], range(1, 5), [0, 0.1, 1]):
        p, _, _ = inclusion_probabilities(weights, batch, gamma)
        assert np.all(p >= 0) and np.all(p <= 1)
        assert p.sum() == pytest.approx(batch, abs=1e-12)
