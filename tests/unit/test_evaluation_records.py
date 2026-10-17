"""Prospective public evaluation diagnostics, checkpoint and execution records."""

import math
from unittest.mock import patch

import pytest

from hponas.executors.base import evaluate_trial
from hponas.executors.reporting import ReportDecision
from hponas.types import Config, Trial


def trial(**options):
    return Trial(Config({"x": .5}), "child", seed=19, fidelity=4., **options)


@pytest.mark.parametrize("case,message", [
    ("mode", "Unknown trial continuation mode"),
    ("checkpoint", "Resumed evaluation requires a checkpoint"),
    ("signature", "Resumed objective must declare checkpoint and resume_from"),
])
def test_pre_execution_refusal_has_precise_error_and_no_streaming_record(case, message):
    target = trial(continuation="invalid" if case == "mode" else "resume",
                   resume_from=2., checkpoint={"step": 2} if case == "signature" else None)
    calls = []

    def objective(config):
        calls.append(config)
        return 1.

    result = evaluate_trial(target, objective)
    assert result.status == target.status == "failed"
    assert math.isnan(result.objective_value)
    assert result.metadata["error"] == message
    assert set(result.metadata) == {"error", "traceback", "execution"}
    assert result.metadata['execution']['mode'] == 'endpoint'
    assert "ValueError" in result.metadata["traceback"]
    assert not calls


@pytest.mark.parametrize("root", [None, "root-17"])
def test_root_context_and_final_checkpoint_are_preserved(root):
    target = trial(root_trial_id=root)
    expected = {"step": 4, "weights": [.25, .75]}

    def objective(config, *, root_trial_id, trial_id, fidelity, seed):
        assert (root_trial_id, trial_id, fidelity, seed) == (root or "child", "child", 4., 19)
        return {"value": .7, "cost": 2., "checkpoint": expected, "metadata": {"owner": "objective"}}

    result = evaluate_trial(target, objective)
    assert result.status == "completed" and result.cost == 2.
    assert result.metadata == {"checkpoint": expected, "owner": "objective", 'execution': result.metadata['execution']}
    assert result.metadata['execution']['elapsed_seconds'] >= 0


def test_nonserializable_final_checkpoint_cannot_be_reported_as_completed():
    result = evaluate_trial(trial(), lambda config: {"value": .7, "checkpoint": {"bad": math.nan}})
    assert result.status == "failed" and math.isnan(result.objective_value)
    assert "ValueError" in result.metadata["traceback"]


@pytest.mark.parametrize("cost", [-1., math.nan, math.inf])
def test_invalid_cost_preserves_exact_diagnostic(cost):
    result = evaluate_trial(trial(), lambda config: {"value": .7, "cost": cost})
    assert result.status == "failed"
    assert result.metadata["error"] == "Objective cost must be finite and nonnegative"


@pytest.mark.parametrize("case,message", [
    ("empty", "Streamed objective returned before reporting its assigned endpoint"),
    ("partial", "Streamed objective returned before reporting its assigned endpoint"),
    ("cost", "Final cost cannot discard reported evaluation work"),
    ("value", "Final value conflicts with the reported endpoint"),
])
def test_streaming_refusal_retains_progress_and_exact_diagnostics(case, message):
    def objective(config, reporter):
        if case != "empty":
            reporter(2. if case == "partial" else 4., .5, cost=3., checkpoint={"step": 2})
        return {"value": .7 if case == "value" else .5, "cost": 2. if case == "cost" else 3.}

    with patch("time.monotonic", return_value=10.):
        result = evaluate_trial(trial(), objective)
    assert result.status == "failed" and math.isnan(result.objective_value)
    assert result.metadata["error"] == message
    assert result.metadata["execution"] == {
        "schema_version": 1, "mode": "streaming", "continuation": "restart",
        "resume_from": 0., "elapsed_seconds": 0.,
        "last_step": None if case == "empty" else 2. if case == "partial" else 4.,
        "accounting": "measured", "duration_scope": "objective_call",
    }
    if case != "empty":
        assert result.cost == 3.
        assert result.metadata["checkpoint"] == {"step": 2}
    else:
        assert "checkpoint" not in result.metadata


@pytest.mark.parametrize("final_checkpoint", [False, True])
@pytest.mark.parametrize("mode", ["restart", "resume"])
@pytest.mark.parametrize("callback", [False, True])
def test_completed_stream_retains_exact_execution_record_and_checkpoint_precedence(final_checkpoint, mode, callback):
    target = trial(continuation=mode, resume_from=2. if mode == "resume" else 0., checkpoint={"saved": 2})

    def objective(config, reporter, checkpoint, resume_from):
        assert checkpoint == {"saved": 2}
        assert resume_from == target.resume_from
        reporter(4., .5, cost=3., checkpoint={"progress": 4})
        output = {"value": .5, "cost": 3.}
        if final_checkpoint:
            output["checkpoint"] = {"final": 4}
        return output

    with patch("time.monotonic", return_value=10.):
        result = evaluate_trial(target, objective, (lambda report: ReportDecision()) if callback else None)
    assert result.status == "completed"
    assert result.metadata == {
        "checkpoint": {"final": 4} if final_checkpoint else {"progress": 4},
        "execution": {"schema_version": 1, "mode": "streaming", "continuation": mode,
                      "accounting": "measured", "duration_scope": "objective_call",
                      "resume_from": target.resume_from, "elapsed_seconds": 0., "last_step": 4.},
    }


@pytest.mark.parametrize('callback', [False, True])
def test_endpoint_without_reports_does_not_invent_a_checkpoint(callback):
    calls = []

    def on_report(report):
        calls.append(report)
        return ReportDecision()

    result = evaluate_trial(trial(), lambda config: 1., on_report if callback else None)
    assert result.status == 'completed' and result.objective_value == 1.
    assert result.metadata['execution']['mode'] == 'endpoint'
    assert result.metadata['execution']['last_step'] is None
    assert 'checkpoint' not in result.metadata
    assert calls == []


@pytest.mark.parametrize("action,status", [("pause", "paused"), ("stop", "pruned"), ("cancel", "cancelled")])
def test_halted_result_has_only_public_checkpoint_reason_and_execution_keys(action, status):
    def objective(config, reporter):
        reporter(2., .6, cost=1., checkpoint={"progress": 2})
        raise AssertionError("Cooperative stop must exit the objective")

    with patch("time.monotonic", return_value=10.):
        result = evaluate_trial(trial(), objective, lambda report: ReportDecision(action, "boundary"))
    assert result.status == status and result.cost == 1. and result.objective_value == .6
    assert result.metadata == {
        "checkpoint": {"progress": 2}, "stop_reason": "boundary",
        "execution": {"schema_version": 1, "mode": "streaming", "continuation": "restart",
                      "accounting": "measured", "duration_scope": "objective_call",
                      "resume_from": 0., "elapsed_seconds": 0., "last_step": 2.},
    }
