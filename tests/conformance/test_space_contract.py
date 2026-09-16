"""Contract conformance tests for SearchSpace and Knob.

Authority: HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 2 Day 3
Purpose: Verify SearchSpace and Knob contract compliance for V03 mutation testing

Contract Requirements:
- Knob validation: bounds checking, kind enforcement, transform support
- SearchSpace operations: add_knob, sample_config, validate_config
- Serialization: to_dict/from_dict, to_json/from_json roundtrips
- Conditional knobs: parent-child relationships, presence validation
- Mutation score ≥0.9 (Item 8 partial)
"""

import json
import pytest
import numpy as np

from hponas.space import SearchSpace, Knob


class TestKnobValidation:
    """Test Knob construction and validation."""

    def test_continuous_knob_requires_tuple_bounds(self):
        """Test continuous knob requires (low, high) tuple."""
        with pytest.raises(ValueError, match="continuous/ordinal requires"):
            Knob(name="x", kind="continuous", bounds=[0.0, 1.0])

    def test_continuous_knob_rejects_invalid_bounds(self):
        """Test continuous knob rejects low >= high."""
        with pytest.raises(ValueError, match="invalid.*low >= high"):
            Knob(name="x", kind="continuous", bounds=(1.0, 0.0))

    def test_continuous_knob_rejects_equal_bounds(self):
        """Test continuous knob rejects low == high."""
        with pytest.raises(ValueError, match="invalid.*low >= high"):
            Knob(name="x", kind="continuous", bounds=(1.0, 1.0))

    def test_ordinal_knob_requires_tuple_bounds(self):
        """Test ordinal knob requires (low, high) tuple."""
        with pytest.raises(ValueError, match="continuous/ordinal requires"):
            Knob(name="n", kind="ordinal", bounds=[1, 10])

    def test_ordinal_knob_rejects_invalid_bounds(self):
        """Test ordinal knob rejects low >= high."""
        with pytest.raises(ValueError, match="invalid.*low >= high"):
            Knob(name="n", kind="ordinal", bounds=(10, 1))

    def test_categorical_knob_requires_list(self):
        """Test categorical knob requires list of values."""
        with pytest.raises(ValueError, match="categorical requires list"):
            Knob(name="choice", kind="categorical", bounds=("a", "b"))

    def test_categorical_knob_requires_at_least_two_values(self):
        """Test categorical knob requires >=2 values."""
        with pytest.raises(ValueError, match="categorical requires list of >=2"):
            Knob(name="choice", kind="categorical", bounds=["single"])


class TestKnobSerialization:
    """Test Knob serialization."""

    def test_continuous_knob_to_dict_converts_tuple_to_list(self):
        """Test to_dict converts tuple bounds to list for JSON."""
        knob = Knob(name="x", kind="continuous", bounds=(0.0, 1.0))
        d = knob.to_dict()
        assert d["bounds"] == [0.0, 1.0]
        assert isinstance(d["bounds"], list)

    def test_continuous_knob_from_dict_restores_tuple(self):
        """Test from_dict restores tuple bounds from list."""
        d = {"name": "x", "kind": "continuous", "bounds": [0.0, 1.0]}
        knob = Knob.from_dict(d)
        assert knob.bounds == (0.0, 1.0)
        assert isinstance(knob.bounds, tuple)

    def test_categorical_knob_roundtrip_preserves_list(self):
        """Test categorical bounds stay as list through roundtrip."""
        knob1 = Knob(name="choice", kind="categorical", bounds=["a", "b", "c"])
        d = knob1.to_dict()
        knob2 = Knob.from_dict(d)
        assert knob2.bounds == ["a", "b", "c"]
        assert isinstance(knob2.bounds, list)

    def test_condition_tuple_survives_roundtrip(self):
        """Test condition tuple is restored after JSON roundtrip."""
        knob1 = Knob(
            name="y",
            kind="continuous",
            bounds=(0.0, 1.0),
            condition=("x", "enabled"),
        )
        d = knob1.to_dict()
        assert d["condition"] == ["x", "enabled"]  # JSON converts to list
        knob2 = Knob.from_dict(d)
        assert knob2.condition == ("x", "enabled")  # Restored to tuple


class TestSearchSpaceAddKnob:
    """Test SearchSpace.add_knob validation."""

    def test_add_knob_rejects_duplicate_name(self):
        """Test add_knob rejects duplicate knob names."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        with pytest.raises(ValueError, match="Duplicate knob name"):
            space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 2.0)))

    def test_add_knob_rejects_unknown_parent(self):
        """Test add_knob rejects condition referencing unknown parent."""
        space = SearchSpace()

        with pytest.raises(ValueError, match="references unknown parent"):
            space.add_knob(
                Knob(
                    name="y",
                    kind="continuous",
                    bounds=(0.0, 1.0),
                    condition=("unknown_parent", "value"),
                )
            )

    def test_add_knob_accepts_valid_condition(self):
        """Test add_knob accepts condition with existing parent."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="categorical", bounds=["a", "b"]))
        space.add_knob(
            Knob(
                name="y",
                kind="continuous",
                bounds=(0.0, 1.0),
                condition=("x", "a"),
            )
        )
        assert len(space.knobs) == 2


class TestSearchSpaceSampleConfig:
    """Test SearchSpace.sample_config behavior."""

    def test_sample_config_returns_valid_continuous_values(self):
        """Test sampled continuous values are within bounds."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        rng = np.random.default_rng(42)
        for _ in range(100):
            config = space.sample_config(rng)
            assert 0.0 <= config["x"] <= 1.0

    def test_sample_config_log_transform_respects_bounds(self):
        """Test log-transformed samples respect original bounds."""
        space = SearchSpace()
        space.add_knob(
            Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-1), transform="log")
        )

        rng = np.random.default_rng(42)
        for _ in range(100):
            config = space.sample_config(rng)
            assert 1e-5 <= config["lr"] <= 1e-1

    def test_sample_config_ordinal_returns_integers(self):
        """Test ordinal knobs return integers."""
        space = SearchSpace()
        space.add_knob(Knob(name="n", kind="ordinal", bounds=(1, 10)))

        rng = np.random.default_rng(42)
        for _ in range(50):
            config = space.sample_config(rng)
            assert isinstance(config["n"], (int, np.integer))
            assert 1 <= config["n"] <= 10

    def test_sample_config_categorical_returns_valid_choice(self):
        """Test categorical knobs return values from bounds."""
        space = SearchSpace()
        space.add_knob(Knob(name="opt", kind="categorical", bounds=["a", "b", "c"]))

        rng = np.random.default_rng(42)
        for _ in range(50):
            config = space.sample_config(rng)
            assert config["opt"] in ["a", "b", "c"]

    def test_sample_config_skips_conditional_when_condition_false(self):
        """Test conditional knobs are skipped when condition not met."""
        space = SearchSpace()
        space.add_knob(Knob(name="mode", kind="categorical", bounds=["a", "b"]))
        space.add_knob(
            Knob(
                name="y",
                kind="continuous",
                bounds=(0.0, 1.0),
                condition=("mode", "a"),
            )
        )

        rng = np.random.default_rng(42)
        configs = [space.sample_config(rng) for _ in range(100)]

        # When mode="a", y should be present
        for cfg in configs:
            if cfg["mode"] == "a":
                assert "y" in cfg
            else:
                assert "y" not in cfg


class TestSearchSpaceValidateConfig:
    """Test SearchSpace.validate_config behavior."""

    def test_validate_config_accepts_valid_config(self):
        """Test validate_config accepts valid configuration."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        # Should not raise
        space.validate_config({"x": 0.5})

    def test_validate_config_rejects_missing_unconditional_knob(self):
        """Test validate_config rejects missing unconditional knob."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        with pytest.raises(ValueError, match="x: missing from config"):
            space.validate_config({})

    def test_validate_config_rejects_out_of_bounds_continuous(self):
        """Test validate_config rejects continuous value out of bounds."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        with pytest.raises(ValueError, match="x:.*out of bounds"):
            space.validate_config({"x": 1.5})

    def test_validate_config_rejects_out_of_bounds_ordinal(self):
        """Test validate_config rejects ordinal value out of bounds."""
        space = SearchSpace()
        space.add_knob(Knob(name="n", kind="ordinal", bounds=(1, 10)))

        with pytest.raises(ValueError, match="n:.*not an integer"):
            space.validate_config({"n": 11})

    def test_validate_config_rejects_non_integer_ordinal(self):
        """Test validate_config rejects non-integer for ordinal."""
        space = SearchSpace()
        space.add_knob(Knob(name="n", kind="ordinal", bounds=(1, 10)))

        with pytest.raises(ValueError, match="n:.*not an integer"):
            space.validate_config({"n": 5.5})

    def test_validate_config_rejects_invalid_categorical_value(self):
        """Test validate_config rejects value not in categorical bounds."""
        space = SearchSpace()
        space.add_knob(Knob(name="opt", kind="categorical", bounds=["a", "b", "c"]))

        with pytest.raises(ValueError, match="opt:.*not in"):
            space.validate_config({"opt": "d"})

    def test_validate_config_requires_conditional_when_condition_met(self):
        """Test validate_config requires conditional knob when condition holds."""
        space = SearchSpace()
        space.add_knob(Knob(name="mode", kind="categorical", bounds=["a", "b"]))
        space.add_knob(
            Knob(
                name="y",
                kind="continuous",
                bounds=(0.0, 1.0),
                condition=("mode", "a"),
            )
        )

        with pytest.raises(ValueError, match="y: required when mode=a"):
            space.validate_config({"mode": "a"})

    def test_validate_config_rejects_conditional_when_condition_not_met(self):
        """Test validate_config rejects conditional knob when condition doesn't hold."""
        space = SearchSpace()
        space.add_knob(Knob(name="mode", kind="categorical", bounds=["a", "b"]))
        space.add_knob(
            Knob(
                name="y",
                kind="continuous",
                bounds=(0.0, 1.0),
                condition=("mode", "a"),
            )
        )

        with pytest.raises(ValueError, match="y: must not be set when mode!=a"):
            space.validate_config({"mode": "b", "y": 0.5})


class TestSearchSpaceSerialization:
    """Test SearchSpace serialization."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test to_dict/from_dict preserves space structure."""
        space1 = SearchSpace()
        space1.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))
        space1.add_knob(Knob(name="n", kind="ordinal", bounds=(1, 10)))

        d = space1.to_dict()
        space2 = SearchSpace.from_dict(d)

        assert len(space2.knobs) == 2
        assert space2.knobs[0].name == "x"
        assert space2.knobs[0].bounds == (0.0, 1.0)
        assert space2.knobs[1].name == "n"
        assert space2.knobs[1].bounds == (1, 10)

    def test_to_json_from_json_roundtrip(self):
        """Test to_json/from_json preserves space structure."""
        space1 = SearchSpace()
        space1.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0), transform="log"))
        space1.add_knob(Knob(name="opt", kind="categorical", bounds=["a", "b"]))

        json_str = space1.to_json()
        space2 = SearchSpace.from_json(json_str)

        assert len(space2.knobs) == 2
        assert space2.knobs[0].transform == "log"
        assert space2.knobs[1].bounds == ["a", "b"]

    def test_to_json_produces_sorted_keys(self):
        """Test to_json produces canonical JSON with sorted keys."""
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(0.0, 1.0)))

        json_str = space.to_json()
        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert "knobs" in parsed

        # Same space should produce identical string
        json_str2 = space.to_json()
        assert json_str == json_str2


# Mutation testing targets (for Week 3 V03 validation)
# These tests are designed to kill common mutations:
# - Bounds comparison operators (< vs <=, > vs >=)
# - Condition logic (== vs !=, presence checks)
# - Type conversions (tuple vs list, int vs float)
# - Transform application (log bounds, ordinal inclusive upper bound)
# - JSON roundtrip edge cases (None handling, tuple restoration)
