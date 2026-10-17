"""Actual vendor methods, promotion safety and interrupted vector integration."""
from copy import deepcopy
import json

import numpy as np
import pytest
from scipy.stats import spearmanr

from hponas import (Knob, SearchSpace, Config, Result, LocalExecutor, MultiObjectiveStudy,
                    MultiObjectiveRandomSearcher, MultiObjectiveBayesSearcher, WrappedNSGAIISearcher,
                    MultiObjectiveScheduler, ObjectiveSpec)
from hponas.store import Store
from workloads.tuning_models import quadratic


OBJECTIVES = [{"name": "loss", "direction": "min", "lower": 0., "upper": 2.},
              {"name": "gain", "direction": "max", "lower": 0., "upper": 1.}]
CONSTRAINTS = {"radius": .85}


def space():
    return SearchSpace([Knob("x", "continuous", (.01, .6))])


def output(config, fidelity=1., checkpoint=None, resume_from=0.):
    value = quadratic(config["x"], int(fidelity), checkpoint if resume_from else None)
    return {"objectives": {"loss": value["value"], "gain": config["x"]},
            "constraints": {"radius": config["x"]}, "work": value["incremental_steps"],
            "cost": float(value["incremental_steps"]), "checkpoint": value["checkpoint"]}


def make_searcher(method, fidelity=1):
    common = dict(objectives=OBJECTIVES, constraints=CONSTRAINTS, seed=9)
    if method == "random":
        return MultiObjectiveRandomSearcher(space(), **common)
    if method == "nsgaii":
        return WrappedNSGAIISearcher(space(), **common, population_size=4, model_fidelity=fidelity)
    return MultiObjectiveBayesSearcher(space(), **common, method=method, model_fidelity=fidelity,
                                       n_initial=4, candidate_count=16, mc_samples=16, fit_maxiter=12)


@pytest.mark.parametrize("method", ["qlognehvi", "chebyshev"])
def test_real_botorch_acquisition_and_recovery_have_identical_proposals(method, monkeypatch):
    from botorch.acquisition.multi_objective import logei as mo_logei
    from botorch.acquisition import logei as scalar_logei
    module = mo_logei if method == "qlognehvi" else scalar_logei
    name = "qLogNoisyExpectedHypervolumeImprovement" if method == "qlognehvi" else "qLogExpectedImprovement"
    constructor, calls = getattr(module, name), []
    def capture(**kwargs):
        calls.append(kwargs)
        return constructor(**kwargs)
    monkeypatch.setattr(module, name, capture)
    searcher = make_searcher(method)
    for i in range(4):
        config = searcher.suggest()
        tid = str(i)
        searcher.trials[tid] = config
        out = output(config.values)
        row = searcher.multi_objective_spec.observation(**{k: out[k] for k in ["objectives", "constraints", "work"]})
        searcher.observe(Result(tid, 0., 1., 1., {"multi_objective": row}))
    first = searcher.suggest()
    searcher.trials["pending"] = first
    assert len(searcher.acquisition_trace) == 1
    first_call = calls[0]
    targets = [m.outcome_transform.untransform(m.train_targets[:, None])[0].detach().numpy().reshape(-1)
               for m in first_call["model"].models]
    raw = [r.metadata["multi_objective"] for r in searcher.history]
    normalized = np.array([[r["objectives"]["loss"]/2, 1-r["objectives"]["gain"]] for r in raw])
    if method == "qlognehvi":
        np.testing.assert_allclose(np.array(targets[:2]).T, -normalized)
        assert first_call["ref_point"] == [-1., -1.]
    else:
        weights = np.array(searcher.acquisition_trace[0]["weights"])
        np.testing.assert_allclose(targets[0], -((normalized*weights).max(axis=1)+.05*(normalized*weights).sum(axis=1)))
    np.testing.assert_allclose(targets[-1], [r["constraints"]["radius"]-.85 for r in raw])
    assert searcher.acquisition_trace[-1]["training_trial_ids"] == ["0", "1", "2", "3"]
    checkpoint = json.loads(json.dumps(searcher.get_state()))
    expected = searcher.suggest()
    restored = make_searcher(method)
    restored.set_state(checkpoint)
    assert restored.suggest() == expected
    assert restored.acquisition_trace == searcher.acquisition_trace
    assert restored.acquisition_trace[0]["method"] == method
    if method == "chebyshev":
        w0, w1 = [r["weights"] for r in restored.acquisition_trace]
        assert w0 != w1 and sum(w0) == pytest.approx(1.)
    else:
        assert all(r["weights"] is None for r in restored.acquisition_trace)


def test_wrapped_nsgaii_matches_vendor_beyond_first_generation_and_recovers():
    import optuna
    wrapped = make_searcher("nsgaii")
    vendor = optuna.create_study(directions=["minimize", "minimize"],
        sampler=optuna.samplers.NSGAIISampler(seed=9, population_size=4,
                                             constraints_func=lambda trial: trial.user_attrs["constraint_excess"]))
    for i in range(16):
        config = wrapped.suggest()
        trial = vendor.ask()
        u = trial.suggest_float("x", 0., 1.)
        assert config.values["x"] == .01+u*(.6-.01)
        out = output(config.values)
        row = wrapped.multi_objective_spec.observation(**{k: out[k] for k in ["objectives", "constraints", "work"]})
        tid = str(i)
        wrapped.trials[tid] = config
        wrapped.observe(Result(tid, 0., 1., 1., {"multi_objective": row}))
        trial.set_user_attr("constraint_excess", [config.values["x"]-.85])
        vendor.tell(trial, [out["objectives"]["loss"]/2., 1-config.values["x"]])
        if i == 6:
            saved = json.loads(json.dumps(wrapped.get_state()))
            wrapped = make_searcher("nsgaii")
            wrapped.set_state(saved)
    checkpoint = json.loads(json.dumps(wrapped.get_state()))
    restored = make_searcher("nsgaii")
    restored.set_state(checkpoint)
    assert restored.suggest() == wrapped.suggest()
    corrupted = deepcopy(checkpoint)
    corrupted["history"][0]["metadata"]["multi_objective"]["objectives"]["loss"] = .5
    before = json.dumps(restored.get_state(), sort_keys=True)
    with pytest.raises(ValueError, match="vendor observations"):
        restored.set_state(corrupted)
    assert json.dumps(restored.get_state(), sort_keys=True) == before


@pytest.mark.parametrize("method", ["random", "nsgaii"])
def test_vector_promotions_resume_actual_quadratic_work_and_recover(tmp_path, method):
    store = Store(tmp_path / "vectors.db")
    def build(fn, checkpoint_dir=None):
        return MultiObjectiveStudy(make_searcher(method, fidelity=8), LocalExecutor(), fn,
            objectives=OBJECTIVES, constraints=CONSTRAINTS, budget=8, study_name="promotions",
            scheduler=MultiObjectiveScheduler(objectives=OBJECTIVES, constraints=CONSTRAINTS, r_min=1, r_max=8),
            continuation="resume", checkpoint_dir=checkpoint_dir, store=store)
    interrupted_once = []
    def interrupted(config, fidelity, checkpoint, resume_from):
        if fidelity == 4 and not interrupted_once:
            interrupted_once.append(True)
            raise KeyboardInterrupt("pending promotion")
        return output(config, fidelity, checkpoint, resume_from)
    first = build(interrupted, tmp_path)
    with pytest.raises(KeyboardInterrupt):
        first.run()
    resumed = build(output)
    resumed.load_checkpoint()
    actual = resumed.run()
    full = build(output).run()
    assert actual.front == full.front
    assert actual.metrics["known_work_lower_bound"] == full.metrics["total_work"] == 64
    assert actual.metrics["total_work"] is None
    assert len(actual.history) == 32
    assert all(r.fidelity == 8 for r in actual.history if r.trial_id in actual.metrics["front_trial_ids"])
    if method == "nsgaii":
        assert not resumed.searcher._pending
        assert len(resumed.searcher._study.trials) == 8


def test_high_rank_correlation_can_still_destroy_the_true_optimum():
    spec = ObjectiveSpec(OBJECTIVES, constraints=CONSTRAINTS)
    advisory = MultiObjectiveScheduler(**spec.contract, r_max=2)
    experimental = MultiObjectiveScheduler(**spec.contract, r_max=2, selection="experimental_pareto")
    before, after = [], []
    for i in range(100):
        before.append(i)
        after.append(i+1 if i < 99 else 0)
        row = spec.observation(objectives={"loss": i/100, "gain": 1-i/100}, constraints={"radius": 0.}, work=1)
        for scheduler in [advisory, experimental]:
            scheduler.report(str(i), 1., row)
    assert spearmanr(before, after).statistic > .94
    assert "99" in {tid for tid, _ in advisory.promote()}
    assert "99" not in {tid for tid, _ in experimental.promote()}


@pytest.mark.parametrize("selection", ["advisory", "experimental_pareto"])
def test_veto_survives_recovery_and_cannot_be_overridden_by_good_objectives(selection):
    spec = ObjectiveSpec(OBJECTIVES, constraints=CONSTRAINTS)
    scheduler = MultiObjectiveScheduler(**spec.contract, selection=selection)
    bad = spec.observation(objectives={"loss": 0., "gain": 1.}, constraints={"radius": .9}, work=1)
    assert scheduler.report("bad", 1., bad) == "stop"
    state = json.loads(json.dumps(scheduler.state_dict()))
    restored = MultiObjectiveScheduler(**spec.contract, selection=selection)
    restored.load_state_dict(state)
    good = spec.observation(objectives={"loss": 0., "gain": 1.}, constraints={"radius": 0.}, work=1)
    assert restored.report("bad", 2., good) == "stop"
    assert not restored.promote()
    tampered = deepcopy(state)
    tampered["events"][0]["observation"]["constraints"]["radius"] = 0.
    with pytest.raises(ValueError):
        MultiObjectiveScheduler(**spec.contract, selection=selection).load_state_dict(tampered)
