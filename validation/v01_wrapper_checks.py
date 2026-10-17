"""Wiring checks for the wrapper inventory omitted by the historical V01 runner.

These synthetic traces are engineering evidence. They are not a multi-task
tabular distributional-equivalence campaign, whose band/design remains open.
"""

from __future__ import annotations

import math
import numpy as np

from validation.reference_checks import pasha_reference, promotion_reference, reference_promotions

WRAPPERS = {"Random", "CMA-ES", "ASHA", "Median", "PASHA", "LegacyGP"}


def _random():
    from hponas import Knob, RandomSearcher, SearchSpace

    target = RandomSearcher(SearchSpace([Knob("rate", "continuous", (1e-5, 1e-1), transform="log"),
                                         Knob("batch", "ordinal", (64, 512))]), seed=31)
    points = np.random.RandomState(31).uniform(size=(64, 2))
    expected = [[float(np.exp(np.log(1e-5) + x * (np.log(1e-1) - np.log(1e-5)))),
                 min(512, int(64 + y * 449))] for x, y in points]
    configs = [target.suggest().values for _ in points]
    return {"component": "Random", "reference": "numpy.RandomState_physical_sampling",
            "actual": [[c["rate"], c["batch"]] for c in configs], "reference_values": expected}


def _cmaes():
    import optuna
    from hponas import CMAESSearcher, Knob, Result, SearchSpace

    space = SearchSpace([Knob("rate", "continuous", (1e-5, 1e-1), transform="log"),
                         Knob("width", "continuous", (-3.0, 5.0))])
    ours = CMAESSearcher(space, seed=23)
    vendor = optuna.create_study(direction="minimize", sampler=optuna.samplers.CmaEsSampler(seed=23))
    actual, expected = [], []
    for index in range(40):
        config = ours.suggest()
        trial = vendor.ask()
        u, v = trial.suggest_float("rate", 0.0, 1.0), trial.suggest_float("width", 0.0, 1.0)
        ref = {"rate": math.exp(math.log(1e-5) + u * math.log(1e4)), "width": -3 + 8 * v}
        value = -(math.log10(config["rate"]) + 3) ** 2 - config["width"] ** 2
        ref_value = -(math.log10(ref["rate"]) + 3) ** 2 - ref["width"] ** 2
        ours.trials[str(index)] = config
        ours.observe(Result(str(index), value))
        vendor.tell(trial, -ref_value)
        actual.append([config["rate"], config["width"], value])
        expected.append([ref["rate"], ref["width"], ref_value])
    return {"component": "CMA-ES", "reference": "optuna.CmaEsSampler",
            "actual": actual, "reference_values": expected}


def _schedulers():
    from hponas.schedulers import ASHAConfig, ASHAScheduler, PASHAConfig, PASHAScheduler
    from tests.fixtures.pasha_reference_cases import REFERENCE

    ref = promotion_reference()
    actual, expected = [], []
    for values in ([], [0], [0, 1], [1] * 4, list(range(7))):
        scheduler = ASHAScheduler(ASHAConfig(r_max=9))
        rows = [(str(i), v) for i, v in enumerate(values)]
        for tid, value in rows:
            scheduler.report(tid, 1, value)
        promotions = []
        while promoted := scheduler.promote():
            promotions.extend([list(p) for p in promoted])
        actual.append(promotions)
        expected.append(reference_promotions(rows, ref))
    checks = [{"component": "ASHA", "reference": "syne_tune_0_13_0",
               "actual": actual, "reference_values": expected}]
    actual, expected = [], []
    for case in REFERENCE["cases"]:
        scheduler = PASHAScheduler(PASHAConfig(r_min=1, r_max=27, ranking_epsilon=case["epsilon"]))
        for i, score in enumerate(case["previous"]):
            scheduler.report(str(i), 1, score)
        scheduler._rung_populations[1] = [(str(i), float(rank)) for rank, i in enumerate(case["top_order"])]
        scheduler._maybe_increase_resources()
        actual.append(scheduler.current_max_fidelity)
        expected.append(9 if case["increase"] else 3)
    actual_promotion, expected_promotion = [], []
    published = pasha_reference()
    for batches in ([[0]], [[0, 1]], [[1] * 4], [[0, 1, 2, 3], [100, 101, 102]]):
        scheduler = PASHAScheduler(PASHAConfig())
        reference = published["PASHARungSystem"]([1, 3, 9], [1/3] * 3, "loss", "min", "step", 27)
        index = 0
        for values in batches:
            for value in values:
                tid = str(index)
                scheduler.report(tid, 1, value)
                reference.on_task_add(tid, 0)
                reference.on_task_report(tid, {"step": 1, "loss": value}, 0)
                reference.on_task_remove(tid)
                index += 1
            ours, theirs = [], []
            while promoted := scheduler.promote():
                ours.extend([list(p) for p in promoted])
            while promoted := reference.on_task_schedule("unused"):
                theirs.append([promoted["trial_id"], promoted["milestone"]])
            actual_promotion.append(ours)
            expected_promotion.append(theirs)
    checks.append({"component": "PASHA", "reference": REFERENCE["reference"],
                   "actual": {"soft_ranking": actual, "promotion": actual_promotion},
                   "reference_values": {"soft_ranking": expected, "promotion": expected_promotion}})
    scheduler = ASHAScheduler(ASHAConfig(r_min=4, r_max=4, median_stopping=True, report_grid=(1, 2, 3, 4)))
    for i in range(5):
        for step in range(1, 5):
            scheduler.report(f"reference-{i}", step, 5, is_progress=True)
        scheduler.finish(f"reference-{i}", "completed")
    # Hand-derived running means against five completed curves of constant 5.
    actual = [scheduler.report("equal", 1, 5, is_progress=True),
              scheduler.report("worse", 1, 6, is_progress=True),
              scheduler.report("missing-prefix", 2, 1000, is_progress=True)]
    checks.append({"component": "Median", "reference": "completed_reference_running_mean_spec",
                   "actual": actual, "reference_values": ["continue", "stop", "continue"]})
    return checks


def _legacy_gp():
    import torch
    from botorch.models import SingleTaskGP
    from botorch.fit import fit_gpytorch_mll
    from botorch.acquisition import qLogExpectedImprovement
    from botorch.optim import optimize_acqf
    from botorch.sampling.normal import SobolQMCNormalSampler
    from gpytorch.kernels import MaternKernel, ScaleKernel
    from gpytorch.priors import GammaPrior
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from scipy.stats import qmc
    from hponas import Knob, SearchSpace
    from hponas.searchers_gp import GPqLogEISearcher

    seed = 19
    ours = GPqLogEISearcher(SearchSpace([Knob("x", "continuous", (0.0, 1.0)),
                                        Knob("y", "continuous", (0.0, 1.0))]), seed=seed)
    actual = ours.propose(4)
    xs = qmc.Sobol(2, scramble=True, seed=seed).random(4)
    for config in actual:
        ours.observe({"config": config, "value": -(config["x"] - 0.3) ** 2 - (config["y"] - 0.7) ** 2})
    proposal = ours.propose(1)[0]
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        X = torch.tensor(xs, dtype=torch.float64)
        Y = -((X - torch.tensor([0.3, 0.7], dtype=torch.float64)) ** 2).sum(dim=1, keepdim=True)
        kernel = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=2,
                                          lengthscale_prior=GammaPrior(3.0, 6.0 / np.sqrt(2))))
        model = SingleTaskGP(X, Y, covar_module=kernel)
        fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
        acq = qLogExpectedImprovement(model, best_f=Y.max().item(),
                                     sampler=SobolQMCNormalSampler(torch.Size([64]), seed=seed))
        point, _ = optimize_acqf(acq, torch.tensor([[0.0, 0.0], [1.0, 1.0]], dtype=torch.float64),
                                 q=1, num_restarts=10, raw_samples=512)
    return {"component": "LegacyGP", "reference": "botorch_gamma_prior_qLogEI",
            "actual": [[c["x"], c["y"]] for c in actual] + [[proposal["x"], proposal["y"]]],
            "reference_values": xs.tolist() + point.detach().tolist()}


def wrapper_checks():
    return [_cmaes(), _random(), *_schedulers(), _legacy_gp()]


def verify_wrappers(checks):
    if len(checks) != len(WRAPPERS) or {c["component"] for c in checks} != WRAPPERS:
        raise ValueError("Complete shipped wrapper inventory required")
    for check in checks:
        a, b = check["actual"], check["reference_values"]
        if not a or not b or not check.get("reference"):
            raise ValueError("Empty wrapper reference evidence")
        if check["component"] in {"ASHA", "Median", "PASHA"}:
            if check["component"] == "PASHA" and (
                not isinstance(a, dict) or not isinstance(b, dict)
                or set(a) != {"soft_ranking", "promotion"} or set(b) != set(a)
                or len(a["soft_ranking"]) != 144 or len(a["promotion"]) != 5
            ):
                raise ValueError("PASHA requires both cap and promotion reference evidence")
            if a != b:
                return False
        else:
            actual, expected = np.asarray(a), np.asarray(b)
            if (actual.shape != expected.shape or not np.isfinite(actual).all()
                    or not np.isfinite(expected).all() or not np.allclose(actual, expected, rtol=1e-10, atol=1e-12)):
                return False
    return True
