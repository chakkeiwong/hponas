"""
V11 campaign harness: three arms, two method families, paired study replicates.

Survey reference: Ch 8 sec:priors, roadmap-10 / ch08-03. Authority:
`validation/protocols.json` entries V11a and V11b.

Both entries require the actual piBO decay multiplier and actual PriorBand rung
portfolio. The piBO arm uses `GPqLogEISearcher` directly. The current PriorBand
arm is only a heuristic diagnostic: artificial rung labels do not implement the
published Hyperband policy. PRI-01 records the missing reference conformance and
scheduler integration. This harness cannot certify that method until repaired.

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

Confirmatory execution requires implementation conformance, a certified protocol
and a matching signed manifest; `allow_draft` cannot bypass these checks. Pilot
outputs are always inconclusive for acceptance. A callable pilot interface does
not supply the master program's missing design, authorization or resource budget.
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

#: Artificial rung labels in the retained heuristic diagnostic, not Hyperband rungs.
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
    One retained heuristic diagnostic, not faithful PriorBand acceptance.

    `PriorBandSampler.propose(n, rung_idx)` shifts weight from the prior to incumbent
    perturbations as the artificial rung index rises; this is not the published policy. The
    sampler's `observe` treats larger as better, so minimized objectives are negated on the
    way in — the returned `best_value` stays in the task's own units.
    """
    for name, value in (("n_trials", n_trials), ("n_rungs", n_rungs)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    started = time.time()
    space = task.space()
    try:
        sampler = PriorBandSampler(
            space, prior_fn=_prior_for_arm(task, arm, space), seed=seed
        )
        per_rung, remainder = divmod(n_trials, n_rungs)
        best: Optional[float] = None
        spent = 0
        for rung_idx in range(n_rungs):
            budget = per_rung + int(rung_idx < remainder)
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
    return {
        f"{task_id}::{method}": bounds
        for task_id, bounds in base.items()
        for method in METHODS
    }


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
        if self.mode != "confirmatory" or self.manifest_digest is None:
            return "inconclusive"
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
            "implementation_notes": {
                "priorband": "Heuristic diagnostic; published portfolio and real scheduler conformance unresolved under PRI-01."
            },
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
                            (
                                d.adjusted_alpha
                                for d in self.holm
                                if d.entry_id == entry_id
                            ),
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

    The register status is an administrative prerequisite, not scientific evidence.
    D-OBJECTIVE-EVIDENCE forbids approval from overriding method/design failures;
    the surrounding conformance and inference guards still determine readiness.
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
    manifest_path: Optional[Path] = None,
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
        allow_draft: retained for compatibility; cannot override confirmatory certification.
        manifest_path: required frozen recipe for confirmatory execution.

    Raises:
        RuntimeError: for `mode="confirmatory"` while the register is not certified and
            the source/task/seed manifest cannot be verified.
    """
    if mode not in ("pilot", "confirmatory"):
        raise ValueError(
            f"run_campaign: mode must be 'pilot' or 'confirmatory', got {mode!r}"
        )

    if mode == "confirmatory" and allow_draft:
        raise ValueError("Draft overrides cannot certify a campaign; use pilot mode")
    if mode == "confirmatory":
        if len(methods) != len(METHODS) or set(methods) != set(METHODS):
            raise ValueError("V11 requires both piBO and PriorBand; partial methods cannot certify the entries")
        raise RuntimeError(
            "Refusing confirmatory V11 campaign: faithful PriorBand portfolio and "
            "scheduler conformance remain unresolved (PRI-01 / D-PROTOCOL)."
        )
    tasks = tasks if tasks is not None else V11_ACCEPTANCE_TASKS
    n_replicates = n_replicates if n_replicates is not None else 5
    seeds = (
        pilot_seeds(n_replicates)
        if mode == "pilot"
        else confirmatory_seeds(n_replicates)
    )
    manifest_digest = None
    if mode == "confirmatory":
        permitted, why = _register_permits_confirmatory()
        if not permitted:
            raise RuntimeError("Refusing confirmatory V11 campaign: " + why)
        if manifest_path is None:
            raise ValueError("Confirmatory execution requires a frozen manifest")
        from tools import verify_manifest as verifier
        from validation.evidence import source_digest, digest
        import subprocess

        manifest_path = Path(manifest_path)
        manifest = verifier.load_manifest(manifest_path)
        verifier.check_required_fields(manifest)
        verifier.check_commit_sha(manifest["commit_sha"])
        verifier.check_registry_digest(manifest)
        verifier.check_entry_ids(manifest, verifier.load_protocols())
        verifier.check_scale_bounds(manifest)
        verifier.check_seed_disjointness(manifest)
        verifier.check_timestamp(manifest)
        verifier.check_signature(manifest)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if (
            manifest["commit_sha"] != head
            or manifest.get("source_digest") != source_digest()
        ):
            raise ValueError(
                "Manifest must freeze the current commit and source fingerprint"
            )
        if manifest["task_registry"] != _cluster_bounds(tasks):
            raise ValueError("Executed tasks differ from the manifest")
        if set(manifest["entry_ids"]) != set(ENTRY_ARMS):
            raise ValueError("Manifest entries differ")
        for entry, arm in ENTRY_ARMS.items():
            expected = {"no_prior": seeds, arm: seeds}
            if manifest["seed_sets"].get(entry) != expected:
                raise ValueError("Executed seeds differ from manifest")
        if manifest.get("n_trials") != n_trials or manifest.get("methods") != list(
            methods
        ):
            raise ValueError("Executed budget/methods differ from manifest")
        manifest_digest = digest(manifest_path)

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
                    study_results.append(runner(task, arm, seed, n_trials=n_trials))
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
        manifest_digest=manifest_digest,
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
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--replicates", type=int, default=None)
    parser.add_argument(
        "--output", type=Path, default=Path("validation/results/v11_campaign.json")
    )
    args = parser.parse_args()

    result = run_campaign(
        mode=args.mode, n_replicates=args.replicates, manifest_path=args.manifest
    )
    output_path = write_artifact(result, args.output)
    print(f"Campaign completed. Results written to: {output_path}")
