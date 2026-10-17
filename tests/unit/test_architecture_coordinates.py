"""Actual tensor shape, normalization and checkpoint compatibility of NAS axes."""

import pytest
import torch
from torch import nn

from hponas.architecture import build, compatible, get_architecture_axes, measure


@pytest.mark.parametrize("activation,kind", [("relu", nn.ReLU), ("tanh", nn.Tanh),
                                           ("elu", nn.ELU), ("gelu", nn.GELU), ("swish", nn.SiLU)])
@pytest.mark.parametrize("normalization", ["none", "layer_norm", "spectral_norm"])
def test_coordinates_construct_the_declared_executable_network(activation, kind, normalization):
    model = build({"width": 3, "depth": 2, "input_dim": 5, "output_dim": 2,
                   "activation": activation, "normalization": normalization, "lr": .01})
    assert (model.width, model.depth, model.input_dim, model.output_dim,
            model.activation, model.normalization) == (3, 2, 5, 2, activation, normalization)
    assert model(torch.zeros(4, 5)).shape == (4, 2)
    assert sum(type(m) is kind for m in model.modules()) == 2
    linear = [m for m in model.modules() if isinstance(m, nn.Linear)]
    assert [(m.in_features, m.out_features) for m in linear] == [(5, 3), (3, 3), (3, 2)]
    assert sum(isinstance(m, nn.LayerNorm) for m in model.modules()) == (2 if normalization == "layer_norm" else 0)
    assert [hasattr(m, "parametrizations") for m in linear] == ([True, True, False] if normalization == "spectral_norm" else [False]*3)
    params, flops = measure(model)
    assert params == 38 + (12 if normalization == "layer_norm" else 0)
    assert flops == 68


@pytest.mark.parametrize("field,value,message", [
    ("activation", "unknown", "Unsupported activation"),
    ("normalization", "unknown", "Unsupported normalization"),
    *[(field, value, "Network dimensions must be positive integers")
      for field in ("width", "depth", "input_dim", "output_dim") for value in (0, -1, 1.5)],
])
def test_invalid_coordinates_refuse_before_torch_construction(field, value, message):
    with pytest.raises(ValueError) as exc:
        build({field: value})
    assert str(exc.value) == message


@pytest.mark.parametrize("field,default,other", [("width", 64, 65), ("depth", 2, 3),
                                                ("input_dim", 4, 5), ("output_dim", 1, 2),
                                                ("normalization", "none", "layer_norm")])
def test_compatibility_matches_loading_with_explicit_and_implicit_defaults(field, default, other):
    assert compatible({}, {field: default}) and compatible({field: default}, {})
    build({field: default}).load_state_dict(build({}).state_dict(), strict=True)
    assert not compatible({}, {field: other}) and not compatible({field: other}, {})
    with pytest.raises(RuntimeError):
        build({field: other}).load_state_dict(build({}).state_dict(), strict=True)


def test_declared_categorical_axes_all_build_executable_models():
    axes = {row["name"]: row for row in get_architecture_axes()}
    for activation in axes["activation"]["bounds"]:
        for normalization in axes["normalization"]["bounds"]:
            model = build({"width": 3, "depth": 2, "activation": activation, "normalization": normalization})
            assert model(torch.zeros(2, 4)).shape == (2, 1)


def test_measure_counts_biasless_dense_layers_and_bias_independently():
    model = nn.Sequential(nn.Linear(4, 3, bias=False), nn.ReLU(), nn.Linear(3, 2))
    # 12 + 6 weights, 2 biases; 36 multiply/add operations and 2 bias additions.
    assert measure(model) == (20, 38)
