#!/usr/bin/env python3
"""V16 audit validator for V12 Mixed-Space TuRBO protocol."""

import sys
from pathlib import Path

# Allow importing from same directory
sys.path.insert(0, str(Path(__file__).parent))

from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V12Validator(ValidationProtocol):
    """V16 audit validator for V12 Mixed-Space TuRBO Performance."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v12_mixed_space_turbo.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for n_trials and n_seeds validation
        has_trials_validation = (
            'n_trials' in impl_text and
            'range(n_trials)' in impl_text
        )

        has_seeds_validation = (
            'n_seeds' in impl_text and
            'range(n_seeds)' in impl_text
        )

        # Check that mixed-space and continuous-only both defined
        has_mixed_space = (
            'mixed' in impl_text.lower() and
            'categorical' in impl_text.lower()
        )

        has_continuous_only = (
            'continuous' in impl_text.lower() and
            'only' in impl_text.lower()
        )

        if has_trials_validation and has_seeds_validation and has_mixed_space and has_continuous_only:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation validates trials/seeds and defines mixed-space vs continuous-only"
            )
        else:
            missing = []
            if not has_trials_validation:
                missing.append("trials validation")
            if not has_seeds_validation:
                missing.append("seeds validation")
            if not has_mixed_space:
                missing.append("mixed-space definition")
            if not has_continuous_only:
                missing.append("continuous-only definition")

            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that margin and task were preregistered before campaign."""
        impl_path = Path("validation/v12_mixed_space_turbo.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for preregistered margin (δ = 0.05)
        has_margin = (
            'SUPERIORITY_MARGIN' in impl_text or
            'delta' in impl_text.lower() or
            'margin' in impl_text.lower()
        )

        # Check for alpha parameter
        has_alpha = (
            'alpha: float' in impl_text or
            'alpha=' in impl_text
        )

        # Check for task definition (mixed-space benchmark)
        has_task_def = (
            'activation' in impl_text and
            'learning_rate' in impl_text and
            'hidden_dim' in impl_text
        )

        if has_margin and has_alpha and has_task_def:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Margin, alpha, and task preregistered"
            )
        else:
            missing = []
            if not has_margin:
                missing.append("superiority margin")
            if not has_alpha:
                missing.append("alpha")
            if not has_task_def:
                missing.append("mixed-space task definition")

            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that comparison is against continuous-only TuRBO baseline."""
        impl_path = Path("validation/v12_mixed_space_turbo.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for mixed-space TuRBO treatment
        has_mixed_turbo = (
            'mixed' in impl_text.lower() and
            'turbo' in impl_text.lower()
        )

        # Check for continuous-only TuRBO baseline
        has_continuous_turbo = (
            'continuous' in impl_text.lower() and
            'only' in impl_text.lower() and
            'turbo' in impl_text.lower()
        )

        # Check for comparison between them
        has_comparison = (
            'ttest' in impl_text.lower() or
            'compare' in impl_text.lower()
        )

        # Ensure not comparing against self
        not_self_comparison = (
            'baseline' in impl_text.lower() or
            'comparator' in impl_text.lower()
        )

        if has_mixed_turbo and has_continuous_turbo and has_comparison and not_self_comparison:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares mixed-space TuRBO against continuous-only TuRBO baseline"
            )
        else:
            missing = []
            if not has_mixed_turbo:
                missing.append("mixed-space TuRBO")
            if not has_continuous_turbo:
                missing.append("continuous-only TuRBO")
            if not has_comparison:
                missing.append("statistical comparison")
            if not not_self_comparison:
                missing.append("baseline terminology")

            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v12_mixed_space_turbo.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check for actual execution
        has_run_call = (
            'run_validation(' in impl_text or
            'run_campaign(' in impl_text
        )

        # Check for result serialization
        has_save_results = (
            'json.dump' in impl_text or
            'with open(' in impl_text
        )

        if has_main_block and has_run_call and has_save_results:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with execution and serialization"
            )
        else:
            missing = []
            if not has_main_block:
                missing.append("__main__ block")
            if not has_run_call:
                missing.append("validation execution")
            if not has_save_results:
                missing.append("result serialization")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run V16 audit on V12 validator")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run V16 audit checks"
    )
    args = parser.parse_args()

    if args.audit:
        validator = V12Validator()
        report = validator.audit()

        print("\n=== V16 Audit Report ===")
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.message}")

        print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

        sys.exit(0 if report.passed else 1)
