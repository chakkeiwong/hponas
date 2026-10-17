"""Analytic feasibility screening; never an acceptance or pilot-sizing receipt.

Assume independent, identically distributed Gaussian task effects and Gaussian
paired-block residuals, with balanced replication. A component's task means are
iid normal, so a one-sample task-mean t test has a noncentral t power function.
Parameters here are supplied assumptions, not estimates from unrun experiments.
The registered bootstrap analysis is not replaced by this planning module.
"""

from __future__ import annotations

import math

from scipy.stats import nct, norm, t


MODEL = "iid Gaussian task effects and paired-block residuals; balanced task-mean t test"


def _count(value, name, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _finite(value, name, *, nonnegative=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (nonnegative and value < 0)):
        raise ValueError(f"Invalid {name}")


def _probability(value, name):
    _finite(value, name)
    if not 0 < value < 1:
        raise ValueError(f"{name} must lie strictly between zero and one")


def paired_mean_variance(tasks, blocks, task_variance, block_variance):
    """Var(mean improvement) = between-task variance/T + within-task variance/(T*n)."""
    _count(tasks, "tasks", 2)
    _count(blocks, "blocks", 1)
    _finite(task_variance, "task_variance", nonnegative=True)
    _finite(block_variance, "block_variance", nonnegative=True)
    variance = (task_variance + block_variance / blocks) / tasks
    if not math.isfinite(variance) or variance <= 0:
        raise ValueError("A finite positive sampling variance is required")
    return variance


def gaussian_component_power(tasks, blocks, gap, task_variance, block_variance, *, alpha=.025):
    """Exact t-test power under this Gaussian model, with T-1 degrees of freedom.

    gap is true mean minus null margin; a zero gap has power alpha. This is not
    the power of the currently registered percentile bootstrap.
    """
    _finite(gap, "gap")
    _probability(alpha, "alpha")
    variance = paired_mean_variance(tasks, blocks, task_variance, block_variance)
    noncentrality = gap / math.sqrt(variance)
    if not math.isfinite(noncentrality):
        raise ValueError("Noncentrality must be finite")
    result = float(nct.sf(t.isf(alpha, tasks - 1), tasks - 1, noncentrality))
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError("Numerical power evaluation failed")
    return result


def conjunction_bounds(marginal_powers):
    """Frechet/union bounds, valid for every dependence between component tests.

    Power of ALL components lies between max(0, 1-sum(1-p_j)) and min(p_j).
    No product-of-powers independence assumption is made.
    """
    powers = list(marginal_powers)
    if not powers:
        raise ValueError("At least one component is required")
    for value in powers:
        _finite(value, "component power")
        if not 0 <= value <= 1:
            raise ValueError("Component powers must lie in [0, 1]")
    return max(0.0, 1.0 - math.fsum(1.0 - p for p in powers)), min(powers)


def gaussian_entry_screen(tasks, blocks, gaps, task_variances, block_variances, *, alpha=.025):
    """Model-conditional bounds for an intersection-union entry, without simulations.

    Use .025 per component as a sufficient first Holm step for a two-entry .05
    family. Eight required V04 components do NOT require alpha/8: their null is
    a union. Joint power, however, must account for eight possible failures.
    """
    gaps, task_variances, block_variances = map(list, (gaps, task_variances, block_variances))
    if not gaps or len({len(gaps), len(task_variances), len(block_variances)}) != 1:
        raise ValueError("Component arrays must have the same positive length")
    powers = [gaussian_component_power(tasks, blocks, gap, between, within, alpha=alpha)
              for gap, between, within in zip(gaps, task_variances, block_variances, strict=True)]
    lower, upper = conjunction_bounds(powers)
    return {"kind": "analytic_feasibility_screen", "certifies_acceptance": False,
            "usable_as_registered_sizing_receipt": False, "model": MODEL,
            "tasks": tasks, "blocks_per_task": blocks, "component_alpha": alpha,
            "component_powers": powers, "joint_power_lower_bound": lower,
            "joint_power_upper_bound": upper,
            "assumptions": {"gaps": gaps, "task_variances": task_variances,
                            "block_variances": block_variances}}


def known_variance_repeat_screen(tasks, gap, task_variance, block_variance, *,
                                 components=1, alpha=.025, joint_power=.8):
    """Closed-form sufficient planning screen for a known-variance normal test.

    Allocating failure probability (1-power)/m to each of m required components
    gives K = z_(1-alpha) + z_(1-(1-power)/m). Need
    tau^2 + sigma^2/n <= T * (gap/K)^2. This is NOT a small-T t-test guarantee.
    """
    paired_mean_variance(tasks, 1, task_variance, block_variance)
    _count(components, "components", 1)
    _finite(gap, "gap")
    _probability(alpha, "alpha")
    _probability(joint_power, "joint_power")
    if gap <= 0:
        raise ValueError("A positive planning alternative is required")
    component_power = 1 - (1 - joint_power) / components
    if component_power <= alpha or component_power >= 1:
        raise ValueError("Requested component power must be above alpha and below one")
    coefficient = float(norm.isf(alpha) + norm.ppf(component_power))
    remaining = tasks * (gap / coefficient) ** 2 - task_variance
    if remaining < 0 or (remaining == 0 and block_variance > 0):
        blocks = None
    elif block_variance == 0:
        blocks = 1
    else:
        blocks = max(1, math.ceil(block_variance / remaining))
    return {"kind": "known_variance_normal_screen", "certifies_acceptance": False,
            "component_power_target": component_power, "coefficient_squared": coefficient ** 2,
            "between_task_variance_floor": task_variance / tasks,
            "required_blocks_for_sufficient_bound": blocks,
            "finite_block_count_can_meet_bound": blocks is not None,
            "note": "Conditional on supplied moments, known variance and normal test; use finite-task power for unknown variance."}


def continuous_cost_optimal_blocks(task_variance, block_variance, setup_cost, block_cost):
    """Continuous known-variance allocation: n* = sqrt(c0*sigma^2/(c1*tau^2)).

    Minimizes T*(c0+n*c1) at fixed variance, before integer/task-cap constraints.
    c0 can include a fixed pilot per task; c1 is cost of one full paired block.
    Does not select tasks or certify a sample count.
    """
    for name, value in (('task_variance', task_variance), ('block_variance', block_variance),
                        ('setup_cost', setup_cost), ('block_cost', block_cost)):
        _finite(value, name, nonnegative=True)
    if task_variance == 0 or block_cost == 0:
        raise ValueError("Positive between-task variance and per-block cost are needed for this interior optimum")
    return math.sqrt(setup_cost / block_cost * block_variance / task_variance)
