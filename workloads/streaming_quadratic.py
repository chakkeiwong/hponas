"""Actual bounded training updates for streaming/fidelity conformance."""
from copy import deepcopy
import math

from workloads.tuning_models import quadratic


class StreamingQuadratic:
    """Report every actual gradient update and retain local physical-work traces.

    Uses eta=i/40, i=1..25 on the known rotated quadratic. The trace is a local
    diagnostic; Study's acknowledged reports supply durable execution evidence.
    """

    def __init__(self):
        self.updates, self.calls = [], []

    def __call__(self, config, fidelity, trial_id, reporter, resume_from, checkpoint):
        if (not isinstance(config, dict) or set(config) != {"eta_index"}
                or type(config["eta_index"]) is not int or not 1 <= config["eta_index"] <= 25):
            raise ValueError("Expected one integer eta_index in [1,25]")
        if (isinstance(fidelity, bool) or isinstance(resume_from, bool)
                or not math.isfinite(fidelity) or not math.isfinite(resume_from)
                or int(fidelity) != fidelity or int(resume_from) != resume_from
                or not 0 <= resume_from < fidelity <= 8):
            raise ValueError("Integral quadratic fidelity and continuation in [0,8] required")
        index, eta = config["eta_index"], config["eta_index"]/40
        if resume_from:
            if checkpoint is None or checkpoint.get("iterations") != int(resume_from):
                raise ValueError("Resume requires the exact parent fidelity checkpoint")
            # Validate schema/configuration without re-executing training work.
            quadratic(eta, int(resume_from), checkpoint)
        elif checkpoint is not None:
            raise ValueError("Restart must not reuse checkpoint state")
        state = checkpoint
        self.calls.append({"trial_id": trial_id, "eta_index": index, "fidelity": fidelity,
                           "resume_from": resume_from, "input_checkpoint": deepcopy(checkpoint),
                           "first_physical_update": len(self.updates)})
        for step in range(int(resume_from)+1, int(fidelity)+1):
            actual = quadratic(eta, step, state)
            if actual["incremental_steps"] != 1:
                raise RuntimeError("Quadratic evaluation did not execute one incremental update")
            state = actual["checkpoint"]
            self.updates.append({"trial_id": trial_id, "eta_index": index, "step": step,
                                 "value": actual["value"], "checkpoint": deepcopy(state)})
            reporter(step, actual["value"], cost=step-resume_from, checkpoint=state)
            self._after_report(step)
        return {"value": actual["value"], "cost": fidelity-resume_from, "checkpoint": state,
                "metadata": {"work_unit": "gradient_updates", "incremental_updates": int(fidelity-resume_from)}}

    def _after_report(self, step):
        """Instrumentation hook after the reporter's durable acknowledgement."""
