"""
Executors: trial launch, checkpointing, and metrics reporting.

Survey reference: Ch 15 sec:executor-adapters, Ch 11 (architecture chapter on Ray Tune).

R1 spike: Ray adapter (trial launch, checkpoint) + local adapter (subprocess isolation).
Tier 0: LocalExecutor operational, Ray deferred to Tier 1.
Tier 1: Full Ray integration for distributed trials, RLlib checkpoint surgery (8d).
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from typing import Any, Callable, Protocol, Optional

try:
    import ray
    from ray import tune
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False


class Executor(Protocol):
    """
    Executor interface contract (Ch 15).

    launch(trial): start a trial (returns trial_id)
    checkpoint(trial_id): save current state
    load_checkpoint(trial_id, checkpoint_path): resume from checkpoint
    """

    def launch(
        self,
        trial_id: str,
        config: dict[str, Any],
        objective_fn: Callable[[dict[str, Any]], float],
        fidelity: float,
    ) -> str:
        """Launch a trial and return its ID."""
        ...

    def checkpoint(self, trial_id: str, path: Path) -> None:
        """Save trial checkpoint."""
        ...

    def load_checkpoint(self, trial_id: str, path: Path) -> Any:
        """Load trial checkpoint."""
        ...


class LocalExecutor:
    """
    Local executor: subprocess isolation for minutes-scale trials (Ch 15 contract).

    Survey: the local adapter runs minutes-scale trials in-process for the Hamiltonian
    regime, where Ch 9 showed the distributed stack's overhead is the visible cost.

    Spike: simple in-process execution (no real subprocess for simplicity).
    Tier 0: real subprocess isolation with pickle serialization.
    """

    def __init__(self, checkpoint_dir: str | Path):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._running_trials: dict[str, dict[str, Any]] = {}

    def launch(
        self,
        trial_id: str,
        config: dict[str, Any],
        objective_fn: Callable[[dict[str, Any]], float],
        fidelity: float,
    ) -> str:
        """
        Launch a trial in-process (spike: synchronous; Tier 0: subprocess).

        Returns the trial_id.
        """
        # Spike: synchronous execution
        start = time.time()
        value = objective_fn(config)
        cost = time.time() - start

        self._running_trials[trial_id] = {
            "config": config,
            "value": value,
            "cost": cost,
            "fidelity": fidelity,
            "status": "completed",
        }
        return trial_id

    def get_result(self, trial_id: str) -> dict[str, Any]:
        """Get trial result."""
        return self._running_trials.get(trial_id, {})

    def checkpoint(self, trial_id: str, path: Path) -> None:
        """
        Save checkpoint for a trial.

        Spike: pickle the trial state.
        Tier 0: real model checkpoint (weights, optimizer state).
        """
        if trial_id in self._running_trials:
            ckpt_path = path / f"{trial_id}.pkl"
            with open(ckpt_path, "wb") as f:
                pickle.dump(self._running_trials[trial_id], f)

    def load_checkpoint(self, trial_id: str, path: Path) -> Any:
        """
        Load checkpoint for a trial.

        Spike: unpickle the trial state.
        Tier 0: load real model checkpoint.
        """
        ckpt_path = path / f"{trial_id}.pkl"
        if ckpt_path.exists():
            with open(ckpt_path, "rb") as f:
                return pickle.load(f)
        return None


class RayExecutor:
    """
    Ray executor: distributed trials across cluster (Tier 1, Ch 11).

    Survey: Ray Tune adapter for parallel trial execution. Each trial runs as a Ray actor,
    enabling distributed HPO across multiple nodes/GPUs.

    Features:
    - Distributed trial execution via Ray actors
    - Remote checkpoint storage
    - Trial status tracking with Ray
    - Graceful shutdown and cleanup

    Usage:
        executor = RayExecutor(num_cpus=2, num_gpus=0.5)
        trial_id = executor.launch(trial_id, config, objective_fn, fidelity)
        result = executor.get_result(trial_id)
    """

    def __init__(
        self,
        checkpoint_dir: str | Path = "./ray_checkpoints",
        num_cpus: float = 1.0,
        num_gpus: float = 0.0,
        ray_address: Optional[str] = None
    ):
        """
        Initialize Ray executor.

        Args:
            checkpoint_dir: Directory for checkpoint storage
            num_cpus: CPUs per trial (can be fractional)
            num_gpus: GPUs per trial (can be fractional)
            ray_address: Ray cluster address (None = local mode)
        """
        if not RAY_AVAILABLE:
            raise ImportError("RayExecutor requires ray: pip install ray")

        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.num_cpus = num_cpus
        self.num_gpus = num_gpus

        # Initialize Ray if not already running
        if not ray.is_initialized():
            ray.init(address=ray_address, ignore_reinit_error=True)

        # Track running trials
        self._futures: dict[str, ray.ObjectRef] = {}
        self._trial_configs: dict[str, dict] = {}

    def launch(
        self,
        trial_id: str,
        config: dict[str, Any],
        objective_fn: Callable[[dict[str, Any]], float],
        fidelity: float,
    ) -> str:
        """
        Launch trial on Ray cluster.

        Args:
            trial_id: Unique trial identifier
            config: Hyperparameter configuration
            objective_fn: Objective function to optimize
            fidelity: Training fidelity (fraction of max budget)

        Returns:
            trial_id
        """
        # Submit trial to Ray using ray.remote wrapper
        future = _run_trial_remote.options(
            num_cpus=self.num_cpus,
            num_gpus=self.num_gpus
        ).remote(trial_id, config, objective_fn, fidelity, self.checkpoint_dir)

        self._futures[trial_id] = future
        self._trial_configs[trial_id] = config

        return trial_id

    def poll(self, trial_id: str) -> dict[str, Any]:
        """
        Poll trial status and wait for completion (blocking).

        For spike compatibility, this blocks until the trial completes.
        Use get_result() with timeout for non-blocking behavior.

        Args:
            trial_id: Trial identifier

        Returns:
            dict with keys: trial_id, value, cost, status
        """
        return self.get_result(trial_id)

    def get_result(self, trial_id: str, timeout: Optional[float] = None) -> dict[str, Any]:
        """
        Get trial result (blocking).

        Args:
            trial_id: Trial identifier
            timeout: Maximum wait time in seconds (None = wait forever)

        Returns:
            dict with keys: value, cost, status
        """
        if trial_id not in self._futures:
            raise KeyError(f"Trial {trial_id} not found")

        future = self._futures[trial_id]

        try:
            result = ray.get(future, timeout=timeout)
            return result
        except ray.exceptions.GetTimeoutError:
            return {
                "trial_id": trial_id,
                "value": None,
                "cost": 0.0,
                "status": "running",
                "error": "Timeout waiting for result"
            }

    def checkpoint(self, trial_id: str, path: Path) -> None:
        """
        Checkpoint trial state.

        Ray executor saves checkpoints during trial execution,
        so this is mostly a no-op. Use for explicit checkpoint requests.
        """
        if trial_id not in self._trial_configs:
            raise KeyError(f"Trial {trial_id} not found")

        # Copy checkpoint to requested path
        src_path = self.checkpoint_dir / f"{trial_id}.pkl"
        if src_path.exists():
            import shutil
            shutil.copy(src_path, path / f"{trial_id}.pkl")

    def load_checkpoint(self, trial_id: str, path: Path) -> Any:
        """
        Load checkpoint.

        Args:
            trial_id: Trial identifier
            path: Checkpoint directory

        Returns:
            Checkpoint data
        """
        ckpt_path = path / f"{trial_id}.pkl"
        if ckpt_path.exists():
            with open(ckpt_path, "rb") as f:
                return pickle.load(f)
        return None

    def copy_checkpoint(self, src_trial_id: str, dst_trial_id: str) -> None:
        """
        Copy checkpoint from src to dst (population method exploit verb, Ch 15).

        Survey: PBT's checkpoint surgery; our adapter's job is to keep it reachable
        from the scheduler's exploit verb.

        Args:
            src_trial_id: Source trial identifier
            dst_trial_id: Destination trial identifier
        """
        src_path = self.checkpoint_dir / f"{src_trial_id}.pkl"
        if not src_path.exists():
            raise FileNotFoundError(f"Source checkpoint {src_path} not found")

        dst_path = self.checkpoint_dir / f"{dst_trial_id}.pkl"
        import shutil
        shutil.copy(src_path, dst_path)

    def shutdown(self) -> None:
        """Shutdown Ray executor and cleanup resources."""
        # Cancel any running trials
        for trial_id, future in self._futures.items():
            try:
                ray.cancel(future)
            except Exception:
                pass

        self._futures.clear()
        self._trial_configs.clear()

        # Note: We don't call ray.shutdown() here because Ray may be shared
        # across multiple executors in the same process

    def __del__(self):
        """Cleanup on deletion."""
        self.shutdown()


# Ray remote function (must be at module level)
if RAY_AVAILABLE:
    @ray.remote
    def _run_trial_remote(
        trial_id: str,
        config: dict[str, Any],
        objective_fn: Callable[[dict[str, Any]], float],
        fidelity: float,
        checkpoint_dir: Path
    ) -> dict[str, Any]:
        """
        Remote trial execution (runs as Ray actor).

        Returns:
            dict with keys: trial_id, value, cost, checkpoint_path
        """
        start_time = time.time()

        try:
            # Execute objective
            value = objective_fn(config)
            cost = time.time() - start_time

            # Save checkpoint
            checkpoint_path = checkpoint_dir / f"{trial_id}.pkl"
            with open(checkpoint_path, "wb") as f:
                pickle.dump({
                    "config": config,
                    "value": value,
                    "fidelity": fidelity,
                    "cost": cost,
                }, f)

            return {
                "trial_id": trial_id,
                "value": value,
                "cost": cost,
                "checkpoint_path": str(checkpoint_path),
                "status": "completed",
            }

        except Exception as e:
            return {
                "trial_id": trial_id,
                "value": None,
                "cost": time.time() - start_time,
                "error": str(e),
                "status": "failed",
            }
