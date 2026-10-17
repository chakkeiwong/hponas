"""The program must expose blocked work and reject false scope/evidence closure."""

import copy
import json
import shutil

import pytest

from tools import program_state as p


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value)


@pytest.fixture
def program(tmp_path):
    root = tmp_path
    decisions = [{"id": "source-1", "capability": "required feature", "tier": "T0"}]
    protocol = {"claim": "parity", "gate": "tier0", "threshold": 0.1}
    write(root / "hpo-survey-decisions.json", decisions)
    write(root / "validation/protocols.json", {"status": "DRAFT", "entries": {"V01": protocol}})
    write(root / "validation/evidence.py", 'TIER0 = ("V01",)\n')
    write(root / "validation/protocols/v01_protocol.md", "protocol")
    write(root / "pyproject.toml", "[project]\nname='fixture'\n")
    write(root / "requirements.txt", "")
    write(root / "BUILD_PROGRAM_REVIEW_VERDICT.md", "requirements")
    write(root / "review.md", "Review evidence, not release certification.")
    write(root / p.MASTER, "# Master\n" + p.START + "\n" + p.END + "\n")
    findings = [f"A{i:02d}" for i in range(1, 12)] + [f"T{i:02d}" for i in range(1, 7)] + ["V03-accounting"]
    requirements = [{"id": f"APP-{i:02d}", "title": f"Requirement {i}",
                     "decision_ids": ["source-1"] if i == 1 else [],
                     "audit_findings": findings if i == 1 else [],
                     "disposition": "required", "work_items": ["W1"],
                     "sources": ["BUILD_PROGRAM_REVIEW_VERDICT.md"], "reason": "retained"}
                    for i in range(1, 13)]
    item = {"id": "W1", "title": "Repair", "owner": "implementation agent",
            "state": "planned", "implementation": "partial", "dependencies": [],
            "decision_dependencies": [], "code_refs": [], "test_refs": [],
            "acceptance_campaigns": ["V01"], "evidence_refs": ["E1"],
            "done_when": "Behavior and evidence agree", "next_action": "Test the behavior",
            "budget": {"wall_seconds": 60}}
    data = {"schema_version": 1, "revision": "test", "master": p.MASTER,
            "current_phase": "tier0_acceptance", "active_work_item": None,
            "tier0_campaigns": ["V01"], "audit_gate": "V16", "audit_findings": findings,
            "requirements": requirements, "work_items": [item],
            "decisions": [{"id": "D1", "title": "Unresolved claim", "status": "open",
                           "rationale": "Conflict", "consequence": "Confirmation blocked"}],
            "protocol_bindings": [{"id": "V01", "registry_claim": protocol["claim"],
                "registry_gate": protocol["gate"], "registry_entry_sha256": p.canonical_digest(protocol),
                "protocol_path": "validation/protocols/v01_protocol.md", "identity": "unresolved",
                "protocol_sha256": p.sha256(root / "validation/protocols/v01_protocol.md"),
                "decision_refs": ["D1"]}],
            "source_inputs": [{"id": f"S{i}", "path": path, "sha256": p.sha256(root / path)}
                for i, path in enumerate(["hpo-survey-decisions.json", "validation/protocols.json", "BUILD_PROGRAM_REVIEW_VERDICT.md"])],
            "evidence": [{"id": "E1", "path": "review.md", "sha256": p.sha256(root / "review.md")}],
            "campaign_receipts": {}}
    run = root / "validation/artifacts/V01/run-1"
    write(run.parent / "latest.json", {"run": run.name})
    write(run / "protocol.md", "protocol")
    write(run / "results.json", {"schema_version": 1, "validation_id": "V01", "verdict": "INCONCLUSIVE", "passed": False})
    write(run / "metadata.json", {"validation_id": "V01", "source_digest": p.source_digest(root), "results_sha256": p.sha256(run / "results.json")})
    checks = [{"name": name, "passed": True, "severity": "error", "message": "ok"}
              for name in sorted(p.AUDIT_CHECKS)]
    next(c for c in checks if c["name"] == "Decision Adherence")["message"] = "Recomputed verdict: INCONCLUSIVE"
    write(run / "v16_audit.json", {"validation_id": "V01", "checks": checks, "passed": True})
    data["campaign_receipts"]["V01"] = {"run": str(run.relative_to(root)), "hashes":
        {name: p.sha256(run / name) for name in ("results.json", "metadata.json", "v16_audit.json")}}
    return root, data


def project(root, data):
    write(root / p.REGISTER, data)
    errors, view = p.validate(root)
    assert not errors, errors
    for path, content in p.generated_documents(root, view).items():
        write(root / path, content)
    return view


def test_blocked_program_is_consistent_and_regeneration_is_deterministic(program):
    root, data = program
    view = project(root, data)
    first = (root / p.MASTER).read_bytes()
    project(root, data)
    assert (root / p.MASTER).read_bytes() == first
    assert p.check(root)[0] == []
    assert view["campaigns"][0]["verdict"] == "INCONCLUSIVE"
    assert "Release status: BLOCKED" in first.decode()


@pytest.mark.parametrize("damage,fragment", [
    (lambda d: d["requirements"][0].update(decision_ids=[]), "exactly one"),
    (lambda d: d["requirements"][1].update(decision_ids=["source-1"]), "exactly one"),
    (lambda d: d.update(requirements=[]), "empty requirements"),
    (lambda d: d["requirements"].pop(), "twelve approval"),
    (lambda d: d["requirements"][0].update(disposition="excluded", reason="convenience"), "scope cannot be excluded"),
    (lambda d: d["protocol_bindings"][0].update(registry_claim="different claim"), "claim or gate identity"),
    (lambda d: d["protocol_bindings"][0].update(registry_gate="tier2"), "claim or gate identity"),
    (lambda d: d["protocol_bindings"][0].update(decision_refs=[]), "missing conflict decision"),
    (lambda d: d.update(tier0_campaigns=[]), "IDs differ"),
    (lambda d: d["work_items"][0].update(dependencies=["missing"]), "unknown dependency"),
    (lambda d: d["work_items"][0].update(dependencies=["W1"]), "cycle"),
    (lambda d: d["work_items"][0].update(state="complete", evidence_refs=[]), "completion requires evidence"),
    (lambda d: d["work_items"][0].update(state="complete", decision_dependencies=["D1"]), "decision D1 remains open"),
    (lambda d: d.update(active_work_item="W1"), "single in-progress"),
    (lambda d: d.update(audit_gate=None), "V16 is mandatory"),
    (lambda d: d.update(current_phase="tier1"), "Phase promotion"),
    (lambda d: d["source_inputs"].pop(0), "must remain hash-bound"),
    (lambda d: d["evidence"][0].update(path="../outside"), "escapes repository"),
])
def test_scope_identity_dependency_and_completion_drift_rejected(program, damage, fragment):
    root, data = program
    damage(data)
    assert fragment in "\n".join(p.validate(root, data)[0])


def test_changed_specification_threshold_is_not_accepted_by_regeneration(program):
    root, data = program
    spec = p.read_json(root / "validation/protocols.json")
    spec["entries"]["V01"]["threshold"] = 0.2
    write(root / "validation/protocols.json", spec)
    errors, _ = p.validate(root, data)
    assert any("rules changed" in e for e in errors)
    assert any("Source input changed" in e for e in errors)


def test_individual_protocol_edits_require_reconciliation(program):
    root, data = program
    write(root / "validation/protocols/v01_protocol.md", "Changed pass rule")
    assert any("individual protocol changed" in e for e in p.validate(root, data)[0])


def test_source_changes_make_receipts_stale_and_views_fail_until_regenerated(program):
    root, data = program
    project(root, data)
    write(root / "hponas/change.py", "x = 1\n")
    errors, view = p.check(root)
    assert view["campaigns"][0]["status"] == "STALE"
    assert any("Generated view stale" in e for e in errors)
    project(root, data)
    assert p.check(root)[0] == []  # truthful STALE is consistent, never acceptance


def test_editing_generated_pass_claim_is_detected(program):
    root, data = program
    project(root, data)
    path = root / p.MASTER
    path.write_text(path.read_text().replace("Release status: BLOCKED", "Release status: PASS"))
    assert any("Generated view stale" in e for e in p.check(root)[0])


def test_forged_pass_does_not_gain_a_receipt(program):
    root, data = program
    run = root / data["campaign_receipts"]["V01"]["run"]
    result = p.read_json(run / "results.json")
    result.update(verdict="PASS", passed=True)
    write(run / "results.json", result)
    assert any("changed or unbound results.json" in e for e in p.validate(root, data)[0])
    data["campaign_receipts"]["V01"]["hashes"]["results.json"] = p.sha256(run / "results.json")
    assert any("not bound to metadata" in e for e in p.validate(root, data)[0])


@pytest.fixture
def adopted_program(program):
    """A small retained baseline and independently bound development transition."""
    root, data = program
    digest = p.source_digest(root)
    run = root / data["campaign_receipts"]["V01"]["run"]
    result = p.read_json(run / "results.json")
    result.update(verdict="PASS", passed=True)
    write(run / "results.json", result)
    metadata = p.read_json(run / "metadata.json")
    metadata["results_sha256"] = p.sha256(run / "results.json")
    write(run / "metadata.json", metadata)
    audit = p.read_json(run / "v16_audit.json")
    next(c for c in audit["checks"] if c["name"] == "Decision Adherence")["message"] = "Recomputed verdict: PASS"
    write(run / "v16_audit.json", audit)
    receipt = data["campaign_receipts"]["V01"]
    receipt["hashes"] = {name: p.sha256(run / name) for name in receipt["hashes"]}

    def bind(name, value):
        write(root / name, value)
        return {"path": name, "sha256": p.sha256(root / name)}

    retained = root / "archive/baseline/source"
    paths = [root / "pyproject.toml", root / "requirements.txt", root / "validation/protocols.json"]
    paths += list((root / "validation").rglob("*.py"))
    paths += list((root / "validation/protocols").glob("*.md"))
    for path in paths:
        target = retained / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    assert p.source_digest(retained) == digest
    snapshot = bind("snapshot.json", {"kind": "accepted_source_snapshot_v1",
        "root": "archive/baseline/source", "source_digest": digest,
        "files": [{"path": str(path.relative_to(root)), "sha256": p.sha256(path)} for path in paths]})
    reviewed = bind("reviewed-program.json", data)
    master = bind("reviewed-master.md", (root / p.MASTER).read_text())
    gate = bind("gate.json", {"error": None, "returncode": 0, "source_digest": digest,
        "result": {"phase": "tier0", "verdict": "pass", "criteria": [
            {"name": "Master program prerequisites", "status": "met"}, {"name": "V01", "status": "met"}]},
        "inputs": [{"path": p.REGISTER, "sha256": reviewed["sha256"]},
                   {"path": p.MASTER, "sha256": master["sha256"]}]})
    package = bind("package.json", {"kind": "tier0_objective_baseline_package_v1",
        "source_digest": digest, "source_snapshot": snapshot, "gate_review": gate,
        "reviewed_program": reviewed, "reviewed_master": master,
        "campaign_receipts": data["campaign_receipts"]})
    verified = bind("verification.json", {"kind": "phase_transition_repair_verification_v1",
        "source_digest": digest, "returncode": 0, "tests": 5, "failures": 0})
    adoption = bind("adoption.json", {"kind": "local_phase_adoption_v1",
        "from_phase": "tier0_acceptance", "to_phase": "tier1_development",
        "decision_id": "D-PHASE", "package": package, "verification": verified,
        "implementation_source_digest": digest,
        "authorization": {"scope": "local_baseline_and_continued_development",
                          "external_publication": False, "standing_user_instructions": ["Continue execution"]}})
    data["evidence"].append({"id": "E-ADOPTION", **adoption})
    data["phase_transition"] = "E-ADOPTION"
    data["current_phase"] = "tier1_development"
    data["decisions"].append({"id": "D-PHASE", "status": "accepted", "kind": "phase_amendment",
        "title": "Local transition", "rationale": "Objective baseline retained",
        "consequence": "Local development proceeds with separate acceptance",
        "authorization": "Standing local execution authorization", "evidence_refs": ["E-ADOPTION"]})
    release = copy.deepcopy(data["work_items"][0])
    release.update(id="REL-01", state="complete")
    data["work_items"].append(release)
    data["continuation"] = {"policy": "repair_verify_refresh_advance_v1", "steps": [{
        "id": sid, "state": "complete", "work_item": "REL-01", "kind": "preparation",
        "dependencies": [], "action": "Review retained baseline", "done_when": "Bound evidence agrees",
        "evidence_refs": ["E-ADOPTION"]} for sid in [
        "REL-01/TIER0-RELEASE-REVIEW", "REL-01/PHASE-TRANSITION-REPAIR", "REL-01/RELEASE-AUTHORIZATION"]]}
    return root, data


def rebind_adoption(root, data):
    """Rebind changed documents so semantic checks, not old hashes, reject them."""
    for parent, field in [("package.json", "gate_review"), ("package.json", "reviewed_program"),
                          ("adoption.json", "package"), ("adoption.json", "verification")]:
        body = p.read_json(root / parent)
        body[field]["sha256"] = p.sha256(root / body[field]["path"])
        write(root / parent, body)
    next(e for e in data["evidence"] if e["id"] == "E-ADOPTION")["sha256"] = p.sha256(root / "adoption.json")


def test_local_adoption_retains_acceptance_without_certifying_development(adopted_program):
    root, data = adopted_program
    baseline = p.phase_transition_view(root, data, p.source_digest(root))["baseline_source_digest"]
    write(root / "hponas/new_feature.py", "value = 1\n")
    errors, view = p.validate(root, data)
    assert not errors, errors
    assert view["phase"]["status"] == "LOCAL BASELINE ACCEPTED"
    assert not view["phase"]["current_source_is_baseline"]
    assert view["phase"]["baseline_source_digest"] == baseline
    assert view["campaigns"][0]["status"] == "STALE"
    text = p.render_status(view)
    assert "Tier 1 development" in text and "No external release" in text
    assert "STALE" in text


@pytest.mark.parametrize("damage,fragment", [
    (lambda d: d.pop("phase_transition"), "Phase promotion"),
    (lambda d: d["continuation"]["steps"][0].update(state="planned"), "prerequisite"),
    (lambda d: d["work_items"][-1].update(state="planned"), "reconciled release"),
    (lambda d: d["decisions"][-1].update(status="open"), "accepted amendment"),
    (lambda d: d["decisions"][-1].update(evidence_refs=[]), "accepted amendment"),
    (lambda d: d.update(current_phase="tier2"), "explicit reviewed"),
])
def test_transition_requires_completed_bound_authorization(adopted_program, damage, fragment):
    root, data = adopted_program
    damage(data)
    assert fragment in "\n".join(p.validate(root, data)[0])


@pytest.mark.parametrize("file,damage,fragment", [
    ("gate.json", lambda d: d["result"].update(verdict="blocked"), "objectively passing"),
    ("gate.json", lambda d: d["result"]["criteria"].pop(), "objectively passing"),
    ("gate.json", lambda d: d["result"]["criteria"][1].update(name="Master program prerequisites"), "objectively passing"),
    ("gate.json", lambda d: d["result"]["criteria"][1].update(status="blocked"), "objectively passing"),
    ("gate.json", lambda d: d.update(source_digest="0" * 64), "objectively passing"),
    ("reviewed-program.json", lambda d: d.update(revision="forged"), "reviewed program"),
    ("verification.json", lambda d: d.update(failures=1), "verification is incomplete"),
    ("adoption.json", lambda d: d["authorization"].update(external_publication=True), "authorization scope"),
    ("adoption.json", lambda d: d["authorization"].update(standing_user_instructions=[]), "authorization scope"),
])
def test_rehashed_false_acceptance_cannot_promote(adopted_program, file, damage, fragment):
    root, data = adopted_program
    body = p.read_json(root / file)
    damage(body)
    write(root / file, body)
    rebind_adoption(root, data)
    assert fragment in "\n".join(p.validate(root, data)[0])


def test_retained_source_is_checked_even_after_development_changes(adopted_program):
    root, data = adopted_program
    write(root / "archive/baseline/source/validation/evidence.py", 'TIER0 = ("V02",)\n')
    assert "accepted source snapshot differs" in "\n".join(p.validate(root, data)[0])


def test_baseline_is_independent_of_later_campaign_pointer(adopted_program):
    root, data = adopted_program
    write(root / "validation/artifacts/V01/latest.json", {"run": "new-development-run"})
    # The baseline retains its exact old receipt; the current register still
    # refuses an unregistered current campaign independently.
    assert p.phase_transition_view(root, data, p.source_digest(root))["status"] == "LOCAL BASELINE ACCEPTED"
    assert any("latest campaign" in e for e in p.validate(root, data)[0])


def test_finite_v01_receipt_checks_indirect_raw_artifacts(program):
    root, data = program
    run = root / data["campaign_receipts"]["V01"]["run"]
    base = run / "finite-v01"

    def bound(name, value):
        write(base / name, value)
        return {"path": name, "sha256": p.sha256(base / name)}
    raw = bound("raw.json", {"rows": [1, 2]})
    record = bound("case.json", {"report": raw})
    execution = bound("execution.json", {"cases": [record]})
    result = p.read_json(run / "results.json")
    result.update(schema_version=2, scope="finite_reference_trace_conformance_v1", run_dir=str(base), execution=execution)
    write(run / "results.json", result)
    meta = p.read_json(run / "metadata.json")
    meta["results_sha256"] = p.sha256(run / "results.json")
    write(run / "metadata.json", meta)
    receipt = data["campaign_receipts"]["V01"]
    for name in receipt["hashes"]:
        receipt["hashes"][name] = p.sha256(run / name)
    assert not p.validate(root, data)[0]
    write(base / "raw.json", {"rows": [1]})
    assert any("changed dependent artifact" in e for e in p.validate(root, data)[0])


def test_retired_partial_v01_and_incomplete_v02_rules_are_rejected():
    from tools.check_protocols import check_finite_conformance

    entries = p.read_json(p.ROOT / "validation/protocols.json")["entries"]
    assert check_finite_conformance(entries) == []
    entries["V01"]["decision_rule"]["pass"] = "matching_prefix"
    entries["V02"].pop("scope_contract")
    assert len(check_finite_conformance(entries)) == 2


def test_empty_or_demoted_audit_cannot_support_acceptance(program):
    root, data = program
    run = root / data["campaign_receipts"]["V01"]["run"]
    audit = p.read_json(run / "v16_audit.json")
    for checks in ([], [{**c, "severity": "warning"} for c in audit["checks"]]):
        write(run / "v16_audit.json", {**audit, "checks": checks})
        data["campaign_receipts"]["V01"]["hashes"]["v16_audit.json"] = p.sha256(run / "v16_audit.json")
        assert p.validate(root, data)[0]


def test_duplicate_keys_and_work_ids_are_rejected(program):
    root, data = program
    write(root / "duplicate.json", '{"id": 1, "id": 2}')
    with pytest.raises(ValueError, match="Duplicate JSON"):
        p.read_json(root / "duplicate.json")
    data["work_items"].append(copy.deepcopy(data["work_items"][0]))
    assert any("duplicate work items" in e for e in p.validate(root, data)[0])


def test_dependent_artifact_hashes_are_checked_after_checkout_relocation(program):
    root, data = program
    run = root / data["campaign_receipts"]["V01"]["run"]
    artifact = run / "events.jsonl"
    write(artifact, "actual events")
    result = p.read_json(run / "results.json")
    result["events"] = {"path": "/old/checkout/" + str(artifact.relative_to(root)), "sha256": p.sha256(artifact)}
    write(run / "results.json", result)
    metadata = p.read_json(run / "metadata.json")
    metadata["results_sha256"] = p.sha256(run / "results.json")
    write(run / "metadata.json", metadata)
    audit = p.read_json(run / "v16_audit.json")
    audit["run_dir"] = "/old/checkout/" + str(run.relative_to(root))
    write(run / "v16_audit.json", audit)
    data["campaign_receipts"]["V01"]["hashes"] = {n: p.sha256(run / n) for n in ("metadata.json", "results.json", "v16_audit.json")}
    assert p.validate(root, data)[0] == []
    write(artifact, "tampered events")
    assert any("changed dependent artifact" in e for e in p.validate(root, data)[0])


@pytest.mark.parametrize("fresh_campaign,verdict,execution_source,audit_source,expected", [
    (False, "INCONCLUSIVE", "old", "current", "HISTORICAL DIAGNOSTIC"),
    (False, "PASS", "old", "current", "PASS requires a fresh mutation execution"),
    (True, "PASS", "current", "current", "CURRENT"),
    (True, "PASS", "old", "old", "STALE"),
    (True, "PASS", "old", "current", "mutation source differs"),
])
def test_mutation_freshness_tracks_execution_not_import_receipt(
    program, fresh_campaign, verdict, execution_source, audit_source, expected
):
    root, data = program
    old = root / data["campaign_receipts"]["V01"]["run"]
    run = root / "validation/artifacts/V03/run-1"
    run.parent.mkdir(parents=True)
    old.rename(run)
    write(run.parent / "latest.json", {"run": "run-1"})
    write(root / "validation/protocols/v03_protocol.md", "protocol")
    digests = {"old": "0" * 64, "current": p.source_digest(root)}
    result = p.read_json(run / "results.json")
    result.update(validation_id="V03", fresh_campaign=fresh_campaign,
                  source_digest=digests[execution_source], verdict=verdict,
                  passed=verdict == "PASS",
                  record_type="fresh_execution" if fresh_campaign else "imported_diagnostic")
    write(run / "results.json", result)
    meta = p.read_json(run / "metadata.json")
    meta.update(validation_id="V03", source_digest=digests[audit_source],
                results_sha256=p.sha256(run / "results.json"))
    write(run / "metadata.json", meta)
    audit = p.read_json(run / "v16_audit.json")
    audit["validation_id"] = "V03"
    next(c for c in audit["checks"] if c["name"] == "Decision Adherence")["message"] = f"Recomputed verdict: {verdict}"
    write(run / "v16_audit.json", audit)
    receipt = {"run": str(run.relative_to(root)), "hashes":
               {n: p.sha256(run / n) for n in ("metadata.json", "results.json", "v16_audit.json")}}
    if expected not in {"CURRENT", "STALE", "HISTORICAL DIAGNOSTIC"}:
        with pytest.raises(ValueError, match=expected):
            p.campaign_view(root, "V03", receipt, p.source_digest(root))
    else:
        view = p.campaign_view(root, "V03", receipt, p.source_digest(root))
        assert view["status"] == expected
        assert view["fresh"] is (expected == "CURRENT")


@pytest.mark.parametrize("damage", [None, "listing", "nested_tool", "escaped"])
def test_v03_v2_master_view_binds_nested_retained_evidence(program, damage):
    root, data = program
    old = root / data["campaign_receipts"]["V01"]["run"]
    run = root / "validation/artifacts/V03/run-1"
    run.parent.mkdir(parents=True)
    old.rename(run)
    write(run.parent / "latest.json", {"run": "run-1"})
    write(root / "validation/protocols/v03_protocol.md", "protocol")

    def bound(name, content):
        dest = run / name
        write(dest, content)
        return {"path": str(dest), "sha256": p.sha256(dest)}

    tool = bound("tool.py", "exact tool bytes")
    freeze = bound("freeze.json", {"tool_sources": [tool]})
    listing = bound("listing.txt", "one unresolved raw record")
    if damage == "escaped":
        freeze["path"] = "/unbound/external/freeze.json"
    result = {"schema_version": 2, "validation_id": "V03", "source_digest": p.source_digest(root),
              "fresh_campaign": True, "execution_completed": False, "record_type": "fresh_execution",
              "verdict": "INCONCLUSIVE", "passed": False, "execution_freeze": freeze, "raw_listing": listing}
    write(run / "results.json", result)
    meta = p.read_json(run / "metadata.json")
    meta.update(validation_id="V03", source_digest=result["source_digest"], results_sha256=p.sha256(run / "results.json"))
    write(run / "metadata.json", meta)
    audit = p.read_json(run / "v16_audit.json")
    audit.update(validation_id="V03", run_dir=str(run))
    next(c for c in audit["checks"] if c["name"] == "Decision Adherence")["message"] = "Recomputed verdict: INCONCLUSIVE"
    write(run / "v16_audit.json", audit)
    receipt = {"run": str(run.relative_to(root)), "hashes":
               {n: p.sha256(run / n) for n in ("metadata.json", "results.json", "v16_audit.json")}}
    if damage in {"listing", "nested_tool"}:
        write(run / ("listing.txt" if damage == "listing" else "tool.py"), "tampered")
    if damage:
        with pytest.raises(ValueError):
            p.campaign_view(root, "V03", receipt, p.source_digest(root))
    else:
        view = p.campaign_view(root, "V03", receipt, p.source_digest(root))
        assert view["verdict"] == "INCONCLUSIVE" and view["status"] == "CURRENT"


@pytest.mark.parametrize("damage", [None, "changed", "missing", "extra", "unbound", "dependency_manifest",
                                    "document_changed", "document_missing", "document_extra", "master_receipt", "retained_master"])
def test_master_mutation_freshness_includes_non_python_test_inputs(program, damage):
    root, data = program
    old = root / data["campaign_receipts"]["V01"]["run"]
    run = root / "validation/artifacts/V03/run-1"
    run.parent.mkdir(parents=True)
    old.rename(run)
    write(run.parent / "latest.json", {"run": "run-1"})
    write(root / "validation/protocols/v03_protocol.md", "protocol")
    fixture = root / "tests/fixtures/cases.json"
    write(fixture, [{"input": 1, "expected": 2}])
    retained = run / "test-inputs/cases.json"
    write(retained, fixture.read_text())
    freeze = {"kind": "v03_execution_freeze_v6", "dependencies": p.dependency_versions(), "test_data_inputs": [
        {"relative_path": "tests/fixtures/cases.json", "binding": {"path": str(retained), "sha256": p.sha256(retained)}}]}
    document = root / "docs/fixtures/reference.json"
    write(document, {"fixed": True})
    master = root / "docs/program/program.json"
    write(master, {"revision": 1})
    (root / "pyproject.toml").write_text('[tool.mutmut]\nalso_copy = ["docs/fixtures", "docs/program/program.json"]\n')
    for path in (document, master):
        saved = run / "test-inputs" / path.relative_to(root)
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(path.read_bytes())
        freeze["test_data_inputs"].append({"relative_path": str(path.relative_to(root)),
            "binding": {"path": str(saved), "sha256": p.sha256(saved)}})
    if damage == "unbound":
        freeze.pop("test_data_inputs")
    elif damage == "dependency_manifest":
        freeze["dependencies"]["mutmut"] = "unreviewed-runtime"
    frozen = run / "freeze.json"
    write(frozen, freeze)
    digest = p.source_digest(root)
    result = {"schema_version": 2, "validation_id": "V03", "source_digest": digest,
              "fresh_campaign": True, "execution_completed": False, "record_type": "fresh_execution",
              "verdict": "INCONCLUSIVE", "passed": False,
              "execution_freeze": {"path": str(frozen), "sha256": p.sha256(frozen)}}
    write(run / "results.json", result)
    meta = p.read_json(run / "metadata.json")
    meta.update(validation_id="V03", source_digest=digest, results_sha256=p.sha256(run / "results.json"))
    write(run / "metadata.json", meta)
    audit = p.read_json(run / "v16_audit.json")
    audit.update(validation_id="V03", run_dir=str(run))
    write(run / "v16_audit.json", audit)
    receipt = {"run": str(run.relative_to(root)), "hashes": {
        name: p.sha256(run / name) for name in ("metadata.json", "results.json", "v16_audit.json")}}
    if damage == "changed":
        write(fixture, [])
    elif damage == "missing":
        fixture.rename(root / "removed-fixture.json")
    elif damage == "extra":
        write(root / "tests/fixtures/extra.json", [])
    elif damage == "document_changed":
        write(document, {"fixed": False})
    elif damage == "document_missing":
        document.unlink()
    elif damage == "document_extra":
        write(root / "docs/fixtures/extra.json", {})
    elif damage == "master_receipt":
        write(master, {"revision": 2})
    elif damage == "retained_master":
        write(run / "test-inputs/docs/program/program.json", {"revision": 2})
    assert p.source_digest(root) == digest
    if damage == "retained_master":
        with pytest.raises(ValueError, match="changed dependent artifact"):
            p.campaign_view(root, "V03", receipt, digest)
        return
    view = p.campaign_view(root, "V03", receipt, digest)
    expected_fresh = damage in (None, "master_receipt")
    assert view["status"] == ("CURRENT" if expected_fresh else "STALE")
    assert view["fresh"] is expected_fresh


@pytest.fixture
def release_program(program):
    """Synthetic approval and PASS receipts, never repository certification."""
    root, data = program
    item = data["work_items"][0]
    item.update(state="complete", phase="tier0")
    data["work_items"].append({
        **copy.deepcopy(item), "id": "REL-01", "title": "Release review",
        "state": "planned", "dependencies": ["W1"],
        "decision_dependencies": ["D-PROTOCOL", "D-TIERS"],
    })
    for did in ("D-PROTOCOL", "D-TIERS"):
        data["decisions"].append({
            "id": did, "title": did, "status": "accepted", "rationale": "Test fixture",
            "consequence": "Synthetic prerequisite", "authorization": "Test fixture only",
        })
    data["decisions"][0].update(status="accepted", authorization="Test fixture only")
    data["protocol_bindings"][0]["identity"] = "aligned"
    registry = p.read_json(root / "validation/protocols.json")
    registry["status"] = "CERTIFIED"
    registry["entries"]["V16"] = {"claim": "audit", "gate": "all"}
    write(root / "validation/protocols.json", registry)
    write(root / "validation/protocols/v16_protocol.md", "audit protocol")
    data["protocol_bindings"].append({
        "id": "V16", "registry_claim": "audit", "registry_gate": "all",
        "registry_entry_sha256": p.canonical_digest(registry["entries"]["V16"]),
        "protocol_path": "validation/protocols/v16_protocol.md",
        "protocol_sha256": p.sha256(root / "validation/protocols/v16_protocol.md"),
        "identity": "aligned", "decision_refs": [],
    })
    for entry in data["source_inputs"]:
        entry["sha256"] = p.sha256(root / entry["path"])
    run = root / data["campaign_receipts"]["V01"]["run"]
    result = p.read_json(run / "results.json")
    result.update(verdict="PASS", passed=True)
    write(run / "results.json", result)
    meta = p.read_json(run / "metadata.json")
    meta.update(source_digest=p.source_digest(root), results_sha256=p.sha256(run / "results.json"))
    write(run / "metadata.json", meta)
    audit = p.read_json(run / "v16_audit.json")
    next(c for c in audit["checks"] if c["name"] == "Decision Adherence")["message"] = "Recomputed verdict: PASS"
    write(run / "v16_audit.json", audit)
    data["campaign_receipts"]["V01"]["hashes"] = {
        name: p.sha256(run / name) for name in ("results.json", "metadata.json", "v16_audit.json")
    }
    project(root, data)
    return root, data


def test_release_prerequisites_can_pass_without_circular_release_completion(release_program):
    root, data = release_program
    assert data["work_items"][-1]["state"] == "planned"
    assert p.tier0_release_blockers(root) == []
    data["decisions"].append({"id": "D-LATER", "title": "Later-tier scope", "status": "open",
                              "rationale": "Deferred", "consequence": "No Tier 0 dependency"})
    project(root, data)
    assert p.tier0_release_blockers(root) == []


@pytest.mark.parametrize("damage,fragment", [
    (lambda d: d["decisions"][1].update(status="open"), "D-PROTOCOL is open"),
    (lambda d: d["decisions"][2].update(status="open"), "D-TIERS is open"),
    (lambda d: d["work_items"][0].update(state="blocked"), "W1 is blocked"),
    (lambda d: d["requirements"][0].update(disposition="unresolved", reason="Open specification"), "APP-01 remains unresolved"),
    (lambda d: d["protocol_bindings"][0].update(identity="unresolved"), "V01 protocol identity"),
    (lambda d: d["protocol_bindings"][1].update(identity="unresolved", decision_refs=["D1"]), "V16 protocol identity"),
    (lambda d: d["work_items"].pop(), "REL-01 release work item is missing"),
])
def test_current_pass_receipts_do_not_bypass_master_requirements(release_program, damage, fragment):
    root, data = release_program
    damage(data)
    project(root, data)
    assert fragment in "\n".join(p.tier0_release_blockers(root))


def test_draft_register_blocks_even_with_accepted_decision_labels(release_program):
    root, data = release_program
    registry = p.read_json(root / "validation/protocols.json")
    registry["status"] = "DRAFT"
    write(root / "validation/protocols.json", registry)
    for entry in data["source_inputs"]:
        entry["sha256"] = p.sha256(root / entry["path"])
    project(root, data)
    assert "Protocol register is DRAFT" in "\n".join(p.tier0_release_blockers(root))


def test_removing_release_dependency_does_not_hide_unfinished_tier0_work(release_program):
    root, data = release_program
    data["work_items"][1]["dependencies"] = []
    data["work_items"][0]["state"] = "blocked"
    project(root, data)
    assert "W1 is blocked" in p.tier0_release_blockers(root)


def test_release_guard_follows_transitive_program_decisions(release_program):
    root, data = release_program
    prerequisite = {**copy.deepcopy(data["work_items"][0]), "id": "PRE", "phase": "program",
                    "state": "blocked", "decision_dependencies": ["D-RESOURCE"]}
    data["decisions"].append({"id": "D-RESOURCE", "title": "Resource assignment", "status": "open",
                              "rationale": "Unassigned", "consequence": "Blocked"})
    data["work_items"].append(prerequisite)
    data["work_items"][0].update(state="blocked", dependencies=["PRE"])
    project(root, data)
    blockers = p.tier0_release_blockers(root)
    assert "PRE is blocked" in blockers
    assert "D-RESOURCE is open or missing" in blockers


def test_release_guard_rejects_stale_or_edited_master_and_receipts(release_program):
    root, data = release_program
    write(root / "hponas/change.py", "changed = True\n")
    assert any("Program consistency" in x for x in p.tier0_release_blockers(root))
    project(root, data)
    assert "V01 lacks a current passing registered receipt" in p.tier0_release_blockers(root)
    write(root / "review.md", "tampered")
    assert any("Evidence changed" in x for x in p.tier0_release_blockers(root))


def test_gate_applies_master_guard_even_when_every_campaign_auditor_passes(release_program, monkeypatch):
    import sys
    from types import SimpleNamespace
    from validation.v16_audit_enforcer import V16Enforcer
    from tools.gate_check import check_tier0_gate

    root, data = release_program
    # Keep governance CI dependency-free; scientific recomputation is the
    # explicitly mocked boundary, while the master guard and files are real.
    monkeypatch.setitem(sys.modules, "validation.evidence", SimpleNamespace(TIER0=("V01",)))
    audit = SimpleNamespace(passed=True, checks=[])
    monkeypatch.setattr(V16Enforcer, "audit_execution", lambda *args: audit)
    assert check_tier0_gate(program_root=root).verdict == "pass"
    data["decisions"][1]["status"] = "open"
    project(root, data)
    result = check_tier0_gate(program_root=root)
    assert result.verdict == "blocked"
    assert result.criteria[0].name == "Master program prerequisites"
    assert "D-PROTOCOL" in result.criteria[0].message
    assert all(c.status == "met" for c in result.criteria[1:])
    audit.passed = False
    data["decisions"][1]["status"] = "accepted"
    project(root, data)
    result = check_tier0_gate(program_root=root)
    assert result.criteria[0].status == "met"
    assert result.verdict == "blocked"
    audit.passed = True
    result = check_tier0_gate(root / "alternate-artifacts", program_root=root)
    assert result.verdict == "blocked"
    assert "Campaign root differs" in result.criteria[0].message


def test_release_guard_rejects_missing_program(tmp_path):
    blockers = p.tier0_release_blockers(tmp_path)
    assert blockers and "Program consistency" in blockers[0]


def test_passing_gate_is_not_release_approval(tmp_path, capsys):
    from tools.gate_check import GateResult, print_report, write_report

    result = GateResult(phase="tier0", verdict="pass", criteria=[], timestamp="test")
    print_report(result, mode="dry-run")
    output = capsys.readouterr().out
    assert "explicit release approval are still required" in output
    assert "Phase may close" not in output
    report = write_report(result, tmp_path).read_text()
    assert "explicit release approval are still required" in report
    assert "Phase may close" not in report
