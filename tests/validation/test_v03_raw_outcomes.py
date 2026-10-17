"""Counterfeit timeout/kill and raw-population integrity checks."""

import copy
import hashlib
import json

import pytest

from validation.v03_raw_outcomes import TOOL_STATUS, reconstruct_raw_outcomes


def fixture(tmp_path, codes):
    module = "hponas.example"
    rows = {f"{module}.x_run__mutmut_{i+1}": code for i, code in enumerate(codes)}
    path = tmp_path / "example.py.meta"
    path.write_text(json.dumps({"exit_code_by_key": rows}))
    binding = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    listed = [{"id": mid, "module": module, "status": TOOL_STATUS.get(code, "suspicious")}
              for mid, code in rows.items()]
    return listed, [{"module": module, "binding": binding}], [module]


@pytest.mark.parametrize("code,status", [
    (0, "survived"), (1, "killed"), (3, "suspicious"), (255, "suspicious"),
    (-24, "timeout"), (24, "suspicious"), (36, "suspicious"), (152, "suspicious"),
    (None, "not checked"), (2, "check was interrupted by user"), (5, "no tests"),
    (33, "no tests"), (34, "skipped"), (35, "suspicious"),
    (37, "caught by type check"), (-11, "segfault"), (-9, "segfault"), (999, "suspicious"),
])
def test_process_classification_preserves_raw_codes_without_inventing_kills(tmp_path, code, status):
    listed, metadata, modules = fixture(tmp_path, [code])
    row, = reconstruct_raw_outcomes(listed, metadata, modules)
    assert row["status"] == status
    assert row["raw_exit_code"] == code
    assert row["tool_status"] == listed[0]["status"]


@pytest.mark.parametrize("damage", ["bytes", "drop_listing", "extra_listing", "status",
    "module", "drop_metadata", "duplicate_metadata", "duplicate_listing", "extra_module"])
def test_inconsistent_or_changed_population_is_refused(tmp_path, damage):
    listed, metadata, modules = fixture(tmp_path, [1, 255])
    if damage == "bytes":
        (tmp_path / "example.py.meta").write_text('{"exit_code_by_key": {}}')
    elif damage == "drop_listing":
        listed.pop()
    elif damage == "extra_listing":
        listed.append(dict(listed[0], id="hponas.example.x_run__mutmut_999"))
    elif damage == "status":
        listed[1]["status"] = "killed"
    elif damage == "module":
        listed[0]["module"] = "hponas.other"
    elif damage == "drop_metadata":
        metadata.clear()
    elif damage == "duplicate_metadata":
        metadata.append(copy.deepcopy(metadata[0]))
    elif damage == "duplicate_listing":
        listed.append(copy.deepcopy(listed[0]))
    elif damage == "extra_module":
        metadata[0]["module"] = "hponas.other"
    with pytest.raises(ValueError):
        reconstruct_raw_outcomes(listed, metadata, modules)


@pytest.mark.parametrize("raw", [
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_1":1,"hponas.example.x_run__mutmut_1":255}}',
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_1":true}}',
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_1":1.0}}',
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_1":"1"}}',
    '{"exit_code_by_key":{"hponas.other.x_run__mutmut_1":1}}',
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_0":1}}',
    '{"exit_code_by_key":{"hponas.example.x_run__mutmut_orig":1}}',
    '{"exit_code_by_key":[]}',
])
def test_invalid_raw_records_cannot_be_hidden_by_rebinding_hash(tmp_path, raw):
    listed, metadata, modules = fixture(tmp_path, [1])
    path = tmp_path / "example.py.meta"
    path.write_text(raw)
    metadata[0]["binding"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        reconstruct_raw_outcomes(listed, metadata, modules)


def test_runner_exception_cannot_manufacture_pass_through_timeout_exclusion(tmp_path):
    from validation.v03_mutation_testing import analyze_results, inventory_verdict

    listed, metadata, modules = fixture(tmp_path, [1] * 99 + [255])
    raw = {"mutants": reconstruct_raw_outcomes(listed, metadata, modules)}
    analysis = analyze_results(raw, required_modules=modules)
    assert analysis["killed"] == 99
    assert analysis["timeout"] == 0 and analysis["denominator"] == 100
    assert inventory_verdict(raw, analysis) == "INCONCLUSIVE"
