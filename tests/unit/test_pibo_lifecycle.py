"""Optional piBO must preserve proposals, recipe and RNG across recovery."""

import copy
import json

import numpy as np
import pytest
from scipy.stats import qmc
import torch

from hponas import Knob, SearchSpace
from hponas.searchers_gp import GPqLogEISearcher


def space(low=0., high=1.):
    return SearchSpace([Knob("x", "continuous", (low, high))])


def prior(config):
    return np.exp(-((config["x"] - .7) / .2)**2)


def searcher(seed=42, prior_fn=prior):
    return GPqLogEISearcher(space(), seed=seed, prior_fn=prior_fn,
                           n_fantasies=16, raw_samples=32, n_restarts=2)


def observe_points(s, count=4):
    for config in s.propose(count):
        s.observe({"config": config, "value": -(config["x"] - .4)**2})


def test_pending_bootstrap_matches_one_independent_sobol_stream():
    s = searcher(prior_fn=None)
    actual = s.propose(2) + s.propose(2) + s.propose(4)
    expected = qmc.Sobol(d=1, scramble=True, seed=42).random(8)
    np.testing.assert_array_equal([c["x"] for c in actual], expected[:, 0])
    assert len({c["x"] for c in actual}) == 8
    saved = json.loads(json.dumps(s.state_dict()))
    restored = searcher(seed=1, prior_fn=None)
    restored.load_state_dict(saved)
    assert restored.propose(4) == s.propose(4)


def test_fitted_prior_resume_matches_exact_trace_despite_other_searcher_activity():
    s = searcher()
    observe_points(s)
    first = s.propose(1)[0]
    s.observe({"config": first, "value": -(first["x"] - .4)**2})
    state = json.loads(json.dumps(s.state_dict()))
    expected = s.propose(1)
    unrelated = searcher(seed=91)
    observe_points(unrelated)
    unrelated.propose(2)
    torch.rand(200)
    restored = searcher(seed=19)
    restored.load_state_dict(state)
    assert restored.propose(1) == expected


def test_searcher_does_not_reseed_or_consume_callers_torch_rng():
    before = torch.get_rng_state().clone()
    s = searcher()
    assert torch.equal(torch.get_rng_state(), before)
    observe_points(s)
    s.propose(1)
    assert torch.equal(torch.get_rng_state(), before)
    restored = searcher(seed=9)
    restored.load_state_dict(json.loads(json.dumps(s.state_dict())))
    assert torch.equal(torch.get_rng_state(), before)


@pytest.mark.parametrize("field,value", [
    ("n_observed", 9), ("n_proposed", True), ("X", [[1., 2.]]),
    ("Y", [float("nan")]), ("torch_rng_state", []),
    ("torch_rng_state", [256]), ("torch_rng_state", [1, 2]),
    ("space", {"knobs": []}), ("prior_identity", "changed"),
    ("versions", {}), ("options", {}), ("schema_version", 1),
])
def test_bad_checkpoints_leave_live_searcher_unchanged(field, value):
    s = searcher()
    observe_points(s, count=1)
    before = copy.deepcopy(s.state_dict())
    bad = copy.deepcopy(before)
    bad[field] = value
    rng = torch.get_rng_state().clone()
    with pytest.raises(ValueError):
        s.load_state_dict(bad)
    assert s.state_dict() == before
    assert torch.equal(torch.get_rng_state(), rng)


def test_bounds_and_prior_mismatch_refused_and_saved_options_restored():
    s = searcher()
    state = s.state_dict()
    with pytest.raises(ValueError, match="space"):
        GPqLogEISearcher(space(10., 20.), prior_fn=prior).load_state_dict(state)
    with pytest.raises(ValueError, match="prior"):
        searcher(prior_fn=None).load_state_dict(state)
    restored = GPqLogEISearcher(space(), prior_fn=prior, prior_beta=5.)
    restored.load_state_dict(state)
    assert restored.prior_beta == s.prior_beta == 2.
    assert restored.n_fantasies == 16
    assert restored.raw_samples == 32 and restored.n_restarts == 2


def test_same_prior_name_cannot_hide_changed_function_code(monkeypatch):
    s = searcher()
    saved = s.state_dict()
    monkeypatch.setattr(prior, "__code__", (lambda config: 1.).__code__)
    with pytest.raises(ValueError, match="prior recipe"):
        s.load_state_dict(saved)


@pytest.mark.parametrize("field,value", [
    ("seed", True), ("seed", -1), ("n_fantasies", 0),
    ("raw_samples", 0), ("n_restarts", True), ("prior_beta", -1),
    ("prior_beta", float("nan")), ("prior_beta", "bad"),
])
def test_invalid_controls_are_rejected(field, value):
    with pytest.raises(ValueError):
        GPqLogEISearcher(space(), **{field: value})


@pytest.mark.parametrize("knob_specs", [
    [],
    [{"name": "x", "kind": "continuous", "bounds": (0., 1.)},
     {"name": "y", "kind": "ordinal", "bounds": (1, 3)}],
    [{"name": "x", "kind": "continuous", "bounds": (.1, .9), "transform": "logit"}],
], ids=["invalid0", "invalid1", "invalid2"])
def test_unsupported_coordinates_are_not_silently_dropped(knob_specs):
    invalid = SearchSpace([Knob(**spec) for spec in knob_specs])
    with pytest.raises(ValueError, match="unconditional continuous"):
        GPqLogEISearcher(invalid)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "bad", [2.]])
def test_invalid_observation_cannot_poison_gp_state(value):
    s = searcher()
    before = s.state_dict()
    with pytest.raises(ValueError):
        s.observe({"config": {"x": .5}, "value": value})
    assert s.state_dict() == before


@pytest.mark.parametrize("count", [True, -1, 1.5])
def test_invalid_ask_count_cannot_advance_stream(count):
    s = searcher()
    before = s.state_dict()
    with pytest.raises(ValueError):
        s.propose(count)
    assert s.propose(0) == []
    assert s.state_dict() == before
