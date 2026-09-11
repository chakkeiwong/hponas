"""Unit tests for GPSearcher.

Tests for hponas/searchers/gp_searcher.py - Phase 0 Day 2-4, Blocking Issue #3
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md
"""

import pytest
import torch
import numpy as np
from hponas.searchers.gp_searcher import GPSearcher
from hponas.types import (
    Config,
    Result,
    Parameter,
    ParameterType,
    SearchSpace,
)


@pytest.fixture
def simple_search_space():
    """Simple 2D continuous search space for testing."""
    params = {
        "x": Parameter(name="x", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
        "y": Parameter(name="y", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
    }
    return SearchSpace(parameters=params)


@pytest.fixture
def mixed_search_space():
    """Mixed search space with continuous, integer, categorical."""
    params = {
        "lr": Parameter(
            name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2), log_scale=True
        ),
        "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        "activation": Parameter(
            name="activation",
            type=ParameterType.CATEGORICAL,
            choices=["relu", "gelu", "tanh"],
        ),
    }
    return SearchSpace(parameters=params)


class TestGPSearcherInitialization:
    """Tests for GPSearcher initialization."""

    def test_gp_searcher_creation(self, simple_search_space):
        """Test creating GP searcher."""
        searcher = GPSearcher(simple_search_space, seed=42)
        assert searcher.search_space == simple_search_space
        assert searcher.seed == 42
        assert searcher.initial_random_samples == 5
        assert searcher.num_restarts == 10
        assert searcher.kernel == "matern52"

    def test_gp_searcher_custom_params(self, simple_search_space):
        """Test GP searcher with custom parameters."""
        searcher = GPSearcher(
            simple_search_space,
            seed=42,
            initial_random_samples=10,
            num_restarts=20,
        )
        assert searcher.initial_random_samples == 10
        assert searcher.num_restarts == 20

    def test_gp_searcher_invalid_kernel(self, simple_search_space):
        """Test GP searcher rejects invalid kernel."""
        with pytest.raises(ValueError, match="Only matern52 kernel supported"):
            GPSearcher(simple_search_space, kernel="rbf")


class TestGPSearcherInitialRandomPhase:
    """Tests for initial random sampling phase."""

    def test_gp_searcher_initial_random(self, simple_search_space):
        """Test initial random phase suggests random configs."""
        searcher = GPSearcher(simple_search_space, seed=42, initial_random_samples=5)

        # First 5 suggestions should be random
        configs = []
        for i in range(5):
            config = searcher.suggest()
            configs.append(config)
            # Simulate observing result
            result = Result(trial_id=f"trial_{i}", objective_value=np.random.rand())
            searcher.observe(result)

        # Should have suggested 5 configs
        assert len(configs) == 5

        # All configs should be valid
        for config in configs:
            assert simple_search_space.validate_config(config)

    def test_gp_searcher_initial_random_deterministic(self, simple_search_space):
        """Test initial random phase is deterministic with seed."""
        searcher1 = GPSearcher(simple_search_space, seed=42, initial_random_samples=5)
        searcher2 = GPSearcher(simple_search_space, seed=42, initial_random_samples=5)

        # Both should suggest same configs with same seed
        for i in range(5):
            config1 = searcher1.suggest()
            config2 = searcher2.suggest()
            assert config1.values == config2.values


class TestGPSearcherAfterInitialPhase:
    """Tests for GP-based optimization after initial phase."""

    def test_gp_searcher_suggest_after_5(self, simple_search_space):
        """Test GP suggests config after initial random phase."""
        searcher = GPSearcher(simple_search_space, seed=42, initial_random_samples=5)

        # Observe 5 random results
        for i in range(5):
            config = searcher.suggest()
            searcher.trials[f"trial_{i}"] = config  # Register mapping
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            searcher.observe(result)

        # 6th suggestion should use GP
        config_6 = searcher.suggest()
        assert simple_search_space.validate_config(config_6)

    def test_gp_searcher_handles_invalid_results(self, simple_search_space):
        """Test GP handles NaN/failed results gracefully."""
        searcher = GPSearcher(simple_search_space, seed=42, initial_random_samples=3)

        # Observe some valid and some invalid results
        for i in range(5):
            config = searcher.suggest()
            searcher.trials[f"trial_{i}"] = config

            if i == 2:
                # Invalid result (NaN)
                result = Result(trial_id=f"trial_{i}", objective_value=np.nan)
            elif i == 3:
                # Failed result
                result = Result(trial_id=f"trial_{i}", objective_value=0.5, status="failed")
            else:
                # Valid result
                result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)

            searcher.observe(result)

        # Should still work despite invalid results
        config_6 = searcher.suggest()
        assert simple_search_space.validate_config(config_6)


class TestGPSearcherConfigTensorConversion:
    """Tests for config-tensor conversion."""

    def test_config_to_tensor(self, simple_search_space):
        """Test converting config to tensor."""
        searcher = GPSearcher(simple_search_space, seed=42)
        config = Config(values={"x": 0.5, "y": 0.8})

        tensor = searcher._config_to_tensor(config)

        assert isinstance(tensor, torch.Tensor)
        assert tensor.shape == (2,)  # 2 parameters
        assert tensor.dtype == torch.float64

        # Values should be in [0, 1] after normalization
        assert torch.all(tensor >= 0.0)
        assert torch.all(tensor <= 1.0)

    def test_tensor_to_config_roundtrip(self, simple_search_space):
        """Test config → tensor → config roundtrip."""
        searcher = GPSearcher(simple_search_space, seed=42)
        original_config = Config(values={"x": 0.3, "y": 0.7})

        # Convert to tensor and back
        tensor = searcher._config_to_tensor(original_config)
        recovered_config = searcher._tensor_to_config(tensor)

        # Should recover same values (within tolerance)
        assert abs(recovered_config["x"] - original_config["x"]) < 1e-6
        assert abs(recovered_config["y"] - original_config["y"]) < 1e-6

    def test_config_to_tensor_log_scale(self):
        """Test config to tensor with log scale parameter."""
        params = {
            "lr": Parameter(
                name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2), log_scale=True
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = GPSearcher(space, seed=42)

        config = Config(values={"lr": 1e-3})
        tensor = searcher._config_to_tensor(config)

        # Should handle log scale properly
        assert isinstance(tensor, torch.Tensor)
        assert 0.0 <= tensor[0] <= 1.0

    def test_config_to_tensor_integer(self):
        """Test config to tensor with integer parameter."""
        params = {
            "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        }
        space = SearchSpace(parameters=params)
        searcher = GPSearcher(space, seed=42)

        config = Config(values={"depth": 5})
        tensor = searcher._config_to_tensor(config)

        # Convert back
        recovered = searcher._tensor_to_config(tensor)
        assert isinstance(recovered["depth"], int)
        assert 2 <= recovered["depth"] <= 10

    def test_config_to_tensor_categorical(self):
        """Test config to tensor with categorical parameter."""
        params = {
            "activation": Parameter(
                name="activation",
                type=ParameterType.CATEGORICAL,
                choices=["relu", "gelu", "tanh"],
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = GPSearcher(space, seed=42)

        config = Config(values={"activation": "gelu"})
        tensor = searcher._config_to_tensor(config)

        # Convert back
        recovered = searcher._tensor_to_config(tensor)
        assert recovered["activation"] in ["relu", "gelu", "tanh"]


class TestGPSearcherPrepareTrainingData:
    """Tests for _prepare_training_data method."""

    def test_prepare_training_data(self, simple_search_space):
        """Test preparing training data from results."""
        searcher = GPSearcher(simple_search_space, seed=42)

        # Create some results with configs
        results = []
        for i in range(5):
            config = Config(values={"x": float(i) / 10.0, "y": float(i) / 10.0})
            searcher.trials[f"trial_{i}"] = config
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            results.append(result)

        # Prepare training data
        X_train, Y_train = searcher._prepare_training_data(results)

        # Check shapes
        assert X_train.shape == (5, 2)  # 5 samples, 2 features
        assert Y_train.shape == (5, 1)  # 5 samples, 1 target

        # Check types
        assert X_train.dtype == torch.float64
        assert Y_train.dtype == torch.float64

    def test_prepare_training_data_empty_trials(self, simple_search_space):
        """Test prepare training data with no trial mappings."""
        searcher = GPSearcher(simple_search_space, seed=42)

        # Results without registered trial mappings
        results = [
            Result(trial_id="trial_0", objective_value=0.5),
            Result(trial_id="trial_1", objective_value=0.7),
        ]

        # Should raise error due to no valid data
        with pytest.raises(ValueError, match="No valid training data"):
            searcher._prepare_training_data(results)

    def test_prepare_training_data_filters_invalid(self, simple_search_space):
        """Test prepare training data filters out missing trials."""
        searcher = GPSearcher(simple_search_space, seed=42)

        # Register some but not all trials
        config0 = Config(values={"x": 0.1, "y": 0.2})
        config2 = Config(values={"x": 0.5, "y": 0.6})
        searcher.trials["trial_0"] = config0
        searcher.trials["trial_2"] = config2

        results = [
            Result(trial_id="trial_0", objective_value=0.5),
            Result(trial_id="trial_1", objective_value=0.6),  # No mapping
            Result(trial_id="trial_2", objective_value=0.7),
        ]

        X_train, Y_train = searcher._prepare_training_data(results)

        # Should only have 2 samples (trial_0 and trial_2)
        assert X_train.shape[0] == 2
        assert Y_train.shape[0] == 2


class TestGPSearcherStateSerialization:
    """Tests for state serialization."""

    def test_get_state(self, simple_search_space):
        """Test getting searcher state."""
        searcher = GPSearcher(simple_search_space, seed=42, initial_random_samples=3)

        # Observe some results
        for i in range(3):
            config = searcher.suggest()
            searcher.trials[f"trial_{i}"] = config
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            searcher.observe(result)

        state = searcher.get_state()

        # Check state contents
        assert "seed" in state
        assert "history" in state
        assert "initial_random_samples" in state
        assert "num_restarts" in state
        assert "kernel" in state
        assert "rng_state" in state
        assert "trials" in state

        assert len(state["history"]) == 3
        assert len(state["trials"]) == 3

    def test_set_state(self, simple_search_space):
        """Test restoring searcher state."""
        searcher1 = GPSearcher(simple_search_space, seed=42, initial_random_samples=3)

        # Observe some results
        for i in range(3):
            config = searcher1.suggest()
            searcher1.trials[f"trial_{i}"] = config
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            searcher1.observe(result)

        # Save state
        state = searcher1.get_state()

        # Create new searcher and restore
        searcher2 = GPSearcher(simple_search_space, seed=99)
        searcher2.set_state(state)

        # Should have same state
        assert len(searcher2.history) == 3
        assert len(searcher2.trials) == 3
        assert searcher2.seed == 42

    def test_state_serialization_roundtrip(self, simple_search_space):
        """Test state serialization roundtrip."""
        searcher1 = GPSearcher(simple_search_space, seed=42, initial_random_samples=3)

        # Observe some results
        for i in range(3):
            config = searcher1.suggest()
            searcher1.trials[f"trial_{i}"] = config
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            searcher1.observe(result)

        # Save and restore
        state = searcher1.get_state()
        searcher2 = GPSearcher(simple_search_space, seed=99)
        searcher2.set_state(state)

        # Next suggestions should be deterministic
        config1 = searcher1.suggest()
        config2 = searcher2.suggest()

        # Should suggest same config (deterministic)
        assert config1.values.keys() == config2.values.keys()


class TestGPSearcherGetBounds:
    """Tests for _get_bounds method."""

    def test_get_bounds(self, simple_search_space):
        """Test getting optimization bounds."""
        searcher = GPSearcher(simple_search_space, seed=42)
        bounds = searcher._get_bounds()

        # Should be [0, 1] for normalized space
        assert bounds.shape == (2, 2)  # 2 rows (lower, upper), 2 cols (x, y)
        assert torch.all(bounds[0, :] == 0.0)
        assert torch.all(bounds[1, :] == 1.0)

    def test_get_bounds_dimensionality(self, mixed_search_space):
        """Test bounds have correct dimensionality."""
        searcher = GPSearcher(mixed_search_space, seed=42)
        bounds = searcher._get_bounds()

        # Should match search space dimensionality
        assert bounds.shape == (2, 3)  # 3 parameters
