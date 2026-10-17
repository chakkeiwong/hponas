"""The production GP uses Matérn 5/2 on normalized, warped coordinates."""

import math

import pytest
import torch

from hponas import Config, GPSearcher, Knob, Result, SearchSpace
import hponas.searchers.gp_searcher as implementation


@pytest.mark.parametrize("dimension", [1, 3])
def test_production_covariance_matches_matern_equation(monkeypatch, dimension):
    space = SearchSpace([Knob(f"x{i}", "continuous", (1e-5, 1e-1), transform="log") for i in range(dimension)])
    searcher = GPSearcher(space, seed=1, initial_random_samples=2)
    for i, value in enumerate([1e-4, 1e-2]):
        searcher.trials[str(i)] = Config({k.name: value for k in space.knobs})
        searcher.observe(Result(str(i), float(i)))
    models = []
    monkeypatch.setattr(implementation, "fit_gpytorch_mll", lambda mll: models.append(mll.model))
    monkeypatch.setattr(implementation, "optimize_acqf", lambda *a, **kw: (torch.full((1, dimension), .5), torch.tensor(0.)))
    searcher.suggest()
    model = models[0]
    xs = model.train_inputs[0]
    assert xs.tolist() == [[pytest.approx(.25)] * dimension, [pytest.approx(.75)] * dimension]
    kernel = model.covar_module
    length = kernel.base_kernel.lengthscale.detach()
    distance = torch.linalg.vector_norm((xs[0] - xs[1]) / length)
    expected = kernel.outputscale * (1 + math.sqrt(5) * distance + 5 * distance**2 / 3) * torch.exp(-math.sqrt(5) * distance)
    actual = kernel(xs).to_dense()
    assert actual[0, 1].item() == pytest.approx(expected.item(), rel=1e-10)
    assert torch.allclose(actual.diagonal(), kernel.outputscale.expand(2))
    assert torch.allclose(actual, actual.T)
