"""Exact geometry and adverse persistence controls for vector execution."""
from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
import json

import numpy as np
import pytest

from hponas import (Knob, SearchSpace, LocalExecutor, MultiObjectiveRandomSearcher,
                    MultiObjectiveStudy, ObjectiveSpec, Result, Study)
from hponas.multi_objective import MetricLedger
from hponas.store import Store


OBJECTIVES = [{"name": "loss", "direction": "min", "lower": 0., "upper": 1.},
              {"name": "gain", "direction": "max", "lower": 0., "upper": 1.}]
CONSTRAINTS = {"radius": .8}


def space():
    return SearchSpace([Knob("x", "continuous", (0., 1.))])


def searcher(seed=4, objectives=OBJECTIVES):
    return MultiObjectiveRandomSearcher(space(), objectives=objectives, constraints=CONSTRAINTS, seed=seed)


def objective(config):
    x = config["x"]
    return {"objectives": {"loss": x*x, "gain": x}, "constraints": {"radius": x}, "work": 3, "cost": .1}


def study(fn=objective, **kwargs):
    return MultiObjectiveStudy(searcher(), LocalExecutor(), fn, objectives=OBJECTIVES,
                               constraints=CONSTRAINTS, budget=12, study_name="vector", **kwargs)


def exact_union(points):
    """Rational inclusion-exclusion oracle, independent of coordinate sweeping."""
    total = Q(0)
    for mask in range(1, 1 << len(points)):
        subset = [row for i, row in enumerate(points) if mask & (1 << i)]
        term = Q(1)
        for axis in range(len(points[0])):
            term *= 1-max(row[axis] for row in subset)
        total += (-1)**(len(subset)+1)*term
    return total


@pytest.mark.parametrize("dimension", [2, 3])
def test_hypervolume_matches_exact_union_with_ties_and_mixed_directions(dimension):
    rng = np.random.RandomState(81)
    specs = [{"name": str(i), "direction": "min" if i % 2 == 0 else "max", "lower": 0, "upper": 1}
             for i in range(dimension)]
    for _ in range(128):
        points = [[Q(int(x), 4) for x in row] for row in rng.randint(0, 5, (6, dimension))]
        ledger = MetricLedger(specs, feasibility_rule="all")
        for i, row in enumerate(points):
            ledger.append({"trial_id": str(i), "values": [float(p) if j % 2 == 0 else float(1-p) for j, p in enumerate(row)],
                           "status": "completed", "feasible": True, "work": 1})
        assert ledger.summary()["hypervolume"] == pytest.approx(float(exact_union(points)), abs=1e-14)
        restored = MetricLedger.restore(json.loads(json.dumps(ledger.state_dict())), specs, feasibility_rule="all")
        assert restored.summary() == ledger.summary()


def test_duplicate_fronts_do_not_trigger_exponential_work():
    ledger = MetricLedger([{**o, "direction": "min"} for o in OBJECTIVES]+[
        {"name": "third", "direction": "min", "lower": 0, "upper": 1}], feasibility_rule="all")
    for i in range(1000):
        ledger.append(dict(trial_id=str(i), values=[.25, .5, .75], work=0, status="completed", feasible=True))
    assert ledger.summary()["hypervolume"] == .75*.5*.25


def test_failed_infeasible_and_partial_work_are_charged_but_excluded_from_front():
    spec = ObjectiveSpec(OBJECTIVES, constraints=CONSTRAINTS)
    rows = []
    for i, x in enumerate([.25, .95]):
        raw = objective({"x": x})
        raw.pop("cost")
        rows.append(Result(str(i), 0., .1, 1., {"multi_objective": spec.observation(**raw)}))
    rows.append(Result("failure", float("nan"), .2, 1., {"multi_objective": spec.observation(
        objectives=None, constraints=None, work=9, status="failed")}, "failed"))
    rows.append(Result("partial", 0., .1, .5, {"multi_objective": spec.observation(
        objectives={"loss": 0., "gain": 1.}, constraints={"radius": 0.}, work=2)}))
    summary = spec.summarize(rows)
    assert summary["front_trial_ids"] == ["0"] and summary["total_work"] == 17
    assert spec.summarize(rows, budget=2)["hypervolume"] == 0
    assert spec.summarize(rows, budget=3)["hypervolume"] == .25*(1-.25**2)
    rows.append(Result("worker_error", float("nan"), 2., 1., {}, "failed"))
    assert spec.summarize(rows)["total_work"] is None
    assert spec.summarize(rows)["known_work_lower_bound"] == 17
    with pytest.raises(ValueError, match="measured work"):
        spec.summarize(rows, budget=20)


def test_vector_execution_store_query_and_completed_recovery(tmp_path):
    store = Store(tmp_path / "vectors.db")
    running = study(store=store, checkpoint_dir=tmp_path)
    result = running.run()
    assert result.n_trials == 12 and result.metrics["total_work"] == 36
    assert result.front and all(row["constraints"]["radius"] <= .8 for row in result.front)
    assert {r.trial_id for r in store.get_pareto_front("vector", ["loss", "gain"])} == set(result.metrics["front_trial_ids"])
    assert store.read_study("vector").objective == "multi_objective"
    assert store.read_study("vector").incumbent_value is None
    with pytest.raises(ValueError, match="frozen"):
        store.get_pareto_front("vector", ["loss", "gain"], ["minimize", "minimize"])
    resumed = study(lambda c: pytest.fail("completed work repeated"), store=store)
    resumed.load_checkpoint()
    assert resumed.run().metrics == result.metrics
    assert resumed.get_pareto_front() == result.front
    assert "best_value" not in result.to_dict()
    with pytest.raises(ValueError, match="Pareto|pareto"):
        running.get_best_so_far()
    json.dumps(result.to_dict(), allow_nan=False)


def test_interruption_preserves_pending_vectors_and_flags_unmeasured_attempt(tmp_path):
    calls = []
    def interrupted(config, trial_id):
        calls.append(trial_id)
        if len(calls) == 3:
            raise KeyboardInterrupt("interrupted before observation")
        return objective(config)
    first = study(interrupted, checkpoint_dir=tmp_path)
    with pytest.raises(KeyboardInterrupt):
        first.run()
    replayed = []
    def finish(config, trial_id):
        replayed.append(trial_id)
        return objective(config)
    recovered = study(finish)
    recovered.load_checkpoint(tmp_path / "vector_checkpoint.json")
    result = recovered.run()
    full = study().run()
    assert recovered.get_pareto_front() == full.front
    assert replayed[0] == "vector_trial_2" and len(replayed) == 10
    assert result.metrics["unmeasured_work_trial_ids"] == ["vector_trial_2"]
    assert result.metrics["total_work"] is None
    assert result.metrics["known_work_lower_bound"] == 36


@pytest.mark.parametrize("damage", [
    lambda s: s["multi_objective"]["contract"]["objectives"][0].update(upper=2),
    lambda s: s["results"]["vector_trial_0"]["metadata"]["multi_objective"].update(feasible=True),
    lambda s: s["results"]["vector_trial_0"]["metadata"]["multi_objective"]["objectives"].update(loss=.5),
    lambda s: s.update(maximize=True),
])
def test_corrupt_vector_checkpoint_refuses_before_changing_live_study(tmp_path, damage):
    done = study()
    done.run()
    snapshot = done._snapshot()
    damage(snapshot)
    path = tmp_path / "damaged.json"
    path.write_text(json.dumps(snapshot))
    live = study()
    before = deepcopy(live._snapshot())
    with pytest.raises(ValueError):
        live.load_checkpoint(path)
    assert live._snapshot() == before


@pytest.mark.parametrize("key,value", [("loss", float("nan")), ("gain", 2.), ("loss", True)])
def test_invalid_completed_vector_is_retained_as_failure_with_unknown_work(key, value):
    def broken(config):
        row = objective(config)
        if config["x"] > .5:
            row["objectives"][key] = value
        return row
    result = study(broken).run()
    assert any(r.status == "failed" for r in result.history)
    assert not result.metrics["exact_work"]


def test_scalar_and_vector_study_contracts_cannot_be_silently_mixed():
    with pytest.raises(ValueError, match="MultiObjectiveStudy"):
        Study(searcher(), LocalExecutor(), lambda c: 1.)
    changed = deepcopy(OBJECTIVES)
    changed[0]["upper"] = 2
    with pytest.raises(ValueError, match="same frozen"):
        MultiObjectiveStudy(searcher(objectives=changed), LocalExecutor(), objective,
                            objectives=OBJECTIVES, constraints=CONSTRAINTS)


@pytest.mark.parametrize("work", [-1, True, .5, None])
def test_metric_cannot_label_invalid_work_as_exact(work):
    with pytest.raises(ValueError):
        ObjectiveSpec(OBJECTIVES).observation(objectives={"loss": 0., "gain": 1.}, constraints={}, work=work)
