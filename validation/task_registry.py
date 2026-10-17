"""
Validation task registry: central catalog of validation campaigns.

Survey reference: Ch 16 (validation chapter).
BUILD_PROGRAM_v2.md lines 118-126: validation infrastructure (14 engineer-days).

This module defines the validation task structure and registry for Tier 0 gate:
- V01: Exact finite-corpus conformance to named references
- V02: Complete recorded event and runtime conformance
- V04-T0: Finite known-answer model and search trace conformance
- V05: Finite log/linear coordinate and paired physical initialization conformance
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


def audited_protocol(
    validation_id, artifact_root=None, smoke=False, run_mutations=False,
    design_path=None, phase="confirmation",
):
    """Execute the fixed campaign for an ID and return its independently audited verdict."""
    import json
    from validation.run_validation_with_audit import ValidationRunner
    from validation.protocol_identity import canonical_id
    from validation.tier1_contract import ENTRIES as TIER1
    validation_id = canonical_id(validation_id)

    if validation_id in {"V04-T0", "V05", 'V07', 'V08', 'V12', 'V15a', *TIER1} and (design_path or smoke or phase != "confirmation"):
        raise ValueError("Legacy PPO design/phase/smoke arguments are retired for the stylized gates")
    runner = ValidationRunner(validation_id, artifact_root=artifact_root)
    if validation_id == 'V07':
        from validation.dehb_finite import campaign
        fn = lambda: campaign(runner.run_dir)
    elif validation_id == 'V12':
        from validation.warm_finite_campaign import campaign
        fn = lambda: campaign(runner.run_dir)
    elif validation_id == 'V15a':
        from validation.ifbo_finite_campaign import campaign
        fn = lambda: campaign(runner.run_dir)
    elif validation_id == 'V08':
        from validation.population_campaign import campaign
        fn = lambda: campaign(runner.run_dir)
    elif validation_id in TIER1:
        from validation.tier1_campaign import campaign
        fn = lambda: campaign(validation_id, runner.run_dir)
    elif validation_id == "V01":
        from validation.v01_finite_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif validation_id == "V02":
        from validation.v02_final_campaign import campaign

        fn = lambda: campaign(runner.run_dir)
    elif validation_id == "V03":
        from validation.v03_mutation_testing import campaign

        fn = lambda: campaign(run=run_mutations)
    elif validation_id == "V14":
        from validation.v14_day_one_walk import campaign

        fn = lambda: campaign(runner.run_dir)
    else:
        from validation.stylized_campaign import campaign

        fn = lambda: campaign(validation_id, runner.run_dir)
    passed = runner.run(fn)
    result = json.loads((runner.run_dir / "results.json").read_text())
    result.update(passed=passed, artifact_run=str(runner.run_dir))
    return result


from functools import partial

for validation_id, objective, hours in [
    ("V01", "Complete finite-corpus conformance to nine named references", 1 / 6),
    ("V02", "Complete recorded event, raw recovery and runtime conformance", 1 / 6),
    ("V03", "Module and critical-path mutation criteria", 6.0),
    ("V04-T0", "Known-answer numerical, search trace and accounting conformance", .25),
    ("V05", "Log/linear coordinate conformance with paired physical initialization", .15),
    ("V14", "Real bounded day-one walk and protected evaluation", 0.02),
]:
    register_validation(
        ValidationTask(
            validation_id,
            objective,
            partial(audited_protocol, validation_id),
            {"passed": True},
            hours,
            0,
            [],
        )
    )

from validation.tier1_contract import ENTRIES as TIER1

for validation_id in TIER1:
    register_validation(ValidationTask(validation_id,
        'Frozen finite known-answer conformance; no default or population claim',
        partial(audited_protocol, validation_id), {'passed': True}, 300/3600, 1, []))

register_validation(ValidationTask('V08',
    'Frozen finite local population conformance; no default or statistical ranking claim',
    partial(audited_protocol, 'V08'), {'passed': True}, 300/3600, 2, []))

register_validation(ValidationTask('V07',
    'Frozen finite native DEHB method and mathematical training conformance',
    partial(audited_protocol, 'V07'), {'passed': True}, 300/3600, 3, []))

register_validation(ValidationTask('V15a',
    'Frozen finite original pretrained ifBO feasibility; non-PASS cancels integration',
    partial(audited_protocol, 'V15a'), {'passed': True}, 300/3600, 3, []))

register_validation(ValidationTask('V12',
    'Frozen finite ranked warm-start conformance; no empirical speedup or service claim',
    partial(audited_protocol, 'V12'), {'passed': True}, 300/3600, 1, []))
