"""
V11 campaign harness: three arms, two method families, paired study replicates.

Survey reference: Ch 8 sec:priors, roadmap-10 / ch08-03. Authority:
`validation/protocols.json` entries V11a and V11b.

Both entries carry the same `implementation_requirement`: "Tests the actual piBO decay
multiplier and the actual PriorBand rung portfolio. GP-mean substitution and top-K sampling
are different methods and do not satisfy this entry." So the arms below drive
`GPqLogEISearcher(prior_fn=...)` and `PriorBandSampler(prior_fn=...)` directly. No
surrogate for the prior mechanism appears anywhere in this file.

Design, following the register:

  repetition_unit  complete study replicate, paired by task and optimizer seed
  cluster          (task, method) pair — both method families are required by the
                   implementation requirement, and a prior helps a GP acquisition and a
                   bandit portfolio through different mechanisms, so pooling them into one
                   per-task number would average over two distinct claims
  arms             no_prior (comparator), folklore_prior (V11a), wrong_prior (V11b)
  endpoint         best objective seen at the declared trial budget
  missingness      a replicate that raises is excluded with its paired block and counted

Pilot and confirmatory runs differ only in seed block and replicate count. Pilot output
sizes the confirmatory campaign; `policy.power.pilot_data_reuse` is `forbidden`, so the
seed blocks are disjoint by construction (see `v11_tasks.PILOT_SEED_BASE`).

Executing a *confirmatory* campaign is gated: `validation/protocols.json` is `status:
DRAFT` and `docs/progress.md` records the protocols as blocked on Codex re-review, pilot
report, and PI certification "before any campaign spend". `run_campaign` refuses
`mode="confirmatory"` unless the register says otherwise or the caller passes
`allow_draft=True` deliberately. The pilot is not gated — the register asks for a pilot
report as a precondition to certification, so running one is the way forward, not a
shortcut past it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np

from hponas.searchers_priorband import PriorBandSampler
from hponas.space import SearchSpace
from validation.stats import (
    DEFAULT_ALPHA,
    DEFAULT_DRAWS,
    Cluster,
    PairedBlock,
    TestResult,
    build_clusters,
    holm_bonferroni,
    non_inferiority_one_sided,
    superiority_one_sided,
)
from validation.v11_tasks import (
    V11_ACCEPTANCE_TASKS,
    AcceptanceTask,
    confirmatory_seeds,
    frozen_task_registry,
    pilot_seeds,
    scale_bounds_by_task,
    verify_all_prior_support,
)

PROTOCOLS_PATH = Path("validation/protocols.json")

#: Arm names. `no_prior` is the comparator for both entries.
ARMS = ("no_prior", "folklore_prior", "wrong_prior")

#: Method families the implementation requirement names.
METHODS = ("pibo", "priorband")

#: Entry ids this harness decides.
ENTRY_IDS = ("V11a", "V11b")

#: Declared size of the tier-1 confirmatory family (policy.confirmatory_families).
#: A campaign running 2 of the 6 members still corrects for 6.
TIER1_FAMILY_SIZE = 6

#: Arm pairing for each V11 entry. The comparator is always "no_prior".
ENTRY_ARMS = {"V11a": "folklore_prior", "V11b": "wrong_prior"}

#: Trials per study replicate. Small by design: πBO refits a GP per proposal, so the
#: pilot's job is variance estimation, not a best-effort optimization result.
DEFAULT_N_TRIALS = 25

#: PriorBand rungs. The rung index drives the portfolio's prior→incumbent decay, which is
#: the mechanism under test, so a single-rung run would not exercise the entry.
DEFAULT_N_RUNGS = 3


# ---------------------------------------------------------------------------
# One study replicate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudyResult:
    """Outcome of one study replicate: one (task, method, arm, seed) cell."""

    task_id: str
    method: str
    arm: str
    seed: int
    best_value: Optional[float]
    n_trials: int
    elapsed_s: float
    error: Optional[str] = None

    @property
    def complete(self) -> bool:
        return self.best_value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "method": self.method,
            "arm": self.arm,
            "seed": self.seed,
            "best_value": self.best_value,
            "n_trials": self.n_trials,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
        }


def _prior_for_arm(task: AcceptanceTask, arm: str, space: SearchSpace):
    """The raw (unguarded) prior for an arm; the searchers guard it at entry."""
    if arm == "no_prior":
        return None
    if arm == "folklore_prior":
        return task.folklore_prior(space)
    if arm == "wrong_prior":
        return task.wrong_prior(space)
    raise ValueError(f"unknown arm {arm!r}")


def _better(direction: str, candidate: float, incumbent: Optional[float]) -> bool:
    if incumbent is None:
        return True
    return candidate < incumbent if direction == "minimize" else candidate > incumbent


def run_pibo_study(
    task: AcceptanceTask,
    arm: str,
    seed: int,
    n_trials: int = DEFAULT_N_TRIALS,
) -> StudyResult:
    """
    One πBO study replicate: sequential GP + qLogEI with the prior decay multiplier.

    `GPqLogEISearcher` applies π(x)^(β/n) inside `PriorWeightedAcquisition`, so the decay
    is exercised exactly as shipped. Proposals are drawn one at a time because the exponent
    depends on the observation count, and a batch would hold it fixed across the batch.
    """
    from hponas.searchers_gp import GPqLogEISearcher

    started = time.time()
    space = task.space()
    try:
        searcher = GPqLogEISearcher(
            space,
            seed=seed,
            prior_fn=_prior_for_arm(task, arm, space),
            raw_samples=128,
            n_restarts=4,
        )
        best: Optional[float] = None
        for _ in range(n_trials):
            config = searcher.propose(1)[0]
            value = task.objective(config)
            # The searcher maximizes; a minimized objective enters negated.
            observed = -value if task.direction == "minimize" else value
            searcher.observe({"config": config, "value": observed})
            if _better(task.direction, value, best):
                best = value
    except Exception as exc:  # missingness, recorded rather than swallowed
        return StudyResult(
            task_id=task.task_id,
            method="pibo",
            arm=arm,
            seed=seed,
            best_value=None,
            n_trials=n_trials,
            elapsed_s=time.time() - started,
            error=f"{type(exc).__name__}: {exc}",
        )

    return StudyResult(
        task_id=task.task_id,
        method="pibo",
        arm=arm,
        seed=seed,
        best_value=best,
        n_trials=n_trials,
        elapsed_s=time.time() - started,
    )


def run_priorband_study(
    task: AcceptanceTask,
    arm: str,
    seed: int,
    n_trials: int = DEFAULT_N_TRIALS,
    n_rungs: int = DEFAULT_N_RUNGS,
) -> StudyResult:
    """
    One PriorBand study replicate: the real rung portfolio across `n_rungs` rungs.

    `PriorBandSampler.propose(n, rung_idx)` shifts weight from the prior to incumbent
    perturbations as the rung index rises, which is the mechanism the entry names. The
    sampler's `observe` treats larger as better, so minimized objectives are negated on the
    way in — the returned `best_value` stays in the task's own units.
    """
    started = time.time()
    space = task.space()
    try:
        sampler = PriorBandSampler(
            space, prior_fn=_prior_for_arm(task, arm, space), seed=seed
        )
        per_rung = max(1, n_trials // n_rungs)
        best: Optional[float] = None
        spent = 0
        for rung_idx in range(n_rungs):
            budget = min(per_rung, n_trials - spent)
            if budget <= 0:
                break
            for config in sampler.propose(budget, rung_idx=rung_idx):
                value = task.objective(config)
                observed = -value if task.direction == "minimize" else value
                sampler.observe({"config": config, "value": observed})
                if _better(task.direction, value, best):
                    best = value
                spent += 1
    except Exception as exc:
        return StudyResult(
            task_id=task.task_id,
            method="priorband",
            arm=arm,
            seed=seed,
            best_value=None,
            n_trials=n_trials,
            elapsed_s=time.time() - started,
            error=f"{type(exc).__name__}: {exc}",
        )

    return StudyResult(
        task_id=task.task_id,
        method="priorband",
        arm=arm,
        seed=seed,
        best_value=best,
        n_trials=spent,
        elapsed_s=time.time() - started,
    )


STUDY_RUNNERS: dict[str, Callable[..., StudyResult]] = {
    "pibo": run_pibo_study,
    "priorband": run_priorband_study,
}


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def blocks_for_entry(
    results: Sequence[StudyResult],
    arm: str,
    comparator: str = "no_prior",
) -> list[PairedBlock]:
    """
    Assemble paired blocks for one entry from a flat list of study results.

    The block key is (task, method, seed): a paired block is the set of arms sharing the
    same task and the same optimizer seed (policy.resampling.pairing_definition), and the
    method family is part of the cluster identity here. The cluster label carries both, so
    `build_clusters` groups per (task, method).
    """
    indexed: dict[tuple[str, str, int, str], StudyResult] = {
        (r.task_id, r.method, r.seed, r.arm): r for r in results
    }
    keys = sorted({(r.task_id, r.method, r.seed) for r in results})

    blocks: list[PairedBlock] = []
    for task_id, method, seed in keys:
        arm_result = indexed.get((task_id, method, seed, arm))
        comp_result = indexed.get((task_id, method, seed, comparator))
        if arm_result is None or comp_result is None:
            continue
        blocks.append(
            PairedBlock(
                task=f"{task_id}::{method}",
                seed=seed,
                arm_value=arm_result.best_value,
                comparator_value=comp_result.best_value,
            )
        )
    return blocks


def _cluster_bounds(tasks: dict[str, AcceptanceTask]) -> dict[str, Any]:
    """Scale bounds keyed by the `task::method` cluster label."""
    base = scale_bounds_by_task(tasks)
    return {f"{task_id}::{method}": bounds for task_id, bounds in base.items() for method in METHODS}


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------


@dataclass
class CampaignResult:
    """Everything a gate report needs, plus the manifest digest it must cite."""

    mode: str
    n_replicates: int
    n_trials: int
    study_results: list[StudyResult]
    tests: dict[str, TestResult]
    clusters: dict[str, list[Cluster]]
    missingness: dict[str, Any]
    holm: list[Any]
    prior_support: list[Any]
    manifest_digest: Optional[str] = None
    voided: bool = False
    void_reason: Optional[str] = None
    elapsed_s: float = 0.0

    def verdict(self, entry_id: str) -> str:
        """
        Entry verdict under the family-adjusted alpha.

        Three outcomes, as the register defines them: `pass`, `fail`, and `inconclusive`
        at the declared `max_sample`. A voided campaign has no verdict at all — missingness
        above 10% "voids the campaign and triggers re-run after diagnosis".
        """
        if self.voided:
            return "void"
        decision = next((d for d in self.holm if d.entry_id == entry_id), None)
        if decision is None:
            return "not_tested"
        if decision.reject and self.tests[entry_id].clears(decision.adjusted_alpha):
            return "pass"
        return "fail" if self.mode == "confirmatory" else "inconclusive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "n_replicates": self.n_replicates,
            "n_trials": self.n_trials,
            "manifest_digest": self.manifest_digest,
            "voided": self.voided,
            "void_reason": self.void_reason,
            "elapsed_s": self.elapsed_s,
            "family": {
                "name": "tier1_gate",
                "declared_size": TIER1_FAMILY_SIZE,
                "tested_here": sorted(self.tests),
                "alpha_family": DEFAULT_ALPHA,
            },
            "holm": [d.to_dict() for d in self.holm],
            "entries": {
                entry_id: {
                    **test.to_dict(
                        alpha=next(
                            (d.adjusted_alpha for d in self.holm if d.entry_id == entry_id),
                            DEFAULT_ALPHA,
                        )
                    ),
                    "verdict": self.verdict(entry_id),
                    "clusters": [
                        {"cluster": c.task, "n_blocks": c.n_blocks, "mean": c.mean}
                        for c in self.clusters[entry_id]
                    ],
                    "missingness": self.missingness[entry_id],
                }
                for entry_id, test in self.tests.items()
            },
            "prior_support": [r.to_dict() for r in self.prior_support],
            "studies": [r.to_dict() for r in self.study_results],
        }


def _register_permits_confirmatory() -> tuple[bool, str]:
    """
    Whether the protocol register permits confirmatory spend.

    The register's own `status_note` is the gate: while it reads DRAFT and names Codex
    re-review, a pilot report, and PI certification as outstanding, a confirmatory campaign
    would be spending against protocols that are not yet certified.
    """
    if not PROTOCOLS_PATH.exists():
        return False, f"protocol register not found at {PROTOCOLS_PATH}"
    with open(PROTOCOLS_PATH) as f:
        register = json.load(f)
    status = register.get("status", "UNKNOWN")
    if status != "CERTIFIED":
        return False, (
            f"protocol register status is {status!r}, not 'CERTIFIED'. "
            f"{register.get('status_note', '')}".strip()
        )
    return True, "register is certified"


def run_campaign(
    mode: str = "pilot",
    n_replicates: Optional[int] = None,
    n_trials: int = DEFAULT_N_TRIALS,
    tasks: Optional[dict[str, AcceptanceTask]] = None,
    methods: Sequence[str] = METHODS,
    draws: int = DEFAULT_DRAWS,
    bootstrap_seed: int = 0,
    allow_draft: bool = False,
    progress: bool = False,
) -> CampaignResult:
    """
    Run the V11 campaign end to end and decide V11a and V11b.

    Args:
        mode: "pilot" (variance estimation, seeds from PILOT_SEED_BASE) or "confirmatory"
            (decision-bearing, seeds from CONFIRMATORY_SEED_BASE).
        n_replicates: study replicates per (task, method, arm). Defaults to the register's
            `min_pilot` of 5 for a pilot, and to that same floor for a confirmatory run,
            which should instead be sized from pilot variance via
            `validation.stats.size_by_simulation`.
        n_trials: trial budget per replicate; the declared endpoint.
        allow_draft: run confirmatorily against a non-certified register anyway. Present so
            the refusal is a deliberate override rather than an obstacle, and recorded in
            the artifact when used.

    Raises:
        RuntimeError: for `mode="confirmatory"` while the register is not certified and
            `allow_draft` is False.
    """
    if mode not in ("pilot", "confirmatory"):
        raise ValueError(f"run_campaign: mode must be 'pilot' or 'confirmatory', got {mode!r}")

    if mode == "confirmatory" and not allow_draft:
        permitted, why = _register_permits_confirmatory()
        if not permitted:
            raise RuntimeError(
                "Refusing confirmatory V11 campaign: " + why + ". "
                "Run mode='pilot' to produce the pilot report the certification needs, or "
                "pass allow_draft=True to override deliberately."
            )

    tasks = tasks if tasks is not None else V11_ACCEPTANCE_TASKS
    n_replicates = n_replicates if n_replicates is not None else 5
    seeds = pilot_seeds(n_replicates) if mode == "pilot" else confirmatory_seeds(n_replicates)

    started = time.time()
    study_results: list[StudyResult] = []
    total = len(tasks) * len(methods) * len(ARMS) * len(seeds)
    done = 0

    for task_id in sorted(tasks):
        task = tasks[task_id]
        for method in methods:
            runner = STUDY_RUNNERS[method]
            for arm in ARMS:
                for seed in seeds:
                    study_results.append(
                        runner(task, arm, seed, n_trials=n_trials)
                    )
                    done += 1
                    if progress:
                        print(
                            f"[{done}/{total}] {task_id} {method} {arm} seed={seed} "
                            f"-> {study_results[-1].best_value}",
                            flush=True,
                        )

    bounds = _cluster_bounds(tasks)

    tests: dict[str, TestResult] = {}
    clusters: dict[str, list[Cluster]] = {}
    missingness: dict[str, Any] = {}
    voided = False
    void_reason: Optional[str] = None

    for entry_id, arm in ENTRY_ARMS.items():
        blocks = blocks_for_entry(study_results, arm)
        entry_clusters, report = build_clusters(blocks, bounds)
        clusters[entry_id] = entry_clusters
        missingness[entry_id] = report.to_dict()
        if report.voids_campaign:
            voided = True
            void_reason = (
                f"{entry_id}: {report.loss_fraction:.1%} of planned replicates incomplete, "
                "above the 10% ceiling (policy.missingness)"
            )
        if entry_id == "V11a":
            tests[entry_id] = superiority_one_sided(
                entry_id, entry_clusters, margin=0.0, draws=draws, seed=bootstrap_seed
            )
        else:
            tests[entry_id] = non_inferiority_one_sided(
                entry_id, entry_clusters, margin=0.1, draws=draws, seed=bootstrap_seed
            )

    holm = holm_bonferroni(
        {entry_id: test.p_value for entry_id, test in tests.items()},
        alpha=DEFAULT_ALPHA,
        family_size=TIER1_FAMILY_SIZE,
    )

    return CampaignResult(
        mode=mode,
        n_replicates=n_replicates,
        n_trials=n_trials,
        study_results=study_results,
        tests=tests,
        clusters=clusters,
        missingness=missingness,
        holm=holm,
        prior_support=verify_all_prior_support(tasks),
        voided=voided,
        void_reason=void_reason,
        elapsed_s=time.time() - started,
    )


def write_artifact(result: CampaignResult, path: Path) -> Path:
    """
    Write the campaign artifact, which must carry the manifest digest it was run under.

    `preregistration_order` step 6 is "Embed manifest digest in every result artifact", and
    step 7 has the gate report cite it. A pilot has no signed manifest yet, so the field is
    null and the artifact says as much rather than inventing a digest.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result.to_dict(), f, indent=2, sort_keys=False)
    return path


if __name__ == "__main__":
    """V16 runnable independently: standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(description="V11 Prior Recovery Campaign")
    parser.add_argument("--mode", choices=["pilot", "confirmatory"], default="pilot")
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("validation/results/v11_campaign.json"))
    args = parser.parse_args()

    result = run_campaign(mode=args.mode, n_replicates=args.replicates)
    output_path = write_artifact(result, args.output)
    print(f"Campaign completed. Results written to: {output_path}")
    return path
