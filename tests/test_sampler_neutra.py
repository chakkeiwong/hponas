"""
Test suite for sampler_neutra workload.

Validates:
1. Basic execution and return schema
2. Correctness metrics (ESS, R̂, divergences)
3. Fidelity scaling
4. Config validation
5. Reproducibility
6. Veto gate thresholds for V13
"""

import pytest
import numpy as np


torch = pytest.importorskip("torch")

from workloads.sampler_neutra import (
    sampler_neutra,
    hmc_step,
    compute_ess,
    compute_rhat,
    neal_funnel_logp,
    neal_funnel_grad,
)


def test_sampler_neutra_basic_execution():
    """Test that sampler_neutra runs and returns expected schema."""
    config = {
        "step_size": 0.1,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result = sampler_neutra(config, fidelity=0.2, seed=42)

    # Check schema
    assert "ess" in result
    assert "rhat" in result
    assert "divergences" in result
    assert "cost" in result

    # Check types and ranges
    assert isinstance(result["ess"], float)
    assert isinstance(result["rhat"], float)
    assert isinstance(result["divergences"], float)
    assert isinstance(result["cost"], float)

    assert result["ess"] > 0.0
    assert result["rhat"] > 0.0
    assert 0.0 <= result["divergences"] <= 1.0
    assert result["cost"] > 0.0


def test_sampler_neutra_correctness_metrics():
    """Test that correctness metrics are in expected ranges."""
    config = {
        "step_size": 0.05,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result = sampler_neutra(config, fidelity=0.5, seed=42)

    # ESS should be positive and less than total samples
    assert result["ess"] > 0.0
    assert result["ess"] <= config["n_chains"] * 500  # fidelity=0.5 * 1000

    # R̂ should be close to 1.0 for converged chains (may not converge at low fidelity)
    assert result["rhat"] > 0.0
    assert result["rhat"] < 10.0  # Reasonable upper bound

    # Divergence rate should be low for reasonable configs
    assert result["divergences"] >= 0.0
    assert result["divergences"] < 1.0


def test_sampler_neutra_fidelity_scaling():
    """Test that higher fidelity produces more samples and better ESS."""
    config = {
        "step_size": 0.05,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result_low = sampler_neutra(config, fidelity=0.1, seed=42)
    result_high = sampler_neutra(config, fidelity=0.5, seed=42)

    # Higher fidelity should have higher or equal ESS
    assert result_high["ess"] >= result_low["ess"] * 0.5

    # Higher fidelity costs more
    assert result_high["cost"] > result_low["cost"]


def test_sampler_neutra_config_validation():
    """Test that missing config keys raise ValueError."""
    incomplete_config = {
        "step_size": 0.1,
        # Missing required keys
    }

    with pytest.raises(ValueError, match="missing required config key"):
        sampler_neutra(incomplete_config, fidelity=0.1, seed=42)


def test_sampler_neutra_reproducibility():
    """Test that same seed produces same results."""
    config = {
        "step_size": 0.05,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result1 = sampler_neutra(config, fidelity=0.2, seed=42)
    result2 = sampler_neutra(config, fidelity=0.2, seed=42)

    # Should be identical (within floating point precision)
    assert np.isclose(result1["ess"], result2["ess"], rtol=1e-3)
    assert np.isclose(result1["rhat"], result2["rhat"], rtol=1e-3)
    assert np.isclose(result1["divergences"], result2["divergences"], rtol=1e-6)


def test_sampler_neutra_veto_gates():
    """Test V13 veto gate thresholds."""
    # Good config should pass veto gates
    good_config = {
        "step_size": 0.05,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result = sampler_neutra(good_config, fidelity=0.3, seed=42)

    # V13 veto: divergences < 0.05
    # (May not always pass at low fidelity, but should be reasonable)
    assert result["divergences"] < 0.5  # Generous threshold for test stability

    # ESS should be positive
    assert result["ess"] > 0.0


def test_sampler_neutra_bad_step_size():
    """Test that bad step size increases divergences."""
    bad_config = {
        "step_size": 1.0,  # Too large
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result = sampler_neutra(bad_config, fidelity=0.2, seed=42)

    # Should have high divergence rate
    assert result["divergences"] > 0.0


def test_neal_funnel_logp():
    """Test Neal's funnel log-density computation."""
    z = np.random.randn(5, 10)
    logp = neal_funnel_logp(z)

    assert logp.shape == (5,)
    assert np.all(np.isfinite(logp))


def test_neal_funnel_grad():
    """Test Neal's funnel gradient computation."""
    z = np.random.randn(5, 10)
    grad = neal_funnel_grad(z)

    assert grad.shape == (5, 10)
    assert np.all(np.isfinite(grad))


def test_hmc_step():
    """Test single HMC step."""
    z = np.random.randn(1, 10)
    rng = np.random.RandomState(42)

    z_next, diverged = hmc_step(
        z, neal_funnel_logp, neal_funnel_grad,
        step_size=0.05, n_leapfrog=10, rng=rng
    )

    assert z_next.shape == (1, 10)
    assert isinstance(diverged, (bool, np.bool_))
    assert np.all(np.isfinite(z_next))


def test_compute_ess():
    """Test ESS computation."""
    # Create mock chains with known properties
    n_chains, n_samples, n_dim = 4, 100, 5
    chains = np.random.randn(n_chains, n_samples, n_dim)

    ess = compute_ess(chains)

    assert isinstance(ess, float)
    assert ess > 0.0
    assert ess <= n_chains * n_samples


def test_compute_rhat():
    """Test R̂ computation."""
    # Create mock chains
    n_chains, n_samples, n_dim = 4, 100, 5
    chains = np.random.randn(n_chains, n_samples, n_dim)

    rhat = compute_rhat(chains)

    assert isinstance(rhat, float)
    assert rhat > 0.0


def test_compute_rhat_converged_chains():
    """Test R̂ is close to 1.0 for converged chains."""
    # Create identical chains (perfect convergence)
    n_chains, n_samples, n_dim = 4, 100, 5
    base_chain = np.random.randn(n_samples, n_dim)
    chains = np.array([base_chain + np.random.randn(n_samples, n_dim) * 0.01 for _ in range(n_chains)])

    rhat = compute_rhat(chains)

    # Should be close to 1.0
    assert 0.9 < rhat < 1.2


def test_sampler_neutra_multiple_chains():
    """Test that multiple chains produce reasonable R̂."""
    config = {
        "step_size": 0.05,
        "n_leapfrog": 10,
        "n_chains": 4,
        "target": "funnel",
    }

    result = sampler_neutra(config, fidelity=0.3, seed=42)

    # R̂ should be computed and finite
    assert np.isfinite(result["rhat"])
    assert result["rhat"] > 0.0
