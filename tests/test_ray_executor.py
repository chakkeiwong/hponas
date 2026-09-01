"""
Test Ray executor for distributed trial execution.

Tier 1 validation: Ray integration enables parallel trials across cluster.
"""

import pytest
import tempfile
from pathlib import Path

try:
    import ray
    from hponas.executors import RayExecutor
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False


@pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
def test_ray_executor_basic():
    """RayExecutor launches and retrieves trial results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(
            checkpoint_dir=tmpdir,
            num_cpus=1.0,
            num_gpus=0.0
        )

        def objective(config):
            return config["x"] ** 2

        # Launch trial
        trial_id = executor.launch(
            trial_id="test_trial",
            config={"x": 2.0},
            objective_fn=objective,
            fidelity=1.0
        )

        assert trial_id == "test_trial"

        # Get result
        result = executor.get_result(trial_id)
        assert result["status"] == "completed"
        assert result["value"] == 4.0
        assert result["cost"] > 0

        executor.shutdown()


@pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
def test_ray_executor_parallel():
    """RayExecutor runs multiple trials in parallel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(
            checkpoint_dir=tmpdir,
            num_cpus=0.5,  # Fractional CPUs for parallelism
            num_gpus=0.0
        )

        def objective(config):
            import time
            time.sleep(0.1)  # Simulate work
            return config["x"] ** 2

        # Launch multiple trials
        trial_ids = []
        for i in range(4):
            trial_id = executor.launch(
                trial_id=f"trial_{i}",
                config={"x": float(i)},
                objective_fn=objective,
                fidelity=1.0
            )
            trial_ids.append(trial_id)

        # Collect results
        results = []
        for trial_id in trial_ids:
            result = executor.get_result(trial_id)
            results.append(result)

        # Verify all completed
        assert len(results) == 4
        assert all(r["status"] == "completed" for r in results)

        # Verify values
        expected = [0.0, 1.0, 4.0, 9.0]
        actual = [r["value"] for r in results]
        assert actual == expected

        executor.shutdown()


@pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
def test_ray_executor_checkpoint():
    """RayExecutor saves and loads checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(checkpoint_dir=tmpdir)

        def objective(config):
            return config["x"] ** 2

        trial_id = executor.launch(
            trial_id="ckpt_trial",
            config={"x": 3.0},
            objective_fn=objective,
            fidelity=1.0
        )

        result = executor.get_result(trial_id)
        assert result["status"] == "completed"

        # Load checkpoint
        ckpt_path = Path(tmpdir)
        checkpoint = executor.load_checkpoint(trial_id, ckpt_path)

        assert checkpoint is not None
        assert checkpoint["config"]["x"] == 3.0
        assert checkpoint["value"] == 9.0

        executor.shutdown()


@pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
def test_ray_executor_error_handling():
    """RayExecutor handles trial errors gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(checkpoint_dir=tmpdir)

        def bad_objective(config):
            raise ValueError("Intentional error")

        trial_id = executor.launch(
            trial_id="error_trial",
            config={"x": 1.0},
            objective_fn=bad_objective,
            fidelity=1.0
        )

        result = executor.get_result(trial_id)
        assert result["status"] == "failed"
        assert "error" in result
        assert "Intentional error" in result["error"]

        executor.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
