"""
Test executors: conformance tests (Ray vs local produce same results).

Survey reference: Ch 15 sec:executor-adapters.
R1 spike exit criterion: conformance tests pass.
"""

import tempfile
from pathlib import Path

from hponas.executors import LocalExecutor, RayExecutor


def dummy_objective(config: dict) -> float:
    """Dummy objective for testing: sum of config values."""
    return sum(v for v in config.values() if isinstance(v, (int, float)))


def test_local_executor_launch():
    """Local executor launches and completes a trial."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = LocalExecutor(checkpoint_dir=tmpdir)

        trial_id = executor.launch(
            trial_id="trial_1",
            config={"x": 1.0, "y": 2.0},
            objective_fn=dummy_objective,
            fidelity=1.0,
        )

        assert trial_id == "trial_1"
        result = executor.get_result(trial_id)
        assert result["value"] == 3.0
        assert result["status"] == "completed"


def test_local_executor_checkpoint():
    """Local executor saves and loads checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = LocalExecutor(checkpoint_dir=tmpdir)

        trial_id = executor.launch(
            trial_id="trial_1",
            config={"x": 1.0, "y": 2.0},
            objective_fn=dummy_objective,
            fidelity=1.0,
        )

        # Save checkpoint
        ckpt_path = Path(tmpdir)
        executor.checkpoint(trial_id, ckpt_path)

        # Load checkpoint
        loaded = executor.load_checkpoint(trial_id, ckpt_path)
        assert loaded is not None
        assert loaded["value"] == 3.0


def test_ray_executor_launch():
    """Ray executor launches a trial (spike: stub)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(checkpoint_dir=tmpdir)

        trial_id = executor.launch(
            trial_id="trial_1",
            config={"x": 1.0, "y": 2.0},
            objective_fn=dummy_objective,
            fidelity=1.0,
        )

        assert trial_id == "trial_1"

        # Poll for result (spike: completes immediately)
        result = executor.poll(trial_id)
        assert result["value"] == 3.0
        assert result["status"] == "completed"


def test_conformance_local_vs_ray():
    """
    Conformance test: local and ray executors produce same results for same config.

    R1 spike exit criterion: same seed → same configs → same results.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {"x": 1.5, "y": 2.5}

        # Local executor
        local_exec = LocalExecutor(checkpoint_dir=Path(tmpdir) / "local")
        local_exec.launch("trial_1", config, dummy_objective, 1.0)
        local_result = local_exec.get_result("trial_1")

        # Ray executor
        ray_exec = RayExecutor(checkpoint_dir=Path(tmpdir) / "ray")
        ray_exec.launch("trial_1", config, dummy_objective, 1.0)
        ray_result = ray_exec.poll("trial_1")

        # Same config should produce same value
        assert local_result["value"] == ray_result["value"]


def test_ray_executor_checkpoint_copy():
    """Ray executor copies checkpoints (population method exploit verb)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = RayExecutor(checkpoint_dir=tmpdir)

        # Launch source trial
        executor.launch("trial_src", {"x": 1.0}, dummy_objective, 1.0)
        executor.poll("trial_src")  # complete it

        # Copy checkpoint to new trial
        executor.copy_checkpoint("trial_src", "trial_dst")

        # Tier 0: Destination checkpoint file should exist
        dst_checkpoint = Path(tmpdir) / "trial_dst.pkl"
        assert dst_checkpoint.exists(), "Destination checkpoint should exist after copy"
