"""Brax PPO architecture axes affect actual parameters and executable outputs."""

from dataclasses import asdict
import json

import numpy as np
import pytest

from workloads.rl_routine import RLSettings, _configuration, _network_factory, evaluate_checkpoint


@pytest.mark.parametrize("width,depth", [(2, 1), (3, 2)])
@pytest.mark.parametrize("activation", ["relu", "tanh", "swish"])
def test_brax_policy_and_value_networks_use_the_declared_axes(width, depth, activation):
    import jax
    import jax.numpy as jnp

    networks = _network_factory(_configuration({"width": width, "depth": depth,
                                                "activation": activation}))(5, 2)
    observations = jnp.array([[-1., -.5, 0., .5, 1.], [1., -2., 3., -4., 5.]])
    for network, outputs in [(networks.policy_network, 4), (networks.value_network, 1)]:
        params = network.init(jax.random.PRNGKey(7))
        layers = params["params"]
        assert list(layers) == [f"hidden_{i}" for i in range(depth+1)]
        assert [layers[f"hidden_{i}"]["kernel"].shape for i in range(depth+1)] == (
            [(5, width)] + [(width, width)] * (depth-1) + [(width, outputs)])
        expected = np.asarray(observations)
        for i in range(depth+1):
            layer = layers[f"hidden_{i}"]
            expected = expected @ np.asarray(layer["kernel"]) + np.asarray(layer["bias"])
            if i < depth:
                if activation == "relu":
                    expected = np.maximum(expected, 0.)
                elif activation == "tanh":
                    expected = np.tanh(expected)
                else:
                    expected = expected / (1. + np.exp(-expected))
        if outputs == 1:
            expected = expected[..., 0]
        actual = np.asarray(network.apply(None, params, observations))
        assert actual.shape == expected.shape
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-6)


@pytest.mark.parametrize("protected_seed", [17, 16, 15, 100, 101, 102, 99, 98])
def test_protected_episode_range_cannot_overlap_training_or_search(tmp_path, monkeypatch, protected_seed):
    from brax import envs
    from brax.io import model

    recipe = {"settings": asdict(RLSettings(eval_episodes=3)), "training_seed": 17,
              "search_seed": 100, "config": _configuration({})}
    (tmp_path / "recipe.json").write_text(json.dumps(recipe))
    monkeypatch.setattr(envs, "get_environment", lambda *a, **k: pytest.fail("Overlap reached environment construction"))
    monkeypatch.setattr(model, "load_params", lambda *a, **k: pytest.fail("Overlap reached policy loading"))
    with pytest.raises(ValueError, match="^Acceptance seed overlaps training or search evaluation$"):
        evaluate_checkpoint(tmp_path / "policy", protected_seed)
