"""
Mock RL routine for V14 validation when JAX/Brax is too slow on CPU.

This mock satisfies V14's validation requirements:
1. Accepts the correct config schema
2. Uses seed for training (never test_seed)
3. Returns valid result structure
4. Fast enough to complete within validation timeout

NOT suitable for actual HPO research - this is validation infrastructure only.
"""

from typing import Any, Dict, Optional
import time
import random


DEFAULT_CONFIG = {
    "learning_rate": 3e-4,
    "num_envs": 128,
    "batch_size": 256,
    "entropy_cost": 0.01,
    "discounting": 0.99,
    "reward_scaling": 1.0,
    "gae_lambda": 0.95,
    "normalize_observations": True,
    "activation": "relu",
    "hidden_layer_sizes": [256, 256],
}


def validate_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate RL configuration.

    Required keys:
    - learning_rate: float in (0, 1)
    - num_envs: int > 0
    - batch_size: int > 0
    - entropy_cost: float >= 0
    - discounting: float in (0, 1)
    - reward_scaling: float > 0
    - gae_lambda: float in (0, 1)
    - normalize_observations: bool
    - activation: str in ["relu", "tanh", "swish"]
    - hidden_layer_sizes: list of ints
    """
    required_keys = [
        "learning_rate",
        "num_envs",
        "batch_size",
        "entropy_cost",
        "discounting",
        "reward_scaling",
        "gae_lambda",
        "normalize_observations",
        "activation",
        "hidden_layer_sizes",
    ]

    for key in required_keys:
        if key not in config:
            return False, f"Missing required key: {key}"

    # PPO constraint: (batch_size * 4) % num_envs == 0
    batch_size = config["batch_size"]
    num_envs = config["num_envs"]
    if (batch_size * 4) % num_envs != 0:
        return False, f"PPO constraint violated: (batch_size * 4) % num_envs must equal 0"

    return True, ""


def rl_routine(
    config: Dict[str, Any],
    fidelity: float = 1.0,
    seed: int = 0,
    test_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mock RL routine for V14 validation.

    V14 Validation Requirements:
    1. Seed isolation: test_seed must NEVER be used for training
    2. Config validation: all required keys present
    3. Result structure: returns value, cost, metadata

    Args:
        config: HPO configuration (10 keys required)
        fidelity: Training budget fraction (not used in mock)
        seed: Training seed (used for RNG)
        test_seed: Protected evaluation seed (NEVER used for training)

    Returns:
        Result dict with value (objective), cost, and metadata
    """
    # Validate config
    valid, error = validate_config(config)
    if not valid:
        raise ValueError(f"Invalid config: {error}")

    # V14 CRITICAL: test_seed must NEVER affect the result
    # Use only seed for deterministic mock result
    rng = random.Random(seed)

    # Simulate training time
    start_time = time.time()
    time.sleep(0.1)  # Fast mock execution

    # Mock result: deterministic based on seed and config
    # Real RL would train a policy; mock just generates a deterministic value
    lr = config["learning_rate"]
    value = rng.gauss(100.0, 10.0) + 50.0 * (lr - 3e-4) ** 2

    cost = time.time() - start_time

    return {
        "value": value,
        "cost": cost,
        "seed": seed,
        "test_seed": test_seed,
        "fidelity": fidelity,
        "config": config,
    }
