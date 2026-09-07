# Prior Recovery Tests Spec

**Date:** 2026-09-07  
**Effort:** ~3 engineer-days  
**Context:** BUILD_PROGRAM_v2.md Tier 1 Tests (~7d), BUILD_PROGRAM_REVIEW_VERDICT.md V11 requirements

---

## Purpose

Test that πBO and PriorBand recover from wrong priors through their decay mechanisms:
- πBO: Prior influence decays as β/n where n = number of observations
- PriorBand: Rung-adaptive portfolio shifts from prior-biased to incumbent-biased

**Key safety property:** A wrong prior must not cause permanent performance degradation. Early loss is acceptable; unbounded regret is not.

---

## Requirements (from BUILD_PROGRAM_REVIEW_VERDICT.md line 208)

> Test the actual decaying multiplier and rung portfolio over several prior qualities, require nonzero support, predefine early gain and worst-case recovery margins, and report regret over budget.

### Functional

1. **Multiple prior qualities**
   - Good prior: centered near true optimum
   - Mediocre prior: off-center but reasonable support
   - Wrong prior: adversarially placed far from optimum
   - Uniform prior: baseline (no guidance)

2. **Recovery metrics**
   - Regret over budget: cumulative suboptimality
   - Recovery budget: trials needed to match uniform baseline
   - Final performance: best objective at budget exhaustion

3. **Decay verification**
   - πBO: Verify β/n exponent behavior (prior weight → 0 as n → ∞)
   - PriorBand: Verify rung-adaptive portfolio (early: prior, late: incumbent)

4. **Safety bounds**
   - Wrong-prior recovery margin: must reach within X% of uniform baseline by budget B
   - Early gain margin: good prior must beat uniform by Y% within budget B/4

### Non-functional

5. **Nonzero support already enforced**
   - `ensure_guarded()` guarantees 5% uniform escape mass
   - Tests verify this exists (test_ensure_guarded_* in test_priors.py)

6. **Deterministic**
   - Fixed seeds for reproducibility
   - Same task/budget across all prior qualities

---

## Test Strategy

### Test Suite 1: πBO Prior Recovery (~1.5d)

**File:** `tests/test_prior_recovery_pibo.py`

#### T1.1: Good prior early advantage
- Task: branin_2d (known optimum)
- Priors: good_prior (centered at optimum), uniform
- Budget: 25 trials
- Metric: Best-so-far at n=10 (early budget)
- Pass rule: good_prior improves by ≥5% over uniform

#### T1.2: Wrong prior eventual recovery
- Task: branin_2d
- Priors: wrong_prior (antipodal from optimum), uniform
- Budget: 50 trials
- Metric: Best-so-far at n=50
- Pass rule: wrong_prior regret ≤ 10% vs uniform at budget exhaustion

#### T1.3: Decay exponent verification
- Task: branin_2d
- Prior: good_prior
- Budget: 50 trials
- Metric: Acquisition weight on prior-favored region over trials
- Pass rule: Prior weight monotonically decreases, approaches 0 as n → 50

#### T1.4: Multiple prior qualities regret curves
- Task: branin_2d
- Priors: good, mediocre, wrong, uniform
- Budget: 50 trials each
- Metric: Cumulative regret curves
- Pass rule: 
  - good < uniform < mediocre < wrong at n=10
  - good < uniform ≈ mediocre ≈ wrong at n=50

### Test Suite 2: PriorBand Portfolio Recovery (~1.5d)

**File:** `tests/test_prior_recovery_priorband.py`

#### T2.1: Early rung prior-biased sampling
- Scheduler: ASHA with r_min=1, r_max=27, eta=3 (3 rungs)
- Prior: good_prior
- Rung: 0 (r=1, early)
- Metric: Sample 100 configs, measure prior density
- Pass rule: ≥40% of samples in top-10% prior density region

#### T2.2: Late rung incumbent-biased sampling
- Scheduler: ASHA with r_min=1, r_max=27, eta=3
- Prior: good_prior
- Rung: 2 (r=27, late)
- Setup: Seed with 10 trials, establish incumbent
- Metric: Sample 100 configs, measure incumbent perturbation rate
- Pass rule: ≥40% of samples within ε-ball of incumbent

#### T2.3: Wrong prior recovery through portfolio
- Task: branin_2d with ASHA
- Prior: wrong_prior
- Budget: 81 full-run equivalents
- Metric: Best objective at budget exhaustion
- Pass rule: PriorBand wrong_prior within 15% of PriorBand uniform

#### T2.4: Portfolio weight progression
- Scheduler: ASHA with 3 rungs
- Prior: good_prior
- Metric: Log portfolio weights at each rung
- Pass rule: uniform weight increases, prior weight decreases monotonically across rungs

---

## Implementation Plan

### 1. Test utilities (~0.3d)

Create `tests/fixtures/recovery_fixtures.py`:

```python
def branin_2d_space():
    """Standard 2D Branin space for recovery tests."""
    return ConfigurationSpace(...)

def create_good_prior(space):
    """Prior centered at known Branin optimum."""
    return Prior(...)

def create_wrong_prior(space):
    """Prior antipodal from optimum."""
    return Prior(...)

def create_mediocre_prior(space):
    """Prior off-center but reasonable."""
    return Prior(...)

def run_pibo_study(prior, budget, seed):
    """Run πBO with given prior to budget."""
    searcher = GPqLogEISearcher(space, prior=prior, seed=seed)
    # ... run loop
    return best_so_far_curve

def run_priorband_study(scheduler, prior, budget, seed):
    """Run PriorBand with ASHA to budget."""
    searcher = PriorBandSampler(space, prior=prior, seed=seed)
    # ... run loop with scheduler
    return best_so_far_curve

def compute_regret(curve, optimal_value):
    """Compute cumulative regret from best-so-far curve."""
    return np.cumsum(curve - optimal_value)

def measure_prior_density_overlap(samples, prior, percentile=0.9):
    """Measure fraction of samples in high-prior-density region."""
    densities = [prior.density(config) for config in samples]
    threshold = np.percentile(densities, percentile)
    return np.mean(densities >= threshold)
```

### 2. πBO recovery tests (~1.2d)

**File:** `tests/test_prior_recovery_pibo.py`

```python
import pytest
import numpy as np
from hponas.searchers_gp import GPqLogEISearcher
from hponas.priors import Prior, ensure_guarded
from tests.fixtures.recovery_fixtures import (
    branin_2d_space,
    create_good_prior,
    create_wrong_prior,
    create_mediocre_prior,
    run_pibo_study,
    compute_regret,
)

BRANIN_OPTIMUM = 0.397887  # Known global minimum

def test_pibo_good_prior_early_advantage():
    """Good prior beats uniform baseline in early budget."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    uniform_prior = Prior.uniform(space)
    
    budget = 25
    seed = 42
    
    good_curve = run_pibo_study(good_prior, budget, seed)
    uniform_curve = run_pibo_study(uniform_prior, budget, seed)
    
    # Check at n=10 (early budget)
    good_best_10 = good_curve[9]
    uniform_best_10 = uniform_curve[9]
    
    improvement = (uniform_best_10 - good_best_10) / (uniform_best_10 - BRANIN_OPTIMUM)
    
    assert improvement >= 0.05, f"Good prior should improve ≥5% at n=10, got {improvement:.3f}"

def test_pibo_wrong_prior_eventual_recovery():
    """Wrong prior recovers to near-uniform performance by budget exhaustion."""
    space = branin_2d_space()
    wrong_prior = create_wrong_prior(space)
    uniform_prior = Prior.uniform(space)
    
    budget = 50
    seed = 42
    
    wrong_curve = run_pibo_study(wrong_prior, budget, seed)
    uniform_curve = run_pibo_study(uniform_prior, budget, seed)
    
    # Check at n=50 (full budget)
    wrong_best_50 = wrong_curve[49]
    uniform_best_50 = uniform_curve[49]
    
    regret_ratio = (wrong_best_50 - BRANIN_OPTIMUM) / (uniform_best_50 - BRANIN_OPTIMUM)
    
    assert regret_ratio <= 1.10, f"Wrong prior regret should be ≤10% vs uniform, got {regret_ratio:.3f}"

def test_pibo_decay_exponent_behavior():
    """Prior weight decays as β/n over trials."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    
    budget = 50
    seed = 42
    beta = 2.0  # Default πBO exponent
    
    # Track acquisition weights on prior-favored region
    searcher = GPqLogEISearcher(space, prior=good_prior, beta=beta, seed=seed)
    
    prior_weights = []
    for n in range(5, budget + 1, 5):
        # Simulate n observations
        for _ in range(n - len(searcher._observed_configs)):
            config = searcher.propose()
            obj = evaluate_branin(config)
            searcher.observe(config, obj)
        
        # Measure prior weight at prior-favored point
        favored_config = get_prior_mode(space, good_prior)
        weight = searcher._compute_prior_weight(favored_config, n)
        prior_weights.append(weight)
    
    # Verify monotonic decrease
    assert all(prior_weights[i] >= prior_weights[i+1] for i in range(len(prior_weights)-1)), \
        "Prior weights should decrease monotonically"
    
    # Verify approaches 0
    assert prior_weights[-1] < 0.1, f"Prior weight at n={budget} should be <0.1, got {prior_weights[-1]:.3f}"

def test_pibo_multiple_prior_qualities_regret():
    """Regret curves converge across prior qualities by full budget."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    mediocre_prior = create_mediocre_prior(space)
    wrong_prior = create_wrong_prior(space)
    uniform_prior = Prior.uniform(space)
    
    budget = 50
    seed = 42
    
    curves = {
        "good": run_pibo_study(good_prior, budget, seed),
        "mediocre": run_pibo_study(mediocre_prior, budget, seed + 1),
        "wrong": run_pibo_study(wrong_prior, budget, seed + 2),
        "uniform": run_pibo_study(uniform_prior, budget, seed + 3),
    }
    
    # Early (n=10): good < uniform < mediocre < wrong
    early_idx = 9
    assert curves["good"][early_idx] < curves["uniform"][early_idx], "Good should beat uniform early"
    assert curves["uniform"][early_idx] < curves["mediocre"][early_idx], "Uniform should beat mediocre early"
    assert curves["mediocre"][early_idx] < curves["wrong"][early_idx], "Mediocre should beat wrong early"
    
    # Late (n=50): converged within 5%
    late_idx = 49
    regrets = {k: v[late_idx] - BRANIN_OPTIMUM for k, v in curves.items()}
    max_regret = max(regrets.values())
    min_regret = min(regrets.values())
    
    convergence = (max_regret - min_regret) / min_regret
    assert convergence <= 0.15, f"Regrets should converge within 15% by n=50, got {convergence:.3f}"
```

### 3. PriorBand recovery tests (~1.2d)

**File:** `tests/test_prior_recovery_priorband.py`

```python
import pytest
import numpy as np
from hponas.searchers_priorband import PriorBandSampler
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.priors import Prior
from tests.fixtures.recovery_fixtures import (
    branin_2d_space,
    create_good_prior,
    create_wrong_prior,
    run_priorband_study,
    measure_prior_density_overlap,
)

def test_priorband_early_rung_prior_biased():
    """Early rung samples favor high-prior-density regions."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    
    sampler = PriorBandSampler(space, prior=good_prior, seed=42)
    scheduler = ASHAScheduler(ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0))
    
    # Sample 100 configs at rung 0 (early)
    samples = [sampler.propose(rung_idx=0) for _ in range(100)]
    
    overlap = measure_prior_density_overlap(samples, good_prior, percentile=90)
    
    assert overlap >= 0.40, f"Early rung should have ≥40% samples in top-10% prior density, got {overlap:.2f}"

def test_priorband_late_rung_incumbent_biased():
    """Late rung samples favor incumbent perturbations."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    
    sampler = PriorBandSampler(space, prior=good_prior, seed=42)
    scheduler = ASHAScheduler(ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0))
    
    # Seed with 10 trials to establish incumbent
    for _ in range(10):
        config = sampler.propose(rung_idx=0)
        obj = evaluate_branin(config)
        sampler.observe(config, obj, rung_idx=0)
    
    incumbent = sampler._incumbent
    
    # Sample 100 configs at rung 2 (late)
    samples = [sampler.propose(rung_idx=2) for _ in range(100)]
    
    # Measure distance to incumbent
    distances = [config_distance(incumbent, s) for s in samples]
    epsilon = 0.2  # 20% of space diameter
    
    perturbation_rate = np.mean(np.array(distances) <= epsilon)
    
    assert perturbation_rate >= 0.40, \
        f"Late rung should have ≥40% samples near incumbent, got {perturbation_rate:.2f}"

def test_priorband_wrong_prior_recovery():
    """PriorBand recovers from wrong prior through portfolio rebalancing."""
    space = branin_2d_space()
    wrong_prior = create_wrong_prior(space)
    uniform_prior = Prior.uniform(space)
    
    scheduler_config = ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0)
    budget = 81  # Full-run equivalents
    seed = 42
    
    wrong_curve = run_priorband_study(scheduler_config, wrong_prior, budget, seed)
    uniform_curve = run_priorband_study(scheduler_config, uniform_prior, budget, seed + 1)
    
    wrong_best = wrong_curve[-1]
    uniform_best = uniform_curve[-1]
    
    regret_ratio = (wrong_best - BRANIN_OPTIMUM) / (uniform_best - BRANIN_OPTIMUM)
    
    assert regret_ratio <= 1.15, \
        f"PriorBand wrong prior should recover within 15% of uniform, got {regret_ratio:.3f}"

def test_priorband_portfolio_weight_progression():
    """Portfolio weights shift from prior-biased to incumbent-biased across rungs."""
    space = branin_2d_space()
    good_prior = create_good_prior(space)
    
    sampler = PriorBandSampler(space, prior=good_prior, seed=42)
    scheduler = ASHAScheduler(ASHAConfig(r_min=1.0, r_max=27.0, eta=3.0))
    
    # Run to populate all rungs
    for _ in range(30):
        config = sampler.propose(rung_idx=0)
        obj = evaluate_branin(config)
        sampler.observe(config, obj, rung_idx=0)
    
    # Extract portfolio weights at each rung
    weights_rung_0 = sampler._get_portfolio_weights(rung_idx=0)
    weights_rung_1 = sampler._get_portfolio_weights(rung_idx=1)
    weights_rung_2 = sampler._get_portfolio_weights(rung_idx=2)
    
    # Verify uniform weight increases
    assert weights_rung_0["uniform"] < weights_rung_1["uniform"], \
        "Uniform weight should increase across rungs"
    assert weights_rung_1["uniform"] < weights_rung_2["uniform"], \
        "Uniform weight should increase across rungs"
    
    # Verify prior weight decreases
    assert weights_rung_0["prior"] > weights_rung_1["prior"], \
        "Prior weight should decrease across rungs"
    assert weights_rung_1["prior"] > weights_rung_2["prior"], \
        "Prior weight should decrease across rungs"
```

### 4. Integration and documentation (~0.3d)

- Add recovery fixtures to `tests/fixtures/`
- Implement helper functions (branin evaluation, config distance, etc.)
- Update test discovery: ensure pytest finds new test files
- Run full test suite to verify no regressions
- Document pass rules and margins in docstrings

---

## Effort Breakdown

| Task | Effort |
|------|--------|
| Test utilities and fixtures | 0.3d |
| πBO recovery tests (4 tests) | 1.2d |
| PriorBand recovery tests (4 tests) | 1.2d |
| Integration and documentation | 0.3d |
| **Total** | **3.0d** |

---

## Success Criteria

1. All 8+ recovery tests passing
2. Good priors demonstrate early advantage (≥5% improvement at n=10)
3. Wrong priors recover to within 10-15% of uniform by budget exhaustion
4. πBO decay exponent verified (prior weight → 0)
5. PriorBand portfolio progression verified (prior-biased → incumbent-biased)
6. No regressions in existing test suite

---

## Out of Scope (Tier 1)

- Multi-task recovery (defer to Tier 2)
- Adaptive β tuning (fixed β=2.0 for Tier 1)
- Constraint-aware priors (defer until V10 constraint validation)
- Prior diagnostics UI (testing only, no reporting tools yet)

---

## Validation Tie-In

**V11a (folklore prior superiority):** Uses same good_prior from recovery tests
**V11b (wrong prior non-inferiority):** Uses same wrong_prior from recovery tests

These unit tests establish the mechanisms work before validation campaigns measure statistical effects across tasks.