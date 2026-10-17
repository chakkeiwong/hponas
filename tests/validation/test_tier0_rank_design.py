import copy
import itertools
import math

import numpy as np
import pytest
from scipy.stats import binom

from validation.tier0_bounded_mean import bounded_mean_evidence
from validation.tier0_inference import require_acceptance_inference
from validation.tier0_rank_design import (
    METHOD, exact_binary_power, incumbent_curve, paired_rank_endpoints,
    preview_rank_family, rank_interval,
)


GRID = [0, .25, .5, .75, 1]


def trace(value=None, *, state="complete", coverage=4, observations=None):
    return {"budget_seconds": 4, "observed_until_seconds": coverage, "state": state,
            "observations": observations if observations is not None else
            ([] if value is None else [{"completed_seconds": .5, "value": value}])}


def test_no_future_leak_and_left_rectangle_occupancy():
    candidate = trace(observations=[{"completed_seconds": 1, "value": 1},
                                   {"completed_seconds": 4, "value": 10},
                                   {"completed_seconds": 5, "value": 1e308}], coverage=5)
    baseline = trace(2)
    assert incumbent_curve(candidate, GRID) == [(False, None), (True, 1), (True, 1), (True, 1), (True, 10)]
    assert paired_rank_endpoints(candidate, baseline, GRID) == {"final_win": (1, 1), "anytime_win": (-.75, -.75)}


def test_algorithm_failure_retains_incumbent_and_no_policy_is_an_outcome():
    stopped = trace(2, state="algorithm_stopped", coverage=1)
    assert paired_rank_endpoints(stopped, trace(1), GRID)["final_win"] == (1, 1)
    assert paired_rank_endpoints(trace(state="algorithm_stopped", coverage=.5), trace(-1e308), GRID)["final_win"] == (-1, -1)
    assert paired_rank_endpoints(trace(), trace(), GRID)["final_win"] == (0, 0)


def test_unresolved_loss_keeps_known_prefix_and_bounds_unknown_suffix():
    candidate = trace(2, state="unresolved", coverage=1)
    result = paired_rank_endpoints(candidate, trace(1), GRID)
    assert result == {"final_win": (-1, 1), "anytime_win": (-.25, .75)}
    assert rank_interval(None, (False, None)) == (0, 1)
    assert rank_interval((False, None), None) == (-1, 0)


def test_all_latent_completions_lie_within_missingness_intervals():
    states = [(False, None), (True, -1e308), (True, 0), (True, 1e308)]
    for a, b in itertools.product([None, *states], repeat=2):
        low, high = rank_interval(a, b)
        for actual_a, actual_b in itertools.product(states if a is None else [a], states if b is None else [b]):
            realized, _ = rank_interval(actual_a, actual_b)
            assert low <= realized <= high


def test_rank_superiority_must_not_be_reported_as_mean_superiority():
    values = [1] * 19 + [-1000]
    assert sum(values) / len(values) < 0
    ranks = [rank_interval((True, value), (True, 0))[0] for value in values]
    assert sum(ranks) / len(ranks) == .9
    assert bounded_mean_evidence(ranks)["p_value"] < .025
    with pytest.raises(ValueError, match="no validated acceptance replacement"):
        require_acceptance_inference({"method": METHOD})


def test_all_planned_vectors_retained_no_false_task_replication():
    tasks = {"V04-T0": ["a", "b", "c"], "V05": ["a", "b", "c"]}
    records = [{"entry": entry, "task": task, "block": 0, "arm": arm, "trace": trace(1)}
               for entry, arms in [("V04-T0", ["gp_log", "tpe_log", "sobol_log", "random_log"]),
                                    ("V05", ["gp_log", "gp_linear"])]
               for task in tasks[entry] for arm in arms]
    result = preview_rank_family(tasks, [0, 1], records, GRID)
    for entry in tasks:
        report = result["entries"][entry]
        assert report["counts"]["independent_vectors_assumed"] == 2
        assert len(report["lower_rows"]) == 2
        assert report["lower_rows"][0] == [0] * len(report["components"])
        assert report["lower_rows"][1] == [-1] * len(report["components"])
        assert report["counts"]["absent_studies"] == report["counts"]["planned_studies"] // 2
        assert report["verdict"] == "INCONCLUSIVE"
    assert len(result["entries"]["V04-T0"]["components"]) == 8
    assert len(result["entries"]["V05"]["components"]) == 1
    assert result["certifies_acceptance"] is False


def test_missing_record_cannot_improve_candidate_evidence():
    tasks, blocks = {"V05": ["a"]}, list(range(20))
    records = [{"entry": "V05", "task": "a", "block": block, "arm": arm, "trace": trace(value)}
               for block in blocks for arm, value in [("gp_log", 1), ("gp_linear", 0)]]
    full = preview_rank_family(tasks, blocks, records, GRID)["entries"]["V05"]
    missing = preview_rank_family(tasks, blocks, records[:-2], GRID)["entries"]["V05"]
    assert missing["entry_p_value"] >= full["entry_p_value"]
    assert len(missing["lower_rows"]) == 20
    # An isolated entry still pays the first step of the two-entry Holm family.
    assert full["family"]["adjusted_alpha"] == .025


def test_adversarial_missingness_preserves_null_error_exactly():
    # Mean-zero skewed law: +.1 with probability 10/11, -1 with 1/11.
    # Hide all negative outcomes; lower-bound them at -1, keep planned n=60.
    # Validity is checked by enumeration over the sufficient statistic, no MC.
    n, p, error = 60, 10 / 11, 0.0
    for positive in range(n + 1):
        data = [.1] * positive + [-1] * (n - positive)
        if bounded_mean_evidence(data)["p_value"] <= .025:
            error += math.comb(n, positive) * p ** positive * (1 - p) ** (n - positive)
    assert 0 < error <= .025


def test_sensitivity_frontier_matches_independent_binomial_summation():
    result = exact_binary_power(20, components=8, magnitude=.99)
    k = result["critical_wins"]
    q = result["required_win_probability_in_binary_model"]
    power = sum(math.comb(20, wins) * q ** wins * (1 - q) ** (20 - wins) for wins in range(k, 21))
    assert power == pytest.approx(.975)
    assert binom.sf(k - 1, 20, q - .001) < .975
    assert bounded_mean_evidence([.99] * k + [-.99] * (20 - k))["p_value"] <= .025
    assert bounded_mean_evidence([.99] * (k - 1) + [-.99] * (21 - k))["p_value"] > .025
    assert result["binary_null_rejection_probability"] <= .025
    assert result["selects_sample_size"] is False
    assert exact_binary_power(5)["critical_wins"] is None


@pytest.mark.parametrize("change", [
    {"budget_seconds": 0}, {"budget_seconds": True}, {"state": "retry_winner"},
    {"observed_until_seconds": 3}, {"observations": [{"completed_seconds": 1, "value": math.inf}]},
    {"observations": [{"completed_seconds": 5, "value": 1}]},
    {"observations": [{"completed_seconds": 0, "value": 1}]},
])
def test_bad_trace_cannot_be_turned_into_a_usable_policy(change):
    invalid = trace(1)
    invalid.update(change)
    with pytest.raises(ValueError):
        incumbent_curve(invalid, GRID)


@pytest.mark.parametrize("grid", [[], [0], [0, 0, 1], [.1, 1], [0, .5], [0, math.nan, 1], [False, 1]])
def test_bad_grid_rejected(grid):
    with pytest.raises(ValueError):
        incumbent_curve(None, grid)


def test_duplicate_unplanned_and_changed_budget_records_refused():
    item = {"entry": "V05", "task": "a", "block": 0, "arm": "gp_log", "trace": trace(1)}
    with pytest.raises(ValueError, match="Duplicate"):
        preview_rank_family({"V05": ["a"]}, [0], [item, item], GRID)
    with pytest.raises(ValueError, match="unplanned"):
        preview_rank_family({"V05": ["a"]}, [1], [item], GRID)
    second = copy.deepcopy(item)
    second["arm"] = "gp_linear"
    second["trace"]["budget_seconds"] = 3
    with pytest.raises(ValueError, match="budget differs"):
        preview_rank_family({"V05": ["a"]}, [0], [item, second], GRID)


def test_task_aggregation_uses_equal_weights_without_iid_task_assumption():
    records = [{"entry": "V05", "task": task, "block": 0, "arm": arm, "trace": trace(value)}
               for task, candidate in [("a", 3), ("b", -100), ("c", 1)]
               for arm, value in [("gp_log", candidate), ("gp_linear", 0)]]
    report = preview_rank_family({"V05": ["a", "b", "c"]}, [0], records, GRID)["entries"]["V05"]
    np.testing.assert_allclose(report["lower_rows"], [[1 / 3]])
    assert report["counts"]["independent_vectors_assumed"] == 1
