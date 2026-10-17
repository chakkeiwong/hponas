"""Accepted Tier 0 method arms with measured sequential budget accounting.

Only ``campaign`` is an acceptance entry point. ``run_study`` is also usable for
deterministic engineering fixtures, which carry no campaign certification.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import time

from hponas import Config, GPSearcher, Knob, RandomSearcher, Result, SearchSpace, SobolSearcher
from hponas.persistence import atomic_json
from validation.tier0_analysis import training_seed
from validation.tier0_design import (
    ACCOUNTING, ARMS, canonical_digest, load_design, require_campaign_ready, study_stream_slot,
)


def make_arm(design, task_id, arm, seed):
    task = design["tasks"][task_id]
    seed = study_stream_slot(design, task_id, seed)
    knobs = []
    for original in task["space"]:
        knob = copy.deepcopy(original)
        if arm == "gp_linear":
            knob["transform"] = "none"
        knobs.append(Knob(knob["name"], knob["kind"], tuple(knob["bounds"]),
                          transform=knob["transform"]))
    space = SearchSpace(knobs)
    maximize = (task["objective_direction"] if design.get("schema_version") == 2
                else task["scale_bounds"]["direction"]) == "maximize"
    if arm in {"gp_log", "gp_linear"}:
        return GPSearcher(space, seed=seed, maximize=maximize, **design["gp_options"])
    if arm == "sobol_log":
        return SobolSearcher(space, seed=seed)
    if arm == "random_log":
        return RandomSearcher(space, seed=seed)
    if arm == "tpe_log":
        from hponas.searchers.adapter import LegacySearcherAdapter
        from hponas.searchers_tpe import TPESearcher

        return LegacySearcherAdapter(TPESearcher(space, seed=seed), maximize=maximize)
    raise ValueError("Unregistered Tier 0 arm")


def run_study(design, entry, task_id, seed, arm, phase, objective, *, clock=time.monotonic):
    """One full study, retaining all observations including charged overshoot.

    objective(config, seed, index) returns {'value': ..., ...}. Exceptions make
    the whole replicate missing; no replacement seed or retry is selected.
    """
    task = design["tasks"][task_id]
    if arm not in ARMS[entry] or seed not in design["seed_sets"][phase]:
        raise ValueError("Arm or seed outside frozen design")
    budget = task["budget"]["seconds"]
    initial = task["initial_configs"][str(seed)] if entry == "V05" else []
    slot = study_stream_slot(design, task_id, seed)
    record = {"entry": entry, "task": task_id, "seed": seed, "arm": arm, "phase": phase,
              "rng_stream_slot": slot,
              "design_digest": canonical_digest(design), "accounting": ACCOUNTING,
              "budget_seconds": budget, "accounting_complete": True,
              "status": "trial_limit", "observations": []}
    started = clock()
    try:
        searcher = make_arm(design, task_id, arm, seed)
        for index in range(task["budget"]["trial_limit"]):
            if clock() - started >= budget:
                record["status"] = "complete"
                break
            if index < len(initial):
                # Observe the same physical design, without sampling from the
                # model coordinate system. Both arms get the same RNG schedule
                # for subsequent acquisition optimization as a five-ask GP.
                config = Config(copy.deepcopy(initial[index]))
                searcher.n_suggestions += 1
            else:
                config = searcher.suggest()
            # Optimizer overhead can itself exhaust the measured budget.
            if clock() - started >= budget:
                record["status"] = "complete"
                break
            tid = f"{entry}_{task_id}_{seed}_{arm}_{index}"
            eval_seed = training_seed(slot, index)
            result = objective(config.values, eval_seed, index)
            value = float(result["value"])
            searcher.trials[tid] = config
            observed = Result(tid, value, cost=0.0)
            if not observed.is_valid():
                raise ValueError("Nonfinite objective result")
            searcher.observe(observed)
            artifact_refs = {}
            if result.get("artifacts"):
                from validation.evidence import digest

                artifact_refs = {name: {"path": path, "sha256": digest(path)}
                                 for name, path in result["artifacts"].items()}
            record["observations"].append({
                "index": index, "config": config.values, "training_seed": eval_seed,
                "completed_seconds": clock() - started, "value": value, "receipt": result,
                "artifact_refs": artifact_refs,
            })
            if clock() - started >= budget:
                record["status"] = "complete"
                break
    except Exception as exc:
        record.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
    record["elapsed_seconds"] = clock() - started
    return record


def _ppo_objective(task, run_dir, prefix):
    if task["adapter"] != "brax_ppo":
        raise ValueError("No executable adapter for this acceptance task")
    from workloads.rl_routine import RLSettings, rl_routine

    settings = RLSettings(**task["settings"])

    def objective(config, seed, index):
        return rl_routine({**task["fixed_config"], **config}, seed=seed, settings=settings,
                          artifact_dir=run_dir / "policies", trial_id=f"{prefix}_{index}")

    return objective


def verify_arm_trace(design, record):
    """Reproduce every suggestion from the declared method, seed and prior observations.

    A method label or valid physical config alone cannot establish which
    optimizer produced the trace. This never re-evaluates the objective.
    """
    task = design["tasks"][record["task"]]
    if record.get("rng_stream_slot") != study_stream_slot(design, record["task"], record["seed"]):
        raise ValueError("Method trace random stream differs from frozen task/block namespace")
    searcher = make_arm(design, record["task"], record["arm"], record["seed"])
    initial = task["initial_configs"][str(record["seed"])] if record["entry"] == "V05" else []
    for index, observation in enumerate(record["observations"]):
        if index < len(initial):
            config = Config(copy.deepcopy(initial[index]))
            searcher.n_suggestions += 1
        else:
            config = searcher.suggest()
        if config.values != observation["config"]:
            raise ValueError("Method label does not reproduce the observed suggestion trace")
        tid = str(index)
        searcher.trials[tid] = config
        searcher.observe(Result(tid, observation["value"], cost=0.0))
    return True


def campaign(validation_id, run_dir, *, design_path=None, phase="confirmation", smoke=False):
    from validation.evidence import digest, source_digest

    if validation_id not in ARMS:
        raise ValueError("Unknown Tier 0 comparison")
    if smoke or design_path is None:
        raise ValueError("V04-T0/V05 require a complete evidence-validated design and resource authorization")
    design = load_design(design_path)
    require_campaign_ready(design, phase)  # Before any task, model, GPU or output work.
    if design.get("schema_version") == 2:
        from validation.tier0_rank_campaign import campaign as rank_campaign

        return rank_campaign(validation_id, run_dir, design_path=design_path, phase=phase)
    run_dir = Path(run_dir)
    frozen = run_dir / "design.json"
    atomic_json(frozen, design)
    source = source_digest()
    records = []
    started = time.monotonic()
    for task_id in design["entry_tasks"][validation_id]:
        task = design["tasks"][task_id]
        seeds = design["seed_sets"][phase][:design["selected_counts"][phase][validation_id]]
        for seed_index, seed in enumerate(seeds):
            # Prespecified balanced rotation limits arm-order confounding. One
            # arm executes at a time under the same resource allocation.
            arms = ARMS[validation_id]
            offset = seed_index % len(arms)
            for arm in arms[offset:] + arms[:offset]:
                if time.monotonic() - started >= design["resource"]["campaign_cap_seconds"]:
                    break
                prefix = f"{validation_id}_{task_id}_{seed}_{arm}"
                atomic_json(run_dir / f"{prefix}.pending.json", {
                    "entry": validation_id, "task": task_id, "seed": seed, "arm": arm,
                    "phase": phase, "design_digest": canonical_digest(design),
                    "accounting_complete": False, "status": "started",
                })
                result = run_study(design, validation_id, task_id, seed, arm, phase,
                                   _ppo_objective(task, run_dir, prefix))
                path = run_dir / f"{prefix}.json"
                atomic_json(path, result)
                records.append({"path": str(path.resolve()), "sha256": digest(path)})
    if source_digest() != source:
        raise ValueError("Source changed during the campaign")
    return {"validation_id": validation_id, "schema_version": 2,
            "claim": "registered_tier0_comparison", "phase": phase,
            "source_digest": source, "design": {"path": str(frozen.resolve()), "sha256": digest(frozen)},
            "studies": records, "duration_seconds": time.monotonic() - started}


def recompute_result(validation_id, result):
    from validation.evidence import digest, source_digest
    from validation.tier0_analysis import analyze

    def read_bound(ref):
        if digest(ref["path"]) != ref["sha256"]:
            raise ValueError("Changed raw comparison evidence")
        return json.loads(Path(ref["path"]).read_text())

    if result.get("schema_version") != 2 or result.get("claim") != "registered_tier0_comparison":
        return "INCONCLUSIVE"
    design = read_bound(result["design"])
    phase = result["phase"]
    require_campaign_ready(design, phase)
    if result.get("source_digest") != source_digest():
        return "INCONCLUSIVE"
    records = [read_bound(ref) for ref in result["studies"]]
    for record in records:
        verify_arm_trace(design, record)
        task = design["tasks"][record["task"]]
        for observation in record["observations"]:
            receipt = observation["receipt"]
            if (receipt.get("value") != observation["value"]
                    or receipt.get("metadata", {}).get("workload") != "brax_ppo"
                    or receipt["metadata"].get("training_seed") != observation["training_seed"]
                    or receipt["metadata"].get("settings") != task["settings"]):
                raise ValueError("Objective receipt differs from the frozen task/observation")
            references = observation.get("artifact_refs", {})
            if set(references) != {"checkpoint", "learning_curve", "recipe"}:
                raise ValueError("PPO policy, curve and execution recipe must be bound")
            for name, reference in references.items():
                if (receipt.get("artifacts", {}).get(name) != reference["path"]
                        or digest(reference["path"]) != reference["sha256"]
                        or Path(reference["path"]).stat().st_size == 0):
                    raise ValueError("Changed or missing PPO policy artifact")
            recipe = read_bound(references["recipe"])
            if (recipe.get("settings") != task["settings"]
                    or recipe.get("training_seed") != observation["training_seed"]
                    or recipe.get("search_seed") != observation["training_seed"] + 100000):
                raise ValueError("Saved PPO recipe differs from frozen evaluation")
            curve = read_bound(references["learning_curve"])
            if not curve or max(point["steps"] for point in curve) < task["settings"]["max_timesteps"]:
                raise ValueError("PPO training did not reach the declared requested fidelity")
            for name, value in {**task["fixed_config"], **observation["config"]}.items():
                if recipe.get("config", {}).get(name) != value:
                    raise ValueError("Saved PPO configuration differs from arm suggestion")
            import numpy as np

            returns = np.asarray(receipt["metadata"].get("search_returns", []), dtype=float)
            if (returns.shape != (task["settings"]["eval_episodes"],)
                    or not np.isfinite(returns).all()
                    or float(returns.mean()) != observation["value"]):
                raise ValueError("Objective differs from raw episode returns")
    report = analyze(design, records, phase, [validation_id])
    if phase == "pilot":
        return "INCONCLUSIVE"
    return report["entries"][validation_id]["verdict"]
