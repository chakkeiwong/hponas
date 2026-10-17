"""
sampler_neutra workload: MCMC sampler tuning with ordinary HMC (legacy module name).

Survey reference: Ch 16 (sampler correctness), Ch 11 (HMC/NUTS regime).
Survey verdict: T1, production template (~5d).
Validation: V13 (veto gates, ESS ranking, posterior agreement).

This is the "sampler" regime from Ch 11 and Ch 16: MCMC sampling from a target
posterior using ordinary HMC; a neural transport is not implemented. The workload tunes
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
    logp_x = -0.5 * np.sum((x**2) * np.exp(-v[:, None]), axis=1) - 0.5 * x.shape[1] * (
        v + np.log(2 * np.pi)
    )

    return logp_v + logp_x


def neal_funnel_grad(z: np.ndarray) -> np.ndarray:
    """Gradient of Neal's funnel log-density."""
    v = z[:, 0]
    x = z[:, 1:]

    grad_v = (
        -v / 9.0 + 0.5 * np.sum(x**2 * np.exp(-v[:, None]), axis=1) - 0.5 * x.shape[1]
    )
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
    diverged = bool(
        not np.isfinite(delta_energy).all() or np.any(np.abs(delta_energy) > 1000.0)
    )

    if diverged:
        return z, True

    if np.log(rng.rand()) < -delta_energy:
        return z_new, False
    else:
        return z, False


def _split_chains(chains):
    chains = np.asarray(chains, dtype=float)
    if (
        chains.ndim != 3
        or chains.shape[0] < 2
        or chains.shape[1] < 4
        or chains.shape[2] < 1
        or not np.isfinite(chains).all()
    ):
        raise ValueError(
            "Diagnostics need >=2 finite chains, >=4 draws and >=1 dimension"
        )
    half = chains.shape[1] // 2
    return np.concatenate([chains[:, :half], chains[:, -half:]], axis=0)


def _rank_normalize(x):
    from scipy.stats import norm, rankdata

    ranks = rankdata(x, method="average").reshape(x.shape)
    return norm.ppf((ranks - 3 / 8) / (x.size + 1 / 4))


def _rhat(x):
    m, n = x.shape
    within = x.var(axis=1, ddof=1).mean()
    if within <= 0:
        return float("inf")
    variance = (n - 1) / n * within + x.mean(axis=1).var(ddof=1)
    return max(1.0, float(np.sqrt(variance / within)))


def _ess(x):
    m, n = x.shape
    within = x.var(axis=1, ddof=1).mean()
    if within <= 0:
        return 0.0
    variance = (n - 1) / n * within + x.mean(axis=1).var(ddof=1)
    centered = x - x.mean(axis=1, keepdims=True)
    fft = np.fft.rfft(centered, n=2 * n, axis=1)
    acov = np.fft.irfft(fft * fft.conjugate(), n=2 * n, axis=1)[:, :n] / n
    rho = 1 - (within - acov.mean(axis=0)) / variance
    rho[0] = 1.0
    # Geyer's initial positive, monotone sequence of adjacent lag pairs.
    pairs = []
    for lag in range(0, n - 1, 2):
        pair = float(rho[lag] + rho[lag + 1])
        if pair < 0:
            break
        pairs.append(min(pair, pairs[-1]) if pairs else pair)
    tau = max(1.0, -1 + 2 * sum(pairs))
    return float(min(m * n, m * n / tau))


def compute_ess(chains: np.ndarray) -> float:
    """Minimum rank-normalized bulk/tail ESS with autocorrelation correction."""
    split = _split_chains(chains)
    values = []
    for d in range(split.shape[2]):
        x = split[:, :, d]
        if np.any(x.var(axis=1) == 0):
            return 0.0
        low, high = np.quantile(x, [0.05, 0.95])
        values.extend(
            [
                _ess(_rank_normalize(x)),
                _ess((x <= low).astype(float)),
                _ess((x >= high).astype(float)),
            ]
        )
    return float(min(values))


def compute_rhat(chains: np.ndarray) -> float:
    """Maximum split rank-normalized/folded R-hat; stuck chains fail closed."""
    split = _split_chains(chains)
    values = []
    for d in range(split.shape[2]):
        x = split[:, :, d]
        if np.any(x.var(axis=1) == 0):
            return float("inf")
        values.extend(
            [
                _rhat(_rank_normalize(x)),
                _rhat(_rank_normalize(np.abs(x - np.median(x)))),
            ]
        )
    return float(max(values))


def sampler_neutra(
    config: dict[str, Any],
    fidelity: float = 1.0,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Sampler workload with ordinary HMC (legacy module name).

    Args:
        config: Hyperparameter configuration
        fidelity: Sampling budget (fraction of max_samples)
        seed: Random seed

    Returns:
        dict with keys:
            - ess: Effective sample size (maximize)
            - rhat: Gelman-Rubin diagnostic (minimize, ideally near 1.0)
            - divergences: Fraction of divergent warmup and retained transitions (any divergence vetoes)
            - cost: Wall-clock seconds

    Config schema:
        step_size: float in [1e-3, 1.0], log-scale
        n_leapfrog: int in [1, 50], ordinal
        n_chains: int in [2, 8], ordinal (for R̂ computation)
        target: "funnel" (ordinary HMC; use gaussian_hmc for the known Gaussian target)
    """
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
    if target != "funnel":
        raise ValueError(f"Unsupported ordinary-HMC target: {target}; supported: funnel")
    if (isinstance(step_size, bool) or not isinstance(step_size, (int, float))
            or not np.isfinite(step_size) or step_size <= 0
            or type(n_leapfrog) is not int or not 1 <= n_leapfrog <= 50
            or type(n_chains) is not int or not 2 <= n_chains <= 8
            or isinstance(fidelity, bool) or not isinstance(fidelity, (int, float))
            or not np.isfinite(fidelity) or not 0 < fidelity <= 1):
        raise ValueError("Invalid ordinary-HMC configuration or fidelity")

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
    warmup_divergences = 0
    total_steps = 0

    for chain_idx in range(n_chains):
        # Random initialization
        z = rng.randn(n_dim) * 0.1

        chain_samples = []
        chain_divergences = 0

        # Burn-in
        for _ in range(100):
            z, diverged = hmc_step(
                z.reshape(1, -1), logp_fn, grad_fn, step_size, n_leapfrog, rng
            )
            z = z.squeeze()
            warmup_divergences += int(diverged)

        # Sampling
        for _ in range(n_samples):
            z, diverged = hmc_step(
                z.reshape(1, -1), logp_fn, grad_fn, step_size, n_leapfrog, rng
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
    from workloads.gaussian_hmc import chain_diagnostics, correctness_veto
    diagnostics = chain_diagnostics(chains)
    ess = min(diagnostics["bulk_ess"], diagnostics["tail_ess"])
    rhat = diagnostics["rhat"]
    all_divergences = total_divergences + warmup_divergences
    all_transitions = total_steps + n_chains*100
    divergence_rate = all_divergences / all_transitions

    cost = time.time() - start_time

    return {
        "ess": ess,
        "rhat": rhat,
        "divergences": divergence_rate,
        "divergence_count": all_divergences,
        "warmup_divergences": warmup_divergences,
        "retained_divergences": total_divergences,
        "method": "ordinary_hmc",
        "target": target,
        "gradient_evaluations": all_transitions * (n_leapfrog + 1),
        "diagnostics": diagnostics,
        "veto": correctness_veto(diagnostics, all_divergences),
        "chains": chains.tolist(),
        "cost": cost,
    }
