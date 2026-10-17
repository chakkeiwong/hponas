"""Objective direction and observed incumbent reach the actual qLogEI model."""

import pytest
import torch
from botorch.acquisition import qLogExpectedImprovement

from hponas import Config, GPSearcher, Knob, Result, SearchSpace
import hponas.searchers.gp_searcher as implementation


@pytest.mark.parametrize("maximize,incumbent", [(True, 7.), (False, 3.)])
def test_qlogei_receives_direction_normalized_valid_observations(monkeypatch, maximize, incumbent):
    searcher = GPSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]),
                          seed=3, initial_random_samples=2, maximize=maximize)
    for tid, x, y, status in [("a", .1, -3., "completed"), ("b", .7, 7., "completed"), ("failed", .5, 1000., "failed")]:
        searcher.trials[tid] = Config({"x": x})
        searcher.observe(Result(tid, y, status=status))
    # Keep real model/transform/acquisition construction; fitting is immaterial
    # to verifying which observations and objective direction the wrapper uses.
    monkeypatch.setattr(implementation, "fit_gpytorch_mll", lambda mll: None)

    def optimize(acquisition, **options):
        assert isinstance(acquisition, qLogExpectedImprovement)
        assert acquisition.best_f.item() == incumbent
        model = acquisition.model
        observed = model.outcome_transform.untransform(model.train_targets.unsqueeze(-1))[0]
        assert observed.flatten().tolist() == pytest.approx([-3., 7.] if maximize else [3., -7.])
        assert model.train_inputs[0].flatten().tolist() == pytest.approx([.1, .7])
        points = torch.tensor([[[.25]], [[.6]]], dtype=torch.float64, requires_grad=True)
        values = acquisition(points)
        assert torch.isfinite(values).all()
        gradient = torch.autograd.grad(values.sum(), points)[0]
        assert torch.isfinite(gradient).all()
        assert options["q"] == 1
        return points.detach()[0], values.detach()[0]

    monkeypatch.setattr(implementation, "optimize_acqf", optimize)
    assert searcher.suggest().values == {"x": .25}
