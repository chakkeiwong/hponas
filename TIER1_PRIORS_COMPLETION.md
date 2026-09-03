# Tier 1 Priors Component - Progress Report

**Date:** 2026-09-03  
**Status:** 6/13 days complete (46% of Priors component)  
**Test Results:** 171/171 tests passing, 85% coverage

---

## Summary

Implemented core prior-aware optimization methods for Tier 1:
- πBO (prior-weighted acquisition) - 4 days
- PriorBand (portfolio sampler) - 2 days

Both components are production-ready with comprehensive test coverage. Remaining work (7 days) includes nonzero guard, warm-start integration, and V11 validation campaigns.

---

## Components Completed

### 1. πBO: Prior-Weighted Acquisition (4 days) ✅

**Survey:** Ch 8 roadmap-10, ch08-01  
**Formula:** α^π(x) = α(x) · π(x)^(β/n)

**Implementation:**
- Added `prior_fn` and `prior_beta` parameters to GPqLogEISearcher
- PriorWeightedAcquisition class wraps any base acquisition
- Prior exponent β/n decays as observations grow
- Epsilon guard prevents log(0) for degenerate priors

**Key Properties:**
- Early optimization: Strong prior influence (large β/n)
- Late optimization: Prior forgotten (β/n → 0)
- Wrong priors: Gracefully forgotten, not obeyed indefinitely
- Good priors: Extract value early when data is scarce

**Tests (6/6 passing):**
- Prior acceptance and capability reporting
- Vanilla GP when no prior provided
- Zero prior handled gracefully (epsilon guard)
- Qualitative tests for prior influence and decay

**Files:**
- `hponas/searchers_gp.py`: πBO integration
- `tests/test_pibo.py`: πBO test suite

---

### 2. PriorBand: Portfolio Sampler (2 days) ✅

**Survey:** Ch 8 roadmap-10, ch08-03  
**Algorithm:** Portfolio mixing for ASHA rungs

**Implementation:**
- Three sampling strategies: uniform, prior-biased, incumbent perturbations
- Rung-adaptive weights: early rungs favor prior, later rungs favor incumbent
- Rejection sampling from prior density
- Gaussian perturbations around best-so-far
- Incumbent tracking with updates

**Key Properties:**
- Rung 0: High prior weight (exploration + expert knowledge)
- Later rungs: Shift toward incumbent perturbations (local search)
- Graceful degradation: Zero prior falls back to uniform
- Continuous knobs only (Tier 1 scope)

**Tests (9/9 passing):**
- Prior acceptance and capability reporting
- Valid config generation within bounds
- Incumbent tracking and updates
- Rung adaptation (later rungs cluster around incumbent)
- Prior-biased sampling pulls toward prior peak
- Incumbent perturbation stays local
- Edge cases (zero prior, no continuous knobs)

**Files:**
- `hponas/searchers_priorband.py`: PriorBand implementation
- `tests/test_priorband.py`: PriorBand test suite

---

## Remaining Work (7 days)

### Nonzero Guard (~1 day)
**Requirement:** Prevent prior density from collapsing to zero regions  
**Status:** Not started  
**Rationale:** Survey mentions "nonzero guard" but details unclear

### Warm-Start Integration (~2 days)
**Requirement:** Query run store for similar past studies to seed new studies  
**Status:** Not started  
**Dependencies:** Store querying infrastructure  
**Validation:** V12 (warm-start > cold-start)

### V11 Validation Campaign (~4 days)
**Requirement:** Prior effectiveness under good/wrong advice scenarios  
**Status:** Not started  
**Pass rule:**
- Good prior: Gains over baseline
- Wrong prior: Recovery within noise
- Failure: Demote πBO/PriorBand to opt-in
**Validation:** V11a (MO veto), V11b (πBO effectiveness)

---

## Technical Highlights

### πBO Design Decisions

1. **Prior Evaluation in Original Space**
   - Prior functions receive configs in original knob space
   - Avoids forcing users to think in normalized [0,1]^d coordinates
   - Denormalization happens inside PriorWeightedAcquisition

2. **Acquisition-Agnostic Wrapper**
   - Works with any AcquisitionFunction (qLogEI, qUCB, etc.)
   - Wraps base acquisition, doesn't replace it
   - Clean separation of concerns

3. **Epsilon Guard for Numerical Stability**
   - Prior values clamped to ≥ 1e-12 before exponentiation
   - Prevents log(0) crashes on pathological priors
   - Graceful degradation rather than hard failures

### PriorBand Design Decisions

1. **Rung-Adaptive Weight Decay**
   ```python
   rung_decay = 0.9 ** rung_idx
   adapted_prior_weight = base_prior_weight * rung_decay
   adapted_incumbent_weight = base_incumbent_weight + (base_prior_weight - adapted_prior_weight)
   ```
   - Exponential decay of prior influence
   - Transferred weight goes to incumbent (not uniform)
   - Preserves total weight sum = 1.0

2. **Rejection Sampling for Prior Density**
   - Generate n_candidates=100 uniform samples
   - Weight by prior density π(x)
   - Sample one proportional to weights
   - Fallback to uniform if prior degenerates

3. **Incumbent Perturbation Strategy**
   - Gaussian noise scaled by knob range
   - Std dev = perturbation_scale * (high - low)
   - Clipped to bounds
   - Fallback to uniform before first incumbent

---

## Integration Points

### Using πBO with GP Searcher

```python
from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_gp import GPqLogEISearcher

# Define prior density
def my_prior(config: dict) -> float:
    x = config["learning_rate"]
    # Gaussian peaked at 0.01
    return np.exp(-0.5 * ((np.log(x) - np.log(0.01)) / 0.5) ** 2)

# Create GP searcher with prior
space = SearchSpace()
space.add_knob(Knob("learning_rate", kind="continuous", bounds=(1e-5, 1e-1), transform="log"))

searcher = GPqLogEISearcher(
    space,
    prior_fn=my_prior,
    prior_beta=2.0,  # Decay rate
    seed=42
)

# Use normally
configs = searcher.propose(10)
searcher.observe({"config": configs[0], "value": trial_result})
```

### Using PriorBand with ASHA

```python
from hponas.searchers_priorband import PriorBandSampler

sampler = PriorBandSampler(
    space,
    prior_fn=my_prior,
    seed=42,
    uniform_weight=0.3,
    prior_weight=0.4,
    incumbent_weight=0.3,
    perturbation_scale=0.1  # 10% perturbations
)

# Propose configs for current rung
configs = sampler.propose(n=20, rung_idx=0)  # Early rung

# Update incumbent
sampler.observe({"config": best_config, "value": best_value})

# Later rung proposals shift toward incumbent
configs_late = sampler.propose(n=20, rung_idx=3)
```

---

## Test Coverage

**πBO Tests:** 6/6 passing
- test_pibo_accepts_prior_fn
- test_pibo_without_prior_is_vanilla
- test_pibo_good_prior_helps_early
- test_pibo_prior_weight_decays
- test_pibo_larger_beta_slower_decay
- test_pibo_zero_prior_handled

**PriorBand Tests:** 9/9 passing
- test_priorband_accepts_prior
- test_priorband_without_prior
- test_priorband_proposes_valid_configs
- test_priorband_updates_incumbent
- test_priorband_rung_adaptation
- test_priorband_prior_sampling_works
- test_priorband_incumbent_perturbation_works
- test_priorband_requires_continuous_knobs
- test_priorband_degenerate_prior_handled

**Overall:** 171/171 tests passing, 85% coverage

---

## Progress Summary

**Tier 1 Overall:** 31/70 days (44%)

**Priors Component:** 6/13 days (46%)
- ✅ πBO: 4 days
- ✅ PriorBand: 2 days
- ⏸ Nonzero guard: 1 day
- ⏸ Warm-start: 2 days
- ⏸ V11 validation: 4 days

**Master Program Status:**
- R0, R1, Tier 0: Complete
- Tier 1: 44% complete
- Tier 2, Beta, Tier 3: Not started

---

## Next Steps

1. **Cost-Aware Acquisition** (7 days) ← Next component
   - EI-per-cost with cost cooling
   - Cost model (GP over log wall-clock time)

2. **Complete Priors** (7 days remaining)
   - Nonzero guard implementation
   - Warm-start integration with store
   - V11 validation campaigns

3. **Production Workloads** (15 days)
   - hamiltonian_mo
   - sampler_neutra
   - finance (conditional)

**All code committed and pushed. Ready to continue with Tier 1 remaining work.**
