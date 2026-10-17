"""Atomic Store snapshots and query projections must describe the same run."""

import copy
import json
import sqlite3

import pytest

from hponas.store import Store
from hponas.types import Config, Result, Trial


def snapshot(maximize=False, scheduled=False, finished=False):
    trials = {}
    results = {}
    for tid, value, fidelity, status in (
        ("base", -4.0, 1.0, "completed"),
        ("full-a", 2.0, 4.0, "completed"),
        ("full-b", 7.0, 4.0, "completed"),
        ("failed", -100.0, 4.0, "failed"),
        ("pending", None, 1.0, "pending"),
    ):
        trial = Trial(
            Config({"x": 0.25}, "config-a"),
            tid,
            seed=5,
            fidelity=fidelity,
            value=value,
            cost=2.5,
            parent_trial_id="base" if tid.startswith("full") else None,
            status=status,
        )
        trials[tid] = trial.to_dict()
        if status != "pending":
            result = Result(
                tid,
                value,
                cost=2.5,
                fidelity=fidelity,
                status=status,
                metadata={"artifacts": {"model": f"{tid}.bin", "ignored": 9}},
            )
            results[tid] = result.to_dict()
    return {
        "study_name": "snap",
        "space": {"knobs": []},
        "budget": 9,
        "maximize": maximize,
        "finished": finished,
        "searcher_state": {"seed": 11},
        "trials": trials,
        "results": results,
        "scheduler_state": {"config": {"r_max": 4}} if scheduled else None,
    }


@pytest.mark.parametrize(
    "maximize,scheduled,incumbent",
    [
        (False, False, -4.0),
        (True, False, 7.0),
        (False, True, 2.0),
        (True, True, 7.0),
    ],
)
def test_snapshot_projections_preserve_fields_and_full_fidelity_incumbent(
    tmp_path, maximize, scheduled, incumbent
):
    path = tmp_path / "store.db"
    state = snapshot(maximize, scheduled, finished=True)
    store = Store(path)
    store.save_study_snapshot(state)
    store.close()
    restored = Store(path)
    try:
        assert restored.load_study_snapshot("snap") == state
        study = restored.read_study("snap")
        assert study.study_id == "snap"
        assert json.loads(study.space_json) == state["space"]
        assert (study.seed, study.budget, study.status) == (11, 9, "completed")
        assert study.objective == ("maximize" if maximize else "minimize")
        assert study.incumbent_value == incumbent
        trials = {t.trial_id: t for t in restored.read_trials("snap")}
        assert set(trials) == set(state["trials"])
        for tid, trial in trials.items():
            expected = state["trials"][tid]
            assert trial.config == expected["config"]["values"]
            assert (
                trial.seed,
                trial.fidelity,
                trial.value,
                trial.cost,
                trial.parent_trial_id,
                trial.status,
            ) == (
                expected["seed"],
                expected["fidelity"],
                expected["value"],
                expected["cost"],
                expected["parent_trial_id"],
                expected["status"],
            )
            artifacts = restored.read_artifacts(tid)
            assert [
                (a["artifact_type"], a["path"], a["metadata"]) for a in artifacts
            ] == ([("model", f"{tid}.bin", None)] if tid in state["results"] else [])
    finally:
        restored.close()


def test_later_snapshot_replaces_completed_artifacts_without_duplicates(tmp_path):
    store = Store(tmp_path / "store.db")
    try:
        original = snapshot()
        store.save_study_snapshot(original)
        updated = copy.deepcopy(original)
        updated["finished"] = True
        updated["results"]["full-a"]["metadata"]["artifacts"] = {
            "checkpoint": "latest.pt"
        }
        updated["results"]["full-b"]["metadata"] = {}
        for _ in range(2):
            store.save_study_snapshot(updated)
        assert store.load_study_snapshot("snap") == updated
        assert store.read_study("snap").status == "completed"
        assert [
            (a["artifact_type"], a["path"]) for a in store.read_artifacts("full-a")
        ] == [("checkpoint", "latest.pt")]
        assert store.read_artifacts("full-b") == []
        assert len(store.read_trials("snap")) == len(original["trials"])
    finally:
        store.close()


def test_failed_snapshot_write_rolls_back_ledger_and_all_query_projections(tmp_path):
    path = tmp_path / "store.db"
    store = Store(path)
    original = snapshot()
    store.save_study_snapshot(original)
    study = store.read_study("snap")
    trials = store.read_trials("snap")
    artifacts = store.read_artifacts("base")
    invalid = copy.deepcopy(original)
    invalid["finished"] = True
    invalid["budget"] = 3
    invalid["results"]["base"]["metadata"]["artifacts"] = {"new": "uncommitted"}
    invalid["trials"]["pending"]["config"] = {"values": {"uncommitted": True}}
    invalid["trials"]["pending"]["status"] = (
        None  # NOT NULL fails after earlier rows were written.
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.save_study_snapshot(invalid)
    assert store.load_study_snapshot("snap") == original
    store.close()
    reopened = Store(path)
    try:
        assert reopened.load_study_snapshot("snap") == original
        assert reopened.read_study("snap") == study
        assert reopened.read_trials("snap") == trials
        assert reopened.read_artifacts("base") == artifacts
    finally:
        reopened.close()


def test_empty_snapshot_and_missing_lookup_remain_distinct(tmp_path):
    store = Store(tmp_path / "empty.db")
    try:
        assert store.load_study_snapshot("absent") is None
        state = snapshot()
        state.update(trials={}, results={}, searcher_state={"seed": None})
        store.save_study_snapshot(state)
        study = store.read_study("snap")
        assert study.status == "running"
        assert study.incumbent_value is None
        assert study.seed == 0
        assert store.load_study_snapshot("snap") == state
    finally:
        store.close()


def test_artifact_queries_are_scoped_by_trial_and_type_and_decode_metadata(tmp_path):
    store = Store(tmp_path / "artifacts.db")
    try:
        store.write_artifact("a", "model", "model.pt", {"epoch": 3, "tags": ["best"]})
        store.write_artifact("a", "plot", "curve.svg")
        store.write_artifact("b", "model", "other.pt", {"epoch": 5})
        models = store.read_artifacts("a", "model")
        assert len(models) == 1
        assert models[0]["artifact_type"] == "model"
        assert models[0]["path"] == "model.pt"
        assert models[0]["metadata"] == {"epoch": 3, "tags": ["best"]}
        assert isinstance(models[0]["artifact_id"], int)
        all_a = store.read_artifacts("a")
        assert {(x["artifact_type"], x["path"]) for x in all_a} == {
            ("model", "model.pt"),
            ("plot", "curve.svg"),
        }
        assert (
            next(x for x in all_a if x["artifact_type"] == "plot")["metadata"] is None
        )
        assert store.read_artifacts("absent") == []
        assert store.read_artifacts("a", "absent") == []
    finally:
        store.close()


@pytest.mark.parametrize("seed", [None, 0])
def test_snapshot_accepts_missing_optional_metadata_and_default_trial_seed(
    tmp_path, seed
):
    store = Store(tmp_path / "optional.db")
    try:
        state = snapshot()
        state["trials"]["base"]["seed"] = seed
        state["results"]["base"].pop("metadata")
        store.save_study_snapshot(state)
        assert store.load_study_snapshot("snap") == state
        trial = next(t for t in store.read_trials("snap") if t.trial_id == "base")
        assert trial.seed == 0
        assert store.read_artifacts("base") == []
    finally:
        store.close()


def vector_snapshot(scheduled=True):
    from hponas.multi_objective import ObjectiveSpec

    spec = ObjectiveSpec([
        {"name": "loss", "direction": "min", "lower": 0, "upper": 10},
        {"name": "accuracy", "direction": "max", "lower": 0, "upper": 10},
    ])
    state = snapshot(scheduled=scheduled, finished=True)
    state["trials"], state["results"] = {}, {}
    state["multi_objective"] = {"contract": spec.contract, "identity": spec.identity}
    endpoint = 4.0 if scheduled else 1.0
    for tid, fidelity, loss, accuracy, parent in [
        ("low", endpoint / 2, 0.0, 10.0, None),
        ("a", endpoint, 2.0, 6.0, "low"),
        ("b", endpoint, 4.0, 9.0, "low"),
        ("dominated", endpoint, 5.0, 3.0, "low"),
    ]:
        state["trials"][tid] = Trial(Config({"x": loss / 10}, "config-" + tid), tid,
            seed=13, fidelity=fidelity, value=0.0, cost=2.75,
            parent_trial_id=parent, status="completed").to_dict()
        payload = spec.observation(objectives={"loss": loss, "accuracy": accuracy}, constraints={}, work=3)
        state["results"][tid] = Result(tid, 0.0, fidelity=fidelity, cost=2.75,
            metadata={"multi_objective": payload}).to_dict()
    return state


@pytest.mark.parametrize("scheduled", [False, True])
def test_vector_snapshot_query_uses_endpoint_and_preserves_complete_records(tmp_path, scheduled):
    from hponas.store import Trial as StoredTrial

    state = vector_snapshot(scheduled)
    store = Store(tmp_path / "vector.db")
    try:
        store.save_study_snapshot(state)
        assert store.read_study("snap").incumbent_value is None
        assert store.read_study("snap").objective == "multi_objective"
        assert all(t.value is None for t in store.read_trials("snap"))
        expected = [StoredTrial("a", {"x": .2}, 13, 4.0 if scheduled else 1.0,
                                None, 2.75, "low", "completed"),
                    StoredTrial("b", {"x": .4}, 13, 4.0 if scheduled else 1.0,
                                None, 2.75, "low", "completed")]
        for directions in [None, ["minimize", "maximize"]]:
            assert store.get_pareto_front("snap", ["loss", "accuracy"], directions) == expected
        with pytest.raises(ValueError) as error:
            store.get_best_trials("snap")
        assert str(error.value) == "Multi-objective studies require a Pareto query"
        for names, directions in [(["accuracy", "loss"], None),
                                  (["loss", "accuracy"], ["minimize", "minimize"])]:
            with pytest.raises(ValueError) as error:
                store.get_pareto_front("snap", names, directions)
            assert str(error.value) == "Query must match the frozen objective names and directions"
    finally:
        store.close()


def test_vector_contract_corruption_is_refused_before_commit_and_at_query(tmp_path):
    store = Store(tmp_path / "identity.db")
    state = vector_snapshot()
    try:
        store.save_study_snapshot(state)
        bad = copy.deepcopy(state)
        bad["multi_objective"]["identity"] = "wrong"
        with pytest.raises(ValueError) as error:
            store.save_study_snapshot(bad)
        assert str(error.value) == "Store objective contract identity differs"
        assert store.load_study_snapshot("snap") == state
        with store._conn:
            store._conn.execute("UPDATE study_snapshots SET payload=? WHERE study_id=?",
                                (json.dumps(bad), "snap"))
        with pytest.raises(ValueError) as error:
            store.get_pareto_front("snap", ["loss", "accuracy"])
        assert str(error.value) == "Stored metric identity differs"
    finally:
        store.close()
