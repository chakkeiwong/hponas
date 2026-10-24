"""Recovery preserves committed work and rejects incompatible/corrupt ledgers."""

import copy
import json
import re

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
    return Study(**options, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')


def write_state(tmp_path, state):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(state))
    return path


class SnapshotValidatingScheduler(ASHAScheduler):
    def validate_study_snapshot(self, state):
        if state["study_name"] != "recovery":
            raise ValueError("Scheduler snapshot belongs to another study")
        self.validated_name = state["study_name"]


class SchedulerAwareRandom(RandomSearcher):
    def validate_study_controls(self, max_concurrent, scheduler):
        if scheduler is None:
            raise ValueError("This searcher requires its scheduler")
        self.validated_controls = (max_concurrent, scheduler.config.r_max)


def test_checkpoint_revalidates_restored_scheduler_and_searcher_controls(tmp_path):
    def build(r_max, concurrency):
        return make_study(searcher=SchedulerAwareRandom(space(), seed=17),
                          scheduler=SnapshotValidatingScheduler(ASHAConfig(r_min=1, r_max=r_max)),
                          max_concurrent=concurrency)

    source = build(4, 2)
    state = source._snapshot()
    target = build(4, 1)
    target.load_checkpoint(write_state(tmp_path, state))
    assert target.searcher.validated_controls == (2, 4)
    assert target.scheduler.validated_name == "recovery"
    before = copy.deepcopy(target._snapshot())
    state["study_name"] = "wrong"
    with pytest.raises(ValueError, match="^Scheduler snapshot belongs to another study$"):
        target.load_checkpoint(write_state(tmp_path, state))
    assert target._snapshot() == before


class SlottedDirectionRandom(RandomSearcher):
    """A searcher extension may expose direction through a property/slot."""
    __slots__ = ("direction",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.direction = True

    @property
    def maximize(self):
        return self.direction

    @maximize.setter
    def maximize(self, value):
        self.direction = value


def test_checkpoint_direction_reaches_a_searcher_property_outside_its_dictionary(tmp_path):
    source = make_study(searcher=SlottedDirectionRandom(space(), seed=17), maximize=False)
    target = make_study(searcher=SlottedDirectionRandom(space(), seed=99), maximize=True)
    target.load_checkpoint(write_state(tmp_path, source._snapshot()))
    assert target.maximize is False and target.searcher.maximize is False


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
    with pytest.raises(ValueError, match="^A checkpoint path or Store is required$"):
        make_study().load_checkpoint()
    store = Store(tmp_path / "empty.db")
    try:
        with pytest.raises(ValueError, match="^No study checkpoint found$"):
            make_study(store=store).load_checkpoint()
    finally:
        store.close()
    with pytest.raises(FileNotFoundError):
        make_study().load_checkpoint(tmp_path / "absent.json")
    with pytest.raises(ValueError, match="^No study checkpoint found$"):
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
        ("schema", "Unsupported checkpoint schema; migrate the legacy checkpoint explicitly"),
        ("space", "Checkpoint search space differs"),
        ("searcher", "Checkpoint searcher differs"),
        ("scheduler", "Checkpoint scheduler differs"),
        ("scheduler_class", "Checkpoint scheduler class differs"),
        ("orphan_result", "Results without trial configurations"),
        ("completed_pending", "Completed trials marked pending"),
        ("duplicate_pending", "Checkpoint pending ledger is inconsistent"),
        ("missing_pending", "Checkpoint pending ledger is inconsistent"),
        ("unknown_pending", "Checkpoint pending ledger is inconsistent"),
        ("missing_root", "Checkpoint trial roots are inconsistent"),
        ("unknown_root", "Checkpoint trial roots are inconsistent"),
        ("trial_identity", "Checkpoint trial identities differ"),
        ("result_identity", "Checkpoint trial identities differ"),
        ("config", "x: 2.0 out of bounds [0.0, 1.0]"),
    ],
)
def test_invalid_checkpoint_is_rejected(tmp_path, interrupted_state, case, message):
    corrupt(interrupted_state, case)
    with pytest.raises(ValueError, match="^" + re.escape(message) + "$"):
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
    message = ("Checkpoint suggestion count is inconsistent" if field == "n_suggested"
               else "Checkpoint maximize must be boolean" if field == "maximize"
               else f"Checkpoint {field} must be a positive integer")
    with pytest.raises(ValueError, match="^" + re.escape(message) + "$"):
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
    with pytest.raises(ValueError, match="^Checkpoint scheduler differs$"):
        make_study(scheduler=ASHAScheduler(ASHAConfig())).load_checkpoint(path)
    source = make_study(scheduler=ASHAScheduler(ASHAConfig()))
    path = write_state(tmp_path, source._snapshot())
    with pytest.raises(ValueError, match="^Checkpoint scheduler class differs$"):
        make_study(scheduler=PASHAScheduler(PASHAConfig())).load_checkpoint(path)


@pytest.mark.parametrize("field", ["live_elapsed", "abandoned_elapsed", "live_cost", "abandoned_cost"])
@pytest.mark.parametrize("value", [-.1, float("nan"), float("inf"), "invalid", True])
def test_invalid_accounting_entry_preserves_a_live_study(tmp_path, interrupted_state, field, value):
    interrupted_state[field] = {"recovery_trial_1": value}
    target = make_study(study_name="live", budget=1)
    target.run()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as error:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == f"Invalid checkpoint {field} ledger"
    assert target._snapshot() == before


@pytest.mark.parametrize("budget", [0., -.1, float("nan"), float("inf"), True])
def test_invalid_checkpoint_compute_allowance(tmp_path, interrupted_state, budget):
    interrupted_state["compute_budget_seconds"] = budget
    target = make_study()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as error:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == "Invalid checkpoint compute budget"
    assert target._snapshot() == before


def report_cache(trial="recovery_trial_1", step=1., value=2.):
    return {trial: {str(step): {"value": value, "decision": {"action": "continue", "reason": "scheduler"}}}}


@pytest.mark.parametrize('reason', [None, 'Different explicit legacy purpose'])
def test_legacy_reason_mismatch_is_refused_before_replacing_live_state(
    tmp_path, interrupted_state, reason
):
    interrupted_state['legacy_reason'] = reason
    target = make_study()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as caught:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(caught.value) == 'Checkpoint legacy_reason differs; explicit migration required'
    assert target._snapshot() == before


@pytest.mark.parametrize('maximize', [False, True])
def test_cached_scalar_metric_must_match_direction_and_reject_atomically(
    tmp_path, interrupted_state, maximize
):
    interrupted_state['maximize'] = maximize
    interrupted_state['report_cache'] = report_cache()
    entry = interrupted_state['report_cache']['recovery_trial_1']['1.0']
    expected = -2. if maximize else 2.
    entry['metric'] = expected + 1.
    target = make_study(maximize=maximize)
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as caught:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(caught.value) == 'Checkpoint progress metric differs'
    assert target._snapshot() == before
    entry['metric'] = expected
    target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert target._report_cache['recovery_trial_1'][1.]['metric'] == expected


class DeclarationAwareRandom(RandomSearcher):
    def validate_study_declaration(self, declaration):
        if declaration is not None:
            raise ValueError('This extension accepts only explicit legacy evaluation')
        self.validated_declaration = declaration
        self.declaration_checked = True


def test_legacy_recovery_revalidates_searcher_with_no_declaration(tmp_path):
    source = make_study(searcher=DeclarationAwareRandom(space(), seed=17))
    target = make_study(searcher=DeclarationAwareRandom(space(), seed=99))
    target.searcher.declaration_checked = False
    target.load_checkpoint(write_state(tmp_path, source._snapshot()))
    assert target.searcher.declaration_checked is True
    assert target.searcher.validated_declaration is None


@pytest.mark.parametrize("trial,step,value,message", [
    ("ghost", 1., 2., "Progress cache without trial"),
    ("recovery_trial_1", 0., 2., "Invalid checkpoint progress report"),
    ("recovery_trial_1", 1.1, 2., "Invalid checkpoint progress report"),
    ("recovery_trial_1", float("nan"), 2., "Invalid checkpoint progress report"),
    ("recovery_trial_1", float("inf"), 2., "Invalid checkpoint progress report"),
    ("recovery_trial_1", .5, float("nan"), "Invalid checkpoint progress report"),
    ("recovery_trial_1", .5, float("inf"), "Invalid checkpoint progress report"),
])
def test_invalid_progress_cache_is_refused_atomically(tmp_path, interrupted_state, trial, step, value, message):
    interrupted_state["report_cache"] = report_cache(trial, step, value)
    target = make_study()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as error:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == message
    assert target._snapshot() == before


@pytest.mark.parametrize("field,value,message", [
    ("root_trial_id", "recovery_trial_0", "Checkpoint progress root differs"),
    ("continuation", "resume", "Checkpoint trial continuation differs"),
    ("resume_from", float("nan"), "Invalid checkpoint resume fidelity"),
    ("resume_from", float("inf"), "Invalid checkpoint resume fidelity"),
    ("resume_from", -.1, "Invalid checkpoint resume fidelity"),
    ("resume_from", 1., "Invalid checkpoint resume fidelity"),
    ("resume_from", .25, "Restart checkpoint contains resume state"),
    ("checkpoint", {"step": 0}, "Restart checkpoint contains resume state"),
])
def test_invalid_trial_continuation_metadata_is_refused(tmp_path, interrupted_state, field, value, message):
    interrupted_state["trials"]["recovery_trial_1"][field] = value
    target = make_study()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError) as error:
        target.load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == message
    assert target._snapshot() == before


def test_checkpoint_cannot_change_the_declared_continuation_policy(tmp_path, interrupted_state):
    interrupted_state["continuation"] = "resume"
    with pytest.raises(ValueError) as error:
        make_study().load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == "Checkpoint continuation policy differs"


def test_legacy_checkpoint_defaults_preserve_pending_work_and_restore_roots(tmp_path, interrupted_state):
    interrupted_state["schema_version"] = 2
    for key in ["continuation", "report_cache", "live_elapsed", "abandoned_elapsed", "live_cost", "abandoned_cost",
                "cancel_requested", "accounting_incomplete", "stop_reason", "outcome"]:
        interrupted_state.pop(key)
    for trial in interrupted_state["trials"].values():
        for key in ["root_trial_id", "continuation", "resume_from", "checkpoint"]:
            trial.pop(key)
    target = make_study(checkpoint_dir=tmp_path)
    target.load_checkpoint(write_state(tmp_path, interrupted_state))
    target.save_checkpoint()
    saved = json.loads((tmp_path / "recovery_checkpoint.json").read_text())
    assert saved["continuation"] == "restart"
    assert saved["report_cache"] == {}
    assert saved["cancel_requested"] == saved["accounting_incomplete"] == []
    assert saved["stop_reason"] is saved["outcome"] is None
    for field in ["live_elapsed", "abandoned_elapsed", "live_cost", "abandoned_cost"]:
        assert saved[field] == {}
    assert all(trial["root_trial_id"] == saved["roots"][tid] for tid, trial in saved["trials"].items())
    assert target.run().n_trials == 3


def test_legacy_checkpoint_does_not_overwrite_an_inconsistent_explicit_root(tmp_path, interrupted_state):
    interrupted_state["schema_version"] = 2
    interrupted_state["trials"]["recovery_trial_1"]["root_trial_id"] = "recovery_trial_0"
    with pytest.raises(ValueError) as error:
        make_study().load_checkpoint(write_state(tmp_path, interrupted_state))
    assert str(error.value) == "Checkpoint progress root differs"


def test_valid_resume_and_boundary_progress_keep_checkpoint_accounting(tmp_path, interrupted_state):
    interrupted_state["continuation"] = "resume"
    for trial in interrupted_state["trials"].values():
        trial["continuation"] = "resume"
    pending = interrupted_state["trials"]["recovery_trial_1"]
    pending["resume_from"], pending["checkpoint"] = .5, {"step": .5}
    interrupted_state["compute_budget_seconds"] = .5
    interrupted_state["report_cache"] = report_cache()
    for index, field in enumerate(["live_elapsed", "abandoned_elapsed", "live_cost", "abandoned_cost"]):
        interrupted_state[field] = {"recovery_trial_1": (index + 1) / 1000}
    target = make_study(continuation="resume", checkpoint_dir=tmp_path)
    target.load_checkpoint(write_state(tmp_path, interrupted_state))
    target.save_checkpoint()
    saved = json.loads((tmp_path / "recovery_checkpoint.json").read_text())
    assert saved == interrupted_state


def test_interrupted_recovery_retains_cancellation_and_unknown_work(tmp_path, interrupted_state):
    pending = "recovery_trial_1"
    interrupted_state["live_elapsed"] = {pending: .25}
    interrupted_state["live_cost"] = {pending: .5}

    def interrupt(config, seed, fidelity, reporter):
        raise KeyboardInterrupt("second crash before the next acknowledged report")

    source = make_study(objective_fn=interrupt, checkpoint_dir=tmp_path)
    source.load_checkpoint(write_state(tmp_path, interrupted_state))
    source.cancel_trial(pending)
    with pytest.raises(KeyboardInterrupt):
        source.run()
    path = tmp_path / "recovery_checkpoint.json"
    state = json.loads(path.read_text())
    assert state["cancel_requested"] == state["accounting_incomplete"] == [pending]

    def stream(config, seed, fidelity, reporter):
        value = objective(config, seed, fidelity)
        reporter(fidelity, value, cost=1.)
        return value

    restored = make_study(objective_fn=stream, checkpoint_dir=tmp_path)
    restored.load_checkpoint(path)
    restored.save_checkpoint()
    assert json.loads(path.read_text()) == state
    outcome = restored.run()
    cancelled = next(result for result in outcome.history if result.trial_id == pending)
    assert cancelled.status == "cancelled"


def test_finished_compute_budget_outcome_survives_resaving(tmp_path):
    import time

    def measured(config, seed, fidelity):
        time.sleep(.01)
        return objective(config, seed, fidelity)

    source = make_study(objective_fn=measured, compute_budget_seconds=.005,
                        max_concurrent=1, checkpoint_dir=tmp_path)
    outcome = source.run()
    assert outcome.status == outcome.reason == "compute_budget_exhausted"
    path = tmp_path / "recovery_checkpoint.json"
    state = json.loads(path.read_text())
    restored = make_study(checkpoint_dir=tmp_path)
    restored.load_checkpoint(path)
    restored.save_checkpoint()
    assert json.loads(path.read_text()) == state


class InPlaceRecoveringRandom(RandomSearcher):
    """An extension restoring its public observation buffer in place."""

    def set_state(self, state):
        from hponas.types import Result

        self.history[:] = [Result(**row) for row in state["history"]]
        super().set_state(state)


def test_failed_component_restore_does_not_change_live_observations(tmp_path):
    source = make_study(searcher=InPlaceRecoveringRandom(space(), seed=17))
    source.run()
    invalid = source._snapshot()
    invalid["searcher_state"]["rng_state"] = ["unknown-generator", [], 0, 0, 0.]
    target = make_study(searcher=InPlaceRecoveringRandom(space(), seed=91),
                        study_name="live", budget=1)
    target.run()
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError):
        target.load_checkpoint(write_state(tmp_path, invalid))
    assert target._snapshot() == before


class InPlaceRecoveringASHA(ASHAScheduler):
    """An extension restoring a mutable public configuration before its ledger."""

    def load_state_dict(self, state):
        self.config.r_max = state["config"]["r_max"]
        super().load_state_dict(state)


def test_later_refusal_cannot_change_live_scheduler_configuration(tmp_path):
    source = make_study(scheduler=InPlaceRecoveringASHA(ASHAConfig(r_max=4)))
    invalid = source._snapshot()
    invalid["continuation"] = "resume"
    target = make_study(scheduler=InPlaceRecoveringASHA(ASHAConfig(r_max=9)))
    before = copy.deepcopy(target._snapshot())
    with pytest.raises(ValueError, match="^Checkpoint continuation policy differs$"):
        target.load_checkpoint(write_state(tmp_path, invalid))
    assert target._snapshot() == before
