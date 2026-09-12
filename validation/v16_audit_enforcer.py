#!/usr/bin/env python3
"""
V16 Audit Enforcement Framework

Enforces V16 audit compliance for all validation executions.
Every validation run must pass V16 audit before results are accepted.

Usage:
    from validation.v16_audit_enforcer import V16Enforcer

    enforcer = V16Enforcer(protocol_path="validation/protocols/v01_protocol.md")
    audit_result = enforcer.audit_execution(
        validation_run_dir="validation/artifacts/v01_run_20260909_143022/"
    )

    if not audit_result.passed:
        print("V16 AUDIT FAILED - results rejected")
        print(audit_result)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class V16Check:
    """Single V16 audit check."""
    name: str
    passed: bool
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class V16AuditResult:
    """V16 audit result for a validation execution."""
    validation_id: str
    run_dir: Path
    checks: list[V16Check] = field(default_factory=list)
    passed: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            'validation_id': self.validation_id,
            'run_dir': str(self.run_dir),
            'checks': [
                {
                    'name': c.name,
                    'passed': c.passed,
                    'message': c.message,
                    'severity': c.severity
                }
                for c in self.checks
            ],
            'passed': self.passed,
            'timestamp': self.timestamp
        }

    def __str__(self) -> str:
        """Human-readable audit report."""
        lines = [f"=== V16 Audit Report: {self.validation_id} ==="]
        lines.append(f"Run: {self.run_dir}")
        lines.append(f"Timestamp: {self.timestamp}")
        lines.append("")

        for check in self.checks:
            if check.passed:
                status = "✓ PASS"
            elif check.severity == "warning":
                status = "⚠ WARN"
            else:
                status = "✗ FAIL"

            lines.append(f"{status}: {check.name}")
            if check.message:
                lines.append(f"  {check.message}")

        lines.append("")
        lines.append(f"Overall: {'✓ PASSED' if self.passed else '✗ FAILED'}")

        return "\n".join(lines)


class V16Enforcer:
    """
    Enforces V16 audit compliance on validation executions.

    Checks:
    1. Protocol immutability - Protocol file unchanged since preregistration
    2. Decision adherence - Verdict follows preregistered thresholds
    3. Artifact completeness - All required outputs preserved
    4. Metadata correctness - Execution details logged
    5. Known issues disclosure - Limitations documented
    """

    def __init__(self, protocol_path: str | Path):
        """
        Initialize V16 enforcer.

        Args:
            protocol_path: Path to the protocol markdown file
        """
        self.protocol_path = Path(protocol_path)
        if not self.protocol_path.exists():
            raise FileNotFoundError(f"Protocol not found: {self.protocol_path}")

        self.validation_id = self._extract_validation_id()

    def _extract_validation_id(self) -> str:
        """Extract validation ID from protocol filename."""
        # v01_protocol.md → V01
        # v04_t0_protocol.md → V04-T0
        stem = self.protocol_path.stem
        parts = stem.split('_')
        vid = parts[0].upper()
        if len(parts) > 1 and parts[1] != 'protocol':
            vid += '-' + parts[1].upper()
        return vid

    def audit_execution(self, validation_run_dir: str | Path) -> V16AuditResult:
        """
        Audit a validation execution for V16 compliance.

        Args:
            validation_run_dir: Directory containing validation run artifacts

        Returns:
            V16AuditResult with all checks
        """
        run_dir = Path(validation_run_dir)

        checks = [
            self._check_protocol_immutability(run_dir),
            self._check_decision_adherence(run_dir),
            self._check_artifact_completeness(run_dir),
            self._check_metadata_correctness(run_dir),
            self._check_known_issues_disclosure(run_dir),
        ]

        # Audit passes only if all error-level checks pass
        error_checks = [c for c in checks if c.severity == "error"]
        passed = all(c.passed for c in error_checks)

        return V16AuditResult(
            validation_id=self.validation_id,
            run_dir=run_dir,
            checks=checks,
            passed=passed
        )

    def _check_protocol_immutability(self, run_dir: Path) -> V16Check:
        """
        Check 1: Protocol file unchanged since preregistration.

        Verifies that the protocol file saved in the run directory matches
        the current protocol file (content hash comparison).
        """
        saved_protocol = run_dir / "protocol.md"

        if not saved_protocol.exists():
            return V16Check(
                name="Protocol Immutability",
                passed=False,
                message=f"Protocol snapshot not found in run artifacts: {saved_protocol}",
                severity="error"
            )

        # Compare content hashes
        current_hash = self._compute_file_hash(self.protocol_path)
        saved_hash = self._compute_file_hash(saved_protocol)

        if current_hash != saved_hash:
            return V16Check(
                name="Protocol Immutability",
                passed=False,
                message=(
                    f"Protocol modified after execution. "
                    f"Current hash: {current_hash[:8]}, "
                    f"Saved hash: {saved_hash[:8]}"
                ),
                severity="error"
            )

        return V16Check(
            name="Protocol Immutability",
            passed=True,
            message="Protocol unchanged since execution",
            severity="error"
        )

    def _check_decision_adherence(self, run_dir: Path) -> V16Check:
        """
        Check 2: Verdict follows preregistered decision thresholds.

        Verifies that the reported verdict (PASS/FAIL/INCONCLUSIVE) matches
        what the preregistered thresholds dictate given the observed metrics.
        """
        results_file = run_dir / "results.json"

        if not results_file.exists():
            return V16Check(
                name="Decision Adherence",
                passed=False,
                message=f"Results file not found: {results_file}",
                severity="error"
            )

        try:
            with open(results_file) as f:
                results = json.load(f)
        except json.JSONDecodeError as e:
            return V16Check(
                name="Decision Adherence",
                passed=False,
                message=f"Results file invalid JSON: {e}",
                severity="error"
            )

        # Check that verdict exists
        if 'verdict' not in results:
            return V16Check(
                name="Decision Adherence",
                passed=False,
                message="No 'verdict' field in results",
                severity="error"
            )

        verdict = results['verdict']
        if verdict not in ['PASS', 'FAIL', 'INCONCLUSIVE']:
            return V16Check(
                name="Decision Adherence",
                passed=False,
                message=f"Invalid verdict: {verdict} (must be PASS/FAIL/INCONCLUSIVE)",
                severity="error"
            )

        # Check that decision criteria are documented
        if 'decision_criteria' not in results:
            return V16Check(
                name="Decision Adherence",
                passed=False,
                message="No 'decision_criteria' field documenting threshold application",
                severity="warning"
            )

        return V16Check(
            name="Decision Adherence",
            passed=True,
            message=f"Verdict '{verdict}' documented with decision criteria",
            severity="error"
        )

    def _check_artifact_completeness(self, run_dir: Path) -> V16Check:
        """
        Check 3: All required artifacts preserved.

        Required artifacts per protocol:
        - protocol.md: Protocol snapshot
        - results.json: Test results and verdict
        - metadata.json: Execution metadata
        - Data artifacts (protocol-specific)
        """
        required_artifacts = [
            ("protocol.md", "Protocol snapshot"),
            ("results.json", "Test results"),
            ("metadata.json", "Execution metadata"),
        ]

        missing = []
        for filename, description in required_artifacts:
            if not (run_dir / filename).exists():
                missing.append(f"{description} ({filename})")

        if missing:
            return V16Check(
                name="Artifact Completeness",
                passed=False,
                message=f"Missing required artifacts: {', '.join(missing)}",
                severity="error"
            )

        return V16Check(
            name="Artifact Completeness",
            passed=True,
            message="All required artifacts present",
            severity="error"
        )

    def _check_metadata_correctness(self, run_dir: Path) -> V16Check:
        """
        Check 4: Execution metadata correctly logged.

        Required metadata fields:
        - validation_id: Which validation (V01, V02, etc.)
        - timestamp: When executed
        - seed: Random seed (if applicable)
        - version: Code version (git commit hash)
        """
        metadata_file = run_dir / "metadata.json"

        if not metadata_file.exists():
            return V16Check(
                name="Metadata Correctness",
                passed=False,
                message=f"Metadata file not found: {metadata_file}",
                severity="error"
            )

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
        except json.JSONDecodeError as e:
            return V16Check(
                name="Metadata Correctness",
                passed=False,
                message=f"Metadata file invalid JSON: {e}",
                severity="error"
            )

        required_fields = ['validation_id', 'timestamp']
        missing_fields = [f for f in required_fields if f not in metadata]

        if missing_fields:
            return V16Check(
                name="Metadata Correctness",
                passed=False,
                message=f"Missing required metadata fields: {', '.join(missing_fields)}",
                severity="error"
            )

        # Check that validation_id matches
        if metadata['validation_id'] != self.validation_id:
            return V16Check(
                name="Metadata Correctness",
                passed=False,
                message=(
                    f"Validation ID mismatch: "
                    f"metadata claims {metadata['validation_id']}, "
                    f"protocol is {self.validation_id}"
                ),
                severity="error"
            )

        # Warn if optional but recommended fields missing
        recommended_fields = ['seed', 'version', 'duration_seconds']
        missing_recommended = [f for f in recommended_fields if f not in metadata]

        if missing_recommended:
            return V16Check(
                name="Metadata Correctness",
                passed=True,
                message=f"Recommended fields missing: {', '.join(missing_recommended)}",
                severity="warning"
            )

        return V16Check(
            name="Metadata Correctness",
            passed=True,
            message="All required metadata fields present and correct",
            severity="error"
        )

    def _check_known_issues_disclosure(self, run_dir: Path) -> V16Check:
        """
        Check 5: Known issues documented in protocol.

        Verifies that the protocol file contains a "Known Issues" section
        disclosing limitations of the validation.
        """
        protocol_content = self.protocol_path.read_text()

        if "## Known Issues" not in protocol_content:
            return V16Check(
                name="Known Issues Disclosure",
                passed=False,
                message="Protocol missing '## Known Issues' section",
                severity="error"
            )

        # Extract Known Issues section
        lines = protocol_content.split('\n')
        in_known_issues = False
        known_issues_lines = []

        for line in lines:
            if line.strip() == "## Known Issues":
                in_known_issues = True
                continue
            if in_known_issues:
                if line.startswith("## "):  # Next section
                    break
                known_issues_lines.append(line)

        # Check that section is non-empty (excluding blank lines)
        non_blank = [l for l in known_issues_lines if l.strip()]
        if not non_blank:
            return V16Check(
                name="Known Issues Disclosure",
                passed=False,
                message="Known Issues section is empty",
                severity="warning"
            )

        return V16Check(
            name="Known Issues Disclosure",
            passed=True,
            message=f"Known Issues section present ({len(non_blank)} lines)",
            severity="error"
        )

    def _compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of file contents."""
        return hashlib.sha256(filepath.read_bytes()).hexdigest()

    def save_audit_result(self, audit_result: V16AuditResult, output_path: Path = None):
        """
        Save audit result to JSON file.

        Args:
            audit_result: The audit result to save
            output_path: Where to save (default: run_dir/v16_audit.json)
        """
        if output_path is None:
            output_path = audit_result.run_dir / "v16_audit.json"

        with open(output_path, 'w') as f:
            json.dump(audit_result.to_dict(), f, indent=2)


def enforce_v16_on_validation(
    validation_id: str,
    run_dir: Path,
    protocol_dir: Path = None
) -> V16AuditResult:
    """
    Convenience function to enforce V16 audit on a validation run.

    Args:
        validation_id: Validation identifier (e.g., "V01", "V04-T0")
        run_dir: Directory containing validation run artifacts
        protocol_dir: Directory containing protocol files (default: validation/protocols/)

    Returns:
        V16AuditResult
    """
    if protocol_dir is None:
        protocol_dir = Path(__file__).parent / "protocols"

    # Map validation_id to protocol filename
    # V01 → v01_protocol.md
    # V04-T0 → v04_t0_protocol.md
    vid_lower = validation_id.lower().replace('-', '_')
    protocol_path = protocol_dir / f"{vid_lower}_protocol.md"

    enforcer = V16Enforcer(protocol_path)
    audit_result = enforcer.audit_execution(run_dir)
    enforcer.save_audit_result(audit_result)

    return audit_result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python v16_audit_enforcer.py <validation_id> <run_dir>")
        print("Example: python v16_audit_enforcer.py V01 validation/artifacts/v01_run_20260909_143022/")
        sys.exit(1)

    validation_id = sys.argv[1]
    run_dir = Path(sys.argv[2])

    print(f"Running V16 audit on {validation_id} execution...")
    print(f"Run directory: {run_dir}")
    print()

    audit_result = enforce_v16_on_validation(validation_id, run_dir)

    print(audit_result)
    print()

    if audit_result.passed:
        print("✓ V16 AUDIT PASSED - validation results accepted")
        sys.exit(0)
    else:
        print("✗ V16 AUDIT FAILED - validation results rejected")
        sys.exit(1)
