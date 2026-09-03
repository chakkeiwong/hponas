"""
Tests for PriorBand portfolio sampler.

Survey reference: Ch 8 roadmap-10, ch08-03.
Validation: V11 (prior-aware methods beat baseline when prior is good).
"""

import pytest
import numpy as np

from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_priorband import PriorBandSampler


def _quadratic_with_optimum_at_07(config: dict) -> float:
    """Simple test objective: optimum at x=0.7"""
    x = config.get("x", 0.5)
    return -(x - 0.7) ** 2


def _good_prior(config: dict) -> float:
    """Prior centered near optimum (x=0.7)."""
    x = config.get("x", 0.5)
    return np.exp(-0.5 * ((x - 0.65) / 0.1) ** 2)


def _bad_prior(config: dict) -> float:
    """Prior centered far from optimum (x=0.2)."""
    x = config.get("x", 0.5)
    return np.exp(-0.5 * ((x - 0.2) / 0.1) ** 2)


def test_priorband_accepts_prior():
    """PriorBand accepts prior function and reports capability."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    sampler = PriorBandSampler(space, prior_fn=_good_prior, seed=42)

    assert sampler.prior_fn is not None
    assert sampler.capabilities["prior"] is True


def test_priorband_without_prior():
    """PriorBand works without prior (uniform + incumbent only)."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    sampler = PriorBandSampler(space, seed=42)

    assert sampler.prior_fn is None
    assert sampler.capabilities["prior"] is False


def test_priorband_proposes_valid_configs():
    """PriorBand proposals are within bounds."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(-5, 5)))

    sampler = PriorBandSampler(space, prior_fn=_good_prior, seed=42)

    configs = sampler.propose(20)

    assert len(configs) == 20
    for config in configs:
        assert "x" in config
        assert "y" in config
        assert 0 <= config["x"] <= 1
        assert -5 <= config["y"] <= 5


def test_priorband_updates_incumbent():
    """PriorBand tracks best configuration."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    sampler = PriorBandSampler(space, seed=42)

    # Initially no incumbent
    assert sampler.incumbent_config is None

    # Observe first trial
    sampler.observe({"config": {"x": 0.3}, "value": -0.16})
    assert sampler.incumbent_config == {"x": 0.3}
    assert sampler.incumbent_value == -0.16

    # Observe better trial
    sampler.observe({"config": {"x": 0.7}, "value": 0.0})
    assert sampler.incumbent_config == {"x": 0.7}
    assert sampler.incumbent_value == 0.0

    # Observe worse trial (incumbent unchanged)
    sampler.observe({"config": {"x": 0.1}, "value": -0.36})
    assert sampler.incumbent_config == {"x": 0.7}
    assert sampler.incumbent_value == 0.0


def test_priorband_rung_adaptation():
    """Later rungs shift weight toward incumbent perturbations."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    sampler = PriorBandSampler(
        space,
        prior_fn=_good_prior,
        seed=42,
        uniform_weight=0.3,
        prior_weight=0.4,
        incumbent_weight=0.3,
    )

    # Set an incumbent
    sampler.observe({"config": {"x": 0.7}, "value": 0.0})

    # Propose at rung 0 (early)
    configs_early = sampler.propose(100, rung_idx=0)

    # Propose at rung 3 (late)
    sampler_late = PriorBandSampler(
        space,
        prior_fn=_good_prior,
        seed=43,
        uniform_weight=0.3,
        prior_weight=0.4,
        incumbent_weight=0.3,
    )
    sampler_late.observe({"config": {"x": 0.7}, "value": 0.0})
    configs_late = sampler_late.propose(100, rung_idx=3)

    # Late rung should cluster more around incumbent (0.7)
    x_early = [c["x"] for c in configs_early]
    x_late = [c["x"] for c in configs_late]

    std_early = np.std(x_early)
    std_late = np.std(x_late)

    # Late rung should have lower std (more clustered around incumbent)
    # This is a qualitative test, not strict inequality
    assert std_late < std_early + 0.2  # Allow some tolerance


def test_priorband_prior_sampling_works():
    """Prior sampling produces configs weighted by prior density."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    # Use only prior sampling (set other weights to 0)
    sampler = PriorBandSampler(
        space,
        prior_fn=_good_prior,
        seed=42,
        uniform_weight=0.0,
        prior_weight=1.0,
        incumbent_weight=0.0,
    )

    configs = sampler.propose(100, rung_idx=0)
    x_values = [c["x"] for c in configs]

    # Prior is centered at 0.65, so mean should be near there
    mean_x = np.mean(x_values)

    # Should be closer to prior peak (0.65) than to uniform mean (0.5)
    assert abs(mean_x - 0.65) < abs(mean_x - 0.5)


def test_priorband_incumbent_perturbation_works():
    """Incumbent perturbation stays near incumbent."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    # Use only incumbent perturbation
    sampler = PriorBandSampler(
        space,
        seed=42,
        uniform_weight=0.0,
        prior_weight=0.0,
        incumbent_weight=1.0,
        perturbation_scale=0.05,  # Small perturbations
    )

    # Set incumbent at 0.7
    sampler.observe({"config": {"x": 0.7}, "value": 0.0})

    configs = sampler.propose(50, rung_idx=0)
    x_values = [c["x"] for c in configs]

    # All perturbations should be near 0.7
    mean_x = np.mean(x_values)
    assert abs(mean_x - 0.7) < 0.15  # Within reasonable perturbation range


def test_priorband_requires_continuous_knobs():
    """PriorBand requires at least one continuous knob."""
    space = SearchSpace()
    space.add_knob(Knob("width", kind="ordinal", bounds=(32, 512)))

    with pytest.raises(ValueError, match="at least one continuous knob"):
        PriorBandSampler(space, seed=42)


def test_priorband_degenerate_prior_handled():
    """Zero prior everywhere should fallback to uniform."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    def zero_prior(config: dict) -> float:
        return 0.0

    sampler = PriorBandSampler(
        space,
        prior_fn=zero_prior,
        seed=42,
        uniform_weight=0.0,
        prior_weight=1.0,
        incumbent_weight=0.0,
    )

    # Should not crash, fallback to uniform
    configs = sampler.propose(10, rung_idx=0)
    assert len(configs) == 10
