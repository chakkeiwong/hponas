"""
V16 Audit Protocol: V07 GPU Campaign Capacity
==============================================

V07 validates that all GPU-intensive campaigns fit within hardware capacity.
Implementation: validation/v07_gpu_capacity_audit.py (not yet created)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V07Validator(ValidationProtocol):
    """V16 audit validator for V07 GPU Campaign Capacity."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that the implementation rejects structurally empty inputs."""
        impl_path = Path("validation/v07_gpu_capacity_audit.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        # If implementation exists, verify it checks for empty validation lists
        impl_text = impl_path.read_text()

        has_empty_check = (
            'len(validations) == 0' in impl_text or
            'not validations' in impl_text
        ) and 'ValueError' in impl_text

        if has_empty_check:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Implementation rejects empty validation lists"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation does not check for empty validation lists"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that GPU budget was preregistered before campaigns."""
        impl_path = Path("validation/v07_gpu_capacity_audit.py")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        # V07 is a resource audit - budget should be a prerecorded constant
        impl_text = impl_path.read_text()

        has_prerecorded_budget = (
            'PRERECORDED_GPU_BUDGET' in impl_text or
            'GPU_BUDGET_GPU_WEEKS = 5' in impl_text
        )

        if has_prerecorded_budget:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="GPU budget preregistered as constant"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="GPU budget not preregistered as constant"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check correct reference (N/A for resource audits)."""
        impl_path = Path("validation/v07_gpu_capacity_audit.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        # V07 is a resource audit - no comparison reference needed
        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="N/A (resource audit, not a comparison)"
        )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that the protocol can run standalone."""
        impl_path = Path("validation/v07_gpu_capacity_audit.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        has_main_block = 'if __name__ == "__main__"' in impl_text
        has_argparse = 'argparse' in impl_text or 'ArgumentParser' in impl_text

        if has_main_block and has_argparse:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Implementation has __main__ block with argument parsing"
            )
        else:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing __main__ block or argument parsing"
            )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="V16 audit for V07 GPU Campaign Capacity")
    parser.add_argument("--audit", action="store_true", help="Run V16 audit checks")
    args = parser.parse_args()

    if args.audit:
        validator = V07Validator()
        report = validator.audit()
        print(report)
        sys.exit(0 if report.passed else 1)
    else:
        print("Use --audit flag to run V16 audit checks")
        sys.exit(1)
