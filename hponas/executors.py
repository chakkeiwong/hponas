"""
Executors: trial launch, checkpointing, and metrics reporting.

Survey reference: Ch 15 sec:executor-adapters, Ch 11 (architecture chapter on Ray Tune).

R1 spike: Ray adapter (trial launch, checkpoint) + local adapter (subprocess isolation).
Tier 0: add RLlib integration (~5d), checkpoint surgery for population methods.
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from typing import Any, Callable, Protocol


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
    Ray Tune adapter: trial launch, checkpoint surgery for population methods (Ch 15 contract).

    Survey: the Ray Tune adapter maps trials to Tune trials and must expose checkpoint
    surgery as first-class operations: save, copy weights across trials, resume. That is
    the machinery PBT exercises inside Tune today and the single strongest reason Ch 11
    kept Tune underneath.

    Spike: stub (returns trial_id, no real Ray).
    Tier 0: real Ray Tune integration (~4d per work breakdown).
    """

    def __init__(self, checkpoint_dir: str | Path):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._trials: dict[str, dict[str, Any]] = {}

    def launch(
        self,
        trial_id: str,
        config: dict[str, Any],
        objective_fn: Callable[[dict[str, Any]], float],
        fidelity: float,
    ) -> str:
        """
        Launch a Ray Tune trial.

        Spike: stub execution (no real Ray, returns immediately).
        Tier 0: ray.tune.run with Trainable class.
        """
        # Spike: fake async by storing the trial and returning immediately
        self._trials[trial_id] = {
            "config": config,
            "objective_fn": objective_fn,
            "fidelity": fidelity,
            "status": "running",
        }
        return trial_id

    def poll(self, trial_id: str) -> dict[str, Any]:
        """
        Poll trial status (spike: complete immediately).

        Tier 0: actual Ray Tune status polling.
        """
        if trial_id in self._trials:
            # Spike: immediately "complete" the trial
            trial = self._trials[trial_id]
            if trial["status"] == "running":
                value = trial["objective_fn"](trial["config"])
                trial["value"] = value
                trial["status"] = "completed"
            return trial
        return {}

    def checkpoint(self, trial_id: str, path: Path) -> None:
        """
        Save checkpoint (spike: stub).

        Tier 0: Ray Tune checkpoint API.
        """
        if trial_id in self._trials:
            ckpt_path = path / f"{trial_id}.pkl"
            with open(ckpt_path, "wb") as f:
                pickle.dump(self._trials[trial_id], f)

    def load_checkpoint(self, trial_id: str, path: Path) -> Any:
        """
        Load checkpoint (spike: stub).

        Tier 0: Ray Tune restore API.
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

        Spike: stub.
        Tier 0: real Ray Tune checkpoint copy with weight surgery.
        """
        # Spike: copy trial state
        if src_trial_id in self._trials:
            self._trials[dst_trial_id] = self._trials[src_trial_id].copy()
            self._trials[dst_trial_id]["status"] = "running"
