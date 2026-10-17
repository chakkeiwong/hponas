"""Real Brax PPO workload with durable policies and separate acceptance evaluation.

The objective returned to Study uses search seeds only. Protected seeds belong to
``evaluate_checkpoint`` after optimization and are never included in a Result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import partial
import json
from pathlib import Path
import time
import uuid

import numpy as np

from hponas.persistence import atomic_json

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


@dataclass(frozen=True)
class RLSettings:
    """Execution budget, fixed independently of the search space."""

    environment: str = "ant"
    backend: str = "generalized"
    max_timesteps: int = 1_000_000
    episode_length: int = 1000
    eval_episodes: int = 10
    num_evals: int = 5
    unroll_length: int = 10
    num_minibatches: int = 16
    num_updates_per_batch: int = 2

    def __post_init__(self):
        for name in (
            "max_timesteps",
            "episode_length",
            "eval_episodes",
            "num_evals",
            "unroll_length",
            "num_minibatches",
            "num_updates_per_batch",
        ):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def smoke(cls):
        return cls(
            environment="inverted_pendulum",
            max_timesteps=128,
            episode_length=16,
            eval_episodes=1,
            num_evals=2,
            unroll_length=2,
            num_minibatches=1,
            num_updates_per_batch=1,
        )


def _configuration(config):
    merged = {**DEFAULT_CONFIG, **config}
    if "width" in config or "depth" in config:
        width, depth = config.get("width", 256), config.get("depth", 2)
        if any(
            not isinstance(v, int) or isinstance(v, bool) or v < 1
            for v in (width, depth)
        ):
            raise ValueError("width and depth must be positive integers")
        merged["hidden_layer_sizes"] = [width] * depth
    return merged


def validate_config(config):
    try:
        c = _configuration(config)
        bounds = {
            "learning_rate": (1e-5, 1e-2),
            "num_envs": (32, 512),
            "batch_size": (64, 1024),
            "entropy_cost": (0.0, 0.1),
            "discounting": (0.95, 0.999),
            "reward_scaling": (0.1, 10.0),
            "gae_lambda": (0.9, 0.99),
        }
        for name, (lo, hi) in bounds.items():
            if not np.isfinite(c[name]) or not lo <= c[name] <= hi:
                return False, f"{name} out of range [{lo}, {hi}]"
        for name in ("num_envs", "batch_size"):
            if not isinstance(c[name], int) or isinstance(c[name], bool):
                return False, f"{name} must be an integer"
        if c["activation"] not in ("relu", "tanh", "swish"):
            return False, "Unsupported activation"
        if not isinstance(c["normalize_observations"], bool):
            return False, "normalize_observations must be boolean"
        if not c["hidden_layer_sizes"] or any(
            not isinstance(v, int) or isinstance(v, bool) or v < 1
            for v in c["hidden_layer_sizes"]
        ):
            return False, "hidden_layer_sizes must contain positive integers"
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    return True, None


def _network_factory(config):
    import jax
    from brax.training.agents.ppo import networks

    return partial(
        networks.make_ppo_networks,
        policy_hidden_layer_sizes=tuple(config["hidden_layer_sizes"]),
        value_hidden_layer_sizes=tuple(config["hidden_layer_sizes"]),
        activation={"relu": jax.nn.relu, "tanh": jax.numpy.tanh, "swish": jax.nn.silu}[
            config["activation"]
        ],
    )


def _evaluate(make_inference_fn, params, settings, seed):
    import jax
    import jax.numpy as jnp
    from brax import envs

    env = envs.get_environment(settings.environment, backend=settings.backend)
    inference = make_inference_fn(params, deterministic=True)

    def episode(key):
        key, reset_key = jax.random.split(key)
        state = env.reset(reset_key)

        def continuing(carry):
            state, _, _, steps = carry
            return (steps < settings.episode_length) & (state.done == 0)

        def step(carry):
            state, key, total, steps = carry
            key, action_key = jax.random.split(key)
            action, _ = inference(state.obs, action_key)
            state = env.step(state, action)
            # Include the terminal transition once, then stop. Continuing the
            # simulator after done can create NaNs; 0 * NaN is still NaN.
            return state, key, total + state.reward, steps + 1

        _, _, total, _ = jax.lax.while_loop(
            continuing,
            step,
            (state, key, jnp.array(0.0), jnp.array(0)),
        )
        return total

    # Preserve each episode's seed and stopping rule while evaluating the
    # independent trajectories together. vmap masks completed loop lanes;
    # a long episode must not extend another episode's accumulated reward.
    keys = jnp.stack([jax.random.PRNGKey(seed + i) for i in range(settings.eval_episodes)])
    returns = np.asarray(jax.jit(jax.vmap(episode))(keys)).astype(float).tolist()
    return {
        "value": float(np.mean(returns)),
        "std": float(np.std(returns)),
        "returns": returns,
        "seed": seed,
    }


def rl_routine(
    config,
    fidelity=1.0,
    seed=0,
    test_seed=None,
    *,
    settings=None,
    artifact_dir="artifacts/rl",
    trial_id=None,
):
    """Train PPO, persist model/curve/recipe, and return search evaluation only."""
    if test_seed is not None:
        raise ValueError(
            "Use evaluate_checkpoint after optimization for protected test seeds"
        )
    valid, error = validate_config(config)
    if not valid:
        raise ValueError(error)
    if not np.isfinite(fidelity) or not 0 < fidelity <= 1:
        raise ValueError("fidelity must be in (0,1]")
    settings = settings or RLSettings()
    c = _configuration(config)
    if c["batch_size"] * settings.num_minibatches % c["num_envs"]:
        raise ValueError("batch_size * num_minibatches must be divisible by num_envs")
    from brax import envs
    from brax.io import model
    from brax.training.agents.ppo import train

    started = time.monotonic()
    run_dir = (
        Path(artifact_dir).resolve() / f"{trial_id or 'trial'}_{uuid.uuid4().hex[:12]}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    curve = []

    def progress(steps, metrics):
        point = {
            "steps": int(steps),
            "seconds": time.monotonic() - started,
            "metrics": {
                k: float(v)
                for k, v in metrics.items()
                if np.ndim(v) == 0 and np.isfinite(v)
            },
        }
        curve.append(point)
        atomic_json(run_dir / "learning_curve.json", curve)

    make_inference, params, _ = train.train(
        environment=envs.get_environment(
            settings.environment, backend=settings.backend
        ),
        num_timesteps=max(1, int(settings.max_timesteps * fidelity)),
        episode_length=settings.episode_length,
        num_envs=c["num_envs"],
        batch_size=c["batch_size"],
        learning_rate=c["learning_rate"],
        entropy_cost=c["entropy_cost"],
        discounting=c["discounting"],
        reward_scaling=c["reward_scaling"],
        gae_lambda=c["gae_lambda"],
        normalize_observations=c["normalize_observations"],
        seed=seed,
        network_factory=_network_factory(c),
        unroll_length=settings.unroll_length,
        num_minibatches=settings.num_minibatches,
        num_updates_per_batch=settings.num_updates_per_batch,
        num_evals=settings.num_evals,
        num_eval_envs=settings.eval_episodes,
        max_devices_per_host=1,
        progress_fn=progress,
    )
    checkpoint = run_dir / "policy.pkl"
    model.save_params(str(checkpoint), params)
    search_seed = seed + 100_000
    evaluation = _evaluate(make_inference, params, settings, search_seed)
    atomic_json(
        run_dir / "recipe.json",
        {
            "config": c,
            "settings": asdict(settings),
            "training_seed": seed,
            "search_seed": search_seed,
        },
    )
    atomic_json(run_dir / "search_evaluation.json", evaluation)
    return {
        "value": evaluation["value"],
        "cost": time.monotonic() - started,
        "metadata": {
            "workload": "brax_ppo",
            "training_seed": seed,
            "search_seed": search_seed,
            "settings": asdict(settings),
            "search_returns": evaluation["returns"],
        },
        "artifacts": {
            "checkpoint": str(checkpoint),
            "learning_curve": str(run_dir / "learning_curve.json"),
            "recipe": str(run_dir / "recipe.json"),
        },
    }


def evaluate_checkpoint(checkpoint, seed):
    """Evaluate a trusted local policy on a protected seed after model selection.

    Brax policy files use pickle; load only checkpoints produced by trusted runs.
    This function returns a separate acceptance receipt, never a search Result.
    """
    from brax import envs
    from brax.io import model
    from brax.training.acme import running_statistics
    from brax.training.agents.ppo import networks

    checkpoint = Path(checkpoint)
    recipe = json.loads((checkpoint.parent / "recipe.json").read_text())
    settings = RLSettings(**recipe["settings"])
    excluded = {
        recipe["training_seed"],
        *range(recipe["search_seed"], recipe["search_seed"] + settings.eval_episodes),
    }
    if any(seed + i in excluded for i in range(settings.eval_episodes)):
        raise ValueError("Acceptance seed overlaps training or search evaluation")
    env = envs.get_environment(settings.environment, backend=settings.backend)
    kwargs = {}
    if recipe["config"]["normalize_observations"]:
        kwargs["preprocess_observations_fn"] = running_statistics.normalize
    network = _network_factory(recipe["config"])(
        env.observation_size, env.action_size, **kwargs
    )
    evaluation = _evaluate(
        networks.make_inference_fn(network),
        model.load_params(str(checkpoint)),
        settings,
        seed,
    )
    atomic_json(checkpoint.parent / f"acceptance_{seed}.json", evaluation)
    return evaluation
