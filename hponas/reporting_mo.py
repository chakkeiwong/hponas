"""
Multi-objective reporting: Pareto fronts, hypervolume, hypervolume-over-budget.

Survey reference: Ch 7 (multi-objective methods), Ch 16 (V09 validation).
BUILD_PROGRAM_v2.md: Tier 1 MO stack, MO reporting utilities.

This module reports on MO results; it does not optimize. It is deliberately
independent of the store schema, whose Trial row carries a single `value` and
cannot represent named objective vectors without a migration. Callers pass
objective vectors directly.

Conventions:
- All objectives are MINIMIZED. Callers negate maximization objectives.
- Objective arrays are shape (n_points, n_objectives).
- Hypervolume is measured between the front and a reference point that must be
  dominated by (i.e. worse on every objective than) the points being measured.

Validation: V09 (hypervolume over budget), V11a (MO veto logic).
"""

from __future__ import annotations

import numpy as np


def pareto_mask(objectives: np.ndarray) -> np.ndarray:
    """
    Boolean mask of non-dominated rows (minimize all objectives).

    A point is dominated when another point is no worse on every objective and
    strictly better on at least one. Duplicate points do not dominate each other,
    so identical rows are all reported as non-dominated.

    Args:
        objectives: (n_points, n_objectives) array

    Returns:
        Boolean array of length n_points, True where non-dominated
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    n = len(objectives)
    if n == 0:
        return np.zeros(0, dtype=bool)

    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            no_worse = np.all(objectives[j] <= objectives[i])
            strictly_better = np.any(objectives[j] < objectives[i])
            if no_worse and strictly_better:
                is_pareto[i] = False
                break
    return is_pareto


def pareto_front(objectives: np.ndarray) -> np.ndarray:
    """
    Return the non-dominated rows of `objectives`.

    Args:
        objectives: (n_points, n_objectives) array

    Returns:
        (n_front, n_objectives) array of non-dominated points
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    if len(objectives) == 0:
        return objectives.reshape(0, objectives.shape[-1] if objectives.ndim > 1 else 0)
    return objectives[pareto_mask(objectives)]


def hypervolume(objectives: np.ndarray, reference_point: np.ndarray) -> float:
    """
    Hypervolume of the region dominated by `objectives` and bounded by the reference.

    Exact for 2 objectives (sort-and-sweep) and for 3+ objectives via
    inclusion-exclusion over the dominated boxes. Inclusion-exclusion is
    exponential in the size of the front, so 3+ objective fronts are capped;
    see `_hypervolume_inclusion_exclusion`.

    Points not dominating the reference point contribute nothing. This is the
    measure V09 tracks, and unlike the rectangular per-point approximation used
    for MO-ASHA's within-front tie-breaking it does not double-count the
    overlap between points.

    Args:
        objectives: (n_points, n_objectives) array, minimized
        reference_point: (n_objectives,) anti-ideal point

    Returns:
        Hypervolume (0.0 when no point dominates the reference)
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    reference_point = np.asarray(reference_point, dtype=float)

    if objectives.size == 0:
        return 0.0
    if objectives.shape[1] != len(reference_point):
        raise ValueError(
            f"objectives have {objectives.shape[1]} columns but reference point "
            f"has {len(reference_point)} entries"
        )

    # Keep only points strictly better than the reference on every objective.
    # A point equal to the reference on any objective spans zero width there and
    # contributes no volume.
    dominating = objectives[np.all(objectives < reference_point, axis=1)]
    if len(dominating) == 0:
        return 0.0

    # Only the front contributes; dominated points lie inside its region.
    front = dominating[pareto_mask(dominating)]

    n_obj = front.shape[1]
    if n_obj == 1:
        return float(reference_point[0] - np.min(front[:, 0]))
    if n_obj == 2:
        return _hypervolume_2d(front, reference_point)
    return _hypervolume_inclusion_exclusion(front, reference_point)


def _hypervolume_2d(front: np.ndarray, reference_point: np.ndarray) -> float:
    """
    Exact 2-objective hypervolume by sweeping the front.

    Sort by the first objective ascending; on a Pareto front the second
    objective is then descending. Partition the f1 axis into vertical strips
    between consecutive points. In the strip starting at point i the dominating
    points are exactly 0..i, whose lowest second coordinate is f2_i, so the strip
    covers f2_i up to the reference. Strips are disjoint, so their areas sum
    without double-counting overlap.
    """
    order = np.argsort(front[:, 0])
    sorted_front = front[order]

    volume = 0.0
    for i in range(len(sorted_front)):
        f1, f2 = sorted_front[i]
        # Width extends to the next point, or to the reference for the last one.
        next_f1 = sorted_front[i + 1][0] if i + 1 < len(sorted_front) else reference_point[0]
        width = next_f1 - f1
        height = reference_point[1] - f2
        if width > 0 and height > 0:
            volume += width * height
    return float(volume)


# Inclusion-exclusion enumerates 2^k subsets; 20 points is ~1M terms, already slow.
_MAX_INCLUSION_EXCLUSION_POINTS = 20


def _hypervolume_inclusion_exclusion(
    front: np.ndarray, reference_point: np.ndarray
) -> float:
    """
    Exact hypervolume for 3+ objectives via inclusion-exclusion.

    Each point dominates the box between itself and the reference. The union of
    those boxes is the hypervolume; inclusion-exclusion sums signed intersection
    volumes, and the intersection of a set of boxes is the box anchored at the
    element-wise maximum of their corners.

    Raises:
        ValueError: when the front exceeds the point cap. Tier 2 should replace
            this with WFG, which is polynomial in practice.
    """
    n = len(front)
    if n > _MAX_INCLUSION_EXCLUSION_POINTS:
        raise ValueError(
            f"Exact hypervolume for {front.shape[1]} objectives is computed by "
            f"inclusion-exclusion and is capped at {_MAX_INCLUSION_EXCLUSION_POINTS} "
            f"front points; got {n}. Reduce the front or use 2 objectives."
        )

    volume = 0.0
    # Iterate over non-empty subsets via bitmask.
    for mask in range(1, 1 << n):
        corner = np.full(front.shape[1], -np.inf)
        bits = 0
        for i in range(n):
            if mask & (1 << i):
                corner = np.maximum(corner, front[i])
                bits += 1
        side_lengths = reference_point - corner
        if np.all(side_lengths > 0):
            term = float(np.prod(side_lengths))
            # Odd-sized subsets add, even-sized subtract.
            volume += term if bits % 2 == 1 else -term
    return volume


def default_reference_point(
    objectives: np.ndarray, margin: float = 0.1
) -> np.ndarray:
    """
    Reference point derived from observed objectives.

    Takes the worst observed value per objective and pushes it away from the
    front by `margin`. A fixed reference point silently yields zero hypervolume
    whenever the objectives exceed it, which makes comparisons meaningless; this
    keeps the reference dominated by construction.

    The offset is `margin * range` per objective, falling back to
    `margin * |worst|` (and finally to `margin`) when an objective is constant,
    so the reference is strictly worse than every point even at zero.

    Args:
        objectives: (n_points, n_objectives) array, minimized
        margin: Relative padding beyond the worst observed value

    Returns:
        (n_objectives,) reference point
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    if objectives.size == 0:
        raise ValueError("Cannot derive a reference point from zero observations")

    worst = np.max(objectives, axis=0)
    best = np.min(objectives, axis=0)
    spread = worst - best

    offset = margin * spread
    # Constant objectives have zero spread; fall back to magnitude, then to margin.
    degenerate = offset <= 0
    if np.any(degenerate):
        fallback = margin * np.abs(worst)
        fallback = np.where(fallback > 0, fallback, margin)
        offset = np.where(degenerate, fallback, offset)

    return worst + offset


def hypervolume_over_budget(
    objectives: np.ndarray,
    costs: np.ndarray,
    reference_point: np.ndarray | None = None,
    n_points: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Hypervolume of the incumbent front as a function of cumulative budget (V09).

    Trials are consumed in the given order, which is the order they completed.
    At each grid point the hypervolume covers every trial finished within that
    budget, so the curve is monotonically non-decreasing.

    The reference point is computed once over ALL objectives rather than
    per-budget. A reference that moved with the data would make hypervolumes at
    different budgets incomparable, which is exactly the comparison V09 makes.

    Args:
        objectives: (n_trials, n_objectives) array, minimized, in completion order
        costs: (n_trials,) per-trial cost
        reference_point: Fixed reference; derived from all objectives when None
        n_points: Number of budget grid points

    Returns:
        (budgets, hypervolumes), both length <= n_points
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    costs = np.asarray(costs, dtype=float)

    if len(objectives) != len(costs):
        raise ValueError(
            f"Got {len(objectives)} objective rows but {len(costs)} costs"
        )
    if len(objectives) == 0:
        raise ValueError("Cannot compute a hypervolume curve from zero trials")
    if np.any(costs < 0):
        raise ValueError("Trial costs must be non-negative")

    if reference_point is None:
        reference_point = default_reference_point(objectives)
    else:
        reference_point = np.asarray(reference_point, dtype=float)

    cumulative = np.cumsum(costs)
    total = cumulative[-1]
    if total <= 0:
        raise ValueError("Total budget is zero; hypervolume curve is undefined")

    budgets = np.linspace(total / n_points, total, n_points)

    hypervolumes = []
    for budget in budgets:
        # Trials finished within this budget.
        n_done = int(np.searchsorted(cumulative, budget, side="right"))
        if n_done == 0:
            hypervolumes.append(0.0)
            continue
        hypervolumes.append(hypervolume(objectives[:n_done], reference_point))

    return budgets, np.array(hypervolumes)


def summarize_front(
    objectives: np.ndarray,
    objective_names: list[str],
    reference_point: np.ndarray | None = None,
) -> dict:
    """
    Summary of a multi-objective result set.

    Args:
        objectives: (n_trials, n_objectives) array, minimized
        objective_names: Names in the same column order as `objectives`
        reference_point: Fixed reference; derived from observations when None

    Returns:
        dict with keys: n_trials, n_front, front_indices, front, hypervolume,
        reference_point, best_per_objective
    """
    objectives = np.atleast_2d(np.asarray(objectives, dtype=float))
    if objectives.size == 0:
        raise ValueError("Cannot summarize zero trials")
    if objectives.shape[1] != len(objective_names):
        raise ValueError(
            f"objectives have {objectives.shape[1]} columns but got "
            f"{len(objective_names)} objective names"
        )

    if reference_point is None:
        reference_point = default_reference_point(objectives)
    else:
        reference_point = np.asarray(reference_point, dtype=float)

    mask = pareto_mask(objectives)
    front_indices = np.flatnonzero(mask)

    # Index of the single best trial on each objective, useful for reporting the
    # extremes of the trade-off.
    best_per_objective = {
        name: {
            "trial_index": int(np.argmin(objectives[:, i])),
            "value": float(np.min(objectives[:, i])),
        }
        for i, name in enumerate(objective_names)
    }

    return {
        "n_trials": int(len(objectives)),
        "n_front": int(mask.sum()),
        "front_indices": front_indices.tolist(),
        "front": objectives[mask].tolist(),
        "hypervolume": hypervolume(objectives, reference_point),
        "reference_point": reference_point.tolist(),
        "best_per_objective": best_per_objective,
    }
