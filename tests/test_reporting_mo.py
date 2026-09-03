"""
Test multi-objective reporting utilities.

BUILD_PROGRAM_v2.md: Tier 1 MO stack, MO reporting utilities (~2d).
Validation: V09 (hypervolume over budget).
"""

import numpy as np
import pytest

from hponas.reporting_mo import (
    default_reference_point,
    hypervolume,
    hypervolume_over_budget,
    pareto_front,
    pareto_mask,
    summarize_front,
)


def test_pareto_mask_identifies_dominated_points():
    """A point worse on every objective is dominated."""
    objectives = np.array([
        [1.0, 1.0],  # dominates the third point
        [2.0, 0.5],  # trade-off: better on f2
        [3.0, 3.0],  # dominated by the first
    ])

    mask = pareto_mask(objectives)

    assert mask.tolist() == [True, True, False]


def test_pareto_mask_keeps_duplicates():
    """Identical points do not dominate each other, so both stay on the front."""
    objectives = np.array([
        [1.0, 2.0],
        [1.0, 2.0],
    ])

    mask = pareto_mask(objectives)

    assert mask.tolist() == [True, True]


def test_pareto_mask_weak_dominance_is_not_dominance():
    """Equal on one objective and equal on the other is not domination."""
    # [1, 2] vs [1, 3]: first is no worse everywhere and strictly better on f2.
    objectives = np.array([
        [1.0, 2.0],
        [1.0, 3.0],
    ])

    mask = pareto_mask(objectives)

    assert mask.tolist() == [True, False]


def test_pareto_mask_empty_input():
    """Zero points yields an empty mask rather than an error."""
    assert pareto_mask(np.zeros((0, 2))).tolist() == []


def test_pareto_front_returns_only_nondominated():
    objectives = np.array([
        [1.0, 5.0],
        [5.0, 1.0],
        [6.0, 6.0],
    ])

    front = pareto_front(objectives)

    assert len(front) == 2
    assert [6.0, 6.0] not in front.tolist()


def test_hypervolume_2d_single_point():
    """One point dominating the reference spans a rectangle."""
    # Point (1, 1), reference (3, 3) -> 2 x 2 = 4
    hv = hypervolume(np.array([[1.0, 1.0]]), np.array([3.0, 3.0]))

    assert hv == pytest.approx(4.0)


def test_hypervolume_2d_two_points_hand_computed():
    """
    Two-point front against a hand-computed value.

    Points (1, 3) and (2, 1) with reference (4, 4).
    Sweeping on f1: (1,3) contributes width (2-1)=1 x height (4-3)=1 = 1.
                    (2,1) contributes width (4-2)=2 x height (4-1)=3 = 6.
    Total = 7. Note the naive per-point rectangle sum would give
    (4-1)(4-3) + (4-2)(4-1) = 3 + 6 = 9, double-counting the overlap.
    """
    front = np.array([[1.0, 3.0], [2.0, 1.0]])

    hv = hypervolume(front, np.array([4.0, 4.0]))

    assert hv == pytest.approx(7.0)


def test_hypervolume_ignores_dominated_points():
    """Adding a dominated point does not change the hypervolume."""
    reference = np.array([4.0, 4.0])
    front = np.array([[1.0, 3.0], [2.0, 1.0]])
    with_dominated = np.vstack([front, [3.0, 3.5]])

    assert hypervolume(with_dominated, reference) == pytest.approx(
        hypervolume(front, reference)
    )


def test_hypervolume_monotone_under_improvement():
    """A strictly better front has strictly larger hypervolume."""
    reference = np.array([4.0, 4.0])
    worse = np.array([[2.0, 2.0]])
    better = np.array([[1.0, 1.0]])

    assert hypervolume(better, reference) > hypervolume(worse, reference)


def test_hypervolume_zero_when_reference_dominated():
    """Points worse than the reference contribute nothing."""
    # Reference (1, 1) is better than the point on both objectives.
    hv = hypervolume(np.array([[2.0, 2.0]]), np.array([1.0, 1.0]))

    assert hv == 0.0


def test_hypervolume_zero_on_reference_boundary():
    """A point equal to the reference on one objective spans zero width."""
    hv = hypervolume(np.array([[1.0, 3.0]]), np.array([3.0, 3.0]))

    assert hv == 0.0


def test_hypervolume_empty_input_is_zero():
    assert hypervolume(np.zeros((0, 2)), np.array([1.0, 1.0])) == 0.0


def test_hypervolume_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="reference point"):
        hypervolume(np.array([[1.0, 2.0]]), np.array([3.0, 3.0, 3.0]))


def test_hypervolume_3d_single_point_hand_computed():
    """Three objectives: (1,1,1) against reference (3,3,3) is a 2x2x2 cube."""
    hv = hypervolume(np.array([[1.0, 1.0, 1.0]]), np.array([3.0, 3.0, 3.0]))

    assert hv == pytest.approx(8.0)


def test_hypervolume_3d_two_points_inclusion_exclusion():
    """
    Two 3-objective points with a hand-computed union volume.

    A = (1,1,2), B = (1,2,1), reference (3,3,3).
    vol(A) = 2*2*1 = 4;  vol(B) = 2*1*2 = 4.
    Intersection is anchored at the element-wise max (1,2,2) -> 2*1*1 = 2.
    Union = 4 + 4 - 2 = 6.
    """
    front = np.array([[1.0, 1.0, 2.0], [1.0, 2.0, 1.0]])

    hv = hypervolume(front, np.array([3.0, 3.0, 3.0]))

    assert hv == pytest.approx(6.0)


def test_hypervolume_3d_matches_2d_when_third_objective_constant():
    """Cross-check the two code paths against each other."""
    front_2d = np.array([[1.0, 3.0], [2.0, 1.0]])
    reference_2d = np.array([4.0, 4.0])

    # Pad with a constant objective one unit better than its reference, so the
    # third dimension contributes a factor of exactly 1.
    front_3d = np.hstack([front_2d, np.zeros((2, 1))])
    reference_3d = np.array([4.0, 4.0, 1.0])

    assert hypervolume(front_3d, reference_3d) == pytest.approx(
        hypervolume(front_2d, reference_2d)
    )


def test_hypervolume_3d_rejects_oversized_front():
    """The inclusion-exclusion cap fails loudly instead of hanging."""
    # Build a guaranteed oversized Pareto front by constructing points that
    # don't dominate each other. Use (i, 25-i, 0) for i=0..24 -> 25 front points.
    front = np.array([[float(i), float(25 - i), 0.0] for i in range(25)])

    with pytest.raises(ValueError, match="capped"):
        hypervolume(front, np.array([26.0, 26.0, 1.0]))


def test_default_reference_point_is_dominated_by_all_points():
    """Every observation must be strictly better than the derived reference."""
    objectives = np.array([
        [1.0, 10.0],
        [5.0, 2.0],
        [3.0, 6.0],
    ])

    reference = default_reference_point(objectives)

    assert np.all(objectives < reference)


def test_default_reference_point_handles_constant_objective():
    """A constant objective has zero spread; the reference must still clear it."""
    objectives = np.array([
        [1.0, 5.0],
        [2.0, 5.0],
    ])

    reference = default_reference_point(objectives)

    assert reference[1] > 5.0
    assert np.all(objectives < reference)


def test_default_reference_point_handles_all_zero_objective():
    """Zero magnitude and zero spread still yields a strictly worse reference."""
    objectives = np.array([
        [0.0, 1.0],
        [0.0, 2.0],
    ])

    reference = default_reference_point(objectives)

    assert reference[0] > 0.0
    assert np.all(objectives < reference)


def test_default_reference_point_rejects_empty():
    with pytest.raises(ValueError, match="zero observations"):
        default_reference_point(np.zeros((0, 2)))


def test_hypervolume_over_budget_is_nondecreasing():
    """Accumulating trials can only grow the dominated region."""
    rng = np.random.RandomState(42)
    objectives = rng.uniform(0, 1, size=(30, 2))
    costs = np.ones(30)

    budgets, hvs = hypervolume_over_budget(objectives, costs, n_points=10)

    assert len(budgets) == 10
    assert np.all(np.diff(hvs) >= -1e-12)


def test_hypervolume_over_budget_reaches_full_front():
    """The last grid point covers every trial."""
    objectives = np.array([[1.0, 3.0], [2.0, 1.0], [3.0, 0.5]])
    costs = np.array([1.0, 1.0, 1.0])
    reference = np.array([4.0, 4.0])

    budgets, hvs = hypervolume_over_budget(
        objectives, costs, reference_point=reference, n_points=3
    )

    assert budgets[-1] == pytest.approx(3.0)
    assert hvs[-1] == pytest.approx(hypervolume(objectives, reference))


def test_hypervolume_over_budget_respects_uneven_costs():
    """An expensive first trial delays when later trials enter the curve."""
    objectives = np.array([[3.0, 3.0], [1.0, 1.0]])
    costs = np.array([9.0, 1.0])
    reference = np.array([4.0, 4.0])

    budgets, hvs = hypervolume_over_budget(
        objectives, costs, reference_point=reference, n_points=10
    )

    # The first trial costs 9, so budget < 9 sees nothing.
    # At budget 10 (the final point) both trials are in.
    first_only_hv = hypervolume(objectives[:1], reference)
    both_hv = hypervolume(objectives, reference)

    assert hvs[0] <= first_only_hv + 1e-9  # May be zero or first-only depending on grid
    assert hvs[-1] == pytest.approx(both_hv)
    assert hvs[-1] > hvs[0]


def test_hypervolume_over_budget_rejects_length_mismatch():
    with pytest.raises(ValueError, match="costs"):
        hypervolume_over_budget(np.array([[1.0, 1.0]]), np.array([1.0, 2.0]))


def test_hypervolume_over_budget_rejects_empty():
    with pytest.raises(ValueError, match="zero trials"):
        hypervolume_over_budget(np.zeros((0, 2)), np.zeros(0))


def test_hypervolume_over_budget_rejects_negative_cost():
    with pytest.raises(ValueError, match="non-negative"):
        hypervolume_over_budget(np.array([[1.0, 1.0]]), np.array([-1.0]))


def test_hypervolume_over_budget_rejects_zero_budget():
    with pytest.raises(ValueError, match="budget is zero"):
        hypervolume_over_budget(np.array([[1.0, 1.0]]), np.array([0.0]))


def test_summarize_front_reports_counts_and_extremes():
    objectives = np.array([
        [1.0, 5.0],  # best on loss
        [5.0, 1.0],  # best on latency
        [6.0, 6.0],  # dominated
    ])

    summary = summarize_front(objectives, ["loss", "latency"])

    assert summary["n_trials"] == 3
    assert summary["n_front"] == 2
    assert summary["front_indices"] == [0, 1]
    assert summary["best_per_objective"]["loss"]["trial_index"] == 0
    assert summary["best_per_objective"]["latency"]["trial_index"] == 1
    assert summary["hypervolume"] > 0.0


def test_summarize_front_is_json_serializable():
    """Summaries get written to gate reports, so no numpy types may leak."""
    import json

    objectives = np.array([[1.0, 2.0], [2.0, 1.0]])

    summary = summarize_front(objectives, ["f1", "f2"])

    json.dumps(summary)  # raises TypeError on numpy scalars


def test_summarize_front_rejects_name_mismatch():
    with pytest.raises(ValueError, match="objective names"):
        summarize_front(np.array([[1.0, 2.0]]), ["only_one"])


def test_summarize_front_rejects_empty():
    with pytest.raises(ValueError, match="zero trials"):
        summarize_front(np.zeros((0, 2)), ["f1", "f2"])
