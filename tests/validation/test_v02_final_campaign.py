"""Mandatory V02 assertion inventory and independent objective reconstruction."""

import copy
import json
import sys

import numpy as np
import pytest

from validation.v01_contract import binding
from validation import v02_conformance as suite
from validation.v02_final_campaign import SCHEDULER_CONFIGS, verify_observations, verify_recipes, recompute_result, SCOPE


def test_failure_journal_retains_actual_failed_results_and_retry_events():
    from types import SimpleNamespace
    from hponas.types import Result

    study = SimpleNamespace(results={"trial": Result("trial", float("nan"), 2, 1,
                            {"attempts": 2, "error": "WorkerCrashedError"}, "failed")},
                            _events=[{"kind": "progress", "data": {"scheduler_applied": False}}])
    excinfo = SimpleNamespace(traceback=[SimpleNamespace(frame=SimpleNamespace(f_locals={"self": study}))])
    captured = suite.failure_context(excinfo)
    json.dumps(captured, allow_nan=False)
    assert captured[0]["results"]["trial"]["metadata"]["error"] == "WorkerCrashedError"
    assert captured[0]["results"]["trial"]["objective_value"] == {"nonfinite": "NaN"}
    assert captured[0]["events"] == study._events


def journal(tmp_path):
    plan = {"nodeids": ["one", "two"], "source_digest": "f" * 64}
    records = [{"kind": "start", "pid": 42, "source_digest": plan["source_digest"]},
               {"kind": "collection", "nodeids": plan["nodeids"]}]
    records.extend({"kind": "test_phase", "nodeid": node, "when": phase, "outcome": "passed",
                    "duration": .001, "wasxfail": False, "error": None}
                   for node in plan["nodeids"] for phase in ("setup", "call", "teardown"))
    records.append({"kind": "finish", "exitstatus": 0, "source_digest": plan["source_digest"]})
    log = tmp_path / "pytest.log"
    log.write_text("2 passed\n")
    execution = {"command": [sys.executable, "-m", "pytest", "-q", "-p", "validation.v02_conformance",
                             "--v02-journal", str(tmp_path / "pytest.jsonl"),
                             f"--hypothesis-seed={suite.SEED}", *suite.FILES],
                 "pid": 42, "timeout": False, "returncode": 0, "log": binding(log, tmp_path)}
    return plan, records, execution


def verify(tmp_path, plan, records, execution):
    path = tmp_path / "pytest.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    execution["journal"] = binding(path, tmp_path)
    return suite.verify(tmp_path, execution, plan)


def test_all_fixed_assertions_and_phases_are_required(tmp_path):
    plan, rows, execution = journal(tmp_path)
    assert verify(tmp_path, plan, rows, execution) == "PASS"
    rows.pop(3)  # Drop a call, retain an optimistic zero return code.
    assert verify(tmp_path, plan, rows, execution) == "INCONCLUSIVE"


@pytest.mark.parametrize("fault", ["subset", "duplicate", "source", "command", "pid"])
def test_rehashed_inventory_and_execution_substitution_is_rejected(tmp_path, fault):
    plan, rows, execution = journal(tmp_path)
    if fault == "subset":
        rows[1] = {"kind": "collection", "nodeids": ["one"]}
    elif fault == "duplicate":
        rows.insert(3, copy.deepcopy(rows[2]))
    elif fault == "source":
        rows[-1]["source_digest"] = "a" * 64
    elif fault == "command":
        execution["command"].pop()
    else:
        execution["pid"] += 1
    with pytest.raises(ValueError):
        verify(tmp_path, plan, rows, execution)


@pytest.mark.parametrize("fault", ["skip", "xfail", "timeout", "unfinished"])
def test_incomplete_checks_never_pass(tmp_path, fault):
    plan, rows, execution = journal(tmp_path)
    if fault == "skip":
        rows[3]["outcome"] = "skipped"
    elif fault == "xfail":
        rows[3]["wasxfail"] = True
    elif fault == "timeout":
        execution["timeout"] = True
    else:
        rows.pop()
    assert verify(tmp_path, plan, rows, execution) == "INCONCLUSIVE"
    rows[2]["outcome"] = "failed"
    assert verify(tmp_path, plan, rows, execution) == "FAIL"


def test_raw_objective_reconstruction_rejects_matching_changed_values(tmp_path):
    x = float(np.random.RandomState(43).uniform())
    raw = [{"event_id": 0, "event_type": "suggest", "trial_id": "trial", "data": {"config": {"x": x}, "seed": 43}},
           {"event_id": 1, "event_type": "observe", "trial_id": "trial", "data": {"objective_value": -((x-.4)**2), "cost": 1.}},
           {"event_id": 2, "event_type": "report", "trial_id": "trial", "data": {"value": (x-.4)**2}}]
    path = tmp_path / "events.jsonl"

    def scenario():
        path.write_text("".join(json.dumps(row)+"\n" for row in raw))
        return {"id": "asha_replay", "seed": 43, "n_trials": 1,
                "event_log": {"path": str(path), "sha256": binding(path, tmp_path)["sha256"]}}
    assert verify_observations(tmp_path, scenario())
    raw[1]["data"]["objective_value"] = -999.
    raw[2]["data"]["value"] = 999.
    assert not verify_observations(tmp_path, scenario())


def test_adversarial_summary_cannot_supply_its_own_expected_outcome(tmp_path):
    points = np.random.RandomState(45).uniform(size=20).tolist()
    reference = [[{"x": x} for x in points], [-((x-.4)**2) for x in points]]
    expected = {"arrival_order": reference, "unique_rung_population": 2,
                "single_promotion": [["a", 3]], "stale_report_no_repromotion": []}
    scenario = {"id": "adversarial_events", "cases": [{"name": name, "expected": value, "actual": copy.deepcopy(value)}
                                                     for name, value in expected.items()]}
    assert verify_observations(tmp_path, scenario)
    scenario["cases"][1].update(expected=999, actual=999)
    assert not verify_observations(tmp_path, scenario)


def test_stream_and_cancellation_raw_records_are_reconstructed(tmp_path):
    from validation.v02_state_replay import streamed_replay, cancelled_replay

    for make in (streamed_replay, cancelled_replay):
        scenario = make(tmp_path)
        assert verify_observations(tmp_path, scenario)


@pytest.mark.parametrize("mode", [None, "candidate_event_grammar", "other"])
def test_final_evidence_cannot_downgrade_to_summary_only_crash_checks(mode):
    with pytest.raises(ValueError, match="bound raw execution"):
        recompute_result({"validation_id": "V02", "schema_version": 2, "scope": SCOPE, "evidence_kind": mode})


@pytest.mark.parametrize("field,value", [("eta", 4), ("median_stopping", True), ("r_max", 2),
                                         ("promotion_policy", "legacy_bootstrap"), ("report_grid", [1,2])])
def test_matching_replay_with_wrong_scheduler_is_not_the_frozen_recipe(field, value):
    scenario = {"id": "asha_replay", "scheduler_config": copy.deepcopy(SCHEDULER_CONFIGS["asha_replay"])}
    result = {"evidence_kind": "bound_candidate_event_grammar", "scenarios": [scenario]}
    verify_recipes(result)
    scenario["scheduler_config"][field] = value
    with pytest.raises(ValueError, match="scheduler recipe"):
        verify_recipes(result)
