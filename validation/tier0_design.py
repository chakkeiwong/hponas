"""Versioned candidate contracts for the accepted V04-T0/V05 identities.

Scientific readiness is deliberately separate from spending permission. This module performs
no workload evaluation and never fills scientific inputs from observed results.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESIGN = ROOT / "validation/designs/tier0_candidate_v2_2.json"
ARMS = {
    "V04-T0": ["gp_log", "tpe_log", "sobol_log", "random_log"],
    "V05": ["gp_log", "gp_linear"],
}
ENDPOINTS = {
    "V04-T0": ["final_objective", "regret_auc"],
    "V05": ["final_objective"],
}
RANK_ENDPOINTS = {"V04-T0": ["final_win", "anytime_win"], "V05": ["final_win"]}
RANK_ANALYSIS = {"method": "fixed_count_bounded_mean_mixture_e_v1", "unit": "complete_seed_vector",
                 "mixture": "uniform_0_1", "count": "fixed", "missingness": "coordinatewise_lower_bounds",
                 "power_target": 0.8, "max_sample": 20}
PROTECTED_EVALUATION = {"selection": "search_score_only_earliest_tie_no_future_observations",
                        "seed_policy": "study_slot_offsets_10000_to_99999",
                        "all_search_frozen_before_test": True, "reuse_same_selected_policy": True,
                        "cost": "separate_measured_elapsed_seconds", "feeds_searcher": False}
PHASES = ("pilot", "confirmation", "replication")
ACCOUNTING = "sequential_elapsed_seconds_including_optimizer"
STREAM_POLICY = "task_offset_20_slots_per_phase_v1"


def canonical_digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def load_design(path=DEFAULT_DESIGN):
    return json.loads(Path(path).read_text())


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def resource_limits(design, entry=None):
    """Return one entry's frozen limits, retaining legacy scalar-cap semantics.

    Explicit per-entry caps are supported by rank campaigns only. They cannot
    be pooled across entries or combined with a second scalar interpretation.
    """
    resource = design.get("resource", {})
    if "entry_caps" not in resource:
        return {key: resource.get(key) for key in ("campaign_cap_seconds", "protected_cap_seconds")}
    if design.get("schema_version") != 2:
        raise ValueError("Per-entry resource caps require the protected-rank design")
    fields = {"campaign_cap_seconds", "protected_cap_seconds"}
    caps = resource["entry_caps"]
    if (fields.intersection(resource) or not isinstance(caps, dict) or set(caps) != set(ARMS)):
        raise ValueError("Exact per-entry resource caps cannot mix with shared scalar caps")
    for limits in caps.values():
        if (not isinstance(limits, dict) or set(limits) != fields
                or any(not _finite(v) or v <= 0 for v in limits.values())
                or limits["protected_cap_seconds"] > limits["campaign_cap_seconds"]):
            raise ValueError("Each entry requires finite positive protected and total caps")
    if entry not in caps:
        raise ValueError("Per-entry resource caps require one exact campaign entry; pooling is refused")
    return dict(caps[entry])


def study_stream_slot(design, task_id, block_seed):
    """Disjoint task/study namespaces, shared only by deliberately paired arms.

    The logical block seed remains the pairing ID. Each pinned task index
    reserves twenty additional slots in every phase; design_errors checks the
    complete allocation for collisions, including adversarial seed sets.
    Disjoint seeds support the PRNG stream model, not task-population sampling.
    """
    if design.get("random_stream_policy") != STREAM_POLICY:
        raise ValueError("Unknown or missing task/study random stream policy")
    if task_id not in design.get("tasks", {}):
        raise ValueError("Unknown random stream task")
    index = design["tasks"][task_id].get("stream_task_index")
    if type(index) is not int or index < 0:
        raise ValueError("Invalid random stream task index")
    if type(block_seed) is not int or not any(isinstance(seeds, list) and block_seed in seeds
                                            for seeds in design.get("seed_sets", {}).values()):
        raise ValueError("Unknown random stream block seed")
    slot = block_seed + 20 * index
    if not 0 <= slot < 32768:
        raise ValueError("Random stream namespace exceeds uint32 evaluation-seed allocation")
    return slot


def design_errors(design, *, check_files=True, phase=None):
    """Return every missing freeze input; a candidate can be inspected while incomplete."""
    errors = []
    requested_phase = phase
    if phase not in (None, "pilot", "confirmation", "replication"):
        return ["Unknown scientific design phase; profiling uses its own development contract"]

    def require(condition, message):
        if not condition:
            errors.append(message)

    rank = design.get("schema_version") == 2
    endpoints = RANK_ENDPOINTS if rank else ENDPOINTS
    require(design.get("schema_version") in (1, 2) and design.get("kind") == "tier0-comparison-design",
            "Unknown Tier 0 design schema")
    require(design.get("arms") == ARMS, "Arm identities must match D-T0-CLAIMS")
    require(design.get("endpoints") == endpoints, "All decision-bearing endpoints are required")
    require(design.get("accounting") == ACCOUNTING, "Unknown measured-budget accounting")
    require(design.get("initialization") == "shared_frozen_physical_v05_charged_to_each_arm",
            "V05 requires frozen physical initialization charged to both arms")
    require(design.get("auc_rule") == ("left_rectangle_paired_win_on_fixed_grid" if rank else
                                      "left_rectangle_on_fixed_grid_no_future_observations"),
            "Unknown regret AUC rule")
    require(design.get("missingness") == ("retain_all_planned_vectors_lower_bounds_void_above_10pct_unresolved_per_arm"
                                         if rank else "exclude_whole_paired_block_void_above_10pct_per_arm"),
            "Missingness rule differs from register")
    require(design.get("family") == {"members": ["V04-T0", "V05"], "alpha": 0.05,
                                    "combination": "intersection_union_then_holm"},
            "Tier 0 family/combination differs from candidate contract")
    require(design.get("analysis") == (RANK_ANALYSIS if rank else {"bootstrap_draws": 10000, "bootstrap_seed": 94029,
                                      "sizing_replicates": 2000, "power_target": 0.8,
                                      "variance_confidence": 0.8, "max_sample": 20}),
            "Analysis controls differ from candidate contract")
    if rank:
        require(design.get("claim_contract") == "protected_paired_rank_finite_suite_v1"
                and design.get("scope") == "conditional_named_finite_suite", "Approved rank/scope contract missing")
        require(design.get("protected_evaluation") == PROTECTED_EVALUATION, "Protected evaluation contract missing")
        require(design.get("stopping") == {"confirmation": "one_fixed_count", "replication": "unused"},
                "Rank design permits only one fixed-count confirmation")
        sampling = design.get("sampling", {})
        require(sampling.get("unit") == "complete_seed_vector" and sampling.get("task_weights") == "equal",
                "Equal task weights and complete seed-vector units required")
        from validation.tier0_objectivity import sampling_errors

        errors.extend(sampling_errors(design, ROOT, check_files=check_files))
        from validation.tier0_phase_contracts import execution_environment_errors

        errors.extend(execution_environment_errors(design, check_files=check_files))
        for name, ref in [("outcome approval", design.get("outcome_approval"))]:
            ref = ref or {}
            require(bool(ref.get("path")) and _sha(ref.get("sha256")), f"Bound {name} missing")
            if check_files and ref.get("path"):
                path = Path(ref["path"])
                path = path if path.is_absolute() else ROOT / path
                require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ref.get("sha256"),
                        f"Changed {name}")
    grid = design.get("budget_grid", [])
    require(len(grid) >= 2 and all(_finite(x) for x in grid)
            and grid[0] == 0 and grid[-1] == 1
            and all(a < b for a, b in zip(grid, grid[1:])), "Budget grid must increase from 0 to 1")
    require(design.get("gp_options") == {"initial_random_samples": 5, "num_restarts": 10,
                                         "kernel": "matern52"}, "GP recipe must be frozen")
    sets = design.get("seed_sets", {})
    pools = []
    for phase in PHASES:
        seeds = sets.get(phase, [])
        valid = isinstance(seeds, list) and all(type(s) is int and 0 <= s < 32768 for s in seeds)
        require(valid, f"{phase}: invalid seed set")
        if not valid:
            seeds = []
        require(len(seeds) == len(set(seeds)), f"{phase}: duplicate optimizer seeds")
        prospective_pilot = (phase == "pilot" and design.get("sampling", {}).get("selection_algorithm")
                             == "prospective_named_suite_local_v1")
        maximum = 32768 if prospective_pilot else 20
        require(5 <= len(seeds) <= maximum, f"{phase}: requires 5..{maximum} prespecified seed slots")
        pools.append(set(seeds))
    require(all(not a & b for i, a in enumerate(pools) for b in pools[i + 1:]),
            "Pilot, confirmation and replication seeds must be disjoint")
    tasks = design.get("tasks", {})
    require(isinstance(tasks, dict) and bool(tasks), "Acceptance task catalog is empty")
    require(design.get("random_stream_policy") == STREAM_POLICY, "Task/study random stream policy missing")
    slots = []
    for tid in tasks:
        for pool in pools:
            for seed in pool:
                try:
                    slots.append(study_stream_slot(design, tid, seed))
                except ValueError as exc:
                    require(False, f"{tid}: {exc}")
    require(len(slots) == len(set(slots)), "Task/study random stream namespaces collide")
    for entry in ARMS:
        ids = design.get("entry_tasks", {}).get(entry, [])
        require(bool(ids) and len(ids) == len(set(ids)) and all(t in tasks for t in ids),
                f"{entry}: missing/duplicate/unknown tasks")
        clusters = [tasks[t].get("cluster_id") for t in ids if t in tasks]
        if not rank:
            require(len(clusters) >= 2 and all(clusters) and len(clusters) == len(set(clusters)),
                    f"{entry}: requires distinct independent task clusters")
        require(any(tasks[t].get("adapter") == "brax_ppo" for t in ids if t in tasks),
                f"{entry}: real PPO must remain in the acceptance set")
        for endpoint in endpoints[entry]:
            margin = design.get("margins", {}).get(entry, {}).get(endpoint)
            require(_finite(margin) and margin >= 0, f"{entry}/{endpoint}: missing normalized threshold")
            if rank:
                require(margin == 0 and not isinstance(margin, bool), f"{entry}/{endpoint}: rank margin must be zero")
            effect = design.get("planning_effects", {}).get(entry, {}).get(endpoint)
            # The prospective rank rule derives alternatives from an independent
            # pilot. Legacy designs still require their explicit alternatives.
            if not rank or requested_phase is None:
                require(_finite(effect) and _finite(margin) and effect > margin,
                        f"{entry}/{endpoint}: prespecified planning alternative must exceed threshold")
    for tid, task in tasks.items():
        if rank:
            require(task.get("role") == "acceptance", f"{tid}: held-out acceptance role missing")
        else:
            require(bool(task.get("independence_basis")), f"{tid}: independence basis missing")
        require(task.get("adapter") == "brax_ppo", f"{tid}: no executable acceptance task adapter")
        require(bool(task.get("version")), f"{tid}: task version missing")
        require(_sha(task.get("data_sha256")), f"{tid}: dataset/environment artifact hash missing")
        require(bool(task.get("provenance")), f"{tid}: provenance missing")
        assets = task.get("data_artifacts", [])
        require(bool(assets), f"{tid}: environment/data artifacts missing")
        for asset in assets:
            require(_sha(asset.get("sha256")) and bool(asset.get("path")), f"{tid}: invalid data artifact")
            if check_files and asset.get("path"):
                path = Path(asset["path"])
                path = path if path.is_absolute() else ROOT / path
                require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == asset.get("sha256"),
                        f"{tid}: changed environment/data artifact")
        if assets:
            require(task.get("data_sha256") == canonical_digest(assets), f"{tid}: environment/data digest mismatch")
        require(bool(task.get("settings")) and bool(task.get("fixed_config")), f"{tid}: task execution recipe missing")
        if task.get("settings"):
            expected_settings = {"environment", "backend", "max_timesteps", "episode_length", "eval_episodes",
                                 "num_evals", "unroll_length", "num_minibatches", "num_updates_per_batch"}
            require(set(task["settings"]) == expected_settings, f"{tid}: complete RLSettings recipe required")
            for key in expected_settings - {"environment", "backend"}:
                value = task["settings"].get(key)
                require(type(value) is int and value > 0, f"{tid}: invalid task setting {key}")
        if rank:
            require(task.get("objective_direction") == "maximize", f"{tid}: rank PPO requires maximized search return")
            require(not {"scale_bounds", "regret_reference", "initial_objective"} & set(task),
                    f"{tid}: legacy raw-return normalization is not the rank contract")
        else:
            bounds = task.get("scale_bounds", {})
            low, high = bounds.get("low"), bounds.get("high")
            require(_finite(low) and _finite(high) and high > low, f"{tid}: finite scale bounds missing")
            require(bounds.get("direction") in {"maximize", "minimize"}, f"{tid}: direction missing")
            require(_finite(task.get("regret_reference")), f"{tid}: regret reference missing")
            require(_finite(task.get("initial_objective")), f"{tid}: pre-observation objective missing")
        budget = task.get("budget", {})
        require(_finite(budget.get("seconds")) and budget["seconds"] > 0, f"{tid}: measured budget missing")
        require(_finite(budget.get("max_overshoot_seconds")) and budget["max_overshoot_seconds"] >= 0,
                f"{tid}: allowed overshoot missing")
        limit = budget.get("trial_limit")
        require(type(limit) is int and 5 < limit < 10000, f"{tid}: trial safety limit missing")
        if rank:
            episodes = task.get("settings", {}).get("eval_episodes")
            require(type(limit) is int and type(episodes) is int and limit * episodes <= 90000,
                    f"{tid}: protected episode reservation overflows")
            require(_finite(budget.get("protected_policy_cap_seconds")) and budget["protected_policy_cap_seconds"] > 0,
                    f"{tid}: protected policy evaluation cap missing")
        domain = task.get("space", [])
        names = [k.get("name") for k in domain]
        require(bool(domain) and all(names) and len(names) == len(set(names)), f"{tid}: physical domain missing")
        for knob in domain:
            values = knob.get("bounds", [])
            valid = len(values) == 2 and all(_finite(x) for x in values) and values[1] > values[0]
            require(valid and knob.get("kind") in {"continuous", "ordinal"}
                    and knob.get("transform") in {"none", "log"}, f"{tid}: invalid physical knob")
            if knob.get("transform") == "log":
                require(valid and values[0] > 0, f"{tid}: log knob requires positive bounds")
            if knob.get("kind") == "ordinal":
                require(valid and all(type(v) is int for v in values), f"{tid}: ordinal bounds require integers")
        require(not set(task.get("fixed_config", {})) & set(names), f"{tid}: fixed configuration overlaps search knobs")
        if tid in design.get("entry_tasks", {}).get("V05", []):
            require(any(k.get("transform") == "log" for k in domain), f"{tid}: V05 needs a scale-sensitive knob")
            frozen = task.get("initial_configs", {})
            for phase in PHASES:
                for seed in sets.get(phase, []):
                    configs = frozen.get(str(seed), [])
                    require(len(configs) == 5, f"{tid}/{seed}: five frozen physical configurations required")
                    for config in configs:
                        require(valid_config(task, config), f"{tid}/{seed}: initial configuration outside domain")
        artifact = task.get("artifact", {})
        require(_sha(artifact.get("sha256")) and bool(artifact.get("path")), f"{tid}: bound task artifact missing")
        if check_files and artifact.get("path"):
            path = Path(artifact["path"])
            path = path if path.is_absolute() else ROOT / path
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == artifact.get("sha256"),
                    f"{tid}: task artifact differs from frozen hash")
    resource = design.get("resource", {})
    require(resource.get("workers") == 1, "Candidate requires one sequential worker per arm")
    require(bool(resource.get("allocation_id")) and bool(resource.get("owner")), "Resource allocation/owner missing")
    if "entry_caps" in resource:
        try:
            for entry in ARMS:
                resource_limits(design, entry)
        except ValueError as exc:
            errors.append(str(exc))
    else:
        require(_finite(resource.get("campaign_cap_seconds")) and resource["campaign_cap_seconds"] > 0,
                "Aggregate campaign cap missing")
        if rank:
            require(_finite(resource.get("protected_cap_seconds")) and resource["protected_cap_seconds"] > 0,
                    "Protected evaluation allocation cap missing")
    require(bool(design.get("dependencies")), "Pinned dependency versions missing")
    required_packages = {"numpy", "scipy", "torch", "botorch", "gpytorch", "optuna", "jax", "jaxlib", "brax"}
    require(required_packages <= set(design.get("dependencies", {})), "Required task/searcher dependencies are not pinned")
    require(all(isinstance(v, str) and bool(v) for v in design.get("dependencies", {}).values()),
            "Invalid pinned dependency version")
    return errors


def valid_config(task, config):
    if set(config) != {k["name"] for k in task["space"]}:
        return False
    for knob in task["space"]:
        value = config[knob["name"]]
        if not _finite(value) or not knob["bounds"][0] <= value <= knob["bounds"][1]:
            return False
        if knob["kind"] == "ordinal" and int(value) != value:
            return False
    return True


def require_complete(design, *, check_files=True, phase=None):
    errors = design_errors(design, check_files=check_files, phase=phase)
    if errors:
        raise ValueError("Incomplete Tier 0 design: " + "; ".join(errors))


def require_confirmation_sizing(design, phase):
    """Prevent legacy bootstrap or conditional sensitivity from sizing rank runs.

    A rank receipt is reconstructed from bound pilot artifacts and the frozen
    sizing rule. Neither a SIZED label nor a conditional frontier is sufficient.
    """
    if phase == "pilot":
        return
    if design.get("schema_version") == 2:
        from validation.tier0_pilot_sizing import verify_sizing_receipt

        return verify_sizing_receipt(design, phase, ROOT)
    sizing = design.get("sizing_receipt") or {}
    if not sizing.get("path"):
        raise ValueError("Confirmation requires a measured pilot sizing receipt")
    path = Path(sizing["path"])
    path = path if path.is_absolute() else ROOT / path
    if hashlib.sha256(path.read_bytes()).hexdigest() != sizing.get("sha256"):
        raise ValueError("Changed sizing receipt")
    report = json.loads(path.read_text())
    for entry in ARMS:
        item = report.get("entries", {}).get(entry, {})
        if (item.get("engineering_fixture") is not False or item.get("verdict") != "SIZED"
                or item.get("chosen_n") != design["selected_counts"][phase][entry]):
            raise ValueError("Confirmation count differs from completed full pilot sizing")


def require_campaign_ready(design, phase):
    """Recompute scientific prerequisites before checking permission to spend.

    No human certifier, reviewer name or approval can discharge these checks.
    """
    from tools.source_identity import source_digest
    import importlib.metadata
    from validation.evidence import require_audit_checkout

    require_audit_checkout()
    if phase not in PHASES:
        raise ValueError("Unknown campaign phase")
    require_complete(design, phase=phase)
    if design.get("schema_version") == 2 and phase == "replication":
        raise ValueError("Optional replication is unused by the adopted rank protocol")
    program = json.loads((ROOT / "docs/program/program.json").read_text())
    decisions = {d["id"]: d for d in program["decisions"]}
    prospective = design.get("sampling", {}).get("selection_algorithm") == "prospective_named_suite_local_v1"
    required = ["D-T0-CLAIMS"] + ([] if prospective else ["D-PROTOCOL"]) + (["D-PILOT-ORDER"] if phase == "pilot" else [])
    if design.get("schema_version") == 2:
        required.append("D-T0-OUTCOME-SCOPE")
    if any(decisions.get(key, {}).get("status") != "accepted" for key in required):
        raise ValueError("Campaign requires accepted " + ", ".join(required))
    if design.get("schema_version") == 2:
        approval = design["outcome_approval"]
        if not any(e.get("kind") == "tier0_outcome_scope_user_approval"
                   and {"path": e["path"], "sha256": e["sha256"]} == approval for e in program["evidence"]):
            raise ValueError("Rank design must bind the recorded user-approved outcome/scope amendment")
    from validation.tier0_inference import require_acceptance_inference

    require_acceptance_inference(design["analysis"])
    if prospective:
        from validation.tier0_phase_contracts import require_prospective_scope, verify_phase_freeze
        from validation.tier0_pilot_sizing import require_nonfutile_pilot

        verify_phase_freeze(design, phase, ROOT)
        require_prospective_scope(design, program, ROOT)
        require_nonfutile_pilot(design)
    else:
        work = {w["id"]: w for w in program["work_items"]}
        prerequisites = ["STAT-02", "STAT-03", "VAL-01"] + ([] if phase == "pilot" else ["PILOT-01", "CAP-01"])
        if any(work[key]["state"] != "complete" for key in prerequisites):
            raise ValueError("Campaign prerequisites are incomplete")
    if design.get("status") != "frozen" or design.get("source_digest") != source_digest():
        raise ValueError("A frozen design bound to current executable source is required")
    register = ROOT / "validation/protocols.json"
    if not prospective and json.loads(register.read_text()).get("status") == "DRAFT":
        raise ValueError("DRAFT protocol register cannot authorize campaign execution")
    if design.get("protocol_register_sha256") != hashlib.sha256(register.read_bytes()).hexdigest():
        raise ValueError("Design does not bind the exact protocol register")
    for package, version in design["dependencies"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError(f"Dependency version differs: {package}")
    sizes = design.get("selected_counts", {})
    for entry in ARMS:
        count = sizes.get(phase, {}).get(entry)
        if type(count) is not int or not 5 <= count <= len(design["seed_sets"][phase]):
            raise ValueError("Frozen selected study counts are required for every entry")
    require_confirmation_sizing(design, phase)
    from validation.tier0_phase_contracts import require_execution_environment

    require_execution_environment(design)
    from validation.tier0_objectivity import require_resource_authorization

    require_resource_authorization(design, phase, program, ROOT)
