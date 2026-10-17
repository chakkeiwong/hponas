"""Original V02 input bindings cannot be replaced with self-claimed success."""

import copy
import hashlib
import json

import pytest

from validation.evidence import decision
from validation.v02_contract import (
    SCENARIOS, execute_population, freeze_contract, frozen_population,
    prepare_contract, verify_bound_result, verify_contract,
)


@pytest.fixture(scope="module")
def executed_population():
    contract = prepare_contract()
    return contract, execute_population(contract)


def bind(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_frozen_inputs_really_drive_all_10000_case_execution(executed_population):
    contract, report = executed_population
    assert [case["spec"] for case in report["cases"]] == frozen_population()["cases"]
    assert report["count"] == 10000
    assert contract["certifies_acceptance"] is False
    assert contract["status"] == "candidate"


@pytest.mark.parametrize("field", ["source_digest", "python_version", "dependencies", "input_population",
                                   "protocol_register", "individual_protocol", "scenarios", "case_count",
                                   "raw_outcome_contract"])
def test_changed_source_recipe_or_dependencies_cannot_be_certified_by_a_label(field):
    contract = prepare_contract()
    contract[field] = None
    with pytest.raises(ValueError, match="contract differs"):
        verify_contract(contract)


def test_modifying_returned_scenario_recipe_does_not_change_the_specification():
    contract = prepare_contract()
    contract["scenarios"]["concurrent_replay"]["workers"] = 1
    assert SCENARIOS["concurrent_replay"]["workers"] == 4
    with pytest.raises(ValueError, match="contract differs"):
        verify_contract(contract)


def test_returned_raw_schedule_cannot_mutate_the_frozen_reference():
    contract = prepare_contract()
    contract["raw_outcome_contract"]["concurrency"]["orders"].clear()
    assert prepare_contract()["raw_outcome_contract"]["concurrency"]["orders"] == ["forward", "reverse"]
    with pytest.raises(ValueError, match="contract differs"):
        verify_contract(contract)


def bound_fixture(tmp_path, executed_population):
    contract, population = executed_population
    ref = freeze_contract(tmp_path, contract)
    return {"validation_id": "V02", "schema_version": 1, "evidence_kind": "bound_candidate_event_grammar",
            "run_dir": str(tmp_path), "input_contract": ref,
            "scenarios": [{"id": name, **options} for name, options in SCENARIOS.items()],
            "event_population": population, "certifies_acceptance": False}


def test_bindings_validate_inputs_but_empty_execution_summaries_cannot_pass(tmp_path, executed_population):
    result = bound_fixture(tmp_path, executed_population)
    assert verify_bound_result(result)
    # The input package is not execution evidence. Gate still demands each
    # actual replay log and every scenario's result, ignoring a claimed PASS.
    result["verdict"] = "PASS"
    with pytest.raises((KeyError, ValueError)):
        decision("V02", result)
    with pytest.raises(ValueError, match="replace frozen"):
        freeze_contract(tmp_path, executed_population[0])


@pytest.mark.parametrize("fault", ["duplicate_scenario", "worker_count", "selected_cases", "wrong_output"])
def test_changed_executed_inventory_or_results_are_refused(tmp_path, executed_population, fault):
    result = copy.deepcopy(bound_fixture(tmp_path, executed_population))
    if fault == "duplicate_scenario":
        result["scenarios"].append(result["scenarios"][0])
    elif fault == "worker_count":
        result["scenarios"][3]["workers"] = 1
    elif fault == "selected_cases":
        result["event_population"]["cases"][1] = result["event_population"]["cases"][0]
    else:
        result["event_population"]["cases"][0]["actual"]["invariants"] = False
        assert verify_bound_result(result) is False
        return
    with pytest.raises(ValueError):
        verify_bound_result(result)


def test_changed_contract_bytes_and_external_event_log_cannot_be_trusted(tmp_path, executed_population):
    result = bound_fixture(tmp_path, executed_population)
    path = tmp_path / "v02-contract.json"
    original = path.read_text()
    path.write_text("{}")
    with pytest.raises(ValueError, match="Changed V02"):
        verify_bound_result(result)
    path.write_text(original)
    external = tmp_path.parent / "not-this-campaign.jsonl"
    external.write_text("{}")
    result["scenarios"][0]["event_log"] = bind(external)
    with pytest.raises(ValueError, match="escapes"):
        verify_bound_result(result)


def test_duplicate_fields_cannot_override_contract_identity(tmp_path, executed_population):
    result = bound_fixture(tmp_path, executed_population)
    path = tmp_path / "v02-contract.json"
    raw = path.read_text().rstrip()
    path.write_text(raw[:-1] + ', "status": "certified"}')
    result["input_contract"] = bind(path)
    with pytest.raises(ValueError, match="Duplicate V02"):
        verify_bound_result(result)
    assert json.loads(path.read_text())["status"] == "certified"
