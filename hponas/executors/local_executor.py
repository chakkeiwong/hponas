"""Local evaluation, with process isolation when a hard deadline is requested."""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import math
import time
import cloudpickle

from hponas.executors.base import BaseExecutor, evaluate_trial
from hponas.types import Result


def _isolated_evaluation(payload, connection):
    try:
        trial, objective = cloudpickle.loads(payload)
        connection.send(evaluate_trial(trial, objective))
    finally:
        connection.close()


def _isolated_streaming_evaluation(payload, connection):
    try:
        trial, objective = cloudpickle.loads(payload)

        def report(progress):
            connection.send(("progress", progress))
            return connection.recv()

        connection.send(("result", evaluate_trial(trial, objective, report)))
    finally:
        connection.close()


class LocalExecutor(BaseExecutor):
    def __init__(self, mode="sync", max_workers=1, timeout=None):
        if mode not in ("sync", "async"):
            raise ValueError(f"Mode must be 'sync' or 'async', got {mode}")
        if (
            not isinstance(max_workers, int)
            or isinstance(max_workers, bool)
            or max_workers < 1
        ):
            raise ValueError("max_workers must be positive")
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive")
        self.mode, self.max_workers, self.timeout = mode, max_workers, timeout
        self._executor = (
            ThreadPoolExecutor(max_workers=max_workers) if mode == "async" else None
        )

    def execute(self, trial, objective_fn, *, on_report=None):
        if self.mode == "async":
            raise ValueError("Use execute_async() for async mode")
        return self._execute_impl(trial, objective_fn, on_report)

    def execute_async(self, trial, objective_fn, *, on_report=None):
        if self.mode != "async":
            raise ValueError("Async execution requires mode='async'")
        if self._executor is None:
            raise RuntimeError("Thread pool not initialized")
        return self._executor.submit(self._execute_impl, trial, objective_fn, on_report)

    def _execute_impl(self, trial, objective_fn, on_report=None):
        if self.timeout is None:
            return evaluate_trial(trial, objective_fn, on_report)
        if on_report is not None:
            return self._execute_streaming_process(trial, objective_fn, on_report)
        # spawn avoids inheriting an initialized CUDA/JAX runtime or thread locks.
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = context.Process(
            target=_isolated_evaluation,
            args=(cloudpickle.dumps((trial, objective_fn)), send),
        )
        started = time.monotonic()
        try:
            process.start()
        except BaseException:
            receive.close()
            send.close()
            raise
        send.close()
        try:
            if receive.poll(max(0.0, self.timeout - (time.monotonic() - started))):
                try:
                    result = receive.recv()
                except EOFError:
                    result = Result(
                        trial.trial_id,
                        float("nan"),
                        time.monotonic() - started,
                        trial.fidelity,
                        {"error": "Objective worker exited without a result"},
                        "failed",
                    )
            else:
                result = Result(
                    trial.trial_id,
                    float("nan"),
                    time.monotonic() - started,
                    trial.fidelity,
                    {
                        "error": f"Deadline of {self.timeout}s exceeded (includes worker startup)",
                        "execution": {"censor_cause": "external_deadline", "deadline_seconds": self.timeout}
                    },
                    "timeout",
                )
            result.metadata.setdefault("execution", {}).update(
                schema_version=1, elapsed_seconds=time.monotonic() - started,
                duration_scope="worker_including_startup", accounting="measured",
                continuation=trial.continuation, resume_from=trial.resume_from,
            )
            trial.status = result.status
            return result
        finally:
            receive.close()
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()

    def _execute_streaming_process(self, trial, objective_fn, on_report):
        """Exchange decisions over a duplex pipe while enforcing the deadline."""
        from dataclasses import replace

        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(
            target=_isolated_streaming_evaluation,
            args=(cloudpickle.dumps((trial, objective_fn)), child),
        )
        started = time.monotonic()
        last_cost = 0.0
        try:
            process.start()
            child.close()
            while True:
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0 or not parent.poll(remaining):
                    result = Result(
                        trial.trial_id,
                        float("nan"),
                        max(last_cost, time.monotonic() - started),
                        trial.fidelity,
                        {"error": f"Deadline of {self.timeout}s exceeded",
                         "execution": {"censor_cause": "external_deadline", "deadline_seconds": self.timeout}},
                        "timeout",
                    )
                    break
                try:
                    kind, payload = parent.recv()
                except EOFError:
                    result = Result(
                        trial.trial_id,
                        float("nan"),
                        max(last_cost, time.monotonic() - started),
                        trial.fidelity,
                        {"error": "Objective worker exited without a result"},
                        "failed",
                    )
                    break
                if kind == "result":
                    result = payload
                    break
                if kind != "progress":
                    raise ValueError("Unknown worker message")
                last_cost = payload.cost
                parent.send(
                    on_report(
                        replace(payload, elapsed_seconds=time.monotonic() - started)
                    )
                )
            result.metadata.setdefault("execution", {}).update(
                schema_version=1,
                elapsed_seconds=time.monotonic() - started,
                continuation=trial.continuation,
                resume_from=trial.resume_from,
                duration_scope="worker_including_startup", accounting="measured",
            )
            trial.status = result.status
            return result
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
