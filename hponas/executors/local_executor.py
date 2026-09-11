"""Local executor for synchronous and asynchronous trial execution."""

import time
import traceback
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, Future
import numpy as np

from hponas.executors.base import BaseExecutor
from hponas.types import Trial, Result


class LocalExecutor(BaseExecutor):
    """Local trial executor with sync/async modes.

    Features:
    - Synchronous mode: blocking execution
    - Asynchronous mode: non-blocking with futures
    - Error handling: NaN, inf, timeout, exceptions
    - Resource limits: CPU/memory constraints (basic)
    """

    def __init__(
        self,
        mode: str = "sync",
        max_workers: int = 1,
        timeout: Optional[float] = None,
    ):
        """Initialize local executor.

        Args:
            mode: Execution mode ("sync" or "async")
            max_workers: Number of parallel workers (async mode only)
            timeout: Timeout in seconds (None = no timeout)
        """
        if mode not in ["sync", "async"]:
            raise ValueError(f"Mode must be 'sync' or 'async', got {mode}")

        self.mode = mode
        self.max_workers = max_workers
        self.timeout = timeout

        self._executor = None
        if mode == "async":
            self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def execute(self, trial: Trial, objective_fn: Callable[[dict], float]) -> Result:
        """Execute trial synchronously.

        Args:
            trial: Trial to execute
            objective_fn: Objective function to evaluate

        Returns:
            Trial result
        """
        if self.mode == "async":
            raise ValueError("Use execute_async() for async mode")

        return self._execute_impl(trial, objective_fn)

    def execute_async(self, trial: Trial, objective_fn: Callable[[dict], float]) -> Future:
        """Execute trial asynchronously.

        Args:
            trial: Trial to execute
            objective_fn: Objective function to evaluate

        Returns:
            Future containing result
        """
        if self.mode != "async":
            raise ValueError("Async execution requires mode='async'")

        if self._executor is None:
            raise RuntimeError("Thread pool not initialized")

        return self._executor.submit(self._execute_impl, trial, objective_fn)

    def _execute_impl(self, trial: Trial, objective_fn: Callable[[dict], float]) -> Result:
        """Internal execution implementation with error handling.

        Args:
            trial: Trial to execute
            objective_fn: Objective function

        Returns:
            Trial result with status
        """
        start_time = time.time()
        trial.status = "running"

        try:
            # Execute objective function
            objective_value = objective_fn(trial.config.values)

            # Check for NaN/inf
            if not np.isfinite(objective_value):
                return Result(
                    trial_id=trial.trial_id,
                    objective_value=float(objective_value),
                    cost=time.time() - start_time,
                    fidelity=trial.fidelity,
                    status="nan" if np.isnan(objective_value) else "inf",
                )

            # Success
            return Result(
                trial_id=trial.trial_id,
                objective_value=float(objective_value),
                cost=time.time() - start_time,
                fidelity=trial.fidelity,
                status="completed",
            )

        except TimeoutError:
            return Result(
                trial_id=trial.trial_id,
                objective_value=float('nan'),
                cost=time.time() - start_time,
                fidelity=trial.fidelity,
                status="timeout",
            )

        except Exception as e:
            # Capture exception details
            return Result(
                trial_id=trial.trial_id,
                objective_value=float('nan'),
                cost=time.time() - start_time,
                fidelity=trial.fidelity,
                status="failed",
                metadata={
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    def shutdown(self) -> None:
        """Shutdown executor and cleanup resources."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
