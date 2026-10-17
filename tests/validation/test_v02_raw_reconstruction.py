"""Real process/thread fixtures and adversarial independently reconstructed data."""

import copy
import hashlib
import json
import shutil

import pytest

from validation.evidence import decision
from validation.v02_fault_execution import execute_crash, execute_concurrency
from validation.v02_raw_reconstruction import verify_crash, verify_concurrency


@pytest.fixture(scope="module")
def executed(tmp_path_factory):
    root = tmp_path_factory.mktemp("v02-independent-raw")
    crash = execute_crash(root)
    concurrent = execute_concurrency(root, executor_kind="local_threads")
    return root, crash, concurrent


@pytest.fixture
def copied(tmp_path, executed):
    root, crash, concurrent = executed
    shutil.copytree(root, tmp_path, dirs_exist_ok=True)
    scenario = copy.deepcopy(concurrent)
    scenario["event_log"]["path"] = str(tmp_path / scenario["raw_evidence"]["runs"]["forward"]["event_log"]["path"])
    return tmp_path, copy.deepcopy(crash), scenario


def refs(value):
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            yield value
        else:
            for nested in value.values():
                yield from refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from refs(nested)


def mutate_everywhere(root, scenario, transform):
    """Corrupt all copies consistently, so redundant-data comparisons still pass."""
    def visit(value):
        if isinstance(value, dict):
            return transform({k: visit(v) for k, v in value.items()})
        if isinstance(value, list):
            return [visit(v) for v in value]
        return value

    paths = {(root / ref["path"]).resolve() for ref in refs(scenario["raw_evidence"])}
    for path in paths:
        if path.suffix == ".jsonl":
            raw = [visit(json.loads(line)) for line in path.read_text().splitlines()]
            path.write_text("".join(json.dumps(row) + "\n" for row in raw))
        else:
            path.write_text(json.dumps(visit(json.loads(path.read_text()))))
    for ref in refs(scenario):
        ref["sha256"] = hashlib.sha256((root / ref["path"]).read_bytes()).hexdigest()


def test_actual_exit_resume_and_opposite_thread_arrivals_reconstruct(executed):
    root, crash, concurrent = executed
    before = verify_crash(root, crash)
    assert before["committed_at_interruption"] == 25
    assert before["pending_at_interruption"] == 1
    assert before["completed_after_resume"] == 50 and before["cost"] == 50
    assert before["reexecuted_committed_trials"] == 0
    after = verify_concurrency(root, concurrent, executor_kind="local_threads")
    for order, stats in after["orders"].items():
        assert stats["four_way_overlap_batches"] == 5
        assert stats["completion_order"][:4] == ([0, 1, 2, 3] if order == "forward" else [3, 2, 1, 0])
    assert after["certifies_acceptance"] is False


def test_oracle_does_not_call_study_replay_searcher_or_producer_objective(executed, monkeypatch):
    import hponas
    import hponas.replay
    import validation.v02_fault_execution as producer

    def forbidden(*args, **kwargs):
        pytest.fail("Independent reconstruction called the system being verified")

    monkeypatch.setattr(hponas.Study, "load_checkpoint", forbidden)
    monkeypatch.setattr(hponas.RandomSearcher, "suggest", forbidden)
    monkeypatch.setattr(hponas.replay.ReplayEngine, "verify_determinism", forbidden)
    monkeypatch.setattr(producer, "recorded_objective", forbidden)
    root, crash, concurrent = executed
    assert verify_crash(root, crash)["reconstructed"]
    assert verify_concurrency(root, concurrent, executor_kind="local_threads")["reconstructed"]


def test_resource_or_human_approval_and_equal_summary_pairs_do_not_establish_outcomes(copied):
    root, crash, _ = copied
    crash.update(verdict="PASS", approved=True, certifier="PI")
    crash["cases"] = [{"expected": "invented", "actual": "invented"}]
    assert verify_crash(root, crash)["reconstructed"]
    del crash["raw_evidence"]
    with pytest.raises(ValueError, match="Raw crash evidence required"):
        verify_crash(root, crash)


def test_polynomial_oracle_rejects_consistently_fabricated_outcomes(copied):
    root, crash, _ = copied

    def wrong(row):
        if row.get("status") == "completed" and "objective_value" in row:
            row["objective_value"] = -123.
        if row.get("status") == "completed" and "config" in row:
            row["value"] = -123.
        if "finish_ns" in row:
            row["value"] = -123.
        return row

    mutate_everywhere(root, crash, wrong)
    crash["cases"] = [{"expected": -123., "actual": -123.}]
    with pytest.raises(ValueError, match="differs"):
        verify_crash(root, crash)


@pytest.mark.parametrize("fault", ["rng", "pending", "exit", "event_order", "committed_change", "duplicate_record",
                                  "missing_record", "changed_hash", "wrong_seed", "outside", "undeclared_record",
                                  "missing_fidelity", "wrong_fidelity"])
def test_corrupt_crash_evidence_cannot_hide_behind_pass_summary(copied, fault):
    root, crash, _ = copied
    raw = crash["raw_evidence"]
    crash["passed"] = True
    if fault in {"duplicate_record", "missing_record", "changed_hash", "outside", "undeclared_record"}:
        rows = raw["after"]["journal"]
        if fault == "duplicate_record":
            rows[-1] = copy.deepcopy(rows[0])
        elif fault == "missing_record":
            rows.pop()
        elif fault == "changed_hash":
            (root / rows[0]["path"]).write_text("{}")
        elif fault == "outside":
            rows[0]["path"] = "../outside.json"
        else:
            (root / rows[0]["path"]).with_name("999.start.json").write_text("{}")
    else:
        def corrupt(row):
            if fault == "rng" and "rng_state" in row:
                row["rng_state"][2] = 0
            if fault == "pending" and "pending" in row and row["pending"]:
                row["pending"] = []
            if fault == "exit" and "returncode" in row:
                row["returncode"] = 0
            if fault == "event_order" and "events" in row:
                row["events"] = row["events"][::-1]
            if fault == "committed_change" and "results" in row and row.get("finished"):
                row["results"]["crash_trial_0"]["objective_value"] = 10.
            if fault == "wrong_seed" and "trial_id" in row and row.get("stage"):
                row["seed"] += 1
            if row.get("kind", row.get("event_type")) == "suggest":
                if fault == "missing_fidelity":
                    row["data"].pop("fidelity", None)
                elif fault == "wrong_fidelity":
                    row["data"]["fidelity"] = 2.0
            return row

        mutate_everywhere(root, crash, corrupt)
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_crash(root, crash)


@pytest.mark.parametrize("fault", ["serial", "one_worker", "wrong_order", "clock_origin", "missing_direction"])
def test_concurrency_requires_real_contexts_overlap_and_both_arrival_orders(copied, fault):
    root, _, concurrent = copied
    if fault == "missing_direction":
        del concurrent["raw_evidence"]["runs"]["reverse"]
    else:
        def corrupt(row):
            if row.get("stage") not in {"forward", "reverse"}:
                return row
            index = int(row["trial_id"].rsplit("_", 1)[1])
            if fault == "serial":
                row["start_ns"] = index * 100 + 1
                if "finish_ns" in row:
                    row["finish_ns"] = index * 100 + 50
            elif fault == "one_worker":
                row["pid"], row["thread"] = 42, 42
            elif fault == "wrong_order":
                row["start_ns"] = 1
                if "finish_ns" in row:
                    row["finish_ns"] = 100 + index
            elif index == 1:
                row["boot_id"] = "different-clock-origin"
            return row

        mutate_everywhere(root, concurrent, corrupt)
    with pytest.raises(ValueError):
        verify_concurrency(root, concurrent, executor_kind="local_threads")


def test_threads_cannot_be_relabeled_as_four_ray_processes(copied):
    root, _, concurrent = copied
    with pytest.raises(ValueError, match="plan/executor"):
        verify_concurrency(root, concurrent)
    mutate_everywhere(root, concurrent, lambda row: {**row, "executor": "ray"} if "executor" in row else row)
    with pytest.raises(ValueError, match="four worker processes"):
        verify_concurrency(root, concurrent)


def test_gate_demands_raw_crash_evidence_before_using_claimed_summaries(monkeypatch, tmp_path):
    from validation import v02_contract

    # Isolate dispatch from the already tested input-population binding.
    monkeypatch.setattr(v02_contract, "verify_bound_result", lambda result: True)
    result = {"validation_id": "V02", "schema_version": 1, "evidence_kind": "bound_candidate_event_grammar",
              "run_dir": str(tmp_path), "verdict": "PASS", "passed": True,
              "scenarios": [{"id": name, **options, "cases": [{"expected": True, "actual": True}]}
                            for name, options in v02_contract.SCENARIOS.items()]}
    with pytest.raises(ValueError, match="Raw crash evidence required"):
        decision("V02", result)


def test_reexecution_refuses_to_replace_actual_fault_evidence(executed):
    root, _, _ = executed
    with pytest.raises(FileExistsError):
        execute_crash(root)
    with pytest.raises(FileExistsError):
        execute_concurrency(root, executor_kind="local_threads")
