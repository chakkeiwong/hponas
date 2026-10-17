"""Synthetic wiring diagnostics for the shipped Tier 0 wrapper inventory.

The registered tabular multi-task equivalence campaign still needs a certified
task suite and divergence bands. Thirty adaptive trials are not thirty studies.
"""

from __future__ import annotations
import numpy as np


def objective(config):
    return -((config["x0"] - 0.3) ** 2) - (config["x1"] - 0.7) ** 2


def campaign():
    import torch

    previous_threads = torch.get_num_threads()
    try:
        # Use the same declared numerical execution recipe for both arms.
        torch.set_num_threads(1)
        return _campaign()
    finally:
        torch.set_num_threads(previous_threads)


def _campaign():
    import optuna
    import torch
    from scipy.stats import qmc
    from botorch.models import SingleTaskGP
    from botorch.models.utils.gpytorch_modules import get_covar_module_with_dim_scaled_prior
    from botorch.fit import fit_gpytorch_mll
    from botorch.acquisition import qLogExpectedImprovement
    from botorch.optim import optimize_acqf
    from gpytorch.kernels import ScaleKernel
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from hponas import Knob, SearchSpace, SobolSearcher, GPSearcher, Result
    from hponas.searchers_tpe import TPESearcher

    space = SearchSpace(
        [Knob("x0", "continuous", (0.0, 1.0)), Knob("x1", "continuous", (0.0, 1.0))]
    )
    sobol_space = SearchSpace(
        [Knob(f"x{i}", "continuous", (0.0, 1.0)) for i in range(5)]
    )
    sobol = SobolSearcher(sobol_space, seed=42)
    ours = np.array([list(sobol.suggest().values.values()) for _ in range(1000)])
    reference = qmc.Sobol(5, scramble=True, seed=42).random(1000)
    comparisons = [
        {
            "component": "Sobol",
            "dimension": d,
            "reference": "scipy",
            "actual": ours[:, d].tolist(),
            "reference_values": reference[:, d].tolist(),
        }
        for d in range(5)
    ]
    tpe = TPESearcher(space, seed=42)
    vendor = optuna.create_study(
        direction="minimize", sampler=optuna.samplers.TPESampler(seed=42)
    )
    actual, expected = [], []
    for _ in range(30):
        config = tpe.propose(1)[0]
        value = objective(config)
        tpe.observe({"config": config, "value": value})
        actual.append(value)
        trial = vendor.ask()
        v = objective(
            {name: trial.suggest_float(name, 0.0, 1.0) for name in ("x0", "x1")}
        )
        vendor.tell(trial, -v)
        expected.append(v)
    comparisons.append(
        {
            "component": "TPE",
            "reference": "optuna",
            "actual": actual,
            "reference_values": expected,
        }
    )
    gp = GPSearcher(space, seed=43)
    rng = np.random.RandomState(43)
    actual, expected, xs = [], [], []
    for index in range(30):
        config = gp.suggest()
        tid = str(index)
        gp.trials[tid] = config
        value = objective(config.values)
        gp.observe(Result(tid, value, 0.0))
        actual.append(value)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(43 + index)
            if index < 5:
                x = rng.uniform(size=2)
            else:
                X = torch.tensor(np.array(xs), dtype=torch.float64)
                Y = torch.tensor(expected, dtype=torch.float64).unsqueeze(-1)
                model = SingleTaskGP(
                    X, Y, covar_module=ScaleKernel(
                        get_covar_module_with_dim_scaled_prior(
                            ard_num_dims=2, use_rbf_kernel=False
                        )
                    )
                )
                fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
                acq = qLogExpectedImprovement(model, best_f=Y.max().item())
                point, _ = optimize_acqf(
                    acq,
                    bounds=torch.tensor([[0.0, 0.0], [1.0, 1.0]], dtype=torch.float64),
                    q=1,
                    num_restarts=10,
                    raw_samples=512,
                )
                x = point[0].detach().numpy()
            xs.append(x)
            expected.append(objective(dict(zip(("x0", "x1"), x))))
    comparisons.append(
        {
            "component": "GP",
            "reference": "botorch",
            "actual": actual,
            "reference_values": expected,
        }
    )
    from validation.v01_wrapper_checks import wrapper_checks

    return {"validation_id": "V01", "schema_version": 1, "comparisons": comparisons,
            "evidence_kind": "synthetic_wrapper_wiring", "certifies_acceptance": False,
            "wrapper_checks": wrapper_checks(),
            "acceptance_gaps": ["Pinned multiple tabular tasks", "Declared stochastic equivalence bands",
                                "Up to 30 independent optimizer runs with final and anytime endpoints"]}
