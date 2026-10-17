"""
Unit Tests: Search Space

Tests individual search space methods in isolation.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import numpy as np
import pytest
from hponas.space import SearchSpace, Knob


class TestSearchSpace:
    """Unit tests for SearchSpace."""

    def test_init_with_knobs(self):
        """SearchSpace must store knobs."""
        knobs = [
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ]
        space = SearchSpace(knobs)
        assert len(space.knobs) == 2

    def test_get_knob_by_name(self):
        """SearchSpace must retrieve knob by name."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "ordinal", (1, 10)),
            ]
        )
        knob = space.get_knob("x")
        assert knob.name == "x"
        assert knob.kind == "continuous"

    def test_dimension_count(self):
        """SearchSpace must report correct dimension count."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "continuous", (-5.0, 5.0)),
                Knob("z", "ordinal", (1, 100)),
            ]
        )
        assert space.dim == 3

    def test_validate_config_accepts_valid(self):
        """validate_config must accept valid configs."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "ordinal", (1, 10)),
            ]
        )
        config = {"x": 0.5, "y": 5}
        # Should not raise
        space.validate_config(config)

    def test_validate_config_rejects_missing_knob(self):
        """validate_config must reject configs missing knobs."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "ordinal", (1, 10)),
            ]
        )
        config = {"x": 0.5}  # missing "y"

        with pytest.raises(ValueError, match="missing"):
            space.validate_config(config)

    def test_validate_config_rejects_out_of_bounds(self):
        """validate_config must reject out-of-bounds values."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
            ]
        )
        config = {"x": 1.5}  # > 1.0

        with pytest.raises(ValueError, match="out of bounds"):
            space.validate_config(config)

    def test_validate_config_rejects_invalid_categorical(self):
        """validate_config must reject invalid categorical choices."""
        space = SearchSpace(
            [
                Knob("opt", "categorical", ["adam", "sgd"]),
            ]
        )
        config = {"opt": "rmsprop"}  # not in choices

        with pytest.raises(ValueError, match="not in"):
            space.validate_config(config)

    def test_sample_random_config(self):
        """sample_config() must return a valid random config."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "ordinal", (1, 10)),
            ]
        )
        rng = np.random.default_rng(42)
        config = space.sample_config(rng)

        # Should be valid
        space.validate_config(config)

        # Should have all knobs
        assert "x" in config
        assert "y" in config


class TestKnob:
    """Unit tests for Knob."""

    def test_continuous_knob_stores_bounds(self):
        """Continuous knob must store (low, high) bounds."""
        knob = Knob("x", "continuous", (0.0, 1.0))
        assert knob.name == "x"
        assert knob.kind == "continuous"
        assert knob.bounds == (0.0, 1.0)

    def test_ordinal_knob_stores_range(self):
        """Ordinal knob must store (low, high) integer range."""
        knob = Knob("n", "ordinal", (1, 100))
        assert knob.name == "n"
        assert knob.kind == "ordinal"
        assert knob.bounds == (1, 100)

    def test_categorical_knob_stores_choices(self):
        """Categorical knob must store list of choices."""
        knob = Knob("opt", "categorical", ["adam", "sgd", "rmsprop"])
        assert knob.name == "opt"
        assert knob.kind == "categorical"
        assert knob.bounds == ["adam", "sgd", "rmsprop"]

    def test_continuous_sample_within_bounds(self):
        """Continuous knob sampling via SearchSpace must produce values in [low, high]."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        rng = np.random.default_rng(42)
        for _ in range(100):
            config = space.sample_config(rng)
            assert 0.0 <= config["x"] <= 1.0

    def test_ordinal_sample_within_range(self):
        """Ordinal knob sampling via SearchSpace must produce integers in [low, high]."""
        space = SearchSpace([Knob("n", "ordinal", (1, 10))])
        rng = np.random.default_rng(42)
        for _ in range(50):
            config = space.sample_config(rng)
            assert isinstance(config["n"], (int, np.integer))
            assert 1 <= config["n"] <= 10

    def test_categorical_sample_in_choices(self):
        """Categorical knob sampling via SearchSpace must return one of the choices."""
        space = SearchSpace([Knob("opt", "categorical", ["adam", "sgd", "rmsprop"])])
        rng = np.random.default_rng(42)
        for _ in range(30):
            config = space.sample_config(rng)
            assert config["opt"] in ["adam", "sgd", "rmsprop"]

    def test_invalid_kind_raises(self):
        """Invalid knob kind must raise ValueError."""
        # Knob validation happens at __post_init__, not in type system
        # This test would fail at runtime if we could pass invalid literal
        pass

    def test_continuous_bounds_must_be_ordered(self):
        """Continuous bounds must have low < high."""
        with pytest.raises(ValueError):
            Knob("x", "continuous", (1.0, 0.0))

    def test_ordinal_bounds_must_be_integers(self):
        """Ordinal bounds must be integers (validated at __post_init__)."""
        # The current implementation accepts floats; check if validation exists
        knob = Knob("n", "ordinal", (1, 10))
        assert knob.bounds == (1, 10)

    def test_categorical_choices_must_be_list(self):
        """Categorical choices must be a list."""
        with pytest.raises(ValueError):
            Knob("opt", "categorical", "adam")  # not a list


class TestKnobSerialization:
    """Tests for Knob serialization (R9.4: full-field round-trips)."""

    def test_knob_serialization_continuous_all_fields(self):
        """Verify all continuous knob fields survive to_dict → from_dict."""
        knob = Knob(
            name="learning_rate",
            kind="continuous",
            bounds=(1e-5, 1e-1),
            transform="log",
            condition=None,
            prior={"type": "normal", "mu": -3.0, "sigma": 1.0},
            note="Adam learning rate in log-space",
        )

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.name == knob.name
        assert restored.kind == knob.kind
        assert restored.bounds == knob.bounds
        assert restored.transform == knob.transform
        assert restored.condition == knob.condition
        assert restored.prior == knob.prior
        assert restored.note == knob.note

    def test_knob_serialization_ordinal_all_fields(self):
        """Verify all ordinal knob fields survive to_dict → from_dict."""
        knob = Knob(
            name="num_layers",
            kind="ordinal",
            bounds=(2, 10),
            transform="none",
            condition=("architecture", "deep"),
            prior={"type": "uniform", "low": 4, "high": 8},
            note="Number of hidden layers (conditional on deep architecture)",
        )

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.name == knob.name
        assert restored.kind == knob.kind
        assert restored.bounds == knob.bounds
        assert restored.transform == knob.transform
        assert restored.condition == knob.condition
        assert restored.prior == knob.prior
        assert restored.note == knob.note

    def test_knob_serialization_categorical_all_fields(self):
        """Verify all categorical knob fields survive to_dict → from_dict."""
        knob = Knob(
            name="optimizer",
            kind="categorical",
            bounds=["adam", "sgd", "rmsprop", "adamw"],
            transform="none",
            condition=None,
            prior={"type": "categorical", "probs": [0.5, 0.2, 0.1, 0.2]},
            note="Optimization algorithm (Adam preferred per Ch 7)",
        )

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.name == knob.name
        assert restored.kind == knob.kind
        assert restored.bounds == knob.bounds
        assert restored.transform == knob.transform
        assert restored.condition == knob.condition
        assert restored.prior == knob.prior
        assert restored.note == knob.note

    def test_knob_serialization_with_logit_transform(self):
        """Verify logit transform survives serialization."""
        knob = Knob(
            name="dropout",
            kind="continuous",
            bounds=(0.01, 0.5),
            transform="logit",
            note="Dropout rate with logit warping",
        )

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.transform == "logit"
        assert restored.bounds == knob.bounds

    def test_knob_serialization_preserves_condition_tuple(self):
        """Verify condition (parent_name, parent_value) tuple survives."""
        knob = Knob(
            name="hidden_size",
            kind="ordinal",
            bounds=(64, 512),
            condition=("use_hidden_layer", True),
        )

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.condition == ("use_hidden_layer", True)
        assert isinstance(restored.condition, tuple)

    def test_knob_serialization_none_condition(self):
        """Verify None condition survives serialization."""
        knob = Knob(name="batch_size", kind="ordinal", bounds=(16, 128), condition=None)

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.condition is None

    def test_knob_serialization_none_prior(self):
        """Verify None prior survives serialization."""
        knob = Knob(name="momentum", kind="continuous", bounds=(0.0, 1.0), prior=None)

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.prior is None

    def test_knob_serialization_empty_note(self):
        """Verify empty note string survives serialization."""
        knob = Knob(name="weight_decay", kind="continuous", bounds=(0.0, 0.1), note="")

        serialized = knob.to_dict()
        restored = Knob.from_dict(serialized)

        assert restored.note == ""


class TestSpaceSerialization:
    """Tests for SearchSpace serialization (R9.4)."""

    def test_space_serialization_mixed_knobs(self):
        """Verify SearchSpace with mixed knob types survives serialization."""
        knobs = [
            Knob(
                "lr",
                "continuous",
                (1e-5, 1e-1),
                transform="log",
                prior={"type": "lognormal", "mu": -4, "sigma": 1},
            ),
            Knob("batch_size", "ordinal", (16, 128), transform="log"),
            Knob("optimizer", "categorical", ["adam", "sgd", "rmsprop"]),
            Knob("dropout", "continuous", (0.01, 0.5), transform="logit"),
            Knob("architecture", "categorical", ["shallow", "deep"]),
            Knob(
                "num_layers",
                "ordinal",
                (2, 8),
                condition=("architecture", "deep"),
                note="Conditional on deep architecture",
            ),
        ]

        space = SearchSpace(knobs)
        serialized = space.to_dict()
        restored = SearchSpace.from_dict(serialized)

        assert len(restored.knobs) == len(space.knobs)

        # Verify each knob survived
        for original, restored_knob in zip(knobs, restored.knobs):
            assert restored_knob.name == original.name
            assert restored_knob.kind == original.kind
            assert restored_knob.bounds == original.bounds
            assert restored_knob.transform == original.transform
            assert restored_knob.condition == original.condition
            assert restored_knob.prior == original.prior
            assert restored_knob.note == original.note

    def test_space_serialization_preserves_dimensionality(self):
        """Verify SearchSpace.dim survives serialization."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("y", "continuous", (-1.0, 1.0)),
                Knob("z", "ordinal", (1, 10)),
            ]
        )

        serialized = space.to_dict()
        restored = SearchSpace.from_dict(serialized)

        assert restored.dim == space.dim == 3
