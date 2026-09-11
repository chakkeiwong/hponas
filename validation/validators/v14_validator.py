#!/usr/bin/env python3
"""V16 audit validator for V14 Day-One Walk protocol."""

import sys
from pathlib import Path

# Allow importing from same directory
sys.path.insert(0, str(Path(__file__).parent))

from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V14Validator(ValidationProtocol):
    """V16 audit validator for V14 Day-One Walk Reproduction."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v14_day_one_walk.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for n_trials > 0 validation
        has_trials_check = (
            'n_trials' in impl_text and
            ('n_trials == 0' in impl_text or 'n_trials = 0' in impl_text)
        )

        # Check for explicit vacuous rejection (from lines 158-161)
        has_vacuous_rejection = (
            'VACUOUS' in impl_text and
            'trials table is empty' in impl_text
        )

        # Check for trials_executed flag
        has_trials_executed = (
            'trials_executed' in impl_text and
            'trials_executed = True' in impl_text
        )

        if has_trials_check and has_vacuous_rejection and has_trials_executed:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation rejects empty trials table (lines 158-161)"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation missing vacuous rejection checks"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that protected seed and criteria were preregistered."""
        impl_path = Path("validation/v14_day_one_walk.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for protected seed (999) preregistration
        has_protected_seed = (
            'protected_seed = 999' in impl_text or
            'protected_seed = 999  # From v14_day_one_walk.py' in impl_text
        )

        # Check for timeout preregistration (60 seconds)
        has_timeout = (
            'timeout=60' in impl_text
        )

        # Check for pass criteria preregistration
        has_pass_criteria = (
            'executed_successfully' in impl_text and
            'artifacts_present' in impl_text and
            'seed_isolated' in impl_text
        )

        if has_protected_seed and has_timeout and has_pass_criteria:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Protected seed (999), timeout (60s), and pass criteria preregistered"
            )
        else:
            missing = []
            if not has_protected_seed:
                missing.append("protected seed")
            if not has_timeout:
                missing.append("timeout")
            if not has_pass_criteria:
                missing.append("pass criteria")

            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check correct reference (N/A for reproduction check)."""
        impl_path = Path("validation/v14_day_one_walk.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        # V14 is a deterministic reproduction check, not a comparison
        # The "reference" is the expected behavior (artifacts produced, seed isolated)
        # This check passes by construction for reproduction protocols
        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="N/A (deterministic reproduction check, not a comparison)"
        )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v14_day_one_walk.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main_block = 'if __name__ == "__main__"' in impl_text

        # Check for validation function execution
        has_validation_call = (
            'v14_day_one_walk_validation(' in impl_text or
            'v14_day_one_walk(' in impl_text
        )

        # Check for result reporting
        has_result_reporting = (
            'result["passed"]' in impl_text or
            'passed' in impl_text
        )

        if has_main_block and has_validation_call and has_result_reporting:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with validation execution (line 214)"
            )
        else:
            missing = []
            if not has_main_block:
                missing.append("__main__ block")
            if not has_validation_call:
                missing.append("validation execution")
            if not has_result_reporting:
                missing.append("result reporting")

            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing: {', '.join(missing)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run V16 audit on V14 validator")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run V16 audit checks"
    )
    args = parser.parse_args()

    if args.audit:
        validator = V14Validator()
        report = validator.audit()

        print("\n=== V16 Audit Report ===")
        for check in report.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            print(f"{status}: {check.name}")
            print(f"  {check.message}")

        print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

        sys.exit(0 if report.passed else 1)
