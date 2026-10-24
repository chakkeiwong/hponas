"""Reject invalid progress, forged lifecycle events and unsafe recovery state."""

import copy
import json
import time

import pytest

from hponas import Config, LocalExecutor, Study, Trial
from hponas.events import EventLog, EventType
from hponas.executors.base import evaluate_trial
from hponas.executors.reporting import ReportDecision, TrialReporter
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import RandomSearcher
from hponas.space import Knob, SearchSpace


@pytest.mark.parametrize('key', ['multi_objective', 'resource'])
@pytest.mark.parametrize('damage', ['changed', 'missing'])
def test_final_output_must_preserve_reported_endpoint_measurements(key, damage):
    payload = {'a': 2., 'b': 3.} if key == 'multi_objective' else {'work': 2., 'unit': 'evaluations'}
    def objective(config, reporter):
        reporter(1., 7., cost=2., metadata={key: payload})
        metadata = {key: {'changed': True}} if damage == 'changed' else {}
        return dict(value=7., cost=2., metadata=metadata)
    result = evaluate_trial(Trial(Config({'x': 1}), 'endpoint'), objective)
    assert result.status == 'failed'
    assert result.metadata['error'] == 'Final measurement conflicts with reported endpoint metadata'
    assert result.metadata[key] == payload
    assert result.cost >= 2.


def test_progress_metadata_reaches_callback_and_final_result():
    reports = []
    payload = {'multi_objective': {'a': 2., 'b': 3.}, 'resource': {'work': 2., 'unit': 'evaluations'}}
    def callback(report):
        reports.append(report.to_dict())
        return ReportDecision()
    def objective(config, reporter):
        reporter(1., 7., cost=2., metadata=payload)
        return dict(value=7., cost=2., metadata=payload)
    result = evaluate_trial(Trial(Config({'x': 1}), 'endpoint'), objective, callback)
    assert result.status == 'completed'
    assert reports[0]['metadata'] == payload
    assert all(result.metadata[k] == v for k, v in payload.items())


@pytest.mark.parametrize('metadata', [[], 'wrong', 1])
def test_progress_metadata_requires_dictionary_with_precise_refusal(metadata):
    reporter = TrialReporter(Trial(Config({}), 'report'), None, time.monotonic())
    with pytest.raises(ValueError) as caught:
        reporter(1., 7., cost=1., metadata=metadata)
    assert str(caught.value) == 'Progress metadata must be a dictionary'
    assert reporter.last is None


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), object()])
def test_progress_metadata_must_be_json_serializable_before_publication(invalid):
    reports = []
    reporter = TrialReporter(Trial(Config({}), 'report'), reports.append, time.monotonic())
    with pytest.raises((ValueError, TypeError)):
        reporter(1., 7., cost=1., metadata={'measurement': invalid})
    assert reporter.last is None
    assert reports == []

@pytest.mark.parametrize(
    "reports",
    [
        [(0, 1, 0)],
        [(5, 1, 1)],
        [(1, float("nan"), 1)],
        [(1, 1, -1)],
        [(2, 1, 2), (1, 1, 3)],
        [(1, 1, 2), (2, 1, 1)],
    ],
)
def test_invalid_progress_fails_without_a_successful_incumbent(reports):
    def objective(config, reporter):
        for step, value, cost in reports:
            reporter(step, value, cost=cost)
        return {"value": 1, "cost": 5}

    result = evaluate_trial(Trial(Config({}), "a", fidelity=4), objective)
    assert result.status == "failed" and not result.is_valid()


def test_invalid_final_cost_cannot_discard_reported_work():
    def objective(config, reporter):
        reporter(1, 1, cost=10)
        return {"value": 1, "cost": 1}

    result = evaluate_trial(Trial(Config({}), "a", fidelity=4), objective)
    assert result.status == "failed" and result.cost >= 10


@pytest.mark.parametrize("report_step", [None, 1])
def test_early_return_cannot_fabricate_full_fidelity_completion(report_step):
    def objective(config, reporter):
        if report_step is not None:
            reporter(report_step, 1, cost=1)
        return {"value": 1, "cost": 1}

    result = evaluate_trial(Trial(Config({}), "early", fidelity=4), objective)
    assert result.status == "failed" and not result.is_valid()
    assert "assigned endpoint" in result.metadata["error"]


@pytest.mark.parametrize(
    "action,status", [("pause", "paused"), ("stop", "pruned"), ("cancel", "cancelled")]
)
def test_objective_cannot_swallow_control_decisions_and_report_success(action, status):
    def objective(config, reporter):
        try:
            reporter(1, 2, cost=3)
        except BaseException:
            pass
        return {"value": 2, "cost": 3}

    result = evaluate_trial(
        Trial(Config({}), "a", fidelity=4), objective, lambda r: ReportDecision(action)
    )
    assert result.status == status and result.cost == 3


@pytest.mark.parametrize("checkpoint", [None, {"step": 1}])
def test_resume_requires_state_and_an_explicit_objective_contract(checkpoint):
    result = evaluate_trial(
        Trial(
            Config({}),
            "a",
            fidelity=4,
            continuation="resume",
            resume_from=1,
            checkpoint=checkpoint,
        ),
        lambda c: 1,
    )
    assert result.status == "failed" and not result.is_valid()


def new_searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0, 1))]), seed=19)


def new_scheduler():
    return ASHAScheduler(ASHAConfig(r_min=2, r_max=2))


def objective(config, reporter):
    reporter(1, 3, cost=1)
    reporter(2, 3, cost=2)
    return {"value": 3, "cost": 2}


@pytest.mark.parametrize(
    "field,value",
    [
        ("root", "other"),
        ("schema_version", 99),
        ("scheduler_decision", "stop"),
        ("control", {"action": "cancel", "reason": "scheduler"}),
    ],
)
def test_replay_rejects_forged_progress(tmp_path, field, value):
    events = EventLog(tmp_path / "log.jsonl")
    study = Study(
        new_searcher(),
        LocalExecutor(),
        objective,
        budget=1,
        scheduler=new_scheduler(),
        event_log=events,
     legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    study.run()
    events.get_events(EventType.PROGRESS)[0].data[field] = value
    assert not ReplayEngine(
        new_searcher(), events, 19, new_scheduler()
    ).verify_determinism(1)[0]


def test_replay_rejects_forged_completion(tmp_path):
    events = EventLog(tmp_path / "log.jsonl")
    study = Study(
        new_searcher(),
        LocalExecutor(),
        objective,
        budget=1,
        scheduler=new_scheduler(),
        event_log=events,
     legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    study.run()
    events.get_events(EventType.FINISH)[0].data["status"] = "failed"
    passed, message, _, _ = ReplayEngine(
        new_searcher(), events, 19, new_scheduler()
    ).verify_determinism(1)
    assert not passed and "outcome" in message


@pytest.mark.parametrize(
    "field,value",
    [
        ("live_elapsed", {"unknown": 0}),
        ("abandoned_cost", {"a": -1}),
        ("compute_budget_seconds", float("nan")),
    ],
)
def test_rejected_accounting_checkpoint_leaves_live_study_unchanged(
    tmp_path, field, value
):
    study = Study(
        new_searcher(), LocalExecutor(), objective, budget=1, scheduler=new_scheduler()
    , legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    before = copy.deepcopy(study._snapshot())
    state = copy.deepcopy(before)
    state[field] = value
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError):
        study.load_checkpoint(path)
    assert study._snapshot() == before


def test_invalid_scheduler_recovery_does_not_replace_live_state():
    scheduler = new_scheduler()
    before = scheduler.state_dict()
    corrupted = copy.deepcopy(before)
    corrupted["rungs"] = [999]
    with pytest.raises(ValueError, match="rungs"):
        scheduler.load_state_dict(corrupted)
    assert scheduler.state_dict() == before
