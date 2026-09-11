"""
Base validator implementing V16 audit protocol.

All validation protocols (V01-V15) inherit from this base.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AuditCheck:
    """Single audit check result."""
    name: str
    passed: bool
    message: str


@dataclass
class AuditReport:
    """V16 audit report."""
    checks: list[AuditCheck]
    passed: bool

    def __str__(self) -> str:
        lines = ["=== V16 Audit Report ==="]
        for check in self.checks:
            status = "✓ PASS" if check.passed else "✗ FAIL"
            lines.append(f"{status}: {check.name}")
            if check.message:
                lines.append(f"  {check.message}")
        lines.append(f"\nOverall: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


class ValidationProtocol:
    """
    Base class for all validation protocols.

    Each validator must implement:
    - run(): Execute the validation campaign
    - _check_non_vacuity(): Verify input is non-trivial
    - _check_no_posthoc_tuning(): Verify thresholds preregistered
    - _check_correct_reference(): Verify comparing to declared vendor
    - _check_runnable_independently(): Verify can run standalone
    """

    def audit(self) -> AuditReport:
        """
        Run V16 audit checks.

        Returns:
            AuditReport with all four checks
        """
        checks = [
            self._check_non_vacuity(),
            self._check_no_posthoc_tuning(),
            self._check_correct_reference(),
            self._check_runnable_independently(),
        ]
        return AuditReport(checks=checks, passed=all(c.passed for c in checks))

    def _check_non_vacuity(self) -> AuditCheck:
        """
        Check 1: Validator fails on structurally empty input.

        Subclasses should verify:
        - validate(results=[]) → ERROR, not PASS
        - validate(results=[{trials: 0}]) → ERROR, not PASS

        Returns:
            AuditCheck indicating pass/fail
        """
        raise NotImplementedError("Subclass must implement _check_non_vacuity()")

    def _check_no_posthoc_tuning(self) -> AuditCheck:
        """
        Check 2: Thresholds recorded before campaign.

        Subclasses should verify:
        - Protocol file preregisters margin/threshold
        - Validator uses exactly that value (no modification)

        Returns:
            AuditCheck indicating pass/fail
        """
        raise NotImplementedError("Subclass must implement _check_no_posthoc_tuning()")

    def _check_correct_reference(self) -> AuditCheck:
        """
        Check 3: Compare against declared vendor, not self.

        Subclasses should verify:
        - V01 "GP matches BoTorch" → compare to BoTorch.GP
        - Not comparing two internal implementations (tautological)

        Returns:
            AuditCheck indicating pass/fail
        """
        raise NotImplementedError("Subclass must implement _check_correct_reference()")

    def _check_runnable_independently(self) -> AuditCheck:
        """
        Check 4: Full protocol executes standalone.

        Subclasses should verify:
        - Script runs without human intervention
        - Protocol parameters read from file, not command-line

        Returns:
            AuditCheck indicating pass/fail
        """
        raise NotImplementedError("Subclass must implement _check_runnable_independently()")

    def run(self) -> dict:
        """
        Execute the validation campaign.

        Returns:
            dict with keys: passed, details, metrics
        """
        raise NotImplementedError("Subclass must implement run()")
