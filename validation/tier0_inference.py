"""Tier 0 inference contracts and diagnostic alternatives.

The task-mean t calculation is exact for iid Gaussian task means. It does not
establish that the benchmark sampling design supplies those assumptions. The
adopted bounded rank contract still requires an evidence-supported sampling design
and protected artifact execution; a bare mathematical method label is insufficient.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.stats import t

from validation.stats import Cluster


INVALIDATED_METHOD = "paired_cluster_percentile"
INVALIDATION_REASON = (
    "STAT-03: paired task/block percentile inference is invalidated by the "
    "three-task null counterexample; a validated replacement and final design are required"
)


def require_acceptance_inference(analysis):
    """Refuse invalid inference and require the whole adopted rank contract.

    The existing schema's implicit method is the invalidated percentile test.
    A caller-supplied method label cannot certify the model-conditional preview.
    The surrounding design and campaign guards own actual sampling assumptions,
    protected outcomes and source/protocol identity; resource permission is separate.
    """
    method = analysis.get("method", INVALIDATED_METHOD)
    if method == INVALIDATED_METHOD:
        raise ValueError(INVALIDATION_REASON)
    from validation.tier0_design import RANK_ANALYSIS

    if analysis == RANK_ANALYSIS:
        # The whole reviewed contract is necessary. Campaign readiness must also
        # verify scope, protected artifacts and sampling assumptions from evidence.
        return
    raise ValueError(f"STAT-03: no validated acceptance replacement for {method!r}")


def task_mean_t_statistics(task_means, *, margin=0.0, alpha=.025):
    """Vectorized candidate statistic over the last axis of independent task means.

    With iid Gaussian task means and nonzero variance, its pivot is t_(T-1).
    This is not an exact distribution-free test of a mean. The vectorized form
    supports cheap assumption stress checks without bootstrap or workload runs.
    """
    if (isinstance(margin, bool) or not isinstance(margin, (int, float))
            or not math.isfinite(margin)):
        raise ValueError("Finite scalar margin required")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("Alpha must be strictly between zero and one")
    means = np.asarray(task_means, dtype=float)
    if means.ndim < 1 or means.shape[-1] < 2 or not means.size or not np.isfinite(means).all():
        raise ValueError("At least two finite task means are required")
    count = means.shape[-1]
    point = means.mean(axis=-1)
    standard_error = means.std(axis=-1, ddof=1) / math.sqrt(count)
    if not np.isfinite(standard_error).all() or np.any(standard_error <= 0):
        raise ValueError("Positive task-level variance is required; identical means cannot certify a population claim")
    statistic = (point - margin) / standard_error
    p_value = t.sf(statistic, count - 1)
    lower = point - t.isf(alpha, count - 1) * standard_error
    if not all(np.isfinite(value).all() for value in (point, statistic, p_value, lower)):
        raise ValueError("Nonfinite candidate statistic")
    return {"point": point, "standard_error": standard_error, "statistic": statistic,
            "p_value": p_value, "lower_bound": lower, "df": count - 1}


def preview_task_mean_t(clusters: Sequence[Cluster], *, margin=0.0, alpha=.025):
    """Analyze balanced complete paired blocks as a model-conditional preview only.

    Collapse within-task blocks before inference. Repeating a task's blocks does
    not create independent tasks or increase degrees of freedom. Unequal counts
    and missingness need a separately justified design and are not inferred here.
    """
    if len(clusters) < 2 or len({cluster.task for cluster in clusters}) != len(clusters):
        raise ValueError("At least two distinct independent task IDs are required")
    if any(not isinstance(c.task, str) or not c.task for c in clusters):
        raise ValueError("Nonempty task IDs are required")
    if any(c.differences.ndim != 1 or c.n_blocks < 2 or not np.isfinite(c.differences).all()
           for c in clusters):
        raise ValueError("Each task needs at least two finite complete paired blocks")
    sizes = {c.n_blocks for c in clusters}
    if len(sizes) != 1:
        raise ValueError("The Gaussian candidate requires balanced paired blocks")
    stats = task_mean_t_statistics([c.mean for c in clusters], margin=margin, alpha=alpha)
    result = {k: int(v) if k == "df" else float(v) for k, v in stats.items()}
    result.update(method="gaussian_task_mean_t_preview", alpha=alpha, margin=margin,
                  n_tasks=len(clusters), blocks_per_task=next(iter(sizes)),
                  candidate_clears=bool(result['p_value'] <= alpha and result['lower_bound'] > margin),
                  verdict="INCONCLUSIVE", certifies_acceptance=False,
                  scientific_status="MODEL_CONDITIONAL_PREVIEW",
                  assumptions="Independent identically distributed Gaussian task means; balanced complete blocks; justified task-population sampling")
    return result
