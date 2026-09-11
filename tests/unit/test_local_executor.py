"""Unit tests for LocalExecutor.

Tests for hponas/executors/local_executor.py - Phase 1 Day 2
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 1, BUILD_PROGRAM_v3.md lines 99-122
"""

import pytest
import time
import numpy as np
from hponas.executors.local_executor import LocalExecutor
from hponas.types import Trial, Config


@pytest.fixture
def simple_trial():
    """Simple trial for testing."""
    config = Config(values={"x": 3.0})
    return Trial(
        config=config,
        trial_id="trial_0",
        fidelity=1.0,
        status="pending",
    )


class TestLocalExecutorInitialization:
    """Tests for LocalExecutor initialization."""

    def test_local_executor_sync_mode(self):
        """Test creating executor in sync mode."""
        executor = LocalExecutor(mode="sync")
        assert executor.mode == "sync"
        assert executor.max_workers == 1
        assert executor.timeout is None
        assert executor._executor is None

    def test_local_executor_async_mode(self):
        """Test creating executor in async mode."""
        executor = LocalExecutor(mode="async", max_workers=4)
        assert executor.mode == "async"
        assert executor.max_workers == 4
        assert executor._executor is not None
        executor.shutdown()

    def test_local_executor_invalid_mode(self):
        """Test invalid mode raises error."""
        with pytest.raises(ValueError, match="Mode must be 'sync' or 'async'"):
            LocalExecutor(mode="invalid")

    def test_local_executor_with_timeout(self):
        """Test executor with timeout."""
        executor = LocalExecutor(mode="sync", timeout=10.0)
        assert executor.timeout == 10.0


class TestLocalExecutorSyncExecution:
    """Tests for synchronous execution."""

    def test_execute_simple_objective(self, simple_trial):
        """Test executing simple objective function."""
        executor = LocalExecutor(mode="sync")

        def objective(config):
            return config["x"] ** 2

        result = executor.execute(simple_trial, objective)

        assert result.trial_id == "trial_0"
        assert result.objective_value == 9.0
        assert result.status == "completed"
        assert result.fidelity == 1.0
        assert result.cost > 0.0

    def test_execute_passes_config_values(self):
        """Test execute passes config values correctly."""
        executor = LocalExecutor(mode="sync")

        captured_config = {}

        def objective(config):
            captured_config.update(config)
            return 42.0

        config = Config(values={"x": 5.0, "y": 10.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, objective)

        assert captured_config["x"] == 5.0
        assert captured_config["y"] == 10.0
        assert result.objective_value == 42.0

    def test_execute_records_cost(self):
        """Test execute records execution time."""
        executor = LocalExecutor(mode="sync")

        def slow_objective(config):
            time.sleep(0.05)
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, objective_fn=slow_objective)

        assert result.cost >= 0.04  # Should be ~0.05s

    def test_execute_handles_nan(self):
        """Test execute handles NaN results."""
        executor = LocalExecutor(mode="sync")

        def nan_objective(config):
            return np.nan

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, nan_objective)

        assert result.status == "nan"
        assert np.isnan(result.objective_value)

    def test_execute_handles_inf(self):
        """Test execute handles inf results."""
        executor = LocalExecutor(mode="sync")

        def inf_objective(config):
            return np.inf

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, inf_objective)

        assert result.status == "inf"
        assert np.isinf(result.objective_value)

    def test_execute_handles_exception(self):
        """Test execute handles exceptions gracefully."""
        executor = LocalExecutor(mode="sync")

        def failing_objective(config):
            raise ValueError("Test error")

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, failing_objective)

        assert result.status == "failed"
        assert np.isnan(result.objective_value)
        assert "error" in result.metadata
        assert "Test error" in result.metadata["error"]
        assert "traceback" in result.metadata

    def test_execute_async_raises_in_sync_mode(self, simple_trial):
        """Test execute_async raises error in sync mode."""
        executor = LocalExecutor(mode="sync")

        def objective(config):
            return 1.0

        with pytest.raises(ValueError, match="Async execution requires mode='async'"):
            executor.execute_async(simple_trial, objective)


class TestLocalExecutorAsyncExecution:
    """Tests for asynchronous execution."""

    def test_execute_async_returns_future(self):
        """Test execute_async returns future."""
        executor = LocalExecutor(mode="async", max_workers=2)

        def objective(config):
            return config["x"] ** 2

        config = Config(values={"x": 3.0})
        trial = Trial(config=config, trial_id="trial_0")

        future = executor.execute_async(trial, objective)

        assert future is not None
        result = future.result()

        assert result.trial_id == "trial_0"
        assert result.objective_value == 9.0
        assert result.status == "completed"

        executor.shutdown()

    def test_execute_sync_raises_in_async_mode(self):
        """Test execute raises error in async mode."""
        executor = LocalExecutor(mode="async")

        def objective(config):
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        with pytest.raises(ValueError, match="Use execute_async\\(\\) for async mode"):
            executor.execute(trial, objective)

        executor.shutdown()

    def test_async_parallel_execution(self):
        """Test async executor can run trials in parallel."""
        executor = LocalExecutor(mode="async", max_workers=2)

        def slow_objective(config):
            time.sleep(0.1)
            return config["x"]

        # Submit two trials
        config1 = Config(values={"x": 1.0})
        config2 = Config(values={"x": 2.0})
        trial1 = Trial(config=config1, trial_id="trial_0")
        trial2 = Trial(config=config2, trial_id="trial_1")

        start_time = time.time()
        future1 = executor.execute_async(trial1, slow_objective)
        future2 = executor.execute_async(trial2, slow_objective)

        result1 = future1.result()
        result2 = future2.result()
        elapsed = time.time() - start_time

        # Should take ~0.1s if parallel (not 0.2s if sequential)
        assert elapsed < 0.15

        assert result1.objective_value == 1.0
        assert result2.objective_value == 2.0

        executor.shutdown()

    def test_async_handles_exception(self):
        """Test async execution handles exceptions."""
        executor = LocalExecutor(mode="async")

        def failing_objective(config):
            raise RuntimeError("Async test error")

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        future = executor.execute_async(trial, failing_objective)
        result = future.result()

        assert result.status == "failed"
        assert "Async test error" in result.metadata["error"]

        executor.shutdown()


class TestLocalExecutorShutdown:
    """Tests for executor shutdown."""

    def test_shutdown_cleans_up_sync(self):
        """Test shutdown in sync mode."""
        executor = LocalExecutor(mode="sync")
        executor.shutdown()
        # Should not raise error

    def test_shutdown_cleans_up_async(self):
        """Test shutdown in async mode."""
        executor = LocalExecutor(mode="async")
        assert executor._executor is not None

        executor.shutdown()

        assert executor._executor is None

    def test_shutdown_waits_for_pending_tasks(self):
        """Test shutdown waits for pending tasks."""
        executor = LocalExecutor(mode="async", max_workers=1)

        def slow_objective(config):
            time.sleep(0.1)
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        future = executor.execute_async(trial, slow_objective)

        # Shutdown should wait
        executor.shutdown()

        # Task should have completed
        assert future.done()


class TestLocalExecutorErrorHandling:
    """Tests for error handling scenarios."""

    def test_handles_zero_division(self):
        """Test handling zero division error."""
        executor = LocalExecutor(mode="sync")

        def bad_objective(config):
            return 1.0 / 0.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, bad_objective)

        assert result.status == "failed"
        assert "division by zero" in result.metadata["error"].lower()

    def test_handles_import_error(self):
        """Test handling import errors in objective."""
        executor = LocalExecutor(mode="sync")

        def bad_objective(config):
            import nonexistent_module  # noqa
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, bad_objective)

        assert result.status == "failed"
        assert "No module named" in result.metadata["error"]

    def test_negative_inf_handled(self):
        """Test negative infinity handled correctly."""
        executor = LocalExecutor(mode="sync")

        def objective(config):
            return -np.inf

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, objective)

        assert result.status == "inf"
        assert np.isneginf(result.objective_value)


class TestLocalExecutorFidelity:
    """Tests for fidelity parameter handling."""

    def test_fidelity_passed_through(self):
        """Test fidelity is passed to result."""
        executor = LocalExecutor(mode="sync")

        def objective(config):
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0", fidelity=0.5)

        result = executor.execute(trial, objective)

        assert result.fidelity == 0.5

    def test_default_fidelity(self):
        """Test default fidelity is 1.0."""
        executor = LocalExecutor(mode="sync")

        def objective(config):
            return 1.0

        config = Config(values={"x": 1.0})
        trial = Trial(config=config, trial_id="trial_0")

        result = executor.execute(trial, objective)

        assert result.fidelity == 1.0
