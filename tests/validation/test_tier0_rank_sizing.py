import math

import numpy as np
import pytest

from validation.tier0_bounded_mean import bounded_mean_evidence
from validation.tier0_design import load_design
from validation.tier0_rank_design import rank_components
from validation.tier0_rank_sizing import component_power_lower, prospective_rank_sizing


def test_power_bound_is_below_exact_ternary_law_not_only_binary_frontier():
    n = 20
    probabilities = (.001, .008, .991)  # Mean .99; ties are allowed.
    exact = 0.0
    for losses in range(n + 1):
        for ties in range(n - losses + 1):
            wins = n - losses - ties
            if bounded_mean_evidence([-1] * losses + [0] * ties + [1] * wins)["p_value"] <= .025:
                coefficient = math.comb(n, losses) * math.comb(n - losses, ties)
                exact += coefficient * math.prod(p ** count for p, count in zip(probabilities, (losses, ties, wins)))
    bound = component_power_lower(n, .99)["power_lower_bound"]
    assert 0 < bound <= exact <= 1


def test_independent_nonidentical_bernoulli_means_use_average_not_iid_assumption():
    probabilities = [.999] * 10 + [.991] * 10
    weights = np.array([1.0])
    for p in probabilities:
        weights = np.convolve(weights, [1 - p, p])
    exact = sum(probability for wins, probability in enumerate(weights) if
                bounded_mean_evidence([1] * wins + [-1] * (20 - wins))["p_value"] <= .025)
    bound = component_power_lower(20, 2 * sum(probabilities) / 20 - 1)["power_lower_bound"]
    assert 0 < bound <= exact


def test_deterministic_and_numerically_extreme_alternatives_preserve_boundary():
    assert component_power_lower(5, 1)["power_lower_bound"] == 0  # Cannot clear alpha even with all wins.
    assert component_power_lower(20, 1)["power_lower_bound"] == 1
    assert .99 < component_power_lower(20, math.nextafter(1, 0))["power_lower_bound"] <= 1
    assert component_power_lower(20, .01)["power_lower_bound"] == 0


def test_all_components_and_anytime_support_enter_conditional_count_selection():
    design = load_design()
    grid = design["budget_grid"]
    alternatives = {entry: {"/".join(key): (1 - grid[1] if key[2] == "anytime_win" else 1) * .999
                            for key in rank_components(entry)} for entry in ("V04-T0", "V05")}
    result = prospective_rank_sizing(alternatives, grid)
    assert all(item["conditional_chosen_n"] is not None for item in result["entries"].values())
    assert not result["selects_campaign_count"] and not result["actual_alternative_established"]
    assert result["verdict"] == "INCONCLUSIVE"
    first = next(iter(alternatives["V04-T0"]))
    alternatives["V04-T0"][first] = .01
    result = prospective_rank_sizing(alternatives, grid)
    assert result["entries"]["V04-T0"]["conditional_chosen_n"] is None
    alternatives["V04-T0"].pop(first)
    with pytest.raises(ValueError, match="nine"):
        prospective_rank_sizing(alternatives, grid)


@pytest.mark.parametrize("n,mean,magnitude", [(True,.1,1), (21,.1,1), (20,0,1), (20,1,.99), (20,float('nan'),1)])
def test_invalid_or_unsupported_power_inputs_refused(n, mean, magnitude):
    with pytest.raises(ValueError):
        component_power_lower(n, mean, magnitude=magnitude)
