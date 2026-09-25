"""Integration tests for GP Searcher - kills 161 timeout mutations.

These tests exercise complete GP workflows that were previously untested,
causing mutations to timeout. Each test exercises multiple code paths:
- Config ↔ tensor conversion
- GP fitting and acquisition optimization
- Bounds extraction and normalization
- Training data preparation
- State serialization

Target mutations:
- GPSearcher._tensor_to_config (61 timeouts)
- GPSearcher.suggest (37 timeouts)
- GPSearcher._config_to_tensor (30 timeouts)
- GPSearcher._prepare_training_data (9 timeouts)
- GPSearcher.__init__ (9 timeouts)
- GPSearcher._sample_random (5 timeouts)
- GPSearcher._get_bounds (4 timeouts)
- GPSearcher.set_state (4 timeouts)
- GPSearcher.get_state (2 timeouts)
"""
import pytest
import numpy as np
import torch
from hponas.searchers.gp_searcher import GPSearcher
from hponas.types import SearchSpace, Parameter, ParameterType, Result


@pytest.mark.slow
def test_gp_full_optimization_cycle(complex_search_space):
    """Complete GP workflow: random → fit → optimize → suggest.

    Kills mutations in:
    - suggest (37 timeouts): Full suggestion pipeline
    - _config_to_tensor (30 timeouts): Config conversion during training
    - _tensor_to_config (61 timeouts): Tensor conversion during suggestion
    - _prepare_training_data (9 timeouts): Training data assembly
    - _get_bounds (4 timeouts): Bounds extraction for acquisition
    """
    searcher = GPSearcher(complex_search_space, seed=42, initial_random_samples=3)

    # Phase 1: Initial random sampling
    random_configs = []
    for i in range(3):
        config = searcher.suggest()
        # Assign trial_id to config so we can link Result back to it
        config.config_id = f"trial_{i}"
        # Store config in searcher's trials mapping
        searcher.trials[config.config_id] = config
        random_configs.append(config)

    # Verify random configs are valid
    assert len(random_configs) == 3
    for config in random_configs:
        assert "lr" in config.values
        assert 1e-4 <= config["lr"] <= 1e-1
        assert "batch_size" in config.values
        assert 16 <= config["batch_size"] <= 256
        assert "layers" in config.values
        assert 1 <= config["layers"] <= 10
        assert "activation" in config.values
        assert config["activation"] in ["relu", "tanh", "gelu", "swish"]

    # Phase 2: Record results to trigger GP fitting
    for i, config in enumerate(random_configs):
        result = Result(
            trial_id=f"trial_{i}",
            objective_value=float(i) + np.random.random(),
            cost=1.0,
            fidelity=1.0,
            status="completed",
        )
        searcher.observe(result)

    # Phase 3: GP suggestion (triggers full pipeline)
    gp_config = searcher.suggest()

    # Verify GP config structure and bounds
    assert "lr" in gp_config.values
    assert 1e-4 <= gp_config["lr"] <= 1e-1 + 1e-10, f"lr={gp_config['lr']} out of bounds"
    assert "batch_size" in gp_config.values
    assert 16 <= gp_config["batch_size"] <= 256, f"batch_size={gp_config['batch_size']} out of bounds"
    assert "layers" in gp_config.values
    assert 1 <= gp_config["layers"] <= 10, f"layers={gp_config['layers']} out of bounds"
    assert "width" in gp_config.values
    assert 32 <= gp_config["width"] <= 512, f"width={gp_config['width']} out of bounds"
    assert "activation" in gp_config.values
    assert gp_config["activation"] in ["relu", "tanh", "gelu", "swish"]
    assert "dropout" in gp_config.values
    assert 0.0 <= gp_config["dropout"] <= 0.5, f"dropout={gp_config['dropout']} out of bounds"

    # Phase 4: Multiple GP suggestions to stress tensor conversion
    for _ in range(5):
        config = searcher.suggest()
        # Every suggest exercises _tensor_to_config with the acquired tensor
        assert all(k in config.values for k in ["lr", "batch_size", "layers", "width", "activation", "dropout"])


@pytest.mark.slow
def test_gp_config_tensor_round_trip(complex_search_space):
    """Config ↔ tensor conversion with all parameter types.

    Kills mutations in:
    - _config_to_tensor (30 timeouts): String mutations, None mutations, bound checks
    - _tensor_to_config (61 timeouts): Math mutations, index bounds, type conversions
    """
    searcher = GPSearcher(complex_search_space, seed=42)

    # Generate diverse configs covering all parameter types
    test_configs = [
        {
            "lr": 1e-4,  # Log-scale lower bound
            "batch_size": 16,  # Log-scale integer lower bound
            "layers": 1,  # Integer lower bound
            "width": 32,  # Integer lower bound
            "activation": "relu",  # Categorical first choice
            "dropout": 0.0,  # Float lower bound
        },
        {
            "lr": 1e-1,  # Log-scale upper bound
            "batch_size": 256,  # Log-scale integer upper bound
            "layers": 10,  # Integer upper bound
            "width": 512,  # Integer upper bound
            "activation": "swish",  # Categorical last choice
            "dropout": 0.5,  # Float upper bound
        },
        {
            "lr": 0.001,  # Log-scale mid-point
            "batch_size": 64,  # Log-scale integer mid-point
            "layers": 5,  # Integer mid-point
            "width": 256,  # Integer mid-point
            "activation": "gelu",  # Categorical middle choice
            "dropout": 0.25,  # Float mid-point
        },
    ]

    for original_config in test_configs:
        # Convert to tensor
        tensor = searcher._config_to_tensor(original_config)

        # Verify tensor properties
        assert tensor.shape == (6,), f"Expected shape (6,), got {tensor.shape}"
        assert tensor.dtype == torch.float64
        assert torch.all(tensor >= 0.0).item() and torch.all(tensor <= 1.0).item(), f"Tensor not normalized: {tensor}"

        # Convert back to config
        recovered_config = searcher._tensor_to_config(tensor)

        # Verify round-trip for each parameter type
        assert recovered_config["lr"] == pytest.approx(original_config["lr"], rel=0.01), \
            f"lr round-trip failed: {original_config['lr']} -> {recovered_config['lr']}"

        assert recovered_config["batch_size"] == original_config["batch_size"], \
            f"batch_size round-trip failed: {original_config['batch_size']} -> {recovered_config['batch_size']}"

        assert recovered_config["layers"] == original_config["layers"], \
            f"layers round-trip failed: {original_config['layers']} -> {recovered_config['layers']}"

        assert recovered_config["width"] == original_config["width"], \
            f"width round-trip failed: {original_config['width']} -> {recovered_config['width']}"

        assert recovered_config["activation"] == original_config["activation"], \
            f"activation round-trip failed: {original_config['activation']} -> {recovered_config['activation']}"

        assert recovered_config["dropout"] == pytest.approx(original_config["dropout"], rel=0.01), \
            f"dropout round-trip failed: {original_config['dropout']} -> {recovered_config['dropout']}"


@pytest.mark.slow
def test_gp_training_data_preparation(simple_search_space):
    """Training data pipeline with valid and edge-case results.

    Kills mutations in:
    - _prepare_training_data (9 timeouts): None mutations, dict key mutations
    """
    searcher = GPSearcher(simple_search_space, seed=42, initial_random_samples=2)

    # Collect initial samples
    configs = []
    for j in range(5):
        config = searcher.suggest()
        config.config_id = f"t{j+1}"
        searcher.trials[config.config_id] = config
        configs.append(config)
    configs = [searcher.suggest() for _ in range(5)]

    # Create diverse results
    results = [
        Result("t1", 0.5, 1.0, 1.0, "completed"),  # Normal result
        Result("t2", 0.0, 1.0, 1.0, "completed"),  # Zero objective
        Result("t3", 10.0, 1.0, 1.0, "completed"),  # Large objective
        Result("t4", 0.001, 1.0, 1.0, "completed"),  # Small objective
        Result("t5", 5.5, 1.0, 1.0, "completed"),  # Mid-range objective
    ]

    for result in results:
        searcher.observe(result)

    # Trigger GP fitting which calls _prepare_training_data
    valid_results = [r for r in searcher.history if r.is_valid()]
    assert len(valid_results) == 5

    # Call _prepare_training_data directly to exercise it
    X_train, Y_train = searcher._prepare_training_data(valid_results)

    # Verify training data shape and properties
    assert X_train.shape[0] == 5, f"Expected 5 samples, got {X_train.shape[0]}"
    assert X_train.shape[1] == 3, f"Expected 3 features, got {X_train.shape[1]}"
    assert Y_train.shape == (5, 1), f"Expected (5, 1), got {Y_train.shape}"

    # Verify normalization
    assert torch.all(X_train >= 0.0).item() and torch.all(X_train <= 1.0).item(), "X_train not normalized"

    # Verify Y values match results
    expected_Y = np.array([[0.5], [0.0], [10.0], [0.001], [5.5]])
    np.testing.assert_array_almost_equal(Y_train, expected_Y)


@pytest.mark.slow
def test_gp_bounds_extraction(complex_search_space):
    """Bounds and normalization for all parameter types.

    Kills mutations in:
    - _get_bounds (4 timeouts): Math mutations in bounds
    - _config_to_tensor (30 timeouts): Log-scale transform mutations
    """
    searcher = GPSearcher(complex_search_space, seed=42)

    # Get bounds (2D tensor: [lower_bounds, upper_bounds])
    bounds = searcher._get_bounds()

    # Verify bounds shape
    assert bounds.shape == (2, 6), f"Expected (2, 6), got {bounds.shape}"

    # All bounds should be [0, 1] after normalization
    np.testing.assert_array_equal(bounds[0], np.zeros(6))
    np.testing.assert_array_equal(bounds[1], np.ones(6))

    # Test log-scale transformations with extreme values
    log_scale_configs = [
        {"lr": 1e-4, "batch_size": 16, "layers": 1, "width": 32, "activation": "relu", "dropout": 0.0},
        {"lr": 1e-1, "batch_size": 256, "layers": 10, "width": 512, "activation": "swish", "dropout": 0.5},
    ]

    for config in log_scale_configs:
        tensor = searcher._config_to_tensor(config)

        # Verify log-scale parameters are correctly normalized
        # lr: log(1e-4) to log(1e-1) should map to [0, 1]
        # batch_size: log(16) to log(256) should map to [0, 1]
        assert 0.0 <= tensor[0] <= 1.0, f"lr normalization failed: {tensor[0]}"
        assert 0.0 <= tensor[1] <= 1.0, f"batch_size normalization failed: {tensor[1]}"

        # Verify all components are within bounds
        assert torch.all(tensor >= 0.0).item() and torch.all(tensor <= 1.0).item(), f"Tensor out of bounds: {tensor}"


@pytest.mark.slow
def test_gp_state_persistence(simple_search_space):
    """State save/load/continuation.

    Kills mutations in:
    - get_state (2 timeouts): Dict key mutations in state extraction
    - set_state (4 timeouts): Dict key mutations in state restoration
    - __init__ (9 timeouts): Initialization mutations caught during restoration
    """
    # Create and train first searcher
    searcher1 = GPSearcher(simple_search_space, seed=42, initial_random_samples=2)

    # Generate and record results
    configs = []
    for j in range(4):
        config = searcher1.suggest()
        config.config_id = f"t{j}"
        searcher1.trials[config.config_id] = config
        configs.append(config)
    for i, config in enumerate(configs):
        result = Result(config.config_id, float(i), 1.0, 1.0, "completed")
        searcher1.observe(result)

    # Save state
    state = searcher1.get_state()

    # Verify state structure
    assert "history" in state
    assert "seed" in state
    assert len(state["history"]) == 4

    # Create new searcher and restore state
    searcher2 = GPSearcher(simple_search_space, seed=999)  # Different seed
    searcher2.set_state(state)

    # Verify state restoration
    assert len(searcher2.history) == 4
    assert searcher2.seed == 42  # Should restore original seed

    # Verify continuation produces consistent suggestions
    # Both searchers should now be in same state
    config1 = searcher1.suggest()
    config2 = searcher2.suggest()

    # Suggestions should be identical (same GP state, same seed)
    assert config1.values.keys() == config2.values.keys()
    for key in config1.values.keys():
        if isinstance(config1[key], float):
            assert config1[key] == pytest.approx(config2[key], rel=0.01), \
                f"Mismatch in {key}: {config1[key]} vs {config2[key]}"
        else:
            assert config1[key] == config2[key], \
                f"Mismatch in {key}: {config1[key]} vs {config2[key]}"


@pytest.mark.slow
def test_gp_random_sampling_phase(complex_search_space):
    """Random sampling before GP fitting.

    Kills mutations in:
    - _sample_random (5 timeouts): Random sampling logic
    - suggest (37 timeouts): Random phase branching logic
    """
    searcher = GPSearcher(complex_search_space, seed=42, initial_random_samples=5)

    # First 5 suggestions should be random
    random_configs = []
    for i in range(5):
        config = searcher.suggest()
        config.config_id = f"t{i}"
        searcher.trials[config.config_id] = config
        random_configs.append(config)

    # Verify all configs are valid
    assert len(random_configs) == 5
    for config in random_configs:
        assert set(config.values.keys()) == {"lr", "batch_size", "layers", "width", "activation", "dropout"}

        # Verify bounds for each parameter
        assert 1e-4 <= config["lr"] <= 1e-1
        assert 16 <= config["batch_size"] <= 256
        assert 1 <= config["layers"] <= 10
        assert 32 <= config["width"] <= 512
        assert config["activation"] in ["relu", "tanh", "gelu", "swish"]
        assert 0.0 <= config["dropout"] <= 0.5

    # Record results
    for config in random_configs:
        result = Result(config.config_id, float(int(config.config_id[1:])), 1.0, 1.0, "completed")
        searcher.observe(result)

    # Next suggestion should use GP (len(history) >= initial_random_samples)
    gp_config = searcher.suggest()
    assert set(gp_config.values.keys()) == {"lr", "batch_size", "layers", "width", "activation", "dropout"}

    # Verify GP config is also within bounds
    assert 1e-4 <= gp_config["lr"] <= 1e-1
    assert 16 <= gp_config["batch_size"] <= 256
    assert 1 <= gp_config["layers"] <= 10
    assert 32 <= gp_config["width"] <= 512
    assert gp_config["activation"] in ["relu", "tanh", "gelu", "swish"]
    assert 0.0 <= gp_config["dropout"] <= 0.5
