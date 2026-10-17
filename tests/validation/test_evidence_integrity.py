"""Gate failures for forged, stale, empty and selectively counted evidence."""

import json
from pathlib import Path

import pytest

from validation.evidence import decision
from validation.v03_mutation_testing import analyze_results, parse_listing
from validation.run_validation_with_audit import ValidationRunner
from validation.v16_audit_enforcer import V16Enforcer
from tools.gate_check import check_tier0_gate, check_tier1_gate, check_tier2_gate


def test_shared_trial_evaluation_is_a_critical_path_even_when_total_score_passes():
    prefix = "hponas.executors.base.x_evaluate_trial__mutmut_"
    mutants = [
        {
            "id": prefix + str(i),
            "module": "hponas.executors.base",
            "status": "survived" if i == 100 else "killed",
        }
        for i in range(1, 101)
    ]
    report = analyze_results(
        {"mutants": mutants}, required_modules=["hponas.executors.base"]
    )
    assert report["kill_score"] == 0.99
    assert not report["passed"]
    assert report["critical_survivors"] == [prefix + "100"]


def test_inventory_includes_killed_and_uncovered_in_denominator():
    raw = parse_listing(
        "\n".join(
            f"hponas.schedulers.xǁASHASchedulerǁpromote__mutmut_{i}: "
            + ("killed" if i < 90 else "no tests" if i < 99 else "survived")
            for i in range(100)
        )
    )
    report = analyze_results(raw, required_modules=["hponas.schedulers"])
    assert report["denominator"] == 100
    assert report["kill_score"] == 0.9
    assert len(report["critical_survivors"]) == 1
    assert not report["passed"]
    assert "Unproved critical-path survivors" in report["errors"]


def test_aggregate_score_cannot_hide_failing_module():
    raw = parse_listing(
        "\n".join(f"hponas.good.xfoo__mutmut_{i}: killed" for i in range(100))
        + "\nhponas.bad.xfoo__mutmut_1: survived"
    )
    result = analyze_results(raw, required_modules=["hponas.good", "hponas.bad"])
    assert result["kill_score"] > 0.9
    assert not result["passed"]


def test_no_status_duplicates_or_unreviewed_equivalents():
    line = "hponas.good.xfoo__mutmut_1: survived"
    with pytest.raises(ValueError, match="Duplicate"):
        parse_listing(line + "\n" + line)
    with pytest.raises(ValueError, match="proof"):
        analyze_results(parse_listing(line), equivalents=[{"id": line.split(":")[0]}])


def test_cached_mutation_results_cannot_certify():
    assert (
        decision(
            "V03",
            {
                "schema_version": 1,
                "validation_id": "V03",
                "passed": True,
                "fresh_campaign": False,
            },
        )
        == "INCONCLUSIVE"
    )


def test_mutation_snapshot_identity_survives_concurrent_edit(monkeypatch):
    import validation.evidence as evidence
    import validation.v03_mutation_testing as mutation

    hashes = iter(["before", "after"])
    monkeypatch.setattr(evidence, "source_digest", lambda: next(hashes))
    monkeypatch.setattr(
        mutation,
        "run_mutmut",
        lambda: {
            "source_digest": "before",
            "mutants": [],
            "workspace": "/tmp/snapshot",
            "execution_completed": True,
        },
    )
    result = mutation.campaign(run=True)
    assert result["source_digest"] == "before"
    assert result["end_source_digest"] == "after"
    assert result["verdict"] == "INCONCLUSIVE"
    assert not result["fresh_campaign"]


def test_mutation_wall_limit_preserves_partial_worker_evidence(tmp_path):
    import os
    import sys
    from validation.v03_mutation_testing import _run_with_deadline

    worker = tmp_path / "waiting.py"
    worker.write_text(
        "import signal,time\n"
        "from pathlib import Path\n"
        "def stop(*unused):\n"
        "    Path('interrupted.txt').write_text('partial evidence saved')\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGINT,stop)\n"
        "time.sleep(60)\n"
    )
    assert not _run_with_deadline(
        [sys.executable, str(worker)], tmp_path, dict(os.environ), timeout=1.0
    )
    assert (tmp_path / "interrupted.txt").read_text() == "partial evidence saved"


def test_missing_artifacts_block_every_tier(tmp_path):
    assert check_tier0_gate(tmp_path).verdict == "blocked"
    assert check_tier1_gate().verdict == "blocked"
    assert check_tier2_gate().verdict == "blocked"


def test_fake_pass_and_empty_scenarios_rejected(tmp_path):
    runner = ValidationRunner("V02", artifact_root=tmp_path)
    assert not runner.run(
        lambda: {
            "schema_version": 1,
            "validation_id": "V02",
            "passed": True,
            "scenarios": [],
        }
    )
    saved = json.loads((runner.run_dir / "results.json").read_text())
    assert saved["verdict"] == "BLOCKED"
    saved.update(verdict="PASS", passed=True)
    (runner.run_dir / "results.json").write_text(json.dumps(saved))
    audit = runner.enforcer.audit_execution(runner.run_dir)
    assert not audit.passed
    assert any(not c.passed and c.name == "Metadata Correctness" for c in audit.checks)


def test_smoke_performance_is_not_a_gate_pass():
    assert (
        decision(
            "V05",
            {
                "schema_version": 1,
                "validation_id": "V05",
                "workload": "brax_ppo",
                "real_workload": True,
                "smoke": True,
                "passed": True,
            },
        )
        == "INCONCLUSIVE"
    )


def test_manifest_signature_verifies_and_rejects_tampering():
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from tools.verify_manifest import check_signature

    key = Ed25519PrivateKey.generate()
    manifest = {
        "campaign": "test",
        "public_key": base64.b64encode(
            key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode(),
    }
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    manifest["signature"] = base64.b64encode(key.sign(canonical)).decode()
    check_signature(manifest)
    manifest["campaign"] = "changed"
    with pytest.raises(SystemExit):
        check_signature(manifest)
