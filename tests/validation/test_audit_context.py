"""Audited campaigns must not invent checkout provenance for installed wheels."""

from pathlib import Path
import subprocess

import pytest

import validation.evidence as evidence
from validation.run_validation_with_audit import ValidationRunner, main


def test_wheel_context_rejected_before_any_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "ROOT", tmp_path / "site-packages")
    output = tmp_path / "evidence"
    with pytest.raises(evidence.AuditContextError, match="full HPO-NAS Git checkout"):
        ValidationRunner("V14", artifact_root=output)
    assert not output.exists()


def test_cli_context_failure_is_actionable_without_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(evidence, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["V14"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "Campaign not started" in error
    assert "tools.check_installed" in error
    assert "Traceback" not in error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("missing", ["tests", "examples", "requirements.txt"])
def test_incomplete_source_copy_rejected(tmp_path, monkeypatch, missing):
    for directory in ("hponas", "workloads", "validation/protocols", "tools", "tests", "examples"):
        if directory != missing:
            (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json"):
        if name != missing:
            (tmp_path / name).write_text("")
    monkeypatch.setattr(evidence, "ROOT", tmp_path)
    with pytest.raises(evidence.AuditContextError):
        evidence.require_audit_checkout()


def test_parent_repository_cannot_supply_unrelated_identity(tmp_path, monkeypatch):
    for directory in ("hponas", "workloads", "validation/protocols", "tools", "tests", "examples"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json"):
        (tmp_path / name).write_text("")
    monkeypatch.setattr(evidence, "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: str(tmp_path.parent))
    with pytest.raises(evidence.AuditContextError):
        evidence.require_audit_checkout()


def test_repository_metadata_keeps_full_source_fingerprint():
    metadata = evidence.metadata("V14")
    assert metadata["source_digest"] == evidence.source_digest()
    assert metadata["version"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
