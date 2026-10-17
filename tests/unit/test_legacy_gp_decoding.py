"""Independent numeric oracle and public regression for inverse decoding."""

from decimal import Decimal, localcontext
import math

import numpy as np
import pytest
import torch

from hponas.searchers_gp import GPqLogEISearcher
from hponas.space import Knob, SearchSpace


@pytest.mark.parametrize("low,high,transform", [
    (-.3, .7, "none"), (-10., .1, "none"),
    (.0001, .1, "log"), (1e-200, 1e200, "log"),
])
@pytest.mark.parametrize("unit", [0., np.nextafter(0., 1.), .125, .5, .875, np.nextafter(1., 0.), 1.])
def test_gp_inverse_stays_in_declared_bounds_and_matches_high_precision_oracle(low, high, transform, unit):
    space = SearchSpace([Knob("x", "continuous", (low, high), transform=transform)])
    searcher = GPqLogEISearcher(space, seed=13)
    config = searcher._from_unit_cube(torch.tensor([unit], dtype=torch.float64))
    space.validate_config(config)
    with localcontext() as context:
        context.prec = 80
        a, b, u = map(Decimal.from_float, (low, high, float(unit)))
        expected = (a + u * (b - a) if transform == "none"
                    else ((1 - u) * a.ln() + u * b.ln()).exp())
    assert math.isclose(config["x"], float(expected), rel_tol=2e-13, abs_tol=0.)
    if unit == 0.:
        assert config["x"] == low
    if unit == 1.:
        assert config["x"] == high


def test_gp_public_proposal_can_be_validated_and_observed_at_a_log_boundary():
    space = SearchSpace([
        Knob("x", "continuous", (0., 1.)),
        Knob("rate", "continuous", (.0001, .1), transform="log"),
    ])
    searcher = GPqLogEISearcher(space, seed=13, n_fantasies=4,
                              raw_samples=8, n_restarts=1, prior_beta=.5)
    searcher.propose(2)
    searcher.observe({"config": {"x": 0., "rate": .0001}, "value": -2.})
    searcher.observe({"config": {"x": 1., "rate": .1}, "value": 3.})
    config = searcher.propose(1)[0]
    space.validate_config(config)
    searcher.observe({"config": config, "value": -1.})
    assert searcher.state_dict()["n_observed"] == 3
