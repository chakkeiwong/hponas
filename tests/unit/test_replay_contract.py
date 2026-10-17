# Historical event fixtures explicitly replay the legacy bootstrap policy.
"""Small adaptive traces distinguish replaying transitions from reading a log."""

import copy

import pytest

from hponas.events import Event, EventLog, EventType
from hponas.replay import ReplayEngine, record_optimization_run
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers.base import BaseSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Result


class AdaptiveSearcher(BaseSearcher):
    def __init__(self):
        super().__init__(SearchSpace([Knob("x", "continuous", (0.0, 1000.0))]), seed=17)
        self.index = 0

    def suggest(self):
        self.index += 1
        return Config({"x": self.index + sum(r.objective_value for r in self.history)})

    def get_state(self):
        return {**super().get_state(), "index": self.index}

    def set_state(self, state):
        super().set_state(state)
        self.index = state["index"]


@pytest.mark.parametrize(
    "batch_size,expected",
    [
        (1, [1.0, 4.0, 13.0, 40.0, 121.0]),
        (2, [1.0, 2.0, 9.0, 10.0, 49.0]),
        (9, [1.0, 2.0, 3.0, 4.0, 5.0]),
    ],
)
def test_record_and_replay_preserve_batch_feedback_order(
    tmp_path, batch_size, expected
):
    log = EventLog(tmp_path / "adaptive.jsonl")
    searcher = AdaptiveSearcher()
    configs = record_optimization_run(
        searcher, lambda c: 2 * c["x"], 5, log, batch_size
    )
    assert [c["x"] for c in configs] == expected
    assert [r.trial_id for r in searcher.history] == [f"trial_{i}" for i in range(5)]
    assert [r.objective_value for r in searcher.history] == [2 * x for x in expected]
    assert all(r.fidelity == 1.0 and r.cost >= 0.0 for r in searcher.history)
    assert searcher.trials == {f"trial_{i}": c for i, c in enumerate(configs)}
    assert [e.data["seed"] for e in log.get_suggestions()] == [17] * 5
    replay = ReplayEngine(AdaptiveSearcher(), EventLog(log.log_path), 17)
    for _ in range(2):
        passed, _, original, repeated = replay.verify_determinism(5, batch_size=99)
        assert passed
        assert original == repeated == [c.values for c in configs]
        assert replay.searcher.history == searcher.history
        assert replay.searcher.trials == searcher.trials
    assert replay.replay_suggestions(3) == [c.values for c in configs[:3]]


@pytest.mark.parametrize("trials,batch", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_record_rejects_nonpositive_counts_before_writing(tmp_path, trials, batch):
    log = EventLog(tmp_path / "invalid.jsonl")
    with pytest.raises(ValueError, match="positive"):
        record_optimization_run(AdaptiveSearcher(), lambda c: 1.0, trials, log, batch)
    assert log.is_empty()


def test_empty_zero_and_insufficient_replay_requests_fail_explicitly(tmp_path):
    log = EventLog(tmp_path / "empty.jsonl")
    replay = ReplayEngine(AdaptiveSearcher(), log, 17)
    assert replay.verify_determinism(1)[0] is False
    with pytest.raises(ValueError, match="empty"):
        replay.replay_suggestions(1)
    record_optimization_run(AdaptiveSearcher(), lambda c: 2.0, 1, log)
    assert replay.verify_determinism(0)[0] is False
    with pytest.raises(ValueError, match="Insufficient"):
        replay.replay_suggestions(2)


@pytest.mark.parametrize(
    "corruption,reason",
    [
        ("duplicate_event", "strictly increasing"),
        ("duplicate_trial", "Duplicate suggestion"),
        ("wrong_config", "Suggestion mismatch"),
        ("orphan_observe", "without configuration"),
        ("missing_config", "config"),
    ],
)
def test_corrupted_adaptive_trace_is_rejected(tmp_path, corruption, reason):
    log = EventLog(tmp_path / "corrupt.jsonl")
    record_optimization_run(AdaptiveSearcher(), lambda c: 2.0, 2, log, batch_size=2)
    events = log.get_events()
    if corruption == "duplicate_event":
        events[1].event_id = events[0].event_id
    elif corruption == "duplicate_trial":
        events[1].trial_id = events[0].trial_id
    elif corruption == "wrong_config":
        events[1].data["config"]["x"] += 1
    elif corruption == "orphan_observe":
        events[2].trial_id = "unknown"
    else:
        events[0].data.pop("config")
    replay = ReplayEngine(AdaptiveSearcher(), log, 17)
    passed, message, _, _ = replay.verify_determinism(2)
    assert passed is False and reason in message


def test_observation_envelope_fields_survive_replay(tmp_path):
    log = EventLog(tmp_path / "envelope.jsonl")
    log.record_suggest("t", {"x": 1}, 17)
    append_event(
        log,
        EventType.OBSERVE,
        "t",
        {
            "objective_value": 7.0,
            "value": -1.0,
            "cost": 3.5,
            "fidelity": 9.0,
            "metadata": {"artifact": "a"},
            "status": "failed",
        },
    )
    replay = ReplayEngine(AdaptiveSearcher(), log, 17)
    assert replay.verify_determinism(1)[0]
    assert replay.searcher.history == [
        Result("t", 7.0, 3.5, 9.0, {"artifact": "a"}, "failed")
    ]


def append_event(log, kind, trial_id, data):
    log._write_event(Event(log.count(), kind, 0.0, trial_id, data))


def scheduled_trace(tmp_path, explicit=True):
    log = EventLog(tmp_path / "scheduled.jsonl")
    log.record_suggest("root", {"x": 1}, 17)
    log.record_observe("root", 1.0, 2.0, 3.0)
    append_event(
        log,
        EventType.REPORT,
        "root",
        {"root": "root", "fidelity": 1.0, "value": 2.0, "decision": "pause"},
    )
    if explicit:
        append_event(
            log, EventType.PROMOTION_ROUND, "", {"promotions": [["root", 3.0]]}
        )
    append_event(
        log,
        EventType.PROMOTE,
        "child",
        {"root": "root", "to_fidelity": 3.0, "config": {"x": 1}},
    )
    log.record_observe("child", 3.0, 1.0, 4.0)
    return log


@pytest.mark.parametrize("explicit", [False, True])
def test_scheduler_replay_repeats_real_decisions_and_registers_promoted_configs(
    tmp_path, explicit
):
    log = scheduled_trace(tmp_path, explicit)
    scheduler = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", r_max=3))
    replay = ReplayEngine(AdaptiveSearcher(), log, 17, scheduler)
    initial = copy.deepcopy(scheduler.state_dict())
    for _ in range(2):
        assert replay.verify_determinism(1)[0]
        assert replay.searcher.trials["child"] == Config({"x": 1})
        assert replay.searcher.history[-1] == Result("child", 1.0, 4.0, 3.0)
    assert initial != scheduler.state_dict()


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("report", "report mismatch"),
        ("round", "round mismatch"),
        ("promotion", "promotion mismatch"),
        ("missing", "Missing promotion"),
        ("next_round", "Missing promotion"),
        ("cull", "Cull event"),
    ],
)
def test_scheduler_transition_mismatch_cannot_pass(tmp_path, fault, reason):
    log = scheduled_trace(tmp_path)
    events = log.get_events()
    if fault == "report":
        events[2].data["decision"] = "continue"
    elif fault == "round":
        events[3].data["promotions"] = []
    elif fault == "promotion":
        events[4].data["to_fidelity"] = 9.0
    elif fault == "missing":
        events[:] = events[:4]
    elif fault == "next_round":
        events[4] = Event(4, EventType.PROMOTION_ROUND, 0.0, "", {"promotions": []})
    else:
        events[2].event_type = EventType.CULL
    replay = ReplayEngine(
        AdaptiveSearcher(), log, 17, ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", r_max=3))
    )
    passed, message, _, _ = replay.verify_determinism(1)
    assert not passed and reason in message


@pytest.mark.parametrize(
    "kind,data",
    [(EventType.REPORT, {}), (EventType.PROMOTION_ROUND, {}), (EventType.PROMOTE, {})],
)
def test_scheduler_events_require_a_scheduler(tmp_path, kind, data):
    log = EventLog(tmp_path / "no-scheduler.jsonl")
    log.record_suggest("root", {"x": 1}, 17)
    append_event(log, kind, "root", data)
    passed, message, _, _ = ReplayEngine(
        AdaptiveSearcher(), log, 17
    ).verify_determinism(1)
    assert not passed and "Scheduler required" in message


def test_default_record_batch_is_sequential_and_cost_is_elapsed(tmp_path, monkeypatch):
    times = iter([10.0, 10.25, 20.0, 20.75])
    monkeypatch.setattr("time.monotonic", lambda: next(times))
    searcher, log = AdaptiveSearcher(), EventLog(tmp_path / "defaults.jsonl")
    configs = record_optimization_run(searcher, lambda c: 2 * c["x"], 2, log)
    assert [c["x"] for c in configs] == [1, 4]
    assert [r.cost for r in searcher.history] == [0.25, 0.75]
    assert [e.data["cost"] for e in log.get_observations()] == [0.25, 0.75]


def test_missing_optional_observation_fields_use_documented_defaults(tmp_path):
    log = EventLog(tmp_path / "defaults.jsonl")
    log.record_suggest("a", {"x": 1}, 17)
    append_event(log, EventType.OBSERVE, "a", {"value": 2.0})
    replay = ReplayEngine(AdaptiveSearcher(), log, 17)
    assert replay.verify_determinism(1)[0]
    assert replay.searcher.history == [Result("a", 2.0, cost=0.0)]


def test_negative_first_event_id_is_invalid(tmp_path):
    log = EventLog(tmp_path / "negative.jsonl")
    log.record_suggest("a", {"x": 1}, 17)
    log.get_events()[0].event_id = -1
    assert not ReplayEngine(AdaptiveSearcher(), log, 17).verify_determinism(1)[0]


def test_legacy_promotion_batch_consumes_each_candidate_in_order(tmp_path):
    log = EventLog(tmp_path / "promotion-batch.jsonl")
    for tid, x in [("a", 1), ("b", 2)]:
        log.record_suggest(tid, {"x": x}, 17)
        append_event(
            log,
            EventType.REPORT,
            tid,
            {"root": tid, "fidelity": 1.0, "value": float(x), "decision": "pause"},
        )
    for tid in ["a", "b"]:
        # Legacy events use their own identity as the root and omit the config.
        log.record_promote(tid, 1.0, 3.0)
    replay = ReplayEngine(
        AdaptiveSearcher(), log, 17, ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", r_max=3))
    )
    assert replay.verify_determinism(2)[0]
    assert replay.searcher.trials == {"a": Config({"x": 1}), "b": Config({"x": 2})}


def test_explicit_empty_round_forbids_unrecorded_promotion(tmp_path):
    log = EventLog(tmp_path / "empty-round.jsonl")
    log.record_suggest("a", {"x": 1}, 17)
    append_event(log, EventType.PROMOTION_ROUND, "", {"promotions": []})
    append_event(
        log,
        EventType.REPORT,
        "a",
        {"root": "a", "fidelity": 1.0, "value": 1.0, "decision": "pause"},
    )
    log.record_promote("a", 1.0, 3.0)
    passed, message, _, _ = ReplayEngine(
        AdaptiveSearcher(), log, 17, ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", r_max=3))
    ).verify_determinism(1)
    assert not passed and "promotion mismatch" in message


def test_replay_owns_nested_initial_and_restored_searcher_state(tmp_path):
    class MutableStateSearcher(AdaptiveSearcher):
        def __init__(self):
            super().__init__()
            self.nested = {"sequence": []}

        def get_state(self):
            return {**super().get_state(), "nested": self.nested}

        def set_state(self, state):
            super().set_state(state)
            self.nested = state["nested"]

        def suggest(self):
            self.nested["sequence"].append(1)
            return Config({"x": len(self.nested["sequence"])})

    log = EventLog(tmp_path / "mutable.jsonl")
    log.record_suggest("a", {"x": 1}, 17)
    searcher = MutableStateSearcher()
    replay = ReplayEngine(searcher, log, 17)
    searcher.nested["sequence"].append(99)
    assert replay.verify_determinism(1)[0]
    assert replay.verify_determinism(1)[0]


def test_replay_owns_nested_initial_and_restored_scheduler_state(tmp_path):
    class MutableStateScheduler:
        def __init__(self):
            self.state = {"reports": []}

        def state_dict(self):
            return self.state

        def load_state_dict(self, state):
            self.state = state

        def report(self, root, fidelity, value):
            self.state["reports"].append(root)
            return "pause" if len(self.state["reports"]) == 1 else "stop"

    log = EventLog(tmp_path / "mutable-scheduler.jsonl")
    log.record_suggest("a", {"x": 1}, 17)
    append_event(
        log,
        EventType.REPORT,
        "a",
        {"root": "a", "fidelity": 1.0, "value": 1.0, "decision": "pause"},
    )
    scheduler = MutableStateScheduler()
    replay = ReplayEngine(AdaptiveSearcher(), log, 17, scheduler)
    scheduler.state["reports"].append("extraneous")
    assert replay.verify_determinism(1)[0]
    assert replay.verify_determinism(1)[0]
