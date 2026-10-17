"""Registered-claim boundaries and independent wrapper/event oracles."""

import copy
import json

import pytest

from validation.evidence import decision, digest
from validation.v02_event_grammar import population, verify_population
from validation.v02_state_replay import streamed_replay, cancelled_replay
from validation.v01_wrapper_checks import wrapper_checks, verify_wrappers


def test_shipped_wrapper_inventory_matches_independent_references():
    import torch

    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        checks = wrapper_checks()
    finally:
        torch.set_num_threads(previous)
    assert verify_wrappers(checks)
    with pytest.raises(ValueError, match="inventory"):
        verify_wrappers(checks[:-1])
    bad = copy.deepcopy(checks)
    bad[0]["actual"][0][0] += 0.01
    assert not verify_wrappers(bad)


def test_complete_generated_population_matches_pinned_oracle():
    report = population()
    assert report["count"] == 10000
    assert verify_population(report)


def test_event_selection_tampering_and_incomplete_population_are_rejected():
    report = population(36)
    assert verify_population(report, require_full=False)
    with pytest.raises(ValueError, match="population"):
        verify_population(report)
    bad = copy.deepcopy(report)
    bad["cases"][0]["actual"]["invariants"] = False
    assert not verify_population(bad, require_full=False)
    bad = copy.deepcopy(report)
    bad["cases"][1] = bad["cases"][0]
    with pytest.raises(ValueError, match="selected"):
        verify_population(bad, require_full=False)


def test_streamed_replay_executes_promotion_resume_and_completion(tmp_path):
    record = json.loads(json.dumps(streamed_replay(tmp_path)))
    assert all(c["expected"] == c["actual"] for c in record["cases"])
    assert digest(record["event_log"]["path"]) == record["event_log"]["sha256"]
    kinds = {json.loads(row)["event_type"] for row in (tmp_path / "streamed_replay.jsonl").read_text().splitlines()}
    assert {"progress", "finish", "promote", "promotion_round", "observe"} <= kinds


def test_cancelled_replay_records_and_replays_control_and_terminal_outcome(tmp_path):
    record = json.loads(json.dumps(cancelled_replay(tmp_path)))
    assert all(c["expected"] == c["actual"] for c in record["cases"])
    rows = [json.loads(row) for row in (tmp_path / "cancelled_replay.jsonl").read_text().splitlines()]
    assert {"cancel_request", "finish", "progress"} <= {row["event_type"] for row in rows}
    # The cancellation request cannot be deleted while leaving its control reply.
    from hponas import RandomSearcher
    from hponas.events import EventLog
    from hponas.replay import ReplayEngine
    from hponas.schedulers import ASHAConfig, ASHAScheduler
    from validation.v02_state_replay import _space

    path = tmp_path / "missing_request.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows if row["event_type"] != "cancel_request"))
    replay = ReplayEngine(RandomSearcher(_space(), seed=48), EventLog(path), 48,
                          ASHAScheduler(ASHAConfig(**record["scheduler_config"])))
    assert not replay.verify_determinism(1)[0]


def test_matching_ks_distributions_do_not_hide_wrong_order_or_certify_v01():
    comparisons = [{"component": "Sobol", "dimension": i, "reference": "scipy",
                    "actual": [j / 1000 for j in range(1000)],
                    "reference_values": [j / 1000 for j in range(1000)]} for i in range(5)]
    comparisons += [{"component": component, "reference": reference,
                     "actual": list(range(30)), "reference_values": list(range(30))}
                    for component, reference in [("GP", "botorch"), ("TPE", "optuna")]]
    record = {"schema_version": 1, "validation_id": "V01", "comparisons": comparisons}
    assert decision("V01", record) == "INCONCLUSIVE"
    comparisons[-1]["actual"].reverse()
    assert decision("V01", record) == "FAIL"


@pytest.mark.parametrize("entry", ["V04-T0", "V05"])
def test_registered_dispatch_uses_stylized_contract_and_preserves_valid_audit(tmp_path, monkeypatch, entry):
    from validation.task_registry import audited_protocol
    import validation.rl_baseline_campaign as historical
    import validation.tier0_campaign as legacy
    import validation.stylized_campaign as current

    monkeypatch.setattr(historical, "campaign", lambda *a, **k: pytest.fail("Historical comparison dispatched"))
    monkeypatch.setattr(legacy, "campaign", lambda *a, **k: pytest.fail("Retired PPO campaign dispatched"))
    calls = []
    def probe(vid, run_dir):
        calls.append(vid)
        return {"schema_version": 1, "validation_id": vid, "blocked_reason": "dispatch probe, no execution"}
    monkeypatch.setattr(current, "campaign", probe)
    result = audited_protocol(entry, artifact_root=tmp_path)
    assert result["verdict"] == "BLOCKED" and result["passed"] is False
    from pathlib import Path

    audit = json.loads((Path(result["artifact_run"]) / "v16_audit.json").read_text())
    assert audit["passed"]
    assert calls == [entry]
    assert "dispatch probe" in result["blocked_reason"]
    with pytest.raises(ValueError, match="retired"):
        audited_protocol(entry, artifact_root=tmp_path, design_path="old-ppo.json")


@pytest.mark.parametrize("entry", ["V01", "V02"])
def test_both_audited_entrypoints_use_final_finite_campaigns(tmp_path, monkeypatch, entry):
    from validation.task_registry import audited_protocol
    from validation.run_validation_with_audit import main
    from validation import v01_vendor_campaign, v02_state_replay, v01_finite_campaign, v02_final_campaign

    final = v01_finite_campaign if entry == "V01" else v02_final_campaign
    old = v01_vendor_campaign if entry == "V01" else v02_state_replay
    monkeypatch.setattr(old, "campaign", lambda *args: pytest.fail("legacy campaign dispatched"))
    calls = []

    def probe(run_dir):
        calls.append(run_dir)
        return {"schema_version": 1, "validation_id": entry, "blocked_reason": "dispatch probe, no execution"}
    monkeypatch.setattr(final, "campaign", probe)
    result = audited_protocol(entry, artifact_root=tmp_path)
    assert result["verdict"] == "BLOCKED" and len(calls) == 1
    # Keep CLI test artifacts isolated from the real latest acceptance pointer.
    from validation.run_validation_with_audit import ValidationRunner
    monkeypatch.setattr("validation.run_validation_with_audit.ValidationRunner",
                        lambda entry, **kwargs: ValidationRunner(entry, artifact_root=tmp_path, **kwargs))
    assert main([entry]) == 1 and len(calls) == 2


@pytest.mark.parametrize("entry", ["V01", "V02", "V04-T0", "V05"])
def test_finite_protocols_disclose_limits_and_static_audits_cannot_certify(tmp_path, entry):
    from validation.evidence import ROOT
    from validation.v16_audit_enforcer import V16Enforcer
    from validation.validators.v01_validator import V01Validator
    from validation.validators.v02_validator import V02Validator
    from validation.validators.v04_validator import V04Validator
    from validation.validators.v05_validator import V05Validator

    enforcer = V16Enforcer(ROOT / f"validation/protocols/{entry.lower().replace('-', '_')}_protocol.md")
    assert enforcer._check_known_issues_disclosure(tmp_path).passed
    validator = {"V01": V01Validator, "V02": V02Validator, "V04-T0": V04Validator, "V05": V05Validator}[entry]
    assert not validator().audit().passed
    (tmp_path / "results.json").write_text(json.dumps({"schema_version": 1, "validation_id": entry, "verdict": "PASS"}))
    assert not validator(tmp_path).audit().passed
