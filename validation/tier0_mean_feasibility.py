"""Exact limitations and sufficient bounds; no simulation or workload calls.

These are design screens, not registered sizing or acceptance inference.
Counts always mean independent units: task names, adaptive trials and repeated
observations must not be inserted as additional replicates.
"""

from __future__ import annotations

import math


def _finite_positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _probability(value, name):
    _finite_positive(value, name)
    if value >= 1:
        raise ValueError(f"{name} must be below one")
    return value


def _count(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def rare_loss_null(gain, loss_probability, independent_units, *, rejection_on_all_gains=1.0):
    """Mean-zero two-point null whose observed sample can look uniformly good.

    X = gain with probability 1-epsilon and
    X = -gain*(1-epsilon)/epsilon otherwise. For any test rejecting an
    all-gain sample with probability r, its null error is at least
    r*(1-epsilon)**n. Taking epsilon -> 0 proves the unrestricted-mean barrier.
    """
    gain = _finite_positive(gain, "gain")
    epsilon = _probability(loss_probability, "loss probability")
    n = _count(independent_units, "independent units")
    r = _finite_positive(rejection_on_all_gains, "rejection probability")
    if r > 1:
        raise ValueError("Rejection probability exceeds one")
    loss = -gain * (1 - epsilon) / epsilon
    if not math.isfinite(loss):
        raise ValueError("Rare loss overflow")
    all_gains = math.exp(n * math.log1p(-epsilon))
    return {"gain": gain, "loss": loss, "loss_probability": epsilon, "null_mean": 0.0,
            "independent_units": n, "probability_of_all_gains": all_gains,
            "type1_error_lower_bound": r * all_gains,
            "certifies_acceptance": False}


def bounded_mean_screen(independent_units, *, alpha=.025, target_power=.8, components=1,
                        difference_low=-1.0, difference_high=1.0):
    """Hoeffding/IUT power sufficiency and a distinct necessary lower bound.

    For independent (not necessarily identically distributed) X in [a,b],
    testing the average expectation at zero using mean(X) > c controls alpha,
    c=(b-a)*sqrt(log(1/alpha)/(2*n)). Union bounding component failures gives
    joint power >= target if every mean exceeds the reported sufficient gap.
    This bound is conservative, not an assertion that smaller gains lack power.

    Separately compare a point alternative X=delta to a two-point mean-zero
    null on {-L,delta}, L=-a. Every level-alpha test with power >= target needs
    delta >= L*((target/alpha)**(1/n)-1). This is necessary for that alternative,
    not a tight characterization of the whole model class.
    """
    n = _count(independent_units, "independent units")
    k = _count(components, "components")
    alpha = _probability(alpha, "alpha")
    target = _probability(target_power, "target power")
    if target <= alpha:
        raise ValueError("Target power must exceed alpha")
    for value in (difference_low, difference_high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Finite difference support required")
    if not difference_low < 0 < difference_high:
        raise ValueError("Difference support must straddle zero")
    width = difference_high - difference_low
    if not math.isfinite(width):
        raise ValueError("Difference support overflow")
    threshold = width * math.sqrt(math.log(1 / alpha) / (2 * n))
    sufficient = threshold + width * math.sqrt(math.log(k / (1 - target)) / (2 * n))
    necessary = -difference_low * math.expm1(math.log(target / alpha) / n)
    return {
        "independent_units": n, "components": k, "component_alpha": alpha, "joint_target_power": target,
        "difference_support": [difference_low, difference_high],
        "hoeffding_rejection_threshold": threshold,
        "sufficient_gap_for_joint_power": sufficient,
        "sufficient_bound_within_support": sufficient < difference_high,
        "necessary_gap_against_point_alternative": necessary,
        "certifies_acceptance": False, "usable_as_registered_sizing_receipt": False,
        "assumptions": "Independent units; genuine almost-sure bounds; fixed means, count and rule; no outcome-dependent exclusions.",
    }


def missingness_counterexample(*, independent_units=20, missing_probability=.09):
    """A <=10% exclusion rule alone does not make complete-case means valid.

    The missing observations are exactly the negative member of a mean-zero
    two-point distribution. Whenever a campaign survives the loss cap, all
    retained values are +1. The event probability is evaluated exactly.
    """
    n = _count(independent_units, "independent units")
    epsilon = _probability(missing_probability, "missing probability")
    maximum_losses = n // 10
    survives = math.fsum(math.comb(n, j) * epsilon**j * (1 - epsilon)**(n-j)
                         for j in range(maximum_losses + 1))
    return {"independent_units": n, "null_mean_before_missingness": 0.0,
            "observed_value": 1.0, "missing_value": -(1-epsilon)/epsilon,
            "missing_probability": epsilon, "permitted_losses": maximum_losses,
            "probability_campaign_survives_with_all_retained_values_positive": survives,
            "certifies_acceptance": False}
