"""Deterministic program views. Consistency is distinct from release certification."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re

from tools.source_identity import ROOT, dependency_versions, source_digest, test_data_paths

REGISTER = "docs/program/program.json"
MASTER = "CONSOLIDATED_MASTER_AUTHORITY.md"
START = "<!-- BEGIN GENERATED PROGRAM STATUS -->"
END = "<!-- END GENERATED PROGRAM STATUS -->"
STATES = {"planned", "in_progress", "complete", "blocked", "deferred"}
IMPLEMENTATION = {"planned", "partial", "implemented", "verified", "not_applicable"}
DISPOSITIONS = {"required", "optional", "deferred", "excluded", "unresolved"}
AUDIT_CHECKS = {"Protocol Immutability", "Decision Adherence", "Artifact Completeness",
                "Metadata Correctness", "Known Issues Disclosure"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=_unique_object)


def local_path(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f"Expected repository-relative path: {name!r}")
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f"Path escapes repository: {name}")
    return path


def _index(items, label):
    if not isinstance(items, list) or not items:
        raise ValueError(f"Missing or empty {label}")
    result = {}
    for item in items:
        key = item["id"]
        if not isinstance(key, str) or not key or key in result:
            raise ValueError(f"Invalid or duplicate {label} ID: {key!r}")
        result[key] = item
    return result


def execution_gate_ids(root):
    """Read actual gate IDs without importing the scientific dependency stack."""
    tree = ast.parse((Path(root) / "validation/evidence.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "TIER0" for t in node.targets
        ):
            values = ast.literal_eval(node.value)
            if not values or len(values) != len(set(values)):
                raise ValueError("Empty or duplicate executable gate IDs")
            return list(values)
    raise ValueError("Executable Tier 0 gate definition missing")


def campaign_view(root, vid, receipt, current_digest, *, require_latest=True):
    """Verify stored receipt bindings; full decision recomputation remains V16's job."""
    run = local_path(root, receipt["run"])
    expected_parent = (Path(root) / "validation/artifacts" / vid).resolve()
    if run.parent != expected_parent:
        raise ValueError(f"{vid}: campaign directory identity differs")
    if require_latest and read_json(expected_parent / "latest.json") != {"run": run.name}:
        raise ValueError(f"{vid}: register does not reference latest campaign")
    names = ("metadata.json", "results.json", "v16_audit.json")
    for name in names:
        if sha256(run / name) != receipt["hashes"].get(name):
            raise ValueError(f"{vid}: changed or unbound {name}")
    meta, result, audit = (read_json(run / n) for n in names)
    if any(x.get("validation_id") != vid for x in (meta, result, audit)):
        raise ValueError(f"{vid}: artifact identity mismatch")
    # Preserve historical v1 receipts as stale after the authorized v2 repair.
    finite = (result.get("schema_version") == 2 and result.get("scope") in {
        "V01": {"finite_reference_trace_conformance_v1", "finite_reference_trace_conformance_v2"},
        "V02": {"recorded_event_and_runtime_conformance_v1"},
    }.get(vid, set()) and vid in {"V01", "V02"})
    mutation_v2 = vid == "V03" and result.get("schema_version") == 2
    if result.get("schema_version") != 1 and not finite and not mutation_v2 and not (
        vid in {"V04-T0", "V05"} and (
            (result.get("schema_version") == 2 and result.get("claim") == "registered_tier0_comparison")
            or (result.get("schema_version") == 3 and result.get("claim") == "protected_paired_rank_finite_suite_v1")
            or (result.get("schema_version") == 4 and result.get("claim") == "finite_stylized_known_answer_conformance_v1")
        )
    ):
        raise ValueError(f"{vid}: unknown result schema")
    verdict = result.get("verdict")
    if verdict not in {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}:
        raise ValueError(f"{vid}: invalid verdict")
    if result.get("passed") is not (verdict == "PASS"):
        raise ValueError(f"{vid}: contradictory passed field")
    if meta.get("results_sha256") != sha256(run / "results.json"):
        raise ValueError(f"{vid}: result is not bound to metadata")
    if not re.fullmatch(r"[0-9a-f]{64}", meta.get("source_digest", "")):
        raise ValueError(f"{vid}: missing execution fingerprint")
    checks = audit.get("checks", [])
    if len(checks) != len(AUDIT_CHECKS) or {c.get("name") for c in checks} != AUDIT_CHECKS:
        raise ValueError(f"{vid}: missing V16 checks")
    if any(c.get("severity") not in {"error", "warning", "info"} or not isinstance(c.get("passed"), bool) for c in checks):
        raise ValueError(f"{vid}: malformed V16 checks")
    if any(c["severity"] != "error" for c in checks if c["name"] != "Metadata Correctness"):
        raise ValueError(f"{vid}: mandatory V16 checks cannot be demoted to warnings")
    calculated = all(c["passed"] for c in checks if c["severity"] == "error")
    if audit.get("passed") is not calculated:
        raise ValueError(f"{vid}: contradictory V16 verdict")
    if verdict == "PASS" and not calculated:
        raise ValueError(f"{vid}: PASS without a passing V16 audit")
    decision = next(c for c in checks if c["name"] == "Decision Adherence")
    if calculated and decision.get("message") != f"Recomputed verdict: {verdict}":
        raise ValueError(f"{vid}: audit does not bind the declared decision")
    # Campaigns currently record absolute paths. Relocate only from the recorded
    # repository root to this checkout; never read arbitrary external paths in CI.
    recorded_run = Path(audit.get("run_dir", str(run)))
    relative_run = Path(receipt["run"])
    if not recorded_run.is_absolute() or tuple(recorded_run.parts[-len(relative_run.parts):]) != relative_run.parts:
        raise ValueError(f"{vid}: invalid recorded run location")
    recorded_root = recorded_run.parents[len(relative_run.parts) - 1]
    dependent_root = Path(root)
    retained = receipt.get("retained_artifacts", {})
    if retained and not (mutation_v2 and verdict != "PASS" and meta["source_digest"] != current_digest):
        raise ValueError("Only stale non-PASS V03 attempts may relocate historical external artifacts")
    for binding in retained.values():
        if sha256(local_path(root, binding["path"])) != binding["sha256"]:
            raise ValueError("Changed retained historical mutation artifact")
    if finite:
        suffix = "finite-v01" if vid == "V01" else ""
        if Path(result.get("run_dir", "")) != recorded_run / suffix:
            raise ValueError(f"{vid}: finite evidence run differs from campaign")
        dependent_root = run / suffix

    def verify_dependents(value, base=dependent_root):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                path = Path(value["path"])
                if path.is_absolute():
                    if not path.is_relative_to(recorded_root):
                        relocated = retained.get(str(path))
                        if relocated is None or relocated["sha256"] != value["sha256"]:
                            raise ValueError(f"{vid}: dependent artifact escapes recorded repository")
                        local = local_path(root, relocated["path"])
                    else:
                        path = path.relative_to(recorded_root)
                        local = local_path(root, str(path))
                else:
                    local = local_path(base, str(path))
                if sha256(local) != value["sha256"]:
                    raise ValueError(f"{vid}: changed dependent artifact: {path}")
            for nested in value.values():
                verify_dependents(nested, base)
        elif isinstance(value, list):
            for nested in value:
                verify_dependents(nested, base)

    verify_dependents(result)
    mutation_data_current = True
    if mutation_v2:
        freeze_path = Path(result["execution_freeze"]["path"])
        if str(freeze_path) in retained:
            freeze_path = local_path(root, retained[str(freeze_path)]["path"])
        else:
            freeze_path = local_path(root, str(freeze_path.relative_to(recorded_root)))
        frozen_mutation = read_json(freeze_path)
        if frozen_mutation.get("kind") in {"v03_execution_freeze_v6", "v03_execution_freeze_v7"}:
            from validation.v03_mutation_testing import same_test_data, test_data_inventory

            # V03 also binds explicitly selected document fixtures. The master
            # context is immutable in the executed snapshot, but later receipt
            # updates are allowed in the live checkout by protocol 2.9.
            def static_inputs(rows):
                return [row for row in rows if row["relative_path"] != "docs/program/program.json"]

            try:
                data_match = same_test_data(static_inputs(frozen_mutation.get("test_data_inputs", [])),
                                            static_inputs(test_data_inventory(root)))
            except (OSError, ValueError):
                data_match = False
            mutation_data_current = ("test_data_inputs" in frozen_mutation
                                     and data_match
                                     and frozen_mutation.get("dependencies") == dependency_versions())
        # Earlier v3 manifests used path/sha256 for source-inventory facts.
        # Those facts belong to the old source, not the current checkout's files.
        # The immutable freeze itself binds them; live comparison is V16's job.
        verify_dependents({k: v for k, v in frozen_mutation.items() if k != "library_ownership"})
        if result.get("calibration"):
            calibration_path = Path(result["calibration"]["path"])
            calibration_path = local_path(root, str(calibration_path.relative_to(recorded_root)))
            verify_dependents(read_json(calibration_path))
    if finite and vid == "V01":
        execution = read_json(local_path(dependent_root, result["execution"]["path"]))
        verify_dependents(execution)
        for ref in execution["cases"]:
            verify_dependents(read_json(local_path(dependent_root, ref["path"])))
    elif finite and vid == "V02":
        execution = read_json(local_path(dependent_root, result["conformance_execution"]["path"]))
        verify_dependents(execution, dependent_root / "conformance")
    protocol = Path(root) / "validation/protocols" / (vid.lower().replace("-", "_") + "_protocol.md")
    fresh = (meta["source_digest"] == current_digest and sha256(protocol) == sha256(run / "protocol.md")
             and mutation_data_current)
    historical_mutation = vid == "V03" and result.get("fresh_campaign") is not True and result.get("record_type") != "fresh_execution"
    if vid == "V03" and not historical_mutation and result.get("source_digest") != meta["source_digest"]:
        raise ValueError("V03: mutation source differs from audited execution fingerprint")
    if historical_mutation and verdict == "PASS":
        raise ValueError("V03: PASS requires a fresh mutation execution, not a new import receipt")
    if historical_mutation:
        fresh = False
    return {"id": vid, "verdict": verdict, "audit_passed": calculated,
            "fresh": fresh, "source_digest": meta["source_digest"], "run": receipt["run"],
            "status": "HISTORICAL DIAGNOSTIC" if historical_mutation else "CURRENT" if fresh else "STALE"}


def phase_transition_view(root, data, current_digest):
    """Verify local phase adoption without transferring acceptance to new code."""
    if data["current_phase"] == "tier0_acceptance":
        if data.get("phase_transition"):
            raise ValueError("Phase promotion record contradicts the current phase")
        return {"label": "Tier 0 acceptance / remediation", "status": "BLOCKED",
                "message": "No transition to Tier 1 has been certified."}
    if data["current_phase"] != "tier1_development":
        raise ValueError("Phase promotion requires an explicit reviewed program amendment")
    evidence = _index(data["evidence"], "evidence")

    def bound(binding):
        path = local_path(root, binding["path"])
        if sha256(path) != binding["sha256"]:
            raise ValueError("Phase promotion evidence changed: " + binding["path"])
        return read_json(path)

    record = bound(evidence[data["phase_transition"]])
    if (record.get("kind") != "local_phase_adoption_v1"
            or record.get("from_phase") != "tier0_acceptance"
            or record.get("to_phase") != data["current_phase"]):
        raise ValueError("Phase promotion identity differs")
    decision = next(d for d in data["decisions"] if d["id"] == record["decision_id"])
    if (decision["status"] != "accepted" or decision.get("kind") != "phase_amendment"
            or data["phase_transition"] not in decision.get("evidence_refs", [])):
        raise ValueError("Phase promotion requires a bound accepted amendment")
    authorization = record.get("authorization", {})
    if (authorization.get("scope") != "local_baseline_and_continued_development"
            or authorization.get("external_publication") is not False
            or not authorization.get("standing_user_instructions")):
        raise ValueError("Phase promotion requires explicit local authorization scope")
    steps = {s["id"]: s for s in data["continuation"]["steps"]}
    for sid in ("REL-01/TIER0-RELEASE-REVIEW", "REL-01/PHASE-TRANSITION-REPAIR",
                "REL-01/RELEASE-AUTHORIZATION"):
        if steps[sid]["state"] != "complete":
            raise ValueError("Phase promotion prerequisite is incomplete: " + sid)
    if next(w for w in data["work_items"] if w["id"] == "REL-01")["state"] != "complete":
        raise ValueError("Phase promotion requires reconciled release work")
    verified = bound(record["verification"])
    if (verified.get("kind") != "phase_transition_repair_verification_v1"
            or verified.get("returncode") != 0 or verified.get("failures") != 0
            or type(verified.get("tests")) is not int or verified["tests"] < 1
            or verified.get("source_digest") != record.get("implementation_source_digest")):
        raise ValueError("Phase promotion implementation verification is incomplete")
    package = bound(record["package"])
    if package.get("kind") != "tier0_objective_baseline_package_v1":
        raise ValueError("Phase promotion requires an objective baseline package")
    baseline_digest = package["source_digest"]
    snapshot = bound(package["source_snapshot"])
    snapshot_root = local_path(root, snapshot["root"])
    if (snapshot.get("kind") != "accepted_source_snapshot_v1"
            or snapshot["source_digest"] != baseline_digest
            or source_digest(snapshot_root) != baseline_digest):
        raise ValueError("Phase promotion accepted source snapshot differs")
    names = [item["path"] for item in snapshot["files"]]
    if len(names) != len(set(names)) or not names:
        raise ValueError("Phase promotion source inventory is malformed")
    for item in snapshot["files"]:
        if sha256(local_path(snapshot_root, item["path"])) != item["sha256"]:
            raise ValueError("Phase promotion retained source/data changed")
    if not {str(p.relative_to(snapshot_root)) for p in test_data_paths(snapshot_root)} <= set(names):
        raise ValueError("Phase promotion test data are not fully retained")
    reviewed = bound(package["reviewed_program"])
    master = local_path(root, package["reviewed_master"]["path"])
    if sha256(master) != package["reviewed_master"]["sha256"]:
        raise ValueError("Phase promotion reviewed master changed")
    gate = bound(package["gate_review"])
    inputs = {b["path"]: b["sha256"] for b in gate["inputs"]}
    if (inputs.get(REGISTER) != package["reviewed_program"]["sha256"]
            or inputs.get(MASTER) != package["reviewed_master"]["sha256"]):
        raise ValueError("Phase promotion gate does not bind the reviewed program")
    required = reviewed["tier0_campaigns"]
    criteria = gate.get("result", {}).get("criteria", [])
    if (gate.get("error") is not None or gate.get("returncode") != 0
            or gate.get("source_digest") != baseline_digest
            or gate.get("result", {}).get("phase") != "tier0"
            or gate.get("result", {}).get("verdict") != "pass"
            or len(criteria) != len(required) + 1
            or {c["name"] for c in criteria} != {"Master program prerequisites", *required}
            or any(c["status"] != "met" for c in criteria)):
        raise ValueError("Phase promotion lacks a complete objectively passing gate")
    if (required != execution_gate_ids(snapshot_root)
            or package["campaign_receipts"] != reviewed["campaign_receipts"]):
        raise ValueError("Phase promotion campaign identities differ from gate inputs")
    for vid in required:
        campaign = campaign_view(root, vid, package["campaign_receipts"][vid],
                                 current_digest, require_latest=False)
        if (campaign["verdict"] != "PASS" or not campaign["audit_passed"]
                or campaign["source_digest"] != baseline_digest):
            raise ValueError("Phase promotion baseline campaign is not accepted: " + vid)
    return {"label": "Tier 1 development", "status": "LOCAL BASELINE ACCEPTED",
            "baseline_source_digest": baseline_digest,
            "current_source_is_baseline": current_digest == baseline_digest,
            "message": "Tier-0 acceptance applies to the retained source. Current development and later phases require their own acceptance. No external release is recorded."}


def validate(root=ROOT, program=None):
    """Return errors and evidence; truthful blocked work is a consistent program."""
    root = Path(root)
    errors, views = [], []
    try:
        data = read_json(root / REGISTER) if program is None else program
        if data.get("schema_version") != 1 or data.get("master") != MASTER:
            raise ValueError("Unknown program schema or competing master")
        requirements = _index(data["requirements"], "requirements")
        work = _index(data["work_items"], "work items")
        decisions = _index(data["decisions"], "decisions")
        bindings = _index(data["protocol_bindings"], "protocol bindings")
        evidence = _index(data["evidence"], "evidence")
        inputs = _index(data["source_inputs"], "source inputs")
        input_paths = {entry["path"] for entry in inputs.values()}
        if not {"hpo-survey-decisions.json", "validation/protocols.json", "BUILD_PROGRAM_REVIEW_VERDICT.md"} <= input_paths:
            errors.append("Required specification inputs must remain hash-bound")
        for entry in inputs.values():
            if sha256(local_path(root, entry["path"])) != entry["sha256"]:
                errors.append(f"Source input changed without reconciliation: {entry['path']}")
        for entry in evidence.values():
            if sha256(local_path(root, entry["path"])) != entry["sha256"]:
                errors.append(f"Evidence changed: {entry['id']}")
        imported = _index(read_json(root / "hpo-survey-decisions.json"), "source decisions")
        mapped = [did for req in requirements.values() for did in req["decision_ids"]]
        if len(mapped) != len(set(mapped)) or set(mapped) != set(imported):
            errors.append("Each source decision must have exactly one requirement disposition")
        mapped_findings = {fid for req in requirements.values() for fid in req["audit_findings"]}
        required_findings = {f"A{i:02d}" for i in range(1, 12)} | {f"T{i:02d}" for i in range(1, 7)} | {"V03-accounting"}
        if mapped_findings != required_findings or set(data["audit_findings"]) != required_findings:
            errors.append("Audit findings are missing from the work breakdown")
        if not {f"APP-{i:02d}" for i in range(1, 13)} <= set(requirements):
            errors.append("The twelve approval requirements must remain in the program")
        for req in requirements.values():
            if req["disposition"] not in DISPOSITIONS:
                errors.append(f"{req['id']}: invalid disposition")
            if not req["work_items"] or not set(req["work_items"]) <= set(work):
                errors.append(f"{req['id']}: missing or unknown work item")
            for path in req["sources"]:
                if not local_path(root, path).is_file():
                    errors.append(f"{req['id']}: missing requirement source {path}")
                if path not in input_paths:
                    errors.append(f"{req['id']}: requirement source is not hash-bound: {path}")
            for did in req["decision_ids"]:
                if did in imported and req["disposition"] == "excluded" and imported[did].get("tier") not in {"exclude", "skip"}:
                    amendment = decisions.get(req.get("disposition_decision"), {})
                    if amendment.get("status") != "accepted" or amendment.get("kind") != "scope_amendment":
                        errors.append(f"{req['id']}: required scope cannot be excluded without an accepted amendment")
            if req["disposition"] in {"deferred", "excluded", "unresolved"} and not req.get("reason"):
                errors.append(f"{req['id']}: disposition needs a reason")
        protocols = read_json(root / "validation/protocols.json")
        if not protocols.get("entries") or set(bindings) != set(protocols["entries"]):
            errors.append("Every protocol ID must have an exact, non-aggregate binding")
        for vid, binding in bindings.items():
            original = protocols["entries"].get(vid, {})
            if binding["registry_entry_sha256"] != canonical_digest(original):
                errors.append(f"{vid}: protocol rules changed without reconciliation")
            if binding["registry_claim"] != original.get("claim") or binding["registry_gate"] != original.get("gate", original.get("gates")):
                errors.append(f"{vid}: claim or gate identity differs from register")
            if not local_path(root, binding["protocol_path"]).is_file():
                errors.append(f"{vid}: protocol file missing")
            elif sha256(local_path(root, binding["protocol_path"])) != binding["protocol_sha256"]:
                errors.append(f"{vid}: individual protocol changed without reconciliation")
            if not set(binding["decision_refs"]) <= set(decisions):
                errors.append(f"{vid}: unknown conflict decision")
            if binding["identity"] not in {"aligned", "unresolved"}:
                errors.append(f"{vid}: invalid identity disposition")
            if binding["identity"] == "unresolved" and not binding["decision_refs"]:
                errors.append(f"{vid}: missing conflict decision")
        required = execution_gate_ids(root)
        if data["tier0_campaigns"] != required or set(data["campaign_receipts"]) != set(required):
            errors.append("Program Tier 0 IDs differ from executable gate")
        if data.get("audit_gate") != "V16":
            errors.append("V16 is mandatory for every campaign")
        active = [w["id"] for w in work.values() if w["state"] == "in_progress"]
        if len(active) > 1 or active != ([data["active_work_item"]] if data["active_work_item"] else []):
            errors.append("Active work item must match the single in-progress item")
        for item in work.values():
            wid = item["id"]
            if item["state"] not in STATES or item["implementation"] not in IMPLEMENTATION:
                errors.append(f"{wid}: invalid execution/implementation state")
            for field in ("owner", "next_action", "done_when", "budget"):
                if not item.get(field):
                    errors.append(f"{wid}: missing {field}")
            if not set(item["dependencies"]) <= set(work):
                errors.append(f"{wid}: unknown dependency")
            if not set(item["decision_dependencies"]) <= set(decisions):
                errors.append(f"{wid}: unknown decision dependency")
            if not set(item["evidence_refs"]) <= set(evidence):
                errors.append(f"{wid}: unknown evidence reference")
            if not set(item["acceptance_campaigns"]) <= set(bindings):
                errors.append(f"{wid}: unknown acceptance campaign")
            for path in item["code_refs"] + item["test_refs"]:
                if not local_path(root, path).is_file():
                    errors.append(f"{wid}: missing code/test path {path}")
            if item["state"] == "complete" and not item["evidence_refs"]:
                errors.append(f"{wid}: completion requires evidence")
            if item["state"] in {"complete", "in_progress"}:
                for dependency in item["dependencies"]:
                    if dependency in work and work[dependency]["state"] != "complete":
                        errors.append(f"{wid}: prerequisite {dependency} is not complete")
                for dependency in item["decision_dependencies"]:
                    if dependency in decisions and decisions[dependency]["status"] != "accepted":
                        errors.append(f"{wid}: decision {dependency} remains open")
        visited, visiting = set(), set()

        def visit(wid):
            if wid in visiting:
                raise ValueError(f"Dependency cycle involving {wid}")
            if wid in visited or wid not in work:
                return
            visiting.add(wid)
            for dependency in work[wid]["dependencies"]:
                visit(dependency)
            visiting.remove(wid)
            visited.add(wid)

        for wid in work:
            visit(wid)
        for item in decisions.values():
            if item["status"] not in {"accepted", "open"}:
                errors.append(f"{item['id']}: invalid decision status")
            if not item.get("rationale") or (item["status"] == "accepted" and not item.get("authorization")):
                errors.append(f"{item['id']}: missing decision rationale/authorization")
        from tools.product_trace import validate_trace
        try:
            validate_trace(root, data)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(f"Product clause trace invalid: {exc}")
        if decisions.get("D-CONTINUOUS-EXECUTION", {}).get("status") == "accepted":
            from tools.program_continuation import continuation

            try:
                continuation(data)
            except ValueError as exc:
                errors.append(f"Continuation drift: {exc}")
        current = source_digest(root)
        for vid in required:
            try:
                views.append(campaign_view(root, vid, data["campaign_receipts"][vid], current))
            except (KeyError, ValueError, OSError, TypeError) as exc:
                errors.append(str(exc))
        phase = None
        try:
            phase = phase_transition_view(root, data, current)
        except (KeyError, ValueError, TypeError, OSError, StopIteration) as exc:
            errors.append(f"Phase promotion invalid: {exc}")
        return errors, {"program": data, "campaigns": views, "source_digest": current,
                        "phase": phase}
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return errors + [f"Invalid program: {exc}"], {}


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_status(view):
    data = view["program"]
    phase = view["phase"]
    lines = ["## Current execution status", "",
             f"Program revision: **{data['revision']}**. Current phase: **{phase['label']}**.",
             "", f"**Release status: {phase['status']}.** {phase['message']}", "",
             f"Executable source fingerprint: `{view['source_digest']}`.", "",
             "These are stored evidence verdicts. CURRENT means source and protocol match; STALE requires revalidation. A new audit cannot make a HISTORICAL DIAGNOSTIC into fresh mutation execution. Full gate recomputation is required for acceptance.", "",
             "| Campaign | Recorded verdict | V16 receipt | Freshness | Run |",
             "|---|---|---|---|---|"]
    for c in view["campaigns"]:
        lines.append(f"| {c['id']} | {c['verdict']} | {'PASS' if c['audit_passed'] else 'FAIL'} | {c['status']} | `{c['run']}` |")
    lines += ["", f"Active work item: **{data['active_work_item'] or 'none'}**."]
    if data.get("continuation"):
        from tools.program_continuation import continuation

        flow = continuation(data)
        lines += ["", f"Continuation: **{flow['status']}**. Stop eligible: **{str(flow['stop_eligible']).lower()}**."]
        if flow["next_step"]:
            step = flow["next_step"]
            lines += [f"Current continuation step: **{step['id']}** — {step['action']}."]
    lines += ["",
              "## Work breakdown", "",
              "Execution and implementation states are separate from campaign acceptance. Completing a repair does not close its performance gate.", "",
              "| ID | Work | Execution | Implementation | Dependencies | Next action |",
              "|---|---|---|---|---|---|"]
    for w in data["work_items"]:
        lines.append("| " + " | ".join(_cell(v) for v in (
            w["id"], w["title"], w["state"], w["implementation"],
            ", ".join(w["dependencies"] + w["decision_dependencies"]) or "—", w["next_action"]
        )) + " |")
    lines += ["", "## Decisions and unresolved conflicts", "",
              "| ID | State | Decision / issue | Consequence |", "|---|---|---|---|"]
    for d in data["decisions"]:
        lines.append("| " + " | ".join(_cell(d[k]) for k in ("id", "status", "title", "consequence")) + " |")
    return "\n".join(lines) + "\n"


def render_traceability(view):
    lines = ["# Program requirement traceability", "",
             "Generated by `python tools/update_progress.py` from `docs/program/program.json`. Historical v1 is archived. A disposition is not a validation PASS.", "",
             "| Requirement | Scope / source decisions | Disposition | Work items | Reason |",
             "|---|---|---|---|---|"]
    for r in view["program"]["requirements"]:
        lines.append("| " + " | ".join(_cell(v) for v in (
            r["id"], r["title"] + (" (" + ", ".join(r["decision_ids"]) + ")" if r["decision_ids"] else ""),
            r["disposition"], ", ".join(r["work_items"]), r["reason"]
        )) + " |")
    return "\n".join(lines) + "\n"


def generated_documents(root, view):
    root = Path(root)
    master = (root / MASTER).read_text()
    if master.count(START) != 1 or master.count(END) != 1 or master.index(START) > master.index(END):
        raise ValueError("Master must contain exactly one ordered generated-status block")
    before, rest = master.split(START)
    _, after = rest.split(END)
    status = render_status(view)
    return {
        MASTER: before + START + "\n\n" + status + "\n" + END + after,
        "docs/progress.md": "# Program progress\n\nSee [the master program](../CONSOLIDATED_MASTER_AUTHORITY.md) for authority, scope and operating rules. This view is generated; edit the structured program and regenerate.\n\n" + status,
        "TRACEABILITY_MATRIX_v1.md": render_traceability(view),
    }


def check(root=ROOT, verify_generated=True):
    errors, view = validate(root)
    if errors:
        return errors, view
    if verify_generated:
        try:
            for name, expected in generated_documents(root, view).items():
                path = Path(root) / name
                if not path.exists() or path.read_text() != expected:
                    errors.append(f"Generated view stale: {name}; run python tools/update_progress.py")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return errors, view


def tier0_protocol_scope_blockers(root, data, registry):
    """Accept a fully bound active phase while unrelated protocols remain draft.

    This binds phase scope only. Per-campaign frozen rules, readiness, raw
    reconstruction and every other release prerequisite remain mandatory.
    """
    if registry.get("status") in ("FROZEN", "APPROVED", "CERTIFIED"):
        return []  # Existing global freeze still needs all downstream guards.
    try:
        phases = data.get("protocol_phase_bindings", {})
        if not isinstance(phases, dict):
            raise ValueError("Phase bindings must be an object")
        ident = phases.get("tier0")
        evidence = next(item for item in data["evidence"] if item["id"] == ident)
        if evidence.get("kind") != "phase_protocol_binding":
            raise ValueError("Exact phase protocol binding evidence required")
        path = local_path(root, evidence["path"])
        if sha256(path) != evidence["sha256"]:
            raise ValueError("Phase binding evidence changed")
        bound = read_json(path)
        if not isinstance(bound, dict):
            raise ValueError("Phase binding must be an object")
        if (bound.get("kind") != "phase_protocol_binding_v1" or bound.get("phase") != "tier0"
                or bound.get("source_digest") != source_digest(root)
                or bound.get("register_sha256") != sha256(Path(root) / "validation/protocols.json")):
            raise ValueError("Phase binding source/register identity differs")
        required = set(execution_gate_ids(root)) | {"V16"}
        if set(bound.get("entries", {})) != required:
            raise ValueError("Exact complete Tier-0 entry set required")
        bindings = _index(data["protocol_bindings"], "protocol bindings")
        for vid in required:
            binding = bindings[vid]
            expected = {"registry_entry_sha256": canonical_digest(registry["entries"][vid]),
                        "protocol_path": binding["protocol_path"],
                        "protocol_sha256": sha256(local_path(root, binding["protocol_path"]))}
            if binding["identity"] != "aligned" or bound["entries"][vid] != expected:
                raise ValueError(f"{vid}: unresolved or stale phase protocol identity")
    except (KeyError, ValueError, TypeError, OSError, StopIteration) as error:
        return [f"Protocol register is {registry.get('status', 'unspecified')}; "
                f"complete current Tier-0 protocol binding required ({error})"]
    return []


def tier0_release_blockers(root=ROOT):
    """Check master prerequisites; passing campaigns do not approve the program.

    REL-01 itself need not be complete: these checks are inputs to its review.
    Deferred later-tier decisions do not block Tier 0 unless explicitly linked.
    """
    errors, view = check(root)
    if errors:
        return [f"Program consistency: {error}" for error in errors]
    data = view["program"]
    work = {item["id"]: item for item in data["work_items"]}
    decisions = {item["id"]: item for item in data["decisions"]}
    release = work.get("REL-01")
    if release is None:
        return ["REL-01 release work item is missing"]

    blockers = []
    registry = read_json(Path(root) / "validation/protocols.json")
    blockers.extend(tier0_protocol_scope_blockers(root, data, registry))
    # Historical status labels are administrative metadata. The gate must still
    # reconstruct scientific outcomes; neither these labels nor approval override it.

    # Include Tier 0 work even if it was accidentally removed from REL-01's
    # direct dependencies, plus every transitive program prerequisite.
    required_work = {wid for wid, item in work.items() if item.get("phase") == "tier0"}
    pending = ["REL-01", *sorted(required_work)]
    visited = set()
    required_decisions = {"D-PROTOCOL", "D-TIERS"}
    while pending:
        wid = pending.pop()
        if wid in visited:
            continue
        visited.add(wid)
        item = work[wid]  # check() has validated all dependency references/cycles.
        pending.extend(item["dependencies"])
        required_decisions.update(item["decision_dependencies"])
        if wid != "REL-01" and item["state"] != "complete":
            blockers.append(f"{wid} is {item['state']}")
    for did in sorted(required_decisions):
        if decisions.get(did, {}).get("status") != "accepted":
            blockers.append(f"{did} is open or missing")

    for req in data["requirements"]:
        if req["disposition"] == "unresolved" and visited.intersection(req["work_items"]):
            blockers.append(f"{req['id']} remains unresolved: {req['title']}")
    active_protocols = set(data["tier0_campaigns"]) | {data["audit_gate"]}
    missing = active_protocols - {binding["id"] for binding in data["protocol_bindings"]}
    for vid in sorted(missing):
        blockers.append(f"{vid} protocol binding is missing")
    for binding in data["protocol_bindings"]:
        if binding["id"] in active_protocols and binding["identity"] != "aligned":
            blockers.append(f"{binding['id']} protocol identity remains unresolved")
    # These receipt checks bind the register to the campaign set used for the
    # release. The gate independently recomputes each scientific decision.
    for campaign in view["campaigns"]:
        if not campaign["fresh"] or campaign["verdict"] != "PASS" or not campaign["audit_passed"]:
            blockers.append(f"{campaign['id']} lacks a current passing registered receipt")
    return blockers
