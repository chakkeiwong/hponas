"""
Architecture factory: build/measure/compatible/transfer for Option A moderate coordinates.

Survey reference: Ch 9 sec:architecture-search-in-moderation, Ch 15 sec:archfactory, Ch 6 (distillation).

R1 spike: stubs only (build returns mock, measure returns fake counts, transfer=RESTART).
Tier 0: real build for simple MLP (width/depth/activation).
Tier 2: real measure (count params/FLOPs), distillation transfer policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TransferPolicy = Literal["RESTART", "DISTILL"]


@dataclass
class ModelStub:
    """
    Stub model object for spike.
    Tier 0: replace with real Flax/Haiku/PyTorch model construction.
    """
    width: int
    depth: int
    activation: str
    normalization: str


def build(config: dict[str, Any]) -> ModelStub:
    """
    Build a model from architecture coordinates (Ch 15 archfactory contract).

    Survey: the workload supplies this; the product never constructs architectures itself.
    The factory is what makes excluded methods excluded by construction: a coordinates→model
    map has no place to put a supernet.

    Spike: returns a stub with typed coordinates.
    Tier 0: real model construction for rl_routine MLP.
    """
    width = config.get("width", 64)
    depth = config.get("depth", 2)
    activation = config.get("activation", "relu")
    normalization = config.get("normalization", "none")
    return ModelStub(
        width=width,
        depth=depth,
        activation=activation,
        normalization=normalization,
    )


def measure(model: ModelStub) -> tuple[int, int]:
    """
    Return (parameter_count, flops_per_forward) for a built model (Ch 15 contract).

    Survey: measured on the constructed model rather than predicted from coordinates, which
    is the reason Ch 9 was willing to treat size as an objective and unwilling to treat
    proxies as a substitute for training.

    Spike: simple mock calculation.
    Tier 0: real param count (sum of parameter tensors).
    Tier 2: real FLOPs (via torch.profiler or manual accounting).
    """
    params = model.width * model.depth * 100  # mock: ~width*depth*100 parameters
    flops = model.width * model.depth * 1_000_000  # mock: ~width*depth*1e6 FLOPs
    return (params, flops)


def compatible(config_a: dict[str, Any], config_b: dict[str, Any]) -> bool:
    """
    Declare whether weights from config_a's model can load into config_b's (Ch 15 contract).

    Survey: pure hyperparameter changes are compatible; a width or depth change is not.
    The scheduler's exploit verb consults this before checkpoint surgery.
    A wrong answer produces silent garbage, so the conformance suite tests it directly.

    Spike: width and depth must match; activation and normalization can differ.
    Tier 0: same rule with real architecture coordinates.
    """
    return (
        config_a.get("width") == config_b.get("width")
        and config_a.get("depth") == config_b.get("depth")
    )


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
