"""Cost efficiency integration tests.

Tests that EI-per-cost acquisition achieves better cost-efficiency than cost-agnostic baselines.
"""

import numpy as np
import pytest
from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_cost import CostAwareGPSearcher
from hponas.searchers_gp import GPqLogEISearcher


def _create_cost_aware_searcher(space, warmup=5, cooldown_duration=20, seed=42):
    """Helper to create CostAwareGPSearcher with factory."""
    return CostAwareGPSearcher(
        space,
        base_searcher_factory=lambda s: GPqLogEISearcher(s, seed=seed),
        warmup=warmup,
        cooldown_duration=cooldown_duration,
        seed=seed,
    )


def _quality_cost_tradeoff_task():
    """
    Synthetic task with a genuine quality-cost tradeoff.

    Quality: flat weak trend + heavy observation noise (signal drowned)
    Cost: 1s → 100s (100× range)

    With a flat/noisy quality surface the qLogEI spread stays small (no
    high-certainty sharp peak), letting the cost term compete. The 100× cost
    range delivers a log-cost spread of ~4.6 nats, enough to shift the argmax
    when the EI spread is modest. This is the working condition verified by
    test_severe_cost_gradient (unstructured quality → EI spread small).

    Efficiency: total quality / total cost. Cost-awareness should secure
    substantially lower cumulative cost without sacrificing quality sum.
    """
    rng = np.random.RandomState(7)
    noise = rng.normal(0, 0.15, 50)

    def quality(x):
        # Deterministic in x: both searchers must see the identical surface,
        # otherwise a same-seed differential compares two different problems.
        return 0.5 + 0.1 * x + noise[min(int(x * 49), 49)]

    def cost(x):
        return 1.0 + 99.0 * x

    return quality, cost


@pytest.mark.slow
def test_cost_quality_tradeoff():
    """Cost-aware searcher achieves better quality-per-cost ratio."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    quality_fn, cost_fn = _quality_cost_tradeoff_task()

    # Cost-aware searcher with full cost-awareness (T=1 immediately)
    cost_aware = _create_cost_aware_searcher(
        space,
        warmup=5,
        cooldown_duration=1,  # Fast transition to T=1
        seed=42,
    )

    # Baseline: standard GP without cost-awareness. Same seed as the cost-aware
    # searcher's base — the only difference between the two arms must be the
    # cost penalty, not the random stream. With different seeds this test passes
    # or fails on sampling luck.
    baseline = GPqLogEISearcher(space, seed=42)

    # Run both for 20 trials
    budget = 20

    def run_study(searcher):
        total_cost = 0.0
        total_quality = 0.0

        for _ in range(budget):
            configs = searcher.propose(n=1)
            config = configs[0]

            q = quality_fn(config["x"])
            c = cost_fn(config["x"])

            total_cost += c
            total_quality += q

            trial = {"config": config, "value": q, "cost": c}
            searcher.observe(trial)

        return total_quality / total_cost  # Quality per unit cost

    cost_aware_efficiency = run_study(cost_aware)
    baseline_efficiency = run_study(baseline)

    # Cost-aware should achieve better efficiency (more quality per cost).
    # Measured separation on this fixture is ~+1.2 (total cost 850 vs 1860);
    # assert a fraction of it so the test tracks the mechanism, not the seed.
    improvement = (cost_aware_efficiency - baseline_efficiency) / baseline_efficiency

    assert improvement > 0.30, \
        f"Cost-aware should improve efficiency by >30%, got {improvement:.3f} " \
        f"({cost_aware_efficiency:.4f} vs {baseline_efficiency:.4f})"


@pytest.mark.slow
def test_temperature_progression_effect():
    """Warmup proposals track the cost-agnostic base searcher; after cooldown
    (T=1) the cost penalty steers proposals into the cheap region.

    Framed as a same-seed differential against GPqLogEISearcher rather than an
    absolute threshold on x. An absolute "late proposals are cheap" assertion is
    only meaningful relative to what a cost-agnostic searcher would have done on
    the identical surface -- on a task whose optimum happens to be cheap it
    passes without the cost model contributing anything.
    """
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    quality_fn, cost_fn = _quality_cost_tradeoff_task()

    warmup, cooldown_duration = 5, 15

    def run(searcher, n=25):
        xs = []
        for _ in range(n):
            config = searcher.propose(n=1)[0]
            x = config["x"]
            xs.append(x)
            searcher.observe(
                {"config": config, "value": quality_fn(x), "cost": cost_fn(x)}
            )
        return np.array(xs)

    cost_aware_x = run(
        _create_cost_aware_searcher(
            space, warmup=warmup, cooldown_duration=cooldown_duration, seed=42
        )
    )
    baseline_x = run(GPqLogEISearcher(space, seed=42))

    # Early trials (warmup, T=0): CostAwareGPSearcher delegates verbatim, so the
    # two arms must coincide. They are not bit-identical because optimize_acqf
    # draws its multi-start points from the global torch RNG, which the two runs
    # advance differently -- measured max deviation ~1e-3, so 0.05 is generous.
    n_delegated = warmup + 1  # T becomes non-zero only once n_observed > warmup
    assert np.allclose(
        cost_aware_x[:n_delegated], baseline_x[:n_delegated], atol=0.05
    ), (
        "During warmup (T=0) proposals should match the base searcher, got "
        f"max deviation {np.abs(cost_aware_x[:n_delegated] - baseline_x[:n_delegated]).max():.4f}"
    )

    # Early trials should still cover ground rather than collapsing immediately.
    early_range = cost_aware_x[:5].max() - cost_aware_x[:5].min()
    assert early_range > 0.3, \
        f"Early trials should explore broadly, got range {early_range:.3f}"

    # Late trials (T=1): cost-aware concentrates in the cheap region while the
    # cost-agnostic baseline chases the (expensive) quality optimum.
    # Measured: mean cost 1.0 vs 98.2 out of a 1-100 range.
    cost_aware_late = float(np.mean([cost_fn(x) for x in cost_aware_x[20:]]))
    baseline_late = float(np.mean([cost_fn(x) for x in baseline_x[20:]]))

    assert cost_aware_late < 0.5 * baseline_late, (
        "Late cost-aware trials should be substantially cheaper than the "
        f"cost-agnostic baseline, got {cost_aware_late:.1f} vs {baseline_late:.1f}"
    )


def test_no_free_lunch_check():
    """Cost-awareness doesn't hurt when cost is uninformative."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])

    # Quality: structured (peaked at x=0.5)
    def quality(x):
        return 1.0 - 4.0 * (x - 0.5)**2

    # Cost: random, no correlation with quality
    rng = np.random.RandomState(99)
    cost_map = {i: rng.uniform(1.0, 10.0) for i in range(50)}

    def cost(x):
        # Discretize x to lookup random cost
        idx = int(x * 49)
        return cost_map.get(idx, 5.0)

    # Cost-aware searcher
    cost_aware = _create_cost_aware_searcher(
        space,
        warmup=3,
        cooldown_duration=5,
        seed=42,
    )

    # Baseline
    baseline = GPqLogEISearcher(space, seed=42)

    def run_study(searcher):
        best_quality = -float('inf')

        for _ in range(15):
            configs = searcher.propose(n=1)
            config = configs[0]

            q = quality(config["x"])
            c = cost(config["x"])

            best_quality = max(best_quality, q)

            trial = {"config": config, "value": q, "cost": c}
            searcher.observe(trial)

        return best_quality

    cost_aware_best = run_study(cost_aware)
    baseline_best = run_study(baseline)

    # Final quality should be similar (within 10%)
    ratio = cost_aware_best / baseline_best

    assert 0.9 <= ratio <= 1.1, \
        f"Cost-awareness shouldn't hurt when cost uninformative, got ratio {ratio:.3f}"


def test_severe_cost_gradient():
    """Cost-aware searcher avoids high-cost region with severe gradient."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])

    # Quality: random GP surface (no structure)
    rng = np.random.RandomState(77)
    quality_samples = rng.randn(20)

    def quality(x):
        # Interpolate from random samples
        idx = int(x * 19)
        return quality_samples[min(idx, 19)]

    # Cost: cliff at x=0.5
    def cost(x):
        return 1.0 if x < 0.5 else 100.0

    searcher = _create_cost_aware_searcher(
        space,
        warmup=3,
        cooldown_duration=5,
        seed=42,
    )

    proposals_after_warmup = []

    for i in range(25):
        configs = searcher.propose(n=1)
        config = configs[0]
        x = config["x"]

        if i >= 20:  # After full warmup + cooldown
            proposals_after_warmup.append(x)

        q = quality(x)
        c = cost(x)
        trial = {"config": config, "value": q, "cost": c}
        searcher.observe(trial)

    # Should concentrate in low-cost region (x < 0.5)
    low_cost_rate = np.mean(np.array(proposals_after_warmup) < 0.5)

    assert low_cost_rate >= 0.6, \
        f"Should favor low-cost region (x<0.5) by trial 20, got {low_cost_rate:.2f} rate"
