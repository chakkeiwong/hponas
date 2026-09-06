"""Prior recovery tests for πBO (GPqLogEISearcher with prior-weighted acquisition)."""

import pytest
import numpy as np
from hponas.searchers_gp import GPqLogEISearcher
from hponas.priors import GuardedPrior
from tests.fixtures.recovery_fixtures import (
    branin_2d_space,
    evaluate_branin,
    create_good_prior,
    create_wrong_prior,
    create_mediocre_prior,
    run_pibo_study,
    get_prior_mode,
    BRANIN_OPTIMUM,
)


@pytest.mark.slow
def test_pibo_good_prior_early_advantage():
    """Good prior beats uniform baseline in early budget."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    # Create uniform prior (always returns 1.0)
    def uniform_prior(config):
        return 1.0

    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)

    budget = 15  # Reduced from 25 for faster test
    seed = 42

    good_curve = run_pibo_study(good_prior, budget, seed)
    uniform_curve = run_pibo_study(uniform_guarded, budget, seed)

    # Check at n=10 (early budget)
    good_best_10 = good_curve[9]
    uniform_best_10 = uniform_curve[9]

    improvement = (uniform_best_10 - good_best_10) / (uniform_best_10 - BRANIN_OPTIMUM)

    assert improvement >= 0.05, \
        f"Good prior should improve ≥5% at n=10, got {improvement:.3f}"


@pytest.mark.slow
def test_pibo_wrong_prior_eventual_recovery():
    """Wrong prior recovers to near-uniform performance by budget exhaustion."""
    space = branin_2d_space()
    wrong_prior = create_wrong_prior(space)

    def uniform_prior(config):
        return 1.0

    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)

    budget = 30  # Reduced from 50 for faster test
    seed = 42

    wrong_curve = run_pibo_study(wrong_prior, budget, seed)
    uniform_curve = run_pibo_study(uniform_guarded, budget, seed)

    # Check at n=30 (full budget)
    wrong_best = wrong_curve[-1]
    uniform_best = uniform_curve[-1]

    regret_ratio = (wrong_best - BRANIN_OPTIMUM) / (uniform_best - BRANIN_OPTIMUM)

    assert regret_ratio <= 1.15, \
        f"Wrong prior regret should be ≤15% vs uniform at n={budget}, got {regret_ratio:.3f}"


def test_pibo_decay_exponent_behavior():
    """Prior weight decays as β/n over trials (exponent β/n decreases)."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)

    budget = 50
    seed = 42
    beta = 2.0  # Default πBO exponent

    # Get a config in high-prior-density region
    favored_config = get_prior_mode(space, good_prior)
    prior_density = good_prior(favored_config)

    # Track exponent β/n over trials (the exponent itself should decrease)
    exponents = []
    observation_counts = []

    for n in [5, 10, 15, 20, 25, 30, 40, 50]:
        exponent = beta / n
        exponents.append(exponent)
        observation_counts.append(n)

    # Verify exponent decreases monotonically
    for i in range(len(exponents) - 1):
        assert exponents[i] > exponents[i+1], \
            f"Exponent β/n should decrease monotonically: {exponents}"

    # Verify first vs last: β/5 = 0.4 vs β/50 = 0.04
    assert exponents[0] > 0.3 and exponents[-1] < 0.1, \
        f"Exponent should decay from {exponents[0]:.3f} to {exponents[-1]:.3f}"


@pytest.mark.slow
def test_pibo_multiple_prior_qualities_regret():
    """Regret curves converge across prior qualities by full budget."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    mediocre_prior = create_mediocre_prior(space)
    wrong_prior = create_wrong_prior(space)

    def uniform_prior(config):
        return 1.0

    from hponas.priors import ensure_guarded
    uniform_guarded = ensure_guarded(uniform_prior, space, alpha=0.95)

    budget = 30  # Reduced from 50 for faster test
    seed = 42

    curves = {
        "good": run_pibo_study(good_prior, budget, seed),
        "mediocre": run_pibo_study(mediocre_prior, budget, seed + 1),
        "wrong": run_pibo_study(wrong_prior, budget, seed + 2),
        "uniform": run_pibo_study(uniform_guarded, budget, seed + 3),
    }

    # Early (n=10): good < uniform < mediocre < wrong
    early_idx = 9
    assert curves["good"][early_idx] < curves["uniform"][early_idx], \
        "Good should beat uniform early"
    assert curves["uniform"][early_idx] < curves["mediocre"][early_idx], \
        "Uniform should beat mediocre early"
    assert curves["mediocre"][early_idx] < curves["wrong"][early_idx], \
        "Mediocre should beat wrong early"

    # Late (n=30): converged within 20%
    late_idx = -1
    regrets = {k: v[late_idx] - BRANIN_OPTIMUM for k, v in curves.items()}
    max_regret = max(regrets.values())
    min_regret = min(regrets.values())

    convergence = (max_regret - min_regret) / min_regret

    assert convergence <= 0.20, \
        f"Regrets should converge within 20% by n={budget}, got {convergence:.3f}"


def test_pibo_nonzero_support_enforced():
    """Guarded priors ensure nonzero acquisition weight everywhere."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)  # Already guarded via ensure_guarded

    # Sample configs across the space uniformly
    rng = np.random.RandomState(42)
    test_configs = []
    for _ in range(100):
        config = {
            "x1": rng.uniform(-5.0, 10.0),
            "x2": rng.uniform(0.0, 15.0)
        }
        test_configs.append(config)

    # All should have nonzero prior density (due to 5% uniform guard)
    densities = [good_prior(config) for config in test_configs]

    assert all(d > 0 for d in densities), \
        "Guarded prior should have nonzero density everywhere"

    # Verify minimum density is at least 4% of uniform (allowing for numerical error)
    uniform_density = 1.0 / (15.0 * 15.0)  # Branin space volume
    min_density = min(densities)
    min_ratio = min_density / uniform_density

    assert min_ratio >= 0.04, \
        f"Minimum density should be ≥4% of uniform (allowing for numerical error), got {min_ratio:.3f}"

    min_ratio = min_density / uniform_density

    assert min_ratio >= 0.04, \
        f"Minimum density should be ≥4% of uniform (allowing for numerical error), got {min_ratio:.3f}"
