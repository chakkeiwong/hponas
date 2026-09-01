"""
rl_routine workload: day-one walk template from Chapter 15.

Survey reference: Ch 15 sec:day-one-walk, Ch 9 (RL regime).
Survey verdict: include, T0, ~8 engineer-days (real PPO/Brax integration).

Validation: V14 (day-one walk reproduction, seed isolation).

This is the "routine RL" regime from Ch 9: minutes-scale trials, Sobol/TPE/GP sufficient,
ASHA worthwhile, local executor is fine. The task is PPO on a Brax locomotion environment
with a moderate hyperparameter space (10-15 knobs).

Tier 0 requirements:
- Real PPO implementation (not stub)
- Real Brax environment (ant, humanoid, or halfcheetah)
- Seed isolation: protected test seeds never reach the searcher
- Configuration validation: reject invalid configs early
- Artifact outputs: checkpoints, learning curves, final policy
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

try:
    import jax
    import jax.numpy as jnp
    import brax
    from brax import envs
    from brax.training import ppo
    JAX_AVAILABLE = True
except ImportError:
    JAX_AVAILABLE = False


def rl_routine(
    config: dict[str, Any],
    fidelity: float = 1.0,
    seed: int = 0,
    test_seed: Optional[int] = None,
) -> dict[str, Any]:
    """
    RL routine workload: PPO on Brax locomotion.

    Args:
        config: Hyperparameter configuration
        fidelity: Training budget (fraction of max_timesteps)
        seed: Training seed
        test_seed: Protected test seed (for V14 validation, must never reach searcher)

    Returns:
        dict with keys: value (maximize), cost (seconds), artifacts (paths)

    Config schema (Ch 15):
        learning_rate: float in [1e-5, 1e-2], log-scale
        num_envs: int in [32, 512], ordinal
        batch_size: int in [64, 1024], ordinal
        entropy_cost: float in [0.0, 0.1]
        discounting: float in [0.95, 0.999]
        reward_scaling: float in [0.1, 10.0], log-scale
        gae_lambda: float in [0.9, 0.99]
        normalize_observations: bool (categorical: [True, False])
        activation: str (categorical: ["relu", "tanh", "swish"])
        hidden_layer_sizes: list[int] (e.g., [256, 256])

    V14 requirements:
        - test_seed is used only for final evaluation, never for training
        - Training uses seed only
        - Final return is evaluated on test_seed environment
    """
    if not JAX_AVAILABLE:
        raise ImportError("rl_routine requires jax and brax: pip install jax brax")

    # Validate config
    required_keys = [
        "learning_rate", "num_envs", "batch_size", "entropy_cost",
        "discounting", "reward_scaling", "gae_lambda",
        "normalize_observations", "activation", "hidden_layer_sizes"
    ]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"rl_routine: missing required config key: {key}")

    # Extract config
    lr = config["learning_rate"]
    num_envs = config["num_envs"]
    batch_size = config["batch_size"]
    entropy_cost = config["entropy_cost"]
    discounting = config["discounting"]
    reward_scaling = config["reward_scaling"]
    gae_lambda = config["gae_lambda"]
    normalize_observations = config["normalize_observations"]
    activation = config["activation"]
    hidden_layer_sizes = config["hidden_layer_sizes"]

    # Max timesteps for full fidelity
    max_timesteps = 1_000_000
    num_timesteps = int(max_timesteps * fidelity)

    # Environment: ant locomotion (Ch 9)
    env_name = "ant"
    env = envs.get_environment(env_name)

    # Training (use seed only, test_seed is protected)
    start_time = time.time()

    # PPO training parameters
    episode_length = 1000
    num_updates = num_timesteps // (num_envs * episode_length)

    # Network architecture from config
    network_factory = lambda: ppo.make_ppo_networks(
        env.observation_size,
        env.action_size,
        hidden_layer_sizes=hidden_layer_sizes,
    )

    # Train
    train_fn = ppo.train(
        environment=env,
        num_timesteps=num_timesteps,
        episode_length=episode_length,
        num_envs=num_envs,
        learning_rate=lr,
        entropy_cost=entropy_cost,
        discounting=discounting,
        reward_scaling=reward_scaling,
        gae_lambda=gae_lambda,
        normalize_observations=normalize_observations,
        seed=seed,
        batch_size=batch_size,
        network_factory=network_factory,
    )

    make_inference_fn, params, _ = train_fn

    training_time = time.time() - start_time

    # Evaluation on test_seed (V14: protected seed never used for training)
    if test_seed is not None:
        eval_seed = test_seed
    else:
        eval_seed = seed + 1000  # Default: offset from training seed

    # Evaluate policy
    eval_env = envs.get_environment(env_name)
    jit_inference_fn = jax.jit(make_inference_fn(params))

    # Run evaluation episodes
    n_eval_episodes = 10
    returns = []

    for ep in range(n_eval_episodes):
        rng = jax.random.PRNGKey(eval_seed + ep)
        state = eval_env.reset(rng)
        episode_return = 0.0

        for step in range(episode_length):
            obs = state.obs
            action, _ = jit_inference_fn(obs)
            state = eval_env.step(state, action)
            episode_return += state.reward

        returns.append(float(episode_return))

    mean_return = np.mean(returns)
    std_return = np.std(returns)

    total_time = time.time() - start_time

    return {
        "value": mean_return,  # Maximize return
        "cost": total_time,
        "std": std_return,
        "train_time": training_time,
        "artifacts": {
            "params": params,  # Trained policy parameters
            "n_eval_episodes": n_eval_episodes,
        },
    }


def validate_config(config: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate rl_routine config before execution.

    Returns: (valid, error_message)
    """
    # Check required keys
    required = [
        "learning_rate", "num_envs", "batch_size", "entropy_cost",
        "discounting", "reward_scaling", "gae_lambda",
        "normalize_observations", "activation", "hidden_layer_sizes"
    ]
    for key in required:
        if key not in config:
            return False, f"Missing required key: {key}"

    # Validate ranges
    lr = config["learning_rate"]
    if not (1e-5 <= lr <= 1e-2):
        return False, f"learning_rate {lr} out of range [1e-5, 1e-2]"

    num_envs = config["num_envs"]
    if not (32 <= num_envs <= 512):
        return False, f"num_envs {num_envs} out of range [32, 512]"

    batch_size = config["batch_size"]
    if not (64 <= batch_size <= 1024):
        return False, f"batch_size {batch_size} out of range [64, 1024]"

    entropy_cost = config["entropy_cost"]
    if not (0.0 <= entropy_cost <= 0.1):
        return False, f"entropy_cost {entropy_cost} out of range [0.0, 0.1]"

    discounting = config["discounting"]
    if not (0.95 <= discounting <= 0.999):
        return False, f"discounting {discounting} out of range [0.95, 0.999]"

    reward_scaling = config["reward_scaling"]
    if not (0.1 <= reward_scaling <= 10.0):
        return False, f"reward_scaling {reward_scaling} out of range [0.1, 10.0]"

    gae_lambda = config["gae_lambda"]
    if not (0.9 <= gae_lambda <= 0.99):
        return False, f"gae_lambda {gae_lambda} out of range [0.9, 0.99]"

    activation = config["activation"]
    if activation not in ["relu", "tanh", "swish"]:
        return False, f"activation {activation} not in ['relu', 'tanh', 'swish']"

    return True, None


# Default configuration for testing
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
