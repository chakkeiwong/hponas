"""Prospective GP recipe, public refusal, numeric and CPU isolation contracts."""

import copy
import math
import platform
from unittest.mock import patch

import botorch
import cloudpickle
import gpytorch
import numpy as np
import pytest
import scipy
import torch

import hponas.searchers_gp as gp
from hponas.space import Knob, SearchSpace


def space():
    return SearchSpace([Knob("linear", "continuous", (-.3, .7)),
                        Knob("rate", "continuous", (.0001, .1), transform="log")])


def test_default_recipe_and_version_ledger_match_the_installed_runtime():
    target = gp.GPqLogEISearcher(space())
    state = target.state_dict()
    assert state["seed"] == 0
    assert state["options"] == {"n_fantasies": 64, "raw_samples": 512, "n_restarts": 10, "prior_beta": 2.}
    assert state["versions"] == {
        "python": platform.python_version(), "torch": str(torch.__version__),
        "botorch": botorch.__version__, "gpytorch": gpytorch.__version__,
        "numpy": np.__version__, "scipy": scipy.__version__, "cloudpickle": cloudpickle.__version__,
    }
    assert target.propose(2) == gp.GPqLogEISearcher(space(), seed=0).propose(2)


@pytest.mark.parametrize("seed", [True, -1, 2**32, 2**32+1, .5, None])
def test_invalid_seed_has_a_precise_closed_interval_refusal(seed):
    with pytest.raises(ValueError) as error:
        gp.GPqLogEISearcher(space(), seed=seed)
    assert str(error.value) == "seed must be an integer in [0, 2**32)"


@pytest.mark.parametrize("name", ["n_fantasies", "raw_samples", "n_restarts"])
@pytest.mark.parametrize("value", [0, -1, True, .5])
def test_invalid_acquisition_count_names_the_parameter(name, value):
    with pytest.raises(ValueError) as error:
        gp.GPqLogEISearcher(space(), **{name: value})
    assert str(error.value) == f"{name} must be a positive integer"


@pytest.mark.parametrize("value", [True, [-1.], "bad", math.nan, math.inf, -1.])
def test_invalid_prior_decay_has_a_precise_diagnostic(value):
    with pytest.raises(ValueError) as error:
        gp.GPqLogEISearcher(space(), prior_beta=value)
    assert str(error.value) == "prior_beta must be finite and nonnegative"


@pytest.mark.parametrize("seed", [0, 2**32-1])
@pytest.mark.parametrize("beta", [0., .5])
def test_smallest_controls_and_seed_endpoints_are_accepted(seed, beta):
    target = gp.GPqLogEISearcher(space(), seed=seed, n_fantasies=1, raw_samples=1, n_restarts=1, prior_beta=beta)
    assert target.state_dict()["options"] == {"n_fantasies": 1, "raw_samples": 1, "n_restarts": 1, "prior_beta": beta}
    assert len(target.propose(1)) == 1


@pytest.mark.parametrize("count", [True, -1, .5, None])
def test_invalid_proposal_count_preserves_public_state(count):
    target = gp.GPqLogEISearcher(space())
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.propose(count)
    assert str(error.value) == "n must be a nonnegative integer"
    assert target.state_dict() == before


@pytest.mark.parametrize("value", [True, [1.], "bad", math.nan, math.inf, -math.inf])
def test_invalid_observation_preserves_state_and_diagnostic(value):
    target = gp.GPqLogEISearcher(space())
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.observe({"config": {"linear": .2, "rate": .01}, "value": value})
    assert str(error.value) == "Observation value must be a finite scalar"
    assert target.state_dict() == before


def test_missing_dependency_explains_the_installation_requirement():
    with patch.object(gp, "BOTORCH_AVAILABLE", False):
        with pytest.raises(ImportError) as error:
            gp.GPqLogEISearcher(space())
    assert str(error.value) == "GPqLogEISearcher requires botorch: pip install botorch gpytorch torch"


def test_unsupported_empty_space_has_an_explicit_domain_diagnostic():
    with pytest.raises(ValueError) as error:
        gp.GPqLogEISearcher(SearchSpace([]))
    assert str(error.value) == "GPqLogEISearcher requires unconditional continuous knobs with none/log transforms"


def test_cpu_proposal_does_not_require_accelerator_rng_initialization():
    target = gp.GPqLogEISearcher(space())
    caller = torch.get_rng_state().clone()
    with patch.object(torch.accelerator, "current_accelerator", return_value=None), \
            patch.object(torch.cuda, "device_count", return_value=1), \
            patch.object(torch.cuda, "get_rng_state", side_effect=RuntimeError("unavailable accelerator RNG")):
        assert len(target.propose(1)) == 1
    assert torch.equal(caller, torch.get_rng_state())


@pytest.mark.parametrize("unit", [0., .125, .5, .875, 1.])
def test_observation_ledger_records_normalized_linear_and_log_coordinates(unit):
    target = gp.GPqLogEISearcher(space())
    config = {"linear": -.3 + unit, "rate": .0001 if unit == 0 else .1 if unit == 1 else 10 ** (-4 + 3 * unit)}
    target.observe({"config": config, "value": .125})
    state = target.state_dict()
    assert state["n_observed"] == 1 and state["Y"] == [.125]
    np.testing.assert_allclose(state["X"], [[unit, unit]], rtol=0, atol=3e-16)
