"""Fixtures for integration tests."""
import pytest
import numpy as np
from hponas.types import SearchSpace, Parameter, ParameterType


@pytest.fixture
def simple_search_space():
    """Simple search space with mixed parameter types."""
    return SearchSpace(
        parameters={
            "x": Parameter("x", ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
            "y": Parameter("y", ParameterType.INTEGER, bounds=(1, 10)),
            "activation": Parameter("activation", ParameterType.CATEGORICAL, choices=["relu", "tanh"]),
        }
    )


@pytest.fixture
def complex_search_space():
    """Complex search space with log-scale and more parameters."""
    return SearchSpace(
        parameters={
            "lr": Parameter("lr", ParameterType.CONTINUOUS, bounds=(1e-4, 1e-1), log_scale=True),
            "batch_size": Parameter("batch_size", ParameterType.INTEGER, bounds=(16, 256), log_scale=True),
            "layers": Parameter("layers", ParameterType.INTEGER, bounds=(1, 10)),
            "width": Parameter("width", ParameterType.INTEGER, bounds=(32, 512)),
            "activation": Parameter("activation", ParameterType.CATEGORICAL, choices=["relu", "tanh", "gelu", "swish"]),
            "dropout": Parameter("dropout", ParameterType.CONTINUOUS, bounds=(0.0, 0.5)),
        }
    )


@pytest.fixture
def simple_objective():
    """Simple deterministic objective function."""
    def objective(config):
        return config["x"] ** 2 + config["y"]
    return objective


@pytest.fixture
def noisy_objective():
    """Objective function with noise."""
    rng = np.random.RandomState(42)

    def objective(config):
        base = config.get("x", 0.5) ** 2 + config.get("y", 5)
        noise = rng.normal(0, 0.1)
        return base + noise

    return objective


@pytest.fixture
def ray_objective():
    """Objective function suitable for Ray execution."""
    def objective(config, fidelity=1.0):
        # Simulate some computation
        result = sum(v for v in config.values() if isinstance(v, (int, float)))
        return {"objective_value": result * fidelity, "cost": 0.1}

    return objective
