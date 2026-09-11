"""Ray executor for distributed trial execution."""

from typing import Callable, List, Optional
import time
import traceback
import numpy as np

from hponas.executors.base import BaseExecutor
from hponas.types import Trial, Result


class RayExecutor(BaseExecutor):
    """Distributed trial executor using Ray.

    Features:
    - Ray cluster management (local or remote)
    - Fault tolerance: retry failed trials, handle worker crashes
    - Resource scheduling: CPU/GPU allocation per trial
    - Parallel execution: configurable concurrency limit
    - Progress monitoring: trial status tracking

    Note: Ray must be installed separately (pip install ray[default])
    """

    def __init__(
        self,
        num_workers: int = 4,
        resources_per_trial: Optional[dict] = None,
        max_retries: int = 3,
        timeout: Optional[float] = None,
    ):
        """Initialize Ray executor.

        Args:
            num_workers: Number of parallel workers
            resources_per_trial: Resource requirements {"num_cpus": 1, "num_gpus": 0}
            max_retries: Number of retries for failed trials
            timeout: Timeout per trial in seconds
        """
        self.num_workers = num_workers
        self.resources_per_trial = resources_per_trial or {"num_cpus": 1}
        self.max_retries = max_retries
        self.timeout = timeout

        self._ray_initialized = False

    def _initialize_ray(self) -> None:
        """Initialize Ray cluster."""
        if self._ray_initialized:
            return

        try:
            import ray

            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True)

            self._ray_initialized = True

            # Note: the per-trial remote wrapper is created in _submit_trial(),
            # which closes over the caller's objective_fn. No cluster-level
            # placeholder is needed here.

        except ImportError:
            raise ImportError(
                "Ray is not installed. Install with: pip install ray[default]"
            )

    def execute(self, trial: Trial, objective_fn: Callable[[dict], float]) -> Result:
        """Execute single trial (synchronous).

        Args:
            trial: Trial to execute
            objective_fn: Objective function

        Returns:
            Trial result
        """
        results = self.execute_batch([trial], objective_fn)
        return results[0]

    def execute_batch(
        self, trials: List[Trial], objective_fn: Callable[[dict], float]
    ) -> List[Result]:
        """Execute batch of trials in parallel.

        Args:
            trials: List of trials to execute
            objective_fn: Objective function

        Returns:
            List of trial results
        """
        self._initialize_ray()

        # Submit all trials as remote tasks
        futures = []
        for trial in trials:
            # Wrap objective function call
            future = self._submit_trial(trial, objective_fn)
            futures.append((trial, future))

        # Collect results, retrying transient failures up to max_retries
        results = []
        for trial, future in futures:
            results.append(self._collect_with_retry(trial, future, objective_fn))

        return results

    def _collect_with_retry(
        self,
        trial: Trial,
        future: "ray.ObjectRef",
        objective_fn: Callable[[dict], float],
    ) -> Result:
        """Collect a trial result, retrying on infrastructure failure.

        Ray worker crashes and timeouts are retried up to ``max_retries``
        times. Objective-function errors are NOT retried: the remote wrapper
        catches them and returns a "failed" payload, which is deterministic
        and would fail identically on every attempt.

        Args:
            trial: Trial being collected
            future: Ray future for the first attempt
            objective_fn: Objective function (used to resubmit on retry)

        Returns:
            Result of trial execution (never a raw dict)
        """
        import ray

        attempt = 0
        while True:
            try:
                payload = ray.get(future, timeout=self.timeout)
                # Remote wrapper returns a dict; convert to the Result the
                # BaseExecutor contract requires (Study relies on attributes).
                return self._payload_to_result(trial, payload)

            except ray.exceptions.GetTimeoutError:
                ray.cancel(future, force=True)
                if attempt >= self.max_retries:
                    return Result(
                        trial_id=trial.trial_id,
                        objective_value=float("nan"),
                        cost=0.0,
                        fidelity=trial.fidelity,
                        status="timeout",
                        metadata={
                            "error": f"trial exceeded timeout={self.timeout}s",
                            "attempts": attempt + 1,
                        },
                    )

            except Exception as e:
                if attempt >= self.max_retries:
                    return Result(
                        trial_id=trial.trial_id,
                        objective_value=float("nan"),
                        cost=0.0,
                        fidelity=trial.fidelity,
                        status="failed",
                        metadata={"error": str(e), "attempts": attempt + 1},
                    )

            # Retry: resubmit the trial as a fresh remote task.
            attempt += 1
            future = self._submit_trial(trial, objective_fn)

    def _payload_to_result(self, trial: Trial, payload: dict) -> Result:
        """Convert a remote payload dict into a Result.

        Args:
            trial: Trial the payload belongs to
            payload: Dict returned by the remote wrapper

        Returns:
            Equivalent Result object
        """
        if isinstance(payload, Result):  # defensive: already converted
            return payload

        return Result(
            trial_id=payload.get("trial_id", trial.trial_id),
            objective_value=float(payload.get("objective_value", float("nan"))),
            cost=payload.get("cost", 0.0),
            fidelity=payload.get("fidelity", trial.fidelity),
            status=payload.get("status", "failed"),
            metadata=payload.get("metadata", {}),
        )

    def _submit_trial(
        self, trial: Trial, objective_fn: Callable[[dict], float]
    ) -> "ray.ObjectRef":
        """Submit trial as remote task.

        Args:
            trial: Trial to execute
            objective_fn: Objective function

        Returns:
            Ray future object
        """
        import ray

        # Create remote function for this trial
        @ray.remote(**self.resources_per_trial)
        def execute_remote(config_values: dict) -> dict:
            """Execute trial remotely."""
            start_time = time.time()

            try:
                objective_value = objective_fn(config_values)

                if not np.isfinite(objective_value):
                    status = "nan" if np.isnan(objective_value) else "inf"
                else:
                    status = "completed"

                return {
                    "trial_id": trial.trial_id,
                    "objective_value": float(objective_value),
                    "cost": time.time() - start_time,
                    "fidelity": trial.fidelity,
                    "status": status,
                }

            except Exception as e:
                return {
                    "trial_id": trial.trial_id,
                    "objective_value": float('nan'),
                    "cost": time.time() - start_time,
                    "fidelity": trial.fidelity,
                    "status": "failed",
                    "metadata": {
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    },
                }

        # Submit task
        future = execute_remote.remote(trial.config.values)
        return future

    def shutdown(self) -> None:
        """Shutdown Ray cluster and cleanup."""
        if self._ray_initialized:
            try:
                import ray
                ray.shutdown()
            except Exception:
                pass
            self._ray_initialized = False
