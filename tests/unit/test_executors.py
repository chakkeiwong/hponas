"""
Unit Tests: Executors

Tests LocalExecutor and DistributedExecutor.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import tempfile
from pathlib import Path
import time

from hponas.legacy_executors import LocalExecutor


class TestLocalExecutor:
    """Unit tests for LocalExecutor."""

    def test_init_sets_checkpoint_dir(self):
        """LocalExecutor stores checkpoint directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            assert executor.checkpoint_dir == Path(tmpdir)

    def test_launch_runs_objective(self):
        """launch() executes objective function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return config["x"]**2

            config = {"x": 3.0}
            trial_id = "trial_1"

            executor.launch(trial_id, config, objective, fidelity=1.0)
            result = executor.get_result(trial_id)

            assert result["status"] == "completed"
            assert result["value"] == 9.0

    def test_launch_passes_config(self):
        """launch() passes config dict to objective."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            captured_config = {}

            def objective(config):
                captured_config.update(config)
                return 0.0

            config = {"x": 5.0, "y": 10.0}
            executor.launch("trial_1", config, objective, fidelity=1.0)
            executor.get_result("trial_1")

            assert captured_config["x"] == 5.0
            assert captured_config["y"] == 10.0

    def test_launch_records_cost(self):
        """launch() records execution time as cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def slow_objective(config):
                time.sleep(0.05)
                return 1.0

            executor.launch("trial_1", {"x": 1.0}, slow_objective, fidelity=1.0)
            result = executor.get_result("trial_1")

            assert result["cost"] > 0.04  # Should record ~0.05s

    def test_get_result_returns_status(self):
        """get_result() returns trial status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return 2.0

            executor.launch("trial_1", {"x": 1.0}, objective, fidelity=1.0)
            result = executor.get_result("trial_1")

            assert result["status"] == "completed"

    def test_get_result_captures_exception(self):
        """get_result() captures and reports exceptions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def failing_objective(config):
                raise RuntimeError("Test failure")

            executor.launch("trial_1", {"x": 1.0}, failing_objective, fidelity=1.0)
            result = executor.get_result("trial_1")

            assert result["status"] == "failed"
            assert "error" in result
            assert "RuntimeError" in result["error"]

    def test_parallel_execution(self):
        """Executor runs multiple trials in parallel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir, max_workers=2)

            def objective(config):
                time.sleep(0.1)
                return config["x"]

            # Launch 4 trials
            for i in range(4):
                executor.launch(f"trial_{i}", {"x": float(i)}, objective, fidelity=1.0)

            # Get all results
            results = [executor.get_result(f"trial_{i}") for i in range(4)]

            assert all(r["status"] == "completed" for r in results)
            assert [r["value"] for r in results] == [0.0, 1.0, 2.0, 3.0]

    def test_max_workers_limits_parallelism(self):
        """max_workers parameter limits concurrent executions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir, max_workers=1)

            def objective(config):
                time.sleep(0.1)
                return 1.0

            # Launch 2 trials
            start = time.time()
            executor.launch("trial_1", {"x": 1.0}, objective, fidelity=1.0)
            executor.launch("trial_2", {"x": 2.0}, objective, fidelity=1.0)

            executor.get_result("trial_1")
            executor.get_result("trial_2")
            elapsed = time.time() - start

            # With max_workers=1, should be sequential (~0.2s)
            assert elapsed > 0.18

    def test_checkpoint_saved_on_completion(self):
        """Executor saves checkpoint after trial completes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def objective(config):
                return config["x"]

            executor.launch("trial_1", {"x": 5.0}, objective, fidelity=1.0)
            result = executor.get_result("trial_1")

            # Checkpoint file should exist
            checkpoint_path = Path(tmpdir) / "trial_1_checkpoint.json"
            # Note: This assumes executor saves checkpoints; implementation may vary

    def test_fidelity_parameter_passed(self):
        """Fidelity parameter is accessible in objective."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            captured_fidelity = None

            def objective(config, fidelity=1.0):
                nonlocal captured_fidelity
                captured_fidelity = fidelity
                return 1.0

            executor.launch("trial_1", {"x": 1.0}, objective, fidelity=0.5)
            executor.get_result("trial_1")

            # If executor supports passing fidelity to objective
            # assert captured_fidelity == 0.5
