"""Ray executor for distributed trial execution."""

from typing import Callable, List, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    import ray
import time
import math
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
        *, resources=None,
    ):
        """Initialize Ray executor.

        Args:
            num_workers: Number of parallel workers
            resources_per_trial: Resource requirements {"num_cpus": 1, "num_gpus": 0}
            max_retries: Number of retries for failed trials
            timeout: Timeout per trial in seconds
        """
        if (
            isinstance(num_workers, bool)
            or not isinstance(num_workers, int)
            or num_workers < 1
        ):
            raise ValueError("num_workers must be positive")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise ValueError("max_retries must be nonnegative")
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive")
        if resources is not None:
            from hponas.executors.resources import ResourceSpec
            if not isinstance(resources, ResourceSpec) or resources_per_trial is not None:
                raise ValueError('Use a ResourceSpec or legacy resources_per_trial, not both')
            if max_retries != 0:
                raise ValueError('ResourceSpec requires explicit max_retries=0')
            resources_per_trial = {'num_cpus': resources.cpu_cores, 'num_gpus': resources.gpus}
        self.resources = resources
        self.num_workers = num_workers
        self.resources_per_trial = resources_per_trial or {"num_cpus": 1}
        self.max_retries = max_retries
        self.timeout = timeout

        self._ray_initialized = False
        self._owns_ray = False
        self._cancellation_failed = False

    def prepare(self) -> None:
        self._initialize_ray()

    def _initialize_ray(self) -> None:
        """Initialize Ray cluster."""
        if self._cancellation_failed:
            raise RuntimeError("Ray executor has an unconfirmed worker cancellation")
        if self._ray_initialized:
            return

        try:
            import ray

            if not ray.is_initialized():
                ray.init(
                    ignore_reinit_error=True,
                    num_cpus=self.num_workers * (self.resources.cpu_cores if self.resources else 1),
                    include_dashboard=False,
                )
                self._owns_ray = True

            if self.resources is not None:
                capacity = ray.cluster_resources()
                if (capacity.get('CPU', 0) < self.resources.cpu_cores * self.num_workers
                        or capacity.get('GPU', 0) < self.resources.gpus * self.num_workers):
                    raise ValueError('Ray cluster cannot satisfy requested concurrent workers')

            self._ray_initialized = True

            # Note: the per-trial remote wrapper is created in _submit_trial(),
            # which closes over the caller's objective_fn. No cluster-level
            # placeholder is needed here.

        except ImportError:
            raise ImportError(
                "Ray is not installed. Install with: pip install ray[default]"
            )

    def execute(
        self, trial: Trial, objective_fn: Callable[[dict], float], *, on_report=None
    ) -> Result:
        """Execute single trial (synchronous).

        Args:
            trial: Trial to execute
            objective_fn: Objective function

        Returns:
            Trial result
        """
        results = self.execute_batch([trial], objective_fn, on_report=on_report)
        return results[0]

    def execute_batch(
        self,
        trials: List[Trial],
        objective_fn: Callable[[dict], float],
        *,
        on_report=None,
    ) -> List[Result]:
        """Execute batch of trials in parallel.

        Args:
            trials: List of trials to execute
            objective_fn: Objective function

        Returns:
            List of trial results
        """
        self._initialize_ray()

        def run_one(trial):
            if on_report is not None:
                return self._execute_streaming(trial, objective_fn, on_report)
            future = self._submit_trial(trial, objective_fn)
            return self._collect_with_retry(trial, future, objective_fn)

        # Each collector starts its deadline at submission. Submission is bounded,
        # and ordered map preserves deterministic observation order for Study.
        with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
            return list(pool.map(run_one, trials))

    def _execute_streaming(self, trial, objective_fn, on_report):
        """Driver-owned decisions; workers wait for an acknowledgement per report.

        The queues use zero-CPU actors, so a one-CPU worker cannot deadlock the
        control channel. Every attempt has fresh channels and explicit cleanup.
        """
        from dataclasses import replace
        import ray
        from ray.util.queue import Queue, Empty

        failed_cost = failed_elapsed = 0.0
        for attempt in range(self.max_retries + 1):
            # A previous batch worker may have failed to finish cancellation
            # while this attempt was queued in the collector pool.
            self._initialize_ray()
            started = time.monotonic()
            requests = replies = future = None
            last_cost = 0.0
            try:
                requests = Queue(actor_options={"num_cpus": 0})
                replies = Queue(actor_options={"num_cpus": 0})
                options = dict(
                    self.resources_per_trial, max_retries=0, retry_exceptions=False
                )
                resource_spec = self.resources

                @ray.remote(**options)
                def evaluate_stream(trial, objective, requests, replies):
                    from hponas.executors.base import evaluate_trial

                    def report(progress):
                        requests.put(progress)
                        return replies.get()

                    if resource_spec is not None:
                        from hponas.executors.ray_resources import evaluate_assigned
                        return evaluate_assigned(trial, objective, resource_spec, report).to_dict()
                    return evaluate_trial(trial, objective, report).to_dict()

                future = evaluate_stream.remote(trial, objective_fn, requests, replies)
                while True:
                    elapsed = time.monotonic() - started
                    if self.timeout is not None and elapsed >= self.timeout:
                        raise ray.exceptions.GetTimeoutError()
                    ready, _ = ray.wait([future], timeout=0)
                    if ready:
                        result = self._payload_to_result(trial, ray.get(future))
                        result.cost += failed_cost
                        result.metadata.update(
                            attempts=attempt + 1,
                            failed_attempt_elapsed_seconds=failed_elapsed,
                        )
                        result.metadata.setdefault("execution", {}).update(
                            schema_version=1,
                            elapsed_seconds=failed_elapsed + time.monotonic() - started,
                            continuation=trial.continuation,
                            resume_from=trial.resume_from,
                        )
                        trial.status = result.status
                        return result
                    wait = (
                        0.02
                        if self.timeout is None
                        else min(0.02, self.timeout - elapsed)
                    )
                    try:
                        progress = requests.get(timeout=wait)
                    except Empty:
                        continue
                    last_cost = progress.cost
                    decision = on_report(
                        replace(
                            progress,
                            elapsed_seconds=failed_elapsed + time.monotonic() - started,
                            cost=failed_cost + progress.cost,
                        )
                    )
                    replies.put(decision)
            except ray.exceptions.RayError as exc:
                if future is not None:
                    self._cancel_and_drain(future)
                elapsed = time.monotonic() - started
                failed_cost += max(elapsed, last_cost)
                failed_elapsed += elapsed
                if attempt == self.max_retries:
                    status = (
                        "timeout"
                        if isinstance(exc, ray.exceptions.GetTimeoutError)
                        else "failed"
                    )
                    trial.status = status
                    return Result(
                        trial.trial_id,
                        float("nan"),
                        failed_cost,
                        trial.fidelity,
                        {
                            "error": str(exc),
                            "attempts": attempt + 1,
                            "failed_attempt_elapsed_seconds": failed_elapsed,
                            "execution": {
                                "schema_version": 1,
                                "elapsed_seconds": failed_elapsed,
                            },
                        },
                        status,
                    )
            finally:
                try:
                    if future is not None and not self._cancellation_failed:
                        self._cancel_and_drain(future)
                finally:
                    for queue in (requests, replies):
                        if queue is not None:
                            queue.shutdown(force=True)

    def _cancel_and_drain(self, future):
        """Confirm task termination before releasing channels or another attempt.

        Force cancellation is asynchronous. Destroying the reporting actors
        first can unblock a worker into the pool while its forced exit is still
        pending, killing the next trial assigned to it.
        """
        import ray

        ready, _ = ray.wait([future], timeout=0)
        if ready:
            return
        ray.cancel(future, force=True)
        try:
            ray.get(future, timeout=30.0)
        except ray.exceptions.GetTimeoutError as exc:
            self._cancellation_failed = True
            raise RuntimeError("Ray worker cancellation did not finish within 30 seconds") from exc
        except ray.exceptions.RayError:
            # A cancelled task or crashed worker is the expected terminal result.
            pass

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
        failed_cost = 0.0
        while True:
            attempt_started = time.monotonic()
            try:
                payload = ray.get(future, timeout=self.timeout)
                # Remote wrapper returns a dict; convert to the Result the
                # BaseExecutor contract requires (Study relies on attributes).
                result = self._payload_to_result(trial, payload)
                result.cost += failed_cost
                result.metadata.update(
                    attempts=attempt + 1, failed_attempt_elapsed_seconds=failed_cost
                )
                return result

            except ray.exceptions.GetTimeoutError:
                self._cancel_and_drain(future)
                failed_cost += time.monotonic() - attempt_started
                if attempt >= self.max_retries:
                    return Result(
                        trial_id=trial.trial_id,
                        objective_value=float("nan"),
                        cost=failed_cost,
                        fidelity=trial.fidelity,
                        status="timeout",
                        metadata={
                            "error": f"trial exceeded timeout={self.timeout}s",
                            "attempts": attempt + 1,
                        },
                    )

            except Exception as e:
                failed_cost += time.monotonic() - attempt_started
                if attempt >= self.max_retries:
                    return Result(
                        trial_id=trial.trial_id,
                        objective_value=float("nan"),
                        cost=failed_cost,
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

        self._initialize_ray()
        # Create remote function for this trial
        # This executor owns retries and their cost ledger. Ray's default worker
        # crash retries would otherwise hide attempts from _collect_with_retry.
        remote_options = dict(
            self.resources_per_trial, max_retries=0, retry_exceptions=False
        )
        resource_spec = self.resources

        @ray.remote(**remote_options)
        def execute_remote(config_values: dict) -> dict:
            """Execute trial remotely."""
            from hponas.executors.base import evaluate_trial

            if resource_spec is not None:
                from hponas.executors.ray_resources import evaluate_assigned
                return evaluate_assigned(trial, objective_fn, resource_spec).to_dict()
            return evaluate_trial(trial, objective_fn).to_dict()

        # Submit task
        future = execute_remote.remote(trial.config.values)
        return future

    def shutdown(self) -> None:
        """Shutdown Ray cluster and cleanup."""
        if self._ray_initialized:
            try:
                import ray

                if self._owns_ray:
                    ray.shutdown()
            except Exception:
                pass
            self._ray_initialized = False
