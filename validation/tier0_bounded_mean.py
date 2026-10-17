"""Finite-sample batch mean inference for genuinely bounded independent units.

The adopted rank protocol uses this mathematics with genuine [-1,1] utilities.
These previews alone never certify a campaign or its sampling assumptions.
Empirical normalization anchors do not supply support for unrestricted raw returns.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from validation.stats import holm_bonferroni
from validation.tier0_analysis import components

@lru_cache(maxsize=32)
def _uniform_quadrature(count):
    # The integrand is a degree-n polynomial. k-point Gauss-Legendre integrates
    # through degree 2*k-1, so this evaluates the fixed uniform mixture without
    # Monte Carlo or an outcome-selected betting fraction. Positive normalized
    # numerical weights also define a valid discrete mixture in their own right.
    nodes, weights = np.polynomial.legendre.leggauss((count + 2) // 2)
    return (nodes + 1) / 2, weights / weights.sum()


def bounded_mean_evidence(differences, *, fractions=None, null_mean=0.0):
    """Test average E[X_i] <= 0 for independent X_i in [-1,1], at fixed n.

    For any predeclared lambda in [0,1], E = product(1+lambda*X_i)
    is nonnegative. Independence gives E[E] = product(1+lambda*mu_i).
    AM-GM bounds this by (1+lambda*mean(mu))**n <= 1 under the null,
    even if task effects differ. A fixed mixture also has expectation <= 1.
    Thus min(1, 1/E) is a valid p-value by Markov's inequality.

    The mixture and count must be fixed independently of confirmation
    outcomes. This batch proof does NOT authorize optional stopping when only
    the overall average mean, rather than every conditional mean, is <= 0.
    Balanced tasks with independent paired studies give the equal-task mean.
    Do not flatten studies sharing random streams or outcome-dependent losses.
    For a nonzero null m, use factors 1+lambda*(X_i-m)/(1+m), m > -1.
    The same proof applies and the evidence decreases monotonically in m.
    Default: uniform mixture over [0,1], integrated by polynomial quadrature.
    An explicitly supplied fixed fraction list uses equal mixture weights.
    """
    raw = np.asarray(differences)
    if raw.dtype.kind not in "iuf" or raw.ndim != 1 or not raw.size:
        raise ValueError("Require a nonempty numeric vector of independent units")
    data = raw.astype(float)
    if not np.isfinite(data).all() or (np.abs(data) > 1).any():
        raise ValueError("Genuine difference support [-1,1] required; no clipping")
    if (isinstance(null_mean, bool) or not isinstance(null_mean, (int, float))
            or not math.isfinite(null_mean) or not -1 < null_mean <= 1):
        raise ValueError("Null mean must be in (-1,1]")
    if fractions is None:
        bets, weights = _uniform_quadrature(len(data))
    else:
        bets = np.asarray(fractions)
        weights = np.full(bets.size, 1 / bets.size) if bets.size else np.array([])
    if (bets.dtype.kind not in "iuf" or bets.ndim != 1 or not bets.size
            or not np.isfinite(bets).all() or (bets < 0).any() or (bets > 1).any()
            or len(set(bets.tolist())) != len(bets)):
        raise ValueError("Prespecified distinct betting fractions in [0,1] required")
    # Log arithmetic retains underflow/overflow cases without discarding an
    # adverse observation or emitting Infinity/NaN into a JSON receipt.
    with np.errstate(divide="ignore"):
        log_products = np.log1p(bets[:, None] * ((data - null_mean) / (1 + null_mean))).sum(axis=1)
    maximum = float(np.max(log_products))
    if maximum == -math.inf:
        log_e, p_value = None, 1.0
    else:
        log_e = maximum + math.log(float(np.dot(weights, np.exp(log_products - maximum))))
        # Keep the minimum representable positive float: a finite mixture must
        # never be reported as a logically impossible p=0 due to underflow.
        p_value = min(1.0, math.exp(max(-744.0, -log_e)))
    return {"independent_units": len(data), "mean_difference": float(data.mean()),
            "log_e_value": log_e, "zero_e_value": maximum == -math.inf,
            "p_value": p_value, "mixture": "uniform_0_1" if fractions is None else "fixed_equal_weight_grid",
            "fractions": bets.tolist(), "weights": weights.tolist(),
            "null_mean": null_mean, "null": "average_expectation_at_most_null_mean", "fixed_count_only": True}


def bounded_mean_lower_bound(differences, *, alpha=.025, fractions=None):
    """Conservative one-sided bound by inversion of the monotone batch test.

    Coverage is >=1-alpha for a fixed alpha under the same assumptions. A
    component bound at a data-selected Holm decision threshold is labeled as
    such, not as simultaneous coverage of all nine component means.
    """
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("Alpha must be strictly between zero and one")
    bounded_mean_evidence(differences, fractions=fractions)  # Validate before inversion.
    low, high = -1.0, 1.0
    for _ in range(60):
        midpoint = (low + high) / 2
        if midpoint == low or midpoint == high:
            break
        p_value = bounded_mean_evidence(differences, fractions=fractions, null_mean=midpoint)["p_value"]
        if p_value <= alpha:
            low = midpoint
        else:
            high = midpoint
    return low


def preview_bounded_family(entry_data):
    """Eight-component V04 IUT then two-entry Holm, always a candidate preview.

    Rows must be independent paired study blocks; columns are the exact
    registered method/comparator/endpoint ordering from components(entry).
    Neither values lying in [-1,1] nor this preview verifies sampling/support.
    """
    if not entry_data or not set(entry_data) <= {"V04-T0", "V05"}:
        raise ValueError("Unknown or empty Tier 0 family")
    reports, p_values = {}, {}
    for entry, matrix in entry_data.items():
        raw = np.asarray(matrix)
        required = components(entry)
        if raw.ndim != 2 or raw.shape[1] != len(required):
            raise ValueError("Every registered component is required")
        tests = {"/".join(key): bounded_mean_evidence(raw[:, index])
                 for index, key in enumerate(required)}
        p_values[entry] = max(test["p_value"] for test in tests.values())
        reports[entry] = {"components": tests, "entry_p_value": p_values[entry], "verdict": "INCONCLUSIVE"}
    for decision in holm_bonferroni(p_values, alpha=.05, family_size=2):
        reports[decision.entry_id]["family"] = decision.to_dict()
        reports[decision.entry_id]["candidate_clears"] = bool(decision.reject)
        for index, test in enumerate(reports[decision.entry_id]["components"].values()):
            test["lower_bound_at_entry_decision_alpha"] = bounded_mean_lower_bound(
                np.asarray(entry_data[decision.entry_id])[:, index], alpha=decision.adjusted_alpha)
        reports[decision.entry_id]["interval_scope"] = "Component decision bounds; not simultaneous confidence intervals for every component mean."
    return {"method": "fixed_count_bounded_mean_mixture_e_v1",
            "scientific_status": "VALID_UNDER_EXPLICIT_SUPPORT_AND_INDEPENDENCE_ASSUMPTIONS",
            "certifies_acceptance": False, "entries": reports,
            "not_authorized": ["raw_unbounded_returns", "empirical_range_as_support", "optional_stopping",
                               "outcome_dependent_exclusion", "unjustified_flattening_of_task_seed_blocks"]}
