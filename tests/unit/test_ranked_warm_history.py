"""Known-answer warm-start selection, store isolation and Study recovery."""
from copy import deepcopy
import json
import sqlite3
import time

import pytest

from hponas.executors.local_executor import LocalExecutor
from hponas.searchers.random_searcher import RandomSearcher
from hponas.space import Knob, SearchSpace
from hponas.store import Store, Study as StudyRow, Trial
from hponas.study import Study
from hponas.types import Config, Result
from hponas.warm_history import digest, select, space_signature, target_context
from hponas.warm_start import RankedWarmStartSearcher, WarmStartSearcher, load_seed_configs
from hponas.legacy_searchers import SobolSearcher


def context(space, **overrides):
    values = dict(study_id="target", task_id="held-out", model_family="ridge",
                  task_domain="linear", objective_key="coefficient_risk",
                  direction="minimize", history_cutoff=time.time() + 1)
    values.update(overrides)
    return target_context(space, **values)


def add_history(store, space, sid, values, configs, **overrides):
    options = dict(task_id="past-"+sid, model_family="ridge", task_domain="linear",
                   objective_key="coefficient_risk")
    options.update(overrides)
    store.write_study(StudyRow(sid, space.to_json(), "minimize", 3, 20, status="completed"))
    for i, (value, config) in enumerate(zip(values, configs)):
        store.write_trial(Trial(f"{sid}-{i}", {"x": config}, 1, 1., value, 1., status="completed"), sid)
    return store.freeze_warm_history(sid, **options)


@pytest.fixture
def histories(tmp_path):
    space = SearchSpace([Knob("x", "continuous", (1., 8.))])
    store = Store(tmp_path / "history.db")
    add_history(store, space, "A", [.1, .2, .3, .4], [1., 2., 3., 4.])
    add_history(store, space, "B", [100., 101.], [5., 6.])
    yield store, space, context(space)
    store.close()


def test_exact_rank_order_is_scale_invariant_and_retains_frozen_provenance(histories):
    store, space, target = histories
    selection = select(store.read_warm_histories(), target, space, 6)
    assert [r["config"]["x"] for r in selection["seeds"]] == [1, 5, 2, 3, 6, 4]
    assert [r["quantile"] for r in selection["seeds"]] == [[1, 8], [1, 4], [3, 8], [5, 8], [3, 4], [7, 8]]
    assert len(selection["history_bindings"]) == 2
    histories = store.read_warm_histories()
    for history in histories:
        for trial in history["trials"]:
            trial["value"] = (trial["value"] - 200)**3
        history["binding"] = digest({k: v for k, v in history.items() if k != "binding"})
    transformed = select(histories[::-1], target, space, 6)
    assert transformed["seeds"] == selection["seeds"]
    assert transformed["history_bindings"] != selection["history_bindings"]


@pytest.mark.parametrize("field,value,reason", [
    ("model_family", "neural", "incompatible_model_family"),
    ("task_domain", "credit", "incompatible_task_domain"),
    ("objective_key", "train_loss", "incompatible_objective_key"),
    ("direction", "maximize", "incompatible_direction"),
    ("completed_at", float("inf"), "outside_history_cutoff"),
    ("task_id", "held-out", "held_out"),
    ("study_id", "target", "held_out"),
    ("endpoint_fidelity", 3., "incompatible_endpoint_fidelity"),
])
def test_attractive_sentinel_cannot_bypass_eligibility(histories, field, value, reason):
    store, space, target = histories
    sentinel = deepcopy(store.read_warm_histories()[0])
    sentinel.update(study_id="sentinel", trials=[{"trial_id": "best", "config": {"x": 8.},
                     "status": "completed", "value": -1e100, "fidelity": 1.}])
    sentinel[field] = value
    result = select([sentinel, *store.read_warm_histories()], target, space, 6)
    assert [r["config"]["x"] for r in result["seeds"]] == [1, 5, 2, 3, 6, 4]
    assert {"study_id": sentinel["study_id"], "reason": reason} in result["excluded"]


def test_transforms_conditions_and_category_order_are_part_of_identity():
    from hponas.warm_start import check_space_compatibility
    linear = SearchSpace([Knob("x", "continuous", (1., 8.))])
    log = SearchSpace([Knob("x", "continuous", (1., 8.), transform="log")])
    assert not check_space_compatibility(log.to_json(), linear)
    a = SearchSpace([Knob("mode", "categorical", ["a", "b"]),
                     Knob("x", "continuous", (1., 8.), condition=("mode", "a"))])
    b = SearchSpace([Knob("mode", "categorical", ["a", "b"]),
                     Knob("x", "continuous", (1., 8.), condition=("mode", "b"))])
    assert not check_space_compatibility(a.to_json(), b)
    b.knobs[0].bounds.reverse()
    assert space_signature(a) != space_signature(b)
    assert check_space_compatibility(a.to_json(), a)


def test_history_snapshot_is_immutable_and_invalid_refreeze_is_atomic(histories):
    store, space, target = histories
    retained = store.read_warm_histories()
    store.write_trial(Trial("A-0", {"x": 8.}, 1, 1., -1e200, 1., status="completed"), "A")
    assert store.read_warm_histories() == retained
    with pytest.raises(ValueError, match="immutable"):
        store.freeze_warm_history("A", task_id="new-task", model_family="ridge", task_domain="linear",
                                  objective_key="coefficient_risk")
    assert store.read_warm_histories() == retained
    assert not store._conn.in_transaction


def test_cutoff_uses_observed_freeze_time_and_cannot_backdate(histories):
    store, space, target = histories
    target["history_cutoff"] = min(s["completed_at"] for s in store.read_warm_histories()) - 1
    assert select(store.read_warm_histories(), target, space, 6)["seeds"] == []
    with pytest.raises(TypeError):
        store.freeze_warm_history("A", task_id="A", model_family="ridge", task_domain="linear",
                                  objective_key="risk", completed_at=0)


def test_unfinished_study_and_unfinished_trial_are_refused_atomically(histories):
    store, space, _ = histories
    store.write_study(StudyRow("unfinished", space.to_json(), "minimize", 1, 4))
    kwargs = dict(task_id="unfinished", model_family="ridge", task_domain="linear", objective_key="risk")
    with pytest.raises(ValueError, match="completed stored"):
        store.freeze_warm_history("unfinished", **kwargs)
    store.write_study(StudyRow("unfinished", space.to_json(), "minimize", 1, 4, status="completed"))
    store.write_trial(Trial("pending", {"x": 1.}, 1, 1., None, 0., status="running"), "unfinished")
    with pytest.raises(ValueError, match="unfinished trials"):
        store.freeze_warm_history("unfinished", **kwargs)
    assert len(store.read_warm_histories()) == 2
    assert not store._conn.in_transaction


def test_one_read_cannot_mix_concurrent_history_revisions(histories):
    store, _, _ = histories
    other = sqlite3.connect(store.db_path)
    before = store.read_warm_histories()
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("DELETE FROM warm_history WHERE study_id='B'")
        assert store.read_warm_histories() == before
        other.rollback()
    finally:
        other.close()


def test_corrupt_history_is_an_error_not_a_silent_cold_start(histories):
    store, space, target = histories
    with store._conn:
        row = store.read_warm_histories()[0]
        row["trials"][0]["value"] = -1e100
        store._conn.execute("UPDATE warm_history SET payload=? WHERE study_id='A'", (json.dumps(row),))
    with pytest.raises(ValueError, match="binding"):
        RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=5), store, context=target)


def test_low_fidelity_attractive_result_does_not_enter_rank(histories):
    store, space, target = histories
    data = store.read_warm_histories()
    data[0]["trials"].append({"trial_id": "low", "config": {"x": 8}, "value": -1e100,
                              "fidelity": .5, "status": "completed"})
    assert [r["config"]["x"] for r in select(data, target, space, 6)["seeds"]] == [1, 5, 2, 3, 6, 4]


def test_missing_eligibility_cold_starts_explicitly(histories):
    store, space, _ = histories
    assert load_seed_configs(store, "A", space) == []
    base = SobolSearcher(space, seed=7)
    warm = WarmStartSearcher.from_store(base, store, space)
    assert warm.fallback_reason == "missing_target_context"
    assert warm.propose(3) == SobolSearcher(space, seed=7).propose(3)


def test_modern_wrapper_only_observes_current_target_measurements(histories):
    store, space, target = histories
    warm = RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=7), store, context=target, n=2)
    assert warm.history == warm._base.history == []
    outcome = Study(warm, LocalExecutor(), lambda config: (config["x"]-3)**2,
                    budget=2, maximize=False, study_name="target", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert [warm.trials[r.trial_id].values["x"] for r in outcome.history] == [1, 5]
    assert [r.objective_value for r in warm.history] == [4, 4]
    assert all(not r.trial_id.startswith(("A-", "B-")) for r in warm.history)
    assert warm.get_state()["base"]["history"] == [r.to_dict() for r in warm.history]


def test_study_cannot_change_target_identity_or_objective(histories):
    store, space, target = histories
    for kwargs in [{"study_name": "other", "maximize": False}, {"study_name": "target", "maximize": True}]:
        warm = RankedWarmStartSearcher.from_store(RandomSearcher(space), store, context=target)
        with pytest.raises(ValueError, match="differs"):
            Study(warm, LocalExecutor(), lambda config: 1, budget=2, **kwargs, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
        assert warm.n_seeds_used == 0


def test_prior_results_in_base_cannot_be_mistaken_for_target_observations(histories):
    store, space, target = histories
    base = RandomSearcher(space)
    base.observe(Result("past-study-result", -1e100))
    with pytest.raises(ValueError, match="fresh target"):
        RankedWarmStartSearcher.from_store(base, store, context=target)


def test_failed_nonfinite_current_outcomes_remain_recoverable(histories):
    store, space, target = histories
    warm = RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=7), store, context=target)
    warm.trials["current"] = Config({"x": 1.})
    warm.observe(Result("current", float("nan"), status="nan"))
    state = json.loads(json.dumps(warm.get_state()))
    resumed = RankedWarmStartSearcher(RandomSearcher(space, seed=11), warm.selection)
    resumed.set_state(state)
    assert resumed.history[0].status == "nan"
    assert not resumed.history[0].is_valid()
    assert resumed.get_state()["binding"] == state["binding"]


def test_json_resume_covers_every_seed_boundary_and_cold_stream(histories):
    store, space, target = histories
    selection = select(store.read_warm_histories(), target, space, 6)
    expected = RankedWarmStartSearcher(RandomSearcher(space, seed=7), selection)
    stream = [expected.suggest().values for _ in range(12)]
    for boundary in range(13):
        source = RankedWarmStartSearcher(RandomSearcher(space, seed=7), selection)
        assert [source.suggest().values for _ in range(boundary)] == stream[:boundary]
        state = json.loads(json.dumps(source.get_state()))
        resumed = RankedWarmStartSearcher(RandomSearcher(space, seed=99), selection)
        resumed.set_state(state)
        assert [resumed.suggest().values for _ in range(12-boundary)] == stream[boundary:]


def test_study_crash_recovery_reuses_pending_seeds_without_repeating_completed_work(histories, tmp_path):
    store, space, target = histories
    selection = select(store.read_warm_histories(), target, space, 6)
    seen = []

    def interrupted(config, trial_id):
        seen.append(trial_id)
        if len(seen) == 3:
            raise KeyboardInterrupt("Simulated crash between warm proposals")
        return (config["x"] - 3)**2

    source = Study(RankedWarmStartSearcher(RandomSearcher(space, seed=7), selection),
                   LocalExecutor(), interrupted, budget=8, study_name="target", maximize=False,
                   checkpoint_dir=tmp_path, store=store, max_concurrent=2, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    with pytest.raises(KeyboardInterrupt):
        source.run()
    completed = set(source.results)
    dispatched = []

    def objective(config, trial_id):
        dispatched.append(trial_id)
        return (config["x"] - 3)**2

    resumed = Study(RankedWarmStartSearcher(RandomSearcher(space, seed=99), selection),
                    LocalExecutor(), objective, budget=8, study_name="target", maximize=False, store=store, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    resumed.load_checkpoint()
    result = resumed.run()
    assert not completed.intersection(dispatched)
    reference = Study(RankedWarmStartSearcher(RandomSearcher(space, seed=7), selection),
                      LocalExecutor(), lambda c: (c["x"] - 3)**2, budget=8, study_name="target",
                      maximize=False, max_concurrent=2, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    expected = reference.run()
    assert [resumed.trials[r.trial_id].config.values for r in result.history] == [
        reference.trials[r.trial_id].config.values for r in expected.history]
    assert [r.objective_value for r in result.history] == [r.objective_value for r in expected.history]
    assert resumed.searcher.n_seeds_used == 6


@pytest.mark.parametrize("field,value", [("study_name", "other"), ("maximize", True)])
def test_study_checkpoint_cannot_change_warm_target_after_partial_restore(histories, tmp_path, field, value):
    store, space, target = histories
    warm = RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=7), store, context=target)
    study = Study(warm, LocalExecutor(), lambda c: 1., budget=2, study_name="target", maximize=False, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    before = study._snapshot()
    bad = deepcopy(before)
    bad[field] = value
    path = tmp_path / "incompatible.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="differs"):
        study.load_checkpoint(path)
    assert study._snapshot() == before


def test_returned_checkpoint_and_selection_cannot_alias_live_state(histories):
    store, space, target = histories
    warm = RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=7), store, context=target)
    warm.trials["current"] = Config({"x": 1.})
    warm.observe(Result("current", 1., metadata={"trace": [1]}))
    before = warm.get_state()
    returned = warm.get_state()
    returned["history"][0]["metadata"]["trace"].append(99)
    returned["selection"]["seeds"][0]["config"]["x"] = 8.
    assert warm.get_state() == before


@pytest.mark.parametrize("damage", [
    lambda s: s["queue"].update(cursor=-1),
    lambda s: s["queue"].update(cursor=True),
    lambda s: s["base"].update(rng_state=["invalid", [], 0, 0, 0.]),
    lambda s: s["selection"]["context"].update(task_id="wrong"),
    lambda s: s["history"].append(Result("forged", 99.).to_dict()),
])
def test_semantic_refusal_does_not_mutate_live_wrapper_or_base(histories, damage):
    store, space, target = histories
    warm = RankedWarmStartSearcher.from_store(RandomSearcher(space, seed=7), store, context=target)
    warm.suggest()
    before = warm.get_state()
    bad = deepcopy(before)
    damage(bad)
    bad["binding"] = digest({k: v for k, v in bad.items() if k != "binding"})
    with pytest.raises((ValueError, KeyError, TypeError)):
        warm.set_state(bad)
    assert warm.get_state() == before


def test_legacy_wrapper_refusal_is_atomic_and_manual_configs_are_deduplicated(histories):
    _, space, _ = histories
    warm = WarmStartSearcher(SobolSearcher(space, seed=4), [{"x": 1}, {"x": 1.}, {"x": 2.}])
    assert warm.n_seeds_remaining == 2
    state = warm.state_dict()
    bad = deepcopy(state)
    bad["n_seeds_used"] = 100
    bad["binding"] = digest({k: v for k, v in bad.items() if k != "binding"})
    with pytest.raises(ValueError, match="cursor/queue"):
        warm.load_state_dict(bad)
    assert warm.state_dict() == state
    bad = deepcopy(state)
    bad["base"] = {}
    bad["binding"] = digest({k: v for k, v in bad.items() if k != "binding"})
    with pytest.raises((ValueError, KeyError)):
        warm.load_state_dict(bad)
    assert warm.state_dict() == state


def test_legacy_adapter_preserves_bound_history_context(histories):
    store, space, target = histories
    warm = WarmStartSearcher.from_store(SobolSearcher(space, seed=7), store, space, context=target)
    for name, maximize in [("wrong", False), ("target", True)]:
        with pytest.raises(ValueError, match="differs"):
            Study(warm, LocalExecutor(), lambda c: 1., budget=2, study_name=name, maximize=maximize, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    outcome = Study(warm, LocalExecutor(), lambda c: (c["x"]-3)**2,
                    budget=2, study_name="target", maximize=False, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert [r.objective_value for r in outcome.history] == [4., 4.]


@pytest.mark.parametrize("endpoint", [0., -1., float("nan"), float("inf"), True])
def test_store_refuses_invalid_history_endpoint_before_writing(histories, endpoint):
    store, _, _ = histories
    before = store.read_warm_histories()
    with pytest.raises(ValueError) as error:
        store.freeze_warm_history("new", task_id="past-new", model_family="ridge",
            task_domain="linear", objective_key="risk", endpoint_fidelity=endpoint)
    assert str(error.value) == "A positive finite endpoint fidelity is required"
    assert store.read_warm_histories() == before


def test_history_freeze_refuses_caller_transaction_without_committing_it(histories):
    store, _, _ = histories
    before = store.read_warm_histories()
    store._conn.execute("BEGIN")
    try:
        with pytest.raises(ValueError) as error:
            store.freeze_warm_history("A", task_id="past-A", model_family="ridge",
                task_domain="linear", objective_key="coefficient_risk")
        assert str(error.value) == "History freeze requires its own transaction"
        assert store._conn.in_transaction
    finally:
        store._conn.rollback()
    assert store.read_warm_histories() == before


@pytest.mark.parametrize("status", ["pending", "running", "paused"])
def test_every_unfinished_history_status_is_refused(histories, status):
    store, space, _ = histories
    store.write_study(StudyRow("new", space.to_json(), "minimize", 1, 4, status="completed"))
    store.write_trial(Trial("unfinished", {"x": 1.}, 1, 1., 2., 1., status=status), "new")
    with pytest.raises(ValueError) as error:
        store.freeze_warm_history("new", task_id="past-new", model_family="ridge",
            task_domain="linear", objective_key="risk")
    assert str(error.value) == "Completed history cannot contain unfinished trials"
    assert len(store.read_warm_histories()) == 2


def test_history_freeze_keeps_invalid_outcomes_with_explicit_nonfinite_disposition(histories):
    store, space, _ = histories
    store.write_study(StudyRow("new", space.to_json(), "minimize", 1, 4, status="completed"))
    for tid, value, cost, status in [("infinite", float("inf"), float("inf"), "completed"),
                                    ("missing", None, 2., "completed"),
                                    ("failed", float("inf"), -float("inf"), "failed")]:
        store.write_trial(Trial(tid, {"x": 1.}, 1, 1., value, cost, status=status), "new")
    record = store.freeze_warm_history("new", task_id="past-new", model_family="ridge",
        task_domain="linear", objective_key="risk")
    assert [(t["trial_id"], t["status"], t["value"], t["cost"]) for t in record["trials"]] == [
        ("failed", "failed", None, None), ("infinite", "nonfinite", None, None),
        ("missing", "nonfinite", None, 2.)]


@pytest.mark.parametrize("damage", ["binding", "schema", "study_id"])
def test_history_reader_refuses_each_integrity_failure_independently(histories, damage):
    store, _, _ = histories
    row = store.read_warm_histories()[0]
    row[damage] = "wrong"
    if damage != "binding":
        row["binding"] = digest({k: v for k, v in row.items() if k != "binding"})
    with store._conn:
        store._conn.execute("UPDATE warm_history SET payload=? WHERE study_id='A'", (json.dumps(row),))
    with pytest.raises(ValueError) as error:
        store.read_warm_histories()
    assert str(error.value) == "Retained warm history binding differs"
    if damage == "binding":
        with pytest.raises(ValueError) as error:
            store.freeze_warm_history("A", task_id="past-A", model_family="ridge",
                task_domain="linear", objective_key="coefficient_risk")
        assert str(error.value) == "Retained warm history binding differs"
