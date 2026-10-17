"""Independent sampling and encoding contracts for both public space schemas."""

import json
import math

import numpy as np
import pytest
from scipy.stats import qmc

from hponas.encoding import SpaceEncoder
from hponas.searchers.random_searcher import RandomSearcher, SobolSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Parameter, ParameterType, SearchSpace as ParameterSpace


@pytest.mark.parametrize("seed", [0, 1, 7, 19, 101])
def test_legacy_log_integer_sampling_matches_the_inverse_cdf_and_stays_in_domain(seed):
    domain = ParameterSpace({"steps": Parameter("steps", ParameterType.INTEGER, (3, 91), log_scale=True)})
    u = np.random.RandomState(seed).uniform()
    expected = math.floor(math.exp(math.log(3) + u * math.log(91 / 3)))
    actual = domain.sample_random(seed)
    assert actual.values == {"steps": expected}
    assert domain.validate_config(actual)


def test_uniform_integer_sampling_includes_both_declared_endpoints():
    domain = ParameterSpace({"steps": Parameter("steps", ParameterType.INTEGER, (2, 3))})
    samples = [domain.sample_random(seed).values["steps"] for seed in range(32)]
    assert set(samples) == {2, 3}


@pytest.mark.parametrize("kind", [ParameterType.DISCRETE, ParameterType.CATEGORICAL])
def test_singleton_choices_are_valid_and_empty_choices_are_refused(kind):
    domain = ParameterSpace({"fixed": Parameter("fixed", kind, choices=["only"])})
    assert domain.sample_random(0).values == {"fixed": "only"}
    with pytest.raises(ValueError) as caught:
        Parameter("fixed", kind, choices=[])
    assert str(caught.value) == "Parameter fixed requires choices"


@pytest.mark.parametrize("scramble", [False, True])
def test_sobol_initial_proposals_use_the_requested_scrambling_before_any_recovery(scramble):
    domain = SearchSpace([Knob("x", "continuous", (-2., 3.)), Knob("y", "continuous", (0., 1.))])
    target = SobolSearcher(domain, seed=19, scramble=scramble)
    oracle = qmc.Sobol(d=2, seed=19, scramble=scramble).random_base2(2)
    for x, y in oracle:
        assert target.suggest().values == {"x": -2. + 5. * x, "y": y}
    assert target.get_state()["sample_count"] == 4


def test_random_checkpoint_preserves_cached_normal_state_as_well_as_uniform_continuation():
    domain = SearchSpace([Knob("x", "continuous", (0., 1.))])
    target = RandomSearcher(domain, seed=13)
    reference = np.random.RandomState(17)
    reference.normal()
    name, values, index, flag, cached = reference.get_state()
    expected = [name, values.tolist(), index, flag, cached]
    checkpoint = target.get_state()
    checkpoint["rng_state"] = expected
    target.set_state(json.loads(json.dumps(checkpoint)))
    assert json.loads(json.dumps(target.get_state()["rng_state"])) == expected
    assert target.suggest().values == {"x": reference.uniform()}


@pytest.mark.parametrize("searcher,message", [
    (SobolSearcher, "SearchSpace must have either parameters or knobs attribute"),
    (RandomSearcher, "SearchSpace must have either sample_random() or sample_config() method"),
])
def test_unsupported_space_refusal_names_the_required_public_interface(searcher, message):
    with pytest.raises(TypeError) as caught:
        searcher(object(), seed=0).suggest()
    assert str(caught.value) == message


def test_conditional_encoding_has_neutral_inactive_coordinate_and_distinct_category_coordinates():
    domain = SearchSpace([
        Knob("branch", "categorical", ["left", "right", "other"]),
        Knob("child", "continuous", (2., 4.), condition=("branch", "right")),
    ])
    encoder = SpaceEncoder(domain)
    for values, expected in [({"branch": "left"}, [0., .5]),
                             ({"branch": "other"}, [2 / 3, .5]),
                             ({"branch": "right", "child": 3.5}, [1 / 3, .75])]:
        coordinates = encoder.encode(Config(values))
        np.testing.assert_array_equal(coordinates, expected)
        assert coordinates.dtype == np.float64
        assert encoder.decode(coordinates) == values
