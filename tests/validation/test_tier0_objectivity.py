"""Objective contracts cannot be completed by labels, signatures or permission."""

import copy
import hashlib
import json

import pytest

from validation.tier0_design import canonical_digest, design_errors, load_design, require_campaign_ready
from validation.tier0_objectivity import (
    OBJECTIVE_POLICY,
    SAMPLING_OPEN_OBLIGATIONS,
    SELECTION_ALGORITHM,
    read_bound_json,
    replay_selection,
    require_resource_authorization,
    sampling_errors,
)


def bind(root, name, value):
    path = root / name
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_protocol_drift_cannot_restore_human_scientific_override():
    from tools.check_protocols import check_objective_evidence

    register = {"policy": {"objective_evidence": copy.deepcopy(OBJECTIVE_POLICY), "open_decisions": [
        {"id": "D5", "chosen": "objective_evidence_separate_resource_authorization"},
    ]}}
    assert check_objective_evidence(register) == []
    register["policy"]["objective_evidence"]["human_scientific_override"] = True
    assert check_objective_evidence(register)
    register["policy"]["objective_evidence"] = copy.deepcopy(OBJECTIVE_POLICY)
    register["policy"]["open_decisions"][0]["chosen"] = "codex_plus_pi_certification"
    assert check_objective_evidence(register)


@pytest.fixture
def selection():
    # Artificial documentation assertions, never actual holdout evidence.
    ledger = {"kind": "tier0_exposure_ledger_v1", "frame": [
        {"id": "a", "stratum": "motion", "exposure": "documented_unexposed"},
        {"id": "b", "stratum": "motion", "exposure": "documented_unexposed"},
        {"id": "c", "stratum": "control", "exposure": "documented_unexposed"},
        {"id": "d", "stratum": "control", "exposure": "unknown"},
        {"id": "already-seen", "stratum": "motion", "exposure": "exposed"},
    ]}
    manifest = {"kind": "tier0_selection_manifest_v1", "algorithm": SELECTION_ALGORITHM,
                "ledger_digest": canonical_digest(ledger), "seed_reveal": "00" * 32,
                "seed_commitment": hashlib.sha256(bytes(32)).hexdigest(),
                "counts": {entry: {"motion": 1, "control": 1} for entry in ("V04-T0", "V05")},
                "entry_tasks": {entry: ["c", "a"] for entry in ("V04-T0", "V05")}}
    return ledger, manifest


def test_consistent_selection_is_reproducible_without_reviewer_and_is_not_acceptance(selection):
    ledger, manifest = selection
    report = replay_selection(ledger, manifest)
    assert report["entry_tasks"] == {"V04-T0": ["c", "a"], "V05": ["c", "a"]}
    assert report["selection_reproduced"]
    assert report["verdict"] == "INCONCLUSIVE" and report["certifies_acceptance"] is False
    assert report["open_obligations"] == list(SAMPLING_OPEN_OBLIGATIONS)
    ledger["frame"].reverse()
    manifest["ledger_digest"] = canonical_digest(ledger)
    assert replay_selection(ledger, manifest) == report


@pytest.mark.parametrize("fault", ["commitment", "short_seed", "changed_ledger", "task_substitution",
                                   "duplicate_task", "unknown_exposure", "overdraw", "boolean_count",
                                   "missing_stratum", "algorithm"])
def test_changed_or_unsupported_selection_fails_even_with_human_approval(selection, fault):
    ledger, manifest = selection
    manifest.update(certifier="PI", approved=True, verdict="PASS")
    if fault == "commitment":
        manifest["seed_commitment"] = "0" * 64
    elif fault == "short_seed":
        manifest["seed_reveal"] = "00"
    elif fault == "changed_ledger":
        ledger["frame"][0]["exposure"] = "exposed"
    elif fault == "task_substitution":
        manifest["entry_tasks"]["V05"] = ["c", "b"]
    elif fault == "duplicate_task":
        ledger["frame"].append(ledger["frame"][0])
        manifest["ledger_digest"] = canonical_digest(ledger)
    elif fault == "unknown_exposure":
        ledger["frame"][2]["exposure"] = "unknown"
        manifest["ledger_digest"] = canonical_digest(ledger)
    elif fault == "overdraw":
        manifest["counts"]["V05"]["motion"] = 3
    elif fault == "boolean_count":
        manifest["counts"]["V05"]["motion"] = True
    elif fault == "missing_stratum":
        del manifest["counts"]["V05"]["control"]
    else:
        manifest["algorithm"] = "human_approved_selection"
    with pytest.raises(ValueError):
        replay_selection(ledger, manifest)


def test_approval_names_and_statuses_have_no_effect_on_selection_conclusion(selection):
    ledger, manifest = selection
    expected = replay_selection(ledger, manifest)
    manifest.update(independent_selector="professor", certifier="PI", approved=True, verdict="PASS")
    assert replay_selection(ledger, manifest) == expected


def test_hashes_and_a_replayed_selection_cannot_attest_chronology_or_isolation(selection, tmp_path):
    ledger, manifest = selection
    design = {"entry_tasks": manifest["entry_tasks"], "tasks": {"a": {}, "c": {}}, "sampling": {
        "selection_algorithm": SELECTION_ALGORITHM,
        "exposure_ledger": bind(tmp_path, "ledger.json", ledger),
        "selection_manifest": bind(tmp_path, "selection.json", manifest),
        "independent_selector": "approved reviewer", "provenance_verified": True,
        "independence_basis": "Trust the signer",
    }}
    assert sampling_errors(design, tmp_path) == list(SAMPLING_OPEN_OBLIGATIONS)
    design["entry_tasks"] = {"V05": ["b"]}
    assert "Design tasks differ from recomputed selection" in sampling_errors(design, tmp_path)


def test_human_exposure_review_and_certification_do_not_change_design_readiness(monkeypatch):
    from validation import tier0_objectivity

    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    errors = design_errors(design)
    design["status"] = "certified"
    design["sampling"].update(independent_selector="PI", independence_basis="approved")
    for task in design["tasks"].values():
        task["exposure_review"] = "approved"
    assert design_errors(design) == errors
    monkeypatch.setattr(tier0_objectivity, "require_resource_authorization",
                        lambda *args: pytest.fail("Permission consulted before scientific checks"))
    with pytest.raises(ValueError, match="exposure-history coverage"):
        require_campaign_ready(design, "pilot")


@pytest.mark.parametrize("raw", ['{"status":0,"status":1}', '{"value":NaN}', '{"value":1e999}', '[]'])
def test_ambiguous_or_nonfinite_evidence_refused(tmp_path, raw):
    path = tmp_path / "evidence.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        read_bound_json(tmp_path, {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def test_bound_evidence_refuses_changed_bytes_and_external_paths(tmp_path):
    ref = bind(tmp_path, "evidence.json", {"data": 1})
    (tmp_path / ref["path"]).write_text('{"data":2}')
    with pytest.raises(ValueError, match="Changed"):
        read_bound_json(tmp_path, ref)
    ref["path"] = "../evidence.json"
    with pytest.raises(ValueError, match="within the repository"):
        read_bound_json(tmp_path, ref)


def test_resource_permission_binds_exact_phase_design_and_allocation_without_certifier(tmp_path):
    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    receipt = {"kind": "tier0_resource_authorization", "scope": "resource_execution_only",
               "phase": "pilot", "design_digest": canonical_digest(design),
               "resource_digest": canonical_digest(design["resource"]),
               "authorization": "Artificial permission fixture; no actual allocation"}
    ref = bind(tmp_path, "permission.json", receipt)
    program = {"evidence": [{"kind": "tier0_resource_authorization", "phases": ["pilot"], **ref}]}
    require_resource_authorization(design, "pilot", program, tmp_path)
    # Passing permission cannot establish scientific completeness.
    assert design_errors(design)
    with pytest.raises(ValueError, match="resource authorization"):
        require_resource_authorization(design, "confirmation", program, tmp_path)
    changed = copy.deepcopy(design)
    changed["resource"]["campaign_cap_seconds"] = 1
    with pytest.raises(ValueError, match="resource authorization"):
        require_resource_authorization(changed, "pilot", program, tmp_path)


@pytest.mark.parametrize("fault", ["legacy_certificate", "scientific_override", "resource_digest"])
def test_human_certificate_cannot_replace_scoped_resource_permission(tmp_path, fault):
    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    receipt = {"kind": "tier0_resource_authorization", "scope": "resource_execution_only",
               "phase": "pilot", "design_digest": canonical_digest(design),
               "resource_digest": canonical_digest(design["resource"]), "authorization": "fixture",
               "certifier": "PI"}
    kind = receipt["kind"]
    if fault == "legacy_certificate":
        kind = receipt["kind"] = "tier0_design_certification"
    elif fault == "scientific_override":
        receipt["scope"] = "accept_scientific_result"
    else:
        receipt["resource_digest"] = "0" * 64
    program = {"evidence": [{"kind": kind, "phases": ["pilot"],
                             **bind(tmp_path, "permission.json", receipt)}]}
    with pytest.raises(ValueError, match="resource authorization"):
        require_resource_authorization(design, "pilot", program, tmp_path)
