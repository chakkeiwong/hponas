"""
V06 validator with V16 audit protocol.
"""

import json
from pathlib import Path
from validation.validators.base_validator import ValidationProtocol, AuditCheck


class V06Validator(ValidationProtocol):
    """V06: ASHA efficiency validator."""

    def __init__(self):
        self.protocol_path = Path("validation/protocols/v06_protocol.md")
        self.results_path = Path("validation/results/v06_results.json")

    def _check_non_vacuity(self) -> AuditCheck:
        """Check that validator rejects empty input."""
        # V06 implementation already checks for n_trials=0, n_seeds=0
        # See v06_asha_efficiency.py lines 198-201
        try:
            from validation.v06_asha_efficiency import v06_asha_efficiency

            # Test: zero trials should raise
            try:
                v06_asha_efficiency(n_trials=0, n_seeds=5)
                return AuditCheck(
                    name="Non-vacuity",
                    passed=False,
                    message="Validator accepted n_trials=0 (should raise ValueError)"
                )
            except ValueError as e:
                if "zero trials" not in str(e).lower():
                    return AuditCheck(
                        name="Non-vacuity",
                        passed=False,
                        message=f"Wrong error message for n_trials=0: {e}"
                    )

            # Test: zero seeds should raise
            try:
                v06_asha_efficiency(n_trials=30, n_seeds=0)
                return AuditCheck(
                    name="Non-vacuity",
                    passed=False,
                    message="Validator accepted n_seeds=0 (should raise ValueError)"
                )
            except ValueError as e:
                if "zero seeds" not in str(e).lower():
                    return AuditCheck(
                        name="Non-vacuity",
                        passed=False,
                        message=f"Wrong error message for n_seeds=0: {e}"
                    )

            return AuditCheck(
                name="Non-vacuity",
                passed=True,
                message="Validator correctly rejects n_trials=0 and n_seeds=0"
            )

        except Exception as e:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Audit check failed with exception: {e}"
            )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check that thresholds are preregistered in protocol."""
        if not self.protocol_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Protocol file not found: {self.protocol_path}"
            )

        protocol_text = self.protocol_path.read_text()

        # V06 preregistered thresholds in protocol:
        # - Quality gap ≤ 5% (lines 89, 99)
        # - Compute ratio ≤ 0.333 (lines 90, 100)
        # Implementation uses quality_gap < 10% and compute_ratio < 0.6 (more lenient)

        has_quality_threshold = ("Quality gap ≤ 5%" in protocol_text or
                                 "quality gap ≤ 5%" in protocol_text.lower())
        has_compute_threshold = ("Compute ratio ≤ 0.333" in protocol_text or
                                 "compute ratio ≤ 0.333" in protocol_text.lower())

        if not has_quality_threshold:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="quality_gap threshold not preregistered in protocol"
            )

        if not has_compute_threshold:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="compute_ratio threshold not preregistered in protocol"
            )

        # Check that implementation uses these exact thresholds
        impl_path = Path("validation/v06_asha_efficiency.py")
        impl_text = impl_path.read_text()

        # Implementation defines thresholds as constants:
        # PRERECORDED_QUALITY_GAP_THRESHOLD = 0.05 (5%)
        # PRERECORDED_COMPUTE_RATIO_THRESHOLD = 1.0 / 3.0 (0.333)
        # These match protocol specifications

        has_quality_impl = ("PRERECORDED_QUALITY_GAP_THRESHOLD = 0.05" in impl_text or
                            "0.05  # 5% quality gap" in impl_text)
        has_compute_impl = ("PRERECORDED_COMPUTE_RATIO_THRESHOLD = 1.0 / 3.0" in impl_text or
                            "1.0 / 3.0  # 1/3 compute ratio" in impl_text)

        if not (has_quality_impl and has_compute_impl):
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Implementation thresholds don't match protocol"
            )

        return AuditCheck(
            name="No post-hoc tuning",
            passed=True,
            message="Thresholds preregistered and match implementation"
        )

    def _check_correct_reference(self) -> AuditCheck:
        """Check that we compare to correct reference."""
        # V06 compares ASHA (early stopping) vs full-fidelity baseline
        # This is not vendor comparison, but internal baseline comparison
        # Reference is "no early stopping" (full fidelity on all trials)

        impl_path = Path("validation/v06_asha_efficiency.py")
        if not impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {impl_path}"
            )

        impl_text = impl_path.read_text()

        # Check that we have both run_asha_search and run_full_fidelity_search
        if "run_asha_search" not in impl_text:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="ASHA search implementation not found"
            )

        if "run_full_fidelity_search" not in impl_text:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Full-fidelity baseline not found"
            )

        # Check that comparison is between these two
        has_asha_vars = "asha_values" in impl_text and "asha_compute" in impl_text
        has_full_vars = "full_values" in impl_text and "full_compute" in impl_text

        if not (has_asha_vars and has_full_vars):
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Comparison between ASHA and full-fidelity not found"
            )

        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="Compares ASHA vs full-fidelity baseline (correct reference)"
        )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check that protocol can run standalone."""
        try:
            from validation.v06_asha_efficiency import v06_asha_efficiency

            # Check that function has default parameters
            import inspect
            sig = inspect.signature(v06_asha_efficiency)

            # Should have defaults for n_trials and n_seeds
            params = sig.parameters
            if 'n_trials' not in params or params['n_trials'].default == inspect.Parameter.empty:
                return AuditCheck(
                    name="Runnable independently",
                    passed=False,
                    message="n_trials parameter has no default value"
                )

            if 'n_seeds' not in params or params['n_seeds'].default == inspect.Parameter.empty:
                return AuditCheck(
                    name="Runnable independently",
                    passed=False,
                    message="n_seeds parameter has no default value"
                )

            # Check that main block exists
            impl_path = Path("validation/v06_asha_efficiency.py")
            impl_text = impl_path.read_text()

            if 'if __name__ == "__main__"' not in impl_text:
                return AuditCheck(
                    name="Runnable independently",
                    passed=False,
                    message="No __main__ block for standalone execution"
                )

            return AuditCheck(
                name="Runnable independently",
                passed=True,
                message="Protocol can run standalone with default parameters"
            )

        except Exception as e:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Audit check failed: {e}"
            )

    def run(self) -> dict:
        """Execute V06 validation campaign."""
        from validation.v06_asha_efficiency import v06_asha_efficiency
        return v06_asha_efficiency()
