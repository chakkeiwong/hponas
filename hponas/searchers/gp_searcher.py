"""GP+qLogEI Bayesian Optimization Searcher.

Reference implementation matching LaTeX Section 3.1 "Baseline Methods".
"""

from typing import Optional, Dict, Any
import numpy as np
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition import qLogExpectedImprovement
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood

from hponas.searchers.base import BaseSearcher
from hponas.types import Config, SearchSpace, Result


# Preregistered defaults (BUILD_PROGRAM_v3.md)
GP_DEFAULT_KERNEL = "matern52"
GP_DEFAULT_INITIAL_RANDOM = 5
GP_DEFAULT_ACQUISITION_OPTIMIZER = "lbfgs"
GP_DEFAULT_NUM_RESTARTS = 10


class GPSearcher(BaseSearcher):
    """Gaussian Process with q-Log Expected Improvement.

    Algorithm:
    1. Initial phase: Random sampling (n=5 default)
    2. Fit GP with Matérn 5/2 kernel
    3. Optimize qLogEI acquisition function
    4. Return next config

    Supports continuous, discrete, categorical parameters.
    """

    def __init__(
        self,
        search_space: SearchSpace,
        seed: Optional[int] = None,
        initial_random_samples: int = GP_DEFAULT_INITIAL_RANDOM,
        num_restarts: int = GP_DEFAULT_NUM_RESTARTS,
        kernel: str = GP_DEFAULT_KERNEL,
    ):
        """Initialize GP+qLogEI searcher.

        Args:
            search_space: Search space definition
            seed: Random seed for reproducibility
            initial_random_samples: Number of initial random samples
            num_restarts: Number of acquisition optimization restarts
            kernel: GP kernel type (only "matern52" supported)
        """
        super().__init__(search_space, seed)
        self.seed = seed  # Store seed for torch RNG control
        self.initial_random_samples = initial_random_samples
        self.num_restarts = num_restarts
        self.kernel = kernel
        self.rng = np.random.RandomState(seed)

        if kernel != "matern52":
            raise ValueError(f"Only matern52 kernel supported, got {kernel}")

    def suggest(self) -> Config:
        """Suggest next configuration using GP+qLogEI.

        Returns:
            Next configuration to evaluate
        """
        # Set torch seed for deterministic BoTorch operations
        # Seed varies with history length to ensure different suggestions
        if self.seed is not None:
            torch.manual_seed(self.seed + len(self.history))

        # Initial random phase
        if len(self.history) < self.initial_random_samples:
            return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))

        # Get valid observations
        valid_results = [r for r in self.history if r.is_valid()]
        if len(valid_results) < self.initial_random_samples:
            return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))

        # Convert to tensors
        X_train, Y_train = self._prepare_training_data(valid_results)

        # Fit GP
        gp = SingleTaskGP(X_train, Y_train)
        mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
        fit_gpytorch_mll(mll)

        # Optimize qLogEI acquisition
        best_f = Y_train.max().item()
        qLogEI = qLogExpectedImprovement(gp, best_f=best_f)

        bounds = self._get_bounds()
        candidate, acq_value = optimize_acqf(
            qLogEI,
            bounds=bounds,
            q=1,
            num_restarts=self.num_restarts,
            raw_samples=512,
        )

        # Convert back to config
        config = self._tensor_to_config(candidate[0])
        return config

    def _prepare_training_data(self, results: list) -> tuple:
        """Convert results to training tensors.

        Args:
            results: List of valid results

        Returns:
            (X_train, Y_train) tensors
        """
        X_list = []
        Y_list = []

        for result in results:
            # Retrieve config from stored mapping
            if result.trial_id not in self.trials:
                continue  # Skip if mapping not found

            config = self.trials[result.trial_id]

            # Convert to tensors
            x = self._config_to_tensor(config)
            y = torch.tensor([result.objective_value], dtype=torch.float64)
            X_list.append(x)
            Y_list.append(y)

        if len(X_list) == 0:
            raise ValueError("No valid training data found")

        X_train = torch.stack(X_list)
        Y_train = torch.stack(Y_list)  # Shape: (n, 1) - no extra unsqueeze needed
        return X_train, Y_train

    def _config_to_tensor(self, config: Config) -> torch.Tensor:
        """Convert config to tensor representation.

        Args:
            config: Configuration

        Returns:
            Tensor of shape (d,)
        """
        values = []
        for name, param in self.search_space.parameters.items():
            value = config[name]
            # Normalize to [0, 1]
            if param.type.value in ["continuous", "integer"]:
                low, high = param.bounds
                if param.log_scale:
                    normalized = (np.log(value) - np.log(low)) / (np.log(high) - np.log(low))
                else:
                    normalized = (value - low) / (high - low)
            else:
                # Categorical: one-hot encoding (simplified for now)
                normalized = param.choices.index(value) / len(param.choices)
            values.append(normalized)

        return torch.tensor(values, dtype=torch.float64)

    def _tensor_to_config(self, tensor: torch.Tensor) -> Config:
        """Convert tensor back to config.

        Args:
            tensor: Tensor of shape (d,)

        Returns:
            Configuration
        """
        values = {}
        tensor_np = tensor.detach().cpu().numpy()

        for i, (name, param) in enumerate(self.search_space.parameters.items()):
            normalized = tensor_np[i]

            if param.type.value in ["continuous", "integer"]:
                low, high = param.bounds
                if param.log_scale:
                    value = np.exp(np.log(low) + normalized * (np.log(high) - np.log(low)))
                else:
                    value = low + normalized * (high - low)

                if param.type.value == "integer":
                    value = int(np.round(value))
            else:
                # Categorical: decode from normalized value
                idx = int(np.round(normalized * len(param.choices)))
                idx = np.clip(idx, 0, len(param.choices) - 1)
                value = param.choices[idx]

            values[name] = value

        return Config(values=values)

    def _get_bounds(self) -> torch.Tensor:
        """Get optimization bounds (all in [0, 1] after normalization).

        Returns:
            Bounds tensor of shape (2, d)
        """
        d = self.search_space.dim()
        return torch.tensor([[0.0] * d, [1.0] * d], dtype=torch.float64)

    def get_state(self) -> Dict[str, Any]:
        """Get searcher state for serialization."""
        state = super().get_state()

        # Convert rng_state to JSON-serializable format
        rng_state = self.rng.get_state()
        rng_state_serializable = (
            rng_state[0],  # String
            rng_state[1].tolist(),  # Convert ndarray to list
            rng_state[2],  # Int
            rng_state[3],  # Int
            rng_state[4],  # Float
        )

        state.update({
            "initial_random_samples": self.initial_random_samples,
            "num_restarts": self.num_restarts,
            "kernel": self.kernel,
            "rng_state": rng_state_serializable,
        })
        return state

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore searcher state from serialization."""
        super().set_state(state)
        self.initial_random_samples = state["initial_random_samples"]
        self.num_restarts = state["num_restarts"]
        self.kernel = state["kernel"]

        # Convert rng_state from serializable format back to numpy format
        rng_state_serializable = state["rng_state"]
        rng_state = (
            rng_state_serializable[0],  # String
            np.array(rng_state_serializable[1]),  # Convert list back to ndarray
            rng_state_serializable[2],  # Int
            rng_state_serializable[3],  # Int
            rng_state_serializable[4],  # Float
        )
        self.rng.set_state(rng_state)
