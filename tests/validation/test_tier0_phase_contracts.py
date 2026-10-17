"""Positive phase route and refusal boundaries; these are artificial fixtures."""

import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import pytest

from validation.tier0_design import ARMS, canonical_digest, design_errors, load_design, require_campaign_ready
from validation.tier0_objectivity import sampling_errors
from validation.tier0_phase_contracts import ASSUMPTIONS, SAMPLING, SIZING_POLICY, experiment_digest, verify_phase_freeze


def bind(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def prospective(tmp_path, monkeypatch):
    from validation import tier0_design
    from tools import source_identity

    design = load_design()
    design["execution_environment"]["python"] = sys.executable
    for key, value in design["execution_environment"]["variables"].items():
        monkeypatch.setenv(key, value)
    task_id = next(iter(design["tasks"]))
    task = design["tasks"][task_id]
    design["tasks"] = {task_id: task}
    design["entry_tasks"] = {entry: [task_id] for entry in ARMS}
    task["role"] = "acceptance"
    artifact = bind(tmp_path, "task.json", {"kind": "inert_engineering_fixture"})
    task.update(artifact=artifact, data_artifacts=[artifact], data_sha256=canonical_digest([artifact]))
    task["budget"].update(seconds=10, max_overshoot_seconds=2, protected_policy_cap_seconds=10)
    # A complete artificial nonfutile reservation, with no actual workload.
    design["seed_sets"]["pilot"] = list(range(10000, 10046))
    design["selected_counts"]["pilot"] = {entry: 46 for entry in ARMS}
    for seed in design["seed_sets"]["pilot"]:
        task["initial_configs"][str(seed)] = copy.deepcopy(task["initial_configs"]["10000"])
    design.update(status="frozen", source_digest="a" * 64, sizing_policy=copy.deepcopy(SIZING_POLICY))
    design["run_schedule"] = {phase: {entry: f"validation/artifacts/{entry}/fixture-{phase}" for entry in ARMS}
                              for phase in ("pilot", "confirmation")}
    design["resource"].update(owner="fixture", allocation_id="no_actual_spend", campaign_cap_seconds=1000,
                              protected_cap_seconds=500)
    design["dependencies"] = {name: importlib.metadata.version(name) for name in
                              ("numpy", "scipy", "torch", "botorch", "gpytorch", "optuna", "jax", "jaxlib", "brax")}
    design["outcome_approval"] = bind(tmp_path, "outcome.json", {"artificial": True})
    exposure = bind(tmp_path, "exposure.json", {"kind": "known_exposure_fixture"})
    manifest = bind(tmp_path, "suite.json", {"kind": SAMPLING, "entry_tasks": design["entry_tasks"],
                    "task_digest": canonical_digest(design["tasks"]), "known_exposure": {task_id: "development_exposed"},
                    "assumptions": ASSUMPTIONS, "exposure_records": [exposure]})
    design["sampling"].update(selection_algorithm=SAMPLING, assumptions=copy.deepcopy(ASSUMPTIONS), suite_manifest=manifest)
    register = bind(tmp_path, "validation/protocols.json", {"status": "DRAFT"})
    design["protocol_register_sha256"] = register["sha256"]
    protocols = {entry: bind(tmp_path, f"validation/protocols/{entry.lower().replace('-', '_')}_protocol.md", {}) for entry in ARMS}
    design.pop("phase_freeze", None)
    design["phase_freeze"] = bind(tmp_path, "pilot-freeze.json", {"kind": "tier0_phase_freeze_v1", "phase": "pilot",
        "design_digest": canonical_digest(design), "source_digest": design["source_digest"], "protocols": protocols,
        "recorded_ns": 1, "boot_id": "fixture"})
    scope = bind(tmp_path, "scope.json", {"kind": "tier0_prospective_scope_authorization", "assumptions": ASSUMPTIONS,
                                         "suite_manifest": manifest, "authorization": "inert fixture"})
    permission = bind(tmp_path, "resources.json", {"kind": "tier0_resource_authorization", "phase": "pilot",
        "scope": "resource_execution_only", "design_digest": canonical_digest(design),
        "resource_digest": canonical_digest(design["resource"]), "authorization": "inert fixture",
        "entry_caps_seconds": {entry: 1000 for entry in ARMS}, "run_schedule": design["run_schedule"]})
    program = {"decisions": [{"id": key, "status": "accepted"} for key in ("D-T0-CLAIMS", "D-PILOT-ORDER", "D-T0-OUTCOME-SCOPE")],
        "evidence": [{"kind": "tier0_outcome_scope_user_approval", **design["outcome_approval"]},
                     {"kind": "tier0_prospective_scope_authorization", **scope},
                     {"kind": "tier0_resource_authorization", "phases": ["pilot"], **permission}]}
    bind(tmp_path, "docs/program/program.json", program)
    monkeypatch.setattr(tier0_design, "ROOT", tmp_path)
    monkeypatch.setattr(source_identity, "source_digest", lambda: "a" * 64)
    return design, tmp_path


def test_concrete_pilot_has_positive_route_without_its_own_results_or_global_completion(prospective):
    design, root = prospective
    assert sampling_errors(design, root) == []
    assert design_errors(design, phase="pilot") == []
    assert any("planning alternative" in e for e in design_errors(design))
    # No D-PROTOCOL flag, broad complete work-item labels, or non-DRAFT register.
    require_campaign_ready(design, "pilot")


def test_otherwise_valid_but_futile_pilot_refused_before_resource_permission(prospective, monkeypatch):
    from validation import tier0_objectivity

    design, root = prospective
    design["selected_counts"]["pilot"]["V04-T0"] = 5
    frozen_ref = design.pop("phase_freeze")
    frozen = json.loads((root / frozen_ref["path"]).read_text())
    frozen["design_digest"] = canonical_digest(design)
    design["phase_freeze"] = bind(root, "new-pilot-freeze.json", frozen)
    monkeypatch.setattr(tier0_objectivity, "require_resource_authorization",
                        lambda *args: pytest.fail("Permission consulted before futility refusal"))
    with pytest.raises(ValueError, match="pilot count 5 is futile"):
        require_campaign_ready(design, "pilot")


@pytest.mark.parametrize("fault", ["exposure", "task_substitution", "source", "rule", "protocol", "scope_permission", "resource_permission"])
def test_approval_labels_cannot_bypass_concrete_pilot_evidence(prospective, fault):
    design, root = prospective
    if fault == "exposure":
        design["sampling"]["assumptions"]["unseen_task_claim"] = True
    elif fault == "task_substitution":
        design["entry_tasks"]["V05"] = ["replacement"]
    elif fault == "source":
        design["source_digest"] = "b" * 64
    elif fault == "rule":
        design["sizing_policy"]["planning_error"] = .9
    elif fault == "protocol":
        (root / "validation/protocols/v05_protocol.md").write_text("changed")
    else:
        path = root / "docs/program/program.json"
        program = json.loads(path.read_text())
        kind = "tier0_prospective_scope_authorization" if fault == "scope_permission" else "tier0_resource_authorization"
        program["evidence"] = [e for e in program["evidence"] if e["kind"] != kind]
        path.write_text(json.dumps(program))
    with pytest.raises((ValueError, KeyError)):
        require_campaign_ready(design, "pilot")


def test_phase_freeze_cannot_be_reused_for_confirmation_or_changed_count(prospective):
    design, root = prospective
    verify_phase_freeze(design, "pilot", root)
    with pytest.raises(ValueError, match="Phase freeze"):
        verify_phase_freeze(design, "confirmation", root)
    design["selected_counts"]["pilot"]["V05"] = 6
    with pytest.raises(ValueError, match="Phase freeze"):
        verify_phase_freeze(design, "pilot", root)


def test_compatibility_allows_only_phase_allocation_and_confirmation_count(prospective):
    design, _ = prospective
    digest = experiment_digest(design)
    changed = copy.deepcopy(design)
    changed["selected_counts"]["confirmation"]["V05"] = 20
    changed["resource"]["campaign_cap_seconds"] *= 4
    assert experiment_digest(changed) == digest
    changed["selected_counts"]["pilot"]["V05"] = 6
    assert experiment_digest(changed) != digest
    changed = copy.deepcopy(design)
    next(iter(changed["tasks"].values()))["settings"]["max_timesteps"] *= 2
    assert experiment_digest(changed) != digest


def test_scientific_api_does_not_misclassify_profiling_as_confirmation():
    assert design_errors(load_design(), phase="profiling") == [
        "Unknown scientific design phase; profiling uses its own development contract"]


@pytest.mark.parametrize("fault", [None, "before_freeze", "after_search", "before_launch", "boot", "design"])
def test_launch_checked_against_frozen_plan_and_observed_children(prospective, fault):
    from validation.tier0_phase_contracts import verify_phase_launch

    design, root = prospective
    launch = {"kind": "prospective_phase_launch_v1", "phase": "pilot", "source_digest": design["source_digest"],
              "design_digest": canonical_digest(design), "phase_freeze": design["phase_freeze"],
              "monotonic_ns": 2, "boot_id": "fixture"}
    reports = [{"launch_ns": 3, "observer": {"boot_id": "fixture"}}]
    if fault == "before_freeze":
        launch["monotonic_ns"] = 0
    elif fault == "after_search":
        launch["monotonic_ns"] = 6
    elif fault == "before_launch":
        reports[0]["launch_ns"] = 1
    elif fault == "boot":
        reports[0]["observer"]["boot_id"] = "another-boot"
    elif fault == "design":
        launch["design_digest"] = "0" * 64
    if fault:
        with pytest.raises(ValueError, match="Prospective"):
            verify_phase_launch(launch, design, "pilot", 5, reports, root)
    else:
        verify_phase_launch(launch, design, "pilot", 5, reports, root)


def test_register_cannot_restore_circular_phase_requirements():
    from tools.check_protocols import check_phase_readiness
    from validation.tier0_phase_contracts import PHASE_POLICY

    data = {"policy": {"tier0_phase_readiness": copy.deepcopy(PHASE_POLICY),
                       "tier0_pilot_sizing": copy.deepcopy(SIZING_POLICY)}}
    assert check_phase_readiness(data) == []
    data["policy"]["tier0_phase_readiness"]["pilot"] = "requires_pilot_results"
    assert check_phase_readiness(data)


def test_register_cannot_select_another_sizing_method_after_pilot():
    from tools.check_protocols import check_phase_readiness
    from validation.tier0_phase_contracts import KL_SIZING_POLICY, PHASE_POLICY

    data = {"policy": {"tier0_phase_readiness": copy.deepcopy(PHASE_POLICY),
                       "tier0_pilot_sizing": copy.deepcopy(KL_SIZING_POLICY)}}
    assert check_phase_readiness(data) == ['Tier 0 pilot sizing differs from the single prespecified method']


def test_development_profile_requires_bounded_recipe_and_explicit_device_before_launch(tmp_path):
    from validation.tier0_development_profile import profile_errors, run_profile

    plan = json.loads(Path("docs/program/evidence/2026-09-30/phase-sequence/development-profile-plan.json").read_text())
    assert profile_errors(plan) == []
    plan["cap_seconds"] = 10000
    plan["device"] = "cuda"
    assert len(profile_errors(plan)) == 2
    with pytest.raises(ValueError, match="GPU"):
        run_profile(plan, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()


def test_preallocated_campaign_directory_is_single_use_and_part_of_experiment(prospective):
    from validation.run_validation_with_audit import ValidationRunner
    from validation.tier0_phase_contracts import campaign_directory

    design, root = prospective
    path = campaign_directory(design, "pilot", "V05", root)
    runner = ValidationRunner("V05", artifact_root=root / "validation/artifacts", run_name=path.name)
    assert runner.run_dir == path
    with pytest.raises(FileExistsError):
        ValidationRunner("V05", artifact_root=root / "validation/artifacts", run_name=path.name)
    changed = copy.deepcopy(design)
    changed["run_schedule"]["pilot"]["V05"] += "-rerun"
    assert experiment_digest(changed) != experiment_digest(design)
    changed["run_schedule"]["pilot"]["V05"] = "../elsewhere"
    with pytest.raises(ValueError, match="direct audited"):
        campaign_directory(changed, "pilot", "V05", root)


def test_resource_receipt_cannot_authorize_two_entries_with_one_undeclared_cap(prospective):
    from validation.tier0_objectivity import require_resource_authorization

    design, root = prospective
    program = json.loads((root / "docs/program/program.json").read_text())
    require_resource_authorization(design, "pilot", program, root)
    row = next(e for e in program["evidence"] if e["kind"] == "tier0_resource_authorization")
    receipt = json.loads((root / row["path"]).read_text())
    receipt["entry_caps_seconds"].pop("V05")
    row.update(bind(root, "underallocated.json", receipt))
    with pytest.raises(ValueError, match="resource authorization"):
        require_resource_authorization(design, "pilot", program, root)


def test_live_authorized_scope_is_adopted_but_not_a_phase_freeze():
    from validation.tier0_phase_contracts import require_prospective_scope
    root = Path(__file__).resolve().parents[2]
    design = load_design()
    program = json.loads((root / "docs/program/program.json").read_text())
    require_prospective_scope(design, program, root)
    assert sampling_errors(design, root) == []
    assert design["phase_freeze"] is None
    assert design_errors(design, phase="pilot")
    with pytest.raises(ValueError, match="Incomplete Tier 0 design"):
        require_campaign_ready(design, "pilot")
