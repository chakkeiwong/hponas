"""Core types and data structures for HPO-NAS."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import numpy as np


class ParameterType(Enum):
    """Parameter type in search space."""
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"
    CATEGORICAL = "categorical"
    INTEGER = "integer"


@dataclass
class Parameter:
    """Search space parameter definition."""
    name: str
    type: ParameterType
    bounds: Optional[tuple] = None  # For continuous/integer
    choices: Optional[List[Any]] = None  # For discrete/categorical
    log_scale: bool = False

    def __post_init__(self) -> None:
        """Validate parameter definition."""
        if self.type in [ParameterType.CONTINUOUS, ParameterType.INTEGER]:
            if self.bounds is None:
                raise ValueError(f"Parameter {self.name} requires bounds")
        elif self.type in [ParameterType.DISCRETE, ParameterType.CATEGORICAL]:
            if self.choices is None or len(self.choices) == 0:
                raise ValueError(f"Parameter {self.name} requires choices")


@dataclass
class Config:
    """Configuration (hyperparameter setting)."""
    values: Dict[str, Any]
    config_id: Optional[str] = None

    def __getitem__(self, key: str) -> Any:
        """Get parameter value."""
        return self.values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set parameter value."""
        self.values[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "values": self.values,
            "config_id": self.config_id,
        }


@dataclass
class Trial:
    """Trial (single evaluation)."""
    config: Config
    trial_id: str
    fidelity: float = 1.0
    status: str = "pending"  # pending, running, completed, failed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "config": self.config.to_dict(),
            "trial_id": self.trial_id,
            "fidelity": self.fidelity,
            "status": self.status,
        }


@dataclass
class Result:
    """Trial result."""
    trial_id: str
    objective_value: float
    cost: float = 1.0
    fidelity: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "completed"  # completed, failed, nan, timeout

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trial_id": self.trial_id,
            "objective_value": self.objective_value,
            "cost": self.cost,
            "fidelity": self.fidelity,
            "metadata": self.metadata,
            "status": self.status,
        }

    def is_valid(self) -> bool:
        """Check if result is valid (not NaN, not failed)."""
        if self.status != "completed":
            return False
        if not np.isfinite(self.objective_value):
            return False
        return True


@dataclass
class MultiObjectiveResult(Result):
    """Multi-objective trial result."""
    objective_values: np.ndarray = field(default_factory=lambda: np.array([]))

    def __post_init__(self) -> None:
        """Validate multi-objective result."""
        if len(self.objective_values) == 0:
            raise ValueError("objective_values must be non-empty")
        # Set objective_value to first objective for compatibility
        if self.objective_value == 0.0:
            self.objective_value = float(self.objective_values[0])


@dataclass
class SearchSpace:
    """Search space definition."""
    parameters: Dict[str, Parameter]

    def sample_random(self, seed: Optional[int] = None) -> Config:
        """Sample random configuration."""
        rng = np.random.RandomState(seed)
        values = {}

        for name, param in self.parameters.items():
            if param.type == ParameterType.CONTINUOUS:
                low, high = param.bounds
                if param.log_scale:
                    values[name] = np.exp(rng.uniform(np.log(low), np.log(high)))
                else:
                    values[name] = rng.uniform(low, high)

            elif param.type == ParameterType.INTEGER:
                low, high = param.bounds
                if param.log_scale:
                    log_val = rng.uniform(np.log(low), np.log(high))
                    values[name] = int(np.exp(log_val))
                else:
                    values[name] = rng.randint(low, high + 1)

            elif param.type in [ParameterType.DISCRETE, ParameterType.CATEGORICAL]:
                values[name] = rng.choice(param.choices)

        return Config(values=values)

    def validate_config(self, config: Config) -> bool:
        """Validate configuration against search space."""
        for name, param in self.parameters.items():
            if name not in config.values:
                return False

            value = config.values[name]

            if param.type in [ParameterType.CONTINUOUS, ParameterType.INTEGER]:
                low, high = param.bounds
                if not (low <= value <= high):
                    return False

            elif param.type in [ParameterType.DISCRETE, ParameterType.CATEGORICAL]:
                if value not in param.choices:
                    return False

        return True

    def dim(self) -> int:
        """Get dimensionality of search space."""
        return len(self.parameters)
