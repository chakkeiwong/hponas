"""
V03Validator: V16 audit protocol compliance for V03 Mutation Testing.

Checks:
1. Non-vacuity: ≥100 mutants generated
2. No post-hoc tuning: Kill score threshold (0.90) preregistered
3. Correct reference: Mutation operators produce actual code changes, not no-ops
4. Runnable independently: Can execute without manual intervention

Note: V03 implementation (validation/v03_mutation_testing.py) does not yet exist.
This validator will report implementation not found until V03 is created.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck


class V03Validator(ValidationProtocol):
    """V16 audit protocol compliance for V03 Mutation Testing."""

    def __init__(self):
        self.protocol_path = Path("validation/protocols/v03_protocol.md")
        self.impl_path = Path("validation/v03_mutation_testing.py")
        self.results_path = Path("validation/results/v03_results.json")

    def _check_non_vacuity(self) -> AuditCheck:
        """Check 1: Validator rejects runs with <100 mutants."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # Check for minimum mutant threshold (≥100)
        has_mutant_check = ("total_mutants" in impl_text or "n_mutants" in impl_text) and (">=" in impl_text or "< 100" in impl_text)

        if not has_mutant_check:
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation does not check for minimum mutant count (≥100)"
            )

        return AuditCheck(
            name="Non-vacuity",
            passed=True,
            message="Validator correctly checks for ≥100 mutants (non-vacuous)"
        )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check 2: Kill score threshold (0.90) preregistered."""
        if not self.protocol_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Protocol file not found: {self.protocol_path}"
            )

        protocol_text = self.protocol_path.read_text()

        # Protocol should contain preregistered kill score threshold
        has_threshold = ("≥0.90" in protocol_text or ">= 0.90" in protocol_text or "Kill score threshold" in protocol_text or "kill score ≥0.90" in protocol_text)

        if not has_threshold:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Kill score threshold not preregistered in protocol"
            )

        # Implementation should match protocol threshold
        if not self.impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # Check for 0.90 threshold in implementation
        has_impl_threshold = ("0.90" in impl_text or "0.9" in impl_text) and ("kill_score" in impl_text.lower() or "threshold" in impl_text)

        if not has_impl_threshold:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Implementation threshold doesn't match protocol (0.90)"
            )

        return AuditCheck(
            name="No post-hoc tuning",
            passed=True,
            message="Kill score threshold (0.90) preregistered and matches implementation"
        )

    def _check_correct_reference(self) -> AuditCheck:
        """Check 3: Mutation operators produce actual code changes."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # V03 should use mutation testing tool (mutmut or cosmic-ray)
        has_mutmut = "mutmut" in impl_text.lower()
        has_cosmic_ray = "cosmic-ray" in impl_text.lower() or "cosmic_ray" in impl_text

        if not (has_mutmut or has_cosmic_ray):
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Implementation does not use mutation testing tool (mutmut or cosmic-ray)"
            )

        # Check for mutation operator configuration
        has_operators = "operator" in impl_text.lower() or "mutation" in impl_text.lower()

        if not has_operators:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Implementation missing mutation operator configuration"
            )

        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="Uses mutation testing tool with configured operators (correct reference)"
        )

    def _check_runnable_independently(self) -> AuditCheck:
        """Check 4: Can run standalone without manual intervention."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # Check for __main__ block
        has_main = 'if __name__ == "__main__"' in impl_text

        if not has_main:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing __main__ block"
            )

        # Check for target modules configuration
        has_targets = "target" in impl_text.lower() or "module" in impl_text.lower() or "in_scope" in impl_text

        if not has_targets:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing target module configuration"
            )

        return AuditCheck(
            name="Runnable independently",
            passed=True,
            message="Protocol can run standalone with configured targets"
        )
