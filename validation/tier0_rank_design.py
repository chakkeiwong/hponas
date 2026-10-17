"""Adopted rank-outcome mathematics; previews do not certify campaigns.

Rank superiority is a different claim from raw-return mean superiority. These
offline previews never certify a campaign or supply a held-out task selection.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import binom

from validation.tier0_bounded_mean import bounded_mean_evidence, preview_bounded_family
from validation.tier0_design import ARMS


METHOD = "paired_rank_fixed_suite_candidate_v1"


def _finite(value, name, *, minimum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (minimum is not None and value < minimum)):
        raise ValueError(f"Invalid {name}")
    return value


def _grid(grid):
    values = tuple(grid)
    if len(values) < 2:
        raise ValueError("Budget grid must have at least two points")
    for value in values:
        _finite(value, "budget fraction", minimum=0)
    if values[0] != 0 or values[-1] != 1 or any(a >= b for a, b in zip(values, values[1:])):
        raise ValueError("Budget grid must increase strictly from zero to one")
    return values


def incumbent_curve(trace, grid):
    """Decode a verified prefix into finite incumbents, no-policy, or unknown.

    None means unknown; (False, None) is a verified absence of a usable policy;
    (True, value) is a delivered policy's finite search-evaluation return.
    A method stopping retains its previously delivered incumbent. Unresolved
    infrastructure loss leaves its unobserved suffix unknown, never excluded.
    Input trace labels need independent evidence in any eventual adapter; this
    decoder is not that validation. Over-budget observations never affect scores.
    """
    grid = _grid(grid)
    if trace is None:
        return [None] * len(grid)
    budget = _finite(trace["budget_seconds"], "budget", minimum=0)
    coverage = _finite(trace["observed_until_seconds"], "observed prefix", minimum=0)
    state = trace["state"]
    if budget == 0 or state not in {"complete", "algorithm_stopped", "unresolved"}:
        raise ValueError("Unknown trace state or zero budget")
    if state == "complete" and coverage < budget:
        raise ValueError("Complete trace does not cover its budget")
    observations, previous = [], 0.0
    for observation in trace["observations"]:
        when = _finite(observation["completed_seconds"], "completion time", minimum=0)
        value = _finite(observation["value"], "raw return")
        if when <= previous or when > coverage:
            raise ValueError("Unordered observation or observation outside verified prefix")
        observations.append((when, value))
        previous = when
    curve = []
    for fraction in grid:
        when = fraction * budget
        if state == "unresolved" and when > coverage:
            curve.append(None)
        else:
            available = [value for completed, value in observations if completed <= when]
            curve.append((True, max(available)) if available else (False, None))
    return curve


def rank_interval(candidate, comparator):
    """Bounds on win-minus-loss utility; ties, including two no-policies, are 0.

    Every finite delivered policy outranks no delivered policy. Unknown states
    span all allowed possibilities. No numerical return floor or clipping is
    used. Direct comparisons avoid overflowing a subtraction of extreme returns.
    """
    for state in (candidate, comparator):
        if state is None:
            continue
        if not isinstance(state, tuple) or len(state) != 2 or type(state[0]) is not bool:
            raise ValueError("Invalid policy state")
        if state[0]:
            _finite(state[1], "policy return")
        elif state[1] is not None:
            raise ValueError("No-policy state must not contain an invented return")
    if candidate is None and comparator is None:
        return -1.0, 1.0
    if candidate is None:
        return (0.0, 1.0) if not comparator[0] else (-1.0, 1.0)
    if comparator is None:
        return (-1.0, 0.0) if not candidate[0] else (-1.0, 1.0)
    if candidate[0] != comparator[0]:
        value = 1.0 if candidate[0] else -1.0
    elif not candidate[0]:
        value = 0.0
    else:
        value = float((candidate[1] > comparator[1]) - (candidate[1] < comparator[1]))
    return value, value


def paired_rank_endpoints(candidate, comparator, grid):
    """Search-score diagnostic; protected curves use rank_curve_endpoints."""
    grid = _grid(grid)
    if candidate is not None and comparator is not None:
        if candidate["budget_seconds"] != comparator["budget_seconds"]:
            raise ValueError("Paired arms must have the same measured budget")
    return rank_curve_endpoints(incumbent_curve(candidate, grid), incumbent_curve(comparator, grid), grid)


def rank_curve_endpoints(candidate_curve, comparator_curve, grid):
    """Final and anytime utility of frozen-policy protected score curves.

    The caller supplies policies selected using search scores only, then
    independently evaluated; maximizing the protected curve would be leakage.
    """
    grid = _grid(grid)
    if len(candidate_curve) != len(grid) or len(comparator_curve) != len(grid):
        raise ValueError("Both policy curves must cover every frozen grid point")
    intervals = [rank_interval(a, b) for a, b in zip(candidate_curve, comparator_curve, strict=True)]
    return {
        "final_win": intervals[-1],
        "anytime_win": tuple(math.fsum((b - a) * pair[index] for a, b, pair in
                                      zip(grid, grid[1:], intervals[:-1])) for index in (0, 1)),
    }


def rank_components(entry):
    if entry == "V04-T0":
        return [(arm, baseline, endpoint) for arm in ("gp_log", "tpe_log")
                for baseline in ("sobol_log", "random_log")
                for endpoint in ("final_win", "anytime_win")]
    if entry == "V05":
        return [("gp_log", "gp_linear", "final_win")]
    raise ValueError("Unknown rank entry")


def preview_rank_family(entry_tasks, block_ids, records, grid):
    """Keep the entire planned Cartesian product, including absent records.

    One inference row is a complete seed vector across a fixed task suite.
    Cross-task dependence within the vector is unrestricted. Different vectors
    must be independent; declaring identifiers does not establish this. Lower
    utility bounds enter the monotone mean test, preserving validity under
    arbitrary missingness since lower bounds never exceed the latent outcomes.
    """
    grid = _grid(grid)
    if not entry_tasks or not set(entry_tasks) <= set(ARMS):
        raise ValueError("Unknown or empty entry family")
    blocks = tuple(block_ids)
    if (not blocks or any(type(b) is not int or b < 0 for b in blocks)
            or len(set(blocks)) != len(blocks)):
        raise ValueError("Distinct nonnegative planned block IDs are required")
    expected = set()
    for entry, tasks in entry_tasks.items():
        if (not tasks or any(not isinstance(t, str) or not t for t in tasks)
                or len(set(tasks)) != len(tasks)):
            raise ValueError("Distinct named tasks are required")
        expected.update((entry, task, block, arm) for task in tasks for block in blocks for arm in ARMS[entry])
    lookup, budgets = {}, {}
    for record in records:
        key = tuple(record.get(k) for k in ("entry", "task", "block", "arm"))
        if key not in expected or key in lookup:
            raise ValueError("Duplicate or unplanned study record")
        trace = record["trace"]
        incumbent_curve(trace, grid)  # Validate even a sole supplied record.
        if trace is not None:
            task = key[1]
            if task in budgets and trace["budget_seconds"] != budgets[task]:
                raise ValueError("Task budget differs across arms, blocks or entries")
            budgets[task] = trace["budget_seconds"]
        lookup[key] = trace
    lower, upper, counts = {}, {}, {}
    for entry, tasks in entry_tasks.items():
        low_rows, high_rows = [], []
        for block in blocks:
            intervals = []
            for task in tasks:
                endpoints = {}
                for arm, baseline, _ in rank_components(entry):
                    if (arm, baseline) not in endpoints:
                        endpoints[arm, baseline] = paired_rank_endpoints(
                            lookup.get((entry, task, block, arm)),
                            lookup.get((entry, task, block, baseline)), grid)
                intervals.append([endpoints[arm, baseline][endpoint]
                                  for arm, baseline, endpoint in rank_components(entry)])
            averages = [[math.fsum(row[j][i] for row in intervals) / len(tasks)
                         for j in range(len(rank_components(entry)))] for i in (0, 1)]
            low_rows.append(averages[0])
            high_rows.append(averages[1])
        lower[entry], upper[entry] = low_rows, high_rows
        counts[entry] = {"planned_studies": len(tasks) * len(blocks) * len(ARMS[entry]),
                         "absent_studies": sum(k not in lookup or lookup[k] is None for k in expected if k[0] == entry),
                         "fixed_tasks": len(tasks), "independent_vectors_assumed": len(blocks)}
    result = preview_bounded_family(lower)
    for entry, report in result["entries"].items():
        # Keep the implementation's IUT/Holm, but never mislabel rank tests as
        # the currently registered raw objective/regret-AUC components.
        report["components"] = {"/".join(key): test for key, test in
                                zip(rank_components(entry), report["components"].values(), strict=True)}
        report["lower_rows"] = lower[entry]
        report["upper_rows"] = upper[entry]
        report["identified_mean_intervals"] = list(zip(np.mean(lower[entry], axis=0).tolist(),
                                                       np.mean(upper[entry], axis=0).tolist()))
        report["counts"] = counts[entry]
    result.update(method=METHOD, scientific_status="ENGINEERING_SEARCH_SCORE_PREVIEW",
                  scope="Conditional on named fixed suite; no task-population inference",
                  outcome="Paired win-minus-loss utility, not raw-return mean or raw-regret AUC",
                  endpoint_status="Search-score diagnostic; final acceptance requires protected incumbent evaluation binding",
                  assumption="Independent complete seed vectors; fixed suite, grid and count",
                  missingness="Retained with worst-case lower bounds, no exclusions or replacement seeds")
    return result


def exact_binary_power(independent_units, *, alpha=.025, target_power=.8, components=1, magnitude=1.0):
    """Exact power of the mixture test for a stated iid +/-1 alternative only.

    This model makes all task ranks in a vector identical. For an anytime
    endpoint, magnitude accounts for the initial interval with no policies
    (maximum .99 on the current grid), so +/-1 is not claimed attainable there.
    It allows arbitrary
    dependence between components by using a union-bound sufficient power target.
    It is an analytic sensitivity frontier, not power of unobserved PPO runs and
    not a practical-effect threshold or a new sample-size authorization.
    """
    if type(independent_units) is not int or independent_units < 1 or independent_units > 1000:
        raise ValueError("Independent unit count must be in 1..1000")
    if type(components) is not int or components < 1:
        raise ValueError("Positive component count required")
    _finite(magnitude, "binary magnitude")
    if not 0 < magnitude <= 1:
        raise ValueError("Binary magnitude must be in (0,1]")
    for name, value in (("alpha", alpha), ("target power", target_power)):
        _finite(value, name)
        if not 0 < value < 1:
            raise ValueError(f"{name} must be strictly between zero and one")
    threshold = next((k for k in range(independent_units + 1)
                      if bounded_mean_evidence([magnitude] * k + [-magnitude] * (independent_units - k))["p_value"] <= alpha), None)
    component_target = 1 - (1 - target_power) / components
    if component_target >= 1:
        raise ValueError("Component target rounded to one")
    required = None
    if threshold is not None:
        low, high = 0.0, 1.0
        for _ in range(60):
            mid = (low + high) / 2
            if binom.sf(threshold - 1, independent_units, mid) >= component_target:
                high = mid
            else:
                low = mid
        required = high
    return {"independent_units": independent_units, "components": components,
            "component_alpha": alpha, "joint_power_target": target_power, "binary_magnitude": magnitude,
            "sufficient_component_power": component_target, "critical_wins": threshold,
            "required_win_probability_in_binary_model": required,
            "binary_null_rejection_probability": 0.0 if threshold is None else float(binom.sf(threshold - 1, independent_units, .5)),
            "model": "iid +/-magnitude vector outcomes; no ties/missingness; all tasks agree within each vector",
            "joint_statement": "Sufficient union bound over components; component dependence unrestricted",
            "certifies_acceptance": False, "selects_sample_size": False}
