"""Evaluation envelopes and process lifecycle without scheduler or GP fitting."""

import math
from types import SimpleNamespace

import cloudpickle
import pytest

from hponas.executors.base import evaluate_trial
import hponas.executors.local_executor as local
from hponas.types import Config, Result, Trial


def make_trial():
    return Trial(Config({"x": 3.0}), "context-trial", seed=17, fidelity=4.0)


def test_workload_envelope_preserves_context_metadata_cost_and_artifacts():
    trial = make_trial()
    metadata = {"metric": [1, 2], "artifacts": {"old": "old.bin"}}

    def objective(config, fidelity, seed, trial_id):
        assert trial.status == "running"
        assert (config, fidelity, seed, trial_id) == (
            {"x": 3.0},
            4.0,
            17,
            "context-trial",
        )
        return {
            "value": "6.5",
            "cost": "2.75",
            "metadata": metadata,
            "artifacts": {"model": "best.pt"},
        }

    result = evaluate_trial(trial, objective)
    assert result == Result(
        "context-trial",
        6.5,
        2.75,
        4.0,
        {"metric": [1, 2], "artifacts": {"model": "best.pt"}, 'execution': result.metadata['execution']},
    )
    assert trial.status == "completed"
    assert metadata["artifacts"] == {"old": "old.bin"}


def test_only_declared_keyword_context_is_injected(monkeypatch):
    ticks = iter([10.0, 12.5, 12.5])
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    trial = make_trial()

    def objective(config, fidelity=9.0, /, *, seed=0, **kwargs):
        assert fidelity == 9.0  # Positional-only parameters cannot receive a keyword.
        assert seed == 17
        assert kwargs == {}
        return config["x"]

    result = evaluate_trial(trial, objective)
    assert result == Result("context-trial", 3.0, 2.5, 4.0, {'execution': result.metadata['execution']})
    assert result.metadata['execution']['elapsed_seconds'] == 2.5


@pytest.mark.parametrize("cost", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_workload_cost_is_a_failed_result(cost):
    trial = make_trial()
    result = evaluate_trial(trial, lambda c: {"value": 1.0, "cost": cost})
    assert result.status == trial.status == "failed"
    assert math.isnan(result.objective_value)
    assert result.cost >= 0 and math.isfinite(result.cost)
    assert "cost" in result.metadata["error"].lower()
    assert "ValueError" in result.metadata["traceback"]


@pytest.mark.parametrize(
    "value,status",
    [(float("nan"), "nan"), (float("inf"), "inf"), (-float("inf"), "inf")],
)
def test_nonfinite_workload_value_keeps_cost_and_metadata(value, status):
    trial = make_trial()
    result = evaluate_trial(
        trial, lambda c: {"value": value, "cost": 0.0, "metadata": {"step": 2}}
    )
    assert result.status == trial.status == status
    assert not result.is_valid()
    assert result.cost == 0.0 and result.fidelity == 4.0
    assert result.metadata['step'] == 2
    assert result.metadata['execution']['elapsed_seconds'] >= 0
    assert set(result.metadata) == {'step', 'execution'}


@pytest.mark.parametrize(
    "error,status",
    [(TimeoutError("deadline"), "timeout"), (RuntimeError("objective bug"), "failed")],
)
def test_objective_failures_return_diagnostics_and_update_trial(error, status):
    trial = make_trial()

    def objective(config):
        raise error

    result = evaluate_trial(trial, objective)
    assert result.status == trial.status == status
    assert result.trial_id == trial.trial_id and result.fidelity == 4.0
    assert math.isnan(result.objective_value)
    assert result.metadata["error"] == str(error)
    assert type(error).__name__ in result.metadata["traceback"]


class Channel:
    def __init__(self, result=None, ready=True):
        self.result, self.ready = result, ready
        self.closed = False
        self.waits = []

    def poll(self, timeout):
        self.waits.append(timeout)
        return self.ready

    def recv(self):
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def send(self, result):
        self.result = result

    def close(self):
        self.closed = True


class Worker:
    def __init__(self, alive=False, stubborn=False, start_error=None):
        self.alive, self.stubborn, self.start_error = alive, stubborn, start_error
        self.started = self.terminated = self.killed = False
        self.joins = []

    def start(self):
        if self.start_error:
            raise self.start_error
        self.started = True

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = self.stubborn

    def join(self, timeout=None):
        self.joins.append(timeout)

    def kill(self):
        self.killed = True
        self.alive = False


def install_worker(monkeypatch, receive, worker):
    send = Channel()
    calls = {}

    def pipe(duplex):
        assert duplex is False
        return receive, send

    def process(**kwargs):
        calls.update(kwargs)
        return worker

    def context(method):
        assert method == "spawn"
        return SimpleNamespace(Pipe=pipe, Process=process)

    monkeypatch.setattr(local.multiprocessing, "get_context", context)
    monkeypatch.setattr(local.time, "monotonic", lambda: 10.0)
    return send, calls


@pytest.mark.parametrize("outcome", ["completed", "eof", "deadline"])
def test_isolated_result_timeout_and_worker_exit_cleanup(monkeypatch, outcome):
    trial = make_trial()
    expected = Result(
        trial.trial_id, 7.0, cost=3.0, fidelity=4.0, metadata={"worker": 1}
    )
    receive = Channel(
        EOFError() if outcome == "eof" else expected, ready=outcome != "deadline"
    )
    worker = Worker(alive=outcome == "deadline", stubborn=outcome == "deadline")
    send, calls = install_worker(monkeypatch, receive, worker)
    executor = local.LocalExecutor(timeout=2.0)
    result = executor.execute(trial, lambda c: c["x"])
    restored_trial, objective = cloudpickle.loads(calls["args"][0])
    assert restored_trial.trial_id == trial.trial_id
    assert objective(restored_trial.config.values) == 3.0
    assert calls["target"] is local._isolated_evaluation
    assert calls["args"][1] is send
    assert receive.waits == [2.0]
    assert worker.started and receive.closed and send.closed
    assert result.trial_id == trial.trial_id and result.fidelity == 4.0
    assert trial.status == result.status
    if outcome == "completed":
        assert result == expected
        assert worker.joins == [1] and not worker.terminated
    else:
        assert math.isnan(result.objective_value)
        assert result.status == ("failed" if outcome == "eof" else "timeout")
        assert result.cost == 0.0
        assert result.metadata["error"]
        if outcome == "deadline":
            assert worker.terminated and worker.killed and worker.joins == [1, None]


def test_failed_worker_start_closes_both_pipe_ends(monkeypatch):
    receive = Channel()
    worker = Worker(start_error=OSError("process creation failed"))
    send, _ = install_worker(monkeypatch, receive, worker)
    with pytest.raises(OSError, match="process creation"):
        local.LocalExecutor(timeout=2.0).execute(make_trial(), lambda c: 1.0)
    assert receive.closed and send.closed
    assert not worker.terminated and not worker.joins


def test_isolated_worker_decodes_objective_and_closes_channel_on_success_and_failure():
    channel = Channel()
    local._isolated_evaluation(
        cloudpickle.dumps((make_trial(), lambda c: c["x"] + 2)), channel
    )
    assert channel.closed and channel.result.is_valid()
    assert channel.result.objective_value == 5.0 and channel.result.fidelity == 4.0
    invalid = Channel()
    with pytest.raises(Exception):
        local._isolated_evaluation(b"invalid pickle", invalid)
    assert invalid.closed


def test_boolean_worker_limit_is_rejected():
    with pytest.raises(ValueError, match="max_workers"):
        local.LocalExecutor(max_workers=True)


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_deadlines_are_rejected(timeout):
    with pytest.raises(ValueError, match="(?i)timeout"):
        local.LocalExecutor(timeout=timeout)


def test_subsecond_deadlines_and_single_worker_are_valid():
    executor = local.LocalExecutor(max_workers=1, timeout=0.25)
    assert executor.max_workers == 1 and executor.timeout == 0.25


@pytest.mark.parametrize("fails", [False, True])
def test_missing_cost_and_failure_cost_measure_elapsed_time(monkeypatch, fails):
    clock = iter([20.0, 20.75, 20.75])
    monkeypatch.setattr("time.monotonic", lambda: next(clock))

    def objective(config):
        if fails:
            raise RuntimeError("failure")
        return {"value": 3.0}

    result = evaluate_trial(make_trial(), objective)
    assert result.status == ("failed" if fails else "completed")
    assert result.cost == 0.75
    if not fails:
        assert set(result.metadata) == {'execution'}
        assert result.metadata['execution']['accounting'] == 'measured'


@pytest.mark.parametrize("startup,remaining", [(1.5, 0.5), (2.5, 0.0)])
def test_worker_startup_consumes_deadline_and_never_waits_past_it(
    monkeypatch, startup, remaining
):
    receive = Channel(ready=False)
    worker = Worker(alive=True)
    send, _ = install_worker(monkeypatch, receive, worker)
    clock = iter([10.0, 10.0 + startup, 10.0 + startup, 10.0 + startup])
    monkeypatch.setattr(local.time, "monotonic", lambda: next(clock))
    result = local.LocalExecutor(timeout=2.0).execute(make_trial(), lambda c: 1.0)
    assert receive.waits == [remaining]
    assert result.cost == startup and result.status == "timeout"
    assert result.metadata['execution']['censor_cause'] == 'external_deadline'
    assert result.metadata['execution']['elapsed_seconds'] == startup
    assert receive.closed and send.closed and worker.terminated


def test_dispatch_after_async_shutdown_has_useful_error():
    executor = local.LocalExecutor(mode="async")
    executor.shutdown()
    with pytest.raises(RuntimeError, match="(?i)thread pool"):
        executor.execute_async(make_trial(), lambda c: 1.0)
