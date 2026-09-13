"""Base searcher interface."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from hponas.types import Config, Result, SearchSpace


class BaseSearcher(ABC):
    """Base class for all searchers (optimization algorithms).

    Contract (tested in tests/conformance/test_searcher_contract.py):
    - suggest() returns valid config from search space
    - observe() accepts trial result
    - State serialization/deserialization works
    - Deterministic behavior given seed
    """

    def __init__(self, search_space: SearchSpace, seed: Optional[int] = None):
        """Initialize searcher.

        Args:
            search_space: Search space definition
            seed: Random seed for reproducibility
        """
        self.search_space = search_space
        self.seed = seed
        self.history: List[Result] = []
        self.trials: Dict[str, Config] = {}  # Maps trial_id to config

    @property
    def capabilities(self) -> Dict[str, Any]:
        """Get searcher capabilities.

        Returns:
            Dict describing what the searcher supports
        """
        # Infer from search space what parameter types are supported
        param_types = set()
        for param in self.search_space.parameters.values():
            param_types.add(param.type.value)

        return {
            "parameter_types": list(param_types),
            "supports_fidelity": False,
            "supports_constraints": False,
        }

    @abstractmethod
    def suggest(self) -> Config:
        """Suggest next configuration to evaluate.

        Returns:
            Config: Next configuration to try
        """
        pass

    def observe(self, result: Result) -> None:
        """Observe trial result.

        Args:
            result: Trial result to incorporate
        """
        self.history.append(result)

    def get_state(self) -> Dict[str, Any]:
        """Get searcher state for serialization.

        Returns:
            Dict containing searcher state
        """
        return {
            "seed": self.seed,
            "history": [r.to_dict() for r in self.history],
            "trials": {tid: config.to_dict() for tid, config in self.trials.items()},
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore searcher state from serialization.

        Args:
            state: Searcher state dictionary
        """
        self.seed = state["seed"]
        self.history = [
            Result(**r) for r in state["history"]
        ]
        self.trials = {
            tid: Config(**cfg) for tid, cfg in state.get("trials", {}).items()
        }

    def state_dict(self) -> Dict[str, Any]:
        """Get searcher state (alias for get_state).

        Returns:
            Dict containing searcher state
        """
        return self.get_state()

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        """Restore searcher state (alias for set_state).

        Args:
            state: Searcher state dictionary
        """
        self.set_state(state)

    def get_best(self, maximize: bool = True) -> Optional[Result]:
        """Get best result seen so far.

        Args:
            maximize: Whether to maximize (True) or minimize (False)

        Returns:
            Best result, or None if no valid results
        """
        valid_results = [r for r in self.history if r.is_valid()]
        if not valid_results:
            return None

        if maximize:
            return max(valid_results, key=lambda r: r.objective_value)
        else:
            return min(valid_results, key=lambda r: r.objective_value)
