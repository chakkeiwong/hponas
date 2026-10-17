"""Conditional spaces, canonical storage and baseline recovery at empty states."""

import json

import numpy as np
import pytest

from hponas.encoding import SpaceEncoder
from hponas.searchers.base import BaseSearcher
from hponas.searchers.random_searcher import RandomSearcher, SobolSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Parameter, ParameterType, Result
from hponas.types import SearchSpace as ParameterSpace


def conditional_space():
    return SearchSpace([
        Knob("branch", "categorical", ["off", "on"]),
        Knob("child", "ordinal", (2, 4), condition=("branch", "on")),
        Knob("rate", "continuous", (1., 81.), transform="log"),
    ])


def test_inactive_coordinate_does_not_hide_later_unconditional_coordinates():
    encoder = SpaceEncoder(conditional_space())
    assert encoder.decode([0., float("nan"), .5]) == {"branch": "off", "rate": pytest.approx(9.)}
    assert encoder.decode([.5, 1., .5]) == {"branch": "on", "child": 4, "rate": pytest.approx(9.)}
    np.testing.assert_allclose(encoder.encode({"branch": "off", "rate": 9.}), [0., .5, .5])


@pytest.mark.parametrize("coordinates,expected", [
    ([-1., -1.], {"letter": "a", "count": 2}),
    ([2., 2.], {"letter": "c", "count": 4}),
])
def test_clipping_applies_before_discrete_coordinate_rounding(coordinates, expected):
    encoder = SpaceEncoder(SearchSpace([Knob("letter", "categorical", ["a", "b", "c"]),
                                        Knob("count", "ordinal", (2, 4))]))
    assert encoder.decode(coordinates) == expected
    assert encoder.decode(coordinates, sampling=True) == expected


@pytest.mark.parametrize("config,message", [
    ({"rate": 9.}, "branch: missing from config"),
    ({"branch": "on", "rate": 9.}, "child: required when branch=on"),
    ({"branch": "off", "child": 3, "rate": 9.}, "child: must not be set when branch!=on"),
])
def test_missing_and_inactive_fields_have_actionable_diagnostics(config, message):
    with pytest.raises(ValueError) as raised:
        conditional_space().validate_config(config)
    assert str(raised.value) == message


def test_duplicate_names_and_forward_conditions_are_refused_without_changing_the_space():
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    before = space.to_dict()
    for knob, message in [
        (Knob("x", "ordinal", (2, 4)), "Duplicate knob name: x"),
        (Knob("y", "ordinal", (2, 4), condition=("absent", "on")),
         "y: condition references unknown parent absent"),
    ]:
        with pytest.raises(ValueError) as raised:
            space.add_knob(knob)
        assert str(raised.value) == message
        assert space.to_dict() == before


def test_degenerate_logit_bounds_name_the_invalid_transform_domain():
    with pytest.raises(ValueError) as raised:
        Knob("x", "continuous", (.5, .5), transform="logit")
    assert str(raised.value) == "Logit bounds must lie inside (0, 1)"


def test_space_wire_schema_and_canonical_key_order_survive_roundtrip():
    space = conditional_space()
    expected = {"knobs": [knob.to_dict() for knob in space.knobs]}
    assert space.to_dict() == expected
    assert space.to_json() == json.dumps(expected, sort_keys=True)
    assert SearchSpace.from_json(space.to_json()) == space
    assert SearchSpace.from_dict({}).to_dict() == {"knobs": []}


def test_sampling_assigns_equal_width_bins_to_integer_and_categorical_values():
    space = SearchSpace([Knob("n", "ordinal", (2, 4)),
                         Knob("label", "categorical", ["a", "b", "c"])])
    rng = np.random.RandomState(0)
    reference = np.random.RandomState(0)
    for _ in range(8):
        u, v = reference.uniform(size=2)
        assert space.sample_config(rng) == {"n": 2 + int(3*u), "label": ["a", "b", "c"][int(3*v)]}


def test_legacy_random_seed_stream_stays_in_the_declared_31_bit_range():
    space = ParameterSpace({"x": Parameter("x", ParameterType.CONTINUOUS, (0., 1.))})
    searcher = RandomSearcher(space, seed=0)
    reference = np.random.RandomState(0)
    for _ in range(8):
        assert searcher.suggest() == space.sample_random(seed=reference.randint(0, 2**31))


def test_empty_legacy_ledger_and_unstarted_sobol_can_resume():
    space = SearchSpace([Knob("x", "continuous", (0., 1.))])
    sampler = RandomSearcher(space, seed=0)
    sampler.trials["stale"] = sampler.suggest()
    BaseSearcher.set_state(sampler, {"seed": 7, "history": []})
    assert sampler.trials == {} and sampler.history == [] and sampler.seed == 7
    original = SobolSearcher(space, seed=11)
    restored = SobolSearcher(space, seed=99)
    restored.load_state_dict(json.loads(json.dumps(original.state_dict())))
    assert restored.suggest() == original.suggest()


@pytest.mark.parametrize("value,status,valid", [
    (2., "paused", True), (float("inf"), "completed", False),
    (float("-inf"), "paused", False),
    (float("nan"), "completed", False), (2., "failed", False),
])
def test_only_finite_completed_or_paused_results_are_observations(value, status, valid):
    assert Result("trial", value, status=status).is_valid() is valid
