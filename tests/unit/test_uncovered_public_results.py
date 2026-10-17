"""Serialization and child reporting must preserve the public result envelope."""

import math

import cloudpickle
import numpy as np
import pytest

from hponas.executors.local_executor import _isolated_streaming_evaluation
from hponas.executors.reporting import ReportDecision
from hponas.study import StudyResult
from hponas.types import Config, MultiObjectiveResult, Result, Trial


@pytest.mark.parametrize("empty", [False, True])
def test_study_result_serializes_complete_and_incomplete_outcomes(empty):
    result = StudyResult(None if empty else Config({"x": 7}, "best"), None if empty else 3.,
                         [] if empty else [Result("trial", 3., 2.5, 4., {"a": [1]}, "completed")],
                         0 if empty else 1, 0 if empty else 2.5,
                         "incomplete" if empty else "completed", "missing" if empty else None, 8.25)
    assert result.to_dict() == {
        "best_config": None if empty else {"values": {"x": 7}, "config_id": "best"},
        "best_value": None if empty else 3., "n_trials": 0 if empty else 1,
        "total_cost": 0 if empty else 2.5, "status": "incomplete" if empty else "completed",
        "reason": "missing" if empty else None, "total_elapsed_seconds": 8.25,
        "evaluation": None, "resources": None,
        "history": [] if empty else [{"trial_id": "trial", "objective_value": 3., "cost": 2.5,
                                      "fidelity": 4., "metadata": {"a": [1]}, "status": "completed"}],
    }


def test_multiobjective_compatibility_value_uses_first_objective_only_when_unset():
    with pytest.raises(ValueError) as exc:
        MultiObjectiveResult("empty", 0.)
    assert str(exc.value) == "objective_values must be non-empty"
    vector = np.array([3, 7])
    default = MultiObjectiveResult("a", 0., objective_values=vector)
    explicit = MultiObjectiveResult("b", 9., objective_values=vector)
    assert default.objective_value == 3. and type(default.objective_value) is float
    assert explicit.objective_value == 9.
    np.testing.assert_array_equal(default.objective_values, [3, 7])


@pytest.mark.parametrize("action,status", [("continue", "completed"), ("stop", "pruned")])
def test_streaming_child_exchanges_reports_before_final_result_and_closes(action, status):
    class Connection:
        def __init__(self):
            self.sent = []
            self.closed = False
        def send(self, message):
            self.sent.append(message)
        def recv(self):
            assert self.sent[-1][0] == "progress"
            return ReportDecision(action)
        def close(self):
            self.closed = True

    def objective(config, reporter):
        reporter(2, config["x"], cost=3, checkpoint={"step": 2})
        return {"value": config["x"], "cost": 3}

    channel = Connection()
    _isolated_streaming_evaluation(cloudpickle.dumps((Trial(Config({"x": 5}), "t", fidelity=2), objective)), channel)
    assert channel.closed
    assert [kind for kind, _ in channel.sent] == ["progress", "result"]
    progress, result = [message for _, message in channel.sent]
    assert (progress.trial_id, progress.step, progress.value, progress.cost, progress.checkpoint) == ("t", 2, 5, 3, {"step": 2})
    assert result.trial_id == "t" and result.fidelity == 2 and result.status == status
    assert result.objective_value == 5 and result.cost == 3
    assert result.metadata["execution"]["last_step"] == 2
    assert math.isfinite(result.metadata["execution"]["elapsed_seconds"])
