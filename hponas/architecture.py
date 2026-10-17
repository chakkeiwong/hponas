"""
Architecture factory: build/measure/compatible/transfer for Option A moderate coordinates.

Survey reference: Ch 9 sec:architecture-search-in-moderation, Ch 15 sec:archfactory, Ch 6 (distillation).

Dense models are constructed from width/depth/activation/normalization coordinates.
Tier 0: real build for simple MLP (width/depth/activation).
Tier 2: real measure (count params/FLOPs), distillation transfer policy.
"""

from __future__ import annotations

from typing import Any, Literal
import torch
from torch import nn

TransferPolicy = Literal["RESTART", "DISTILL"]


class CoordinateMLP(nn.Sequential):
    """An actual dense network; attributes retain the architecture coordinates."""

    def __init__(
        self,
        width=64,
        depth=2,
        activation="relu",
        normalization="none",
        input_dim=4,
        output_dim=1,
    ):
        activations = {
            "relu": nn.ReLU,
            "tanh": nn.Tanh,
            "elu": nn.ELU,
            "gelu": nn.GELU,
            "swish": nn.SiLU,
        }
        if activation not in activations:
            raise ValueError("Unsupported activation")
        if normalization not in ("none", "layer_norm", "spectral_norm"):
            raise ValueError("Unsupported normalization")
        if any(
            not isinstance(v, int) or v < 1
            for v in (width, depth, input_dim, output_dim)
        ):
            raise ValueError("Network dimensions must be positive integers")
        layers = []
        previous = input_dim
        for _ in range(depth):
            linear = nn.Linear(previous, width)
            if normalization == "spectral_norm":
                linear = nn.utils.parametrizations.spectral_norm(linear)
            layers.append(linear)
            if normalization == "layer_norm":
                layers.append(nn.LayerNorm(width))
            layers.append(activations[activation]())
            previous = width
        layers.append(nn.Linear(previous, output_dim))
        super().__init__(*layers)
        self.width, self.depth, self.activation, self.normalization = (
            width,
            depth,
            activation,
            normalization,
        )
        self.input_dim, self.output_dim = input_dim, output_dim


def build(config: dict[str, Any]) -> CoordinateMLP:
    return CoordinateMLP(
        **{
            k: config[k]
            for k in (
                "width",
                "depth",
                "activation",
                "normalization",
                "input_dim",
                "output_dim",
            )
            if k in config
        }
    )


def measure(model: CoordinateMLP) -> tuple[int, int]:
    """Actual trainable parameters and dense-layer multiply/add FLOPs per example.

    FLOPs exclude activation, normalization and spectral parametrization overhead;
    they are an explicitly scoped operation count, not measured device latency.
    """
    params = sum(p.numel() for p in model.parameters())
    flops = sum(
        2 * m.in_features * m.out_features
        + (m.out_features if m.bias is not None else 0)
        for m in model.modules()
        if isinstance(m, nn.Linear)
    )
    return params, flops


def compatible(config_a: dict[str, Any], config_b: dict[str, Any]) -> bool:
    """
    Declare whether weights from config_a's model can load into config_b's (Ch 15 contract).

    Survey: pure hyperparameter changes are compatible; a width or depth change is not.
    The scheduler's exploit verb consults this before checkpoint surgery.
    A wrong answer produces silent garbage, so the conformance suite tests it directly.

    Spike: width and depth must match; activation and normalization can differ.
    Tier 0: same rule with real architecture coordinates.
    """
    defaults = {
        "width": 64,
        "depth": 2,
        "input_dim": 4,
        "output_dim": 1,
        "normalization": "none",
    }
    return all(config_a.get(k, v) == config_b.get(k, v) for k, v in defaults.items())


def transfer_policy(parent: dict[str, Any], child: dict[str, Any]) -> TransferPolicy:
    """
    Policy for incompatible inheritance (Ch 15 contract, Ch 9 distillation cost).

    Survey: restart from initialization, or warm-start by distillation (BG-PBT's route, Ch 6).
    The choice is declared per study, and its cost is charged to the trial that caused it.

    Spike: always RESTART (distillation deferred to Tier 2).
    Tier 2: add DISTILL option (~6d implementation per work breakdown).
    """
    return "RESTART"


def get_architecture_axes() -> list[dict[str, Any]]:
    """
    Return the architecture knob declarations for Option A moderate coordinates (Ch 9, Ch 15).

    Survey scope (Ch 9): width and depth as ordinal axes, a small number of structural flags
    as categorical axes.

    Spike: returns the schema for rl_routine PPO policy network (width, depth, activation, normalization).
    Tier 0: used by rl_routine workload template to construct its SearchSpace.
    """
    return [
        {
            "name": "width",
            "kind": "ordinal",
            "bounds": (32, 512),  # policy network width
            "note": "Hidden layer width (ordinal per Ch 9)",
        },
        {
            "name": "depth",
            "kind": "ordinal",
            "bounds": (2, 4),  # policy network depth
            "note": "Number of hidden layers (ordinal per Ch 9)",
        },
        {
            "name": "activation",
            "kind": "categorical",
            "bounds": ["relu", "tanh", "elu"],
            "note": "Activation function (categorical per Ch 9)",
        },
        {
            "name": "normalization",
            "kind": "categorical",
            "bounds": ["none", "layer_norm", "spectral_norm"],
            "note": "Normalization choice (categorical per Ch 9, spectral_norm per running example)",
        },
    ]
