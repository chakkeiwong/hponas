"""Executor boundaries and stopped recovery preserve the public study ledger."""

import json
import math
from types import SimpleNamespace

import pytest

from hponas import IncompleteStudyError, LocalExecutor, RandomSearcher, Study
from hponas.events import EventLog
from hponas.executors import reporting
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.space import Knob, SearchSpace
from hponas.types import Result


def searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=11)


@pytest.mark.parametrize("fault,diagnostic", [
    ("unknown", "Executor returned an unknown or completed trial"),
    ("duplicate", "Executor returned an unknown or completed trial"),
    ("fidelity", "Executor changed trial fidelity"),
])
def test_executor_identity_refusal_keeps_a_durable_valid_prefix(tmp_path, fault, diagnostic):
    class Executor:
        def execute_batch(self, trials, objective_fn):
            first, second = trials
            valid = Result(first.trial_id, 5., 2., first.fidelity)
            invalid = Result(second.trial_id, 7., 3., second.fidelity)
            if fault == "unknown":
                invalid.trial_id = "foreign_trial"
            elif fault == "duplicate":
                invalid.trial_id = first.trial_id
            else:
                invalid.fidelity = second.fidelity + 1
            return [valid, invalid]

        def shutdown(self):
            self.closed = True

    executor = Executor()
    study = Study(searcher(), executor, lambda config: 5., budget=2,
                  max_concurrent=2, study_name="identity", checkpoint_dir=tmp_path)
    with pytest.raises(ValueError) as raised:
        study.run()
    assert str(raised.value) == diagnostic
    assert executor.closed
    state = json.loads((tmp_path / "identity_checkpoint.json").read_text())
    assert list(state["results"]) == ["identity_trial_0"]
    assert state["pending"] == ["identity_trial_1"]
    assert state["results"]["identity_trial_0"]["objective_value"] == 5.


@pytest.mark.parametrize("reported_cost", [0., .25, 2.])
def test_endpoint_batch_and_singleton_keep_identity_results_and_zero_unreported_elapsed(reported_cost):
    class Executor:
        def __init__(self):
            self.calls = []

        def execute_batch(self, trials, objective_fn):
            self.calls.append(("batch", [t.trial_id for t in trials]))
            assert objective_fn is objective
            return [Result(t.trial_id, objective_fn(t.config.values), reported_cost, t.fidelity)
                    for t in trials]

        def execute(self, trial, objective_fn):
            self.calls.append(("single", trial.trial_id))
            assert objective_fn is objective
            return Result(trial.trial_id, objective_fn(trial.config.values), reported_cost, trial.fidelity)

        def shutdown(self):
            self.calls.append("shutdown")

    def objective(config):
        return 5. + config["x"]

    executor = Executor()
    study = Study(searcher(), executor, objective, budget=3, max_concurrent=2,
                  study_name="endpoint")
    result = study.run()
    assert executor.calls == [("batch", ["endpoint_trial_0", "endpoint_trial_1"]),
                              ("single", "endpoint_trial_2"), "shutdown"]
    assert result.status == "completed" and result.reason is None
    assert result.n_trials == 3 and result.total_cost == 3 * reported_cost
    assert result.total_elapsed_seconds == 0.
    assert [row.trial_id for row in result.history] == [f"endpoint_trial_{i}" for i in range(3)]
    for row in result.history:
        assert row.cost == reported_cost
        assert row.objective_value == objective(study.trials[row.trial_id].config.values)
        assert row.metadata == {"execution": {"elapsed_seconds": 0.}}


def test_cancel_during_endpoint_execution_retains_cost_but_never_an_incumbent(tmp_path):
    def objective(config, trial_id):
        study.cancel_trial(trial_id)
        return {"value": 7., "cost": 3.}

    study = Study(searcher(), LocalExecutor(), objective, budget=1,
                  study_name="cancel", checkpoint_dir=tmp_path)
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    result = raised.value.result
    assert result.best_config is None and result.best_value is None
    assert result.total_cost == 3. and result.n_trials == 1
    assert result.history[0].status == "cancelled"
    state = json.loads((tmp_path / "cancel_checkpoint.json").read_text())
    assert state["results"]["cancel_trial_0"]["status"] == "cancelled"
    assert state["trials"]["cancel_trial_0"]["status"] == "cancelled"


def test_scheduler_endpoint_reports_bind_evaluation_and_training_completion(tmp_path):
    study = Study(searcher(), LocalExecutor(), lambda config: {"value": 5., "cost": 2.},
                  budget=2, maximize=False, study_name="training", checkpoint_dir=tmp_path,
                  event_log=EventLog(tmp_path / "events.jsonl"),
                  scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2)))
    result = study.run()
    assert result.status == "completed" and result.reason is None
    assert [row.metadata["training_status"] for row in result.history] == [
        "paused", "paused", "completed", "completed"]
    reports = [row for row in map(json.loads, (tmp_path / "events.jsonl").read_text().splitlines())
               if row["event_type"] == "report"]
    assert [row["trial_id"] for row in reports] == [row.trial_id for row in result.history]
    for event, outcome in zip(reports, result.history, strict=True):
        assert event["data"]["root"] == study.trials[outcome.trial_id].root_trial_id
        assert event["data"]["fidelity"] == outcome.fidelity
        assert event["data"]["value"] == 5.


@pytest.mark.parametrize("reported_cost", [0., 3.])
def test_recovery_after_compute_stop_cancels_pending_without_losing_acknowledged_cost(tmp_path, monkeypatch, reported_cost):
    tick = [0.]
    monkeypatch.setattr(reporting, "time", SimpleNamespace(monotonic=lambda: tick[0]))

    class InterruptedAcceptance(LocalExecutor):
        def execute(self, *args, **kwargs):
            super().execute(*args, **kwargs)
            raise KeyboardInterrupt("stopped before acceptance")

    def objective(config, reporter):
        tick[0] = reporter.started + 2.
        reporter(1., 5., cost=reported_cost)
        pytest.fail("The exhausted compute budget must stop training")

    def make(executor, objective_fn):
        return Study(searcher(), executor, objective_fn, budget=1, study_name="stopped",
                     checkpoint_dir=tmp_path, compute_budget_seconds=1.,
                     scheduler=ASHAScheduler(ASHAConfig(r_min=2, r_max=2)))

    interrupted = make(InterruptedAcceptance(), objective)
    with pytest.raises(KeyboardInterrupt, match="stopped before acceptance"):
        interrupted.run()
    checkpoint = tmp_path / "stopped_checkpoint.json"
    state = json.loads(checkpoint.read_text())
    assert state["stop_reason"] == "compute_budget_exhausted"
    assert state["pending"] == ["stopped_trial_0"]
    assert state["live_cost"] == {"stopped_trial_0": reported_cost}

    restored = make(LocalExecutor(), lambda config: pytest.fail("Stopped work was redispatched"))
    restored.load_checkpoint(checkpoint)
    with pytest.raises(IncompleteStudyError) as raised:
        restored.run()
    result = raised.value.result
    assert result.status == "incomplete" and result.reason == "compute_budget_exhausted"
    assert result.n_trials == 1 and result.total_cost == reported_cost
    assert result.total_elapsed_seconds == 2.
    row, = result.history
    assert row.trial_id == "stopped_trial_0" and row.fidelity == 2.
    assert math.isnan(row.objective_value)
    assert row.status == "cancelled" and row.metadata["stop_reason"] == "compute_budget_exhausted"
    if reported_cost:
        assert row.metadata["execution"]["accounting"] == "lower_bound_after_interruption"
    state = json.loads(checkpoint.read_text())
    assert state["pending"] == [] and state["live_cost"] == {} and state["live_elapsed"] == {}
    assert state["scheduler_state"]["terminal"] == {"stopped_trial_0": "cancelled"}
