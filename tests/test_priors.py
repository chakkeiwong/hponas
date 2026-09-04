"""
Tests for hponas.priors: nonzero-guard construction.

Survey reference: Ch 8 roadmap-10, ch08-01, ch08-03.
Validation: V11 (prior effectiveness).
"""

import math

import numpy as np
import pytest

from hponas.priors import (
    GuardedPrior,
    ensure_guarded,
    estimate_prior_mean,
    is_guarded,
    make_nonzero_guarded_prior,
)
from hponas.space import Knob, SearchSpace


def test_hard_zero_prior():
    """A prior that always returns 0 is guarded to (1 - alpha) everywhere."""
    space = SearchSpace(
        knobs=[
            Knob(name="x", kind="continuous", bounds=(0.0, 1.0)),
            Knob(name="y", kind="continuous", bounds=(0.0, 1.0)),
        ]
    )

    def zero_prior(config):
        return 0.0

    guarded = make_nonzero_guarded_prior(zero_prior, space, alpha=0.95)
    assert guarded({"x": 0.5, "y": 0.5}) == pytest.approx(0.05, abs=1e-9)


def test_partially_zero_prior():
    """A prior that is zero in some regions is nonzero everywhere after guarding."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def partial_prior(config):
        return 1.0 if config["x"] < 0.5 else 0.0

    guarded = make_nonzero_guarded_prior(partial_prior, space, alpha=0.95)
    assert guarded({"x": 0.2}) > 0.05  # Prior is 1.0 here
    assert guarded({"x": 0.8}) == pytest.approx(0.05, abs=1e-9)  # Prior is 0.0


def test_log_scaled_knob_base_measure():
    """estimate_prior_mean samples log-uniformly for log-transformed knobs."""
    space = SearchSpace(
        knobs=[Knob(name="lr", kind="continuous", bounds=(1e-4, 1e-1), transform="log")]
    )

    def constant_prior(config):
        return 1.0

    mean = estimate_prior_mean(constant_prior, space, n_samples=1024, seed=42)
    assert mean == pytest.approx(1.0, abs=0.1)


def test_unit_mean_rescaling():
    """Unit-mean rescaling normalizes a prior to have mean ~1.0."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def scaled_prior(config):
        return 10.0  # Constant 10.0 everywhere

    guarded = make_nonzero_guarded_prior(scaled_prior, space, alpha=0.95, normalize=True)
    # scale should be ~10.0, so user_val = 10.0 / 10.0 = 1.0
    # mixed = 0.95 * 1.0 + 0.05 = 1.0
    assert guarded({"x": 0.5}) == pytest.approx(1.0, abs=0.05)


def test_alpha_validation():
    """alpha outside (0, 1) raises ValueError."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def dummy_prior(config):
        return 1.0

    with pytest.raises(ValueError, match="alpha must be in"):
        make_nonzero_guarded_prior(dummy_prior, space, alpha=0.0)

    with pytest.raises(ValueError, match="alpha must be in"):
        make_nonzero_guarded_prior(dummy_prior, space, alpha=1.0)

    with pytest.raises(ValueError, match="alpha must be in"):
        make_nonzero_guarded_prior(dummy_prior, space, alpha=-0.1)


def test_pathological_prior_raises():
    """Prior that raises is treated as 0.0."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def exploding_prior(config):
        raise RuntimeError("boom")

    guarded = make_nonzero_guarded_prior(exploding_prior, space, alpha=0.95)
    assert guarded({"x": 0.5}) == pytest.approx(0.05, abs=1e-9)


def test_pathological_prior_nan():
    """Prior that returns NaN is treated as 0.0."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def nan_prior(config):
        return float("nan")

    guarded = make_nonzero_guarded_prior(nan_prior, space, alpha=0.95)
    assert guarded({"x": 0.5}) == pytest.approx(0.05, abs=1e-9)


def test_pathological_prior_inf():
    """Prior that returns inf is treated as 0.0 (no information)."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def inf_prior(config):
        return float("inf")

    # _safe_eval rejects non-finite values before mixing, so inf collapses to
    # the uniform escape mass rather than dominating the acquisition.
    guarded = make_nonzero_guarded_prior(inf_prior, space, alpha=0.95, normalize=False)
    assert guarded({"x": 0.5}) == pytest.approx(0.05, abs=1e-9)


def test_pathological_prior_negative():
    """Prior that returns negative is treated as 0.0."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def negative_prior(config):
        return -5.0

    guarded = make_nonzero_guarded_prior(negative_prior, space, alpha=0.95)
    assert guarded({"x": 0.5}) == pytest.approx(0.05, abs=1e-9)


def test_ensure_guarded_idempotent():
    """ensure_guarded on a GuardedPrior returns the same object."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def dummy_prior(config):
        return 1.0

    g1 = ensure_guarded(dummy_prior, space, alpha=0.95)
    g2 = ensure_guarded(g1, space, alpha=0.95)
    assert g1 is g2


def test_ensure_guarded_none():
    """ensure_guarded(None, space) returns None."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )
    assert ensure_guarded(None, space) is None


def test_is_guarded():
    """is_guarded identifies GuardedPrior instances."""
    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def dummy_prior(config):
        return 1.0

    assert not is_guarded(dummy_prior)
    guarded = make_nonzero_guarded_prior(dummy_prior, space)
    assert is_guarded(guarded)


def test_priorband_with_hard_zero_prior():
    """PriorBandSampler with a hard-zero prior still explores via the guard."""
    from hponas.searchers_priorband import PriorBandSampler

    space = SearchSpace(
        knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))]
    )

    def zero_prior(config):
        return 0.0

    sampler = PriorBandSampler(
        space, prior_fn=zero_prior, seed=42, uniform_weight=0.0, prior_weight=1.0, incumbent_weight=0.0
    )
    configs = sampler.propose(n=1, rung_idx=0)
    # The guard ensures nonzero density, so rejection sampling succeeds
    assert len(configs) == 1
    assert "x" in configs[0]
    assert 0.0 <= configs[0]["x"] <= 1.0
