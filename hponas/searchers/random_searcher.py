"""Random and Sobol baseline searchers."""

from typing import Optional, Dict, Any
import numpy as np
from scipy.stats import qmc

from hponas.searchers.base import BaseSearcher
from hponas.types import Config, SearchSpace


class RandomSearcher(BaseSearcher):
    """Uniform random sampling baseline.

    Algorithm:
    - Sample uniformly from search space
    - Seed-deterministic for reproducibility
    """

    def __init__(self, search_space: SearchSpace, seed: Optional[int] = None):
        """Initialize random searcher.

        Args:
            search_space: Search space definition
            seed: Random seed for reproducibility
        """
        super().__init__(search_space, seed)
        self.rng = np.random.RandomState(seed)

    def suggest(self) -> Config:
        """Suggest random configuration.

        Returns:
            Random configuration from search space
        """
        return self.search_space.sample_random(seed=self.rng.randint(0, 2**31))

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

        state["rng_state"] = rng_state_serializable
        return state

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore searcher state from serialization."""
        super().set_state(state)

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


class SobolSearcher(BaseSearcher):
    """Sobol quasi-random low-discrepancy sampling baseline.

    Algorithm:
    - Generate Sobol sequence (quasi-random)
    - Better space coverage than pure random
    - Used in V04-T0 validation

    Properties:
    - Low discrepancy: more uniform coverage
    - Deterministic given seed
    - Better than random for same sample size
    """

    def __init__(
        self,
        search_space: SearchSpace,
        seed: Optional[int] = None,
        scramble: bool = True,
    ):
        """Initialize Sobol searcher.

        Args:
            search_space: Search space definition
            seed: Random seed for scrambling
            scramble: Whether to scramble sequence (recommended)
        """
        super().__init__(search_space, seed)
        self.scramble = scramble
        self.d = search_space.dim()

        # Initialize Sobol sampler
        self.sampler = qmc.Sobol(d=self.d, scramble=scramble, seed=seed)
        self.sample_count = 0

    def suggest(self) -> Config:
        """Suggest next configuration using Sobol sequence.

        Returns:
            Configuration from Sobol sequence
        """
        # Get next Sobol sample (in [0, 1]^d)
        sobol_sample = self.sampler.random(1)[0]

        # Convert to config
        config = self._sobol_to_config(sobol_sample)
        self.sample_count += 1

        return config

    def _sobol_to_config(self, sobol_sample: np.ndarray) -> Config:
        """Convert Sobol sample to configuration.

        Args:
            sobol_sample: Array in [0, 1]^d

        Returns:
            Configuration
        """
        values = {}

        for i, (name, param) in enumerate(self.search_space.parameters.items()):
            u = sobol_sample[i]  # Uniform in [0, 1]

            if param.type.value == "continuous":
                low, high = param.bounds
                if param.log_scale:
                    value = np.exp(np.log(low) + u * (np.log(high) - np.log(low)))
                else:
                    value = low + u * (high - low)

            elif param.type.value == "integer":
                low, high = param.bounds
                if param.log_scale:
                    log_val = np.log(low) + u * (np.log(high) - np.log(low))
                    value = int(np.exp(log_val))
                else:
                    value = int(low + u * (high - low + 1))

            elif param.type.value in ["discrete", "categorical"]:
                idx = int(u * len(param.choices))
                idx = min(idx, len(param.choices) - 1)  # Handle u=1.0 edge case
                value = param.choices[idx]

            values[name] = value

        return Config(values=values)

    def get_state(self) -> Dict[str, Any]:
        """Get searcher state for serialization."""
        state = super().get_state()
        state.update({
            "scramble": self.scramble,
            "sample_count": self.sample_count,
            # Note: Sobol sampler state not fully serializable in scipy
            # For V02 validation, we'll need to track sequence position
        })
        return state

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore searcher state from serialization."""
        super().set_state(state)
        self.scramble = state["scramble"]
        self.sample_count = state["sample_count"]

        # Reinitialize sampler and fast-forward to correct position
        self.sampler = qmc.Sobol(d=self.d, scramble=self.scramble, seed=self.seed)
        if self.sample_count > 0:
            # Fast-forward by sampling (not ideal but works for now)
            self.sampler.random(self.sample_count)
