"""Deterministic worker faults: deadline, accounting, messages and cleanup."""

from collections import deque
from dataclasses import replace
import math
from types import SimpleNamespace

import cloudpickle
import pytest

import hponas.executors.local_executor as local
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.types import Config, Result, Trial


class Endpoint:
    def __init__(self, clock, messages=()):
        self.clock, self.messages = clock, deque(messages)
        self.closed, self.sent, self.waits = False, [], []

    def poll(self, timeout):
        assert timeout is not None and timeout > 0
        self.waits.append(timeout)
        self.clock.value += .25 if self.messages else timeout
        return bool(self.messages)

    def recv(self):
        value = self.messages.popleft()
        if isinstance(value, Exception):
            raise value
        return value

    def send(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True


def environment(monkeypatch, messages, *, startup=0, stubborn=False, start_error=False):
    clock = SimpleNamespace(value=100.)
    parent, child = Endpoint(clock, messages), Endpoint(clock)
    worker = SimpleNamespace(pid=None, alive=False, joins=[], terminated=False, killed=False)
    calls = {}

    def start():
        if start_error:
            raise OSError("process startup failed")
        worker.pid, worker.alive = 123, True
        clock.value += startup

    def terminate():
        worker.terminated, worker.alive = True, stubborn

    def kill():
        worker.killed, worker.alive = True, False

    worker.start, worker.terminate, worker.kill = start, terminate, kill
    worker.is_alive = lambda: worker.alive
    worker.join = lambda timeout=None: worker.joins.append(timeout)

    def process(**kwargs):
        calls.update(kwargs)
        return worker

    def pipe(duplex):
        assert duplex is True
        return parent, child

    def context(method):
        assert method == "spawn"
        return SimpleNamespace(Pipe=pipe, Process=process)

    monkeypatch.setattr(local.multiprocessing, "get_context", context)
    monkeypatch.setattr(local.time, "monotonic", lambda: clock.value)
    return clock, parent, child, worker, calls


@pytest.mark.parametrize("outcome", ["result", "eof", "timeout"])
@pytest.mark.parametrize("progress", [False, True])
def test_streaming_result_or_failure_retains_cost_context_and_closes_worker(monkeypatch, outcome, progress):
    trial = Trial(Config({"x": 3}), "child", fidelity=4, root_trial_id="root",
                  continuation="resume", resume_from=1, checkpoint={"step": 1})
    report = ProgressReport("child", "root", 2., 7., 9., 88., {"step": 2})
    final = Result("child", 6., 10., 4., {"execution": {"mode": "streaming"}})
    messages = [("progress", report)] if progress else []
    messages += [("result", final)] if outcome == "result" else [EOFError()] if outcome == "eof" else []
    clock, parent, child, worker, calls = environment(monkeypatch, messages, stubborn=True)
    received = []
    decision = ReportDecision("continue", "checked")
    result = local.LocalExecutor(timeout=2.).execute(
        trial, lambda c: c["x"], on_report=lambda r: received.append(r) or decision)
    assert calls["target"] is local._isolated_streaming_evaluation
    sent_trial, objective = cloudpickle.loads(calls["args"][0])
    assert (sent_trial.trial_id, sent_trial.fidelity, sent_trial.continuation,
            sent_trial.resume_from, sent_trial.checkpoint) == ("child", 4, "resume", 1, {"step": 1})
    assert objective(sent_trial.config.values) == 3 and calls["args"][1] is child
    assert parent.closed and child.closed and worker.terminated and worker.killed
    assert worker.joins == [1, None]
    assert parent.waits == ([2., 1.75] if progress else [2.])
    assert received == ([replace(report, elapsed_seconds=.25)] if progress else [])
    assert parent.sent == ([decision] if progress else [])
    assert result.trial_id == "child" and result.fidelity == 4
    assert result.metadata["execution"] == {
        **({"mode": "streaming"} if outcome == "result" else {}),
        **({'censor_cause': 'external_deadline', 'deadline_seconds': 2.} if outcome == 'timeout' else {}),
        "schema_version": 1, "elapsed_seconds": clock.value - 100,
        "continuation": "resume", "resume_from": 1,
        "duration_scope": "worker_including_startup", "accounting": "measured",
    }
    if outcome == "result":
        assert result is final and result.objective_value == 6 and result.cost == 10
        assert result.status == trial.status == "completed"
    else:
        assert math.isnan(result.objective_value)
        assert result.cost == (9. if progress else 2. if outcome == "timeout" else .25)
        assert result.status == trial.status == ("failed" if outcome == "eof" else "timeout")
        assert result.metadata["error"] == ("Objective worker exited without a result" if outcome == "eof" else "Deadline of 2.0s exceeded")


@pytest.mark.parametrize("startup", [1.5, 2., 2.5])
def test_startup_consumes_deadline_and_exact_expiry_never_polls(monkeypatch, startup):
    final = Result("trial", 1, 1, 4)
    clock, parent, child, worker, _ = environment(monkeypatch, [("result", final)], startup=startup)
    trial = Trial(Config({}), "trial", fidelity=4)
    result = local.LocalExecutor(timeout=2).execute(trial, lambda _: 1, on_report=lambda _: ReportDecision())
    assert parent.waits == ([.5] if startup < 2 else [])
    assert result.status == ("completed" if startup < 2 else "timeout")
    assert parent.closed and child.closed and worker.terminated and not worker.killed
    assert worker.joins == [1]


@pytest.mark.parametrize("fault,message", [("startup", "process startup failed"),
                                         ("protocol", "Unknown worker message"),
                                         ("callback", "scheduler failed")])
def test_exception_closes_both_channels_and_reaps_only_a_started_worker(monkeypatch, fault, message):
    report = ProgressReport("trial", "trial", 1, 2, 3, 4)
    messages = [("alien", None)] if fault == "protocol" else [("progress", report)]
    _, parent, child, worker, _ = environment(monkeypatch, messages, start_error=fault == "startup")

    def callback(_):
        raise RuntimeError("scheduler failed")

    with pytest.raises((OSError, ValueError, RuntimeError)) as exc:
        local.LocalExecutor(timeout=2).execute(Trial(Config({}), "trial", fidelity=4), lambda _: 1, on_report=callback)
    assert str(exc.value) == message
    assert parent.closed and child.closed
    assert worker.joins == ([] if fault == "startup" else [1])
