"""
Test architecture factory: Option A moderate coordinates.

Survey reference: Ch 9 sec:architecture-search-in-moderation, Ch 15 sec:archfactory.
R1 spike exit criterion: compatibility tests pass, incompatible pairs refuse correctly.
"""

from hponas.architecture import build, compatible, get_architecture_axes, measure, transfer_policy


def test_build_stub():
    """Build returns a model stub with typed coordinates."""
    config = {
        "width": 128,
        "depth": 3,
        "activation": "relu",
        "normalization": "layer_norm",
    }
    model = build(config)
    assert model.width == 128
    assert model.depth == 3
    assert model.activation == "relu"
    assert model.normalization == "layer_norm"


def test_build_defaults():
    """Build uses defaults for missing coordinates."""
    model = build({})
    assert model.width == 64  # default
    assert model.depth == 2  # default
    assert model.activation == "relu"
    assert model.normalization == "none"


def test_measure_stub():
    """Measure returns (param_count, flops) for a model."""
    config = {"width": 128, "depth": 3}
    model = build(config)
    params, flops = measure(model)

    # Spike: simple mock calculation
    assert params == 128 * 3 * 100
    assert flops == 128 * 3 * 1_000_000


def test_compatible_same_architecture():
    """Pure hyperparameter changes are compatible (Ch 15 contract)."""
    config_a = {"width": 128, "depth": 3, "lr": 0.01, "activation": "relu"}
    config_b = {"width": 128, "depth": 3, "lr": 0.001, "activation": "tanh"}

    # Width and depth match → compatible (activation/lr can differ)
    assert compatible(config_a, config_b)


def test_incompatible_width_change():
    """Width change is incompatible (Ch 15 contract, Ch 9 weight inheritance)."""
    config_a = {"width": 128, "depth": 3}
    config_b = {"width": 256, "depth": 3}

    # Width differs → incompatible
    assert not compatible(config_a, config_b)


def test_incompatible_depth_change():
    """Depth change is incompatible."""
    config_a = {"width": 128, "depth": 3}
    config_b = {"width": 128, "depth": 4}

    # Depth differs → incompatible
    assert not compatible(config_a, config_b)


def test_transfer_policy_restart():
    """Transfer policy is RESTART for spike (distillation deferred to Tier 2)."""
    config_parent = {"width": 128, "depth": 3}
    config_child = {"width": 256, "depth": 3}

    policy = transfer_policy(config_parent, config_child)
    assert policy == "RESTART"


def test_get_architecture_axes():
    """Architecture axes for Option A moderate coordinates (Ch 9 scope boundary)."""
    axes = get_architecture_axes()

    # Should have 4 axes: width, depth, activation, normalization
    assert len(axes) == 4

    # Find each axis
    width_axis = next(a for a in axes if a["name"] == "width")
    depth_axis = next(a for a in axes if a["name"] == "depth")
    activation_axis = next(a for a in axes if a["name"] == "activation")
    normalization_axis = next(a for a in axes if a["name"] == "normalization")

    # Width and depth are ordinal (Ch 9: ordinal axes)
    assert width_axis["kind"] == "ordinal"
    assert depth_axis["kind"] == "ordinal"

    # Activation and normalization are categorical (Ch 9: structural flags)
    assert activation_axis["kind"] == "categorical"
    assert normalization_axis["kind"] == "categorical"

    # Check bounds
    assert width_axis["bounds"] == (32, 512)
    assert depth_axis["bounds"] == (2, 4)
    assert "relu" in activation_axis["bounds"]
    assert "tanh" in activation_axis["bounds"]
    assert "spectral_norm" in normalization_axis["bounds"]


def test_conformance_compatible_predicate():
    """
    Conformance test: every compatible pair survives checkpoint load (Ch 15 contract).

    Survey: a workload that gets this predicate wrong produces silent garbage,
    so the conformance suite tests it directly.

    Spike: just verify the predicate logic is correct.
    Tier 0: test with real checkpoint load/save.
    """
    # Same architecture, different hyperparameters → should be compatible
    configs_compatible = [
        ({"width": 128, "depth": 3, "lr": 0.01}, {"width": 128, "depth": 3, "lr": 0.001}),
        ({"width": 64, "depth": 2, "activation": "relu"}, {"width": 64, "depth": 2, "activation": "tanh"}),
    ]

    for cfg_a, cfg_b in configs_compatible:
        assert compatible(cfg_a, cfg_b), f"Should be compatible: {cfg_a} vs {cfg_b}"

    # Different architecture → should be incompatible
    configs_incompatible = [
        ({"width": 128, "depth": 3}, {"width": 256, "depth": 3}),
        ({"width": 128, "depth": 3}, {"width": 128, "depth": 4}),
        ({"width": 128, "depth": 3}, {"width": 256, "depth": 4}),
    ]

    for cfg_a, cfg_b in configs_incompatible:
        assert not compatible(cfg_a, cfg_b), f"Should be incompatible: {cfg_a} vs {cfg_b}"
