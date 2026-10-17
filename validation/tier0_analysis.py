"""Independent endpoint extraction and paired Tier 0 decision recomputation."""

from __future__ import annotations

import math
import numpy as np

from validation.stats import Cluster, holm_bonferroni, superiority_one_sided
from validation.tier0_design import (
    ACCOUNTING, ARMS, ENDPOINTS, canonical_digest, require_complete, study_stream_slot, valid_config,
)


def components(entry):
    if entry == "V04-T0":
        return [(arm, comparator, endpoint) for arm in ("gp_log", "tpe_log")
                for comparator in ("sobol_log", "random_log") for endpoint in ENDPOINTS[entry]]
    if entry == "V05":
        return [("gp_log", "gp_linear", "final_objective")]
    raise ValueError("Unknown entry")


def training_seed(optimizer_seed, index):
    # Reserve 2**17 slots per optimizer seed: 0..9999 for training and
    # 100000..109999 for PPO search evaluation. Adjacent studies cannot reuse
    # each other's search/training seeds; the whole range fits uint32.
    if type(optimizer_seed) is not int or not 0 <= optimizer_seed < 32768 or not 0 <= index < 10000:
        raise ValueError("Evaluation seed outside reserved namespace")
    return optimizer_seed * 131072 + index


def endpoints(design, task_id, study):
    """Use only observations available by each declared budget point.

    The over-budget evaluation is charged in elapsed_seconds, but never leaks
    into final quality or AUC. A failed/short/truncated study is missing whole.
    """
    task = design["tasks"][task_id]
    budget = task["budget"]["seconds"]
    slot = study_stream_slot(design, task_id, study["seed"])
    if study.get("rng_stream_slot") != slot:
        raise ValueError("Study random stream differs from frozen task/block namespace")
    if study.get("accounting") != ACCOUNTING or study.get("budget_seconds") != budget:
        raise ValueError("Study accounting differs from design")
    elapsed = study.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Invalid measured elapsed time")
    observations = study.get("observations", [])
    if len(observations) > task["budget"]["trial_limit"]:
        raise ValueError("Trial safety limit exceeded")
    last = -1.0
    for index, observation in enumerate(observations):
        time = observation["completed_seconds"]
        value = observation["value"]
        if (not math.isfinite(time) or time <= last or time > elapsed
                or not math.isfinite(value) or observation.get("index") != index):
            raise ValueError("Invalid, unordered or nonfinite observation")
        if not valid_config(task, observation["config"]):
            raise ValueError("Observed configuration outside physical domain")
        if observation.get("training_seed") != training_seed(slot, index):
            raise ValueError("Evaluation seed differs from frozen pairing")
        last = time
    if study["entry"] == "V05":
        initial = task["initial_configs"][str(study["seed"])]
        if [r["config"] for r in observations[:5]] != initial[:len(observations[:5])]:
            raise ValueError("V05 initial physical configurations differ between arms")
        if len(observations) < len(initial):
            return None
    if (study.get("status") != "complete" or study.get("accounting_complete") is not True
            or elapsed < budget or elapsed > budget + task["budget"]["max_overshoot_seconds"]):
        return None
    available = [r for r in observations if r["completed_seconds"] <= budget]
    if not available or (study["entry"] == "V05" and len(available) < 5):
        return None
    bounds = task["scale_bounds"]
    maximize = bounds["direction"] == "maximize"
    best = max if maximize else min
    grid = np.asarray(design["budget_grid"], dtype=float)
    values = []
    for fraction in grid:
        seen = [r["value"] for r in available if r["completed_seconds"] <= fraction * budget]
        values.append(best(seen) if seen else task["initial_objective"])
    sign = 1 if maximize else -1
    regret = sign * (task["regret_reference"] - np.asarray(values)) / (bounds["high"] - bounds["low"])
    # Never interpolate toward a result that was not yet available. No clipping
    # to [0,1]: declared scale bounds are denominators, not observed extrema.
    return {"final_objective": values[-1], "regret_auc": float(np.dot(np.diff(grid), regret[:-1]))}


def collect_blocks(design, records, phase, entry):
    """Retain all planned arms; exclude an incomplete block from every component."""
    seeds = design["seed_sets"][phase]
    if design.get("status") == "certified":
        seeds = seeds[:design["selected_counts"][phase][entry]]
    tasks = design["entry_tasks"][entry]
    expected = {(t, seed, arm) for t in tasks for seed in seeds for arm in ARMS[entry]}
    lookup = {}
    for record in records:
        if record.get("entry") != entry:
            continue
        key = (record.get("task"), record.get("seed"), record.get("arm"))
        if key not in expected or key in lookup:
            raise ValueError("Unexpected or duplicate task/seed/arm record")
        if record.get("design_digest") != canonical_digest(design) or record.get("phase") != phase:
            raise ValueError("Record belongs to a different design or seed phase")
        lookup[key] = record
    missing = {arm: 0 for arm in ARMS[entry]}
    blocks, dropped = {}, []
    for tid in tasks:
        values = []
        for seed in seeds:
            measured = {}
            for arm in ARMS[entry]:
                record = lookup.get((tid, seed, arm))
                measured[arm] = endpoints(design, tid, record) if record is not None else None
                missing[arm] += measured[arm] is None
            if any(v is None for v in measured.values()):
                dropped.append([tid, seed])
                continue
            bounds = design["tasks"][tid]["scale_bounds"]
            row = []
            for arm, comparator, endpoint in components(entry):
                diff = measured[arm][endpoint] - measured[comparator][endpoint]
                if endpoint == "regret_auc":
                    diff = -diff
                else:
                    diff /= bounds["high"] - bounds["low"]
                    if bounds["direction"] == "minimize":
                        diff = -diff
                row.append(diff)
            values.append(row)
        blocks[tid] = np.asarray(values, dtype=float).reshape(-1, len(components(entry)))
    planned = len(tasks) * len(seeds)
    report = {"planned_per_arm": planned, "missing_per_arm": missing, "dropped_blocks": dropped,
              "void": any(n / planned > 0.10 for n in missing.values()),
              "complete_per_task": {tid: len(rows) for tid, rows in blocks.items()}}
    return blocks, report


def analyze(design, records, phase="confirmation", entry_ids=None):
    """Compute candidate statistics. Certification is checked separately at the gate.

    With only one supplied entry, retain family size two (alpha .025). The .05
    second Holm step is available only when both entries are recomputed here.
    """
    require_complete(design)
    if design.get("status") == "certified":
        from validation.tier0_inference import require_acceptance_inference

        require_acceptance_inference(design["analysis"])
    if phase not in design["seed_sets"]:
        raise ValueError("Unknown seed phase")
    entries = list(entry_ids or ARMS)
    if not entries or len(set(entries)) != len(entries) or not set(entries) <= set(ARMS):
        raise ValueError("Unknown or duplicate analysis entry")
    if any(r.get("entry") not in entries for r in records):
        raise ValueError("Unexpected entry in raw evidence")
    tests, reports, p_values = {}, {}, {}
    for entry in entries:
        blocks, missing = collect_blocks(design, records, phase, entry)
        reports[entry] = {"missingness": missing, "verdict": "INCONCLUSIVE", "components": {}}
        if missing["void"] or any(len(rows) < 2 for rows in blocks.values()):
            p_values[entry] = 1.0
            continue
        tests[entry] = {}
        for index, (arm, comparator, endpoint) in enumerate(components(entry)):
            key = f"{arm}/{comparator}/{endpoint}"
            clusters = [Cluster(tid, rows[:, index]) for tid, rows in sorted(blocks.items())]
            test = superiority_one_sided(key, clusters, margin=design["margins"][entry][endpoint],
                                         draws=design["analysis"]["bootstrap_draws"],
                                         seed=design["analysis"]["bootstrap_seed"])
            tests[entry][key] = test
        p_values[entry] = max(test.p_value for test in tests[entry].values())
    for decision in holm_bonferroni(p_values, alpha=0.05, family_size=2):
        entry = decision.entry_id
        reports[entry]["family"] = decision.to_dict()
        if entry not in tests:
            continue
        reports[entry]["components"] = {
            key: test.to_dict(decision.adjusted_alpha) for key, test in tests[entry].items()
        }
        clears = decision.reject and all(test.clears(decision.adjusted_alpha) for test in tests[entry].values())
        # Missing power/sizing never becomes a loss or a PASS merely by adding
        # adaptive trials. At the cap, a non-clear remains INCONCLUSIVE.
        reports[entry]["candidate_clears"] = clears
        reports[entry]["verdict"] = "INCONCLUSIVE"
    return {"design_digest": canonical_digest(design), "phase": phase,
            "certifies_acceptance": False, "scientific_status": "INVALIDATED_INFERENCE",
            "entries": reports}
