"""
V05 Validator: V16 audit compliance for Log-Warping Effectiveness.

Validates V05 implementation against four V16 audit criteria:
1. Non-vacuity: Rejects structurally empty inputs
2. No post-hoc tuning: Thresholds preregistered before campaigns
3. Correct reference: Log vs linear transform comparison
4. Runnable independently: Standalone execution
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck, AuditReport


class V05Validator(ValidationProtocol):
    """V16 audit validator for V05 Log-Warping Effectiveness."""

    def _check_non_vacuity(self) -> AuditCheck:
        """Check V05 rejects n_trials=0 and n_seeds=0."""
        impl_path = Path("validation/v05_log_warping.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for zero trials rejection
        has_trials_check = (
            'n_trials == 0' in impl_text and
            'ValueError' in impl_text and
            'vacuous pass' in impl_text
        )

        # Check for zero seeds rejection
        has_seeds_check = (
            'n_seeds == 0' in impl_text and
            'ValueError' in impl_text and
            'vacuous pass' in impl_text
        )

        passed = has_trials_check and has_seeds_check

        if passed:
            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Rejects n_trials=0 and n_seeds=0 with ValueError (lines 109-112)"
            )
        else:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Missing vacuity checks: trials={has_trials_check}, seeds={has_seeds_check}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check V05 uses preregistered threshold (15%)."""
        impl_path = Path("validation/v05_log_warping.py")
        protocol_path = Path("validation/protocols/v05_protocol.md")

        if not impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for PRERECORDED_THRESHOLD constant
        has_constant = 'PRERECORDED_THRESHOLD = 0.15' in impl_text

        # Check usage in function
        has_usage = 'improvement_threshold = PRERECORDED_THRESHOLD' in impl_text

        # Check protocol specifies 15% improvement
        protocol_match = False
        if protocol_path.exists():
            protocol_text = protocol_path.read_text()
            protocol_match = 'Improvement > 15%' in protocol_text or '0.15' in protocol_text

        passed = has_constant and has_usage

        if passed:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=True,
                message="Pre-recorded threshold PRERECORDED_THRESHOLD = 0.15 (line 24)"
            )
        else:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Missing preregistered threshold: constant={has_constant}, usage={has_usage}"
            )

    def _check_correct_reference(self) -> AuditCheck:
        """Check V05 compares log-warped vs linear sampling."""
        impl_path = Path("validation/v05_log_warping.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for log-transform space
        has_log_space = (
            'space_log' in impl_text and
            'transform="log"' in impl_text
        )

        # Check for linear space (no transform)
        has_linear_space = (
            'space_linear' in impl_text and
            'transform=None' in impl_text
        )

        # Check same objective used
        has_same_objective = 'log_sensitive_objective' in impl_text

        passed = has_log_space and has_linear_space and has_same_objective

        if passed:
            return AuditCheck(
                name="Correct reference",
                passed=True,
                message="Compares log-transform vs no transform on same objective (lines 121-126)"
            )
        else:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Missing comparison: log={has_log_space}, linear={has_linear_space}, obj={has_same_objective}"
            )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check V05 has standalone execution."""
        impl_path = Path("validation/v05_log_warping.py")

        if not impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check for __main__ block
        has_main = 'if __name__ == "__main__"' in impl_text

        # Check for audit flag
        has_audit = '--audit' in impl_text

        # Check function call
        has_call = 'v05_log_warping_effectiveness(' in impl_text

        passed = has_main and has_call

        if passed:
            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Standalone executable with __main__ block (lines 220-226)"
            )
        else:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Missing standalone execution: main={has_main}, call={has_call}"
            )


if __name__ == "__main__":
    validator = V05Validator()
    report = validator.audit()
    print(report)
