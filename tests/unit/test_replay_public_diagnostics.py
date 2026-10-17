"""Replay refusal diagnostics and streamed event lifecycle witnesses."""

import copy
from types import SimpleNamespace

import pytest

from hponas.events import Event, EventType
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.types import Config


class Searcher:
    def __init__(self):
        self.trials, self.history, self.index = {}, [], 0

    def get_state(self):
        return {"index": self.index, "trials": copy.deepcopy(self.trials), "history": copy.deepcopy(self.history)}

    def set_state(self, state):
        self.index, self.trials, self.history = state["index"], state["trials"], state["history"]

    def suggest(self):
        self.index += 1
        return Config({"x": self.index})

    def observe(self, result):
        self.history.append(result)


class Log:
    def __init__(self, events):
        self.events = events

    def get_events(self):
        return self.events

    def is_empty(self):
        return not self.events


class Scheduler:
    def __init__(self, promotions=()):
        self.config = SimpleNamespace(r_max=3, promotion_policy="current")
        self.promotions = list(promotions)
        self.finished = []
        self._terminal = {}

    def state_dict(self):
        return {"finished": list(self.finished)}

    def load_state_dict(self, state):
        self.finished = state["finished"]

    def report(self, root, fidelity, value, *, is_progress=False):
        return "continue" if fidelity < 3 else "stop"

    def promote(self):
        return list(self.promotions)

    def finish(self, root, status):
        self.finished.append((root, status))


def event(kind, data, trial="t", index=1):
    return Event(index, kind, 0., trial, data)


def suggestion():
    return event(EventType.SUGGEST, {"config": {"x": 1}}, index=0)


@pytest.mark.parametrize("kind,version_message,outcome_message", [
    (EventType.SEARCH_BUDGET_EXHAUSTED, "Unsupported search budget event version", "Search budget was not exhausted"),
    (EventType.SEARCH_EXHAUSTED, "Unsupported exhaustion event version", "Search space was not exhausted"),
    (EventType.SUGGEST_PENDING, "Unsupported pending suggestion version", "Pending suggestion unexpectedly completed"),
])
def test_exhaustion_and_pending_refusals_identify_the_actual_problem(kind, version_message, outcome_message):
    for version, expected in [(2, version_message), (1, outcome_message)]:
        engine = ReplayEngine(Searcher(), Log([event(kind, {"schema_version": version})]), seed=0)
        passed, message, original, replayed = engine.verify_determinism(1)
        assert not passed and message == expected
        assert original == replayed == []


def test_replay_initial_fidelity_refusal_is_explanatory():
    class RegisteredScheduler(Scheduler):
        def register_trial(self, trial_id):
            return 2.0

    events = [event(EventType.SUGGEST, {"config": {"x": 1}, "fidelity": 1.0}, index=0)]
    passed, message, original, replayed = ReplayEngine(
        Searcher(), Log(events), 0, RegisteredScheduler()).verify_determinism(1)
    assert not passed and message == "Initial scheduler fidelity mismatch"
    assert original == replayed == []


def test_replay_registers_root_and_parent_metadata_for_searcher_extensions():
    class RegisteredSearcher(Searcher):
        def __init__(self):
            super().__init__()
            self.registered = []

        def register_trial(self, trial):
            self.registered.append(trial)

    searcher = RegisteredSearcher()
    events = [
        event(EventType.SUGGEST, {"config": {"x": 1}, "fidelity": 1.0}, index=0),
        event(EventType.PROMOTION_ROUND, {"promotions": [["t", 3.0]]}, index=1),
        event(EventType.PROMOTE, {"config": {"x": 1}, "root": "t", "parent": "t",
                                 "to_fidelity": 3.0}, trial="promoted", index=2),
    ]
    passed, _, original, replayed = ReplayEngine(
        searcher, Log(events), 0, Scheduler([("t", 3.0)])).verify_determinism(1)
    assert passed and original == replayed == [{"x": 1}]
    assert [(t.trial_id, t.root_trial_id, t.parent_trial_id, t.fidelity, t.config.values)
            for t in searcher.registered] == [
        ("t", "t", None, 1.0, {"x": 1}),
        ("promoted", "t", "t", 3.0, {"x": 1}),
    ]


def progress(**updates):
    data = {"schema_version": 1, "root": "t", "root_trial_id": "t", "step": 1,
            "normalized_value": 2., "scheduler_applied": False,
            "scheduler_decision": "continue", "control": {"action": "continue"}}
    data.update(updates)
    return data


CASES = [
    ("empty", "Empty event log or replay request"),
    ("zero", "Empty event log or replay request"),
    ("event_order", "Event order is not strictly increasing"),
    ("duplicate_trial", "Duplicate suggestion identity"),
    ("orphan_observation", "Observation without configuration"),
    ("no_report_scheduler", "Scheduler required to replay report events"),
    ("report_mismatch", "Scheduler report mismatch"),
    ("progress_version", "Unsupported progress version"),
    ("progress_orphan", "Progress identity or lifecycle mismatch"),
    ("progress_finished", "Progress identity or lifecycle mismatch"),
    ("progress_root", "Progress identity or lifecycle mismatch"),
    ("progress_root_id", "Progress identity or lifecycle mismatch"),
    ("no_progress_scheduler", "Scheduler required to replay progress"),
    ("progress_mismatch", "Scheduler progress mismatch"),
    ("control_mismatch", "Scheduler progress control mismatch"),
    ("cancel_without_request", "Cancellation without a request"),
    ("budget_without_cap", "Compute cancellation before budget exhaustion"),
    ("budget_before_cap", "Compute cancellation before budget exhaustion"),
    ("cancel_reason", "Unknown cancellation reason"),
    ("cancel_version", "Cancellation identity or version mismatch"),
    ("cancel_root", "Cancellation identity or version mismatch"),
    ("no_finish_scheduler", "Scheduler required to replay completion"),
    ("finish_version", "Unsupported completion version"),
    ("finish_root", "Completion identity mismatch"),
    ("finish_status", "Completion disagrees with evaluation outcome"),
    ("no_round_scheduler", "Scheduler required to replay promotion rounds"),
    ("round_mismatch", "Scheduler promotion round mismatch"),
    ("no_promotion_scheduler", "Scheduler required to replay promotions"),
    ("promotion_mismatch", "Scheduler promotion mismatch"),
    ("missing_promotion", "Missing promotion events"),
    ("next_round", "Missing promotion events"),
    ("cull", "Cull event lacks a replayable scheduler report"),
    ("insufficient", "Insufficient suggestion events"),
]


@pytest.mark.parametrize("case,message", CASES)
def test_replay_refuses_corrupt_or_incomplete_public_events_with_exact_diagnostic(case, message):
    events, scheduler, trials = [suggestion()], None, 1
    if case == "empty":
        events = []
    elif case == "zero":
        trials = 0
    elif case == "event_order":
        events.append(event(EventType.CHECKPOINT, {}, index=0))
    elif case == "duplicate_trial":
        trials = 2
        events.append(event(EventType.SUGGEST, {"config": {"x": 2}}))
    elif case == "orphan_observation":
        events.append(event(EventType.OBSERVE, {"value": 2.}, trial="unknown"))
    elif case in {"no_report_scheduler", "report_mismatch"}:
        scheduler = Scheduler() if case == "report_mismatch" else None
        events.append(event(EventType.REPORT, {"root": "t", "fidelity": 1, "value": 2., "decision": "pause"}))
    elif case.startswith("progress_") or case in {"no_progress_scheduler", "control_mismatch"}:
        data = progress()
        if case == "progress_version":
            data["schema_version"] = 0
        elif case == "progress_root":
            data.update(root="wrong", root_trial_id="wrong")
        elif case == "progress_root_id":
            data["root_trial_id"] = "wrong"
        elif case == "progress_finished":
            events.append(event(EventType.OBSERVE, {"value": 2.}))
        elif case in {"no_progress_scheduler", "progress_mismatch", "control_mismatch"}:
            data["scheduler_applied"] = True
            if case != "no_progress_scheduler":
                scheduler = Scheduler()
                if case == "progress_mismatch":
                    data["scheduler_decision"] = "pause"
                else:
                    data["control"] = {"action": "stop"}
        events.append(event(EventType.PROGRESS, data, trial="unknown" if case == "progress_orphan" else "t", index=len(events)))
    elif case in {"cancel_without_request", "budget_without_cap", "budget_before_cap", "cancel_reason"}:
        reason = "user_cancellation" if case == "cancel_without_request" else "compute_budget_exhausted" if case.startswith("budget") else "invented"
        data = progress(control={"action": "cancel", "reason": reason})
        if case == "budget_before_cap":
            data.update(compute_budget_seconds=10., total_elapsed_seconds=9.)
        events.append(event(EventType.PROGRESS, data))
    elif case in {"cancel_version", "cancel_root"}:
        events.append(event(EventType.CANCEL_REQUEST, {"schema_version": 0 if case == "cancel_version" else 1,
                                                       "root": "wrong" if case == "cancel_root" else "t"}))
    elif case in {"no_finish_scheduler", "finish_version", "finish_root", "finish_status"}:
        scheduler = None if case == "no_finish_scheduler" else Scheduler()
        events.append(event(EventType.FINISH, {"schema_version": 0 if case == "finish_version" else 1,
                                               "root": "wrong" if case == "finish_root" else "t", "status": "completed"}))
    elif case in {"no_round_scheduler", "round_mismatch", "missing_promotion", "next_round"}:
        if case != "no_round_scheduler":
            scheduler = Scheduler([("t", 3.)])
        events.append(event(EventType.PROMOTION_ROUND, {"promotions": [] if case == "round_mismatch" else [["t", 3.]]}))
        if case == "next_round":
            events.append(event(EventType.PROMOTION_ROUND, {"promotions": [["t", 3.]]}, index=2))
    elif case in {"no_promotion_scheduler", "promotion_mismatch"}:
        scheduler = None if case == "no_promotion_scheduler" else Scheduler()
        events.append(event(EventType.PROMOTE, {"root": "t", "to_fidelity": 3.}))
    elif case == "cull":
        events.append(event(EventType.CULL, {}))
    elif case == "insufficient":
        trials = 2
    else:
        raise AssertionError(case)
    accepted, diagnostic, original, repeated = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(trials)
    assert accepted is False
    assert diagnostic == message
    assert original == repeated


@pytest.mark.parametrize("mode", ["no_finish", "legacy", "missing_policy", "current"])
def test_replay_adapts_progress_call_to_scheduler_public_contract(mode):
    class EndpointOnly:
        def state_dict(self):
            return {}

        def load_state_dict(self, state):
            pass

        def report(self, root, fidelity, value):
            return "continue"

    class Legacy(EndpointOnly):
        config = SimpleNamespace(promotion_policy="legacy_bootstrap", r_max=3)

        def finish(self, root, status):
            pass

    class Current(EndpointOnly):
        config = SimpleNamespace(r_max=3)

        def report(self, root, fidelity, value, *, is_progress=False):
            return "continue" if is_progress else "pause"

        def finish(self, root, status):
            pass

    scheduler = EndpointOnly() if mode == "no_finish" else Legacy() if mode == "legacy" else Current()
    if mode == "current":
        scheduler.config = SimpleNamespace(promotion_policy="current", r_max=3)
    events = [suggestion(), event(EventType.PROGRESS, progress(scheduler_applied=True))]
    assert ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1) == (
        True, "Replay exact", [{"x": 1}], [{"x": 1}])


@pytest.mark.parametrize("reason", ["user_cancellation", "compute_budget_exhausted"])
def test_replay_accepts_complete_cancellation_at_the_budget_boundary(reason):
    events = [suggestion()]
    if reason == "user_cancellation":
        events.append(event(EventType.CANCEL_REQUEST, {"schema_version": 1, "root": "t"}))
    events.append(event(EventType.PROGRESS, progress(control={"action": "cancel", "reason": reason},
        compute_budget_seconds=10., total_elapsed_seconds=10.), index=len(events)))
    events.append(event(EventType.OBSERVE, {"value": 2., "status": "cancelled"}, index=len(events)))
    events.append(event(EventType.FINISH, {"schema_version": 1, "root": "t", "status": "cancelled"}, index=len(events)))
    scheduler = Scheduler()
    assert ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)[0] is True
    assert scheduler.finished == [("t", "cancelled")]


@pytest.mark.parametrize("terminal", ["pruned", "completed", "absent"])
def test_maximum_resource_stop_preserves_pruning_but_does_not_cancel_normal_completion(terminal):
    class TerminalScheduler:
        config = SimpleNamespace(r_max=3)

        def state_dict(self):
            return {}

        def load_state_dict(self, state):
            pass

        def report(self, root, fidelity, value):
            if terminal != "absent":
                self._terminal = {root: terminal}
            return "stop"

    scheduler = TerminalScheduler()
    data = progress(step=3, scheduler_applied=True, scheduler_decision="stop",
                    control={"action": "stop" if terminal == "pruned" else "continue"})
    events = [suggestion(), event(EventType.PROGRESS, data)]
    assert ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1) == (
        True, "Replay exact", [{"x": 1}], [{"x": 1}])


def test_completion_requires_a_scheduler_implementing_the_finish_contract():
    scheduler = SimpleNamespace(state_dict=lambda: {}, load_state_dict=lambda state: None)
    events = [suggestion(), event(EventType.FINISH, {"schema_version": 1, "root": "t", "status": "completed"})]
    result = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)
    assert result[:2] == (False, "Scheduler required to replay completion")


@pytest.mark.parametrize("status", ["completed", "pruned", "cancelled", "failed", "nan", "timeout"])
def test_completion_maps_unsuccessful_observation_statuses_to_failed(status):
    expected = status if status in {"completed", "pruned", "cancelled"} else "failed"
    events = [suggestion(), event(EventType.OBSERVE, {"value": 2., "status": status}),
              event(EventType.FINISH, {"schema_version": 1, "root": "t", "status": expected}, index=2)]
    scheduler = Scheduler()
    result = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)
    assert result == (True, "Replay exact", [{"x": 1}], [{"x": 1}])
    assert scheduler.finished == [("t", expected)]


def test_missing_observation_and_null_completion_remain_a_precise_real_scheduler_refusal():
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=3, eta=3))
    before = copy.deepcopy(scheduler.state_dict())
    events = [suggestion(), event(EventType.FINISH, {"schema_version": 1, "root": "t", "status": None})]
    result = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)
    assert result[:2] == (False, "Unknown terminal trial status")
    assert scheduler.state_dict() == before


@pytest.mark.parametrize("requested", [False, True])
def test_cancellation_before_evaluation_requires_an_explicit_request(requested):
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=3, eta=3))
    events = [suggestion()]
    if requested:
        events.append(event(EventType.CANCEL_REQUEST, {"schema_version": 1, "root": "t"}))
    events.append(event(EventType.FINISH, {"schema_version": 1, "root": "t", "status": "cancelled"}, index=len(events)))
    result = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)
    assert result[:2] == ((True, "Replay exact") if requested else (False, "Completion disagrees with evaluation outcome"))
    assert scheduler.state_dict()["terminal"] == ({"t": "cancelled"} if requested else {})


def test_legacy_promotion_without_root_retains_identity_for_later_progress():
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=3, eta=3, promotion_policy="legacy_bootstrap"))
    events = [suggestion(),
              event(EventType.REPORT, {"root": "t", "fidelity": 1, "value": 2., "decision": "pause"}),
              event(EventType.PROMOTE, {"from_fidelity": 1, "to_fidelity": 3}, index=2),
              event(EventType.PROGRESS, progress(step=3, scheduler_applied=True, scheduler_decision="stop",
                                               control={"action": "continue"}), index=3)]
    result = ReplayEngine(Searcher(), Log(events), 0, scheduler).verify_determinism(1)
    assert result == (True, "Replay exact", [{"x": 1}], [{"x": 1}])
