"""Physical work and independent streaming decision/accounting controls."""
from copy import deepcopy
import json

import pytest

from examples.multifidelity_tuning import run_one
from workloads.streaming_quadratic import StreamingQuadratic
from workloads import streaming_quadratic as module
from validation.multifidelity_reference import verify


def test_checkpoint_validation_does_not_execute_hidden_training_updates(monkeypatch):
    actual = module.quadratic
    executed = []
    def observed(*args, **kwargs):
        result = actual(*args, **kwargs)
        executed.extend(result["trace"])
        return result
    monkeypatch.setattr(module, "quadratic", observed)
    workload = StreamingQuadratic()
    checkpoint, previous, costs = None, 0, []
    for fidelity in [1, 2, 4, 8]:
        result = workload({"eta_index": 18}, fidelity, str(fidelity), lambda *args, **kwargs: None, previous, checkpoint)
        checkpoint, previous = json.loads(json.dumps(result["checkpoint"])), fidelity
        costs.append(result["cost"])
    assert len(executed) == len(workload.updates) == sum(costs) == 8
    assert [r["iteration"] for r in executed] == list(range(1, 9))
    assert [r["cost"] for r in [result]] == [4]


def test_restarted_promotions_charge_every_repeated_update():
    workload = StreamingQuadratic()
    for fidelity in [1, 2, 4, 8]:
        workload({"eta_index": 18}, fidelity, str(fidelity), lambda *args, **kwargs: None, 0, None)
    assert len(workload.updates) == 15
    assert [c["first_physical_update"] for c in workload.calls] == [0, 1, 3, 7]


def test_actual_streaming_trace_has_independent_decisions_and_refuses_corruption(tmp_path):
    run_one(tmp_path, "bounded", [1, 25, 10, 18, 8, 22], "resume", False)
    raw = json.loads((tmp_path / "bounded/raw.json").read_text())
    assert verify(raw)["reference_decisions_verified"]
    for kind in ["value", "cost", "state", "promotion"]:
        bad = deepcopy(raw)
        if kind == "value":
            next(e for e in bad["events"] if e["kind"] == "progress")["data"]["value"] += .1
        elif kind == "cost":
            bad["endpoints"][0]["result"]["cost"] += 1
        elif kind == "state":
            bad["updates"][0]["checkpoint"]["state"][0] += .1
        else:
            next(e for e in bad["events"] if e["kind"] == "promotion_round" and e["data"]["promotions"])["data"]["promotions"][0][1] = 8
        with pytest.raises(ValueError):
            verify(bad)


@pytest.mark.parametrize("config,fidelity,resume,checkpoint", [
    ({"eta_index": True}, 1, 0, None), ({"eta_index": 0}, 1, 0, None),
    ({"eta_index": 18}, 1.5, 0, None), ({"eta_index": 18}, 1, 1, None),
    ({"eta_index": 18}, 4, 2, None), ({"eta_index": 18}, 4, 0, {}),
])
def test_invalid_streaming_context_refuses_before_physical_work(config, fidelity, resume, checkpoint):
    workload = StreamingQuadratic()
    with pytest.raises(ValueError):
        workload(config, fidelity, "bad", lambda *args, **kwargs: pytest.fail("reported invalid work"), resume, checkpoint)
    assert not workload.updates and not workload.calls
