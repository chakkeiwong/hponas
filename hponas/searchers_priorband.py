"""
PriorBand: Portfolio sampler for ASHA with rung-dependent prior mixing.

Survey reference: Ch 8 roadmap-10, ch08-03.
Validation: V11 (prior-aware methods beat baseline when prior is good).

PriorBand generates trial configurations by mixing three strategies:
1. Uniform sampling (exploration)
2. Prior-biased sampling (exploitation of expert knowledge)
3. Incumbent perturbations (local search around best-so-far)

The mixing weights adapt by rung: early rungs rely more on prior, later
rungs shift toward incumbent perturbations as data accumulates.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from hponas.space import SearchSpace, Knob


class PriorBandSampler:
    """
    PriorBand portfolio sampler for multifidelity optimization.

    Args:
        space: Search space
        prior_fn: User prior density π(x), takes dict config → float
        seed: Random seed
        uniform_weight: Base weight for uniform sampling (default 0.3)
        prior_weight: Base weight for prior sampling (default 0.4)
        incumbent_weight: Base weight for incumbent perturbation (default 0.3)
        perturbation_scale: Std dev for Gaussian perturbations (default 0.1)
    """

    def __init__(
        self,
        space: SearchSpace,
        prior_fn: Optional[callable] = None,
        seed: int = 42,
        uniform_weight: float = 0.3,
        prior_weight: float = 0.4,
        incumbent_weight: float = 0.3,
        perturbation_scale: float = 0.1,
    ):
        self.space = space
        self.prior_fn = prior_fn
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        # Portfolio weights (sum to 1.0)
        total = uniform_weight + prior_weight + incumbent_weight
        self.uniform_weight = uniform_weight / total
        self.prior_weight = prior_weight / total
        self.incumbent_weight = incumbent_weight / total
        self.perturbation_scale = perturbation_scale

        # Track best configuration seen so far
        self.incumbent_config: Optional[dict] = None
        self.incumbent_value: Optional[float] = None

        # Continuous knobs only (Tier 1 scope)
        self.cont_knobs = [k for k in space.knobs if k.kind == "continuous"]

        if not self.cont_knobs:
            raise ValueError("PriorBand requires at least one continuous knob")

    @property
    def capabilities(self) -> dict[str, Any]:
        """Declare PriorBand capabilities."""
        return {
            "knob_kinds": ["continuous"],
            "conditionals": False,
            "multi_objective": False,
            "prior": self.prior_fn is not None,
        }

    def _sample_uniform(self) -> dict:
        """Sample uniformly from search space."""
        config = {}
        for knob in self.cont_knobs:
            low, high = knob.bounds
            config[knob.name] = self.rng.uniform(low, high)
        return config

    def _sample_from_prior(self, n_candidates: int = 100) -> dict:
        """
        Sample from prior using rejection sampling.

        Generate n_candidates uniform samples, weight by prior, select one.
        """
        if self.prior_fn is None:
            # No prior provided, fallback to uniform
            return self._sample_uniform()

        candidates = [self._sample_uniform() for _ in range(n_candidates)]

        # Evaluate prior density for each candidate
        weights = np.array([self.prior_fn(c) for c in candidates])

        # Normalize to probabilities
        if weights.sum() == 0:
            # Degenerate prior, fallback to uniform
            return self._sample_uniform()

        probs = weights / weights.sum()

        # Sample one candidate according to prior weights
        idx = self.rng.choice(len(candidates), p=probs)
        return candidates[idx]

    def _perturb_incumbent(self) -> dict:
        """
        Perturb incumbent configuration with Gaussian noise.

        If no incumbent yet, fallback to uniform sampling.
        """
        if self.incumbent_config is None:
            return self._sample_uniform()

        config = {}
        for knob in self.cont_knobs:
            low, high = knob.bounds
            incumbent_val = self.incumbent_config[knob.name]

            # Add Gaussian noise scaled by range
            noise = self.rng.normal(0, self.perturbation_scale * (high - low))
            new_val = incumbent_val + noise

            # Clip to bounds
            config[knob.name] = np.clip(new_val, low, high)

        return config

    def propose(self, n: int, rung_idx: int = 0) -> list[dict]:
        """
        Propose n configurations using portfolio sampling.

        Args:
            n: Number of configurations to propose
            rung_idx: Current rung index (0 = first rung, higher = later rungs)

        Returns:
            List of proposed configurations
        """
        # Adapt weights by rung: later rungs favor incumbent perturbations
        # Early rungs (rung_idx=0): stick to base weights
        # Later rungs: shift toward incumbent
        rung_decay = 0.9 ** rung_idx
        adapted_prior_weight = self.prior_weight * rung_decay
        adapted_incumbent_weight = self.incumbent_weight + (
            self.prior_weight - adapted_prior_weight
        )

        # Normalize
        total = self.uniform_weight + adapted_prior_weight + adapted_incumbent_weight
        w_uniform = self.uniform_weight / total
        w_prior = adapted_prior_weight / total
        w_incumbent = adapted_incumbent_weight / total

        configs = []
        for _ in range(n):
            # Sample strategy from portfolio
            strategy = self.rng.choice(
                ["uniform", "prior", "incumbent"], p=[w_uniform, w_prior, w_incumbent]
            )

            if strategy == "uniform":
                config = self._sample_uniform()
            elif strategy == "prior":
                config = self._sample_from_prior()
            else:  # incumbent
                config = self._perturb_incumbent()

            configs.append(config)

        return configs

    def observe(self, trial: dict[str, Any]) -> None:
        """
        Update incumbent based on observed trial result.

        Args:
            trial: Trial result with keys "config" and "value"
        """
        config = trial["config"]
        value = trial["value"]

        # Update incumbent if this is the best so far
        if self.incumbent_value is None or value > self.incumbent_value:
            self.incumbent_config = config
            self.incumbent_value = value
