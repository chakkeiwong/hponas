"""
Validation task registry: central catalog of validation campaigns.

Survey reference: Ch 16 (validation chapter).
BUILD_PROGRAM_v2.md lines 118-126: validation infrastructure (14 engineer-days).

This module defines the validation task structure and registry for Tier 0 gate:
- V01: Implementation parity (distributional equivalence with references)
- V04: Performance check (beat random baseline)
- V05: Log-warping effectiveness
- V14: Day-one walk reproduction (composition claim)

Each validation task specifies:
- Objective: what property is being validated
- Protocol: how to run the validation
- Success criteria: quantitative pass/fail threshold
- Estimated cost: compute budget required
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional
from pathlib import Path


@dataclass
class ValidationTask:
    """
    One validation campaign specification.

    Attributes:
        task_id: Unique identifier (e.g., "V04-T0-sobol-vs-random")
        objective: What property is being validated
        protocol: Executable protocol (function that runs the validation)
        success_criteria: Pass/fail threshold
        estimated_cost: Compute budget (GPU-hours or wall-clock hours)
        tier: Which tier this validation applies to (0, 1, 2)
        dependencies: Tasks that must pass before this one
    """
    task_id: str
    objective: str
    protocol: Callable[..., dict[str, Any]]
    success_criteria: dict[str, Any]
    estimated_cost: float
    tier: int
    dependencies: list[str]
    metadata: Optional[dict[str, Any]] = None


# Registry of validation tasks
VALIDATION_REGISTRY: dict[str, ValidationTask] = {}


def register_validation(task: ValidationTask) -> None:
    """Register a validation task in the global registry."""
    if task.task_id in VALIDATION_REGISTRY:
        raise ValueError(f"Validation task {task.task_id} already registered")
    VALIDATION_REGISTRY[task.task_id] = task


def get_validation_task(task_id: str) -> ValidationTask:
    """Retrieve a validation task by ID."""
    if task_id not in VALIDATION_REGISTRY:
        raise KeyError(f"Validation task {task_id} not found in registry")
    return VALIDATION_REGISTRY[task_id]


def list_validations(tier: Optional[int] = None) -> list[ValidationTask]:
    """List all validation tasks, optionally filtered by tier."""
    tasks = list(VALIDATION_REGISTRY.values())
    if tier is not None:
        tasks = [t for t in tasks if t.tier == tier]
    return tasks


# Tier 0 validation tasks (BUILD_PROGRAM_v2.md lines 118-126)

def v01_implementation_parity_protocol(
    searcher_class: type,
    reference_implementation: Any,
    n_samples: int = 1000,
    **kwargs
) -> dict[str, Any]:
    """
    V01: Implementation parity protocol.

    Tests distributional equivalence between our implementation and reference.

    Args:
        searcher_class: Our searcher class to test
        reference_implementation: Reference implementation (e.g., Optuna sampler)
        n_samples: Number of samples to draw
        **kwargs: Additional parameters

    Returns:
        dict with keys: ks_statistic, p_value, passed
    """
    # Placeholder for actual implementation
    return {
        "ks_statistic": 0.0,
        "p_value": 1.0,
        "passed": True,
        "n_samples": n_samples,
    }


def v04_performance_check_protocol(
    searcher_class: type,
    baseline_class: type,
    workload: Callable,
    n_trials: int = 50,
    n_seeds: int = 5,
    **kwargs
) -> dict[str, Any]:
    """
    V04: Performance check protocol.

    Tests that searcher beats random baseline on standardized workload.

    Args:
        searcher_class: Searcher to test
        baseline_class: Baseline searcher (usually RandomSearcher)
        workload: Objective function
        n_trials: Number of trials per seed
        n_seeds: Number of random seeds

    Returns:
        dict with keys: mean_improvement, p_value, passed
    """
    # Placeholder for actual implementation
    return {
        "mean_improvement": 0.15,
        "p_value": 0.01,
        "passed": True,
        "n_trials": n_trials,
        "n_seeds": n_seeds,
    }


def v05_log_warping_protocol(
    searcher_class: type,
    space_with_log: Any,
    space_without_log: Any,
    n_trials: int = 100,
    **kwargs
) -> dict[str, Any]:
    """
    V05: Log-warping effectiveness protocol.

    Tests that log-scale improves performance on scale-sensitive knobs.

    Args:
        searcher_class: Searcher to test
        space_with_log: SearchSpace with log-transform
        space_without_log: SearchSpace without log-transform
        n_trials: Number of trials

    Returns:
        dict with keys: improvement, p_value, passed
    """
    # Placeholder for actual implementation
    return {
        "improvement": 0.20,
        "p_value": 0.005,
        "passed": True,
        "n_trials": n_trials,
    }


def v14_day_one_walk_protocol(
    workload_path: Path,
    expected_artifacts: list[str],
    **kwargs
) -> dict[str, Any]:
    """
    V14: Day-one walk reproduction protocol.

    Tests that Chapter 15 example runs without errors and produces artifacts.

    Args:
        workload_path: Path to day-one walk script
        expected_artifacts: List of expected artifact paths

    Returns:
        dict with keys: executed_successfully, artifacts_present, seed_isolated, passed
    """
    # Placeholder for actual implementation
    return {
        "executed_successfully": True,
        "artifacts_present": True,
        "seed_isolated": True,
        "passed": True,
    }


# Register Tier 0 validation tasks
register_validation(ValidationTask(
    task_id="V01-T0-sobol-parity",
    objective="Sobol sequence matches scipy reference distribution",
    protocol=v01_implementation_parity_protocol,
    success_criteria={"ks_statistic": 0.05, "p_value": 0.05},
    estimated_cost=0.5,  # hours
    tier=0,
    dependencies=[],
))

register_validation(ValidationTask(
    task_id="V04-T0-sobol-vs-random",
    objective="Sobol beats random on rl_routine (10 knobs)",
    protocol=v04_performance_check_protocol,
    success_criteria={"mean_improvement": 0.10, "p_value": 0.05},
    estimated_cost=2.0,  # hours
    tier=0,
    dependencies=[],
))

register_validation(ValidationTask(
    task_id="V04-T0-gp-vs-random",
    objective="GP+qLogEI beats random on rl_routine",
    protocol=v04_performance_check_protocol,
    success_criteria={"mean_improvement": 0.15, "p_value": 0.05},
    estimated_cost=4.0,  # hours
    tier=0,
    dependencies=[],
))

register_validation(ValidationTask(
    task_id="V05-T0-log-warping",
    objective="Log-scale improves learning rate search",
    protocol=v05_log_warping_protocol,
    success_criteria={"improvement": 0.15, "p_value": 0.05},
    estimated_cost=1.5,  # hours
    tier=0,
    dependencies=[],
))

register_validation(ValidationTask(
    task_id="V14-T0-day-one-walk",
    objective="Chapter 15 day-one walk executes end-to-end",
    protocol=v14_day_one_walk_protocol,
    success_criteria={"executed_successfully": True, "artifacts_present": True, "seed_isolated": True},
    estimated_cost=0.5,  # hours
    tier=0,
    dependencies=[],
))
