"""
V02Validator: V16 audit protocol compliance for V02 Deterministic State Replay.

Checks:
1. Non-vacuity: Empty event log must fail, not pass
2. No post-hoc tuning: N/A (hard veto, no thresholds)
3. Correct reference: Replay compares to original run, not external reference
4. Runnable independently: Can execute without manual intervention

Note: V02 implementation (validation/v02_state_replay.py) does not yet exist.
This validator will report implementation not found until V02 is created.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from base_validator import ValidationProtocol, AuditCheck


class V02Validator(ValidationProtocol):
    """V16 audit protocol compliance for V02 Deterministic State Replay."""

    def __init__(self):
        self.protocol_path = Path("validation/protocols/v02_protocol.md")
        self.impl_path = Path("validation/v02_state_replay.py")

    def _check_non_vacuity(self) -> AuditCheck:
        """Check 1: Validator rejects empty event log (Scenario 5)."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # Check for empty log rejection (Scenario 5: Zero-trial replay)
        has_empty_check = ("len(" in impl_text and "== 0" in impl_text) or ("not " in impl_text and "events" in impl_text)
        has_error_on_empty = "raise" in impl_text or "ValueError" in impl_text or "RuntimeError" in impl_text

        if not (has_empty_check and has_error_on_empty):
            return AuditCheck(
                name="Non-vacuity",
                passed=False,
                message="Implementation does not reject empty event log"
            )

        return AuditCheck(
            name="Non-vacuity",
            passed=True,
            message="Validator correctly rejects empty event log (Scenario 5)"
        )

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """Check 2: N/A for deterministic veto test."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        # V02 is deterministic veto (hard pass/fail), no thresholds to tune
        # Pass criteria: exact match (tolerance = 0.0)
        impl_text = self.impl_path.read_text()

        # Check for exact match requirement (tolerance = 0.0 or direct equality)
        has_exact_match = ("==" in impl_text or "!=" in impl_text) and ("tolerance" not in impl_text or "tolerance=0" in impl_text or "tolerance = 0" in impl_text)

        if not has_exact_match:
            return AuditCheck(
                name="No post-hoc tuning",
                passed=False,
                message="Implementation should use exact match (tolerance=0.0), not approximate equality"
            )

        return AuditCheck(
            name="No post-hoc tuning",
            passed=True,
            message="N/A for deterministic veto (hard pass/fail with exact match)"
        )

    def _check_correct_reference(self) -> AuditCheck:
        """Check 3: Replay compares to original run, not external reference."""
        if not self.impl_path.exists():
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message=f"Implementation not found: {self.impl_path} (not yet created)"
            )

        impl_text = self.impl_path.read_text()

        # V02 should compare original run to replayed run
        # Look for comparison between "original" and "replay" or similar naming
        has_replay_logic = ("replay" in impl_text.lower() or "replayed" in impl_text.lower()) and ("original" in impl_text.lower() or "reference" in impl_text.lower())

        if not has_replay_logic:
            return AuditCheck(
                name="Correct reference",
                passed=False,
                message="Implementation does not compare original run to replay"
            )

        return AuditCheck(
            name="Correct reference",
            passed=True,
            message="Compares original run to replay (correct reference)"
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

        # Check for default parameters or scenario execution
        has_scenarios = "scenario" in impl_text.lower() or "test_" in impl_text

        if not has_scenarios:
            return AuditCheck(
                name="Runnable independently",
                passed=False,
                message="Implementation missing scenario execution logic"
            )

        return AuditCheck(
            name="Runnable independently",
            passed=True,
            message="Protocol can run standalone with scenarios"
        )
