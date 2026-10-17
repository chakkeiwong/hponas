"""Prospective recovery contracts, kept outside attempt 07's frozen tests."""

import copy
import json

import numpy as np
import pytest
import torch

from hponas.searchers_gp import GPqLogEISearcher
from hponas.space import Knob, SearchSpace


def searcher(seed=13):
    space = SearchSpace([
        Knob("x", "continuous", (0., 1.)),
        Knob("rate", "continuous", (.0001, .1), transform="log"),
    ])
    return GPqLogEISearcher(space, seed=seed, n_fantasies=4,
                          raw_samples=8, n_restarts=1, prior_beta=.5)


def observed_searcher():
    target = searcher()
    target.propose(2)
    target.observe({"config": {"x": 0., "rate": .0001}, "value": -2.})
    target.observe({"config": {"x": 1., "rate": .1}, "value": 3.})
    return target


CASES = [
    ("kind", "random", "GPqLogEISearcher cannot load state of kind 'random'"),
    ("schema_version", 1, "Incomplete legacy GP checkpoint; explicit migration required"),
    ("space", {"knobs": []}, "Searcher state does not match space"),
    ("knob_names", ["rate", "x"], "Searcher state does not match space"),
    ("prior_identity", "different", "Checkpoint prior recipe differs"),
    ("versions", {}, "Checkpoint dependency versions differ"),
    ("options", {}, "Incomplete acquisition options"),
    ("n_observed", -1, "Invalid checkpoint counts"),
    ("n_observed", True, "Invalid checkpoint counts"),
    ("n_proposed", -1, "Invalid checkpoint counts"),
    ("n_proposed", True, "Invalid checkpoint counts"),
    ("n_proposed", 2.5, "Invalid checkpoint counts"),
    ("X", [[0., 0.]], "Checkpoint observation counts differ"),
    ("Y", [-2.], "Checkpoint observation counts differ"),
    ("X", [[0.], [1.]], "Invalid checkpoint coordinates"),
    ("X", [[[0., 0.]], [[1., 1.]]], "Invalid checkpoint coordinates"),
    ("X", [[-.1, 0.], [1., 1.]], "Invalid checkpoint coordinates"),
    ("X", [[0., 0.], [1.5, 1.]], "Invalid checkpoint coordinates"),
    ("X", [[float("nan"), 0.], [1., 1.]], "Invalid checkpoint coordinates"),
    ("X", [[float("inf"), 0.], [1., 1.]], "Invalid checkpoint coordinates"),
    ("Y", [[-2.], [3.]], "Invalid checkpoint objectives"),
    ("Y", [float("nan"), 3.], "Invalid checkpoint objectives"),
    ("Y", [float("inf"), 3.], "Invalid checkpoint objectives"),
    ("torch_rng_state", [], "Invalid checkpoint RNG state"),
    ("torch_rng_state", (), "Invalid checkpoint RNG state"),
    ("torch_rng_state", [True], "Invalid checkpoint RNG state"),
    ("torch_rng_state", [-1], "Invalid checkpoint RNG state"),
    ("torch_rng_state", [256], "Invalid checkpoint RNG state"),
    ("torch_rng_state", [1.5], "Invalid checkpoint RNG state"),
    ("torch_rng_state", [1, 2], "Invalid GP checkpoint"),
]


@pytest.mark.parametrize("field,value,message", CASES)
def test_gp_checkpoint_refusal_is_precise_and_preserves_live_state(field, value, message):
    target = observed_searcher()
    before = copy.deepcopy(target.state_dict())
    invalid = copy.deepcopy(before)
    invalid[field] = copy.deepcopy(value)
    rng_before = torch.get_rng_state().clone()
    with pytest.raises(ValueError) as failure:
        target.load_state_dict(invalid)
    assert str(failure.value) == message
    assert target.state_dict() == before
    assert torch.equal(torch.get_rng_state(), rng_before)


def test_gp_checkpoint_accepts_endpoints_and_owns_restored_arrays():
    original = observed_searcher()
    saved = json.loads(json.dumps(original.state_dict()))
    np.testing.assert_array_equal(saved["X"], [[0., 0.], [1., 1.]])
    restored = searcher(seed=99)
    rng_before = torch.get_rng_state().clone()
    restored.load_state_dict(saved)
    assert restored.state_dict() == original.state_dict()
    assert torch.equal(torch.get_rng_state(), rng_before)
    saved["X"][0][0] = .75
    saved["Y"][1] = -99.
    saved["torch_rng_state"][0] ^= 1
    assert restored.state_dict() == original.state_dict()


def test_gp_missing_recovery_input_is_rejected_before_replacing_live_state():
    target = observed_searcher()
    before = copy.deepcopy(target.state_dict())
    invalid = copy.deepcopy(before)
    del invalid["seed"]
    with pytest.raises(ValueError) as failure:
        target.load_state_dict(invalid)
    assert str(failure.value) == "Invalid GP checkpoint"
    assert target.state_dict() == before
