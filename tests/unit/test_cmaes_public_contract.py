"""Prospective refusal diagnostics and unchanged public recovery state."""

import copy
from importlib.metadata import version

import pytest

from hponas import CMAESSearcher, Config, Knob, Result, SearchSpace


def test_cmaes_rejection_diagnostics_and_state_are_stable():
    target = CMAESSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=7)
    config = target.suggest()
    before = copy.deepcopy(target.get_state())
    with pytest.raises(ValueError) as error:
        target.observe(Result("unknown", 1.))
    assert str(error.value) == "CMA-ES result has no registered trial configuration"
    assert target.get_state() == before
    target.trials["a"] = config
    target.observe(Result("a", 1.))
    before = copy.deepcopy(target.get_state())
    with pytest.raises(ValueError) as error:
        target.observe(Result("a", 2.))
    assert str(error.value) == "Cannot revise an observed CMA-ES result"
    assert target.get_state() == before
    target.trials["orphan"] = Config({"x": .5})
    before = copy.deepcopy(target.get_state())
    with pytest.raises(ValueError) as error:
        target.observe(Result("orphan", 2.))
    assert str(error.value) == "CMA-ES result does not match a pending suggestion"
    assert target.get_state() == before


def test_default_seed_and_version_ledger_support_exact_recovery():
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    target, explicit = CMAESSearcher(space), CMAESSearcher(space, seed=0)
    assert target.get_state()["seed"] == 0
    assert target.get_state()["versions"] == {name: version(name) for name in ("optuna", "cmaes")}
    assert target.suggest().values == explicit.suggest().values


@pytest.mark.parametrize("seed", [True, -1, 2**32, .5, None])
def test_invalid_seed_diagnostic(seed):
    with pytest.raises(ValueError) as error:
        CMAESSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=seed)
    assert str(error.value) == "seed must be an integer in [0, 2**32)"


@pytest.mark.parametrize("direction", [None, 0, 1, "minimize"])
def test_nonboolean_direction_is_rejected_at_construction_and_before_sampling(direction):
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    with pytest.raises(ValueError) as error:
        CMAESSearcher(space, maximize=direction)
    assert str(error.value) == "maximize must be boolean"
    target = CMAESSearcher(space)
    target.maximize = direction
    before = copy.deepcopy(target.get_state())
    with pytest.raises(ValueError) as error:
        target.suggest()
    assert str(error.value) == "maximize must be boolean"
    assert target.get_state() == before


@pytest.mark.parametrize("direction", [True, False])
def test_direction_cannot_change_after_first_suggestion(direction):
    target = CMAESSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), maximize=direction)
    target.suggest()
    target.maximize = not direction
    before = copy.deepcopy(target.get_state())
    with pytest.raises(ValueError) as error:
        target.suggest()
    assert str(error.value) == "Cannot change direction after CMA-ES has started"
    assert target.get_state() == before


def test_unsupported_empty_space_reports_the_required_domain():
    with pytest.raises(ValueError) as error:
        CMAESSearcher(SearchSpace([]))
    assert str(error.value) == "CMA-ES requires a nonempty unconditional continuous space"
