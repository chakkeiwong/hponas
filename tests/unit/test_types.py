"""Unit tests for core types (Config, Trial, Result, SearchSpace).

Tests for hponas/types.py - Phase 0 Day 2-4, Blocking Issue #3
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md
"""

import pytest
import numpy as np
from hponas.types import (
    Config,
    Trial,
    Result,
    MultiObjectiveResult,
    Parameter,
    ParameterType,
    SearchSpace,
)


class TestConfig:
    """Tests for Config dataclass."""

    def test_config_creation(self):
        """Test creating a config."""
        config = Config(values={"lr": 0.01, "batch_size": 32})
        assert config.values == {"lr": 0.01, "batch_size": 32}
        assert config.config_id is None

    def test_config_with_id(self):
        """Test creating config with ID."""
        config = Config(values={"lr": 0.01}, config_id="test_id")
        assert config.config_id == "test_id"

    def test_config_getitem(self):
        """Test getting parameter value via []."""
        config = Config(values={"lr": 0.01, "batch_size": 32})
        assert config["lr"] == 0.01
        assert config["batch_size"] == 32

    def test_config_setitem(self):
        """Test setting parameter value via []."""
        config = Config(values={"lr": 0.01})
        config["lr"] = 0.001
        assert config["lr"] == 0.001

    def test_config_to_dict(self):
        """Test converting config to dict."""
        config = Config(values={"lr": 0.01}, config_id="test")
        d = config.to_dict()
        assert d == {"values": {"lr": 0.01}, "config_id": "test"}


class TestTrial:
    """Tests for Trial dataclass."""

    def test_trial_creation(self):
        """Test creating a trial."""
        config = Config(values={"lr": 0.01})
        trial = Trial(config=config, trial_id="trial_0")
        assert trial.config == config
        assert trial.trial_id == "trial_0"
        assert trial.fidelity == 1.0
        assert trial.status == "pending"

    def test_trial_with_fidelity(self):
        """Test trial with custom fidelity."""
        config = Config(values={"lr": 0.01})
        trial = Trial(config=config, trial_id="trial_0", fidelity=0.5)
        assert trial.fidelity == 0.5

    def test_trial_to_dict(self):
        """Test converting trial to dict."""
        config = Config(values={"lr": 0.01})
        trial = Trial(config=config, trial_id="trial_0", fidelity=0.5)
        d = trial.to_dict()
        assert d["trial_id"] == "trial_0"
        assert d["fidelity"] == 0.5
        assert d["config"]["values"] == {"lr": 0.01}


class TestResult:
    """Tests for Result dataclass."""

    def test_result_creation(self):
        """Test creating a result."""
        result = Result(trial_id="trial_0", objective_value=0.95)
        assert result.trial_id == "trial_0"
        assert result.objective_value == 0.95
        assert result.cost == 1.0
        assert result.fidelity == 1.0
        assert result.status == "completed"

    def test_result_is_valid_completed(self):
        """Test is_valid for completed result."""
        result = Result(trial_id="trial_0", objective_value=0.95, status="completed")
        assert result.is_valid()

    def test_result_is_valid_nan(self):
        """Test is_valid returns False for NaN."""
        result = Result(trial_id="trial_0", objective_value=np.nan, status="completed")
        assert not result.is_valid()

    def test_result_is_valid_inf(self):
        """Test is_valid returns False for inf."""
        result = Result(trial_id="trial_0", objective_value=np.inf, status="completed")
        assert not result.is_valid()

    def test_result_is_valid_failed(self):
        """Test is_valid returns False for failed status."""
        result = Result(trial_id="trial_0", objective_value=0.95, status="failed")
        assert not result.is_valid()

    def test_result_to_dict(self):
        """Test converting result to dict."""
        result = Result(trial_id="trial_0", objective_value=0.95, cost=2.5)
        d = result.to_dict()
        assert d["trial_id"] == "trial_0"
        assert d["objective_value"] == 0.95
        assert d["cost"] == 2.5


class TestParameter:
    """Tests for Parameter dataclass."""

    def test_continuous_parameter(self):
        """Test continuous parameter."""
        param = Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2))
        assert param.name == "lr"
        assert param.type == ParameterType.CONTINUOUS
        assert param.bounds == (1e-5, 1e-2)

    def test_continuous_parameter_log_scale(self):
        """Test continuous parameter with log scale."""
        param = Parameter(
            name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2), log_scale=True
        )
        assert param.log_scale

    def test_categorical_parameter(self):
        """Test categorical parameter."""
        param = Parameter(
            name="activation",
            type=ParameterType.CATEGORICAL,
            choices=["relu", "gelu", "tanh"],
        )
        assert param.choices == ["relu", "gelu", "tanh"]

    def test_integer_parameter(self):
        """Test integer parameter."""
        param = Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10))
        assert param.bounds == (2, 10)

    def test_parameter_validation_continuous_no_bounds(self):
        """Test parameter validation fails for continuous without bounds."""
        with pytest.raises(ValueError, match="requires bounds"):
            Parameter(name="lr", type=ParameterType.CONTINUOUS)

    def test_parameter_validation_categorical_no_choices(self):
        """Test parameter validation fails for categorical without choices."""
        with pytest.raises(ValueError, match="requires choices"):
            Parameter(name="activation", type=ParameterType.CATEGORICAL)


class TestSearchSpace:
    """Tests for SearchSpace dataclass."""

    def test_search_space_creation(self):
        """Test creating a search space."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2)),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        }
        space = SearchSpace(parameters=params)
        assert len(space.parameters) == 2

    def test_search_space_sample_random(self):
        """Test sampling random config from search space."""
        params = {
            "lr": Parameter(
                name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2), log_scale=True
            ),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
            "activation": Parameter(
                name="activation",
                type=ParameterType.CATEGORICAL,
                choices=["relu", "gelu"],
            ),
        }
        space = SearchSpace(parameters=params)

        # Sample with seed for reproducibility
        config1 = space.sample_random(seed=42)
        config2 = space.sample_random(seed=42)

        # Same seed should give same config
        assert config1.values["lr"] == config2.values["lr"]
        assert config1.values["depth"] == config2.values["depth"]
        assert config1.values["activation"] == config2.values["activation"]

    def test_search_space_sample_bounds(self):
        """Test sampled config respects bounds."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(0.001, 0.1)),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 5)),
        }
        space = SearchSpace(parameters=params)

        # Sample multiple times and check bounds
        for seed in range(10):
            config = space.sample_random(seed=seed)
            assert 0.001 <= config["lr"] <= 0.1
            assert 2 <= config["depth"] <= 5
            assert isinstance(config["depth"], (int, np.integer))

    def test_search_space_validate_config_valid(self):
        """Test validate_config returns True for valid config."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2)),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        }
        space = SearchSpace(parameters=params)

        config = Config(values={"lr": 0.001, "depth": 5})
        assert space.validate_config(config)

    def test_search_space_validate_config_missing_param(self):
        """Test validate_config returns False for missing parameter."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2)),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        }
        space = SearchSpace(parameters=params)

        config = Config(values={"lr": 0.001})  # Missing depth
        assert not space.validate_config(config)

    def test_search_space_validate_config_out_of_bounds(self):
        """Test validate_config returns False for out-of-bounds value."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2)),
        }
        space = SearchSpace(parameters=params)

        config = Config(values={"lr": 0.1})  # Too large
        assert not space.validate_config(config)

    def test_search_space_validate_config_invalid_choice(self):
        """Test validate_config returns False for invalid choice."""
        params = {
            "activation": Parameter(
                name="activation",
                type=ParameterType.CATEGORICAL,
                choices=["relu", "gelu"],
            ),
        }
        space = SearchSpace(parameters=params)

        config = Config(values={"activation": "sigmoid"})  # Not in choices
        assert not space.validate_config(config)

    def test_search_space_dim(self):
        """Test dimensionality calculation."""
        params = {
            "lr": Parameter(name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2)),
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
            "activation": Parameter(
                name="activation",
                type=ParameterType.CATEGORICAL,
                choices=["relu", "gelu"],
            ),
        }
        space = SearchSpace(parameters=params)
        assert space.dim() == 3
