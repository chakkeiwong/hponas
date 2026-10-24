"""Complete mutation artifacts and abnormal evidence must fail closed."""

import json

import pytest

from validation.v03_mutation_testing import (
    CALIBRATION_CONTROLS, CALIBRATION_FUNCTION, CALIBRATION_ORDER_TESTS, CALIBRATION_WALL_SECONDS,
    CRITICAL_PATHS, IN_SCOPE_MODULES, DEFERRED_MODULES, FACADE_MODULES,
    MAX_MUTATION_WORKERS, MAX_CAMPAIGN_WALL_SECONDS, _binding, analyze_results,
    inventory_verdict, library_ownership, parse_listing, reconstruct_inventory,
    verify_execution_artifacts,
)
from validation.v03_raw_outcomes import RAW_OUTCOME_POLICY
from validation.v03_resource_scheduler import POLICY_PATH
from tools.source_identity import ROOT


def bind_raw_fixture(directory, result, prefix=""):
    from pathlib import Path
    from tools.source_identity import dependency_versions
    from validation.v03_mutation_testing import test_data_inventory
    result["tested_data_inputs"] = test_data_inventory(ROOT)
    result["end_dependencies"] = dependency_versions()
    grouped = {}
    codes = {"killed": 1, "survived": 0, "not checked": None, "timeout": -24}
    for row in parse_listing(Path(result["raw_listing"]["path"]).read_text())["mutants"]:
        grouped.setdefault(row["module"], {})[row["id"]] = codes[row["status"]]
    result["raw_metadata"] = []
    for module, rows in grouped.items():
        path = directory / (prefix + module + ".meta")
        path.write_text(json.dumps({"exit_code_by_key": rows}))
        result["raw_metadata"].append({"module": module, "binding": _binding(path)})
    result.update(reconstruct_inventory(Path(result["raw_listing"]["path"]).read_text(), result["raw_metadata"]))
    result["inventory_error"] = None
    result["listing_returncode"] = 0
    stderr = directory / (prefix + "listing-stderr.txt")
    stderr.write_text("")
    result["listing_stderr"] = _binding(stderr)
    for key in ("mutation_stats", "worker_log"):
        path = directory / key
        path.write_text("{}" if key == "mutation_stats" else "raw worker evidence\n")
        result[key] = _binding(path)


def calibration_fixture(tmp_path, freeze):
    import sys
    from validation.v03_equivalence import RULES
    from tools.source_identity import dependency_versions
    from validation.v03_mutation_testing import test_data_inventory
    freeze["test_data_inputs"] = test_data_inventory(ROOT)
    freeze["dependencies"] = dependency_versions()
    # Synthetic outcome fixtures carry actual pinned tool bytes.
    from validation.v03_mutation_testing import REQUIRED_TOOL_SOURCES
    overlay = ROOT / "tests/fixtures/v03_tool_overlay_v6"
    freeze["tool_sources"] = [_binding(overlay / (r["relative_path"] + ".txt"))
                              for r in REQUIRED_TOOL_SOURCES]
    freeze["tool_source_manifest"] = REQUIRED_TOOL_SOURCES
    freeze.update(python=sys.executable, calibration_controls=CALIBRATION_CONTROLS,
                  resource_policy=_binding(POLICY_PATH),
                  max_workers=MAX_MUTATION_WORKERS, wall_seconds=MAX_CAMPAIGN_WALL_SECONDS,
                  calibration_wall_seconds=CALIBRATION_WALL_SECONDS,
                  calibration_order_tests=list(CALIBRATION_ORDER_TESTS),
                  equivalence_rules=list(RULES),
                  equivalence_argument=_binding(ROOT / "docs/program/MUTATION_EQUIVALENCE_LEMMAS_2026_10_23.md"))
    lines = [f"{module}.x_function__mutmut_1: not checked" for module in IN_SCOPE_MODULES]
    lines.extend(f"{mid}: {row['status']}" for mid, row in CALIBRATION_CONTROLS.items())
    raw = tmp_path / "calibration-listing.txt"
    raw.write_text("\n".join(lines) + "\n")
    log = tmp_path / "calibration.log"
    log.write_text("Running stats\nRunning clean tests\nRunning forced fail test\nRunning mutation testing\n")
    stats = tmp_path / "calibration-stats.json"
    stats.write_text(json.dumps({"tests_by_mangled_function_name": {CALIBRATION_FUNCTION: ["test_behavior"]},
                                 "duration_by_test": {"test_behavior": .01}}))
    junit = tmp_path / "order.xml"
    junit.write_text('<testsuite>' + ''.join(
        f'<testcase classname="{test.split("::")[0].removesuffix(".py").replace("/", ".")}" '
        f'name="{test.split("::")[-1]}"/>' for test in CALIBRATION_ORDER_TESTS) + '</testsuite>')
    order_log = tmp_path / "order.log"
    order_log.write_text(f"{len(CALIBRATION_ORDER_TESTS)} passed\n")
    diffs = {}
    for i, (mid, row) in enumerate(CALIBRATION_CONTROLS.items()):
        path = tmp_path / f"calibration-{i}.diff"
        path.write_text("-" + row["removed"] + "\n+" + row["added"] + "\n")
        diffs[mid] = _binding(path)
    record = {"kind": "v03_isolation_calibration_v3",
              "end_dependencies": freeze["dependencies"],
              "command": [sys.executable, "-m", "mutmut", "run", "--max-children", str(MAX_MUTATION_WORKERS), *CALIBRATION_CONTROLS],
              "source_digest": freeze["source_digest"], "end_source_digest": freeze["source_digest"],
              "returncode": 0, "timed_out": False, "elapsed_seconds": 1,
              "clean_order": {"command": [sys.executable, "-m", "pytest", "-q", *CALIBRATION_ORDER_TESTS,
                                           "--junitxml=../calibration/order-tests.xml"],
                              "returncode": 0, "timed_out": False, "log": _binding(order_log), "junit": _binding(junit)},
              "log": _binding(log), "raw_listing": _binding(raw), "stats": _binding(stats), "control_diffs": diffs}
    bound = {"raw_listing": record["raw_listing"]}
    bind_raw_fixture(tmp_path, bound, prefix="calibration-")
    record.update({key: bound[key] for key in ("raw_metadata", "listing_returncode", "listing_stderr")})
    record["test_data_inputs"] = test_data_inventory(ROOT)
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(record))
    return _binding(path)


def bind_schedule_fixture(directory, result):
    """Bind a synthetic schedule to the same individual raw fixture outcomes."""
    import hashlib
    from types import SimpleNamespace
    from validation.v03_resource_scheduler import make_rows

    stats = {"tests_by_mangled_function_name": {
        row["id"].split("__mutmut_", 1)[0]: ["fixture::test"] for row in result["mutants"]},
        "duration_by_test": {"fixture::test": .1}}
    stats_path = directory / "schedule-stats.json"
    stats_path.write_text(json.dumps(stats))
    result["mutation_stats"] = _binding(stats_path)
    rows = make_rows([(None, row["id"], None) for row in result["mutants"]],
        stats["tests_by_mangled_function_name"], stats["duration_by_test"],
        SimpleNamespace(timeout_constant=22.0, timeout_multiplier=3.0))
    schedule = {"kind": "v03_complete_resource_schedule_v1", "rows": rows,
        "precompleted": sorted(CALIBRATION_CONTROLS),
        "policy_sha256": _binding(POLICY_PATH)["sha256"],
        "stats_sha256": hashlib.sha256(json.dumps(stats, sort_keys=True).encode()).hexdigest()}
    path = directory / "schedule.json"
    path.write_text(json.dumps(schedule))
    result["resource_schedule"] = _binding(path)
    path = directory / "schedule-trace.jsonl"
    codes = {row["id"]: row["raw_exit_code"] for row in result["mutants"]}
    trace = []
    for row in sorted(rows, key=lambda row: (-row["estimated_test_seconds"], row["mutant"])):
        if row["mutant"] not in CALIBRATION_CONTROLS:
            trace.extend([{"kind": "submit", "mutant": row["mutant"]},
                          {"kind": "complete", "mutant": row["mutant"], "exit_code": codes[row["mutant"]]}])
    path.write_text(''.join(json.dumps(row) + '\n' for row in trace))
    result["resource_trace"] = _binding(path)


@pytest.mark.parametrize("status,expected", [
    ("killed", "PASS"), ("survived", "FAIL"), ("no tests", "FAIL"),
    ("timeout", "INCONCLUSIVE"), ("suspicious", "INCONCLUSIVE"),
    ("not checked", "INCONCLUSIVE"), ("segfault", "INCONCLUSIVE"),
    ("check was interrupted by user", "INCONCLUSIVE"), ("skipped", "INCONCLUSIVE"),
    ("caught by type check", "INCONCLUSIVE"),
])
def test_inventory_classifies_complete_failure_and_unresolved_evidence(status, expected):
    raw = parse_listing("\n".join(f"hponas.space.x_function__mutmut_{i}: {status}" for i in range(100)))
    analysis = analyze_results(raw, required_modules=["hponas.space"])
    assert inventory_verdict(raw, analysis) == expected


@pytest.mark.parametrize("damage", [None, "listing", "tool", "reported_status", "equivalence", "dependency_manifest", "worker_allocation", "wall_allocation"])
def test_reconstruction_binds_raw_individual_results_and_frozen_tool(tmp_path, damage):
    source = tmp_path / "source.py"
    source.write_text("frozen tool or execution input")
    listing = tmp_path / "results.txt"
    listing.write_text("hponas.space.x_function__mutmut_1: survived\n")
    freeze = {
        "kind": "v03_execution_freeze_v8", "source_digest": "fixture",
        "raw_outcome_policy": RAW_OUTCOME_POLICY,
        "library_ownership": library_ownership(ROOT),
        "required_modules": IN_SCOPE_MODULES, "critical_paths": list(CRITICAL_PATHS),
        "tool_version": "3.8.0", "equivalent_exclusions": [], "tool_sources": [_binding(source)],
        **{key: _binding(source) for key in ("config_file", "protocol", "protocol_register")},
    }
    calibration = calibration_fixture(tmp_path, freeze)
    with listing.open("a") as handle:
        handle.write("\n".join(f"{mid}: {row['status']}" for mid, row in CALIBRATION_CONTROLS.items()) + "\n")
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(freeze))
    result = {"source_digest": "fixture", "execution_freeze": _binding(path),
              "raw_listing": _binding(listing), "mutants": parse_listing(listing.read_text())["mutants"],
              "equivalent_mutants": [], "calibration": calibration, "execution_log": _binding(source)}
    bind_raw_fixture(tmp_path, result)
    if damage == "listing":
        listing.write_text("hponas.space.x_function__mutmut_1: killed\n")
    elif damage == "tool":
        changed = tmp_path / "changed-tool.py"
        changed.write_text("changed")
        freeze["tool_sources"][0] = _binding(changed)
        path.write_text(json.dumps(freeze))
        result["execution_freeze"] = _binding(path)
    elif damage == "reported_status":
        result["mutants"][0]["status"] = "killed"
    elif damage == "equivalence":
        result["equivalent_mutants"] = [{"id": result["mutants"][0]["id"], "reviewed_by": "label only"}]
    elif damage in {"worker_allocation", "wall_allocation"}:
        key = "max_workers" if damage == "worker_allocation" else "wall_seconds"
        freeze[key] += 1
        path.write_text(json.dumps(freeze))
        result["execution_freeze"] = _binding(path)
    elif damage == "dependency_manifest":
        freeze["dependencies"]["mutmut"] = "unreviewed-runtime"
        path.write_text(json.dumps(freeze))
        result["execution_freeze"] = _binding(path)
    if damage:
        with pytest.raises(ValueError):
            verify_execution_artifacts(result)
    else:
        assert verify_execution_artifacts(result) == freeze


def test_failed_clean_suite_retains_unchecked_population_without_counting_kills(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace

    from validation import v03_mutation_testing as mutation

    (tmp_path / "validation").mkdir()
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json"):
        (tmp_path / name).write_text("inert fixture")
    monkeypatch.setattr(mutation, "prepare_mutation_workspace", lambda: tmp_path)
    monkeypatch.setattr(mutation, "mutation_freeze", lambda _: {"kind": "inert_fixture"})
    monkeypatch.setattr(mutation, "calibrate_isolation", lambda *a: ({"passed": True}, {}))

    def baseline_failure(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(mutation, "_run_with_deadline", baseline_failure)
    listing = "hponas.space.x_function__mutmut_1: not checked\n"
    metadata = tmp_path / "mutants/hponas/space.py.meta"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"exit_code_by_key": {"hponas.space.x_function__mutmut_1": None}}))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=listing, stderr="", returncode=0))
    result = mutation.run_mutmut()
    assert not result["execution_completed"]
    assert result["execution_error"] == "mutmut run exited 1"
    assert result["not_checked"] == 1 and result["killed"] == 0
    assert result["raw_listing"] == _binding(tmp_path / "individual-results.txt")
    assert (tmp_path / "individual-results.txt").read_text() == listing
    assert (tmp_path / "execution-freeze.json").exists()


@pytest.mark.parametrize("fresh", [True, False])
def test_public_gate_accepts_v2_schema_and_recomputes_unresolved_inventory(monkeypatch, fresh):
    from validation import evidence, v03_mutation_testing as mutation

    checked = []
    monkeypatch.setattr(mutation, "verify_execution_artifacts", lambda value: checked.append(value))
    result = {"schema_version": 2, "validation_id": "V03", "fresh_campaign": fresh,
              "source_digest": evidence.source_digest(), "equivalent_mutants": [],
              "mutants": parse_listing("hponas.space.x_function__mutmut_1: not checked")["mutants"]}
    assert evidence.decision("V03", result) == "INCONCLUSIVE"
    assert bool(checked) == fresh


def test_actual_tpe_implementation_and_decision_functions_are_in_scope():
    import tomllib
    from pathlib import Path

    config = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())["tool"]["mutmut"]
    assert "hponas/searchers_tpe.py" in config["source_paths"]
    assert "hponas.searchers_tpe" in IN_SCOPE_MODULES
    assert {"TPESearcherǁpropose", "TPESearcherǁobserve", "TPESearcherǁload_state_dict"} <= set(CRITICAL_PATHS)


@pytest.mark.parametrize("damage", [None, "unassigned", "missing", "facade_code", "hidden_exclusion"])
def test_whole_library_ownership_catches_jointly_incomplete_configuration(tmp_path, damage):
    import shutil

    shutil.copytree(ROOT / "hponas", tmp_path / "hponas", ignore=shutil.ignore_patterns("__pycache__"))
    if damage == "unassigned":
        (tmp_path / "hponas/new_backend.py").write_text("def f(): return 1\n")
    elif damage == "missing":
        (tmp_path / "hponas/searchers_gp.py").rename(tmp_path / "omitted.py")
    elif damage == "facade_code":
        (tmp_path / "hponas/__init__.py").write_text("def hidden(): return 1\n")
    elif damage == "hidden_exclusion":
        (tmp_path / "hponas/searchers_gp.py").write_text("def hidden(): return 1  # pragma: no mutate\n")
    if damage:
        with pytest.raises(ValueError):
            library_ownership(tmp_path)
    else:
        inventory = library_ownership(tmp_path)
        assert len(inventory) == len(IN_SCOPE_MODULES) + len(DEFERRED_MODULES) + len(FACADE_MODULES)
        assert sum(row["disposition"] == "required" for row in inventory) == 24
        assert sum(row["disposition"] == "deferred" for row in inventory) == len(DEFERRED_MODULES)
        assert {row["module"] for row in inventory if row["disposition"] == "required"} == set(IN_SCOPE_MODULES)


@pytest.mark.parametrize('module', ['evaluation', 'budgets', 'capabilities', 'diagnostics', 'reporting'])
def test_product_foundation_modules_have_explicit_nonmutation_owners(tmp_path, monkeypatch, module):
    import shutil
    from validation import v03_mutation_testing as mutation

    shutil.copytree(ROOT / 'hponas', tmp_path / 'hponas', ignore=shutil.ignore_patterns('__pycache__'))
    name = 'hponas.' + module
    row = next(row for row in library_ownership(tmp_path) if row['module'] == name)
    assert (row['disposition'], row['work_item']) == ('deferred', 'PRD-01')
    monkeypatch.delitem(mutation.DEFERRED_MODULES, name)
    with pytest.raises(ValueError, match='Unassigned or missing'):
        library_ownership(tmp_path)


def test_streaming_product_module_has_gap_owner_without_changing_mutation_population(monkeypatch):
    from validation import v03_mutation_testing as mutation

    name = 'hponas.evaluation_streaming'
    row = next(row for row in library_ownership(ROOT) if row['module'] == name)
    assert (row['disposition'], row['work_item']) == ('deferred', 'GAP-01')
    assert name not in IN_SCOPE_MODULES
    monkeypatch.delitem(mutation.DEFERRED_MODULES, name)
    with pytest.raises(ValueError, match='Unassigned or missing'):
        library_ownership(ROOT)


def test_required_legacy_gp_and_architecture_are_configured_before_freezing():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    assert {"hponas/searchers_gp.py", "hponas/architecture.py", "hponas/priors.py"} <= set(config["source_paths"])


def test_joint_refactor_preserves_critical_proposal_coverage():
    assert {'GPSearcherǁ_suggest_impl', 'GPSearcherǁ_suggest_joint_impl',
            'GPSearcherǁ_joint_finite', 'GPSearcherǁsuggest_batch',
            'GPSearcherǁpending_locations'} <= set(CRITICAL_PATHS)


def test_configured_population_is_exact_despite_later_modules_in_same_directories():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    expected = {name.replace(".", "/") + ".py" for name in IN_SCOPE_MODULES}
    assert set(config["source_paths"]) == expected
    assert all((ROOT / name).is_file() for name in config["source_paths"])
    assert (ROOT / "hponas/searchers/prior.py").is_file()
    assert "hponas/searchers/prior.py" not in expected


def test_workspace_preserves_selected_document_bytes_without_copying_environments(tmp_path, monkeypatch):
    from validation import evidence
    from validation.v03_mutation_testing import prepare_mutation_workspace, same_test_data, test_data_inventory

    source = tmp_path / "source"
    for name in ("hponas", "workloads", "validation", "tools", "tests", "examples", "docs/program/old/py313"):
        (source / name).mkdir(parents=True)
    (source / "pyproject.toml").write_text('[tool.mutmut]\nalso_copy = ["docs/program/reference.json", "docs/program/program.json"]\n')
    (source / "docs/program/reference.json").write_text('{"answer": 42}\n')
    (source / "docs/program/program.json").write_text('{"revision": "fixture"}\n')
    (source / "docs/program/old/py313/environment.bin").write_bytes(b"not a test input")
    (source / "tests/test_case.py").write_text('def test_case(): assert True\n')
    (source / "tests/expected.txt").write_text('42\n')
    monkeypatch.setattr(evidence, "ROOT", source)
    workspace = prepare_mutation_workspace()
    assert (workspace / "tests/test_case.py").read_bytes() == (source / "tests/test_case.py").read_bytes()
    assert not (workspace / "docs/program/old").exists()
    assert same_test_data(test_data_inventory(source), test_data_inventory(workspace))
    (workspace / "docs/program/reference.json").write_text('{"answer": 43}\n')
    assert not same_test_data(test_data_inventory(source), test_data_inventory(workspace))


@pytest.mark.parametrize("fault", ["changed", "missing", "external"])
def test_selected_operation_dependency_is_bound_and_cannot_change(tmp_path, fault):
    from validation.v03_mutation_testing import test_data_inventory, same_test_data

    root = tmp_path / "root"
    (root / "program_operations").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[tool.mutmut]\nalso_copy = ["program_operations/helper.py"]\n')
    helper = root / "program_operations/helper.py"
    helper.write_text('def run(): return 1\n')
    frozen = test_data_inventory(root)
    assert [row["relative_path"] for row in frozen] == ["program_operations/helper.py"]
    if fault == "changed":
        helper.write_text('def run(): return 2\n')
        with pytest.raises(ValueError, match="Changed or missing V03 execution artifact"):
            same_test_data(frozen, test_data_inventory(root))
    else:
        helper.unlink()
        if fault == "external":
            outside = tmp_path / "outside.py"
            outside.write_text('def run(): return 1\n')
            helper.symlink_to(outside)
        with pytest.raises(ValueError, match="document input"):
            test_data_inventory(root)


@pytest.mark.parametrize("fault", ["missing", "external"])
def test_document_fixture_inventory_refuses_missing_or_external_inputs(tmp_path, fault):
    from validation.v03_mutation_testing import test_data_inventory

    root = tmp_path / "root"
    (root / "docs").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[tool.mutmut]\nalso_copy = ["docs/reference.json"]\n')
    if fault == "external":
        outside = tmp_path / "outside.json"
        outside.write_text('{}')
        (root / "docs/reference.json").symlink_to(outside)
    with pytest.raises(ValueError, match="document input"):
        test_data_inventory(root)
    assert {"GPqLogEISearcherǁ_build_acqf", "GPqLogEISearcherǁload_state_dict",
            "CoordinateMLPǁ__init__", "compatible", "build"} <= set(CRITICAL_PATHS)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "other_plugin"])
def test_execution_freeze_refuses_changed_deterministic_order_plugin(tmp_path, monkeypatch, damage):
    from validation import v03_mutation_testing as mutation

    original = (ROOT / "pyproject.toml").read_text()
    entry = '    "-p", "tools.v03_test_order",'
    assert original.count(entry) == 1
    replacement = {"missing": "", "duplicate": entry + "\n" + entry,
                   "other_plugin": '    "-p", "tools.other_order",'}[damage]
    (tmp_path / "pyproject.toml").write_text(original.replace(entry, replacement))
    monkeypatch.setattr(mutation, "verify_phase_register", lambda root: None)
    monkeypatch.setattr(mutation, "library_ownership", lambda root: [])
    with pytest.raises(ValueError, match="inventory-preserving deterministic test order"):
        mutation.mutation_freeze(tmp_path)


def test_retained_evidence_survives_missing_original_temporary_inputs(tmp_path):
    from validation.v03_mutation_testing import retain_execution_artifacts

    work = tmp_path / "temporary"
    work.mkdir()
    source = work / "source"
    source.write_text("frozen input")
    freeze = {"kind": "v03_execution_freeze_v8", "source_digest": "fixture",
              "raw_outcome_policy": RAW_OUTCOME_POLICY,
              "library_ownership": library_ownership(ROOT),
              "required_modules": IN_SCOPE_MODULES, "critical_paths": list(CRITICAL_PATHS),
              "tool_version": "3.8.0", "equivalent_exclusions": [], "tool_sources": [_binding(source)],
              **{k: _binding(source) for k in ("config_file", "protocol", "protocol_register")}}
    calibration = calibration_fixture(work, freeze)
    freeze_path = work / "freeze.json"
    freeze_path.write_text(json.dumps(freeze))
    listing = work / "listing"
    listing.write_text("hponas.space.x_function__mutmut_1: survived\n")
    with listing.open("a") as handle:
        handle.write("\n".join(f"{mid}: {row['status']}" for mid, row in CALIBRATION_CONTROLS.items()) + "\n")
    result = {"source_digest": "fixture", "execution_freeze": _binding(freeze_path),
              "raw_listing": _binding(listing), "mutants": parse_listing(listing.read_text())["mutants"],
              "equivalent_mutants": [], "calibration": calibration, "execution_log": _binding(source)}
    bind_raw_fixture(work, result)
    retain_execution_artifacts(result, tmp_path / "retained")
    work.rename(tmp_path / "unavailable")
    verify_execution_artifacts(result)
    # Keeping the listing/results consistent cannot conceal a changed frozen input.
    from pathlib import Path
    stored = json.loads(Path(result["execution_freeze"]["path"]).read_text())
    Path(stored["tool_sources"][0]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="Changed or missing"):
        verify_execution_artifacts(result)


@pytest.mark.parametrize("damage", [None, "execution_completed", "snapshot_end_source_digest", "end_source_digest"])
def test_gate_cannot_promote_tool_exit_or_changed_source_to_complete_acceptance(monkeypatch, damage):
    from validation import evidence, v03_mutation_testing as mutation

    monkeypatch.setattr(mutation, "verify_execution_artifacts", lambda _: None)
    digest = evidence.source_digest()
    result = {"schema_version": 2, "validation_id": "V03", "source_digest": digest,
              "snapshot_end_source_digest": digest, "end_source_digest": digest,
              "fresh_campaign": True, "execution_completed": True, "equivalent_mutants": [],
              "mutants": parse_listing("\n".join(
                  f"{module}.x_function__mutmut_{i}: killed" for module in IN_SCOPE_MODULES for i in range(5)
              ))["mutants"]}
    if damage:
        result[damage] = False if damage == "execution_completed" else "changed"
    assert evidence.decision("V03", result) == ("INCONCLUSIVE" if damage else "PASS")


def test_coordinator_failure_terminates_its_orphaned_worker_before_returning(tmp_path):
    import os
    import subprocess
    import sys
    from validation.v03_mutation_testing import _run_with_deadline

    (tmp_path / "child.py").write_text(
        "import signal,time\nfrom pathlib import Path\n"
        "def stop(*unused):\n    Path('stopped').write_text('terminated')\n    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM,stop)\nPath('ready').touch()\ntime.sleep(20)\n")
    (tmp_path / "parent.py").write_text(
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        "subprocess.Popen([sys.executable,'child.py'])\n"
        "for _ in range(100):\n    if Path('ready').exists(): break\n    time.sleep(.01)\n"
        "raise SystemExit(3)\n")
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _run_with_deadline([sys.executable, "parent.py"], tmp_path, dict(os.environ), timeout=5)
    assert exc.value.returncode == 3
    assert (tmp_path / "stopped").read_text() == "terminated"


@pytest.mark.parametrize("damage", [None, "false_kill", "false_survival", "wrong_diff", "extra_execution",
                                    "changed_source", "timeout", "clean_failure", "missing_clean", "unbound_tests",
                                    "order_failure", "order_skipped", "order_reversed",
                                    "order_wrong_module", "order_duplicate"])
def test_calibration_reconstructs_controls_and_refuses_misleading_pass_labels(tmp_path, damage):
    from pathlib import Path
    from validation.v03_mutation_testing import verify_calibration

    freeze = {"source_digest": "frozen"}
    ref = calibration_fixture(tmp_path, freeze)
    record = json.loads(Path(ref["path"]).read_text())
    record["passed"] = True
    if damage in {"false_kill", "false_survival", "extra_execution"}:
        path = Path(record["raw_listing"]["path"])
        text = path.read_text()
        if damage == "false_kill":
            text = text.replace(": survived", ": killed")
        elif damage == "false_survival":
            text = text.replace(": killed", ": survived")
        else:
            text = text.replace(": not checked", ": killed", 1)
        path.write_text(text)
        record["raw_listing"] = _binding(path)
    elif damage == "wrong_diff":
        mid = next(iter(CALIBRATION_CONTROLS))
        path = Path(record["control_diffs"][mid]["path"])
        path.write_text(path.read_text().replace("+    X_train = None", "+    X_train = []"))
        record["control_diffs"][mid] = _binding(path)
    elif damage == "changed_source":
        record["end_source_digest"] = "other"
    elif damage == "timeout":
        record["timed_out"] = True
    elif damage == "clean_failure":
        record["returncode"] = 1
    elif damage == "missing_clean":
        path = Path(record["log"]["path"])
        path.write_text("Running mutation testing\n")
        record["log"] = _binding(path)
    elif damage == "unbound_tests":
        path = Path(record["stats"]["path"])
        path.write_text("{}")
        record["stats"] = _binding(path)
    elif damage == "order_failure":
        record["clean_order"]["returncode"] = 1
    elif damage == "order_skipped":
        path = Path(record["clean_order"]["junit"]["path"])
        path.write_text(path.read_text().replace('/>', '><skipped/></testcase>', 1))
        record["clean_order"]["junit"] = _binding(path)
    elif damage in {"order_reversed", "order_wrong_module", "order_duplicate"}:
        import xml.etree.ElementTree as ET

        path = Path(record["clean_order"]["junit"]["path"])
        tree = ET.fromstring(path.read_text())
        if damage == "order_reversed":
            tree[:] = list(reversed(list(tree)))
        elif damage == "order_wrong_module":
            tree[0].set("classname", "unrelated.module")
        else:
            tree[1].set("classname", tree[0].get("classname"))
            tree[1].set("name", tree[0].get("name"))
        path.write_text(ET.tostring(tree, encoding="unicode"))
        record["clean_order"]["junit"] = _binding(path)
    assert verify_calibration(record, freeze) is (damage is None)


def test_full_run_is_not_launched_after_failed_calibration(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from validation import v03_mutation_testing as mutation
    import subprocess

    (tmp_path / "validation").mkdir()
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json"):
        (tmp_path / name).write_text("inert fixture")
    monkeypatch.setattr(mutation, "prepare_mutation_workspace", lambda: tmp_path)
    monkeypatch.setattr(mutation, "mutation_freeze", lambda _: {"kind": "inert_fixture"})
    monkeypatch.setattr(mutation, "calibrate_isolation", lambda *a: ({"passed": False}, {}))
    monkeypatch.setattr(mutation, "_run_with_deadline", lambda *a, **kw: pytest.fail("Full run bypassed calibration"))
    metadata = tmp_path / "mutants/hponas/space.py.meta"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"exit_code_by_key": {"hponas.space.x_function__mutmut_1": None}}))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="hponas.space.x_function__mutmut_1: not checked\n", stderr="", returncode=0))
    result = mutation.run_mutmut()
    assert not result["execution_completed"]
    assert result["execution_error"] == "Required mutation isolation calibration failed"


@pytest.mark.parametrize("code,tool_status", [(255, "timeout"), (3, "killed")])
@pytest.mark.parametrize("damage", [None, "forged_status", "missing_metadata", "changed_metadata", "missing_worker_log",
                                    "missing_test_data", "changed_test_data", "rebound_test_data", "end_dependencies"])
def test_raw_runner_failures_remain_unresolved_through_retention_and_public_gate(tmp_path, code, tool_status, damage):
    from pathlib import Path
    from validation import evidence
    from validation.v03_mutation_testing import retain_execution_artifacts

    work = tmp_path / "working"
    work.mkdir()
    source = work / "source"
    source.write_text("bound input bytes\n")
    digest = evidence.source_digest()
    freeze = {"kind": "v03_execution_freeze_v8", "source_digest": digest,
              "raw_outcome_policy": RAW_OUTCOME_POLICY,
              "library_ownership": library_ownership(ROOT),
              "required_modules": IN_SCOPE_MODULES, "critical_paths": list(CRITICAL_PATHS),
              "tool_version": "3.8.0", "tool_sources": [_binding(source)],
              **{k: _binding(source) for k in ("config_file", "protocol", "protocol_register")}}
    calibration = calibration_fixture(work, freeze)
    frozen_path = work / "freeze.json"
    frozen_path.write_text(json.dumps(freeze))
    listing = work / "listing"
    mid = "hponas.space.x_function__mutmut_1"
    listing.write_text("\n".join(
        [f"{module}.x_function__mutmut_{i}: killed" for module in IN_SCOPE_MODULES for i in range(1, 6)]
        + [f"{key}: {row['status']}" for key, row in CALIBRATION_CONTROLS.items()]) + "\n")
    result = {"validation_id": "V03", "schema_version": 2, "source_digest": digest,
              "end_source_digest": digest, "snapshot_end_source_digest": digest,
              "fresh_campaign": True, "execution_completed": True,
              "execution_freeze": _binding(frozen_path), "raw_listing": _binding(listing),
              "equivalent_mutants": [], "calibration": calibration, "execution_log": _binding(source)}
    bind_raw_fixture(work, result)
    listing.write_text(listing.read_text().replace(mid + ": killed", mid + ": " + tool_status))
    result["raw_listing"] = _binding(listing)
    entry = next(row for row in result["raw_metadata"] if row["module"] == "hponas.space")
    metadata = Path(entry["binding"]["path"])
    raw = json.loads(metadata.read_text())
    raw["exit_code_by_key"][mid] = code
    metadata.write_text(json.dumps(raw))
    entry["binding"] = _binding(metadata)
    result.update(reconstruct_inventory(listing.read_text(), result["raw_metadata"]))
    bind_schedule_fixture(work, result)
    retain_execution_artifacts(result, tmp_path / "retained")
    work.rename(tmp_path / "unavailable")
    if damage == "forged_status":
        next(row for row in result["mutants"] if row["id"] == mid)["status"] = tool_status
    elif damage == "missing_metadata":
        result["raw_metadata"].pop()
    elif damage == "changed_metadata":
        Path(result["raw_metadata"][0]["binding"]["path"]).write_text("{}")
    elif damage == "missing_worker_log":
        result["worker_log"] = None
    elif damage == "end_dependencies":
        result["end_dependencies"]["mutmut"] = "unreviewed-runtime"
    elif damage == "missing_test_data":
        result["tested_data_inputs"].pop()
    elif damage in {"changed_test_data", "rebound_test_data"}:
        entry = result["tested_data_inputs"][-1]
        data = Path(entry["binding"]["path"])
        data.write_bytes(data.read_bytes() + b"\nchanged\n")
        if damage == "rebound_test_data":
            entry["binding"] = _binding(data)
    if damage:
        with pytest.raises(ValueError):
            evidence.decision("V03", result)
    else:
        assert evidence.decision("V03", result) == "INCONCLUSIVE"
        row = next(row for row in result["mutants"] if row["id"] == mid)
        assert row == {"id": mid, "module": "hponas.space", "status": "suspicious",
                       "raw_exit_code": code, "tool_status": tool_status}
        assert analyze_results(result)["timeout"] == 0


@pytest.mark.parametrize("code", [3, 255])
def test_calibration_cannot_accept_abnormal_exit_as_known_kill(tmp_path, code):
    from pathlib import Path
    from validation.v03_mutation_testing import verify_calibration
    from validation.v03_raw_outcomes import TOOL_STATUS

    freeze = {"source_digest": "frozen"}
    ref = calibration_fixture(tmp_path, freeze)
    record = json.loads(Path(ref["path"]).read_text())
    mid = next(mid for mid, row in CALIBRATION_CONTROLS.items() if row["status"] == "killed")
    entry = next(row for row in record["raw_metadata"] if row["module"] == mid.rsplit(".", 1)[0])
    path = Path(entry["binding"]["path"])
    raw = json.loads(path.read_text())
    raw["exit_code_by_key"][mid] = code
    path.write_text(json.dumps(raw))
    entry["binding"] = _binding(path)
    listing = Path(record["raw_listing"]["path"])
    listing.write_text(listing.read_text().replace(mid + ": killed", mid + ": " + TOOL_STATUS[code]))
    record["raw_listing"] = _binding(listing)
    assert verify_calibration(record, freeze) is False


@pytest.mark.parametrize("failure", ["listing_exit", "malformed_listing", "inconsistent_metadata"])
def test_failed_generation_retains_unresolved_evidence_without_launching_full_run(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    from validation import v03_mutation_testing as mutation

    (tmp_path / "validation").mkdir()
    for name in ("pyproject.toml", "requirements.txt", "validation/protocols.json"):
        (tmp_path / name).write_text("inert fixture")
    monkeypatch.setattr(mutation, "prepare_mutation_workspace", lambda: tmp_path)
    monkeypatch.setattr(mutation, "mutation_freeze", lambda _: {"kind": "inert_fixture"})
    monkeypatch.setattr(mutation, "calibrate_isolation", lambda *a: ({"passed": False}, {}))
    monkeypatch.setattr(mutation, "_run_with_deadline", lambda *a, **kw: pytest.fail("Bypassed calibration"))
    stdout = "" if failure == "listing_exit" else "malformed" if failure == "malformed_listing" else "hponas.space.x_function__mutmut_1: killed\n"
    monkeypatch.setattr(mutation.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        stdout=stdout, stderr="retained diagnostic", returncode=2 if failure == "listing_exit" else 0))
    result = mutation.run_mutmut()
    assert result["execution_completed"] is False
    assert result["inventory_error"]
    assert result["mutants"] == []
    assert result["killed"] == 0
    assert (tmp_path / "individual-results.txt").read_text() == stdout
    assert (tmp_path / "listing-stderr.txt").read_text() == "retained diagnostic"
    assert mutation.inventory_verdict(result, mutation.analyze_results(result)) == "INCONCLUSIVE"


@pytest.mark.parametrize("damage", [None, "version", "markdown", "rules", "timeout_code", "kill_code", "threshold", "ownership", "workers", "cpu_slots", "wall", "calibration_wall", "missing_admission", "retry_admission", "missing_prerequisite", "tool_manifest"])
def test_prospective_launch_refuses_stale_or_weakened_phase_register(tmp_path, damage):
    from validation.v03_mutation_testing import verify_phase_register

    (tmp_path / "validation/protocols").mkdir(parents=True)
    register = json.loads((ROOT / "validation/protocols.json").read_text())
    entry = register["entries"]["V03"]
    markdown = (ROOT / "validation/protocols/v03_protocol.md").read_text()
    if damage == "version":
        entry["version"] = "2.6"
    elif damage == "markdown":
        markdown = markdown.replace("**Version:** 2.30", "**Version:** 2.20")
    elif damage == "tool_manifest":
        entry["tool_source_manifest"].pop()
    elif damage == "missing_admission":
        entry.pop("execution_admission")
    elif damage == "retry_admission":
        entry["execution_admission"]["automatic_retry"] = True
    elif damage == "missing_prerequisite":
        entry["execution_admission"]["prerequisites"].remove("current_complete_calibration")
    elif damage == "rules":
        entry["decision_rule"]["equivalence_rules"].pop()
    elif damage == "timeout_code":
        entry["decision_rule"]["raw_timeout_exit_code"] = 255
    elif damage == "kill_code":
        entry["decision_rule"]["raw_kill_exit_code"] = 3
    elif damage == "threshold":
        entry["decision_rule"]["every_module_minimum"] = .8
    elif damage == "workers":
        entry["execution_resources"]["workers"] = 4
    elif damage == "cpu_slots":
        entry["execution_resources"]["cpu_slots"] = "pid_modulo"
    elif damage == "wall":
        entry["execution_resources"]["wall_seconds"] += 1
    elif damage == "calibration_wall":
        entry["execution_resources"]["calibration_wall_seconds"] += 1
    elif damage == "ownership":
        entry["module_ownership"]["outside_scope"].pop("hponas.postgres")
    (tmp_path / "validation/protocols.json").write_text(json.dumps(register))
    (tmp_path / "validation/protocols/v03_protocol.md").write_text(markdown)
    if damage:
        with pytest.raises(ValueError, match="phase register"):
            verify_phase_register(tmp_path)
    else:
        verify_phase_register(tmp_path)


@pytest.mark.parametrize("damage", [None, "bytes", "missing", "extra", "stale_name", "escape"])
def test_tool_overlay_requires_reviewed_names_and_bytes(tmp_path, damage):
    from validation.v03_mutation_testing import REQUIRED_TOOL_SOURCES, verify_tool_overlay

    fixture = ROOT / "tests/fixtures/v03_tool_overlay_v6"
    overlay = tmp_path / "mutmut-evidence-v6/mutmut"
    for row in REQUIRED_TOOL_SOURCES:
        dest = overlay / row["relative_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((fixture / (row["relative_path"] + ".txt")).read_bytes())
    first = overlay / REQUIRED_TOOL_SOURCES[0]["relative_path"]
    if damage == "bytes":
        first.write_bytes(first.read_bytes() + b"# unreviewed change")
    elif damage == "missing":
        first.unlink()
    elif damage == "extra":
        (overlay / "unexpected.py").write_text("# extra executable input")
    elif damage == "stale_name":
        overlay.parent.rename(tmp_path / "mutmut-evidence-v3")
        overlay = tmp_path / "mutmut-evidence-v3/mutmut"
    elif damage == "escape":
        external = tmp_path / "outside.py"
        external.write_bytes(first.read_bytes())
        first.unlink()
        first.symlink_to(external)
    if damage:
        with pytest.raises(ValueError, match="V03"):
            verify_tool_overlay(overlay)
    else:
        sources, manifest = verify_tool_overlay(overlay)
        assert manifest == REQUIRED_TOOL_SOURCES
        assert len(sources) == len(REQUIRED_TOOL_SOURCES)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "reorder", "relabeled", "changed_bytes"])
def test_retained_tool_inventory_cannot_conceal_damage(tmp_path, damage):
    from validation.v03_mutation_testing import REQUIRED_TOOL_SOURCES, verify_frozen_tool_sources
    fixture = ROOT / "tests/fixtures/v03_tool_overlay_v6"
    sources = [_binding(fixture / (r["relative_path"] + ".txt")) for r in REQUIRED_TOOL_SOURCES]
    manifest = [dict(row) for row in REQUIRED_TOOL_SOURCES]
    if damage == "missing":
        sources.pop()
    elif damage == "duplicate":
        sources[1] = sources[0]
    elif damage == "reorder":
        sources.reverse()
    elif damage == "relabeled":
        manifest[0]["relative_path"] = "other.py"
    else:
        altered = tmp_path / "altered.py"
        altered.write_text("# different tool")
        sources[0] = _binding(altered)
    with pytest.raises(ValueError, match="V03 tool source"):
        verify_frozen_tool_sources(sources, manifest)


@pytest.mark.parametrize("damage", [None, "bytes", "rebound", "missing", "extra", "duplicate"])
def test_non_python_fixture_inventory_refuses_effective_test_input_drift(tmp_path, damage):
    from validation.v03_mutation_testing import same_test_data, test_data_inventory

    source, executed = tmp_path / "source", tmp_path / "executed"
    for root in (source, executed):
        directory = root / "tests/fixtures"
        directory.mkdir(parents=True)
        (directory / "cases.json").write_text('[{"input": 1, "expected": 2}]')
        (directory / "bound.py.txt").write_text("reviewed implementation\n")
    frozen, observed = test_data_inventory(source), test_data_inventory(executed)
    if damage in {"bytes", "rebound"}:
        (executed / "tests/fixtures/cases.json").write_text("[]")
        if damage == "rebound":
            observed = test_data_inventory(executed)
    elif damage == "missing":
        observed.pop()
    elif damage == "extra":
        (executed / "tests/fixtures/extra.json").write_text("[]")
        observed = test_data_inventory(executed)
    elif damage == "duplicate":
        observed.append(observed[0])
    if damage in {"bytes", "duplicate"}:
        with pytest.raises(ValueError):
            same_test_data(frozen, observed)
    else:
        assert same_test_data(frozen, observed) is (damage is None)


def test_calibration_refuses_a_changed_fixture_even_when_python_source_matches(tmp_path):
    from pathlib import Path
    from validation.v03_mutation_testing import verify_calibration

    freeze = {"source_digest": "unchanged-python"}
    reference = calibration_fixture(tmp_path, freeze)
    record = json.loads(Path(reference["path"]).read_text())
    changed = tmp_path / "altered-fixture.json"
    changed.write_text("[]")
    record["test_data_inputs"][-1]["binding"] = _binding(changed)
    assert record["source_digest"] == record["end_source_digest"] == freeze["source_digest"]
    assert verify_calibration(record, freeze) is False


def test_calibration_refuses_runtime_drift_before_full_campaign_spending(tmp_path):
    from pathlib import Path
    from validation.v03_mutation_testing import verify_calibration

    freeze = {"source_digest": "unchanged-python"}
    reference = calibration_fixture(tmp_path, freeze)
    record = json.loads(Path(reference["path"]).read_text())
    record["end_dependencies"]["mutmut"] = "unreviewed-runtime"
    assert verify_calibration(record, freeze) is False
