"""Version 1 cooperative reporting protocol shared by local and Ray workers."""

from dataclasses import asdict, dataclass
import json
import math
import time
from typing import Any


@dataclass(frozen=True)
class ProgressReport:
    trial_id: str
    root_trial_id: str
    step: float
    value: float
    cost: float
    elapsed_seconds: float
    checkpoint: Any = None
    schema_version: int = 1
    metadata: Any = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ReportDecision:
    action: str = "continue"
    reason: str = "scheduler"

    def __post_init__(self):
        if self.action not in {"continue", "pause", "stop", "cancel"}:
            raise ValueError("Unknown reporting decision")


class TrialHalted(BaseException):
    """Executor control flow: an objective must not swallow scheduling decisions."""

    def __init__(self, decision):
        self.decision = decision


def validate_checkpoint(checkpoint):
    # Store durable references or JSON state, never silently stringify a model.
    json.dumps(checkpoint, allow_nan=False)


class TrialReporter:
    def __init__(self, trial, callback, started):
        self.trial, self.callback, self.started = trial, callback, started
        self.last = None
        self.halted = None

    def __call__(self, step, value, *, cost=None, checkpoint=None, metadata=None):
        if self.halted:
            raise TrialHalted(self.halted)
        elapsed = time.monotonic() - self.started
        step, value = float(step), float(value)
        cost = elapsed if cost is None else float(cost)
        if not all(math.isfinite(v) for v in (step, value, cost)):
            raise ValueError("Progress step, value and cost must be finite")
        if step <= self.trial.resume_from or step > self.trial.fidelity or cost < 0:
            raise ValueError("Progress outside assigned fidelity or negative cost")
        if self.last and (step < self.last.step or cost < self.last.cost):
            raise ValueError(
                "Progress step and cumulative evaluation cost must not decrease"
            )
        validate_checkpoint(checkpoint)
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError('Progress metadata must be a dictionary')
        validate_checkpoint(metadata)
        report = ProgressReport(
            self.trial.trial_id,
            self.trial.root_trial_id or self.trial.trial_id,
            step,
            value,
            cost,
            elapsed,
            checkpoint,
            metadata=metadata,
        )
        self.last = report
        decision = self.callback(report) if self.callback else ReportDecision()
        if isinstance(decision, str):
            decision = ReportDecision(decision)
        if not isinstance(decision, ReportDecision):
            raise TypeError("Progress callback must return a ReportDecision")
        if decision.action != "continue":
            self.halted = decision
            raise TrialHalted(decision)
        return decision
