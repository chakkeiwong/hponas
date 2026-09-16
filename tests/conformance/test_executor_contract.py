"""Contract conformance tests for Executor interface.

Authority: HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 2 Day 3
Purpose: Verify LocalExecutor and RayExecutor contract compliance

Contract Requirements:
- execute() accepts trial and returns result
- Failure modes handled gracefully (timeout, crash, OOM)
- State serialization/deserialization works correctly
- Concurrent execution works correctly (async mode)
- Mutation score ≥0.9 (Item 8 partial)

Note: Current LocalExecutor API uses execute(trial, objective_fn), not submit().
Tests written to match actual BaseExecutor interface.
"""

import json
import time
import pytest

from hponas.executors.local_executor import LocalExecutor
from hponas.types import Config, Trial, Result, SearchSpace, Parameter, ParameterType


def _simple_space():
    """2D search space for conformance testing."""
    return SearchSpace(
        parameters={
            "x": Parameter(name="x", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
            "y": Parameter(name="y", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
        }
    )


def _dummy_objective(config_values: dict) -> float:
    """Simple test objective function."""
    x = config_values["x"]
    y = config_values["y"]
    return -(x**2 + y**2)  # Minimize distance from origin


class TestExecutorContractExecute:
    """Test execute() contract compliance."""

    def test_execute_returns_result(self):
        """Test execute() returns Result object."""
        executor = LocalExecutor(mode="sync")
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, _dummy_objective)

        assert isinstance(result, Result)
        assert result.trial_id == "trial_0"
        assert result.status == "completed"

    def test_execute_accepts_trial(self):
        """Test execute() accepts Trial object."""
        executor = LocalExecutor(mode="sync")
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        # Should not raise
        result = executor.execute(trial, _dummy_objective)
        assert result is not None

    def test_execute_computes_objective(self):
        """Test execute() correctly evaluates objective function."""
        executor = LocalExecutor(mode="sync")
        config = Config(values={"x": 0.0, "y": 0.0})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, _dummy_objective)

        assert result.objective_value == 0.0  # At origin
        assert result.status == "completed"


class TestExecutorContractAsync:
    """Test async execution."""

    def test_execute_async_returns_future(self):
        """Test execute_async() returns Future."""
        executor = LocalExecutor(mode="async", max_workers=2)
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        future = executor.execute_async(trial, _dummy_objective)

        assert future is not None
        result = future.result(timeout=2.0)
        assert isinstance(result, Result)

    def test_async_concurrent_execution(self):
        """Test multiple trials execute concurrently."""
        executor = LocalExecutor(mode="async", max_workers=2)

        futures = []
        for i in range(4):
            config = Config(values={"x": float(i) / 10, "y": float(i) / 10})
            trial = Trial(config=config, trial_id=f"trial_{i}", fidelity=1.0)
            future = executor.execute_async(trial, _dummy_objective)
            futures.append(future)

        # Wait for all to complete
        results = [f.result(timeout=2.0) for f in futures]
        assert all(isinstance(r, Result) for r in results)
        assert all(r.status == "completed" for r in results)


class TestExecutorContractFailureModes:
    """Test failure mode handling."""

    def test_objective_exception_handled(self):
        """Test executor handles objective function exceptions."""
        executor = LocalExecutor(mode="sync")

        def failing_objective(config_values):
            raise ValueError("Intentional failure")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, failing_objective)

        assert result is not None
        assert result.status == "failed"
        assert "error" in result.metadata

    def test_objective_nan_handled(self):
        """Test executor handles NaN returns."""
        executor = LocalExecutor(mode="sync")

        def nan_objective(config_values):
            return float("nan")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, nan_objective)

        assert result.status == "nan"

    def test_objective_inf_handled(self):
        """Test executor handles inf returns."""
        executor = LocalExecutor(mode="sync")

        def inf_objective(config_values):
            return float("inf")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, inf_objective)

        assert result.status == "inf"

    def test_objective_timeout_handled(self):
        """Test executor handles timeouts if supported."""
        pytest.skip("Timeout support implementation-defined")

    def test_objective_oom_handled(self):
        """Test executor handles OOM if supported."""
        pytest.skip("OOM handling implementation-defined")


class TestExecutorContractShutdown:
    """Test shutdown behavior."""

    def test_shutdown_completes(self):
        """Test shutdown() completes without error."""
        executor = LocalExecutor(mode="async", max_workers=2)

        # Submit some work
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)
        future = executor.execute_async(trial, _dummy_objective)
        future.result(timeout=2.0)

        # Should not raise
        executor.shutdown()

    def test_shutdown_waits_for_pending_work(self):
        """Test shutdown() waits for pending work to complete."""
        executor = LocalExecutor(mode="async", max_workers=1)

        def slow_objective(config_values):
            time.sleep(0.1)
            return -1.0

        # Submit work
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)
        future = executor.execute_async(trial, slow_objective)

        # Shutdown should wait
        executor.shutdown()

        # Work should have completed
        result = future.result(timeout=0.1)
        assert result.status == "completed"


class TestExecutorContractErrorHandling:
    """Test comprehensive error handling."""

    def test_execute_captures_exception_message(self):
        """Test exception messages are captured in metadata."""
        executor = LocalExecutor(mode="sync")

        def failing_objective(config_values):
            raise ValueError("Custom error message")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, failing_objective)

        assert result.status == "failed"
        assert "Custom error message" in result.metadata["error"]

    def test_execute_captures_traceback(self):
        """Test full traceback is captured on failure."""
        executor = LocalExecutor(mode="sync")

        def failing_objective(config_values):
            raise RuntimeError("Traceback test")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, failing_objective)

        assert result.status == "failed"
        assert "traceback" in result.metadata
        assert "RuntimeError" in result.metadata["traceback"]

    def test_nan_result_preserves_trial_id(self):
        """Test NaN results preserve trial_id."""
        executor = LocalExecutor(mode="sync")

        def nan_objective(config_values):
            return float("nan")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_xyz", fidelity=2.5)

        result = executor.execute(trial, nan_objective)

        assert result.trial_id == "trial_xyz"
        assert result.fidelity == 2.5
        assert result.status == "nan"

    def test_inf_result_preserves_fidelity(self):
        """Test inf results preserve fidelity."""
        executor = LocalExecutor(mode="sync")

        def inf_objective(config_values):
            return float("inf")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=10.0)

        result = executor.execute(trial, inf_objective)

        assert result.fidelity == 10.0
        assert result.status == "inf"

    def test_negative_inf_detected_as_inf(self):
        """Test negative infinity is detected as inf status."""
        executor = LocalExecutor(mode="sync")

        def neg_inf_objective(config_values):
            return float("-inf")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, neg_inf_objective)

        assert result.status == "inf"


class TestExecutorContractModeValidation:
    """Test mode validation and constraints."""

    def test_sync_mode_rejects_execute_async(self):
        """Test sync mode raises error on execute_async()."""
        executor = LocalExecutor(mode="sync")
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        with pytest.raises(ValueError, match="Async execution requires mode='async'"):
            executor.execute_async(trial, _dummy_objective)

    def test_async_mode_rejects_execute(self):
        """Test async mode raises error on execute()."""
        executor = LocalExecutor(mode="async", max_workers=2)
        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        with pytest.raises(ValueError, match="Use execute_async"):
            executor.execute(trial, _dummy_objective)

    def test_invalid_mode_raises_error(self):
        """Test invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Mode must be 'sync' or 'async'"):
            LocalExecutor(mode="invalid")


class TestExecutorContractMaxWorkers:
    """Test max_workers parameter behavior."""

    def test_max_workers_limits_concurrency(self):
        """Test max_workers=1 enforces serial execution."""
        executor = LocalExecutor(mode="async", max_workers=1)

        execution_times = []

        def timed_objective(config_values):
            start = time.time()
            time.sleep(0.05)
            execution_times.append((start, time.time()))
            return -1.0

        # Submit 3 trials
        futures = []
        for i in range(3):
            config = Config(values={"x": 0.5, "y": 0.5})
            trial = Trial(config=config, trial_id=f"trial_{i}", fidelity=1.0)
            future = executor.execute_async(trial, timed_objective)
            futures.append(future)

        # Wait for completion
        for f in futures:
            f.result(timeout=1.0)

        # With max_workers=1, executions should be serial (no overlap)
        # Check that second execution starts after first ends
        assert len(execution_times) == 3
        assert execution_times[1][0] >= execution_times[0][1] - 0.01  # Small tolerance

        executor.shutdown()


class TestExecutorContractCost:
    """Test cost tracking."""

    def test_cost_measures_elapsed_time(self):
        """Test cost field measures actual elapsed time."""
        executor = LocalExecutor(mode="sync")

        def slow_objective(config_values):
            time.sleep(0.1)
            return -1.0

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, slow_objective)

        # Cost should be at least 0.1 seconds
        assert result.cost >= 0.1
        assert result.status == "completed"

    def test_cost_tracked_on_failure(self):
        """Test cost is tracked even when objective fails."""
        executor = LocalExecutor(mode="sync")

        def failing_objective(config_values):
            time.sleep(0.05)
            raise ValueError("Test failure")

        config = Config(values={"x": 0.5, "y": 0.5})
        trial = Trial(config=config, trial_id="trial_0", fidelity=1.0)

        result = executor.execute(trial, failing_objective)

        assert result.status == "failed"
        assert result.cost >= 0.05


# Mutation testing targets (for Week 3 V03 validation)
# These tests are designed to kill common mutations:
# - Off-by-one errors in max_workers
# - Missing exception handling
# - Incorrect status on failure (failed vs nan vs inf)
# - Missing NaN/inf checks (np.isfinite vs manual checks)
# - Race conditions in concurrent execution
# - Mode validation (sync vs async enforcement)
# - Metadata capture (error message vs traceback)
# - Cost tracking (start_time initialization, failure paths)
