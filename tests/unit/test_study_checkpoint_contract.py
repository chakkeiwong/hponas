"""Recovery preserves committed work and rejects incompatible/corrupt ledgers."""

import copy
import json

import pytest

from hponas import Knob, LocalExecutor, RandomSearcher, SearchSpace, Study
from hponas.events import EventLog
from hponas.schedulers import ASHAConfig, ASHAScheduler, PASHAConfig, PASHAScheduler
from hponas.store import Store


def space():
    return SearchSpace([Knob("x", "continuous", (0.0, 1.0))])


def objective(config, seed, fidelity):
    return config["x"] + seed / 1000 + fidelity / 100


def make_study(**kwargs):
    options = dict(
        searcher=RandomSearcher(space(), seed=17),
        executor=LocalExecutor(),
        objective_fn=objective,
        budget=3,
        maximize=False,
        study_name="recovery",
        max_concurrent=2,
    )
    options.update(kwargs)
    return Study(**options)


def write_state(tmp_path, state):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(state))
    return path


@pytest.fixture
def interrupted_state():
    calls = []

    def interrupt(config, seed, fidelity, trial_id):
        calls.append(trial_id)
        if len(calls) == 2:
            raise KeyboardInterrupt("interrupted before commit")
        return objective(config, seed, fidelity)

    study = make_study(objective_fn=interrupt)
    with pytest.raises(KeyboardInterrupt):
        study.run()
    assert len(study.get_history()) == 1
    return json.loads(json.dumps(study._snapshot()))


@pytest.mark.parametrize("backend", ["file", "store"])
def test_resume_preserves_state_trace_events_and_committed_work(
    tmp_path, interrupted_state, backend
):
    state = interrupted_state
    store = Store(tmp_path / "recovery.db")
    events = EventLog(tmp_path / "events.jsonl")
    events.record_suggest("uncommitted", {"x": 0.8}, 99)
    seen = []

    def record(config, seed, fidelity, trial_id):
        seen.append((trial_id, dict(config), seed, fidelity))
        return objective(config, seed, fidelity)

    target = make_study(
        searcher=RandomSearcher(space(), seed=99),
        budget=8,
        maximize=True,
        max_concurrent=1,
        store=store,
        event_log=events,
        objective_fn=record,
    )
    if backend == "file":
        target.load_checkpoint(write_state(tmp_path, state))
    else:
        store.save_study_snapshot(state)
        target.load_checkpoint()
    assert json.loads(json.dumps(target._snapshot())) == state
    logged = [
        {"kind": e.event_type.value, "trial_id": e.trial_id, "data": e.data}
        for e in events.get_events()
    ]
    assert logged == state["events"]
    result = target.run()
    reference = make_study()
    expected = reference.run()
    # Dispatch context and objective trace must survive changes in constructor inputs.
    assert [x[0] for x in seen] == ["recovery_trial_1", "recovery_trial_2"]
    assert seen == [
        (t.trial_id, t.config.values, t.seed, t.fidelity)
        for t in reference.trials.values()
        if t.trial_id != "recovery_trial_0"
    ]
    assert [
        (r.trial_id, r.objective_value, r.fidelity, r.status) for r in result.history
    ] == [
        (r.trial_id, r.objective_value, r.fidelity, r.status) for r in expected.history
    ]
    assert result.best_config == expected.best_config
    assert result.best_value == expected.best_value
    assert store.read_study("recovery").status == "completed"
    assert len(store.read_trials("recovery")) == 3
    assert json.loads(json.dumps(target._snapshot())) == store.load_study_snapshot(
        "recovery"
    )
    store.close()


def test_completed_checkpoint_restores_finished_state_without_redispatch(tmp_path):
    source = make_study()
    result = source.run()
    state = source._snapshot()
    target = make_study(
        objective_fn=lambda c: pytest.fail("committed work was repeated")
    )
    target.load_checkpoint(write_state(tmp_path, state))
    assert target._snapshot()["finished"] is True
    assert target.run() == result


def test_missing_checkpoint_sources_report_explicit_errors(tmp_path):
    with pytest.raises(ValueError, match="checkpoint path or Store"):
        make_study().load_checkpoint()
    store = Store(tmp_path / "empty.db")
    try:
        with pytest.raises(ValueError, match="No study checkpoint"):
            make_study(store=store).load_checkpoint()
    finally:
        store.close()
    with pytest.raises(FileNotFoundError):
        make_study().load_checkpoint(tmp_path / "absent.json")
    with pytest.raises(ValueError, match="No study checkpoint"):
        make_study().load_checkpoint(write_state(tmp_path, None))


def corrupt(state, case):
    done, pending = "recovery_trial_0", "recovery_trial_1"
    if case == "schema":
        state["schema_version"] = 1
    elif case == "space":
        state["space"] = SearchSpace([Knob("y", "continuous", (0.0, 1.0))]).to_dict()
    elif case == "searcher":
        state["searcher_class"] = "different.Searcher"
    elif case == "scheduler":
        state["scheduler_state"] = {"unexpected": True}
    elif case == "scheduler_class":
        state["scheduler_class"] = "different.Scheduler"
    elif case == "orphan_result":
        state["results"]["ghost"] = {**state["results"][done], "trial_id": "ghost"}
    elif case == "completed_pending":
        state["pending"].append(done)
    elif case == "duplicate_pending":
        state["pending"].append(pending)
    elif case == "missing_pending":
        state["pending"] = []
    elif case == "unknown_pending":
        state["pending"] = ["ghost"]
    elif case == "missing_root":
        state["roots"].pop(pending)
    elif case == "unknown_root":
        state["roots"][pending] = "ghost"
    elif case == "trial_identity":
        state["trials"][pending]["trial_id"] = "ghost"
    elif case == "result_identity":
        state["results"][done]["trial_id"] = "ghost"
    elif case == "config":
        state["trials"][pending]["config"]["values"]["x"] = 2.0
    else:
        raise AssertionError(case)


@pytest.mark.parametrize(
    "case,message",
    [
        ("schema", "checkpoint schema"),
        ("space", "search space"),
        ("searcher", "searcher differs"),
        ("scheduler", "scheduler differs"),
        ("scheduler_class", "scheduler class"),
        ("orphan_result", "Results without"),
        ("completed_pending", "Completed trials"),
        ("duplicate_pending", "pending ledger"),
        ("missing_pending", "pending ledger"),
        ("unknown_pending", "pending ledger"),
        ("missing_root", "trial roots"),
        ("unknown_root", "trial roots"),
        ("trial_identity", "identities"),
        ("result_identity", "identities"),
        ("config", "bounds"),
    ],
)
def test_invalid_checkpoint_is_rejected(tmp_path, interrupted_state, case, message):
    corrupt(interrupted_state, case)
    with pytest.raises(ValueError, match=message):
        make_study().load_checkpoint(write_state(tmp_path, interrupted_state))


def test_rejected_ledger_does_not_replace_live_study(tmp_path, interrupted_state):
    target = make_study(study_name="live", budget=1)
    target.run()
    before = copy.deepcopy(target._snapshot())
    corrupt(interrupted_state, "duplicate_pending")
    with pytest.raises(ValueError):
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert target._snapshot() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("budget", 0),
        ("budget", True),
        ("budget", 2.5),
        ("max_concurrent", 0),
        ("max_concurrent", -1),
        ("max_concurrent", True),
        ("max_concurrent", 1.5),
        ("n_suggested", -1),
        ("n_suggested", True),
        ("n_suggested", 1),
        ("n_suggested", 4),
        ("n_suggested", 2.0),
        ("maximize", "false"),
    ],
)
def test_invalid_recovery_controls_cannot_bypass_constructor(
    tmp_path, interrupted_state, field, value
):
    interrupted_state[field] = value
    message = "suggestion count" if field == "n_suggested" else field
    with pytest.raises(ValueError, match=message):
        make_study().load_checkpoint(write_state(tmp_path, interrupted_state))


@pytest.mark.parametrize("options", [{"max_concurrent": True}, {"maximize": "false"}])
def test_constructor_rejects_ambiguous_controls(options):
    with pytest.raises(ValueError):
        make_study(**options)


def test_optional_checkpoint_fields_recover_a_sequential_ledger(
    tmp_path, interrupted_state
):
    # Exercise the loader's supported fallback for omitted execution fields.
    for key in (
        "searcher_class",
        "max_concurrent",
        "n_suggested",
        "roots",
        "pending",
        "events",
        "finished",
    ):
        interrupted_state.pop(key)
    target = make_study()
    target.load_checkpoint(write_state(tmp_path, interrupted_state))
    restored = target._snapshot()
    assert restored["max_concurrent"] == 1
    assert restored["n_suggested"] == 2
    assert restored["pending"] == ["recovery_trial_1"]
    assert restored["roots"] == {
        "recovery_trial_0": "recovery_trial_0",
        "recovery_trial_1": "recovery_trial_1",
    }
    assert restored["events"] == []
    assert restored["finished"] is False
    assert target.run().n_trials == 3


class DirectionalRandom(RandomSearcher):
    """A supported searcher whose base checkpoint does not own Study direction."""

    def __init__(self, search_space, seed):
        super().__init__(search_space, seed)
        self.maximize = True


def test_study_direction_is_restored_on_searchers_that_do_not_serialize_it(tmp_path):
    source = make_study(searcher=DirectionalRandom(space(), seed=17))
    expected = source.run()
    target = make_study(searcher=DirectionalRandom(space(), seed=99), maximize=True)
    target.load_checkpoint(write_state(tmp_path, source._snapshot()))
    assert target.searcher.maximize is False
    assert (
        target.searcher.get_best(target.searcher.maximize).objective_value
        == expected.best_value
    )


def test_scheduler_resume_preserves_promotions_and_original_policy(tmp_path):
    def scheduler():
        return ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=4, median_stopping=True, promotion_policy="legacy_bootstrap"))

    calls = []

    def interrupt(config, seed, fidelity):
        calls.append(fidelity)
        if fidelity > 1:
            raise KeyboardInterrupt("crash at promotion")
        return objective(config, seed, fidelity)

    source = make_study(scheduler=scheduler(), objective_fn=interrupt)
    with pytest.raises(KeyboardInterrupt):
        source.run()
    state = source._snapshot()
    assert any(t["parent_trial_id"] is not None for t in state["trials"].values())
    target = make_study(scheduler=ASHAScheduler(ASHAConfig(eta=3, r_max=9, promotion_policy="legacy_bootstrap")))
    target.load_checkpoint(write_state(tmp_path, state))
    assert target.scheduler.config == scheduler().config
    assert json.loads(json.dumps(target._snapshot())) == json.loads(json.dumps(state))
    actual = target.run()
    expected = make_study(scheduler=scheduler()).run()
    assert [(r.trial_id, r.fidelity, r.objective_value) for r in actual.history] == [
        (r.trial_id, r.fidelity, r.objective_value) for r in expected.history
    ]
    assert actual.best_value == expected.best_value


def test_scheduler_presence_and_type_must_match(tmp_path, interrupted_state):
    path = write_state(tmp_path, interrupted_state)
    with pytest.raises(ValueError, match="scheduler differs"):
        make_study(scheduler=ASHAScheduler(ASHAConfig())).load_checkpoint(path)
    source = make_study(scheduler=ASHAScheduler(ASHAConfig()))
    path = write_state(tmp_path, source._snapshot())
    with pytest.raises(ValueError, match="scheduler class differs"):
        make_study(scheduler=PASHAScheduler(PASHAConfig())).load_checkpoint(path)
