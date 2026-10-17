"""Cluster-free Ray controller contracts, included in the V03 test selection.

Use the real executor and objective wrapper with a small transport double. Live
worker/process conformance remains in test_ray_executor_tier0.py; this suite makes
driver retry, ordering, ownership and accounting branches mutation-testable.
"""

from types import SimpleNamespace
import math
import sys
import threading
import time

import pytest

import hponas.executors.ray_executor as module
from hponas.executors.ray_executor import RayExecutor
from hponas.types import Config, Result, Trial


class RayError(Exception):
    pass


class GetTimeoutError(RayError):
    pass


class Transport:
    def __init__(self):
        self.initialized = False
        self.init_calls, self.options, self.cancelled, self.get_calls = [], [], [], []
        self.shutdown_calls = 0
        self.exceptions = SimpleNamespace(GetTimeoutError=GetTimeoutError, RayError=RayError)
        self.outcomes = []

    def is_initialized(self):
        return self.initialized

    def init(self, **kwargs):
        self.init_calls.append(kwargs)
        self.initialized = True

    def shutdown(self):
        self.shutdown_calls += 1
        self.initialized = False

    def remote(self, **kwargs):
        self.options.append(kwargs)
        return lambda fn: SimpleNamespace(remote=lambda *args: (fn, args))

    def get(self, future, timeout=None):
        if any(cancelled is future for cancelled, _ in self.cancelled):
            raise RayError("cancelled worker exited")
        self.get_calls.append((future, timeout))
        if self.outcomes:
            result = self.outcomes.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        fn, args = future
        return fn(*args)

    def cancel(self, future, force=False):
        self.cancelled.append((future, force))

    def wait(self, futures, timeout=0):
        return [], futures


@pytest.fixture
def transport(monkeypatch):
    fake = Transport()
    monkeypatch.setitem(sys.modules, "ray", fake)
    return fake


def trial(tid="trial-x", x=3):
    return Trial(config=Config({"x": x}), trial_id=tid, fidelity=0.5, seed=17)


@pytest.mark.parametrize("kwargs", [
    {"num_workers": 0}, {"num_workers": -1}, {"num_workers": 1.5},
    {"num_workers": True}, {"max_retries": -1}, {"max_retries": 1.5},
    {"max_retries": True}, {"timeout": 0}, {"timeout": -1},
    {"timeout": float("nan")}, {"timeout": float("inf")},
])
def test_invalid_limits_rejected_before_any_cluster_use(transport, kwargs):
    with pytest.raises(ValueError):
        RayExecutor(**kwargs)
    assert not transport.init_calls


def test_defaults_custom_limits_and_lazy_initialization(transport):
    default = RayExecutor()
    assert (default.num_workers, default.max_retries, default.timeout) == (4, 3, None)
    assert default.resources_per_trial == {"num_cpus": 1}
    assert not default._ray_initialized and not default._owns_ray
    resources = {"num_cpus": 2, "num_gpus": 0.5}
    custom = RayExecutor(2, resources, 0, 0.75)
    assert (custom.num_workers, custom.max_retries, custom.timeout) == (2, 0, 0.75)
    assert custom.resources_per_trial == resources
    assert not transport.init_calls


def test_single_worker_and_zero_retries_are_valid_boundary_values(transport):
    result = RayExecutor(num_workers=1, max_retries=0).execute(trial(), lambda c: 7)
    assert result.objective_value == 7 and result.is_valid()
    assert transport.init_calls[0]["num_cpus"] == 1


def test_single_trial_progress_callback_can_stop_the_objective(transport, monkeypatch):
    from hponas.executors.base import evaluate_trial
    from hponas.executors.reporting import ReportDecision

    executor = RayExecutor(num_workers=1, max_retries=0)
    # Exercise the public single/batch routing with the shared worker evaluator.
    # The remote transport itself has separate live conformance tests.
    monkeypatch.setattr(executor, "_execute_streaming", evaluate_trial)
    seen, tail = [], []

    def objective(config, reporter):
        reporter(.25, 5, cost=2, checkpoint={"step": .25})
        tail.append("must stop before continuing training")
        reporter(.5, 6, cost=3)
        return {"value": 6, "cost": 3}

    def stop(report):
        seen.append(report)
        return ReportDecision("stop", "quality floor")

    result = executor.execute(trial(), objective, on_report=stop)
    assert len(seen) == 1 and seen[0].trial_id == "trial-x"
    assert seen[0].step == .25 and seen[0].value == 5
    assert not tail
    assert result.status == "pruned" and result.cost == 2
    assert result.metadata["checkpoint"] == {"step": .25}
    assert result.metadata["stop_reason"] == "quality floor"


def test_own_cluster_initializes_once_and_shuts_down(transport):
    ex = RayExecutor(num_workers=2)
    assert ex.execute(trial(), lambda c: c["x"] ** 2).objective_value == 9
    ex.execute(trial("second"), lambda c: 4)
    assert transport.init_calls == [{"ignore_reinit_error": True, "num_cpus": 2, "include_dashboard": False}]
    assert ex._ray_initialized and ex._owns_ray
    ex.shutdown()
    ex.shutdown()
    assert transport.shutdown_calls == 1
    assert not ex._ray_initialized


def test_existing_cluster_is_neither_reinitialized_nor_shut_down(transport):
    transport.initialized = True
    ex = RayExecutor()
    ex.execute(trial(), lambda c: 1)
    assert ex._ray_initialized and not ex._owns_ray
    assert transport.init_calls == []
    ex.shutdown()
    assert transport.shutdown_calls == 0
    assert transport.initialized
    assert not ex._ray_initialized


def test_missing_ray_reports_installation_requirement(monkeypatch):
    monkeypatch.setitem(sys.modules, "ray", None)
    ex = RayExecutor()
    with pytest.raises(ImportError, match="Ray is not installed"):
        ex.execute(trial(), lambda c: 1)
    assert not ex._ray_initialized


def test_cluster_initialization_failure_is_not_silently_marked_ready(transport, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("cluster unavailable")
    monkeypatch.setattr(transport, "init", fail)
    ex = RayExecutor()
    with pytest.raises(RuntimeError, match="unavailable"):
        ex.execute(trial(), lambda c: 1)
    assert not ex._ray_initialized and not ex._owns_ray


def test_shutdown_failure_still_clears_initialized_flag(transport, monkeypatch):
    ex = RayExecutor()
    ex.execute(trial(), lambda c: 1)
    monkeypatch.setattr(transport, "shutdown", lambda: (_ for _ in ()).throw(RuntimeError("gone")))
    ex.shutdown()
    assert not ex._ray_initialized


def test_remote_resource_policy_and_objective_context_are_preserved(transport):
    ex = RayExecutor(num_workers=2, resources_per_trial={"num_cpus": 2, "num_gpus": 0.25, "max_retries": 99})
    received = []

    def objective(config, fidelity, seed, trial_id):
        received.append((config, fidelity, seed, trial_id))
        return {"value": 7.5, "cost": 2.5, "metadata": {"metric": "reward"}}

    result = ex.execute(trial(), objective)
    assert received == [({"x": 3}, 0.5, 17, "trial-x")]
    assert transport.options == [{"num_cpus": 2, "num_gpus": 0.25, "max_retries": 0, "retry_exceptions": False}]
    assert (result.trial_id, result.objective_value, result.fidelity, result.cost) == ("trial-x", 7.5, 0.5, 2.5)
    assert result.status == "completed"
    assert result.metadata["metric"] == "reward"
    assert result.metadata["attempts"] == 1
    assert result.metadata["failed_attempt_elapsed_seconds"] == 0


def test_objective_failure_is_not_retried(transport):
    calls = []
    def fail(config):
        calls.append(config)
        raise ValueError("bad input")
    result = RayExecutor(max_retries=3).execute(trial(), fail)
    assert result.status == "failed" and not result.is_valid()
    assert "bad input" in result.metadata["error"]
    assert result.metadata["attempts"] == 1
    assert len(calls) == len(transport.get_calls) == len(transport.options) == 1


@pytest.mark.parametrize("failure,status", [(GetTimeoutError("deadline"), "timeout"), (RuntimeError("worker died"), "failed")])
@pytest.mark.parametrize("max_retries", [0, 2])
def test_retry_exhaustion_counts_attempts_cost_and_cancels_timeouts(transport, monkeypatch, failure, status, max_retries):
    transport.outcomes = [failure] * (max_retries + 1)
    stamps = iter(range(2 * (max_retries + 1)))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(stamps)))
    ex = RayExecutor(max_retries=max_retries, timeout=0.25)
    result = ex.execute(trial(), lambda c: 9)
    assert result.status == status and not result.is_valid()
    assert result.trial_id == "trial-x" and result.fidelity == 0.5
    assert math.isnan(result.objective_value)
    assert result.cost == max_retries + 1
    assert result.metadata["attempts"] == max_retries + 1
    assert len(transport.options) == len(transport.get_calls) == max_retries + 1
    assert all(timeout == 0.25 for _, timeout in transport.get_calls)
    if status == "timeout":
        assert transport.cancelled == [(future, True) for future, _ in transport.get_calls]
        assert "0.25" in result.metadata["error"]
    else:
        assert not transport.cancelled
        assert result.metadata["error"] == "worker died"


def test_mixed_infrastructure_failures_recover_without_losing_cost(transport, monkeypatch):
    transport.outcomes = [GetTimeoutError(), RuntimeError("worker died"),
                          {"objective_value": 8, "cost": 0.75, "fidelity": 0.5, "status": "completed", "metadata": {"user": "value"}}]
    stamps = iter([10, 12, 20, 23, 30])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(stamps)))
    result = RayExecutor(max_retries=2, timeout=4).execute(trial(), lambda c: 9)
    assert result.is_valid() and result.objective_value == 8
    assert result.cost == 5.75
    assert result.metadata == {"user": "value", "attempts": 3, "failed_attempt_elapsed_seconds": 5.0}
    assert len(transport.cancelled) == 1
    assert len(transport.options) == 3


def test_retry_executes_original_objective_and_context(transport, monkeypatch):
    # Success is produced by the actual submitted objective, not a canned payload.
    # This catches accidentally dropping the callback on either retry boundary.
    transport.outcomes = [RuntimeError("first worker died")]
    stamps = iter([10, 12, 20])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(stamps)))
    received = []

    def objective(config, fidelity, seed, trial_id):
        received.append((config, fidelity, seed, trial_id))
        return {"value": 11, "cost": 0.75}

    result = RayExecutor(max_retries=1).execute(trial(), objective)
    assert received == [({"x": 3}, 0.5, 17, "trial-x")]
    assert result.is_valid() and result.objective_value == 11
    assert result.cost == 2.75 and result.metadata["attempts"] == 2


def test_payload_fields_defaults_and_passthrough(transport):
    ex = RayExecutor()
    t = trial()
    default = ex._payload_to_result(t, {})
    assert default.trial_id == t.trial_id and default.fidelity == t.fidelity
    assert default.cost == 0 and default.status == "failed" and not default.is_valid()
    assert default.metadata == {}
    full = ex._payload_to_result(t, {"trial_id": "reported", "objective_value": "3.5", "cost": 9.25, "fidelity": 0.75, "status": "completed", "metadata": {"a": 1}})
    assert (full.trial_id, full.objective_value, full.cost, full.fidelity, full.status, full.metadata) == ("reported", 3.5, 9.25, 0.75, "completed", {"a": 1})
    existing = Result("ready", 4.0, cost=2.0)
    assert ex._payload_to_result(t, existing) is existing


def test_batch_bounds_active_work_and_preserves_dispatch_order(transport):
    active, peak = 0, 0
    lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=3)
    completions = []

    def objective(config):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait()
            if config["x"] % 2 == 0:
                time.sleep(0.01)
            completions.append(config["x"])
            return {"value": config["x"], "cost": 0.5}
        finally:
            with lock:
                active -= 1

    results = RayExecutor(num_workers=2, max_retries=0).execute_batch([trial(str(i), i) for i in range(6)], objective)
    assert peak == 2 and active == 0
    assert [r.objective_value for r in results] == list(range(6))
    assert [r.trial_id for r in results] == [str(i) for i in range(6)]
    assert all(r.cost == 0.5 and r.is_valid() for r in results)
    assert completions != list(range(6))


def test_empty_batch_does_not_submit_work(transport):
    assert RayExecutor().execute_batch([], lambda c: 1) == []
    assert transport.options == [] and transport.get_calls == []
