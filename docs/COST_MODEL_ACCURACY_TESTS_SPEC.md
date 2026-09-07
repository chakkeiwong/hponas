# Cost Model Accuracy Tests Spec

**Date:** 2026-09-07  
**Effort:** ~2.5 engineer-days  
**Context:** BUILD_PROGRAM_v2.md Tier 1 Tests (~7d), Cost-Aware component complete
**Status:** Implemented. 22 tests passing (9 accuracy + 4 integration + 9 pre-existing
`test_cost_aware.py`) in 61s. See the Dependencies section: the spec's "tests only"
assumption did not hold.

---

## Purpose

Test that CostModelGP accurately predicts trial costs and that EI-per-cost acquisition steers toward cost-efficient configurations without sacrificing objective quality.

**Key properties:**
1. Cost model learns monotonic trends (faster vs slower regions)
2. Cost model generalizes to unseen configs (out-of-sample prediction)
3. EI-per-cost acquisition finds Pareto-efficient solutions (quality vs cost tradeoff)
4. Temperature cooling balances exploration and cost-awareness

---

## Background

Per TIER1_PROGRESS_SUMMARY.md section 11:
- `CostModelGP`: GP surrogate over log(wall-clock time)
- `EI-per-cost`: α_cost(x) = α(x) / cost_model(x)^T
- Cost cooling: Temperature T anneals from 0 (warmup) to 1 (full cost-aware)
- Handles wide cost ranges (0.1s to 1000s+) via log-transform
- Config normalization to [0,1]^d unit cube with log-warping

Existing tests (test_cost_aware.py, 9/9 passing):
- Cold start behavior
- Learning from observations
- Temperature cooling schedule
- Wide cost range handling
- Integration with CostAwareGPSearcher

**Gap:** No tests for prediction accuracy, generalization, or end-to-end cost-efficiency.

---

## Requirements

### Functional

1. **Cost prediction accuracy**
   - Given training data with known cost trend, verify predictions follow trend
   - Measure mean absolute percentage error (MAPE) on held-out configs
   - Test on synthetic functions with controllable cost patterns

2. **Generalization**
   - Train on subset of space, predict on held-out region
   - Verify predictions are reasonable (not default, not degenerate)
   - Test interpolation (within training hull) and extrapolation (outside)

3. **Monotonicity preservation**
   - If true cost is monotonic in a dimension, predictions should preserve direction
   - Example: larger network width → higher cost

4. **EI-per-cost tradeoff**
   - Given task with quality-cost tradeoff, verify CostAwareGPSearcher finds solutions on Pareto front
   - Compare against cost-agnostic baseline (should achieve better cost-efficiency)

5. **Temperature effect**
   - Warmup phase (T=0): proposals match base searcher
   - Full cost-aware (T=1): proposals favor low-cost regions
   - Intermediate T: smooth interpolation

### Non-functional

6. **Deterministic** - Fixed seeds for reproducibility
7. **Fast** - Unit tests run in <5s each, integration tests <30s
8. **Isolated** - No external dependencies beyond existing test infrastructure

---

## Test Strategy

### Suite 1: Cost Model Prediction Accuracy (~1d)

**File:** `tests/test_cost_model_accuracy.py`

#### T1.1: Linear cost trend prediction
- Space: 1D continuous x ∈ [0, 1]
- True cost: cost(x) = 1 + 9x (linear, 1s to 10s)
- Train: 10 uniform samples
- Test: 20 held-out uniform samples
- Metric: MAPE < 20% on test set, Spearman rho > 0.9

#### T1.2: Quadratic cost trend prediction
- Space: 1D continuous x ∈ [0, 1]
- True cost: cost(x) = 1 + 99x² (quadratic, 1s to 100s)
- Train: 15 samples (including x=0, 0.5, 1.0)
- Test: 25 held-out samples
- Metric: MAPE < 25%, predictions preserve monotonicity

#### T1.3: Multi-dimensional cost
- Space: 2D (x1, x2) ∈ [0, 1]²
- True cost: cost(x1, x2) = 1 + 4x1 + 4x2 (additive)
- Train: 20 samples
- Test: 30 held-out samples
- Metric: MAPE < 30%, corner predictions rank correctly

#### T1.4: Log-warped cost
- Space: 1D continuous x ∈ [1, 100] with log transform
- True cost: cost(x) = x / 10 (linear in log-space)
- Train: 10 log-uniform samples
- Test: 20 held-out samples
- Metric: MAPE < 25%, predictions increase with x

#### T1.5: Extrapolation robustness
- Space: 1D x ∈ [0, 1]
- Train: 10 samples from x ∈ [0.2, 0.8]
- Test: query x=0, x=1 (extrapolation)
- Metric: Predictions are positive, finite, and reasonable (not default=1.0)

#### T1.6: Small sample behavior
- Train: 2 samples (minimum for GP)
- Test: Verify predictions interpolate, do not crash
- Train: 1 sample → should return default or median

### Suite 2: EI-per-Cost Integration (~1d)

**File:** `tests/test_cost_efficiency.py`

#### T2.1: Cost-quality tradeoff task
- Objective: quality(x) = 0.5 + 0.1x + noise(0, 0.15), noise deterministic in x
- Cost: cost(x) = 1 + 99x (increasing, 1s to 100s)
- Run CostAwareGPSearcher for 20 trials, warmup=5, cooldown_duration=1 (fast T→1)
- Run baseline GPqLogEISearcher **at the same seed** for 20 trials
- Metric: Cost-aware achieves better quality-per-cost ratio (total quality / total cost)

**Fixture design note (revised during implementation).** The original spec put
the quality peak at x=0, the *cheapest* point, so quality and cost optima
coincide: a single config dominates on both axes, both arms converge to it, and
the ratio measures convergence speed rather than cost-awareness. Moving the peak
to the expensive end fixes that but exposes a second, deeper problem — scale
competition. Once the GP converges on a smooth deterministic 1D objective,
qLogEI's spread across the space reaches ~32-35 nats, while the log-cost spread
is bounded by log(cost ratio): 2.30 nats at 10×, 4.61 nats at 100×. The cost
penalty is then a few-percent correction on a term varying an order of magnitude
more and cannot move the argmax. This is correct EI-per-cost behaviour, not a
defect: a 10× cost saving does not justify abandoning a region e^35 times more
promising.

The lever is therefore a **flatter or noisier quality surface**, not a steeper
cost function (100× was measured and found insufficient: improvement +0.046
against a 0.05 threshold). A weak trend buried in observation noise keeps EI
alive across the space, and the cost term competes. Measured separation on the
adopted fixture: efficiency +1.19, cumulative cost 850 vs 1860.

Both arms must also run at the **same seed** — with different seeds the test
passes or fails on sampling luck (a same-seed probe of the original fixture gave
cost 231.4 vs 231.4, ratio 1.000, while the seed-42-vs-43 comparison "passed").

#### T2.2: Temperature progression effect
- Same task as T2.1
- Run with warmup=5, cooldown_duration=15, 25 trials, against a same-seed
  cost-agnostic GPqLogEISearcher
- Assert: (a) warmup proposals (n ≤ warmup, T=0) match the base searcher within
  0.05 — the searcher delegates verbatim; (b) early proposals span > 0.3;
  (c) late (trials 20-25) mean cost is < 50% of the baseline's

**Framing note (revised during implementation).** The original absolute
assertion — late mean x < 0.6 — asserts a property EI-per-cost does not have at
this cost scale, and is vacuously true on any task whose optimum happens to sit
in the cheap region. Recast as a same-seed differential it tests the mechanism:
measured late mean cost 1.0 (cost-aware) vs 98.2 (baseline) on a 1-100 range,
with the two trajectories identical through trial 5 and diverging at trial 6,
exactly where T first becomes non-zero.

#### T2.3: No free lunch check
- Objective: quality is independent of cost
- Cost: cost(x) = random uniform [1, 10]
- Run cost-aware vs baseline
- Metric: Final best quality should be similar (cost-awareness doesn't hurt when cost uninformative)

#### T2.4: Severe cost gradient
- Objective: quality(x) = random GP surface (no structure)
- Cost: cost(x) = 1 if x < 0.5 else 100 (cliff)
- Run cost-aware with T=1
- Metric: >80% of proposals in x < 0.5 (low-cost region) by trial 20

### Suite 3: Robustness (~0.5d)

**File:** Add to `test_cost_model_accuracy.py`

#### T3.1: Identical cost observations
- Train: 5 samples all with cost=5.0 (zero variance)
- Test: Predictions should return constant (not crash, not NaN)

#### T3.2: Near-zero costs
- Observe cost=0.01 (valid, but extreme)
- Predict: should handle log(0.01) gracefully

#### T3.3: Cost outliers
- Train: [1.0, 1.1, 1.2, 50.0, 1.3] (one outlier)
- Predict: model should not be dominated by outlier

---

## Acceptance Criteria

- 15 tests total (6 accuracy + 4 integration + 3 robustness)
- All tests passing
- Suite runs in <60s total
- Coverage: CostModelGP predict/observe paths, CostAwareAcquisition forward, temperature schedule edge cases

---

## Dependencies

- Existing: CostModelGP, CostAwareGPSearcher, linear_cooling_schedule
- Test fixtures: synthetic cost functions, quality-cost tradeoff tasks
- **New implementation was required.** The spec assumed EI-per-cost was already
  wired; writing Suite 2 showed it was not. `CostAwareGPSearcher.propose()`
  delegated to the base searcher on both branches, so the cost penalty was never
  applied, and `CostAwareAcquisition` was not exercised by any test in
  `test_cost_aware.py` (a grep for the class name there returns nothing), which
  is how the defects survived a "COMPLETE" status. Fixed in `searchers_cost.py`:
  (1) `propose()` now builds the GP, wraps the base acquisition, and runs
  `optimize_acqf`, with a duck-typed fallback to delegation for searchers that
  lack the BoTorch hooks (e.g. `SobolSearcher`); (2) `forward()` applies the
  penalty **subtractively** for log-scale acquisitions — dividing a qLogEI value
  by cost^T inverts the preference wherever EI < 1, the same bug already fixed in
  `PriorWeightedAcquisition`; (3) `forward()` handles BoTorch's `b × q × d`
  q-batch shape rather than iterating rows; (4) new
  `CostModelGP.posterior_mean_log_cost()` keeps the cost term in torch, since
  `predict()` round-trips through numpy under `no_grad` and would contribute no
  gradient to the L-BFGS acquisition optimizer.

---

## Success Metrics

Per TIER1_PROGRESS_SUMMARY.md completion criteria:
- Cost model accuracy verified on multiple cost patterns
- EI-per-cost demonstrates cost-efficiency improvement
- Robustness to edge cases (zero variance, outliers, extrapolation)
- Tests complete → Tier 1 Tests milestone advances to 7/7d complete
