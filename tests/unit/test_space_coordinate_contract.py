"""Fast public space, coordinate and serialized-ledger boundary checks."""

import json

import numpy as np
import pytest

from hponas.encoding import SpaceEncoder, as_knob_space
from hponas.searchers.random_searcher import RandomSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Parameter, ParameterType, Result, Trial
from hponas.types import SearchSpace as ParameterSpace


@pytest.mark.parametrize("kind,bounds,transform,u,sampling,expected", [
    ("continuous", (-2., 6.), "none", .25, False, 0.),
    ("continuous", (1., 81.), "log", .25, False, 3.),
    ("continuous", (.1, .9), "logit", .25, False, .25),
    ("continuous", (-2., 6.), "none", -1., False, -2.),
    ("continuous", (-2., 6.), "none", 2., False, 6.),
    ("ordinal", (2, 4), "none", .3, False, 3),
    ("ordinal", (2, 4), "none", .3, True, 2),
    ("ordinal", (2, 4), "none", 1., True, 4),
    ("ordinal", (1, 81), "log", .5, True, 9),
    ("categorical", ["a", "b", "c"], "none", .2, False, "b"),
    ("categorical", ["a", "b", "c"], "none", .2, True, "a"),
    ("categorical", ["a", "b", "c"], "none", 1., False, "c"),
    ("categorical", ["a", "b", "c"], "none", 1., True, "c"),
])
def test_normalized_coordinate_has_the_declared_inverse(kind, bounds, transform, u, sampling, expected):
    space = SearchSpace([Knob("x", kind, bounds, transform=transform)])
    values = SpaceEncoder(space).decode([u], sampling=sampling)
    assert list(values) == ["x"]
    assert values["x"] == (pytest.approx(expected) if kind == "continuous" else expected)
    if kind == "ordinal":
        assert type(values["x"]) is int
    if kind == "continuous":
        assert type(values["x"]) is float


@pytest.mark.parametrize("coordinates,message", [
    ([], "Coordinate dimension does not match search space"),
    ([0., 0.], "Coordinate dimension does not match search space"),
    ([float("nan")], "Coordinates must be finite"),
])
def test_invalid_coordinate_refusal_is_specific(coordinates, message):
    encoder = SpaceEncoder(SearchSpace([Knob("x", "continuous", (0., 1.))]))
    with pytest.raises(ValueError) as raised:
        encoder.decode(coordinates)
    assert str(raised.value) == message


@pytest.mark.parametrize("kind,bounds,transform,message", [
    ("unknown", (0., 1.), "none", "Unknown knob kind: unknown"),
    ("continuous", (0., 1.), "unknown", "Unknown transform: unknown"),
    ("continuous", [0., 1.], "none", "x: continuous/ordinal requires (low, high) bounds"),
    ("ordinal", (1., 3), "none", "Ordinal bounds must be integers"),
    ("ordinal", (1, 3.), "none", "Ordinal bounds must be integers"),
    ("continuous", (0., 1.), "log", "Log bounds must be positive"),
    ("continuous", (0., .8), "logit", "Logit bounds must lie inside (0, 1)"),
    ("continuous", (.2, 1.), "logit", "Logit bounds must lie inside (0, 1)"),
    ("continuous", (1, 1), "none", "x: bounds (1, 1) invalid (low >= high)"),
    ("continuous", (3, 1), "none", "x: bounds (3, 1) invalid (low >= high)"),
    ("continuous", (0., float("inf")), "none", "x: bounds (0.0, inf) invalid (low >= high)"),
    ("categorical", ["only"], "none", "x: categorical requires list of >=2 values"),
    ("categorical", ("a", "b"), "none", "x: categorical requires list of >=2 values"),
])
def test_invalid_knob_refusal_names_the_broken_domain(kind, bounds, transform, message):
    with pytest.raises(ValueError) as raised:
        Knob("x", kind, bounds, transform=transform)
    assert str(raised.value) == message


@pytest.mark.parametrize("kind,bounds,bad,message", [
    ("continuous", (2, 4), 1, "x: 1 out of bounds [2, 4]"),
    ("continuous", (2, 4), 5, "x: 5 out of bounds [2, 4]"),
    ("ordinal", (2, 4), 3.5, "x: 3.5 not an integer in [2, 4]"),
    ("ordinal", (2, 4), 1, "x: 1 not an integer in [2, 4]"),
    ("ordinal", (2, 4), 5, "x: 5 not an integer in [2, 4]"),
    ("categorical", ["a", "b"], "c", "x: c not in ['a', 'b']"),
])
def test_configuration_includes_both_endpoints_and_refuses_outside_domain(kind, bounds, bad, message):
    space = SearchSpace([Knob("x", kind, bounds)])
    for good in bounds:
        space.validate_config({"x": good})
    with pytest.raises(ValueError) as raised:
        space.validate_config({"x": bad})
    assert str(raised.value) == message


def test_parameter_conversion_preserves_names_transforms_choices_and_order():
    original = ParameterSpace({
        "rate": Parameter("rate", ParameterType.CONTINUOUS, (1., 81.), log_scale=True),
        "count": Parameter("count", ParameterType.INTEGER, (2, 4)),
        "choice": Parameter("choice", ParameterType.DISCRETE, choices=[7, 11]),
        "label": Parameter("label", ParameterType.CATEGORICAL, choices=["a", "b"]),
    })
    converted = as_knob_space(original)
    assert [(k.name, k.kind, k.bounds, k.transform) for k in converted.knobs] == [
        ("rate", "continuous", (1., 81.), "log"), ("count", "ordinal", (2, 4), "none"),
        ("choice", "categorical", [7, 11], "none"), ("label", "categorical", ["a", "b"], "none")]
    assert as_knob_space(converted) is converted
    with pytest.raises(TypeError) as raised:
        as_knob_space(object())
    assert str(raised.value) == "Expected a Knob or Parameter SearchSpace"
    decoded = SpaceEncoder(original).decode([.5, 1., 0., .5])
    assert decoded == {"rate": pytest.approx(9.), "count": 4, "choice": 7, "label": "b"}


def test_conditional_knob_serialization_keeps_optional_fields_and_schema_spelling():
    child = Knob("n", "integer", (2, 5), condition=("branch", "yes"),
                 prior={"weight": 3}, note="layer count")
    expected = {"name": "n", "kind": "ordinal", "bounds": [2, 5], "transform": "none",
                "condition": ["branch", "yes"], "prior": {"weight": 3}, "note": "layer count"}
    assert child.to_dict() == expected
    assert Knob.from_dict(json.loads(json.dumps(expected))) == child
    plain = Knob("x", "continuous", (0., 1.))
    assert plain.to_dict() == {"name": "x", "kind": "continuous", "bounds": [0., 1.],
                               "transform": "none", "condition": None, "prior": None, "note": ""}


def test_trial_wire_record_retains_resume_identity_and_all_paid_work():
    config = Config({"x": 3}, "configuration")
    trial = Trial(config, "child", seed=19, fidelity=4., value=7., cost=2.,
                  parent_trial_id="parent", status="paused", root_trial_id="root",
                  continuation="resume", resume_from=2., checkpoint={"step": 2.})
    assert json.loads(json.dumps(trial.to_dict())) == {
        "config": {"values": {"x": 3}, "config_id": "configuration"},
        "trial_id": "child", "seed": 19, "fidelity": 4., "value": 7., "cost": 2.,
        "parent_trial_id": "parent", "status": "paused", "root_trial_id": "root",
        "continuation": "resume", "resume_from": 2., "checkpoint": {"step": 2.}}


def test_random_search_state_and_capabilities_preserve_both_space_schemas():
    space = SearchSpace([Knob("x", "continuous", (2., 5.)), Knob("n", "ordinal", (2, 4))])
    sampler = RandomSearcher(space, seed=19)
    # Support is a property of the method, independent of the supplied axes.
    assert sampler.capabilities["parameter_types"] == ["continuous", "ordinal", "categorical"]
    assert sampler.capabilities["conditionals"] is True
    assert sampler.capabilities["supports_fidelity"] is True
    assert sampler.capabilities["supports_constraints"] is False
    assert sampler.capabilities["max_dim"] is None
    sampler.trials["a"] = Config({"x": 3., "n": 2}, "config")
    sampler.observe(Result("a", 1.))
    sampler.observe(Result("b", 5.))
    sampler.observe(Result("a", 7.))
    sampler.observe(Result("c", 100., status="failed"))
    assert sampler.get_best().trial_id == "a"
    assert sampler.get_best(maximize=False).trial_id == "b"
    state = json.loads(json.dumps(sampler.state_dict()))
    restored = RandomSearcher(space, seed=101)
    restored.load_state_dict(state)
    assert restored.seed == 19 and restored.trials == sampler.trials
    assert restored.history == sampler.history
    assert [restored.suggest().values for _ in range(3)] == [sampler.suggest().values for _ in range(3)]
    legacy = ParameterSpace({"x": Parameter("x", ParameterType.CONTINUOUS, (2., 5.)),
                             "choice": Parameter("choice", ParameterType.DISCRETE, choices=[7, 11])})
    legacy_sampler = RandomSearcher(legacy, seed=19)
    assert legacy_sampler.capabilities == sampler.capabilities
    expected_seed = np.random.RandomState(19).randint(0, 2**31)
    assert legacy_sampler.suggest() == legacy.sample_random(seed=expected_seed)
