"""Protected-policy Tier 0 execution and independent artifact recomputation.

Campaign entry requires the whole phase certificate before any write or model
work. Staging functions also support CPU engineering fixtures. Their reports
remain INCONCLUSIVE until the campaign gate validates the actual phase/design.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from hponas.persistence import atomic_json
from validation.tier0_analysis import training_seed
from validation.tier0_bounded_mean import preview_bounded_family
from validation.tier0_design import (
    ACCOUNTING, ARMS, RANK_ANALYSIS, canonical_digest, load_design, require_campaign_ready, study_stream_slot,
    resource_limits,
)
from validation.tier0_protected_evaluation import freeze_incumbent_plan, protected_curve
from validation.tier0_rank_design import rank_components, rank_curve_endpoints


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _path(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError("Missing artifact path")
    root = Path(root).resolve()
    candidate = Path(name)
    candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("Artifact escapes its campaign directory")
    return candidate


def _binding(root, path):
    path = _path(root, str(path))
    return {"path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _read(root, ref, *, parse=True):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Artifact requires an exact path/hash binding")
    path = _path(root, ref["path"])
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("A referenced artifact is missing; integrity failure") from exc
    if not raw or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Changed or empty artifact")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON literal: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant) if parse else path


def _write(root, path, value):
    path = _path(root, str(path))
    if path.exists():
        raise ValueError("Refusing to overwrite frozen campaign evidence")
    canonical_digest(value)  # Refuse NaN/Infinity before persistence.
    atomic_json(path, value)
    return _binding(root, path)


def _key(record):
    return tuple(record.get(field) for field in ("entry", "task", "seed", "arm"))


def _expected(design, entries, phase):
    if (design.get("schema_version") != 2 or design.get("analysis") != RANK_ANALYSIS
            or design.get("claim_contract") != "protected_paired_rank_finite_suite_v1"):
        raise ValueError("Approved rank design contract required")
    if (not entries or len(entries) != len(set(entries)) or not set(entries) <= set(ARMS)
            or phase not in {"pilot", "confirmation"}):
        raise ValueError("Invalid entry family or phase; optional replication is unused")
    expected = []
    for entry in entries:
        count = design.get("selected_counts", {}).get(phase, {}).get(entry)
        seeds = design["seed_sets"][phase]
        tasks = design["entry_tasks"][entry]
        maximum = len(seeds) if phase == "pilot" and design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1" else 20
        if (type(count) is not int or not 5 <= count <= maximum or count > len(seeds)
                or len(set(seeds)) != len(seeds) or not tasks or len(set(tasks)) != len(tasks)):
            raise ValueError("Fixed selected counts and distinct tasks/seeds required")
        expected.extend((entry, task, seed, arm) for task in tasks for seed in seeds[:count] for arm in ARMS[entry])
    return expected


def _pilot_search_futility(design, phase, bad_vectors):
    """Only irretrievable search losses can trigger this pre-test shortcut."""
    from validation.tier0_joint_pilot_sizing import optimistic_pilot_completion
    from validation.tier0_phase_contracts import JOINT_SIZING_POLICY

    if phase != "pilot" or design.get("sizing_policy") != JOINT_SIZING_POLICY:
        return None
    for entry, seeds in bad_vectors.items():
        count = design["selected_counts"]["pilot"][entry]
        if not set(seeds) <= set(design["seed_sets"]["pilot"][:count]):
            raise ValueError("Futility loss is outside the fixed pilot reservation")
        if not seeds:
            continue
        bound = optimistic_pilot_completion(count, len(set(seeds)))
        if bound["futile"]:
            return {"entry": entry, "bad_seeds": sorted(set(seeds)), **bound}
    return None


def _frozen_search_futility(bundle, design, decoded):
    bad = {entry: set() for entry in bundle["entries"]}
    for slot, _, plan in decoded:
        if plan is None or any(plan["unknown_grid"]):
            entry, _, seed, _ = slot["identity"]
            bad[entry].add(seed)
    return _pilot_search_futility(design, bundle["phase"], bad)


def _verify_search(design, record, root, phase):
    """Replay method identity and verify actual bytes before any pickle loading."""
    from validation.tier0_campaign import verify_arm_trace

    if record.get("phase") != phase or record.get("accounting") != ACCOUNTING:
        raise ValueError("Search phase or accounting differs from frozen design")
    plan = freeze_incumbent_plan(design, record, allow_incomplete=True)
    verify_arm_trace(design, record)
    task = design["tasks"][record["task"]]
    for index, observation in enumerate(record["observations"]):
        refs = observation.get("artifact_refs", {})
        if set(refs) != {"checkpoint", "recipe", "learning_curve"}:
            raise ValueError("Every delivered PPO policy requires all three artifacts")
        checkpoint = _read(root, refs["checkpoint"], parse=False)
        recipe, curve = _read(root, refs["recipe"]), _read(root, refs["learning_curve"])
        if _path(root, refs["recipe"]["path"]) != checkpoint.parent / "recipe.json":
            raise ValueError("Checkpoint loader recipe differs from the bound recipe")
        receipt = observation.get("receipt", {})
        metadata = receipt.get("metadata", {})
        expected_config = {**task["fixed_config"], **observation["config"]}
        seed = training_seed(record["rng_stream_slot"], index)
        if (recipe.get("settings") != task["settings"] or recipe.get("training_seed") != seed
                or recipe.get("search_seed") != seed + 100000
                or any(recipe.get("config", {}).get(k) != v for k, v in expected_config.items())
                or metadata.get("training_seed") != seed or metadata.get("search_seed") != seed + 100000
                or metadata.get("settings") != task["settings"] or metadata.get("workload") != "brax_ppo"
                or receipt.get("value") != observation["value"]):
            raise ValueError("Raw PPO receipt/recipe differs from frozen policy")
        for name, ref in refs.items():
            if receipt.get("artifacts", {}).get(name) != ref["path"]:
                raise ValueError("Receipt artifact differs from actual policy binding")
        returns = metadata.get("search_returns", [])
        if (len(returns) != task["settings"]["eval_episodes"] or not all(_finite(x) for x in returns)
                or float(np.mean(returns)) != observation["value"]):
            raise ValueError("Search score differs from all planned raw episodes")
        if (not curve or any(not _finite(point.get("steps")) for point in curve)
                or max(point["steps"] for point in curve) < task["settings"]["max_timesteps"]):
            raise ValueError("Delivered policy lacks full-fidelity training evidence")
    return plan


def freeze_search_bundle(design, root, record_refs, *, entries, phase):
    """Freeze every planned slot and incumbent plan before protected evaluation.

    Absent slots remain explicitly absent. Duplicates and changed artifacts are
    rejected before anything is frozen; unclassified failed traces keep only
    their verified prefix. Engineering callers must not label this a certificate.
    """
    root = Path(root).resolve()
    expected = _expected(design, entries, phase)
    lookup, plans = {}, {}
    for ref in record_refs:
        record = _read(root, ref)
        key = _key(record)
        if key not in expected or key in lookup:
            raise ValueError("Duplicate or unplanned search study")
        plans[key] = _verify_search(design, record, root, phase)
        lookup[key] = ref
    stage = root / "protected-stage"
    stage.mkdir(exist_ok=False)  # A second freeze cannot replace an earlier one.
    design_ref = _write(root, stage / "design.json", design)
    slots = []
    for index, key in enumerate(expected):
        plan_ref = _write(root, stage / f"plan-{index}.json", plans[key]) if key in plans else None
        slots.append({"identity": list(key), "search": lookup.get(key), "plan": plan_ref})
    bundle = {"kind": "frozen-search-and-protected-plan-bundle", "schema_version": 1,
              "design": design_ref, "entries": entries, "phase": phase, "slots": slots,
              "certifies_acceptance": False, "test_scores_available_at_freeze": False}
    return _write(root, stage / "search-freeze.json", bundle)


def _load_bundle(root, bundle_ref):
    bundle = _read(root, bundle_ref)
    if (bundle.get("kind") != "frozen-search-and-protected-plan-bundle" or bundle.get("schema_version") != 1
            or bundle.get("test_scores_available_at_freeze") is not False):
        raise ValueError("Unknown protected search freeze")
    design = _read(root, bundle["design"])
    expected = _expected(design, bundle["entries"], bundle["phase"])
    if [slot["identity"] for slot in bundle["slots"]] != [list(key) for key in expected]:
        raise ValueError("Frozen bundle omits or changes planned slots")
    decoded = []
    for slot in bundle["slots"]:
        if slot["search"] is None:
            if slot["plan"] is not None:
                raise ValueError("A missing search cannot have a selected policy plan")
            decoded.append((slot, None, None))
            continue
        record, plan = _read(root, slot["search"]), _read(root, slot["plan"])
        if list(_key(record)) != slot["identity"] or _verify_search(design, record, root, bundle["phase"]) != plan:
            raise ValueError("Plan cannot be independently reproduced from frozen search")
        decoded.append((slot, record, plan))
    return bundle, design, decoded


def execute_protected_bundle(root, bundle_ref, *, evaluator, clock=time.monotonic, acceptance=False,
                             remaining_total_seconds=None, skip_futile_pilot=False):
    """Evaluate frozen incumbents once, separately timing and retaining failures.

    evaluator(checkpoint, seed) is a trusted local evaluator. Real campaign calls
    set acceptance=True to recheck the exact phase certificate before invoking
    it. Unit fixtures inject an inert evaluator and never claim certification.
    Caps stop new evaluations; in-flight elapsed overshoot is charged and vetoed.
    """
    root = Path(root).resolve()
    bundle, design, decoded = _load_bundle(root, bundle_ref)
    if type(skip_futile_pilot) is not bool:
        raise ValueError("Explicit pilot futility flag required")
    if skip_futile_pilot and _frozen_search_futility(bundle, design, decoded) is None:
        raise ValueError("Frozen search does not establish pilot sizing futility")
    if acceptance:
        require_campaign_ready(design, bundle["phase"])
    entry = bundle["entries"][0] if len(bundle["entries"]) == 1 else None
    cap = resource_limits(design, entry)["protected_cap_seconds"]
    if not _finite(cap) or cap <= 0:
        raise ValueError("Frozen protected evaluation cap required before evaluation")
    if remaining_total_seconds is not None:
        if not _finite(remaining_total_seconds) or remaining_total_seconds < 0:
            raise ValueError("Invalid remaining total time allocation")
        cap = min(cap, remaining_total_seconds)
    for _, record, plan in decoded:
        if plan is not None:
            policy_cap = design["tasks"][record["task"]]["budget"].get("protected_policy_cap_seconds")
            if not _finite(policy_cap) or policy_cap <= 0:
                raise ValueError("Frozen per-policy protected evaluation cap required")
    output = root / "protected-stage" / "evaluations"
    output.mkdir(exist_ok=False)  # No retry/replacement after seeing test outcomes.
    started = clock()
    refs, overshoot = [], False
    for slot_index, (slot, record, plan) in enumerate(decoded):
        if skip_futile_pilot:
            break  # All unexecuted slots remain unknown; no fabricated failures.
        if plan is None:
            continue
        task_cap = design["tasks"][record["task"]]["budget"].get("protected_policy_cap_seconds")
        if not _finite(task_cap) or task_cap <= 0:
            raise ValueError("Frozen per-policy protected evaluation cap required")
        for item in plan["evaluations"]:
            if clock() - started >= cap:
                break
            # Verify all inputs again immediately before the trusted evaluator
            # loads them, including the adjacent recipe used by Brax's loader.
            _read(root, slot["search"])
            observation = record["observations"][item["observation_index"]]
            for name, ref in observation["artifact_refs"].items():
                _read(root, ref, parse=name != "checkpoint")
            checkpoint = _read(root, item["checkpoint"], parse=False)
            before = clock()
            raw = {"observation_index": item["observation_index"], "plan_digest": canonical_digest(plan),
                   "checkpoint_sha256": item["checkpoint"]["sha256"], "seed": item["seed"]}
            _write(root, output / f"{slot_index}-{item['observation_index']}.pending.json", raw)
            try:
                evaluation = evaluator(checkpoint, item["seed"])
            except Exception as exc:
                raw.update(status="evaluation_failed", returns=[None] * item["episodes"],
                           failure=f"{type(exc).__name__}: {exc}")
            else:
                if not isinstance(evaluation, dict):
                    raise ValueError("Malformed protected evaluator output")
                values = evaluation.get("returns")
                if (evaluation.get("seed") != item["seed"] or not isinstance(values, list)
                        or len(values) != item["episodes"]
                        or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)):
                    raise ValueError("Malformed protected evaluator output")
                # JSON never carries NaN/Infinity. Keep their original category
                # per episode and mark them unresolved; no episodes are dropped.
                raw.update(status="complete" if all(_finite(v) for v in values) else "nonfinite_episodes",
                           returns=[v if _finite(v) else None for v in values],
                           episode_statuses=["finite" if _finite(v) else "nan" if math.isnan(v)
                                             else "positive_infinity" if v > 0 else "negative_infinity" for v in values])
            raw["elapsed_seconds"] = clock() - before
            if not _finite(raw["elapsed_seconds"]) or raw["elapsed_seconds"] < 0:
                raise ValueError("Invalid protected evaluation clock")
            overshoot |= raw["elapsed_seconds"] > task_cap
            for name, ref in observation["artifact_refs"].items():
                _read(root, ref, parse=name != "checkpoint")
            protected_curve(plan, [raw])  # Verify slot/seed and all episode fields.
            ref = _write(root, output / f"{slot_index}-{item['observation_index']}.json", raw)
            refs.append({"slot_index": slot_index, "receipt": ref})
    elapsed = clock() - started
    if not _finite(elapsed) or elapsed < 0:
        raise ValueError("Invalid protected stage clock")
    report = {"kind": "protected-evaluation-bundle", "schema_version": 1, "search_freeze": bundle_ref,
              "receipts": refs, "elapsed_seconds": elapsed, "effective_cap_seconds": cap,
              "cap_exceeded": overshoot or elapsed > cap,
              "skipped_for_pilot_search_futility": skip_futile_pilot,
              "certifies_acceptance": False}
    return _write(root, output / "manifest.json", report)


def recompute_protected(root, bundle_ref, evaluations_ref):
    """Independent endpoint/family recomputation; every planned vector retained."""
    bundle, design, decoded = _load_bundle(root, bundle_ref)
    evaluation = _read(root, evaluations_ref)
    if (evaluation.get("kind") != "protected-evaluation-bundle" or evaluation.get("schema_version") != 1
            or evaluation.get("search_freeze") != bundle_ref):
        raise ValueError("Test evidence belongs to another frozen search")
    skipped = evaluation.get("skipped_for_pilot_search_futility", False)
    if (type(skipped) is not bool or (skipped and (evaluation["receipts"]
            or _frozen_search_futility(bundle, design, decoded) is None))):
        raise ValueError("Protected skip lacks independently reconstructed pilot futility")
    grouped, seen, policy_seconds = {}, set(), 0.0
    cap_exceeded = False
    for row in evaluation["receipts"]:
        slot_index = row["slot_index"]
        if type(slot_index) is not int or not 0 <= slot_index < len(decoded) or decoded[slot_index][2] is None:
            raise ValueError("Protected receipt has no planned search slot")
        receipt = _read(root, row["receipt"])
        key = slot_index, receipt["observation_index"]
        if key in seen:
            raise ValueError("Duplicate protected policy receipt")
        seen.add(key)
        elapsed = receipt.get("elapsed_seconds")
        if not _finite(elapsed) or elapsed < 0:
            raise ValueError("Invalid protected policy elapsed time")
        status, values = receipt.get("status"), receipt.get("returns", [])
        if status == "complete":
            if not all(_finite(v) for v in values) or receipt.get("episode_statuses") != ["finite"] * len(values):
                raise ValueError("Complete protected receipt contains unresolved episodes")
        elif status == "evaluation_failed":
            if any(v is not None for v in values) or not receipt.get("failure"):
                raise ValueError("Failed protected receipt has inconsistent outcomes")
        elif status == "nonfinite_episodes":
            labels = receipt.get("episode_statuses", [])
            if (len(labels) != len(values) or not any(v is None for v in values)
                    or any(v is not None and not _finite(v) for v in values)
                    or any((label != "finite" if _finite(v) else
                            label not in {"nan", "positive_infinity", "negative_infinity"})
                           for v, label in zip(values, labels))):
                raise ValueError("Nonfinite protected episode categories are inconsistent")
        else:
            raise ValueError("Unknown protected receipt status")
        task = decoded[slot_index][1]["task"]
        cap_exceeded |= elapsed > design["tasks"][task]["budget"]["protected_policy_cap_seconds"]
        policy_seconds += elapsed
        grouped.setdefault(slot_index, []).append(receipt)
    total = evaluation.get("elapsed_seconds")
    if not _finite(total) or total < policy_seconds - 1e-9:
        raise ValueError("Protected accounting omits measured evaluation cost")
    cap = evaluation.get("effective_cap_seconds")
    entry = bundle["entries"][0] if len(bundle["entries"]) == 1 else None
    if not _finite(cap) or not 0 <= cap <= resource_limits(design, entry)["protected_cap_seconds"]:
        raise ValueError("Protected cap exceeds frozen allocation")
    cap_exceeded |= total > cap
    if evaluation.get("cap_exceeded") is not cap_exceeded:
        raise ValueError("Protected budget verdict differs from recomputed accounting")
    curves, failures, search_seconds, search_overshoot = {}, {}, 0.0, False
    raw_reports = []
    for slot_index, (slot, record, plan) in enumerate(decoded):
        key = tuple(slot["identity"])
        curve = [None] * len(design["budget_grid"]) if plan is None else protected_curve(plan, grouped.get(slot_index, []))
        curves[key] = curve
        unresolved = any(value is None for value in curve)
        failures[key] = unresolved
        if record is not None:
            task = design["tasks"][record["task"]]
            search_seconds += record["elapsed_seconds"]
            search_overshoot |= record["elapsed_seconds"] > task["budget"]["seconds"] + task["budget"]["max_overshoot_seconds"]
        raw_reports.append({"identity": list(key), "protected_curve": curve,
                            "search_values": [] if record is None else [r["value"] for r in record["observations"]],
                            "search_status": "absent" if record is None else record["status"],
                            "search_failure": None if record is None else record.get("failure"),
                            "protected_statuses": [r["status"] for r in grouped.get(slot_index, [])],
                            "unresolved": unresolved})
    lower, upper, counts = {}, {}, {}
    for entry in bundle["entries"]:
        tasks = design["entry_tasks"][entry]
        seeds = design["seed_sets"][bundle["phase"]][:design["selected_counts"][bundle["phase"]][entry]]
        low_rows, high_rows = [], []
        for seed in seeds:
            task_intervals = []
            for task in tasks:
                pairs = {(arm, baseline): rank_curve_endpoints(curves[entry, task, seed, arm],
                         curves[entry, task, seed, baseline], design["budget_grid"])
                         for arm, baseline, _ in rank_components(entry)}
                task_intervals.append([pairs[arm, baseline][endpoint] for arm, baseline, endpoint in rank_components(entry)])
            averages = [[math.fsum(row[j][i] for row in task_intervals) / len(tasks)
                         for j in range(len(rank_components(entry)))] for i in (0, 1)]
            low_rows.append(averages[0])
            high_rows.append(averages[1])
        lower[entry], upper[entry] = low_rows, high_rows
        losses = {arm: sum(failures[entry, task, seed, arm] for task in tasks for seed in seeds) for arm in ARMS[entry]}
        planned = len(tasks) * len(seeds)
        counts[entry] = {"independent_vectors": len(seeds), "tasks": len(tasks), "planned_studies_per_arm": planned,
                         "unresolved_per_arm": losses, "loss_cap_void": any(n / planned > .1 for n in losses.values())}
    # An operationally void entry cannot unlock Holm's second step for another.
    statistics = {entry: np.full_like(values, -1.0) if counts[entry]["loss_cap_void"] else values
                  for entry, values in lower.items()}
    report = preview_bounded_family(statistics)
    for entry, result in report["entries"].items():
        result["components"] = {"/".join(key): value for key, value in
                                zip(rank_components(entry), result["components"].values(), strict=True)}
        result.update(counts=counts[entry], lower_rows=lower[entry], upper_rows=upper[entry],
                      identified_mean_intervals=list(zip(np.mean(lower[entry], axis=0).tolist(), np.mean(upper[entry], axis=0).tolist())))
    report.update(scientific_status="ADOPTED_RANK_ARTIFACT_RECOMPUTATION_PHASE_UNCERTIFIED",
                  phase=bundle["phase"], design_digest=canonical_digest(design),
                  scope="conditional_named_finite_suite", raw_study_outcomes=raw_reports,
                  budget_veto=bool(cap_exceeded or search_overshoot),
                  stopping="One fixed-count analysis; missing slots retained; no optional replication",
                  protected_evaluation_scope="Noisy protected episode scores of search-selected policies; no raw-return mean claim",
                  cost={"search_elapsed_seconds": search_seconds, "protected_elapsed_seconds": total,
                        "protected_policy_seconds": policy_seconds,
                        "combined_measured_seconds": search_seconds + total})
    return report


def campaign(validation_id, run_dir, *, design_path, phase="confirmation"):
    """Certified single-entry campaign; both raw bundles can be jointly analyzed later."""
    from tools.source_identity import source_digest
    from validation.tier0_isolation import run_isolated
    design = load_design(design_path)
    require_campaign_ready(design, phase)  # Before directories, model work or evaluation.
    limits = resource_limits(design, validation_id)
    expected = _expected(design, [validation_id], phase)
    root = Path(run_dir).resolve()
    if design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1":
        from validation.tier0_phase_contracts import campaign_directory
        from tools.source_identity import ROOT

        if root != campaign_directory(design, phase, validation_id, ROOT):
            raise ValueError("Campaign must use its prespecified single-use directory")
    root.mkdir(parents=True, exist_ok=True)
    fingerprint, started = source_digest(), time.monotonic()
    launch_ref = None
    if design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1":
        launch_ref = _write(root, root / "phase-launch.json", {
            "kind": "prospective_phase_launch_v1", "phase": phase, "design_digest": canonical_digest(design),
            "source_digest": fingerprint, "monotonic_ns": time.monotonic_ns(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "phase_freeze": design["phase_freeze"]})
    refs, process_refs = [], []
    bad_vectors, futility = {validation_id: set()}, None
    for task in design["entry_tasks"][validation_id]:
        if futility is not None:
            break
        count = design["selected_counts"][phase][validation_id]
        for index, seed in enumerate(design["seed_sets"][phase][:count]):
            if futility is not None:
                break
            arms = ARMS[validation_id]
            offset = index % len(arms)
            for arm in arms[offset:] + arms[:offset]:
                if time.monotonic() - started >= limits["campaign_cap_seconds"]:
                    break
                prefix = f"{validation_id}_{task}_{seed}_{arm}"
                _write(root, root / f"{prefix}.pending.json", {"identity": [validation_id, task, seed, arm],
                       "design_digest": canonical_digest(design), "status": "started"})
                remaining = limits["campaign_cap_seconds"] - (time.monotonic() - started)
                if remaining <= 0:
                    break
                budget = design["tasks"][task]["budget"]
                # Bound the whole child, including interpreter/readiness work.
                # A stalled study must not inherit the entire campaign window.
                child_cap = budget["seconds"] + budget["max_overshoot_seconds"]
                process_ref, process_report = run_isolated(root, f"search-{len(process_refs)}", {
                    "operation": "search", "design": design, "entry": validation_id, "task": task,
                    "seed": seed, "arm": arm, "phase": phase}, timeout_seconds=min(remaining, child_cap))
                process_refs.append(process_ref)
                if process_report["status"] == "complete":
                    record = process_report["output"]
                    refs.append(_write(root, root / f"{prefix}.json", record))
                    # A failed trace can retain a verified prefix. Only a
                    # genuinely unresolved suffix makes this vector bad.
                    if any(freeze_incumbent_plan(design, record, allow_incomplete=True)["unknown_grid"]):
                        bad_vectors[validation_id].add(seed)
                else:
                    bad_vectors[validation_id].add(seed)
                futility = _pilot_search_futility(design, phase, bad_vectors)
                if futility is not None:
                    break
    frozen = freeze_search_bundle(design, root, refs, entries=[validation_id], phase=phase)
    freeze_ns = time.monotonic_ns()
    policy_caps = {}
    for slot in _read(root, frozen)["slots"]:
        if slot["plan"] is None:
            continue
        plan = _read(root, slot["plan"])
        cap = design["tasks"][plan["task"]]["budget"]["protected_policy_cap_seconds"]
        for item in plan["evaluations"]:
            key = (item["checkpoint"]["path"], item["checkpoint"]["sha256"], item["seed"])
            if key in policy_caps:
                raise ValueError("Duplicate protected policy/seed allocation")
            policy_caps[key] = cap

    def isolated_evaluator(checkpoint, seed):
        remaining = limits["campaign_cap_seconds"] - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Campaign allocation exhausted before protected launch")
        reference = _binding(root, checkpoint)
        cap = policy_caps[(reference["path"], reference["sha256"], seed)]
        process_ref, process_report = run_isolated(root, f"protected-{len(process_refs)}", {
            "operation": "protected", "root": str(root), "search_freeze": frozen,
            "checkpoint": reference, "seed": seed}, timeout_seconds=min(remaining, cap))
        process_refs.append(process_ref)
        if process_report["status"] != "complete":
            raise RuntimeError(f"Protected child {process_report['status']}; raw process record retained")
        return process_report["output"]

    evaluated = execute_protected_bundle(root, frozen, evaluator=isolated_evaluator, acceptance=True,
                                        remaining_total_seconds=max(0, limits["campaign_cap_seconds"]
                                                                    - (time.monotonic() - started)),
                                        skip_futile_pilot=futility is not None)
    isolation = _write(root, root / "process-isolation.json", {
        "kind": "rank_campaign_process_sequence_v1", "source_digest": fingerprint,
        "search_freeze": frozen, "freeze_ns": freeze_ns, "processes": process_refs,
        "phase_launch": launch_ref})
    verify_campaign_isolation(root, frozen, evaluated, isolation, fingerprint)
    report = recompute_protected(root, frozen, evaluated)
    duration = time.monotonic() - started
    if source_digest() != fingerprint:
        raise ValueError("Source changed during the campaign")
    return {"validation_id": validation_id, "schema_version": 3, "claim": "protected_paired_rank_finite_suite_v1",
            "source_digest": fingerprint, "phase": phase, "run_dir": str(root), "search_freeze": frozen,
            "protected_evaluations": evaluated, "planned_studies": len(expected), "duration_seconds": duration,
            "process_isolation": isolation,
            "pilot_search_futility": futility,
            "budget_veto": report["budget_veto"] or duration > limits["campaign_cap_seconds"],
            "certifies_acceptance": False, "verdict": "INCONCLUSIVE"}


def verify_campaign_isolation(root, frozen, evaluated, isolation, fingerprint):
    """Bind each scientific record to one fresh child and enforce stage order."""
    from validation.tier0_isolation import verify_sequence

    root = Path(root).resolve()
    manifest = _read(root, isolation)
    if (manifest.get("kind") != "rank_campaign_process_sequence_v1"
            or manifest["source_digest"] != fingerprint or manifest["search_freeze"] != frozen
            or type(manifest["freeze_ns"]) is not int):
        raise ValueError("Process sequence differs from frozen campaign")
    bundle, design, decoded = _load_bundle(root, frozen)
    expected = {tuple(slot["identity"]): record for slot, record, _ in decoded}
    evaluations = _read(root, evaluated)
    protected, policy_caps = {}, {}
    for row in evaluations["receipts"]:
        receipt = _read(root, row["receipt"])
        plan = decoded[row["slot_index"]][2]
        item = next(item for item in plan["evaluations"] if item["observation_index"] == receipt["observation_index"])
        key = (item["checkpoint"]["path"], item["checkpoint"]["sha256"], item["seed"])
        if key in protected:
            raise ValueError("Duplicate protected process output")
        protected[key] = receipt
        policy_caps[key] = design["tasks"][plan["task"]]["budget"]["protected_policy_cap_seconds"]
    seen_search, seen_protected = set(), set()
    reports = verify_sequence(root, manifest["processes"], expected_source=fingerprint)
    if design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1":
        from validation.tier0_phase_contracts import verify_phase_launch
        from tools.source_identity import ROOT

        launch = _read(root, manifest.get("phase_launch"))
        verify_phase_launch(launch, design, bundle["phase"], manifest["freeze_ns"], reports, ROOT)
    for report in reports:
        payload = report["payload"]
        if payload["operation"] == "search":
            key = tuple(payload.get(k) for k in ("entry", "task", "seed", "arm"))
            if (key not in expected or key in seen_search or payload.get("design") != design
                    or payload.get("phase") != bundle["phase"] or report["finish_ns"] > manifest["freeze_ns"]):
                raise ValueError("Search job input, repetition or stage order differs")
            budget = design["tasks"][key[1]]["budget"]
            timeout = report.get("timeout_seconds")
            if not _finite(timeout) or not 0 < timeout <= budget["seconds"] + budget["max_overshoot_seconds"]:
                raise ValueError("Search process timeout exceeds its frozen study allowance")
            seen_search.add(key)
            if (report["output"] if report["status"] == "complete" else None) != expected[key]:
                raise ValueError("Search artifact differs from child output")
            if expected[key] is not None and expected[key]["elapsed_seconds"] > report["elapsed_seconds"] + 1e-9:
                raise ValueError("Search clock exceeds observed child lifetime")
        elif payload["operation"] == "protected":
            key = (payload["checkpoint"]["path"], payload["checkpoint"]["sha256"], payload["seed"])
            if (key not in protected or key in seen_protected or payload.get("search_freeze") != frozen
                    or payload.get("root") != str(root) or report["launch_ns"] < manifest["freeze_ns"]):
                raise ValueError("Protected job input, repetition or stage order differs")
            timeout = report.get("timeout_seconds")
            if not _finite(timeout) or not 0 < timeout <= policy_caps[key]:
                raise ValueError("Protected process timeout exceeds its frozen policy allowance")
            seen_protected.add(key)
            receipt = protected[key]
            if receipt["elapsed_seconds"] < report["elapsed_seconds"] - 1e-9:
                raise ValueError("Protected accounting omits child process time")
            if report["status"] == "complete":
                output = report["output"]
                if receipt["returns"] != output.get("returns") or receipt["seed"] != output.get("seed"):
                    raise ValueError("Protected receipt differs from child returns")
            elif receipt["status"] != "evaluation_failed":
                raise ValueError("Interrupted protected child supplied a resolved outcome")
        else:
            raise ValueError("Engineering probes cannot supply scientific evidence")
    if any(record is not None and key not in seen_search for key, record in expected.items()):
        raise ValueError("Search result lacks a child process")
    if any(key not in seen_protected and receipt["status"] != "evaluation_failed"
           for key, receipt in protected.items()):
        raise ValueError("Protected result lacks a child process")
    return {"jobs_verified": len(reports), "fresh_process_records": True,
            "search_precedes_protected": True, "certifies_independence": False,
            "measured_process_seconds": math.fsum(item["elapsed_seconds"] for item in reports),
            "process_span_seconds": 0.0 if not reports else (reports[-1]["finish_ns"] - reports[0]["launch_ns"]) / 1e9}


def recompute_result(validation_id, result):
    """Acceptance gate ignores supplied decision fields and rechecks every input."""
    from tools.source_identity import ROOT, source_digest

    if (result.get("schema_version") != 3 or result.get("validation_id") != validation_id
            or result.get("claim") != "protected_paired_rank_finite_suite_v1"):
        raise ValueError("Unknown rank campaign identity")
    root = Path(result["run_dir"]).resolve()
    if root.parent != (ROOT / "validation/artifacts" / validation_id).resolve():
        raise ValueError("Rank evidence is not in its audited campaign directory")
    bundle, design, _ = _load_bundle(root, result["search_freeze"])
    if design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1":
        from validation.tier0_phase_contracts import campaign_directory

        if root != campaign_directory(design, result.get("phase"), validation_id, ROOT):
            raise ValueError("Evidence is from an unscheduled campaign attempt")
    if bundle["entries"] != [validation_id] or bundle["phase"] != result.get("phase"):
        raise ValueError("Entry/phase differs from frozen search")
    require_campaign_ready(design, result["phase"])
    if result.get("source_digest") != source_digest():
        return "INCONCLUSIVE"
    isolation = verify_campaign_isolation(root, result["search_freeze"], result["protected_evaluations"],
                                          result.get("process_isolation"), result["source_digest"])
    report = recompute_protected(root, result["search_freeze"], result["protected_evaluations"])
    duration = result.get("duration_seconds")
    if (not _finite(duration) or duration < report["cost"]["combined_measured_seconds"] - 1e-9
            or duration < isolation["process_span_seconds"] - 1e-9
            or result.get("planned_studies") != len(bundle["slots"])):
        raise ValueError("Invalid full campaign accounting")
    entry = report["entries"][validation_id]
    if (result["phase"] == "pilot" or report["budget_veto"] or entry["counts"]["loss_cap_void"]
            or duration > resource_limits(design, validation_id)["campaign_cap_seconds"]):
        return "INCONCLUSIVE"
    return "PASS" if entry["candidate_clears"] else "INCONCLUSIVE"
