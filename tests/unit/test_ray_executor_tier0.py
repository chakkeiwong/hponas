"""Unit tests for RayExecutor.

Tests for hponas/executors/ray_executor.py - Phase 1 Day 3
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 1, BUILD_PROGRAM_v3.md lines 123-147

Ray is slow to start, so a single module-scoped cluster is shared by all tests.
"""

import sys
import time

import numpy as np
import pytest

from hponas.executors.ray_executor import RayExecutor
from hponas.types import Config, Result, Trial

ray = pytest.importorskip("ray", reason="Ray not installed")

# Ray workers cannot import this pytest module by name, so the default
# serialize-by-reference fails for module-level objective functions.
# Registering the module forces serialization by value. Ray vendors its own
# cloudpickle, so it must be registered there rather than on the standalone one.
ray.cloudpickle.register_pickle_by_value(sys.modules[__name__])


def _trial(trial_id: str = "trial_0", x: float = 3.0, fidelity: float = 1.0) -> Trial:
    """Build a single-parameter trial."""
    return Trial(
        config=Config(values={"x": x}),
        trial_id=trial_id,
        fidelity=fidelity,
        status="pending",
    )


def square(config: dict) -> float:
    """Simple objective: x squared."""
    return config["x"] ** 2


@pytest.fixture(scope="module")
def executor():
    """Module-scoped Ray executor (cluster startup is expensive)."""
    ex = RayExecutor(num_workers=2)
    yield ex
    ex.shutdown()


class TestRayExecutorInitialization:
    """Tests for RayExecutor initialization."""

    def test_defaults(self):
        """Test default configuration."""
        ex = RayExecutor()
        assert ex.num_workers == 4
        assert ex.resources_per_trial == {"num_cpus": 1}
        assert ex.max_retries == 3
        assert ex.timeout is None
        assert ex._ray_initialized is False

    def test_custom_params(self):
        """Test custom configuration."""
        ex = RayExecutor(
            num_workers=8,
            resources_per_trial={"num_cpus": 2, "num_gpus": 1},
            max_retries=5,
            timeout=30.0,
        )
        assert ex.num_workers == 8
        assert ex.resources_per_trial == {"num_cpus": 2, "num_gpus": 1}
        assert ex.max_retries == 5
        assert ex.timeout == 30.0

    def test_ray_not_initialized_until_execute(self):
        """Test Ray cluster is lazily initialized."""
        ex = RayExecutor()
        assert ex._ray_initialized is False


class TestRayExecutorContract:
    """Tests that RayExecutor honours the BaseExecutor contract.

    Regression guard: execute()/execute_batch() previously returned the raw
    dict produced by the remote wrapper, so Study crashed on attribute access.
    """

    def test_execute_returns_result_not_dict(self, executor):
        """Test execute() returns a Result object, not a dict."""
        result = executor.execute(_trial("contract_0"), square)

        assert isinstance(result, Result)
        assert not isinstance(result, dict)

    def test_execute_result_attributes_accessible(self, executor):
        """Test Result attributes are accessible (Study depends on this)."""
        result = executor.execute(_trial("contract_1", x=3.0), square)

        assert result.trial_id == "contract_1"
        assert result.objective_value == 9.0
        assert result.status == "completed"
        assert result.fidelity == 1.0
        assert result.cost >= 0.0

    def test_execute_result_supports_is_valid(self, executor):
        """Test returned Result supports is_valid() used by searchers."""
        result = executor.execute(_trial("contract_2"), square)

        assert result.is_valid() is True

    def test_execute_batch_returns_results(self, executor):
        """Test execute_batch returns Result objects for every trial."""
        trials = [_trial(f"batch_{i}", x=float(i)) for i in range(4)]

        results = executor.execute_batch(trials, square)

        assert len(results) == 4
        assert all(isinstance(r, Result) for r in results)
        assert [r.objective_value for r in results] == [0.0, 1.0, 4.0, 9.0]

    def test_execute_batch_preserves_order(self, executor):
        """Test results come back in submission order."""
        trials = [_trial(f"order_{i}", x=float(i)) for i in range(5)]

        results = executor.execute_batch(trials, square)

        assert [r.trial_id for r in results] == [f"order_{i}" for i in range(5)]


class TestRayExecutorErrorHandling:
    """Tests for error handling."""

    def test_objective_exception_marked_failed(self, executor):
        """Test objective exceptions produce a failed Result."""
        def failing(config):
            raise ValueError("Test error")

        result = executor.execute(_trial("err_0"), failing)

        assert isinstance(result, Result)
        assert result.status == "failed"
        assert np.isnan(result.objective_value)
        assert "Test error" in result.metadata["error"]
        assert "traceback" in result.metadata

    def test_nan_objective_marked_nan(self, executor):
        """Test NaN objective values are flagged."""
        result = executor.execute(_trial("err_1"), lambda c: np.nan)

        assert result.status == "nan"
        assert result.is_valid() is False

    def test_inf_objective_marked_inf(self, executor):
        """Test inf objective values are flagged."""
        result = executor.execute(_trial("err_2"), lambda c: np.inf)

        assert result.status == "inf"
        assert result.is_valid() is False

    def test_failure_does_not_abort_batch(self, executor):
        """Test one failing trial does not prevent others from completing."""
        def sometimes_fails(config):
            if config["x"] == 1.0:
                raise RuntimeError("selective failure")
            return config["x"] ** 2

        trials = [_trial(f"mixed_{i}", x=float(i)) for i in range(4)]
        results = executor.execute_batch(trials, sometimes_fails)

        assert len(results) == 4
        statuses = [r.status for r in results]
        assert statuses.count("failed") == 1
        assert statuses.count("completed") == 3


class TestRayExecutorRetry:
    """Tests for retry behaviour.

    Regression guard: max_retries was previously stored but never used, so
    no retry ever happened.
    """

    def test_timeout_returns_timeout_status(self):
        """Test a trial exceeding timeout yields status='timeout'."""
        ex = RayExecutor(num_workers=1, max_retries=0, timeout=0.5)

        def slow(config):
            time.sleep(30)
            return 1.0

        result = ex.execute(_trial("timeout_0"), slow)

        assert isinstance(result, Result)
        assert result.status == "timeout"
        assert result.metadata["attempts"] == 1

    def test_timeout_retries_up_to_max_retries(self):
        """Test timeouts are retried max_retries times before giving up."""
        ex = RayExecutor(num_workers=1, max_retries=2, timeout=0.4)

        def slow(config):
            time.sleep(30)
            return 1.0

        result = ex.execute(_trial("timeout_1"), slow)

        assert result.status == "timeout"
        # 1 initial attempt + 2 retries
        assert result.metadata["attempts"] == 3

    def test_objective_error_not_retried(self, executor):
        """Test deterministic objective errors are not retried.

        The remote wrapper catches objective exceptions and returns a payload,
        so no retry occurs and no attempt counter is recorded.
        """
        def failing(config):
            raise ValueError("deterministic")

        result = executor.execute(_trial("retry_0"), failing)

        assert result.status == "failed"
        assert "attempts" not in result.metadata


class TestRayExecutorCollectRetryUnit:
    """In-process tests for _collect_with_retry / _payload_to_result.

    These exercise the retry and conversion branches directly, without
    depending on code paths that execute inside Ray worker processes.
    """

    def test_payload_dict_converted_to_result(self):
        """Test a remote payload dict is converted into a Result."""
        ex = RayExecutor()
        trial = _trial("conv_0", fidelity=0.5)

        result = ex._payload_to_result(
            trial,
            {
                "trial_id": "conv_0",
                "objective_value": 4.0,
                "cost": 1.25,
                "fidelity": 0.5,
                "status": "completed",
            },
        )

        assert isinstance(result, Result)
        assert result.objective_value == 4.0
        assert result.cost == 1.25
        assert result.fidelity == 0.5
        assert result.status == "completed"

    def test_payload_already_result_passed_through(self):
        """Test an already-converted Result is returned unchanged."""
        ex = RayExecutor()
        trial = _trial("conv_1")
        existing = Result(trial_id="conv_1", objective_value=7.0)

        assert ex._payload_to_result(trial, existing) is existing

    def test_payload_missing_fields_falls_back_to_trial(self):
        """Test missing payload fields fall back to trial defaults."""
        ex = RayExecutor()
        trial = _trial("conv_2", fidelity=0.75)

        result = ex._payload_to_result(trial, {})

        assert result.trial_id == "conv_2"
        assert np.isnan(result.objective_value)
        assert result.fidelity == 0.75
        assert result.status == "failed"

    def test_generic_exception_retried_then_gives_up(self, monkeypatch):
        """Test non-timeout ray.get errors are retried up to max_retries."""
        ex = RayExecutor(num_workers=1, max_retries=2)
        trial = _trial("retry_unit_0")

        calls = {"get": 0, "submit": 0}

        def fake_get(future, timeout=None):
            calls["get"] += 1
            raise RuntimeError("worker crashed")

        def fake_submit(t, fn):
            calls["submit"] += 1
            return object()

        monkeypatch.setattr(ray, "get", fake_get)
        monkeypatch.setattr(ex, "_submit_trial", fake_submit)

        result = ex._collect_with_retry(trial, object(), square)

        assert result.status == "failed"
        assert "worker crashed" in result.metadata["error"]
        # 1 initial attempt + 2 retries
        assert result.metadata["attempts"] == 3
        assert calls["get"] == 3
        assert calls["submit"] == 2

    def test_generic_exception_recovers_on_retry(self, monkeypatch):
        """Test a transient failure that succeeds on retry returns success."""
        ex = RayExecutor(num_workers=1, max_retries=3)
        trial = _trial("retry_unit_1")

        state = {"n": 0}

        def flaky_get(future, timeout=None):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("transient")
            return {
                "trial_id": "retry_unit_1",
                "objective_value": 9.0,
                "cost": 0.1,
                "fidelity": 1.0,
                "status": "completed",
            }

        monkeypatch.setattr(ray, "get", flaky_get)
        monkeypatch.setattr(ex, "_submit_trial", lambda t, fn: object())

        result = ex._collect_with_retry(trial, object(), square)

        assert result.status == "completed"
        assert result.objective_value == 9.0
        assert state["n"] == 2


class TestRayExecutorFidelity:
    """Tests for fidelity handling."""

    def test_fidelity_passed_through(self, executor):
        """Test fidelity flows into the Result."""
        result = executor.execute(_trial("fid_0", fidelity=0.25), square)

        assert result.fidelity == 0.25

    def test_default_fidelity(self, executor):
        """Test default fidelity is 1.0."""
        result = executor.execute(_trial("fid_1"), square)

        assert result.fidelity == 1.0


class TestRayExecutorShutdown:
    """Tests for shutdown behaviour."""

    def test_shutdown_resets_flag(self):
        """Test shutdown clears the initialization flag."""
        ex = RayExecutor(num_workers=1)
        ex.execute(_trial("shutdown_0"), square)
        assert ex._ray_initialized is True

        ex.shutdown()

        assert ex._ray_initialized is False

    def test_shutdown_idempotent(self):
        """Test shutdown can be called safely when never initialized."""
        ex = RayExecutor()
        ex.shutdown()
        ex.shutdown()
        assert ex._ray_initialized is False
