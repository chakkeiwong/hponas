"""Prior recovery tests for PriorBand (portfolio sampler with rung-adaptive weights)."""

import pytest
import numpy as np
from hponas.searchers_priorband import PriorBandSampler
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.priors import GuardedPrior
from tests.fixtures.recovery_fixtures import (
    branin_2d_space,
    evaluate_branin,
    create_good_prior,
    create_wrong_prior,
    run_priorband_study,
    measure_prior_density_overlap,
    config_distance,
    BRANIN_OPTIMUM,
)


def test_priorband_early_rung_prior_biased():
    """Early rung samples favor high-prior-density regions compared to uniform."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    sampler_prior = PriorBandSampler(space, prior_fn=good_prior, seed=42)

    # Create baseline sampler without prior (uniform)
    def uniform_prior(config):
        return 1.0
    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)
    sampler_uniform = PriorBandSampler(space, prior_fn=uniform_guarded, seed=43)

    # Sample 100 configs at rung 0 (early) from each
    samples_prior = sampler_prior.propose(n=100, rung_idx=0)
    samples_uniform = sampler_uniform.propose(n=100, rung_idx=0)

    # Measure mean prior density for each
    mean_density_prior = np.mean([good_prior(c) for c in samples_prior])
    mean_density_uniform = np.mean([good_prior(c) for c in samples_uniform])

    assert mean_density_prior > mean_density_uniform, \
        f"Prior sampler should have higher mean density than uniform, got {mean_density_prior:.3f} vs {mean_density_uniform:.3f}"


def test_priorband_late_rung_incumbent_biased():
    """Late rung samples favor incumbent perturbations."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    sampler = PriorBandSampler(space, prior_fn=good_prior, seed=42)

    # Seed with 10 trials to establish incumbent
    for _ in range(10):
        configs = sampler.propose(n=1, rung_idx=0)
        config = configs[0]
        obj = evaluate_branin(config)
        trial = {"config": config, "value": -obj, "fidelity": 1.0, "cost": 1.0}
        sampler.observe(trial)

    incumbent = sampler.incumbent_config

    # Sample 100 configs at rung 2 (late)
    samples = sampler.propose(n=100, rung_idx=2)

    # Measure distance to incumbent
    distances = [config_distance(incumbent, s) for s in samples]
    epsilon = 0.3  # 30% of space diameter

    perturbation_rate = np.mean(np.array(distances) <= epsilon)

    assert perturbation_rate >= 0.25, \
        f"Late rung should have ≥25% samples near incumbent, got {perturbation_rate:.2f}"


@pytest.mark.slow
def test_priorband_wrong_prior_recovery():
    """PriorBand recovers from wrong prior through portfolio rebalancing."""
    space = branin_2d_space()
    wrong_prior = create_wrong_prior(space)

    def uniform_prior(config):
        return 1.0

    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)

    scheduler_config = ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0)
    budget = 81  # Full-run equivalents
    seed = 42

    wrong_curve = run_priorband_study(scheduler_config, wrong_prior, budget, seed)
    uniform_curve = run_priorband_study(scheduler_config, uniform_guarded, budget, seed + 1)

    # Take final value (or last available)
    wrong_best = wrong_curve[-1]
    uniform_best = uniform_curve[-1]

    regret_ratio = (wrong_best - BRANIN_OPTIMUM) / (uniform_best - BRANIN_OPTIMUM)

    assert regret_ratio <= 1.15, \
        f"PriorBand wrong prior should recover within 15% of uniform, got {regret_ratio:.3f}"


def test_priorband_portfolio_weight_progression():
    """Portfolio weights shift from prior-biased to uniform/incumbent across rungs."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    sampler = PriorBandSampler(space, prior_fn=good_prior, seed=42)

    # Run to populate incumbent
    for _ in range(30):
        configs = sampler.propose(n=1, rung_idx=0)
        config = configs[0]
        obj = evaluate_branin(config)
        trial = {"config": config, "value": -obj, "fidelity": 1.0, "cost": 1.0}
        sampler.observe(trial)

    # Sample from each rung and check distribution
    samples_rung_0 = sampler.propose(n=100, rung_idx=0)
    samples_rung_1 = sampler.propose(n=100, rung_idx=1)
    samples_rung_2 = sampler.propose(n=100, rung_idx=2)

    # Measure prior overlap (higher at early rungs)
    overlap_0 = measure_prior_density_overlap(samples_rung_0, good_prior, percentile=90)
    overlap_1 = measure_prior_density_overlap(samples_rung_1, good_prior, percentile=90)
    overlap_2 = measure_prior_density_overlap(samples_rung_2, good_prior, percentile=90)

    # Prior influence should decrease across rungs
    assert overlap_0 >= overlap_1 or overlap_0 >= overlap_2, \
        f"Prior overlap should decrease or stay flat across rungs: {overlap_0:.2f}, {overlap_1:.2f}, {overlap_2:.2f}"


def test_priorband_uniform_component_always_present():
    """PriorBand portfolio always includes uniform component for exploration."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    sampler = PriorBandSampler(space, prior_fn=good_prior, seed=42)

    # Even at early rung, should have some uniform samples (not 100% prior)
    samples = sampler.propose(n=200, rung_idx=0)

    overlap = measure_prior_density_overlap(samples, good_prior, percentile=90)

    # Should not be all high-prior-density (uniform must contribute)
    assert overlap < 0.95, \
        f"Early rung should not be 100% prior-biased, got {overlap:.2f} high-density overlap"


@pytest.mark.slow
def test_priorband_convergence_with_good_prior():
    """PriorBand with good prior converges faster than uniform."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    def uniform_prior(config):
        return 1.0

    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)

    scheduler_config = ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0)
    budget = 27  # One full rung
    seed = 42

    good_curve = run_priorband_study(scheduler_config, good_prior, budget, seed)
    uniform_curve = run_priorband_study(scheduler_config, uniform_guarded, budget, seed + 1)

    # Good prior should find better solution at budget exhaustion
    assert good_curve[-1] < uniform_curve[-1], \
        f"Good prior should beat uniform at budget {budget}, got {good_curve[-1]:.3f} vs {uniform_curve[-1]:.3f}"


def test_priorband_nonzero_support_enforced():
    """Guarded priors ensure PriorBand can sample entire space."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)  # Already guarded

    sampler = PriorBandSampler(space, prior_fn=good_prior, seed=42)

    # Sample many configs, even from prior-biased rung
    samples = sampler.propose(n=500, rung_idx=0)

    # Should cover space (not just high-prior region)
    x1_vals = [s["x1"] for s in samples]
    x2_vals = [s["x2"] for s in samples]

    x1_range = max(x1_vals) - min(x1_vals)
    x2_range = max(x2_vals) - min(x2_vals)

    # Should explore at least 50% of each dimension
    assert x1_range >= 7.5, f"x1 range should be ≥50% of bounds, got {x1_range:.2f}"
    assert x2_range >= 7.5, f"x2 range should be ≥50% of bounds, got {x2_range:.2f}"
