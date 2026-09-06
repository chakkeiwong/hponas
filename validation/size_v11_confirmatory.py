"""
Size the V11 confirmatory campaigns from the pilot artifact.

The register requires the confirmatory sample to be sized by simulation under the entry's
own two-level hierarchy (policy.power.method = simulation), against the upper confidence
bound on pilot variance rather than the point estimate
(policy.power.pilot_variance_treatment) so pilot noise inflates the sample instead of
shrinking it.

The two variance components the simulation needs are separated as follows:

  cluster_sd  between-task spread of the cluster-level paired mean difference, taken as
              the sample SD across `task::method` clusters
  block_sd    within-cluster spread of paired block differences, pooled across clusters

Both are normalized differences (the estimand's own scale), so they are computed from
`Cluster.differences`, not from raw objective values. Each is passed through
`variance_upper_bound` at the register's declared confidence.

Sizing uses the alpha the entry would face in the worst case under Holm within the
tier1_gate family: alpha / m with m = 6. Holm's least-significant rank gets a larger
alpha, so alpha/m is the conservative choice for a sample-size decision made before the
p-values exist.

Usage:
    python -m validation.size_v11_confirmatory [--pilot PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from validation.stats import (
    DEFAULT_ALPHA,
    PILOT_VARIANCE_CONFIDENCE,
    SIZING_DRAWS,
    SIZING_REPLICATES,
    Cluster,
    build_clusters,
    cluster_level_mean,
    size_by_simulation,
    variance_upper_bound,
)
from validation.v11_campaign import (
    ENTRY_ARMS,
    TIER1_FAMILY_SIZE,
    StudyResult,
    _cluster_bounds,
    blocks_for_entry,
)
from validation.v11_tasks import V11_ACCEPTANCE_TASKS

DEFAULT_PILOT = Path("validation/results/v11_pilot.json")
DEFAULT_OUT = Path("validation/results/v11_sizing.json")

# Superiority tests theta > 0; non-inferiority tests theta > -margin.
ENTRY_THRESHOLDS = {"V11a": 0.0, "V11b": -0.1}
N_CLUSTERS = len(V11_ACCEPTANCE_TASKS) * 2  # tasks x method families


def rehydrate_studies(pilot: dict[str, Any]) -> list[StudyResult]:
    """Rebuild StudyResult records from a pilot artifact's `studies` array."""
    return [
        StudyResult(
            task_id=s["task_id"],
            method=s["method"],
            arm=s["arm"],
            seed=s["seed"],
            best_value=s["best_value"],
            n_trials=s["n_trials"],
            elapsed_s=s["elapsed_s"],
            error=s.get("error"),
        )
        for s in pilot["studies"]
    ]


def variance_components(
    clusters: list[Cluster],
    confidence: float = PILOT_VARIANCE_CONFIDENCE,
) -> tuple[float, float, float]:
    """
    Effect and the two SD components, each at its upper confidence bound.

    Returns (effect, cluster_sd_upper, block_sd_upper). The effect is the point estimate:
    sizing inflates variance, not the assumed effect, because deflating the effect as well
    would compound two conservatisms and the register only asks for the variance one.

    A single cluster leaves the between-task component unidentifiable; it is reported as
    0.0, and the caller is told, rather than silently treated as no between-task spread.
    """
    if not clusters:
        raise ValueError("variance_components: no clusters")

    effect = cluster_level_mean(clusters)

    cluster_means = [c.mean for c in clusters]
    if len(cluster_means) >= 2:
        cluster_sd_upper = float(np.sqrt(variance_upper_bound(cluster_means, confidence)))
    else:
        cluster_sd_upper = 0.0

    # Pooled within-cluster differences, centred per cluster so between-task spread does
    # not leak into the block component.
    centred: list[float] = []
    for cluster in clusters:
        diffs = np.asarray(cluster.differences, dtype=float)
        if diffs.size >= 2:
            centred.extend((diffs - diffs.mean()).tolist())
    if len(centred) >= 2:
        # Centring each cluster costs one degree of freedom per cluster; variance_upper_bound
        # assumes ddof=1 overall, so rescale to the correct dof before bounding.
        n_obs = sum(c.n_blocks for c in clusters)
        dof_actual = n_obs - len(clusters)
        block_sd_upper = float(np.sqrt(variance_upper_bound(centred, confidence)))
        if dof_actual > 0:
            scale = np.sqrt((len(centred) - 1) / dof_actual)
            block_sd_upper *= float(scale)
    else:
        block_sd_upper = 0.0

    return effect, cluster_sd_upper, block_sd_upper


def size_entry(
    entry_id: str,
    clusters: list[Cluster],
    alpha: float,
    replicates: int,
    draws: int,
    power_target: float = 0.8,
    max_sample: int = 20,
) -> dict[str, Any]:
    """Size one entry and return the record written to the sizing artifact."""
    effect, cluster_sd, block_sd = variance_components(clusters)
    threshold = ENTRY_THRESHOLDS[entry_id]

    sizing = size_by_simulation(
        effect=effect,
        cluster_sd=cluster_sd,
        block_sd=block_sd,
        n_clusters=len(clusters),
        threshold=threshold,
        alpha=alpha,
        power_target=power_target,
        max_sample=max_sample,
        replicates=replicates,
        draws=draws,
        seed=0,
    )

    return {
        "entry_id": entry_id,
        "arm": ENTRY_ARMS[entry_id],
        "threshold": threshold,
        "pilot_effect": effect,
        "cluster_sd_upper": cluster_sd,
        "block_sd_upper": block_sd,
        "n_clusters": len(clusters),
        "alpha_used": alpha,
        "power_target": power_target,
        "max_sample": max_sample,
        "n_sized": sizing.chosen_n,
        "power_attained": sizing.attained_power,
        "power_curve": [{"n": n, "power": p} for n, p in sizing.curve],
        "clusters": [
            {"cluster": c.task, "n_blocks": c.n_blocks, "mean": c.mean} for c in clusters
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Size V11 confirmatory campaigns from pilot.")
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT, help="Pilot artifact.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Sizing artifact.")
    parser.add_argument("--replicates", type=int, default=SIZING_REPLICATES)
    parser.add_argument("--draws", type=int, default=SIZING_DRAWS)
    args = parser.parse_args(argv)

    if not args.pilot.exists():
        print(f"Pilot artifact not found: {args.pilot}", file=sys.stderr)
        return 1

    with open(args.pilot) as f:
        pilot = json.load(f)

    if pilot.get("mode") != "pilot":
        print(f"Refusing to size from a {pilot.get('mode')!r} artifact.", file=sys.stderr)
        return 1
    if pilot.get("voided"):
        print(f"Refusing to size from a voided pilot: {pilot.get('void_reason')}", file=sys.stderr)
        return 1

    studies = rehydrate_studies(pilot)
    bounds = _cluster_bounds(V11_ACCEPTANCE_TASKS)

    # Holm's worst case within the family: alpha / m.
    alpha = DEFAULT_ALPHA / TIER1_FAMILY_SIZE

    records: dict[str, Any] = {}
    for entry_id, arm in ENTRY_ARMS.items():
        blocks = blocks_for_entry(studies, arm)
        clusters, report = build_clusters(blocks, bounds)
        record = size_entry(
            entry_id,
            clusters,
            alpha=alpha,
            replicates=args.replicates,
            draws=args.draws,
        )
        record["missingness"] = report.to_dict()
        records[entry_id] = record

        print(f"\n{'=' * 68}")
        print(f"{entry_id}  arm={arm}  threshold={record['threshold']:+.2f}")
        print(f"  pilot effect      {record['pilot_effect']:+.4f} (normalized)")
        print(f"  cluster SD (upper) {record['cluster_sd_upper']:.4f}")
        print(f"  block SD (upper)   {record['block_sd_upper']:.4f}")
        print(f"  alpha used         {alpha:.5f}  (0.05 / {TIER1_FAMILY_SIZE}, Holm worst case)")
        if record["n_sized"] is not None:
            print(
                f"  SIZED n={record['n_sized']} replicates per task::method cluster "
                f"(power {record['power_attained']:.3f})"
            )
        else:
            print(
                f"  NOT SIZED: power {record['power_attained']:.3f} at max_sample="
                f"{record['max_sample']}, below target {record['power_target']}. "
                "Confirmatory verdict would be `inconclusive` "
                "(policy.power.max_sample_rule)."
            )
        for row in record["clusters"]:
            print(f"    {row['cluster']:28s} n={row['n_blocks']}  mean={row['mean']:+.4f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(
            {
                "source_pilot": str(args.pilot),
                "family": {"name": "tier1_gate", "declared_size": TIER1_FAMILY_SIZE},
                "alpha_family": DEFAULT_ALPHA,
                "alpha_used": alpha,
                "pilot_variance_confidence": PILOT_VARIANCE_CONFIDENCE,
                "sizing_replicates": args.replicates,
                "sizing_draws": args.draws,
                "entries": records,
            },
            f,
            indent=2,
        )

    print(f"\n{'=' * 68}")
    print(f"Sizing artifact: {args.out}")
    for entry_id, record in records.items():
        n = record["n_sized"]
        print(f"  {entry_id}: " + (f"n={n}" if n is not None else "inconclusive at max_sample"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
