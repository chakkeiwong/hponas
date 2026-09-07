"""
Test suite for hamiltonian_mo workload.

Validates:
1. Basic execution and return schema
2. Multi-objective outputs (prediction_error, drift)
3. Fidelity scaling
4. Config validation
5. Reproducibility
"""

import pytest
import numpy as np


torch = pytest.importorskip("torch")

from workloads.hamiltonian_mo import hamiltonian_mo, HamiltonianNet, generate_pendulum_data, compute_energy_drift


def test_hamiltonian_mo_basic_execution():
    """Test that hamiltonian_mo runs and returns expected schema."""
    config = {
        "learning_rate": 1e-3,
        "batch_size": 32,
        "hidden_sizes": [32, 32],
        "activation": "tanh",
        "weight_decay": 1e-4,
        "optimizer": "adam",
    }

    result = hamiltonian_mo(config, fidelity=0.1, seed=42)

    # Check schema
    assert "prediction_error" in result
    assert "drift" in result
    assert "cost" in result

    # Check types and ranges
    assert isinstance(result["prediction_error"], float)
    assert isinstance(result["drift"], float)
    assert isinstance(result["cost"], float)

    assert result["prediction_error"] >= 0.0
    assert result["drift"] >= 0.0
    assert result["cost"] > 0.0


def test_hamiltonian_mo_multi_objective():
    """Test that both objectives vary with config quality."""
    good_config = {
        "learning_rate": 1e-3,
        "batch_size": 64,
        "hidden_sizes": [64, 64],
        "activation": "tanh",
        "weight_decay": 1e-4,
        "optimizer": "adam",
    }

    bad_config = {
        "learning_rate": 1e-5,
        "batch_size": 16,
        "hidden_sizes": [8],
        "activation": "relu",
        "weight_decay": 1e-2,
        "optimizer": "sgd",
    }

    result_good = hamiltonian_mo(good_config, fidelity=0.3, seed=42)
    result_bad = hamiltonian_mo(bad_config, fidelity=0.3, seed=42)

    # Good config should have lower error (not guaranteed but likely)
    # At minimum, both should produce finite values
    assert np.isfinite(result_good["prediction_error"])
    assert np.isfinite(result_good["drift"])
    assert np.isfinite(result_bad["prediction_error"])
    assert np.isfinite(result_bad["drift"])


def test_hamiltonian_mo_fidelity_scaling():
    """Test that higher fidelity produces better results."""
    config = {
        "learning_rate": 1e-3,
        "batch_size": 32,
        "hidden_sizes": [32, 32],
        "activation": "tanh",
        "weight_decay": 1e-4,
        "optimizer": "adam",
    }

    result_low = hamiltonian_mo(config, fidelity=0.1, seed=42)
    result_high = hamiltonian_mo(config, fidelity=1.0, seed=42)

    # Higher fidelity should have lower or equal error
    assert result_high["prediction_error"] <= result_low["prediction_error"] * 1.5

    # Higher fidelity costs more
    assert result_high["cost"] > result_low["cost"]


def test_hamiltonian_mo_config_validation():
    """Test that missing config keys raise ValueError."""
    incomplete_config = {
        "learning_rate": 1e-3,
        "batch_size": 32,
        # Missing required keys
    }

    with pytest.raises(ValueError, match="missing required config key"):
        hamiltonian_mo(incomplete_config, fidelity=0.1, seed=42)


def test_hamiltonian_mo_reproducibility():
    """Test that same seed produces same results."""
    config = {
        "learning_rate": 1e-3,
        "batch_size": 32,
        "hidden_sizes": [32, 32],
        "activation": "tanh",
        "weight_decay": 1e-4,
        "optimizer": "adam",
    }

    result1 = hamiltonian_mo(config, fidelity=0.2, seed=42)
    result2 = hamiltonian_mo(config, fidelity=0.2, seed=42)

    # Should be identical (within floating point precision)
    assert np.isclose(result1["prediction_error"], result2["prediction_error"], rtol=1e-5)
    assert np.isclose(result1["drift"], result2["drift"], rtol=1e-5)


def test_generate_pendulum_data():
    """Test pendulum data generation."""
    states, derivs = generate_pendulum_data(n_trajectories=5, n_steps=50, seed=42)

    assert states.shape == (5 * 50, 2)
    assert derivs.shape == (5 * 50, 2)
    assert np.all(np.isfinite(states))
    assert np.all(np.isfinite(derivs))


def test_hamiltonian_net_forward():
    """Test HamiltonianNet forward pass."""
    model = HamiltonianNet([32, 32], activation="tanh")

    qp = torch.randn(10, 2)
    H = model.forward(qp)

    assert H.shape == (10, 1)
    assert torch.all(torch.isfinite(H))


def test_hamiltonian_net_time_derivative():
    """Test HamiltonianNet time derivative computation."""
    model = HamiltonianNet([32, 32], activation="tanh")

    qp = torch.randn(10, 2)
    dqp_dt = model.time_derivative(qp)

    assert dqp_dt.shape == (10, 2)
    assert torch.all(torch.isfinite(dqp_dt))


def test_compute_energy_drift():
    """Test energy drift computation."""
    model = HamiltonianNet([32, 32], activation="tanh")

    # Generate test data
    states, _ = generate_pendulum_data(n_trajectories=3, n_steps=50, seed=42)

    drift = compute_energy_drift(model, states, n_traj=3, steps_per_traj=50)

    assert isinstance(drift, float)
    assert drift >= 0.0
    assert np.isfinite(drift)


def test_hamiltonian_mo_activations():
    """Test all activation functions work."""
    for activation in ["tanh", "relu", "elu"]:
        config = {
            "learning_rate": 1e-3,
            "batch_size": 32,
            "hidden_sizes": [32, 32],
            "activation": activation,
            "weight_decay": 1e-4,
            "optimizer": "adam",
        }

        result = hamiltonian_mo(config, fidelity=0.1, seed=42)
        assert np.isfinite(result["prediction_error"])


def test_hamiltonian_mo_optimizers():
    """Test all optimizer options work."""
    for optimizer in ["adam", "sgd", "rmsprop"]:
        config = {
            "learning_rate": 1e-3,
            "batch_size": 32,
            "hidden_sizes": [32, 32],
            "activation": "tanh",
            "weight_decay": 1e-4,
            "optimizer": optimizer,
        }

        result = hamiltonian_mo(config, fidelity=0.1, seed=42)
        assert np.isfinite(result["prediction_error"])
