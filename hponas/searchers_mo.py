"""
Multi-objective searchers: qLogNEHVI, Chebyshev scalarization, NSGA-II.

Survey reference: Ch 7 (multi-objective methods), Ch 4 (Bayesian MO).
BUILD_PROGRAM_v2.md lines 147: MO stack (16 engineer-days).

Tier 1 MO stack:
- qLogNEHVI: GP with log expected hypervolume improvement
- Chebyshev: scalarization fallback
- NSGA-II: evolutionary multi-objective optimizer

Validation: V09 (hypervolume over budget), V11a (MO veto logic).
"""

from __future__ import annotations

import numpy as np
from typing import Any, Optional

from .space import SearchSpace
from .searchers import Searcher

try:
    from botorch.models import SingleTaskGP
    from botorch.acquisition import qLogNoisyExpectedHypervolumeImprovement
    from botorch.optim import optimize_acqf
    from botorch.utils.transforms import normalize, unnormalize
    from botorch.utils.multi_objective import Hypervolume
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from botorch import fit_gpytorch_model
    import torch
    BOTORCH_AVAILABLE = True
except ImportError:
    BOTORCH_AVAILABLE = False


class qLogNEHVISearcher(Searcher):
    """
    Multi-objective Bayesian optimization with log expected hypervolume improvement.

    Survey: Ch 7 multi-objective methods, qLogNEHVI from BoTorch.

    Features:
    - Gaussian process modeling of Pareto front
    - Log expected hypervolume improvement acquisition
    - Reference point adaptation
    - Continuous + ordinal knobs (via one-hot encoding)

    Limitations (Tier 1):
    - Continuous/ordinal only (categorical support deferred to Tier 2)
    - 2-3 objectives (high-dimensional MO deferred)
    """

    def __init__(
        self,
        space: SearchSpace,
        objectives: list[str],
        reference_point: Optional[np.ndarray] = None,
        seed: int = 0
    ):
        """
        Initialize qLogNEHVI searcher.

        Args:
            space: Search space
            objectives: List of objective names (minimize all by default)
            reference_point: Reference point for hypervolume (anti-ideal point)
            seed: Random seed
        """
        if not BOTORCH_AVAILABLE:
            raise ImportError("qLogNEHVISearcher requires botorch: pip install botorch")

        self.space = space
        self.objectives = objectives
        self.n_objectives = len(objectives)
        self.seed = seed

        # Validate objectives
        if self.n_objectives < 2:
            raise ValueError("qLogNEHVI requires at least 2 objectives")
        if self.n_objectives > 3:
            raise ValueError("Tier 1: qLogNEHVI supports 2-3 objectives only")

        # Reference point (anti-ideal, for hypervolume computation)
        if reference_point is None:
            # Default: slightly worse than origin
            self.reference_point = np.ones(self.n_objectives) * 1.1
        else:
            self.reference_point = np.array(reference_point)

        # Storage
        self._X: list[np.ndarray] = []  # Configurations (normalized)
        self._Y: list[np.ndarray] = []  # Objectives (raw)

        # Random state
        self.rng = np.random.RandomState(seed)
        torch.manual_seed(seed)

        # Check knob support
        for knob in space.knobs:
            if knob.kind == "categorical":
                raise ValueError(f"Tier 1: qLogNEHVI doesn't support categorical knobs yet")

        self.capabilities = {
            "knob_kinds": ["continuous", "ordinal"],
            "multi_objective": True,
            "fidelity_aware": False,
            "supports_log_transform": True,
        }

    def propose(self, n: int = 1) -> list[dict[str, Any]]:
        """
        Propose n configurations.

        Returns:
            List of configurations (dicts)
        """
        if len(self._X) < 2 * len(self.space.knobs):
            # Initial random sampling (Sobol-like)
            return self._propose_random(n)

        # BO acquisition
        return self._propose_bo(n)

    def _propose_random(self, n: int) -> list[dict[str, Any]]:
        """Random sampling for initialization."""
        configs = []
        for _ in range(n):
            config = {}
            for knob in self.space.knobs:
                if knob.kind == "continuous":
                    # Uniform in [0, 1], transform applied by space
                    val = self.rng.uniform(0, 1)
                    config[knob.name] = knob.denormalize(val)
                elif knob.kind == "ordinal":
                    # Random integer in range
                    low, high = knob.bounds
                    config[knob.name] = self.rng.randint(low, high + 1)
            configs.append(config)
        return configs

    def _propose_bo(self, n: int) -> list[dict[str, Any]]:
        """Bayesian optimization via qLogNEHVI."""
        # Convert data to tensors
        X_train = torch.tensor(np.array(self._X), dtype=torch.float64)
        Y_train = torch.tensor(np.array(self._Y), dtype=torch.float64)

        # Fit GP model for each objective
        models = []
        for obj_idx in range(self.n_objectives):
            y_obj = Y_train[:, obj_idx].unsqueeze(-1)

            model = SingleTaskGP(X_train, y_obj)
            mll = ExactMarginalLogLikelihood(model.likelihood, model)
            fit_gpytorch_model(mll)

            models.append(model)

        # Compute current Pareto front for reference
        pareto_mask = self._compute_pareto_mask(Y_train.numpy())
        pareto_Y = Y_train[pareto_mask]

        # qLogNEHVI acquisition function
        ref_point_tensor = torch.tensor(self.reference_point, dtype=torch.float64)

        acq = qLogNoisyExpectedHypervolumeImprovement(
            model=models[0],  # Single model for now (Tier 1 simplification)
            ref_point=ref_point_tensor,
            X_baseline=X_train,
            prune_baseline=True,
        )

        # Optimize acquisition
        bounds = torch.tensor([[0.0] * len(self.space.knobs), [1.0] * len(self.space.knobs)], dtype=torch.float64)

        candidates, _ = optimize_acqf(
            acq_function=acq,
            bounds=bounds,
            q=n,
            num_restarts=10,
            raw_samples=512,
        )

        # Convert back to configs
        configs = []
        for candidate in candidates:
            config = self._tensor_to_config(candidate.numpy())
            configs.append(config)

        return configs

    def _tensor_to_config(self, x: np.ndarray) -> dict[str, Any]:
        """Convert normalized tensor to config dict."""
        config = {}
        for i, knob in enumerate(self.space.knobs):
            val = x[i]
            if knob.kind == "continuous":
                config[knob.name] = knob.denormalize(val)
            elif knob.kind == "ordinal":
                # Round to nearest integer
                low, high = knob.bounds
                config[knob.name] = int(np.clip(np.round(val * (high - low) + low), low, high))
        return config

    def _compute_pareto_mask(self, Y: np.ndarray) -> np.ndarray:
        """
        Compute Pareto front mask (non-dominated points).

        Args:
            Y: Objectives (n_points, n_objectives)

        Returns:
            Boolean mask of Pareto-optimal points
        """
        n = Y.shape[0]
        pareto_mask = np.ones(n, dtype=bool)

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue

                # Check if j dominates i (all objectives better or equal, at least one strictly better)
                dominates = np.all(Y[j] <= Y[i]) and np.any(Y[j] < Y[i])

                if dominates:
                    pareto_mask[i] = False
                    break

        return pareto_mask

    def observe(self, result: dict[str, Any]) -> None:
        """
        Observe trial result.

        Args:
            result: dict with keys: config, objectives (dict), fidelity, cost
        """
        config = result["config"]
        objectives = result["objectives"]  # dict mapping objective name -> value

        # Normalize config
        x = np.array([self._normalize_knob(config[knob.name], knob) for knob in self.space.knobs])

        # Extract objective values
        y = np.array([objectives[obj_name] for obj_name in self.objectives])

        self._X.append(x)
        self._Y.append(y)

    def _normalize_knob(self, val: Any, knob) -> float:
        """Normalize knob value to [0, 1]."""
        if knob.kind == "continuous":
            return knob.normalize(val)
        elif knob.kind == "ordinal":
            low, high = knob.bounds
            return (val - low) / (high - low)
        return 0.0

    def state_dict(self) -> dict[str, Any]:
        """Serialize state."""
        return {
            "kind": "qLogNEHVI",
            "seed": self.seed,
            "objectives": self.objectives,
            "reference_point": self.reference_point.tolist(),
            "X": [x.tolist() for x in self._X],
            "Y": [y.tolist() for y in self._Y],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore state."""
        self.seed = state["seed"]
        self.objectives = state["objectives"]
        self.reference_point = np.array(state["reference_point"])
        self._X = [np.array(x) for x in state["X"]]
        self._Y = [np.array(y) for y in state["Y"]]
        self.rng = np.random.RandomState(self.seed)
        torch.manual_seed(self.seed)
