"""Analytical constraints checked against hand-derived discrete examples."""

import math

import pytest

from validation.tier0_mean_feasibility import (
    bounded_mean_screen, missingness_counterexample, rare_loss_null,
)


def test_unrestricted_mean_null_can_look_uniformly_better():
    result = rare_loss_null(1, .01, 20, rejection_on_all_gains=.8)
    assert .99 * result["gain"] + .01 * result["loss"] == pytest.approx(0)
    assert result["probability_of_all_gains"] == pytest.approx(.99**20)
    assert result["type1_error_lower_bound"] > .65
    nearer = rare_loss_null(1, 1e-8, 20, rejection_on_all_gains=.8)
    assert nearer["type1_error_lower_bound"] > .799999


def test_necessary_bound_meets_two_point_null_likelihood_exactly():
    result = bounded_mean_screen(20)
    delta = result["necessary_gap_against_point_alternative"]
    p_gain = 1 / (1 + delta)
    assert p_gain * delta - (1 - p_gain) == pytest.approx(0)
    assert .8 * p_gain**20 == pytest.approx(.025)
    assert .8 * (1 / (1 + delta / 2))**20 > .025


def test_hoeffding_threshold_bounds_binomial_null_by_exact_enumeration():
    # X in {-1,+1} with p=.5 is on the mean-zero boundary.
    for n in (5, 20, 60):
        threshold = bounded_mean_screen(n)["hoeffding_rejection_threshold"]
        exact = sum(math.comb(n, k) / 2**n for k in range(n + 1) if 2*k/n - 1 > threshold)
        assert exact <= .025


def test_sufficient_joint_power_bound_is_distinct_from_necessary_bound():
    single, joint = bounded_mean_screen(20), bounded_mean_screen(20, components=8)
    assert joint["sufficient_gap_for_joint_power"] > single["sufficient_gap_for_joint_power"]
    assert joint["sufficient_gap_for_joint_power"] > 1
    assert not joint["sufficient_bound_within_support"]
    assert joint["necessary_gap_against_point_alternative"] < 1
    assert not joint["usable_as_registered_sizing_receipt"]
    assert not joint["certifies_acceptance"]


def test_units_and_scale_have_the_mathematical_effect_claimed():
    base = bounded_mean_screen(20)
    four_times = bounded_mean_screen(80)
    scaled = bounded_mean_screen(20, difference_low=-10, difference_high=10)
    for key in ("hoeffding_rejection_threshold", "sufficient_gap_for_joint_power"):
        assert four_times[key] == pytest.approx(base[key] / 2)
        assert scaled[key] == pytest.approx(10 * base[key])


def test_missingness_cap_does_not_control_selection_bias():
    result = missingness_counterexample()
    assert .91 + .09 * result["missing_value"] == pytest.approx(0)
    expected = .91**20 + 20*.09*.91**19 + 190*.09**2*.91**18
    assert result["probability_campaign_survives_with_all_retained_values_positive"] == pytest.approx(expected)
    assert expected > .7
    assert result["permitted_losses"] == 2


@pytest.mark.parametrize("function,args", [
    (rare_loss_null, (1, 0, 20)), (rare_loss_null, (1, 1, 20)),
    (rare_loss_null, (math.nan, .1, 20)), (rare_loss_null, (1, .1, True)),
    (bounded_mean_screen, (0,)), (bounded_mean_screen, (2.5,)),
    (missingness_counterexample, ()),
])
def test_invalid_inputs_cannot_produce_feasibility_receipts(function, args):
    kwargs = {"missing_probability": math.inf} if function is missingness_counterexample else {}
    with pytest.raises(ValueError):
        function(*args, **kwargs)
