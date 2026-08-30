"""
Test SearchSpace: contract tests for knob validation, sampling, and conditional structure.

Survey reference: Ch 15 sec:search-space-schema.
R1 spike exit criterion: contract tests pass.
"""

import numpy as np
import pytest

from hponas.space import Knob, SearchSpace


def test_continuous_knob():
    """Continuous knob with bounds and optional log transform."""
    knob = Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2), transform="log")
    assert knob.name == "lr"
    assert knob.kind == "continuous"
    assert knob.transform == "log"


def test_ordinal_knob():
    """Ordinal knob is an integer with natural order (Ch 2)."""
    knob = Knob(name="width", kind="ordinal", bounds=(32, 512))
    assert knob.kind == "ordinal"
    assert knob.bounds == (32, 512)


def test_categorical_knob():
    """Categorical knob has no 'between' (Ch 2)."""
    knob = Knob(name="activation", kind="categorical", bounds=["relu", "tanh", "elu"])
    assert knob.kind == "categorical"
    assert len(knob.bounds) == 3


def test_invalid_continuous_bounds():
    """Continuous knob with low >= high is rejected."""
    with pytest.raises(ValueError, match="invalid"):
        Knob(name="bad", kind="continuous", bounds=(10.0, 5.0))


def test_invalid_categorical_bounds():
    """Categorical knob with <2 values is rejected."""
    with pytest.raises(ValueError, match="list of >=2 values"):
        Knob(name="bad", kind="categorical", bounds=["single"])


def test_search_space_add_knob():
    """Add knobs to a SearchSpace."""
    space = SearchSpace()
    space.add_knob(Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2), transform="log"))
    space.add_knob(Knob(name="batch_size", kind="ordinal", bounds=(16, 256)))
    assert len(space.knobs) == 2


def test_duplicate_knob_name():
    """Duplicate knob names are rejected."""
    space = SearchSpace()
    space.add_knob(Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2)))
    with pytest.raises(ValueError, match="Duplicate"):
        space.add_knob(Knob(name="lr", kind="continuous", bounds=(1e-4, 1e-1)))


def test_conditional_knob():
    """Conditional knob exists only when parent condition holds (Ch 2, Ch 15)."""
    space = SearchSpace()
    space.add_knob(Knob(name="use_annealing", kind="categorical", bounds=[True, False]))
    space.add_knob(Knob(
        name="lr_final",
        kind="continuous",
        bounds=(1e-6, 1e-3),
        condition=("use_annealing", True)
    ))
    assert len(space.knobs) == 2


def test_conditional_missing_parent():
    """Conditional knob with unknown parent is rejected."""
    space = SearchSpace()
    with pytest.raises(ValueError, match="unknown parent"):
        space.add_knob(Knob(
            name="lr_final",
            kind="continuous",
            bounds=(1e-6, 1e-3),
            condition=("use_annealing", True)
        ))


def test_sample_config_continuous():
    """Sample a configuration from continuous space."""
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))

    rng = np.random.default_rng(42)
    config = space.sample_config(rng)

    assert "x" in config
    assert "y" in config
    assert -5.0 <= config["x"] <= 10.0
    assert 0.0 <= config["y"] <= 15.0


def test_sample_config_log_transform():
    """Log-transform produces log-uniform samples (Ch 3 roadmap-01)."""
    space = SearchSpace()
    space.add_knob(Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2), transform="log"))

    rng = np.random.default_rng(42)
    samples = [space.sample_config(rng)["lr"] for _ in range(100)]

    # All samples should be in bounds
    assert all(1e-5 <= s <= 1e-2 for s in samples)
    # Log-uniform means log(samples) should be ~uniform
    log_samples = np.log(samples)
    # Check that they span the log-space range
    assert np.min(log_samples) < np.log(1e-4)
    assert np.max(log_samples) > np.log(1e-3)


def test_validate_config():
    """Validate a configuration against space constraints."""
    space = SearchSpace()
    space.add_knob(Knob(name="lr", kind="continuous", bounds=(1e-5, 1e-2)))
    space.add_knob(Knob(name="batch_size", kind="ordinal", bounds=(16, 256)))

    # Valid config
    space.validate_config({"lr": 1e-4, "batch_size": 32})

    # Missing knob
    with pytest.raises(ValueError, match="missing"):
        space.validate_config({"lr": 1e-4})

    # Out of bounds
    with pytest.raises(ValueError, match="out of bounds"):
        space.validate_config({"lr": 1e-1, "batch_size": 32})


def test_validate_conditional():
    """Conditional knob validation (Ch 15 contract)."""
    space = SearchSpace()
    space.add_knob(Knob(name="use_annealing", kind="categorical", bounds=[True, False]))
    space.add_knob(Knob(
        name="lr_final",
        kind="continuous",
        bounds=(1e-6, 1e-3),
        condition=("use_annealing", True)
    ))

    # Condition met, lr_final required
    space.validate_config({"use_annealing": True, "lr_final": 1e-5})

    # Condition not met, lr_final must be absent
    space.validate_config({"use_annealing": False})

    # Condition met but lr_final missing
    with pytest.raises(ValueError, match="required when"):
        space.validate_config({"use_annealing": True})

    # Condition not met but lr_final present
    with pytest.raises(ValueError, match="must not be set"):
        space.validate_config({"use_annealing": False, "lr_final": 1e-5})
