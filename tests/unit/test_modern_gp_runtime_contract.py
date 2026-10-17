"""Public GP CPU isolation, seed-zero and restored-state refusal contracts."""

import copy
import json
from unittest.mock import patch

import numpy as np
import pytest
import torch

from hponas.searchers.gp_searcher import GPSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Parameter, ParameterType, SearchSpace as ParameterSpace
from hponas.types import Config, Result
import hponas.searchers.gp_searcher as implementation


def space():
    return SearchSpace([Knob("x", "continuous", (0., 1.))])


def test_zero_seed_produces_the_independent_random_sequence_without_changing_caller_rng():
    target = GPSearcher(space(), seed=0)
    reference = np.random.RandomState(0)
    caller = torch.get_rng_state().clone()
    for index in range(3):
        assert target.suggest().values == {"x": reference.uniform(0., 1.)}
        assert target.get_state()["n_suggestions"] == index + 1
        assert torch.equal(torch.get_rng_state(), caller)


def test_suggestion_uses_one_numerical_thread_and_restores_the_caller_setting():
    domain = space()
    target = GPSearcher(domain, seed=17)
    sample = domain.sample_config
    observed = []

    def monitored_sample(*args, **kwargs):
        observed.append(torch.get_num_threads())
        return sample(*args, **kwargs)

    before = torch.get_num_threads()
    try:
        torch.set_num_threads(3)
        with patch.object(domain, "sample_config", monitored_sample):
            assert 0 <= target.suggest().values["x"] <= 1
        assert observed == [1]
        assert torch.get_num_threads() == 3
    finally:
        torch.set_num_threads(before)


def test_cpu_suggestion_does_not_require_initializing_unavailable_accelerator_rng():
    target = GPSearcher(space(), seed=0)
    with patch.object(torch.accelerator, "current_accelerator", return_value=None), \
            patch.object(torch.cuda, "device_count", return_value=1), \
            patch.object(torch.cuda, "get_rng_state", side_effect=RuntimeError("unavailable accelerator RNG")):
        assert 0 <= target.suggest().values["x"] <= 1


@pytest.mark.parametrize("seed", [-1, "invalid", .5])
def test_invalid_restored_seed_is_refused_before_suggestion_state_or_caller_rng_changes(seed):
    target = GPSearcher(space(), seed=17)
    state = target.get_state()
    state["seed"] = seed
    target.set_state(state)
    before = copy.deepcopy(target.get_state())
    caller, threads = torch.get_rng_state().clone(), torch.get_num_threads()
    with pytest.raises(RuntimeError) as caught:
        target.suggest()
    assert str(caught.value) == f"Invalid seed state: {seed}"
    assert target.get_state() == before
    assert torch.equal(torch.get_rng_state(), caller)
    assert torch.get_num_threads() == threads


def test_legacy_parameter_space_receives_reproducible_independent_sampling_seeds():
    domain = ParameterSpace({"x": Parameter("x", ParameterType.CONTINUOUS, bounds=(-2., 4.))})
    target = GPSearcher(domain, seed=19)
    seeds = np.random.RandomState(19)
    for _ in range(3):
        expected = domain.sample_random(seed=int(seeds.randint(0, 2**31)))
        assert target.suggest().values == expected.values


def test_replacing_public_space_with_an_unsupported_sampler_has_an_actionable_refusal():
    target = GPSearcher(space(), seed=1)
    target.search_space = object()
    with pytest.raises(TypeError) as caught:
        target.suggest()
    assert str(caught.value) == "SearchSpace must have either sample_random() or sample_config() method"


@pytest.mark.parametrize("maximize", [True, False])
def test_fitted_proposal_uses_the_fixed_acquisition_budget_and_correct_objective_direction(maximize):
    target = GPSearcher(space(), seed=3, initial_random_samples=2, num_restarts=3, maximize=maximize)
    for index, (x, value) in enumerate(((.1, -2.), (.9, 3.))):
        target.trials[str(index)] = Config({"x": x})
        target.observe(Result(str(index), value))
    calls = []

    def optimize(acquisition, *, bounds, q, num_restarts, raw_samples):
        # Observe the existing fixed numerical recipe at its library boundary.
        # One extra raw sample changes the acquisition search and RNG budget.
        assert q == 1 and num_restarts == 3 and raw_samples == 512
        assert acquisition.best_f.item() == (3. if maximize else 2.)
        torch.testing.assert_close(bounds, torch.tensor([[0.], [1.]], dtype=torch.float64))
        calls.append(acquisition)
        return torch.tensor([[.625]], dtype=torch.float64), torch.tensor(0.)

    with patch.object(implementation, "fit_gpytorch_mll", lambda mll: mll), \
            patch.object(implementation, "optimize_acqf", optimize):
        assert target.suggest().values == {"x": .625}
    assert len(calls) == 1
    assert target.get_state()["n_suggestions"] == 1


def test_legacy_checkpoint_defaults_restore_maximization_and_history_based_suggestion_count():
    original = GPSearcher(space(), seed=13)
    original.observe(Result("observed", .4))
    checkpoint = original.get_state()
    del checkpoint["maximize"]
    del checkpoint["n_suggestions"]
    restored = GPSearcher(space(), seed=99, maximize=False)
    restored.set_state(json.loads(json.dumps(checkpoint)))
    actual = restored.get_state()
    assert actual["maximize"] is True
    assert actual["n_suggestions"] == 1
    assert restored.suggest().values == original.suggest().values


def test_serialized_numpy_state_preserves_the_cached_normal_field_separately_from_its_flag():
    target = GPSearcher(space(), seed=13)
    rng = np.random.RandomState(17)
    rng.normal()
    name, values, index, has_gauss, cached = rng.get_state()
    checkpoint = target.get_state()
    expected = [name, values.tolist(), index, has_gauss, cached]
    checkpoint["rng_state"] = expected
    target.set_state(json.loads(json.dumps(checkpoint)))
    assert json.loads(json.dumps(target.get_state()["rng_state"])) == expected
    assert target.suggest().values == {"x": rng.uniform(0., 1.)}
