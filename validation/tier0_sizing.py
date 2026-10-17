"""Candidate joint power/coverage sizing, using independent pilot paired blocks.

This is a planning model, not a claim that the unknown task population is normal.
Its Gaussian random-effects assumption and UCB approximation require PI review.
The simulation preserves all component correlations and the conjunctive entry.
"""

from __future__ import annotations

import numpy as np

from validation.stats import variance_upper_bound


def size_from_pilot(design, records):
    """Bind the sizing procedure to complete, disjoint pilot evidence and frozen effects."""
    from validation.tier0_analysis import collect_blocks, components
    from validation.tier0_design import ARMS, canonical_digest, require_complete

    if design.get("schema_version") == 2:
        raise ValueError("STAT-03/E: legacy bootstrap sizing cannot size the protected-rank design")
    require_complete(design)
    if any(record.get("entry") not in ARMS or record.get("phase") != "pilot" for record in records):
        raise ValueError("Only independent pilot records may size confirmation")
    reports = {}
    for entry in ARMS:
        blocks, missing = collect_blocks(design, records, "pilot", entry)
        if missing["void"]:
            raise ValueError("Pilot missingness voids sizing; diagnose before a new pilot")
        endpoints = [endpoint for _, _, endpoint in components(entry)]
        reports[entry] = size_joint_entry(
            blocks, [design["planning_effects"][entry][e] for e in endpoints],
            [design["margins"][entry][e] for e in endpoints],
            seed=design["analysis"]["bootstrap_seed"],
        )
    return {"design_digest": canonical_digest(design), "entries": reports,
            "pilot_reused_for_confirmation": False}


def pilot_model(blocks):
    """Conservative multivariate task/block planning covariance.

    Use task-mean variance (including sampling noise) for task effects, without
    subtracting within-task noise. Bound each residual variance within its task
    with the upper 80% chi-square bound, then take the largest across tasks.
    Correlations are empirical and are not given a coverage guarantee.
    """
    arrays = list(blocks.values())
    if len(arrays) < 2 or any(a.ndim != 2 or len(a) < 5 or not np.isfinite(a).all() for a in arrays):
        raise ValueError("Sizing needs at least two task clusters and five complete pilot blocks per task")
    if len({a.shape[1] for a in arrays}) != 1:
        raise ValueError("Pilot components differ between tasks")
    means = np.array([a.mean(axis=0) for a in arrays])
    residuals = np.concatenate([a - a.mean(axis=0) for a in arrays])

    def inflated_covariance(values, variances):
        cov = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
        diagonal = np.diag(cov)
        denominator = np.sqrt(np.outer(diagonal, diagonal))
        correlation = np.divide(cov, denominator, out=np.eye(len(diagonal)), where=denominator > 0)
        return correlation * np.sqrt(np.outer(variances, variances))

    task_variances = [variance_upper_bound(means[:, i]) for i in range(means.shape[1])]
    block_variances = [max(variance_upper_bound(a[:, i]) for a in arrays) for i in range(means.shape[1])]
    return inflated_covariance(means, task_variances), inflated_covariance(residuals, block_variances)


def joint_bootstrap(samples, draws, rng):
    """One set of task/block draws shared by all endpoint/comparator components."""
    tasks, blocks, _ = samples.shape
    clusters = rng.integers(0, tasks, size=(draws, tasks))
    paired = rng.integers(0, blocks, size=(draws, tasks, blocks))
    return samples[clusters[:, :, None], paired].mean(axis=2).mean(axis=1)


def size_joint_entry(blocks, effects, thresholds, *, max_sample=20, candidates=None,
                     replicates=2000, draws=10000, seed=94029):
    """Size the complete intersection-union entry at conservative family alpha .025.

    Both entries passing at .025 is sufficient for the actual Holm family. This
    avoids sizing each component at .80 and incorrectly claiming .80 joint power.
    Report component interval coverage and joint rejection frequency at every n.
    Reduced simulation counts are labeled engineering fixtures, never measured sizing.
    """
    if replicates == 2000 and draws == 10000:
        from validation.tier0_inference import require_acceptance_inference

        # Do not spend CPU on full sizing for a disproven decision procedure.
        # Reduced fixtures may still reproduce its mechanics as diagnostics.
        require_acceptance_inference({})
    task_cov, block_cov = pilot_model(blocks)
    effects, thresholds = np.asarray(effects, dtype=float), np.asarray(thresholds, dtype=float)
    width = task_cov.shape[0]
    if (effects.shape != (width,) or thresholds.shape != (width,)
            or not np.isfinite(effects).all() or not np.isfinite(thresholds).all()
            or np.any(effects <= thresholds)):
        raise ValueError("Freeze a finite planning alternative above every threshold")
    if type(max_sample) is not int or not 5 <= max_sample <= 20 or replicates < 1 or draws < 2:
        raise ValueError("Invalid simulation controls or registered sample cap")
    grid = list(range(5, max_sample + 1)) if candidates is None else sorted(set(candidates))
    if not grid or any(type(n) is not int or not 5 <= n <= max_sample for n in grid):
        raise ValueError("Candidate replicate count outside registered cap")
    curve, chosen = [], None
    for n in grid:
        rng = np.random.default_rng(seed + n)
        passes = 0
        coverage = np.zeros(width)
        for _ in range(replicates):
            task_effects = rng.multivariate_normal(effects, task_cov, size=len(blocks))
            residuals = rng.multivariate_normal(np.zeros(width), block_cov, size=(len(blocks), n))
            bootstrap = joint_bootstrap(task_effects[:, None, :] + residuals, draws, rng)
            lower = np.quantile(bootstrap, 0.025, axis=0)
            p = (1 + (bootstrap <= thresholds).sum(axis=0)) / (draws + 1)
            passes += bool(np.all(lower > thresholds) and np.all(p <= 0.025))
            coverage += lower <= effects
        power = passes / replicates
        curve.append({"blocks_per_task": n, "joint_power": power,
                      "power_mc_se": float(np.sqrt(power * (1 - power) / replicates)),
                      "one_sided_component_coverage": (coverage / replicates).tolist()})
        if power >= 0.8:
            chosen = n
            break
    return {"chosen_n": None, "candidate_chosen_n": chosen, "verdict": "INCONCLUSIVE",
            "curve": curve, "task_covariance_ucb": task_cov.tolist(),
            "block_covariance_ucb": block_cov.tolist(), "family_alpha_used": 0.025,
            "replicates": replicates, "draws": draws, "max_sample": max_sample,
            "engineering_fixture": replicates != 2000 or draws != 10000,
            "scientific_status": "INVALIDATED_INFERENCE",
            "usable_as_registered_sizing_receipt": False,
            "model": "Gaussian task/block effects; marginal upper-80% variance bounds; empirical correlations"}
