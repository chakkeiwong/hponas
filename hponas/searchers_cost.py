"""
Cost-aware searchers for HPO-NAS.

Survey: Ch 8 roadmap-12, EI-per-cost with cost cooling.

Key idea: Divide acquisition by predicted cost raised to a temperature.
α_cost(x) = α(x) / cost_model(x)^T where T ∈ [0, 1] anneals over time.

Components:
- CostModelGP: GP over log(wall-clock time)
- CostAwareAcquisition: Wraps any acquisition, divides by cost^T
- Cost cooling: Temperature T anneals from 0 (ignore cost) to 1 (full cost-aware)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch.acquisition import AcquisitionFunction
from botorch.optim import optimize_acqf

from hponas import SearchSpace


class CostModelGP:
    """
    GP surrogate for trial costs (wall-clock time).

    Fits log(cost) to handle wide cost ranges. Censored observations
    (failed/killed trials) are not yet supported (Tier 1 scope).
    """

    def __init__(self, space: SearchSpace):
        self.space = space
        self._model: Optional[SingleTaskGP] = None
        self._train_x: list[np.ndarray] = []
        self._train_y: list[float] = []

        # Extract continuous knobs for normalization
        self.cont_knobs = [k for k in space.knobs if k.kind == "continuous" and not k.condition]
        if not self.cont_knobs:
            raise ValueError("CostModelGP requires continuous knobs")

        # Store bounds for normalization to [0, 1]^d
        self._bounds_low = torch.tensor([k.bounds[0] for k in self.cont_knobs], dtype=torch.float64)
        self._bounds_high = torch.tensor([k.bounds[1] for k in self.cont_knobs], dtype=torch.float64)
        self._log_dims = torch.tensor([k.transform == "log" for k in self.cont_knobs], dtype=torch.bool)

    def _to_unit_cube(self, config: dict) -> np.ndarray:
        """Transform config from original space to [0, 1]^d unit cube."""
        x = np.zeros(len(self.cont_knobs), dtype=np.float64)
        for i, knob in enumerate(self.cont_knobs):
            val = config[knob.name]
            low, high = knob.bounds

            if knob.transform == "log":
                # Log-warp: x_unit = (log(val) - log(low)) / (log(high) - log(low))
                log_low, log_high = np.log(low), np.log(high)
                log_val = np.log(val)
                x[i] = (log_val - log_low) / (log_high - log_low)
            else:
                # Linear: x_unit = (val - low) / (high - low)
                x[i] = (val - low) / (high - low)

        return x

    def observe(self, config: dict, cost: float) -> None:
        """Record a trial's wall-clock cost (seconds)."""
        if cost <= 0:
            raise ValueError(f"Cost must be positive, got {cost}")

        # Normalize config to [0, 1]^d
        x_norm = self._to_unit_cube(config)
        self._train_x.append(x_norm)
        self._train_y.append(np.log(cost))  # Log transform for wide ranges

        # Refit model
        if len(self._train_x) >= 2:
            X = torch.tensor(np.array(self._train_x), dtype=torch.float64)
            Y = torch.tensor(np.array(self._train_y), dtype=torch.float64).unsqueeze(-1)

            self._model = SingleTaskGP(X, Y)
            mll = ExactMarginalLogLikelihood(self._model.likelihood, self._model)
            fit_gpytorch_mll(mll)

    def predict(self, configs: list[dict]) -> np.ndarray:
        """
        Predict log(cost) for configs.

        Returns:
            Array of predicted costs in seconds (exponentiated).
        """
        if self._model is None or len(self._train_x) < 2:
            # Cold start: return median observed cost or default
            if self._train_y:
                median_log_cost = np.median(self._train_y)
                return np.exp(median_log_cost) * np.ones(len(configs))
            else:
                return np.ones(len(configs))  # Default: 1 second

        # Normalize and predict
        X = torch.tensor(
            np.array([self._to_unit_cube(c) for c in configs]),
            dtype=torch.float64
        )

        with torch.no_grad():
            posterior = self._model.posterior(X)
            log_cost_pred = posterior.mean.squeeze(-1).numpy()

        return np.exp(log_cost_pred)

    def posterior_mean_log_cost(self, X: torch.Tensor) -> torch.Tensor:
        """
        Differentiable log(cost) prediction for points already in the unit cube.

        `predict` round-trips through numpy under `torch.no_grad()`, which severs
        the autograd graph. Acquisition optimization is gradient-based (L-BFGS via
        `optimize_acqf`), so a cost term built on `predict` would contribute no
        gradient and the optimizer would effectively ignore it. This path keeps
        the GP posterior in torch.

        Args:
            X: (..., d) tensor in [0, 1]^d, dimensions ordered as `self.cont_knobs`.

        Returns:
            Tensor of shape `X.shape[:-1]` holding predicted log(cost).
        """
        if self._model is None or len(self._train_x) < 2:
            # Cold start: a flat prediction carries no gradient, which is the
            # correct behaviour — an unfitted cost model must not steer the search.
            fill = float(np.median(self._train_y)) if self._train_y else 0.0
            return torch.full(X.shape[:-1], fill, dtype=X.dtype, device=X.device)

        X_flat = X.reshape(-1, X.shape[-1]).to(dtype=torch.float64)
        posterior = self._model.posterior(X_flat)
        log_cost = posterior.mean.squeeze(-1)

        return log_cost.reshape(X.shape[:-1]).to(dtype=X.dtype)


def _is_log_scale_acquisition(acq: AcquisitionFunction) -> bool:
    """
    True if `acq` returns values on a log scale (qLogEI and friends).

    Wrappers are unwrapped first: `PriorWeightedAcquisition`'s own class name
    carries no "Log" but it returns whatever its base acquisition returns.
    """
    seen: set[int] = set()
    current: Any = acq

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if "log" in type(current).__name__.lower():
            return True

        nxt = getattr(current, "base_acqf", None)
        if nxt is None:
            nxt = getattr(current, "base_acq", None)
        current = nxt

    return False


class CostAwareAcquisition(AcquisitionFunction):
    """
    Wraps any acquisition function to penalise predicted cost.

    α_cost(x) = α(x) / cost_model(x)^T

    Temperature T ∈ [0, 1]:
    - T=0: Ignore cost (pure acquisition)
    - T=1: Full cost-awareness (EI-per-cost)
    - T=0.5: Balanced (square-root cost penalty)

    Cost cooling: Anneal T from 0 to 1 as trials accumulate.

    Log-scale bases (qLogEI): dividing a log-scale acquisition by cost^T inverts
    the intended preference wherever the acquisition is negative, i.e. wherever
    EI < 1 — division makes a negative value *less* negative, so the wrapper would
    reward expensive configs exactly where EI is small. The penalty is therefore
    applied subtractively for log-scale bases:

        log(EI(x) / cost(x)^T) = qLogEI(x) - T·log cost(x)

    This is the same correction already applied to πBO in
    `searchers_gp.PriorWeightedAcquisition`.
    """

    def __init__(
        self,
        base_acq: AcquisitionFunction,
        cost_model: CostModelGP,
        temperature: float = 1.0,
    ):
        super().__init__(model=base_acq.model)
        self.base_acq = base_acq
        self.cost_model = cost_model
        self.temperature = temperature

        if not 0 <= temperature <= 1:
            raise ValueError(f"Temperature must be in [0, 1], got {temperature}")

    def forward(self, X: torch.Tensor) -> torch.Tensor:
        """
        Evaluate cost-aware acquisition α(x) / cost(x)^T or, for log-scale α,
        the equivalent α(x) - T·log cost(x).

        Args:
            X: (batch_size, q, d) or (batch_size, d) tensor in [0, 1]^d
               (the unit-cube encoding used by both CostModelGP and the base searcher).

        Returns:
            Tensor matching the shape `base_acq(X)` returns.

        Temperature T ∈ [0, 1]:
          - T=0: pure acquisition (cost ignored),
          - T=1: full EI-per-cost,
          - intermediate: square-root-like penalty.

        For q > 1, the q costs are summed (q is sequential wall-clock) then the
        penalty is applied once to the q-batch joint acquisition value, matching
        how PriorWeightedAcquisition averages the prior.
        """
        base_values = self.base_acq(X)

        # (b, q, d) → (b*q, d), or (b, d) → (b, d)
        X_flat = X.reshape(-1, X.shape[-1])
        log_costs = self.cost_model.posterior_mean_log_cost(X_flat)

        # Sum costs across q (batch sequential scenario: q is serial)
        if X.ndim >= 3:
            q = X.shape[-2]
            log_total_cost = log_costs.reshape(-1, q).sum(dim=-1)
        else:
            log_total_cost = log_costs

        log_total_cost = log_total_cost.clamp(min=-20.0)  # exp(-20) ~ 2e-9, epsilon guard

        # Apply penalty
        if _is_log_scale_acquisition(self.base_acq):
            # α(x) - T·log cost(x)
            penalty = self.temperature * log_total_cost
            result = base_values - penalty
        else:
            # α(x) / cost(x)^T = α(x) · exp(-T·log cost(x))
            penalty = torch.exp(self.temperature * log_total_cost)
            result = base_values / penalty

        # Preserve shape (scalar if base_values was scalar)
        if base_values.ndim == 0:
            return result.reshape(())
        return result.reshape(base_values.shape)


def linear_cooling_schedule(
    n_observed: int,
    warmup: int = 5,
    cooldown_duration: int = 20,
) -> float:
    """
    Linear annealing schedule for cost temperature.

    T = 0 for first `warmup` trials (ignore cost while model initializes)
    T linearly increases from 0 to 1 over `cooldown_duration` trials
    T = 1 afterward (full cost-awareness)

    Args:
        n_observed: Number of trials observed so far
        warmup: Number of initial trials to ignore cost
        cooldown_duration: Number of trials over which to anneal

    Returns:
        Temperature T ∈ [0, 1]
    """
    if n_observed < warmup:
        return 0.0

    progress = (n_observed - warmup) / cooldown_duration
    return min(1.0, progress)


class CostAwareGPSearcher:
    """
    GP searcher with EI-per-cost and cost cooling.

    Wraps any GP-based searcher to add cost-awareness. Uses a separate
    GP to model trial costs, then divides acquisition by cost^T where
    T anneals from 0 to 1.
    """

    def __init__(
        self,
        space: SearchSpace,
        base_searcher_factory: Callable[[SearchSpace], Any],
        warmup: int = 5,
        cooldown_duration: int = 20,
        seed: Optional[int] = None,
    ):
        """
        Args:
            space: Search space
            base_searcher_factory: Factory that creates base searcher
                e.g., lambda s: GPqLogEISearcher(s, seed=42)
            warmup: Ignore cost for first N trials
            cooldown_duration: Anneal T over this many trials
            seed: Random seed
        """
        self.space = space
        self.base_searcher = base_searcher_factory(space)
        self.cost_model = CostModelGP(space)
        self.warmup = warmup
        self.cooldown_duration = cooldown_duration
        self.seed = seed

        self._n_observed = 0

        # Expose base capabilities
        if hasattr(self.base_searcher, "capabilities"):
            self.capabilities = self.base_searcher.capabilities.copy()
            self.capabilities["cost_aware"] = True
        else:
            self.capabilities = {"cost_aware": True}

    def propose(self, n: int = 1) -> list[dict]:
        """Propose n configurations using cost-aware acquisition."""
        temperature = linear_cooling_schedule(
            self._n_observed,
            self.warmup,
            self.cooldown_duration,
        )

        if temperature == 0.0 or self._n_observed < 2:
            return self.base_searcher.propose(n)

        # Introspect: can we plug into the base searcher's BoTorch machinery,
        # or must we fall back to passive delegation?
        #
        # We need _build_gp, _build_acqf, _acqf, _from_unit_cube, _dim, n_restarts,
        # raw_samples. If any are missing, delegate — e.g. SobolSearcher has none.
        required = ("_build_gp", "_build_acqf", "_acqf", "_from_unit_cube",
                    "_dim", "n_restarts", "raw_samples")
        if any(not hasattr(self.base_searcher, attr) for attr in required):
            return self.base_searcher.propose(n)

        # The wrapper feeds the base searcher's unit-cube X straight to the cost
        # model, so both must encode the same knobs in the same order. They do
        # today (identical `cont_knobs` filter), but a divergence would silently
        # score the wrong dimension rather than raise.
        base_names = [k.name for k in getattr(self.base_searcher, "cont_knobs", [])]
        if base_names != [k.name for k in self.cost_model.cont_knobs]:
            return self.base_searcher.propose(n)

        # Construct a GP + cost-aware acquisition and run optimize_acqf
        return self._propose_cost_aware(n, temperature)

    def _propose_cost_aware(self, n: int, temperature: float) -> list[dict]:
        """
        Optimize the cost-aware acquisition via `optimize_acqf`.

        Mirrors `GPqLogEISearcher.propose` active phase: build GP, build acquisition,
        wrap with CostAwareAcquisition, optimize, convert back from [0,1]^d.
        """
        base = self.base_searcher

        # Build models (fitting happens inside these methods)
        base._build_gp()
        base._build_acqf(batch_size=n)

        if base._acqf is None:
            # No GP could be built (no observations reached the base searcher).
            return base.propose(n)

        # Wrap the searcher's acquisition with cost penalty
        cost_aware_acqf = CostAwareAcquisition(
            base_acq=base._acqf,
            cost_model=self.cost_model,
            temperature=temperature,
        )

        bounds = torch.stack([
            torch.zeros(base._dim, dtype=torch.float64),
            torch.ones(base._dim, dtype=torch.float64),
        ])

        candidates, _ = optimize_acqf(
            acq_function=cost_aware_acqf,
            bounds=bounds,
            q=n,
            num_restarts=base.n_restarts,
            raw_samples=base.raw_samples,
        )

        configs = []
        for i in range(n):
            cfg = base._from_unit_cube(candidates[i])
            configs.append(cfg)

        base._n_proposed += n
        return configs

    def observe(self, observation: dict) -> None:
        """
        Observe a trial result with cost.

        observation keys:
        - config: dict
        - value: float (objective)
        - cost: float (wall-clock seconds)
        """
        config = observation["config"]
        value = observation["value"]
        cost = observation.get("cost")

        # Update base searcher (performance model)
        self.base_searcher.observe({"config": config, "value": value})

        # Update cost model
        if cost is not None and cost > 0:
            self.cost_model.observe(config, cost)

        self._n_observed += 1
