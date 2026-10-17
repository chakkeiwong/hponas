"""Independent budget/algebra checks and censor-mechanism counterexamples."""
from fractions import Fraction
import itertools
import math

import numpy as np
import pytest
import torch

from hponas.cost_policy import CostRecord, cheap_first, cooling, cost_aware_acquisition, observation_record
from hponas.types import Result


def test_cooling_matches_primary_formula_and_time_unit_invariance():
    for total, initial in [(8, 1), (100, 0), (100, 20)]:
        values = []
        for spent in range(0, total+10):
            expected = min(Fraction(1), max(Fraction(0), Fraction(total-spent, total-initial)))
            actual = cooling(spent, total, initial)
            assert actual == float(expected)
            assert cooling(60*spent, 60*total, 60*initial) == actual
            values.append(actual)
        assert values == sorted(values, reverse=True)
        assert cooling(initial, total, initial) == 1 and cooling(total, total, initial) == 0
    for args in [(0, 0, 0), (-1, 8, 1), (1, 8, 8), (math.nan, 8, 1), (True, 8, 1)]:
        with pytest.raises(ValueError): cooling(*args)


def test_cheap_first_elimination_matches_exhaustive_small_reference():
    def reference(costs, distances):
        values = list(range(len(costs))); trace = []
        use_cost = True
        while len(values) > 1:
            # Sort by primary value, stable original index for ties.
            ordered = sorted(values, key=lambda i: ((-costs[i] if use_cost else distances[i]), i))
            victim = ordered[0]
            trace.append({'index': victim, 'reason': 'most_expensive' if use_cost else 'closest_to_design'})
            values = [i for i in values if i != victim]
            use_cost = not use_cost
        return values[0], trace
    for costs in itertools.product([0., 1., 2.], repeat=4):
        for distances in [[1., 2., 3., 4.], [3., 1., 4., 2.], [math.inf]*4]:
            assert cheap_first(costs, distances) == reference(costs, distances)
    assert cheap_first([0.], [math.inf]) == (0, [])
    with pytest.raises(ValueError): cheap_first([1, 2], [math.inf, 1])


def test_expected_cost_acquisition_domains_gradients_and_zero_ei():
    x = torch.tensor([.2, .5, .9], dtype=torch.double, requires_grad=True)
    ei = torch.exp(-x*x)
    # This is log E[T], including the lognormal variance correction.
    log_cost = x+(.3+x*x)/2
    for alpha in [0., .5, 1.]:
        actual = cost_aware_acquisition(ei, log_cost, alpha, log_domain=False)
        logs = cost_aware_acquisition(ei.log(), log_cost, alpha, log_domain=True)
        torch.testing.assert_close(actual, logs.exp())
        gradient, = torch.autograd.grad(actual.sum(), x, retain_graph=True)
        torch.testing.assert_close(gradient, actual*(-2*x-alpha*(1+x)))
        seconds = cost_aware_acquisition(ei, log_cost+math.log(60), alpha, log_domain=False)
        torch.testing.assert_close(seconds, actual/60**alpha)
    zero = cost_aware_acquisition(torch.tensor([-math.inf]), torch.tensor([1.]), 1., log_domain=True)
    assert torch.isneginf(zero).all()
    with pytest.raises(ValueError): cost_aware_acquisition(-ei, log_cost, 1., log_domain=False)
    # Exp(log-mean) is a median; uncertainty changes the expected-cost ranking.
    means = np.array([0., .2]); variances = np.array([1., .01])
    assert np.argmin(means) != np.argmin(means+variances/2)


def test_censoring_preserves_all_work_and_refuses_unsupported_mechanisms():
    def result(status, **execution):
        return Result('trial', 1. if status == 'completed' else math.nan, 8, 1,
                      {'execution': {'elapsed_seconds': 3., **execution}}, status)
    completed = observation_record(result('completed'))
    assert completed.kind == 'complete' and completed.spent == completed.duration == 3.
    assert observation_record(result('completed'), unit='declared_work_units').spent == 8
    for status in ['timeout', 'failed', 'nan', 'inf', 'pruned', 'cancelled']:
        row = observation_record(result(status))
        assert row.kind == 'unmodeled' and row.spent == 3 and row.duration is None
    censored = observation_record(result('timeout', censor_cause='external_deadline'),
                                  timeout_assumption='deadline_independent_given_config')
    assert censored.kind == 'right_censored' and censored.duration == 3
    assert observation_record(result('timeout', censor_cause='external_deadline')).kind == 'unmodeled'
    assert observation_record(result('completed', accounting='lower_bound_after_interruption')).kind == 'unmodeled'
    assert observation_record(result('timeout', accounting='lower_bound_after_interruption',
                                     censor_cause='external_deadline'),
                              timeout_assumption='deadline_independent_given_config').kind == 'unmodeled'
    assert CostRecord(**censored.to_dict()) == censored
    for cause in ['quality_stop', 'diverged', 'unknown']:
        with pytest.raises(ValueError): CostRecord('t', 3., 3., 'right_censored', cause, 'wall_seconds',
                                                   'measured', 'deadline_independent_given_config')
    with pytest.raises(ValueError): observation_record(Result('missing', 1., 8))
