"""The production GP must carry the roadmap's dimension-scaled prior."""

import math

import pytest
import torch
from gpytorch.priors import LogNormalPrior

from hponas import Config, GPSearcher, Knob, Result, SearchSpace
import hponas.searchers.gp_searcher as implementation


@pytest.mark.parametrize("dimension", [1, 4, 16])
def test_prior_is_attached_to_the_model_used_for_acquisition(monkeypatch, dimension):
    space = SearchSpace([Knob(f"x{i}", "continuous", (0., 1.)) for i in range(dimension)])
    target = GPSearcher(space, seed=9, initial_random_samples=2)
    for i in range(2):
        target.trials[str(i)] = Config({k.name: 0.2 + i * 0.4 for k in space.knobs})
        target.observe(Result(str(i), float(i)))
    fitted = []
    monkeypatch.setattr(implementation, "fit_gpytorch_mll", lambda mll: fitted.append(mll.model))

    def inspect_acquisition(acq, **kwargs):
        assert acq.model is fitted[0]
        kernel = acq.model.covar_module.base_kernel
        assert kernel.nu == 2.5
        assert kernel.ard_num_dims == dimension
        prior = kernel.lengthscale_prior
        assert isinstance(prior, LogNormalPrior)
        # Independent published parameterization: median proportional to sqrt(d).
        assert prior.loc.item() == pytest.approx(math.sqrt(2) + math.log(dimension) / 2)
        assert prior.scale.item() == pytest.approx(math.sqrt(3))
        assert prior.icdf(torch.tensor(.5)).item() / math.sqrt(dimension) == pytest.approx(math.exp(math.sqrt(2)))
        assert kernel.lengthscale.detach().flatten().tolist() == pytest.approx(
            [math.exp(math.sqrt(2) + math.log(dimension) / 2 - 3)] * dimension
        )
        return torch.full((1, dimension), .5, dtype=torch.float64), torch.tensor(0.)

    monkeypatch.setattr(implementation, "optimize_acqf", inspect_acquisition)
    assert target.suggest().values == {k.name: .5 for k in space.knobs}
