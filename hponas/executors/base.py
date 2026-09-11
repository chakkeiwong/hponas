"""Base executor interface."""

from abc import ABC, abstractmethod
from typing import Callable, Any
from hponas.types import Trial, Result


class BaseExecutor(ABC):
    """Base class for trial executors.

    Contract (tested in tests/conformance/test_executor_contract.py):
    - execute() runs trial and returns result
    - Handles NaN, inf, timeout, exceptions
    - Checkpoint save/load works
    """

    @abstractmethod
    def execute(self, trial: Trial, objective_fn: Callable[[dict], float]) -> Result:
        """Execute trial and return result.

        Args:
            trial: Trial to execute
            objective_fn: Function that evaluates config and returns objective value

        Returns:
            Result of trial execution
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown executor and cleanup resources."""
        pass
