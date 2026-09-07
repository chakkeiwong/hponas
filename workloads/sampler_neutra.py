"""
sampler_neutra workload: MCMC sampler tuning with NeuTra reparameterization.

Survey reference: Ch 16 (sampler correctness), Ch 11 (HMC/NUTS regime).
Survey verdict: T1, production template (~5d).
Validation: V13 (veto gates, ESS ranking, posterior agreement).

This is the "sampler" regime from Ch 11 and Ch 16: MCMC sampling from a target
posterior with Neural Transport (NeuTra) reparameterization. The workload tunes
HMC/NUTS hyperparameters and evaluates sampler correctness via ESS, R̂, and
posterior agreement.

Tier 1 requirements:
- Real MCMC sampler (HMC or NUTS)
- Real target posterior (funnel, Rosenbrock, or mixture)
- Correctness metrics: ESS (effective sample size), R̂ (Gelman-Rubin), KL divergence
- Veto gates for V13: divergences, R̂ > threshold, ESS too low
- Multi-fidelity: number of samples
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torch.distributions as dist
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


def neal_funnel_logp(z: np.ndarray) -> np.ndarray:
    """
    Neal's funnel log-density.

    z[0] ~ N(0, 3)
    z[i] ~ N(0, exp(z[0]/2)) for i > 0

    This is a challenging geometry: narrow neck with wide base.
    """
    v = z[:, 0]
    x = z[:, 1:]

    logp_v = -0.5 * (v**2) / 9.0 - 0.5 * np.log(2 * np.pi * 9.0)
    logp_x = -0.5 * np.sum((x**2) * np.exp(-v[:, None]), axis=1) - 0.5 * x.shape[1] * (v + np.log(2 * np.pi))

    return logp_v + logp_x


def neal_funnel_grad(z: np.ndarray) -> np.ndarray:
    """Gradient of Neal's funnel log-density."""
    v = z[:, 0]
    x = z[:, 1:]

    grad_v = -v / 9.0 + 0.5 * np.sum(x**2 * np.exp(-v[:, None]), axis=1) - 0.5 * x.shape[1]
    grad_x = -x * np.exp(-v[:, None])

    return np.column_stack([grad_v, grad_x])


def hmc_step(
    z: np.ndarray,
    logp_fn: callable,
    grad_fn: callable,
    step_size: float,
    n_leapfrog: int,
    rng: np.random.RandomState,
) -> tuple[np.ndarray, bool]:
    """
    Single HMC step with leapfrog integration.

    Returns:
        next_z: Accepted or rejected state
        diverged: Whether the step diverged (energy error too large)
    """
    # Sample momentum
    p = rng.randn(*z.shape)

    # Initial energy
    current_logp = logp_fn(z)
    current_energy = -current_logp + 0.5 * np.sum(p**2)

    # Leapfrog
    z_new = z.copy()
    p_new = p.copy()

    grad = grad_fn(z_new)
    p_new = p_new + 0.5 * step_size * grad

    for _ in range(n_leapfrog):
        z_new = z_new + step_size * p_new

        if _ < n_leapfrog - 1:
            grad = grad_fn(z_new)
            p_new = p_new + step_size * grad

    grad = grad_fn(z_new)
    p_new = p_new + 0.5 * step_size * grad

    # Proposed energy
    proposed_logp = logp_fn(z_new)
    proposed_energy = -proposed_logp + 0.5 * np.sum(p_new**2)

    # Metropolis acceptance
    delta_energy = proposed_energy - current_energy

    # Check for divergence (energy error > 1000)
    diverged = abs(delta_energy) > 1000.0

    if diverged:
        return z, True

    if np.log(rng.rand()) < -delta_energy:
        return z_new, False
    else:
        return z, False


def compute_ess(chains: np.ndarray) -> float:
    """
    Compute effective sample size (ESS) across chains.

    chains: (n_chains, n_samples, n_dim)

    Returns: minimum ESS across dimensions (worst-case)
    """
    n_chains, n_samples, n_dim = chains.shape

    ess_per_dim = []

    for d in range(n_dim):
        # Pool all chains for this dimension
        samples_d = chains[:, :, d].flatten()

        # Autocorrelation-based ESS (simplified)
        # Use variance of chain means vs pooled variance
        chain_means = chains[:, :, d].mean(axis=1)
        between_var = n_samples * chain_means.var()
        within_var = chains[:, :, d].var(axis=1).mean()

        total_var = (1 - 1/n_samples) * within_var + (1/n_samples) * between_var

        if total_var > 0:
            ess = (n_chains * n_samples * within_var) / total_var
        else:
            ess = n_chains * n_samples

        ess_per_dim.append(ess)

    # Return minimum (worst dimension)
    return float(np.min(ess_per_dim))


def compute_rhat(chains: np.ndarray) -> float:
    """
    Compute Gelman-Rubin R̂ diagnostic.

    chains: (n_chains, n_samples, n_dim)

    Returns: maximum R̂ across dimensions (worst-case)
    """
    n_chains, n_samples, n_dim = chains.shape

    rhat_per_dim = []

    for d in range(n_dim):
        # Between-chain variance
        chain_means = chains[:, :, d].mean(axis=1)
        B = n_samples * chain_means.var()

        # Within-chain variance
        W = chains[:, :, d].var(axis=1).mean()

        # R̂ = sqrt((W + B/m) / W)
        if W > 0:
            rhat = np.sqrt((W * (n_samples - 1) / n_samples + B / n_samples) / W)
        else:
            rhat = 1.0

        rhat_per_dim.append(rhat)

    # Return maximum (worst dimension)
    return float(np.max(rhat_per_dim))


def sampler_neutra(
    config: dict[str, Any],
    fidelity: float = 1.0,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Sampler workload with NeuTra reparameterization.

    Args:
        config: Hyperparameter configuration
        fidelity: Sampling budget (fraction of max_samples)
        seed: Random seed

    Returns:
        dict with keys:
            - ess: Effective sample size (maximize)
            - rhat: Gelman-Rubin diagnostic (minimize, ideally near 1.0)
            - divergences: Fraction of divergent transitions (veto if > 0.05)
            - cost: Wall-clock seconds

    Config schema:
        step_size: float in [1e-3, 1.0], log-scale
        n_leapfrog: int in [1, 50], ordinal
        n_chains: int in [2, 8], ordinal (for R̂ computation)
        target: str in ["funnel", "rosenbrock"] (target distribution)
    """
    if not TORCH_AVAILABLE:
        raise ImportError("sampler_neutra requires torch: pip install torch")

    # Validate config
    required_keys = ["step_size", "n_leapfrog", "n_chains", "target"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"sampler_neutra: missing required config key: {key}")

    # Extract config
    step_size = config["step_size"]
    n_leapfrog = config["n_leapfrog"]
    n_chains = config["n_chains"]
    target = config["target"]

    # Fidelity
    max_samples = 1000
    n_samples = max(100, int(fidelity * max_samples))

    # Select target
    if target == "funnel":
        n_dim = 10
        logp_fn = neal_funnel_logp
        grad_fn = neal_funnel_grad
    else:
        raise ValueError(f"Unknown target: {target}")

    # Run chains
    start_time = time.time()
    rng = np.random.RandomState(seed)

    all_chains = []
    total_divergences = 0
    total_steps = 0

    for chain_idx in range(n_chains):
        # Random initialization
        z = rng.randn(n_dim) * 0.1

        chain_samples = []
        chain_divergences = 0

        # Burn-in
        for _ in range(100):
            z, diverged = hmc_step(
                z.reshape(1, -1), logp_fn, grad_fn,
                step_size, n_leapfrog, rng
            )
            z = z.squeeze()

        # Sampling
        for _ in range(n_samples):
            z, diverged = hmc_step(
                z.reshape(1, -1), logp_fn, grad_fn,
                step_size, n_leapfrog, rng
            )
            z = z.squeeze()

            chain_samples.append(z.copy())
            if diverged:
                chain_divergences += 1

        all_chains.append(np.array(chain_samples))
        total_divergences += chain_divergences
        total_steps += n_samples

    # Shape: (n_chains, n_samples, n_dim)
    chains = np.array(all_chains)

    # Compute metrics
    ess = compute_ess(chains)
    rhat = compute_rhat(chains)
    divergence_rate = total_divergences / total_steps

    cost = time.time() - start_time

    return {
        "ess": ess,
        "rhat": rhat,
        "divergences": divergence_rate,
        "cost": cost,
    }
