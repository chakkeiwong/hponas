"""
Probe the trial budget at which the no-prior baselines stop saturating.

The pilot found that GP + qLogEI reaches the declared optimum on all four acceptance
tasks within 25 trials, leaving V11a's superiority estimand no headroom to detect. This
script sweeps the trial budget for both method families and reports the normalized gap to
the declared optimum, so the confirmatory budget can be chosen from evidence rather than
guessed.

The gap is reported on the estimand's own scale (gap / span), because that is the ceiling
on any effect V11a could measure.

Usage:
    python -m validation.probe_v11_saturation [--budgets 5 10 15 20 25] [--seeds 3]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from validation.v11_campaign import STUDY_RUNNERS
from validation.v11_tasks import V11_ACCEPTANCE_TASKS, PILOT_SEED_BASE

DEFAULT_BUDGETS = (5, 10, 15, 20, 25)
DEFAULT_OUT = Path("validation/results/v11_saturation_probe.json")


def probe(
    budgets: tuple[int, ...],
    n_seeds: int,
    methods: tuple[str, ...] = ("pibo", "priorband"),
) -> list[dict[str, Any]]:
    """Median no-prior best value and normalized gap to the declared optimum."""
    rows: list[dict[str, Any]] = []
    for task_id, task in V11_ACCEPTANCE_TASKS.items():
        opt_value = task.objective(task.declared_optimum)
        span = task.bound_high - task.bound_low
        for method in methods:
            runner = STUDY_RUNNERS[method]
            for budget in budgets:
                values: list[float] = []
                for k in range(n_seeds):
                    result = runner(
                        task, "no_prior", PILOT_SEED_BASE + k, n_trials=budget
                    )
                    if result.best_value is not None:
                        values.append(result.best_value)
                if not values:
                    continue
                median = float(np.median(values))
                gap = (
                    opt_value - median
                    if task.direction == "maximize"
                    else median - opt_value
                )
                rows.append(
                    {
                        "task_id": task_id,
                        "method": method,
                        "direction": task.direction,
                        "n_trials": budget,
                        "n_seeds": len(values),
                        "declared_optimum_value": opt_value,
                        "median_best": median,
                        "gap": gap,
                        "normalized_gap": gap / span,
                    }
                )
                print(
                    f"{task_id:18s} {method:10s} n={budget:2d} "
                    f"median={median:+12.6f} norm_gap={gap / span:+.5f}",
                    flush=True,
                )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe V11 baseline saturation.")
    parser.add_argument("--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS))
    parser.add_argument("--seeds", type=int, default=3, help="Seeds per cell.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    rows = probe(tuple(args.budgets), args.seeds)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"seeds_per_cell": args.seeds, "rows": rows}, f, indent=2)

    print(f"\nArtifact: {args.out}")
    print("\nNormalized gap is the ceiling on any effect V11a could measure.")
    print("A budget leaving < 0.01 of span is saturated for that method family.\n")

    for method in ("pibo", "priorband"):
        print(f"{method}:")
        for budget in args.budgets:
            gaps = [
                r["normalized_gap"]
                for r in rows
                if r["method"] == method and r["n_trials"] == budget
            ]
            if not gaps:
                continue
            worst = min(gaps)  # smallest headroom across tasks
            print(
                f"  n={budget:2d}: min headroom across tasks = {worst:+.5f}"
                + ("  <- saturated" if worst < 0.01 else "")
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
