"""Known acquisition optima; decay is not a finite objective-regret guarantee.

The original Branin assertions and their failures are retained unchanged in
docs/program/evidence/2026-10-08/integrated-repair-01/legacy-prior-diagnostics.
"""
import math

import pytest
import torch
from botorch.acquisition import AcquisitionFunction
from botorch.optim import optimize_acqf

from hponas.searchers_gp import PriorWeightedAcquisition
from hponas.space import Knob


class QuadraticLogAcquisition(AcquisitionFunction):
    def __init__(self):
        super().__init__(model=None)

    def forward(self, X):
        return -(X[..., 0] - 0.75).square().mean(dim=-1)


@pytest.mark.parametrize("observations,optimum", [(1, 0.0), (10, 0.25), (20, 0.5), (100, 0.7)])
def test_decaying_wrong_prior_has_known_acquisition_optimum(observations, optimum):
    bounds = torch.tensor([[0.0], [1.0]], dtype=torch.float64)
    weighted = PriorWeightedAcquisition(
        QuadraticLogAcquisition(), lambda c: math.exp(-5 * c["x"]), observations,
        2.0, bounds[0], bounds[1], [Knob("x", "continuous", (0.0, 1.0))],
    )
    candidate, score = optimize_acqf(
        weighted, bounds, q=1, num_restarts=1,
        batch_initial_conditions=torch.tensor([[[0.9]]], dtype=torch.float64),
    )
    # Completing the square gives x*=clip(3/4-5/n,0,1).
    assert candidate.item() == pytest.approx(optimum, abs=1e-5)
    assert score.item() == pytest.approx(
        -(optimum - 0.75) ** 2 - 10 * optimum / observations, abs=1e-9
    )
    # For the known objective (x-3/4)^2, even this correctly optimized
    # acquisition gives strictly positive regret at every finite n here.
    assert (candidate.item() - 0.75) ** 2 > 0
