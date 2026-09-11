"""
⚠️ OLD CODE - DO NOT USE IN NEW IMPLEMENTATIONS ⚠️
This file is LEGACY code from pre-recovery implementation.
- Used only by validation scripts
- May contain specification violations related to πBO implementation

Nonzero-guard prior construction for πBO and PriorBand.

Survey reference: Ch 8 roadmap-10, ch08-01, ch08-03.
Validation: V11 (prior effectiveness).

A user prior that returns exactly 0 on part of the space permanently excludes that
region: πBO multiplies the acquisition by π(x)^(β/n), so a zero kills the candidate
at every budget, and PriorBand's prior-biased sampler can never draw it. The guard
mixes the user prior with a uniform component:

    π_guarded(x) = α · π̂_user(x) + (1 - α) · 1

where π̂_user is the user prior rescaled to unit mean over the space, so that α is a
genuine mixture weight rather than a function of the user prior's arbitrary scale.
The result is bounded below by (1 - α) > 0 everywhere, so no region is ever ruled
out and a wrong prior can still be overcome by data.

Default α = 0.95: 95% user prior, 5% uniform escape mass.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from hponas.space import SearchSpace

PriorFn = Callable[[dict[str, Any]], float]

#: Absolute floor applied after mixing, so the guard survives α → 1 and
#: pathological user priors (inf, NaN) without ever emitting a zero.
MIN_DENSITY = 1e-12


def _safe_eval(prior: PriorFn, config: dict[str, Any]) -> float:
    """
    Evaluate a user prior defensively.

    User priors are arbitrary callables: they may raise, return negatives, or
    return NaN/inf. Any of those is treated as "no information here" (0.0) rather
    than propagating into the acquisition function.
    """
    try:
        val = float(prior(config))
    except Exception:
        return 0.0
    if not np.isfinite(val) or val < 0.0:
        return 0.0
    return val


def estimate_prior_mean(
    prior: PriorFn,
    space: SearchSpace,
    n_samples: int = 1024,
    seed: int = 0,
) -> float:
    """
    Monte Carlo estimate of E_uniform[π_user(x)] over the search space.

    Used to put the user prior on the same scale as the uniform component so the
    mixture weight α means what it says. Sampling uses `space.sample_config`, so
    log-transformed knobs are sampled log-uniformly and conditional knobs are
    respected — the estimate is taken under the same base measure the searchers use.

    Args:
        prior: User prior density (need not be normalized)
        space: Search space to average over
        n_samples: Number of Monte Carlo samples
        seed: RNG seed (fixed so the guard is deterministic)

    Returns:
        Mean prior density, or 1.0 if the estimate is degenerate (all zero /
        non-finite), in which case no rescaling is applied.
    """
    rng = np.random.default_rng(seed)
    vals = np.array(
        [_safe_eval(prior, space.sample_config(rng)) for _ in range(n_samples)],
        dtype=np.float64,
    )
    mean = float(vals.mean())
    if not np.isfinite(mean) or mean <= 0.0:
        return 1.0
    return mean


class GuardedPrior:
    """
    User prior mixed with a uniform floor so density is strictly positive.

    Callable with the same signature as a raw prior function, so it drops into
    `PriorWeightedAcquisition` and `PriorBandSampler` unchanged.

    Attributes:
        user_prior: The wrapped prior
        alpha: Mixture weight on the user prior
        scale: Rescaling divisor applied to the user prior (unit-mean normalization)
        floor: Guaranteed lower bound on the returned density
    """

    def __init__(
        self,
        user_prior: PriorFn,
        space: SearchSpace,
        alpha: float = 0.95,
        normalize: bool = True,
        n_samples: int = 1024,
        seed: int = 0,
    ) -> None:
        if not (0.0 < alpha < 1.0):
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")

        self.user_prior = user_prior
        self.space = space
        self.alpha = float(alpha)
        self.scale = (
            estimate_prior_mean(user_prior, space, n_samples=n_samples, seed=seed)
            if normalize
            else 1.0
        )
        self.floor = max((1.0 - self.alpha), MIN_DENSITY)

    def __call__(self, config: dict[str, Any]) -> float:
        """Evaluate π_guarded(x) = α · π̂_user(x) + (1 - α), never zero."""
        user_val = _safe_eval(self.user_prior, config) / self.scale
        mixed = self.alpha * user_val + (1.0 - self.alpha)
        if not np.isfinite(mixed):
            # user_val overflowed; the prior is maximally favourable here
            return float(np.finfo(np.float64).max)
        return max(mixed, MIN_DENSITY)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"GuardedPrior(alpha={self.alpha}, scale={self.scale:.4g}, "
            f"floor={self.floor:.4g})"
        )


def make_nonzero_guarded_prior(
    user_prior: PriorFn,
    space: SearchSpace,
    alpha: float = 0.95,
    normalize: bool = True,
    n_samples: int = 1024,
    seed: int = 0,
) -> GuardedPrior:
    """
    Wrap a user prior so it can never exclude a region of the search space.

    Args:
        user_prior: User's prior density π_user(x); any nonnegative callable
        space: Search space, used for the uniform component and rescaling
        alpha: Mixture weight on the user prior, in (0, 1). Lower = more escape mass
        normalize: Rescale the user prior to unit mean before mixing (recommended;
            makes α scale-free). Set False if the prior is already unit-mean
        n_samples: Monte Carlo samples for the rescaling estimate
        seed: RNG seed for the rescaling estimate

    Returns:
        A `GuardedPrior` callable with π(x) >= 1 - α > 0 everywhere

    Raises:
        ValueError: If alpha is not in (0, 1)
    """
    return GuardedPrior(
        user_prior,
        space,
        alpha=alpha,
        normalize=normalize,
        n_samples=n_samples,
        seed=seed,
    )


def is_guarded(prior: PriorFn) -> bool:
    """True if `prior` already carries a nonzero guard."""
    return isinstance(prior, GuardedPrior)


def ensure_guarded(
    prior: PriorFn | None,
    space: SearchSpace,
    alpha: float = 0.95,
) -> GuardedPrior | None:
    """
    Idempotently guard a prior.

    Searchers call this on whatever the user handed them: `None` passes through
    (no prior in use), an already-guarded prior is returned as-is, and a raw
    callable gets wrapped.
    """
    if prior is None:
        return None
    if isinstance(prior, GuardedPrior):
        return prior
    return make_nonzero_guarded_prior(prior, space, alpha=alpha)
