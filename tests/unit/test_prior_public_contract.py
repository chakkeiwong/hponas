"""Prior normalization checked against independently generated base samples."""

import numpy as np
import pytest

from hponas.priors import GuardedPrior, ensure_guarded, estimate_prior_mean, make_nonzero_guarded_prior
from hponas.space import Knob, SearchSpace


def space():
    return SearchSpace([Knob("x", "continuous", (0.0, 1.0))])


def density(config):
    return 0.2 + 0.7 * config["x"]


def expected_mean(samples, seed):
    values = np.random.default_rng(seed).uniform(0.0, 1.0, size=samples)
    return float(np.array([0.2 + 0.7 * x for x in values], dtype=np.float64).mean())


def test_prior_default_mean_uses_declared_base_measure_sample_count_and_seed():
    assert estimate_prior_mean(density, space()) == expected_mean(1024, 0)


@pytest.mark.parametrize("factory", [GuardedPrior, make_nonzero_guarded_prior])
@pytest.mark.parametrize("options,samples,seed,alpha", [({}, 1024, 0, .95), ({"n_samples": 7, "seed": 17, "alpha": .3}, 7, 17, .3)])
def test_public_prior_normalization_and_attributes(factory, options, samples, seed, alpha):
    domain = space()
    guarded = factory(density, domain, **options)
    mean = expected_mean(samples, seed)
    assert guarded.user_prior is density and guarded.space is domain
    assert guarded.alpha == alpha and guarded.scale == mean
    assert guarded.floor == max(1.0 - alpha, 1e-12)
    # Four floating arithmetic operations: allow their rounding, not a change
    # to the exact sample count, random seed, normalization or mixture.
    assert guarded({"x": .4}) == pytest.approx(alpha * density({"x": .4}) / mean + (1.0 - alpha), rel=1e-14, abs=1e-14)


@pytest.mark.parametrize("factory", [GuardedPrior, make_nonzero_guarded_prior])
def test_unnormalized_prior_preserves_original_density_scale(factory):
    guarded = factory(density, space(), alpha=.3, normalize=False)
    assert guarded.scale == 1.0
    assert guarded({"x": .4}) == .3 * density({"x": .4}) + .7


def test_zero_prior_has_unit_fallback_and_no_excluded_region():
    assert estimate_prior_mean(lambda _: 0.0, space(), n_samples=7) == 1.0
    guarded = GuardedPrior(lambda _: 0.0, space(), alpha=.8, n_samples=7)
    assert guarded.scale == 1.0
    assert guarded({"x": .3}) == pytest.approx(.2)


def test_normalized_overflow_saturates_to_largest_finite_density():
    guarded = GuardedPrior(lambda c: 1e300 if c["x"] == 1 else 1e-300,
                           space(), alpha=.7, n_samples=7, seed=17)
    assert guarded({"x": 1.0}) == float(np.finfo(np.float64).max)


def test_ensure_guarded_honors_explicit_mixture_and_is_idempotent():
    domain = space()
    guarded = ensure_guarded(density, domain, alpha=.3)
    assert guarded.alpha == .3
    assert guarded({"x": .4}) == .3 * density({"x": .4}) / expected_mean(1024, 0) + .7
    assert ensure_guarded(guarded, domain, alpha=.8) is guarded
    assert ensure_guarded(None, domain) is None
