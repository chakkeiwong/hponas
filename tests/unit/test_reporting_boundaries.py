"""Observable reporting boundaries, default accounting and control propagation."""

import pytest

from hponas.executors.reporting import ProgressReport, ReportDecision, TrialHalted, TrialReporter
from hponas.types import Config, Trial


def reporter(monkeypatch, callback=None):
    monkeypatch.setattr("hponas.executors.reporting.time.monotonic", lambda: 103.25)
    trial = Trial(Config({}), "child", fidelity=4, root_trial_id="root", resume_from=1)
    return TrialReporter(trial, callback, 100)


def test_default_cost_and_callback_receive_the_complete_report(monkeypatch):
    received = []
    target = reporter(monkeypatch, lambda row: received.append(row) or "continue")
    checkpoint = {"weights": [1, 2]}
    assert target(2, 7, checkpoint=checkpoint) == ReportDecision()
    assert received == [ProgressReport("child", "root", 2., 7., 3.25, 3.25, checkpoint)]
    assert target.last == received[0]


@pytest.mark.parametrize("cost", [0, 0.25])
def test_endpoint_and_equal_progress_allow_zero_or_small_cost(monkeypatch, cost):
    target = reporter(monkeypatch)
    assert target(4, 7, cost=cost) == ReportDecision()
    assert target(4, 7, cost=cost) == ReportDecision()
    assert target.last.step == 4 and target.last.cost == cost


@pytest.mark.parametrize("field", ["step", "value", "cost"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_reports_refuse_before_callback_or_state_change(monkeypatch, field, value):
    target = reporter(monkeypatch, lambda _: pytest.fail("invalid progress reached callback"))
    args = {"step": 2, "value": 7, "cost": 1, field: value}
    with pytest.raises(ValueError) as exc:
        target(**args)
    assert str(exc.value) == "Progress step, value and cost must be finite"
    assert target.last is None


@pytest.mark.parametrize("step,cost", [(1, 0), (0.9, 1), (4.1, 1), (2, -0.1)])
def test_assigned_fidelity_and_nonnegative_cost_are_independent_constraints(monkeypatch, step, cost):
    target = reporter(monkeypatch)
    with pytest.raises(ValueError) as exc:
        target(step, 7, cost=cost)
    assert str(exc.value) == "Progress outside assigned fidelity or negative cost"
    assert target.last is None


@pytest.mark.parametrize("step,cost", [(1.5, 3), (3, 1)])
def test_step_or_cost_regression_preserves_the_last_report(monkeypatch, step, cost):
    target = reporter(monkeypatch)
    target(2, 7, cost=2)
    previous = target.last
    with pytest.raises(ValueError) as exc:
        target(step, 7, cost=cost)
    assert str(exc.value) == "Progress step and cumulative evaluation cost must not decrease"
    assert target.last is previous


@pytest.mark.parametrize("action", ["pause", "stop", "cancel"])
def test_repeated_halt_preserves_the_same_decision_without_reinvoking_callback(monkeypatch, action):
    decision = ReportDecision(action, "budget exhausted")
    calls = []
    target = reporter(monkeypatch, lambda r: calls.append(r) or decision)
    for step in [2, 3]:
        with pytest.raises(TrialHalted) as exc:
            target(step, 7, cost=1)
        assert exc.value.decision is decision
    assert len(calls) == 1 and target.last is calls[0]


def test_callback_result_must_be_a_decision(monkeypatch):
    target = reporter(monkeypatch, lambda _: None)
    with pytest.raises(TypeError) as exc:
        target(2, 7, cost=1)
    assert str(exc.value) == "Progress callback must return a ReportDecision"


@pytest.mark.parametrize("checkpoint", [{"weights": float("nan")}, {"model": object()}])
def test_checkpoint_is_durable_json_before_report_is_delivered(monkeypatch, checkpoint):
    target = reporter(monkeypatch, lambda _: pytest.fail("Invalid checkpoint reached scheduler"))
    with pytest.raises((ValueError, TypeError)):
        target(2, 7, cost=1, checkpoint=checkpoint)
    assert target.last is None
