"""
Unit Tests: Search Space

Tests individual search space methods in isolation.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

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
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ])
        knob = space.get_knob("x")
        assert knob.name == "x"
        assert knob.kind == "continuous"

    def test_dimension_count(self):
        """SearchSpace must report correct dimension count."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "continuous", (-5.0, 5.0)),
            Knob("z", "ordinal", (1, 100)),
        ])
        assert space.dim == 3

    def test_validate_config_accepts_valid(self):
        """validate_config must accept valid configs."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ])
        config = {"x": 0.5, "y": 5}
        # Should not raise
        space.validate_config(config)

    def test_validate_config_rejects_missing_knob(self):
        """validate_config must reject configs missing knobs."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ])
        config = {"x": 0.5}  # missing "y"

        with pytest.raises(ValueError, match="missing"):
            space.validate_config(config)

    def test_validate_config_rejects_out_of_bounds(self):
        """validate_config must reject out-of-bounds values."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
        ])
        config = {"x": 1.5}  # > 1.0

        with pytest.raises(ValueError, match="out of bounds"):
            space.validate_config(config)

    def test_validate_config_rejects_invalid_categorical(self):
        """validate_config must reject invalid categorical choices."""
        space = SearchSpace([
            Knob("opt", "categorical", ["adam", "sgd"]),
        ])
        config = {"opt": "rmsprop"}  # not in choices

        with pytest.raises(ValueError, match="invalid choice"):
            space.validate_config(config)

    def test_sample_random_config(self):
        """sample() must return a valid random config."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "ordinal", (1, 10)),
        ])
        config = space.sample(seed=42)

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
        assert knob.choices == ["adam", "sgd", "rmsprop"]

    def test_continuous_sample_within_bounds(self):
        """Continuous knob sample must be in [low, high]."""
        knob = Knob("x", "continuous", (0.0, 1.0))
        for _ in range(100):
            value = knob.sample(seed=None)
            assert 0.0 <= value <= 1.0

    def test_ordinal_sample_within_range(self):
        """Ordinal knob sample must be integer in [low, high]."""
        knob = Knob("n", "ordinal", (1, 10))
        for _ in range(50):
            value = knob.sample(seed=None)
            assert isinstance(value, int)
            assert 1 <= value <= 10

    def test_categorical_sample_in_choices(self):
        """Categorical knob sample must be one of the choices."""
        knob = Knob("opt", "categorical", ["adam", "sgd", "rmsprop"])
        for _ in range(30):
            value = knob.sample(seed=None)
            assert value in ["adam", "sgd", "rmsprop"]

    def test_invalid_kind_raises(self):
        """Invalid knob kind must raise ValueError."""
        with pytest.raises(ValueError, match="kind"):
            Knob("x", "invalid_kind", (0.0, 1.0))

    def test_continuous_bounds_must_be_ordered(self):
        """Continuous bounds must have low < high."""
        with pytest.raises(ValueError):
            Knob("x", "continuous", (1.0, 0.0))

    def test_ordinal_bounds_must_be_integers(self):
        """Ordinal bounds must be integers."""
        with pytest.raises(ValueError):
            Knob("n", "ordinal", (1.5, 10.5))

    def test_categorical_choices_must_be_list(self):
        """Categorical choices must be a list."""
        with pytest.raises(ValueError):
            Knob("opt", "categorical", "adam")  # not a list
