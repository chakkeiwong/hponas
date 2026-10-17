"""Independent wrapper/vendor loops over a declared projected finite table.

These trace primitives support the explicitly scoped finite-corpus V01 gate.
Their own reports remain engineering evidence; they never certify an entire
corpus or equality in distribution. No workload training occurs here.
"""

from __future__ import annotations

import importlib.metadata

import numpy as np

from validation.tabular_projection import FiniteLandscapeProjection

SEARCHERS = ("Random", "Sobol", "TPE", "CMA-ES", "GP", "LegacyGP")


def _wrapper(component, dimension, seed):
    from hponas import CMAESSearcher, GPSearcher, Knob, RandomSearcher, Result, SearchSpace, SobolSearcher
    from hponas.searchers.adapter import LegacySearcherAdapter
    from hponas.searchers_gp import GPqLogEISearcher
    from hponas.searchers_tpe import TPESearcher

    space = SearchSpace([Knob(f"x{i}", "continuous", (0.0, 1.0)) for i in range(dimension)])
    factories = {"Random": RandomSearcher, "Sobol": SobolSearcher, "GP": GPSearcher,
                 "CMA-ES": CMAESSearcher}
    if component == "TPE":
        searcher = LegacySearcherAdapter(TPESearcher(space, seed=seed))
    elif component == "LegacyGP":
        searcher = GPqLogEISearcher(space, seed=seed)
    else:
        searcher = factories[component](space, seed=seed)

    def suggest():
        config = searcher.propose(1)[0] if component == "LegacyGP" else searcher.suggest().values
        return [config[f"x{i}"] for i in range(dimension)]

    def observe(index, point, value):
        config = {f"x{i}": v for i, v in enumerate(point)}
        if component == "LegacyGP":
            searcher.observe({"config": config, "value": value})
        else:
            from hponas import Config

            searcher.trials[str(index)] = Config(config)
            searcher.observe(Result(str(index), value))

    return suggest, observe


def _vendor(component, dimension, seed):
    """Independent vendor state; no wrapper configs, histories or fitting helpers."""
    from scipy.stats import qmc

    if component in {"Random", "Sobol"}:
        generator = (np.random.RandomState(seed) if component == "Random"
                     else qmc.Sobol(dimension, scramble=True, seed=seed))
        return (lambda: (generator.uniform(size=dimension) if component == "Random"
                         else generator.random(1)[0]).tolist()), lambda *args: None
    if component in {"TPE", "CMA-ES"}:
        import optuna

        sampler = (optuna.samplers.TPESampler if component == "TPE" else optuna.samplers.CmaEsSampler)(seed=seed)
        study = optuna.create_study(direction="minimize", sampler=sampler)
        pending = []

        def suggest():
            trial = study.ask()
            pending.append(trial)
            return [trial.suggest_float(f"x{i}", 0.0, 1.0) for i in range(dimension)]

        def observe(index, point, value):
            study.tell(pending.pop(0), -value)

        return suggest, observe

    import torch
    from botorch.acquisition import qLogExpectedImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.models.utils.gpytorch_modules import get_covar_module_with_dim_scaled_prior
    from botorch.optim import optimize_acqf
    from botorch.sampling.normal import SobolQMCNormalSampler
    from gpytorch.kernels import MaternKernel, ScaleKernel
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from gpytorch.priors import GammaPrior

    points, values = [], []
    rng = np.random.RandomState(seed)
    initial = qmc.Sobol(dimension, scramble=True, seed=seed)
    stream = [torch.Generator().manual_seed(seed).get_state()]

    def suggest():
        count = len(points)
        if component == "GP" and count < 5:
            return rng.uniform(size=dimension).tolist()
        if component == "LegacyGP" and count == 0:
            return initial.random(1)[0].tolist()
        with torch.random.fork_rng(devices=[]):
            if component == "GP":
                torch.manual_seed(seed + count)
            else:
                torch.set_rng_state(stream[0])
            X = torch.tensor(points, dtype=torch.float64)
            Y = torch.tensor(values, dtype=torch.float64).unsqueeze(-1)
            kernel = (get_covar_module_with_dim_scaled_prior(ard_num_dims=dimension, use_rbf_kernel=False)
                      if component == "GP" else MaternKernel(nu=2.5, ard_num_dims=dimension,
                                  lengthscale_prior=GammaPrior(3.0, 6.0 / np.sqrt(dimension))))
            model = SingleTaskGP(X, Y, covar_module=ScaleKernel(kernel))
            fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
            options = {} if component == "GP" else {
                "sampler": SobolQMCNormalSampler(torch.Size([64]), seed=seed)}
            acquisition = qLogExpectedImprovement(model, best_f=Y.max().item(), **options)
            proposal, _ = optimize_acqf(acquisition,
                bounds=torch.tensor([[0.0] * dimension, [1.0] * dimension], dtype=torch.float64),
                q=1, num_restarts=10, raw_samples=512)
            if component == "LegacyGP":
                stream[0] = torch.get_rng_state().clone()
            return proposal[0].detach().tolist()

    def observe(index, point, value):
        points.append(list(point))
        values.append(value)

    return suggest, observe


def _trace(projection, actor, *, optimizer_seed, table_seed, training_steps, count):
    suggest, observe = actor
    rows = []
    for index in range(count):
        point = suggest()
        cell = projection.evaluate(point, seed=table_seed, training_steps=training_steps)
        rows.append({"index": index, **cell})
        if cell["status"] != "finite":
            # An external missing cell is never imputed or replaced. Halt this
            # diagnostic; it cannot silently become a complete adaptive trace.
            break
        observe(index, point, cell["value"])
    return {"optimizer_seed": optimizer_seed, "table_seed": table_seed, "training_steps": training_steps,
            "requested_count": count, "rows": rows,
            "status": "complete" if len(rows) == count and rows[-1]["status"] == "finite" else "unresolved_cell"}


def compare_table_traces(projection: FiniteLandscapeProjection, component, *, optimizer_seed,
                         table_seed, training_steps, count):
    """Run both actors independently on identical geometry/recorded-cell recipes.

    CPU double precision and one Torch thread are explicit. Vendor outcomes are
    obtained from vendor proposals, never copied from the wrapper. Count bounds
    are engineering controls, not the registered number of independent studies.
    """
    if (component not in SEARCHERS or type(count) is not int or not 1 <= count <= 50
            or type(optimizer_seed) is not int or not 0 <= optimizer_seed < 2**31):
        raise ValueError("Known searcher, bounded diagnostic count and optimizer seed required")
    import torch

    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        dimension = len(projection.coordinates)
        options = dict(optimizer_seed=optimizer_seed, table_seed=table_seed,
                       training_steps=training_steps, count=count)
        actual = _trace(projection, _wrapper(component, dimension, optimizer_seed), **options)
        expected = _trace(projection, _vendor(component, dimension, optimizer_seed), **options)
    finally:
        torch.set_num_threads(previous)
    result = {"kind": "v01_projected_table_trace", "component": component,
              "projection": projection.specification, "projection_digest": projection.digest,
              "actual": actual, "reference": expected,
              "dependencies": {name: importlib.metadata.version(name) for name in
                               ("numpy", "scipy", "torch", "botorch", "gpytorch", "optuna", "cmaes")},
              "execution": "cpu_float64_one_torch_thread",
              "claim": "coupled_trace_engineering_only", "certifies_acceptance": False,
              "verdict": "INCONCLUSIVE"}
    result["comparison"] = verify_table_traces(projection, result)
    return result


def verify_table_traces(projection, report):
    """Recompute geometry and raw outcomes, reporting exact cell disagreements.

    This is not an acceptance gate or authentication of vendor execution. Final
    V01 needs its reviewed claim, task/source freeze and execution provenance.
    """
    if (report.get("kind") != "v01_projected_table_trace" or report.get("component") not in SEARCHERS
            or report.get("projection_digest") != projection.digest
            or report.get("projection") != projection.specification):
        raise ValueError("V01 trace belongs to a different table/domain recipe")
    actual, reference = report["actual"], report["reference"]
    keys = ("optimizer_seed", "table_seed", "training_steps", "requested_count")
    if any(actual.get(key) != reference.get(key) for key in keys):
        raise ValueError("V01 wrapper/reference recipes differ")
    for trace in (actual, reference):
        rows = trace.get("rows", [])
        count = trace.get("requested_count")
        if type(count) is not int or not 1 <= len(rows) <= count <= 50:
            raise ValueError("Empty or excessive V01 trace")
        for index, row in enumerate(rows):
            expected = projection.evaluate(row["proposal"], seed=trace["table_seed"],
                                           training_steps=trace["training_steps"])
            if row != {"index": index, **expected}:
                raise ValueError("V01 trace differs from its original recorded cell")
            if row["status"] != "finite" and index != len(rows) - 1:
                raise ValueError("V01 continued past an unresolved table cell")
        status = "complete" if len(rows) == count and rows[-1]["status"] == "finite" else "unresolved_cell"
        if trace.get("status") != status or (len(rows) < count and rows[-1]["status"] == "finite"):
            raise ValueError("V01 trace silently drops planned proposals")
    pairs = list(zip(actual["rows"], reference["rows"]))
    mismatches = [a["index"] for a, b in pairs if (a["config_id"], a["status"], a["value"]) !=
                  (b["config_id"], b["status"], b["value"])]
    same_length = len(actual["rows"]) == len(reference["rows"])
    return {"exact_cell_agreement": same_length and not mismatches, "cell_mismatch_indices": mismatches,
            "equal_trace_lengths": same_length,
            "maximum_absolute_proposal_difference": max(abs(x - y) for a, b in pairs
                                                         for x, y in zip(a["proposal"], b["proposal"])),
            "complete_traces": actual["status"] == reference["status"] == "complete",
            "certifies_distributional_equivalence": False}


def reconstruct_reference(projection, report):
    """Rebuild vendor state from its seed and table, never from supplied history.

    A producer can fabricate two matching proposal/score lists. Cell lookup
    alone cannot detect that; the vendor's whole adaptive path must be rebuilt.
    This verifier does not construct the tested wrapper.
    """
    comparison = verify_table_traces(projection, report)
    recipe = report["reference"]
    seed = recipe["optimizer_seed"]
    if (type(seed) is not int or not 0 <= seed < 2**31
            or type(recipe["table_seed"]) is not int or recipe["table_seed"] not in projection.table.seeds
            or type(recipe["training_steps"]) is not int or recipe["training_steps"] not in projection.table.training_steps):
        raise ValueError("Invalid reference seed/fidelity")
    import torch

    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        rebuilt = _trace(projection, _vendor(report["component"], len(projection.coordinates), seed),
                         optimizer_seed=seed, table_seed=recipe["table_seed"],
                         training_steps=recipe["training_steps"], count=recipe["requested_count"])
    finally:
        torch.set_num_threads(previous)
    if rebuilt != recipe:
        raise ValueError("Vendor path differs from independently reconstructed reference")
    return comparison
