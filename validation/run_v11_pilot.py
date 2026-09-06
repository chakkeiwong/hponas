"""
Run the V11 pilot and write its artifact.

The pilot exists to estimate the variance components the confirmatory sample size is
derived from (`policy.power.method = simulation`), and to produce the pilot report the
register's `status_note` names as outstanding before certification. It is not
decision-bearing: `CampaignResult.verdict` returns `inconclusive` rather than `fail` in
pilot mode.

Seeds come from `PILOT_SEED_BASE` and are disjoint from the confirmatory block, because
`policy.power.pilot_data_reuse` is `forbidden`.

Usage:
    python -m validation.run_v11_pilot [--replicates N] [--out PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from validation.v11_campaign import run_campaign, write_artifact

DEFAULT_OUT = Path("validation/results/v11_pilot.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the V11 pilot campaign.")
    parser.add_argument(
        "--replicates",
        type=int,
        default=None,
        help="Study replicates per (task, method, arm). Defaults to the register's min_pilot.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Artifact path.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-study progress.")
    args = parser.parse_args(argv)

    result = run_campaign(
        mode="pilot",
        n_replicates=args.replicates,
        progress=not args.quiet,
    )

    # Write before any summarising, so a downstream error cannot discard the compute.
    path = write_artifact(result, args.out)
    print(f"\nArtifact: {path}")
    print(f"Elapsed: {result.elapsed_s / 60:.1f} min")
    print(f"Studies: {len(result.study_results)}")

    if result.voided:
        print(f"VOIDED: {result.void_reason}")
        return 1

    for entry_id in sorted(result.tests):
        test = result.tests[entry_id]
        miss = result.missingness[entry_id]
        lb = test.lower_bound(0.05 / 6)  # family-adjusted alpha
        print(
            f"\n{entry_id}: point={test.point:+.4f} "
            f"lb={lb:+.4f} p={test.p_value:.4f} "
            f"verdict={result.verdict(entry_id)}"
        )
        print(f"  missingness: {miss}")
        for cluster in result.clusters[entry_id]:
            print(f"  {cluster.task:28s} n={cluster.n_blocks} mean={cluster.mean:+.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
