"""Conservative prospective sizing from independent protected pilot vectors.

The simultaneous confidence statement and power bound are conditional on the
fixed experiment, stationary independent vector law and sufficient execution
resources. Neither the pilot nor a sufficient sample count is an acceptance.
"""

from __future__ import annotations

import math

from validation.tier0_phase_contracts import KL_SIZING_POLICY, SIZING_POLICY, experiment_digest
from validation.tier0_rank_design import rank_components
from validation.tier0_rank_sizing import component_power_lower


def kl_lower(mean, n, error):
    """Invert the bounded-variable Chernoff upper tail for a mean in [0,1].

    For independent identically distributed bounded observations, Hoeffding's
    Bernoulli mgf domination gives P(KL(mean_hat, mu)>=log(1/delta)/n,
    mean_hat>mu)<=delta. It needs neither a Bernoulli law nor normality.
    """
    if (isinstance(mean, bool) or not isinstance(mean, (float, int)) or not math.isfinite(mean)
            or not 0 <= mean <= 1 or type(n) is not int or n < 1 or not 0 < error < 1):
        raise ValueError("Valid bounded sample mean, count and confidence error required")
    if mean == 0:
        return 0.0
    if mean == 1:
        return math.exp(math.log(error) / n)
    low, high, threshold = 0.0, mean, -math.log(error) / n
    for _ in range(70):
        mid = (low + high) / 2
        divergence = mean * math.log(mean / mid) + (1 - mean) * math.log((1 - mean) / (1 - mid))
        if divergence > threshold:
            low = mid
        else:
            high = mid
    return low  # Outward/conservative rounding.


def size_pilot_vectors(rows, unresolved, grid, *, policy=None):
    """Apply the one prespecified rule; never select by favorable pilot output."""
    if policy == SIZING_POLICY:
        from validation.tier0_joint_pilot_sizing import size_joint_vectors

        return size_joint_vectors(rows, unresolved, grid, policy=policy)
    return size_kl_pilot_vectors(rows, unresolved, grid, policy=policy)


def size_kl_pilot_vectors(rows, unresolved, grid, *, policy=None):
    """Derive nine lower means, two loss bounds and the smallest sufficient n.

    An unresolved vector means at least one planned study/curve was unresolved.
    At most floor(.1*n) such vectors guarantees at most 10% unresolved studies
    in every arm, even if every task is unresolved in each bad vector. Under
    the stationary independent-vector model their count has a binomial law;
    its exact upper tail is bounded using the pilot upper confidence limit q.
    Utility lower bounds already retain missingness; subtracting this veto tail
    additionally permits arbitrary dependence between loss and utility.
    Cost vetoes remain separate and must be disclosed, never assumed measured
    by the statistical calculation. Raw-data verification is a separate layer.
    """
    if policy != KL_SIZING_POLICY:
        raise ValueError("Frozen prospective pilot sizing rule required")
    if (not isinstance(grid, list) or len(grid) < 2 or grid[0] != 0 or grid[-1] != 1
            or any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in grid)
            or any(a >= b for a, b in zip(grid, grid[1:]))):
        raise ValueError("Frozen increasing budget grid required")
    entries = ("V04-T0", "V05")
    if set(rows) != set(entries) or set(unresolved) != set(entries):
        raise ValueError("Both pilot entries required")
    error = policy["planning_error"] / policy["confidence_components"]
    results = {}
    for entry in entries:
        values, flags = rows[entry], unresolved[entry]
        keys = ["/".join(key) for key in rank_components(entry)]
        if (not isinstance(values, list) or len(values) < 5 or len(flags) != len(values)
                or any(type(flag) is not bool for flag in flags)):
            raise ValueError("At least five complete planned pilot vectors and loss flags required")
        magnitudes = [1 - grid[1] if key.endswith("/anytime_win") else 1.0 for key in keys]
        for row in values:
            if (not isinstance(row, list) or len(row) != len(keys)
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                           or not -1 <= x <= b + 1e-12 for x, b in zip(row, magnitudes))):
                raise ValueError("Invalid retained pilot vector support or component coverage")
        means = {key: (b + 1) * kl_lower(min(1.0, math.fsum((row[j] + 1) / (b + 1)
                 for row in values) / len(values)), len(values), error) - 1
                 for j, (key, b) in enumerate(zip(keys, magnitudes))}
        loss_upper = 1 - kl_lower(1 - sum(flags) / len(flags), len(flags), error)
        frontier = []
        for n in range(5, 21):
            powers = [0.0 if means[key] <= 0 else component_power_lower(
                n, means[key], magnitude=b, negative_magnitude=1.0)["power_lower_bound"]
                for key, b in zip(keys, magnitudes)]
            statistical = max(0.0, 1 - math.fsum(1 - p for p in powers))
            veto = min(1.0, math.fsum(math.comb(n, k) * loss_upper ** k * (1 - loss_upper) ** (n - k)
                                     for k in range(n // 10 + 1, n + 1)))
            combined = max(0.0, statistical - veto)
            frontier.append({"n": n, "test_power_lower": statistical, "unresolved_veto_upper": veto,
                             "power_lower_conditional_on_resources": combined})
        count = next((r["n"] for r in frontier if r["power_lower_conditional_on_resources"] >= .8), None)
        results[entry] = {"pilot_vectors": len(values), "mean_lower_bounds": means, "unresolved_probability_upper": loss_upper,
                          "chosen_n": count, "frontier": frontier}
    return {"kind": "independent_pilot_rank_sizing_v1", "policy": policy, "entries": results,
            "verdict": "SIZED" if all(r["chosen_n"] is not None for r in results.values()) else "INFEASIBLE_UNDER_RULE",
            "confidence": .95, "power_target": .8, "certifies_acceptance": False,
            "assumptions": ["Independent stationary pilot/confirmation vectors from the identical frozen experiment.",
                            "Separate confirmation, including its random streams; no outcome reuse.",
                            "Frozen execution resource envelope is sufficient; cost vetoes still prevent acceptance."],
            "scope": "conditional_power_with_simultaneous_planning_confidence_not_an_unconditional_guarantee"}


def ideal_pilot_screen(count, grid, *, policy=None):
    """An upper bound on what this sufficient rule can report with count rows.

    Every component is at its mathematical maximum and no vector is lost.
    Failure of this screen proves futility of this rule/count, not impossibility
    of every statistical design or of actual superiority.
    """
    if type(count) is not int or count < 5:
        raise ValueError("Pilot screening count must be at least five")
    rows = {entry: [[1 - grid[1] if key[-1] == "anytime_win" else 1.0
                     for key in rank_components(entry)]] * count for entry in ("V04-T0", "V05")}
    return size_pilot_vectors(rows, {entry: [False] * count for entry in rows}, grid,
                             policy=SIZING_POLICY if policy is None else policy)


def require_nonfutile_pilot(design):
    """Refuse spending on a count that fails even with maximal ideal outcomes.

    Passing is only necessary for this sizing rule to succeed. It predicts
    neither the observed pilot outcome nor the actual confirmation power.
    """
    if design.get("sizing_policy") != SIZING_POLICY:
        raise ValueError("Frozen prospective pilot sizing rule required")
    screens = {}
    for entry in ("V04-T0", "V05"):
        count = design.get("selected_counts", {}).get("pilot", {}).get(entry)
        if type(count) is not int or not 5 <= count <= len(design.get("seed_sets", {}).get("pilot", [])):
            raise ValueError("Frozen selected pilot count and reserved streams required")
        if count not in screens:
            screens[count] = ideal_pilot_screen(count, design["budget_grid"])
        if screens[count]["entries"][entry]["chosen_n"] is None:
            raise ValueError(f"{entry}: selected pilot count {count} is futile under the prespecified sizing rule even with ideal outcomes")
    return screens


def verify_sizing_receipt(design, phase, root):
    """Read/reconstruct actual pilot campaigns; ignore receipt decision labels."""
    from validation.tier0_objectivity import read_bound_json
    from validation.tier0_rank_campaign import _load_bundle, _read, recompute_protected, recompute_result
    from validation.tier0_phase_contracts import verify_phase_freeze
    from validation.tier0_isolation import verify_sequence
    from validation.tier0_design import resource_limits

    if phase != "confirmation":
        raise ValueError("Rank sizing supports only fixed confirmation")
    try:
        receipt = read_bound_json(root, design.get("sizing_receipt"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("STAT-03/E: prospective protected-rank sizing requires a supported actual alternative and pilot receipt") from exc
    if (receipt.get("kind") != "independent_pilot_rank_sizing_receipt_v1"
            or receipt.get("experiment_digest") != experiment_digest(design)
            or set(receipt.get("pilot_results", {})) != {"V04-T0", "V05"}):
        raise ValueError("Prospective protected-rank sizing receipt has incompatible pilot evidence")
    rows, losses = {}, {}
    confirmation_freeze = verify_phase_freeze(design, phase, root)
    for entry, ref in receipt["pilot_results"].items():
        result = read_bound_json(root, ref)
        if result.get("phase") != "pilot":
            raise ValueError("Sizing cannot reuse confirmation outcomes")
        # Enforces audited directory, readiness, source, raw process order and accounting.
        recompute_result(entry, result)
        _, pilot, _ = _load_bundle(result["run_dir"], result["search_freeze"])
        if experiment_digest(pilot) != experiment_digest(design):
            raise ValueError("Pilot experiment differs from confirmation")
        sequence = _read(result["run_dir"], result["process_isolation"])
        jobs = verify_sequence(result["run_dir"], sequence["processes"], expected_source=design["source_digest"])
        if (not jobs or any(job["observer"]["boot_id"] != confirmation_freeze["boot_id"]
                            or job["finish_ns"] >= confirmation_freeze["recorded_ns"] for job in jobs)):
            raise ValueError("Pilot observations must precede the confirmation freeze on the same local recorder boot")
        report = recompute_protected(result["run_dir"], result["search_freeze"], result["protected_evaluations"])
        if report["budget_veto"] or result["duration_seconds"] > resource_limits(pilot, entry)["campaign_cap_seconds"]:
            raise ValueError("Pilot exceeded its cost envelope; resource repair required")
        rows[entry] = report["entries"][entry]["lower_rows"]
        seeds = pilot["seed_sets"]["pilot"][:len(rows[entry])]
        losses[entry] = [any(row["unresolved"] for row in report["raw_study_outcomes"]
                            if row["identity"][2] == seed) for seed in seeds]
        n = design.get("selected_counts", {}).get("confirmation", {}).get(entry)
        if type(n) is not int or not 5 <= n <= 20:
            raise ValueError("Confirmation count missing or outside registered cap")
        for field in ("campaign_cap_seconds", "protected_cap_seconds"):
            if resource_limits(design, entry)[field] / n < resource_limits(pilot, entry)[field] / len(seeds):
                raise ValueError("Confirmation resource envelope shrinks the pilot allowance per vector")
    rebuilt = size_pilot_vectors(rows, losses, design["budget_grid"], policy=design.get("sizing_policy"))
    if rebuilt["verdict"] != "SIZED":
        raise ValueError("Pilot cannot establish .80 power under the frozen sizing rule and 20-vector cap")
    if any(design["selected_counts"][phase][entry] != row["chosen_n"] for entry, row in rebuilt["entries"].items()):
        raise ValueError("Confirmation count differs from independently reconstructed pilot sizing")
    return rebuilt
