"""
Tests for cost-aware searchers.

Survey: Ch 8 roadmap-12
"""

import numpy as np
import pytest

from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_cost import (
    CostModelGP,
    linear_cooling_schedule,
    CostAwareGPSearcher,
)


def _simple_space() -> SearchSpace:
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    return space


def test_cost_model_cold_start():
    """Cost model returns default before seeing data."""
    space = _simple_space()
    model = CostModelGP(space)

    # Before any observations, predict returns default (1.0 second)
    preds = model.predict([{"x": 0.5}])
    assert preds.shape == (1,)
    assert preds[0] == 1.0


def test_cost_model_learns_from_observations():
    """Cost model learns cost trends from observations."""
    space = _simple_space()
    model = CostModelGP(space)

    # Observe: x near 0 is fast, x near 1 is slow
    model.observe({"x": 0.1}, cost=1.0)
    model.observe({"x": 0.9}, cost=10.0)
    model.observe({"x": 0.2}, cost=1.5)
    model.observe({"x": 0.8}, cost=9.0)

    # Predict: x=0 should be fast, x=1 should be slow
    pred_fast = model.predict([{"x": 0.0}])
    pred_slow = model.predict([{"x": 1.0}])

    assert pred_fast[0] < pred_slow[0], (
        f"Expected low x to be faster, got {pred_fast[0]:.2f} vs {pred_slow[0]:.2f}"
    )


def test_cost_model_rejects_nonpositive_cost():
    """Cost model requires positive costs."""
    space = _simple_space()
    model = CostModelGP(space)

    with pytest.raises(ValueError, match="Cost must be positive"):
        model.observe({"x": 0.5}, cost=0.0)

    with pytest.raises(ValueError, match="Cost must be positive"):
        model.observe({"x": 0.5}, cost=-1.0)


def test_linear_cooling_schedule():
    """Temperature anneals from 0 to 1."""
    # Warmup phase: T=0
    assert linear_cooling_schedule(0, warmup=5, cooldown_duration=10) == 0.0
    assert linear_cooling_schedule(4, warmup=5, cooldown_duration=10) == 0.0

    # Cooldown phase: T increases linearly
    assert linear_cooling_schedule(5, warmup=5, cooldown_duration=10) == 0.0
    assert 0.4 < linear_cooling_schedule(10, warmup=5, cooldown_duration=10) < 0.6
    assert linear_cooling_schedule(15, warmup=5, cooldown_duration=10) == 1.0

    # Post-cooldown: T=1
    assert linear_cooling_schedule(20, warmup=5, cooldown_duration=10) == 1.0
    assert linear_cooling_schedule(100, warmup=5, cooldown_duration=10) == 1.0


def test_cost_aware_searcher_accepts_cost():
    """CostAwareGPSearcher accepts cost in observations."""
    from hponas.searchers_sobol import SobolSearcher

    space = _simple_space()

    searcher = CostAwareGPSearcher(
        space,
        base_searcher_factory=lambda s: SobolSearcher(s, seed=42),
        warmup=2,
        cooldown_duration=5,
        seed=42,
    )

    # Should not crash
    configs = searcher.propose(3)
    assert len(configs) == 3

    searcher.observe({"config": configs[0], "value": 0.5, "cost": 1.0})
    searcher.observe({"config": configs[1], "value": 0.8, "cost": 5.0})

    # Cost model should have learned
    assert searcher.cost_model._train_y == [np.log(1.0), np.log(5.0)]


def test_cost_aware_searcher_capabilities():
    """CostAwareGPSearcher exposes cost_aware capability."""
    from hponas.searchers_sobol import SobolSearcher

    space = _simple_space()

    searcher = CostAwareGPSearcher(
        space,
        base_searcher_factory=lambda s: SobolSearcher(s, seed=42),
        seed=42,
    )

    assert "cost_aware" in searcher.capabilities
    assert searcher.capabilities["cost_aware"] is True


def test_cost_aware_warmup_phase():
    """During warmup, temperature is 0 (ignore cost)."""
    from hponas.searchers_sobol import SobolSearcher

    space = _simple_space()

    searcher = CostAwareGPSearcher(
        space,
        base_searcher_factory=lambda s: SobolSearcher(s, seed=42),
        warmup=5,
        cooldown_duration=10,
        seed=42,
    )

    # First 5 observations: T=0
    for i in range(5):
        configs = searcher.propose(1)
        searcher.observe({"config": configs[0], "value": 0.5, "cost": 1.0})

        T = linear_cooling_schedule(searcher._n_observed, 5, 10)
        assert T == 0.0, f"Expected T=0 during warmup, got {T} at trial {i}"


def test_cost_aware_cooldown_phase():
    """During cooldown, temperature increases from 0 to 1."""
    from hponas.searchers_sobol import SobolSearcher

    space = _simple_space()

    searcher = CostAwareGPSearcher(
        space,
        base_searcher_factory=lambda s: SobolSearcher(s, seed=42),
        warmup=2,
        cooldown_duration=5,
        seed=42,
    )

    # Warmup (2 trials)
    for _ in range(2):
        configs = searcher.propose(1)
        searcher.observe({"config": configs[0], "value": 0.5, "cost": 1.0})

    # Cooldown (5 trials): T should increase
    temps = []
    for _ in range(5):
        configs = searcher.propose(1)
        searcher.observe({"config": configs[0], "value": 0.5, "cost": 1.0})
        T = linear_cooling_schedule(searcher._n_observed, 2, 5)
        temps.append(T)

    # Check monotonic increase
    for i in range(len(temps) - 1):
        assert temps[i] <= temps[i + 1], f"Temperature not monotonic: {temps}"

    # Last temp should be 1.0
    assert temps[-1] == 1.0


def test_cost_model_handles_wide_cost_ranges():
    """Log transform handles costs spanning orders of magnitude."""
    space = _simple_space()
    model = CostModelGP(space)

    # Wide range: 0.1 seconds to 1000 seconds
    model.observe({"x": 0.0}, cost=0.1)
    model.observe({"x": 1.0}, cost=1000.0)
    model.observe({"x": 0.5}, cost=10.0)

    # Predictions should be reasonable (no overflow/underflow)
    preds = model.predict([{"x": 0.25}, {"x": 0.75}])
    assert np.all(preds > 0)
    assert np.all(np.isfinite(preds))
