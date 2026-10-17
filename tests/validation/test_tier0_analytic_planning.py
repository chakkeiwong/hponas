"""Mathematical invariants for the explicitly model-conditional planning screen."""

import numpy as np
import pytest

from validation.tier0_analytic_planning import (
    conjunction_bounds, continuous_cost_optimal_blocks, gaussian_component_power,
    gaussian_entry_screen, known_variance_repeat_screen, paired_mean_variance,
)


@pytest.mark.parametrize("tasks,blocks,task_var,block_var", [
    (3, 1, .25, 1), (3, 20, .25, 1), (10, 5, 1, 2), (20, 10, 0, 1),
])
def test_boundary_null_rejection_is_alpha_under_the_gaussian_model(tasks, blocks, task_var, block_var):
    assert gaussian_component_power(tasks, blocks, 0, task_var, block_var) == pytest.approx(.025)


def test_more_replicates_cannot_eliminate_between_task_uncertainty():
    floor = .25 / 3
    variance = paired_mean_variance(3, 1_000_000, .25, 1)
    assert variance > floor
    assert variance == pytest.approx(floor, rel=1e-5)
    # Even with infinitely precise task means, three tasks still have only two
    # degrees of freedom. A well-separated task-level alternative remains weak.
    assert gaussian_component_power(3, 1_000_000, .5, .25, 1) < .2


def test_joint_power_bounds_allow_perfect_dependence_and_disjoint_failures():
    lower, upper = conjunction_bounds([.9] * 8)
    assert (lower, upper) == pytest.approx((.2, .9))
    # Eight components succeeding with .8 marginal power cannot establish .8
    # joint power. The usual product also assumes unwarranted independence.
    assert conjunction_bounds([.8] * 8) == (0, .8)
    assert conjunction_bounds([.975] * 8)[0] == pytest.approx(.8)
    assert conjunction_bounds([.8]) == pytest.approx((.8, .8))


def test_known_variance_screen_rejects_irreducible_task_variance():
    impossible = known_variance_repeat_screen(3, .5, .25, 1)
    assert impossible["required_blocks_for_sufficient_bound"] is None
    possible = known_variance_repeat_screen(20, .5, .25, 1, components=8)
    assert possible["required_blocks_for_sufficient_bound"] == 14
    assert possible["coefficient_squared"] == pytest.approx(15.3658352828)


def test_continuous_cost_optimum_beats_neighboring_allocations():
    # Hold variance fixed, so total cost is proportional to
    # (setup + n*block_cost) * (task_variance + block_variance/n).
    n = continuous_cost_optimal_blocks(.25, 1, 5, 1)
    assert n == pytest.approx(np.sqrt(20))
    def cost(r):
        return (5 + r) * (.25 + 1 / r)
    assert cost(n) < min(cost(n * .8), cost(n * 1.2))


def test_planning_screen_is_never_a_registered_sizing_receipt():
    screen = gaussian_entry_screen(30, 5, [.5] * 8, [.25] * 8, [1.] * 8)
    assert screen["joint_power_lower_bound"] > .8
    assert screen["certifies_acceptance"] is False
    assert screen["usable_as_registered_sizing_receipt"] is False
    assert "verdict" not in screen and "chosen_n" not in screen


@pytest.mark.parametrize("call", [
    lambda: gaussian_component_power(1, 5, .5, .25, 1),
    lambda: gaussian_component_power(True, 5, .5, .25, 1),
    lambda: gaussian_component_power(3, 5, float('nan'), .25, 1),
    lambda: gaussian_component_power(3, 5, .5, -.25, 1),
    lambda: gaussian_component_power(3, 5, .5, 0, 0),
    lambda: gaussian_component_power(3, 5, .5, .25, 1, alpha=0),
    lambda: gaussian_entry_screen(3, 5, [.5], [.25, .25], [1]),
    lambda: conjunction_bounds([]),
    lambda: conjunction_bounds([float('inf')]),
    lambda: known_variance_repeat_screen(3, 0, .25, 1),
    lambda: continuous_cost_optimal_blocks(0, 1, 5, 1),
])
def test_invalid_planning_assumptions_fail(call):
    with pytest.raises(ValueError):
        call()
