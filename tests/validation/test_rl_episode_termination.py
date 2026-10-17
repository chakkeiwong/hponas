"""Episode totals stop at done; invalid active rewards are never erased."""

from collections import namedtuple
import math
from types import SimpleNamespace

import pytest

from workloads.rl_routine import RLSettings, _evaluate

State = namedtuple("State", "obs reward done")


@pytest.mark.parametrize("terminal,limit,poison_at,expected", [
    (2, 1000, 3, 12.),       # Terminal reward 7 counted; poison after done unseen.
    (100, 3, 100, 21.),      # A live episode still respects its finite horizon.
    (2, 1000, 2, math.nan),  # Invalid terminal reward is a real failed outcome.
    (100, 3, 2, math.nan),   # Invalid live reward is not masked or imputed.
    (0, 1000, 1, 0.),       # A reset already marked done has no transitions.
])
def test_exact_episode_stopping_and_failure_boundary(monkeypatch, terminal, limit, poison_at, expected):
    import jax.numpy as jnp
    from brax import envs

    def reset(key):
        return State(jnp.array(0), jnp.array(0.), jnp.array(float(terminal == 0)))

    def step(state, action):
        count = state.obs + 1
        reward = jnp.where(count >= poison_at, jnp.nan, 2. * count + 3.)
        return State(count, reward, jnp.asarray(count >= terminal, dtype=float))

    monkeypatch.setattr(envs, "get_environment", lambda *a, **k: SimpleNamespace(reset=reset, step=step))
    result = _evaluate(lambda params, deterministic: lambda obs, key: (0., {}), None,
                       RLSettings(episode_length=limit, eval_episodes=3), 1916)
    if math.isnan(expected):
        assert all(math.isnan(value) for value in result["returns"])
        assert math.isnan(result["value"])
    else:
        assert result["returns"] == [expected] * 3
        assert result["value"] == expected and result["std"] == 0


def test_batched_episodes_keep_individual_seeds_stops_and_nonfinite_failures(monkeypatch):
    import jax
    import jax.numpy as jnp
    from brax import envs

    def reset(key):
        stop = key[0] % 5
        return State(jnp.array([0, stop]), jnp.array(0.), jnp.asarray(stop == 0, dtype=float))

    def step(state, action):
        count, stop = state.obs[0] + 1, state.obs[1]
        poison = (count > stop) | ((stop == 4) & (count == 2))
        reward = jnp.where(poison, jnp.nan, 2. * count + 3.)
        return State(jnp.array([count, stop]), reward, jnp.asarray(count >= stop, dtype=float))

    monkeypatch.setattr(envs, "get_environment", lambda *a, **k: SimpleNamespace(reset=reset, step=step))
    seed, episodes = 1916, 20
    stops = [int(jax.random.split(jax.random.PRNGKey(seed + i))[1][0] % 5) for i in range(episodes)]
    assert set(stops) == {0, 1, 2, 3, 4}
    result = _evaluate(lambda params, deterministic: lambda obs, key: (0., {}), None,
                       RLSettings(episode_length=6, eval_episodes=episodes), seed)
    assert result["seed"] == seed and len(result["returns"]) == episodes
    for stop, value in zip(stops, result["returns"]):
        if stop == 4:
            assert math.isnan(value)
        else:
            assert value == sum(2 * step + 3 for step in range(1, stop + 1))
    assert math.isnan(result["value"])
