"""Regression checks for the 2026-09-25 audit's observable counterexamples."""

import base64
import copy
import json
import math
from pathlib import Path
import time

import numpy as np
import pytest
import torch

from hponas import (
    Config,
    GPSearcher,
    Knob,
    LocalExecutor,
    RandomSearcher,
    Result,
    SearchSpace,
    Study,
    Trial,
)
from hponas.encoding import SpaceEncoder
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.schedulers import (
    ASHAConfig,
    ASHAScheduler,
    MOASHAConfig,
    MOASHAScheduler,
    PASHAConfig,
    PASHAScheduler,
)
from hponas.store import Store


def space():
    return SearchSpace([Knob("x", "continuous", (0.0, 1.0))])


def values(study):
    return [
        (r.trial_id, study.trials[r.trial_id].config.values, r.objective_value)
        for r in study.get_history()
    ]


def test_completed_resume_executes_no_more_work(tmp_path):
    study = Study(
        RandomSearcher(space(), seed=12),
        LocalExecutor(),
        lambda c: c["x"],
        budget=4,
        study_name="done",
        checkpoint_dir=tmp_path,
    )
    result = study.run()
    resumed = Study(
        RandomSearcher(space(), seed=99),
        LocalExecutor(),
        lambda c: pytest.fail("repeated completed trial"),
    )
    resumed.load_checkpoint(tmp_path / "done_checkpoint.json")
    other = resumed.run()
    assert values(resumed) == values(study)
    assert other.n_trials == 4
    assert other.best_config.values == result.best_config.values
    assert other.best_config.values["x"] == other.best_value


def test_crash_inside_batch_preserves_pending_configs_and_store(tmp_path):
    seen = []

    def objective(c, trial_id):
        seen.append(trial_id)
        if len(seen) == 2:
            raise KeyboardInterrupt("crash before observation")
        return c["x"]

    store = Store(tmp_path / "study.db")
    study = Study(
        RandomSearcher(space(), seed=12),
        LocalExecutor(),
        objective,
        budget=5,
        study_name="crash",
        checkpoint_dir=tmp_path,
        store=store,
        max_concurrent=3,
    )
    with pytest.raises(KeyboardInterrupt):
        study.run()
    assert len(study.results) == 1
    dispatched = []

    def resumed_objective(c, trial_id):
        dispatched.append(trial_id)
        return c["x"]

    resumed = Study(
        RandomSearcher(space(), seed=99),
        LocalExecutor(),
        resumed_objective,
        store=store,
        study_name="crash",
    )
    resumed.load_checkpoint()
    resumed.run()
    reference = Study(
        RandomSearcher(space(), seed=12),
        LocalExecutor(),
        lambda c: c["x"],
        budget=5,
        study_name="crash",
        max_concurrent=3,
    )
    reference.run()
    assert values(resumed) == values(reference)
    assert "crash_trial_0" not in dispatched
    assert len(dispatched) == 4
    assert len(store.read_trials("crash")) == 5
    assert store.read_study("crash").status == "completed"
    store.close()


def test_gp_replay_crosses_warmup_and_preserves_rng(tmp_path):
    events = EventLog(tmp_path / "events.jsonl")
    searcher = GPSearcher(
        space(), seed=2, initial_random_samples=2, num_restarts=1, maximize=False
    )
    study = Study(
        searcher,
        LocalExecutor(),
        lambda c: (c["x"] - 0.3) ** 2,
        budget=4,
        maximize=False,
        event_log=events,
    )
    before = torch.random.get_rng_state().clone()
    study.run()
    assert torch.equal(before, torch.random.get_rng_state())
    replay = GPSearcher(
        space(), seed=2, initial_random_samples=2, num_restarts=1, maximize=False
    )
    passed, message, original, actual = ReplayEngine(
        replay, events, 2
    ).verify_determinism(4)
    assert passed, message
    assert original == actual
    assert replay.get_state() == searcher.get_state()


def test_gp_minimization_uses_matern_and_correct_sign(monkeypatch):
    import hponas.searchers.gp_searcher as module

    captured = {}
    original = module.SingleTaskGP

    def make_gp(x, y, **kwargs):
        captured.update(x=x, y=y, covar=kwargs["covar_module"])
        return original(x, y, **kwargs)

    monkeypatch.setattr(module, "SingleTaskGP", make_gp)
    monkeypatch.setattr(module, "fit_gpytorch_mll", lambda mll: None)
    monkeypatch.setattr(
        module,
        "optimize_acqf",
        lambda *a, **kw: (torch.tensor([[0.3]], dtype=torch.float64),
                          torch.tensor(0.0, dtype=torch.float64)),
    )
    searcher = GPSearcher(space(), seed=1, initial_random_samples=2, maximize=False)
    for tid, x, y in [("one", 0.2, 2.0), ("two", 0.8, 7.0)]:
        searcher.trials[tid] = Config({"x": x})
        searcher.observe(Result(tid, y, 1.0))
    assert searcher.suggest().values == {"x": 0.3}
    assert searcher.proposal_batches[-1]["log_acquisition"] == 0.0
    assert captured["y"].flatten().tolist() == [-2.0, -7.0]
    assert captured["covar"].base_kernel.nu == 2.5


def test_gp_proposals_are_exact_across_caller_thread_counts():
    """Changing host parallelism must not change the seeded proposal trace."""
    traces = []
    original_threads = torch.get_num_threads()
    try:
        for threads in (1, 2):
            torch.set_num_threads(threads)
            searcher = GPSearcher(
                space(), seed=42, initial_random_samples=2, num_restarts=2
            )
            configs = []
            for i in range(8):
                config = searcher.suggest()
                assert torch.get_num_threads() == threads
                tid = str(i)
                searcher.trials[tid] = config
                searcher.observe(Result(tid, -(config.values["x"] - 0.4)**2, 1.0))
                configs.append(config.values)
            traces.append(configs)
        assert traces[0] == traces[1]
    finally:
        torch.set_num_threads(original_threads)


def test_mixed_space_round_trip_and_sampling():
    mixed = SearchSpace(
        [
            Knob("kind", "categorical", ["small", "big"]),
            Knob("width", "ordinal", (2, 5)),
            Knob("lr", "continuous", (1e-5, 1e-2), transform="log"),
            Knob("extra", "continuous", (0.0, 1.0), condition=("kind", "big")),
        ]
    )
    encoder = SpaceEncoder(mixed)
    for seed in range(25):
        config = mixed.sample_config(np.random.default_rng(seed))
        recovered = encoder.decode(encoder.encode(config))
        assert recovered["kind"] == config["kind"]
        assert recovered["width"] == config["width"]
        assert ("extra" in recovered) == (config["kind"] == "big")
        assert recovered["lr"] == pytest.approx(config["lr"])


def test_duplicate_observation_last_wins():
    searcher = RandomSearcher(space(), seed=0)
    searcher.observe(Result("a", 1.0, 1.0))
    searcher.observe(Result("b", 2.0, 1.0))
    searcher.observe(Result("a", 3.0, 1.0))
    assert [(r.trial_id, r.objective_value) for r in searcher.history] == [
        ("a", 3.0),
        ("b", 2.0),
    ]


@pytest.mark.parametrize("scheduler_kind", ["asha", "pasha"], ids=["scheduler0", "scheduler1"])
def test_scheduler_json_restores_configuration_and_unique_reports(scheduler_kind):
    if scheduler_kind == "asha":
        scheduler = ASHAScheduler(ASHAConfig(
            eta=2, r_min=1, r_max=4, median_stopping=True, promotion_policy="legacy_bootstrap"))
    else:
        scheduler = PASHAScheduler(PASHAConfig(eta=2, r_min=1, r_max=4, promotion_budget=5))
    scheduler.report("a", 1, 0.8)
    scheduler.report("a", 1, 0.8)
    if isinstance(scheduler, PASHAScheduler):
        before = json.loads(json.dumps(scheduler.state_dict()))
        with pytest.raises(ValueError, match="Conflicting duplicate"):
            scheduler.report("a", 1, 0.2)
        assert json.loads(json.dumps(scheduler.state_dict())) == before
    else:
        # Only the explicitly legacy ASHA contract replaces a repeated score.
        scheduler.report("a", 1, 0.2)
    scheduler.report("b", 1, 0.7)
    state = json.loads(json.dumps(scheduler.state_dict()))
    restored = type(scheduler)(type(scheduler.config)(**({"promotion_policy": "legacy_bootstrap"} if isinstance(scheduler, ASHAScheduler) else {})))
    restored.load_state_dict(state)
    assert restored.config == scheduler.config
    assert len(restored._rung_populations[0]) == 2
    assert restored.promote() == scheduler.promote()
    assert restored.promote() == []


def test_scheduler_study_replay_includes_empty_promotion_rounds(tmp_path):
    log = EventLog(tmp_path / "scheduler.jsonl")
    scheduler = ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=4))
    searcher = RandomSearcher(space(), seed=4)
    study = Study(
        searcher,
        LocalExecutor(),
        lambda c, fidelity: c["x"] * fidelity,
        budget=4,
        scheduler=scheduler,
        max_concurrent=4,
        event_log=log,
    )
    result = study.run()
    assert result.best_value == max(
        r.objective_value for r in result.history if r.fidelity == 4
    )
    restored = ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=4))
    engine = ReplayEngine(RandomSearcher(space(), seed=4), log, 4, restored)
    ok, message, _, _ = engine.verify_determinism(4)
    assert ok, message
    assert restored.state_dict() == scheduler.state_dict()


def test_mo_exclusive_hv_and_state():
    scheduler = MOASHAScheduler(
        MOASHAConfig(
            r_min=1, r_max=3, objectives=["a", "b"], reference_point=[4.0, 4.0]
        )
    )
    pop = [
        ("x", np.array([1.0, 3.0])),
        ("y", np.array([2.0, 1.0])),
        ("z", np.array([1.5, 2.0])),
    ]
    np.testing.assert_allclose(
        scheduler._compute_hypervolume_contributions(pop), [0.5, 2.0, 0.5]
    )
    for tid, y in pop:
        scheduler.report(tid, 1, dict(zip(["a", "b"], y)))
    restored = MOASHAScheduler(
        MOASHAConfig(r_min=1, r_max=9, objectives=["old", "names"])
    )
    restored.load_state_dict(json.loads(json.dumps(scheduler.state_dict())))
    assert restored.promote() == scheduler.promote()


def test_tpe_pending_resume_and_maximize_direction():
    pytest.importorskip("optuna")
    from hponas.searchers_tpe import TPESearcher
    from hponas.searchers.adapter import LegacySearcherAdapter

    mixed = SearchSpace(
        [
            Knob("choice", "categorical", ["a", "b"]),
            Knob("x", "continuous", (0.0, 1.0), condition=("choice", "b")),
        ]
    )
    source = TPESearcher(mixed, seed=4)
    configs = source.propose(12)
    for config in configs[:10]:
        source.observe({"config": config, "value": float(config.get("x", 0.0))})
    restored = TPESearcher(mixed, seed=99)
    restored.load_state_dict(json.loads(json.dumps(source.state_dict())))
    for target in (source, restored):
        target.observe({"config": configs[10], "value": 0.4})
    assert restored.propose(3) == source.propose(3)
    adapter = LegacySearcherAdapter(TPESearcher(space(), seed=1), maximize=True)
    adapter.trials["a"] = adapter.suggest()
    adapter.observe(Result("a", 5.0, 1.0))
    assert adapter.searcher._study.trials[0].value == -5.0


def test_named_store_objectives_honor_direction(tmp_path):
    from hponas.store import Study as RowStudy, Trial as RowTrial

    store = Store(tmp_path / "front.db")
    store.write_study(RowStudy("s", "{}", "maximize", 0, 3))
    for tid, accuracy, latency in [("a", 0.8, 2), ("b", 0.9, 3), ("c", 0.7, 4)]:
        store.write_trial(RowTrial(tid, {}, 0, 1.0, 0.0, 0.0, status="completed"), "s")
        store.write_objectives(tid, {"accuracy": accuracy, "latency": latency})
    assert {
        t.trial_id
        for t in store.get_pareto_front(
            "s", ["accuracy", "latency"], ["maximize", "minimize"]
        )
    } == {"a", "b"}
    with pytest.raises(ValueError, match="Missing objective"):
        store.get_pareto_front("s", ["unknown"])
    store.close()


def test_sampler_diagnostics_detect_stuck_and_correlated_chains():
    from workloads.sampler_neutra import compute_ess, compute_rhat

    stuck = np.ones((4, 200, 2))
    assert compute_ess(stuck) == 0
    assert math.isinf(compute_rhat(stuck))
    rng = np.random.default_rng(3)
    independent = rng.normal(size=(4, 2000, 1))
    correlated = np.empty_like(independent)
    correlated[:, 0] = independent[:, 0]
    for i in range(1, 2000):
        correlated[:, i] = 0.98 * correlated[:, i - 1] + independent[:, i]
    assert compute_rhat(independent) < 1.01
    assert compute_ess(independent) > 3000
    assert compute_ess(correlated) < 500


def test_local_deadline_stops_work_before_late_side_effect(tmp_path):
    target = tmp_path / "late"

    def objective(c):
        time.sleep(3)
        target.write_text("should not execute")
        return 1.0

    result = LocalExecutor(timeout=0.15).execute(
        Trial(Config({"x": 0.0}), "timeout"), objective
    )
    assert result.status == "timeout"
    assert not target.exists()


def test_protected_seed_cannot_enter_workload_objective():
    from workloads.rl_routine import rl_routine

    with pytest.raises(ValueError, match="evaluate_checkpoint"):
        rl_routine({}, test_seed=999)


def test_batch_cost_penalty_uses_sum_of_costs():
    from botorch.acquisition import AcquisitionFunction
    from hponas.searchers_cost import CostAwareAcquisition

    class ConstantLogEI(AcquisitionFunction):
        def __init__(self):
            super().__init__(model=None)

        def forward(self, X):
            return X.new_full(X.shape[:-2], -1.0)

    class Costs:
        def posterior_mean_log_cost(self, X):
            return X[..., 0].log()

    acquisition = CostAwareAcquisition(ConstantLogEI(), Costs(), temperature=1.0)
    x = torch.tensor([[[2.0], [3.0]]], dtype=torch.float64, requires_grad=True)
    value = acquisition(x)
    assert value.item() == pytest.approx(-1 - math.log(5))
    value.backward()
    np.testing.assert_allclose(x.grad.numpy(), [[[-0.2], [-0.2]]])


def test_mo_acquisition_trains_in_maximization_coordinates(monkeypatch):
    import hponas.searchers_mo as module

    captured = []

    class Model(torch.nn.Module):
        def __init__(self, x, y):
            super().__init__()
            captured.append(y.detach().clone())
            self.likelihood = None

    monkeypatch.setattr(module, "SingleTaskGP", Model)
    monkeypatch.setattr(module, "ExactMarginalLogLikelihood", lambda *a: None)
    monkeypatch.setattr(module, "fit_gpytorch_mll", lambda *a: None)
    monkeypatch.setattr(module, "ModelListGP", lambda *a: None)
    refs = []
    monkeypatch.setattr(
        module,
        "qLogNoisyExpectedHypervolumeImprovement",
        lambda **kw: refs.append(kw["ref_point"]) or None,
    )
    monkeypatch.setattr(
        module,
        "optimize_acqf",
        lambda **kw: (torch.tensor([[0.4]], dtype=torch.float64), None),
    )
    searcher = module.qLogNEHVISearcher(
        space(), objectives=["a", "b"], reference_point=np.array([10.0, 20.0]), seed=2
    )
    searcher.observe({"config": {"x": 0.2}, "objectives": {"a": 1.0, "b": 2.0}})
    searcher.observe({"config": {"x": 0.5}, "objectives": {"a": 3.0, "b": 4.0}})
    searcher._propose_bo(1)
    assert captured[0].flatten().tolist() == [-1.0, -3.0]
    assert captured[1].flatten().tolist() == [-2.0, -4.0]
    assert refs[0].tolist() == [-10.0, -20.0]


@pytest.mark.parametrize("kind", ["qnehvi", "nsgaii"])
def test_mo_rng_restores_after_prior_proposals(kind):
    from hponas.searchers_mo import qLogNEHVISearcher, NSGAIISearcher

    factory = qLogNEHVISearcher if kind == "qnehvi" else NSGAIISearcher
    source = factory(space(), objectives=["a", "b"], seed=4)
    source.propose(3)
    restored = factory(space(), objectives=["a", "b"], seed=99)
    restored.load_state_dict(json.loads(json.dumps(source.state_dict())))
    assert restored.propose(3) == source.propose(3)


def test_asha_efficiency_counts_every_actual_evaluation():
    from validation.v06_asha_efficiency import run_asha_search

    calls = []

    def objective(config, fidelity):
        calls.append((config["x"], fidelity))
        return {"value": config["x"], "cost": 7.0}

    # Study accepts dictionary objectives; costs must sum all evaluations.
    _, cost, best = run_asha_search(
        space(), objective, 6, 2, ASHAConfig(eta=3, r_min=1, r_max=9)
    )
    assert cost == 7 * len(calls)
    assert any(x == best["x"] and fidelity == 9 for x, fidelity in calls)
