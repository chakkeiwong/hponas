"""Compatibility interface backed by immutable evidence, never source keywords."""

import json
from pathlib import Path

from validation.evidence import ROOT
from validation.validators.base_validator import AuditCheck, AuditReport, ValidationProtocol
from validation.v16_audit_enforcer import V16Enforcer


class FiniteCampaignValidator(ValidationProtocol):
    validation_id = None
    schema_version = 2

    def __init__(self, run_dir=None):
        self.run_dir = Path(run_dir) if run_dir is not None else None

    def audit(self):
        """An integrity audit can pass on INCONCLUSIVE evidence; it is no release."""
        if self.run_dir is None:
            return AuditReport([AuditCheck("Immutable execution required", False,
                f"Supply the run directory from validation.run_validation_with_audit {self.validation_id}; source scans cannot certify.")], False)
        try:
            result = json.loads((self.run_dir / "results.json").read_text())
        except (OSError, ValueError) as exc:
            return AuditReport([AuditCheck("Readable evidence required", False, str(exc))], False)
        if result.get("schema_version") != self.schema_version or result.get("validation_id") != self.validation_id:
            return AuditReport([AuditCheck("Finite evidence required", False,
                "Historical diagnostic schema cannot certify this finite contract.")], False)
        protocol = ROOT / f"validation/protocols/{self.validation_id.lower().replace('-', '_')}_protocol.md"
        report = V16Enforcer(protocol).audit_execution(self.run_dir)
        return AuditReport([AuditCheck(check.name, check.passed, check.message) for check in report.checks], report.passed)

    def run(self, artifact_root=None):
        from validation.task_registry import audited_protocol

        return audited_protocol(self.validation_id, artifact_root=artifact_root)
