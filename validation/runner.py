"""
Validation campaign runner: executes validation tasks and generates reports.

Survey reference: Ch 16 (validation chapter).
BUILD_PROGRAM_v2.md lines 118-126: validation infrastructure (14 engineer-days).

The runner:
- Executes validation tasks from the registry
- Tracks dependencies (e.g., V04 requires contract tests passing)
- Generates structured reports for gate reviews
- Supports parallel execution for independent tasks
- Provides cost estimation before running campaigns

Tier 0 gate criteria (BUILD_PROGRAM_v2.md lines 58-65):
- All contracts pass
- V01 (implementation parity): Sobol, TPE match references
- V04 (performance): Sobol, GP beat random baseline
- V05 (log-warping): demonstrates effectiveness
- V14 (day-one walk): Chapter 15 example executes
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import json

from .task_registry import ValidationTask, get_validation_task, list_validations


@dataclass
class ValidationResult:
    """Result of running one validation task."""
    task_id: str
    passed: bool
    metrics: dict[str, Any]
    execution_time: float
    error: Optional[str] = None


class ValidationRunner:
    """
    Execute validation campaigns and generate reports.

    Usage:
        runner = ValidationRunner(output_dir="./validation_results")
        results = runner.run_tier(tier=0)
        report = runner.generate_report(results)
    """

    def __init__(self, output_dir: str | Path = "./validation_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[ValidationResult] = []

    def run_task(self, task_id: str, **kwargs) -> ValidationResult:
        """
        Execute a single validation task.

        Args:
            task_id: Validation task identifier
            **kwargs: Additional arguments passed to protocol

        Returns:
            ValidationResult with pass/fail and metrics
        """
        print(f"\n=== Running validation: {task_id} ===")

        task = get_validation_task(task_id)

        # Check dependencies
        for dep_id in task.dependencies:
            dep_passed = any(r.task_id == dep_id and r.passed for r in self.results)
            if not dep_passed:
                print(f"  Dependency {dep_id} not satisfied, skipping")
                return ValidationResult(
                    task_id=task_id,
                    passed=False,
                    metrics={},
                    execution_time=0.0,
                    error=f"Dependency {dep_id} not satisfied"
                )

        print(f"  Objective: {task.objective}")
        print(f"  Estimated cost: {task.estimated_cost:.1f} hours")

        # Execute protocol
        start_time = time.time()
        try:
            result_metrics = task.protocol(**kwargs)
            execution_time = time.time() - start_time

            # Check success criteria
            passed = self._check_criteria(result_metrics, task.success_criteria)

            result = ValidationResult(
                task_id=task_id,
                passed=passed,
                metrics=result_metrics,
                execution_time=execution_time,
            )

            status = "✓ PASSED" if passed else "✗ FAILED"
            print(f"  Result: {status}")
            print(f"  Execution time: {execution_time:.2f}s")

        except Exception as e:
            execution_time = time.time() - start_time
            print(f"  ✗ ERROR: {e}")

            result = ValidationResult(
                task_id=task_id,
                passed=False,
                metrics={},
                execution_time=execution_time,
                error=str(e)
            )

        self.results.append(result)
        return result

    def _check_criteria(self, metrics: dict[str, Any], criteria: dict[str, Any]) -> bool:
        """Check if metrics satisfy success criteria."""
        for key, threshold in criteria.items():
            if key not in metrics:
                return False

            value = metrics[key]

            # Boolean criteria: must be True
            if isinstance(threshold, bool):
                if value != threshold:
                    return False

            # Numeric criteria: value must meet threshold
            elif isinstance(threshold, (int, float)):
                # For p-values and ks_statistic: lower is better
                if key in ["p_value", "ks_statistic"]:
                    if value > threshold:
                        return False
                # For improvements: higher is better
                elif key in ["mean_improvement", "improvement"]:
                    if value < threshold:
                        return False

        return True

    def run_tier(self, tier: int, **kwargs) -> list[ValidationResult]:
        """
        Execute all validation tasks for a tier.

        Args:
            tier: Tier number (0, 1, or 2)
            **kwargs: Additional arguments passed to all protocols

        Returns:
            List of ValidationResult for all tasks in tier
        """
        print(f"\n{'='*60}")
        print(f"  Tier {tier} Validation Campaign")
        print(f"{'='*60}")

        tasks = list_validations(tier=tier)
        print(f"\nFound {len(tasks)} validation tasks for Tier {tier}")

        # Estimate total cost
        total_cost = sum(t.estimated_cost for t in tasks)
        print(f"Estimated total cost: {total_cost:.1f} hours")

        # Execute tasks
        tier_results = []
        for task in tasks:
            result = self.run_task(task.task_id, **kwargs)
            tier_results.append(result)

        # Summary
        passed_count = sum(1 for r in tier_results if r.passed)
        print(f"\n{'='*60}")
        print(f"  Tier {tier} Summary: {passed_count}/{len(tier_results)} passed")
        print(f"{'='*60}")

        return tier_results

    def generate_report(
        self,
        results: list[ValidationResult],
        output_path: Optional[Path] = None
    ) -> dict[str, Any]:
        """
        Generate structured validation report.

        Args:
            results: List of ValidationResult
            output_path: Optional path to save JSON report

        Returns:
            Report dict with pass/fail status and metrics
        """
        if output_path is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"validation_report_{timestamp}.json"

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tasks": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "total_execution_time": sum(r.execution_time for r in results),
            "tasks": [
                {
                    "task_id": r.task_id,
                    "passed": r.passed,
                    "metrics": r.metrics,
                    "execution_time": r.execution_time,
                    "error": r.error,
                }
                for r in results
            ]
        }

        # Save report
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nValidation report saved to: {output_path}")

        return report

    def tier0_gate_check(self) -> tuple[bool, str]:
        """
        Check Tier 0 gate criteria.

        Per BUILD_PROGRAM_v2.md lines 58-65:
        - All contracts pass
        - V01 (implementation parity): Sobol, TPE
        - V04 (performance): Sobol, GP beat random
        - V05 (log-warping): effectiveness
        - V14 (day-one walk): Chapter 15 example

        Returns:
            (gate_passed, summary_message)
        """
        required_tasks = [
            "V01-T0-sobol-parity",
            "V04-T0-sobol-vs-random",
            "V04-T0-gp-vs-random",
            "V05-T0-log-warping",
            "V14-T0-day-one-walk",
        ]

        # Check each required task
        missing = []
        failed = []

        for task_id in required_tasks:
            result = next((r for r in self.results if r.task_id == task_id), None)

            if result is None:
                missing.append(task_id)
            elif not result.passed:
                failed.append(task_id)

        # Generate summary
        if not missing and not failed:
            message = "✓ Tier 0 gate: ALL CRITERIA SATISFIED"
            return True, message

        message_parts = ["✗ Tier 0 gate: CRITERIA NOT SATISFIED"]

        if missing:
            message_parts.append(f"  Missing: {', '.join(missing)}")

        if failed:
            message_parts.append(f"  Failed: {', '.join(failed)}")

        return False, "\n".join(message_parts)
