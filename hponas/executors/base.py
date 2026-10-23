"""Base executor interface."""

from abc import ABC, abstractmethod
from typing import Callable, Any
from hponas.types import Trial, Result


class BaseExecutor(ABC):
    """Base class for trial executors.

    Contract (tested in tests/conformance/test_executor_contract.py):
    - execute() runs trial and returns result
    - Handles NaN, inf, timeout, exceptions
    - Checkpoint save/load works
    """

    def prepare(self) -> None:
        """Prepare owned services on the calling thread before worker dispatch."""

    @abstractmethod
    def execute(
        self, trial: Trial, objective_fn: Callable[[dict], float], *, on_report=None
    ) -> Result:
        """Execute trial and return result.

        Args:
            trial: Trial to execute
            objective_fn: Function that evaluates config and returns objective value

        Returns:
            Result of trial execution
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown executor and cleanup resources."""
        pass


def evaluate_trial(trial, objective_fn, on_report=None):
    """Evaluate scalar or workload-dictionary objectives with explicit trial context."""
    import inspect
    import math
    import time
    import traceback
    from hponas.executors.reporting import (
        TrialHalted,
        TrialReporter,
        validate_checkpoint,
    )

    started = time.monotonic()
    reporter = TrialReporter(trial, on_report, started)
    streamed = False
    trial.status = "running"
    try:
        signature = inspect.signature(objective_fn)
        if trial.continuation not in {"resume", "restart"}:
            raise ValueError("Unknown trial continuation mode")
        if trial.continuation == "resume" and trial.resume_from > 0:
            if trial.checkpoint is None:
                raise ValueError("Resumed evaluation requires a checkpoint")
            if not all(
                name in signature.parameters for name in ("checkpoint", "resume_from")
            ):
                raise ValueError(
                    "Resumed objective must declare checkpoint and resume_from"
                )
        context = {}
        for name, value in (
            ("fidelity", trial.fidelity),
            ("seed", trial.seed),
            ("trial_id", trial.trial_id),
            ("root_trial_id", trial.root_trial_id or trial.trial_id),
            ("resume_from", trial.resume_from),
            ("checkpoint", trial.checkpoint),
            ("reporter", reporter),
        ):
            if (
                name in signature.parameters
                and signature.parameters[name].kind != inspect.Parameter.POSITIONAL_ONLY
            ):
                context[name] = value
        streamed = "reporter" in context
        output = objective_fn(trial.config.values, **context)
        if reporter.halted:
            raise TrialHalted(reporter.halted)
        if streamed and (reporter.last is None or reporter.last.step != trial.fidelity):
            raise ValueError("Streamed objective returned before reporting its assigned endpoint")
        if isinstance(output, dict):
            value = float(output["value"])
            cost = float(output.get("cost", time.monotonic() - started))
            metadata = dict(output.get("metadata", {}))
            if "artifacts" in output:
                metadata["artifacts"] = output["artifacts"]
            if "checkpoint" in output:
                validate_checkpoint(output["checkpoint"])
                metadata["checkpoint"] = output["checkpoint"]
        else:
            value, cost, metadata = float(output), time.monotonic() - started, {}
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("Objective cost must be finite and nonnegative")
        if reporter.last and cost < reporter.last.cost:
            raise ValueError("Final cost cannot discard reported evaluation work")
        if (
            reporter.last
            and reporter.last.step == trial.fidelity
            and value != reporter.last.value
        ):
            raise ValueError("Final value conflicts with the reported endpoint")
        if reporter.last and reporter.last.metadata:
            for key in ('multi_objective', 'resource'):
                if key in reporter.last.metadata and metadata.get(key) != reporter.last.metadata[key]:
                    raise ValueError('Final measurement conflicts with reported endpoint metadata')
        status = (
            "nan" if math.isnan(value) else "inf" if math.isinf(value) else "completed"
        )
        result = Result(trial.trial_id, value, cost, trial.fidelity, metadata, status)
    except TrialHalted as halt:
        last = reporter.last
        result = Result(
            trial.trial_id,
            last.value,
            last.cost,
            trial.fidelity,
            {**(last.metadata or {}), "checkpoint": last.checkpoint, "stop_reason": halt.decision.reason},
            {"pause": "paused", "stop": "pruned", "cancel": "cancelled"}[
                halt.decision.action
            ],
        )
    except Exception as exc:
        result = Result(
            trial.trial_id,
            float("nan"),
            time.monotonic() - started,
            trial.fidelity,
            {"error": str(exc), "traceback": traceback.format_exc()},
            "timeout" if isinstance(exc, TimeoutError) else "failed",
        )
        if reporter.last:
            result.cost = max(result.cost, reporter.last.cost)
            result.metadata.update(reporter.last.metadata or {})
    result.metadata["execution"] = {
        "schema_version": 1,
        "mode": "streaming" if streamed else "endpoint",
        "continuation": trial.continuation,
        "resume_from": trial.resume_from,
        "elapsed_seconds": time.monotonic() - started,
        "last_step": reporter.last.step if reporter.last else None,
        "accounting": "measured",
        "duration_scope": "objective_call",
    }
    if reporter.last and "checkpoint" not in result.metadata:
        result.metadata["checkpoint"] = reporter.last.checkpoint
    trial.status = result.status
    return result
