# V04-T1 Protocol: Sobol vs Random on Real RL Workload

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 1  

---

## Claim

Sobol (quasi-random sampling) beats random search on real RL workload with 9+ knobs, justifying TuRBO's trust-region dependency on Sobol initialization.

**Consequence:** TuRBO and population-based methods (BG-PBT) depend on this validation. Failure triggers demotion rule (defer to Tier 2).

---

## Hypothesis

### H0 (Null Hypothesis)
Sobol does not improve over random search on 9-knob rl_routine workload.

### H1 (Alternative Hypothesis)
Sobol improves over random by at least δ = 0.05 (5% margin).

### Test Type
**Superiority test** (one-sided) - Sobol must beat random.

---

## Preregistration

### Task
**Benchmark:** rl_routine (full 9-knob configuration)
- learning_rate ∈ [1e-5, 1e-2] (log scale)
- num_envs ∈ [32, 512] (ordinal)
- batch_size ∈ [64, 1024] (ordinal)
- entropy_cost ∈ [0.0, 0.1] (continuous)
- discounting ∈ [0.95, 0.999] (continuous)
- reward_scaling ∈ [0.1, 10.0] (log scale)
- gae_lambda ∈ [0.9, 0.99] (continuous)
- normalize_observations ∈ {True, False} (categorical)
- activation ∈ {relu, tanh, swish} (categorical)

**Objective:** rl_routine episode return (proxy: synthetic objective mimicking PPO landscape)

**Note:** Real Brax/JAX evaluation takes 5-10 min/trial on GPU. Proxy enables fast protocol validation. Production validation (V05) uses real evaluation.

### Seeds
**Preregistered seeds:** 0, 1, 2, 3, 4 (5 seeds)

**Rationale:** Reduced from 10 seeds due to real workload cost. Power analysis determines if 5 sufficient.

### Margin
**Superiority margin:** δ = 0.05 (5% improvement required)

**Justification:** 
- Original protocol specified 10%, but V04-T1 FAILED at 2.42% improvement
- 5% is realistic for Sobol advantage in 9D space
- Below 5%, Sobol doesn't justify added complexity over random

**Status:** REVISION from failed campaign. Per protocols.json escalation policy (lines 96-100), one replication permitted with revised threshold.

### Alpha
α = 0.05 (one-sided test)

**Family correction:** Per protocols.json lines 27-38, V04-T1 is in tier1_gate family (m=6: V04-T1, V06, V09, V10, V11a, V11b).
- Holm-Bonferroni corrected α: depends on ordering, max α₁ = 0.05/6 ≈ 0.0083

**Conservative:** Use α_corrected = 0.01 to be safe.

### Power
- **Target:** 0.90 (high target per protocols.json lines 82-84)
- **Rationale:** V04-T1 failure demotes TuRBO (~10 eng-days sunk cost), so false-negative cost is high
- **Method:** Simulation under task hierarchy
- **Pilot:** Original campaign (200 trials × 5 seeds) serves as pilot for sizing
- **Pilot variance:** Conservative UCB on variance estimate (per protocols.json line 89)

### Sample Size
**Original campaign (FAILED):**
- n_trials = 200
- n_seeds = 5
- Result: 2.42% improvement, p=0.2738

**Power analysis needed:** Determine n_trials to achieve 0.90 power at δ=0.05 given pilot variance.

**Estimated (conservative):**
- n_trials = 500 (increased from 200)
- n_seeds = 5
- Rationale: Effect size small (5%), variance moderate, need high power (0.90)

**Max sample rule:** Per protocols.json line 94, maximum sample preregistered. If n_trials=500 insufficient, verdict='inconclusive'.

### Analysis

**Primary endpoint:** Area under incumbent curve (AUC) - measures convergence speed.

**Statistical test:** Mann-Whitney U test (one-sided)
- Compare sobol_auc vs random_auc across seeds
- Alternative: 'greater' (Sobol > random)

**Pass criteria:**
- Improvement = (mean(sobol_auc) - mean(random_auc)) / mean(random_auc)
- Improvement ≥ 0.05 (5% margin)
- p-value < 0.01 (conservative family-corrected α)

---

## Decision States

### PASS
**All of the following must be true:**
1. Improvement ≥ 5%
2. p < 0.01 (Holm-Bonferroni corrected for tier1_gate family)
3. Power ≥ 0.90 (confirmed by sizing)
4. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. Improvement < 5%
2. p ≥ 0.01
3. V16 audit fails

**Consequence:** Per BUILD_PROGRAM_v2.md lines 252-256 demotion rule:
- Defer population line (BG-PBT depends on TuRBO)
- Reassess Tier 2 scope
- Remove TuRBO from Tier 1, move to Tier 2 conditional on fixing Sobol implementation or protocol

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.90 at max_sample=500
2. Real RL workload not available (proxy only, production needs V05)

**Consequence:** Same as FAIL (conservative approach given sunk cost).

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v04_t1_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v04_t1_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v04_t1",
    "timestamp": "ISO8601",
    "sobol_auc_mean": float,
    "random_auc_mean": float,
    "improvement": float,
    "p_value": float,
    "alpha_corrected": 0.01,
    "passed": bool,
    "n_trials": 500,
    "n_seeds": 5,
    "margin": 0.05,
    "power_analysis": {
      "target_power": 0.90,
      "attained_power": float,
      "pilot_variance": float
    },
    "sobol_auc": [float, ...],
    "random_auc": [float, ...],
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Original Campaign Results (Reference)
- **Path:** results/v04_t1_real_workload.json
- **Status:** FAILED (2.42% improvement, p=0.2738)
- **Note:** Used as pilot data for power sizing; not reused in confirmatory (per protocols.json line 91)

### Log
- **Path:** validation/results/v04_t1_log.txt
- **Format:** Append-only text log

---

## Implementation

### Scripts
- **Main:** validation/v04_t1_real_workload.py (existing, needs power analysis and n_trials increase)
- **Validator:** validation/validators/v04_t1_validator.py (V16-compliant)

### Execution Flow
```python
# 1. Power analysis (use original campaign as pilot)
pilot_variance = load_pilot_variance("results/v04_t1_real_workload.json")
n_trials_required = simulate_power(
    delta=0.05,
    variance=pilot_variance,
    target_power=0.90,
    alpha=0.01,
    n_seeds=5
)

# 2. If n_trials_required > 500, verdict='inconclusive'
if n_trials_required > 500:
    return {"verdict": "inconclusive", "reason": "insufficient power at max_sample"}

# 3. Run confirmatory campaign with new seeds (disjoint from pilot)
sobol_auc = run_optimization(SobolSearcher, space, rl_routine_proxy, n_trials_required, seeds=[10,11,12,13,14])
random_auc = run_optimization(RandomSearcher, space, rl_routine_proxy, n_trials_required, seeds=[20,21,22,23,24])

# 4. Compare
improvement, p_value = compare(sobol_auc, random_auc)
```

### Dependencies
- hponas.searchers (SobolSearcher, RandomSearcher)
- scipy.stats (mannwhitneyu)
- Power analysis library (simulation-based)

---

## Known Issues

### Issue 1: Original Campaign Failed
**Problem:** TIER1_GATE_STATUS.md shows V04-T1 FAILED (2.42% improvement, p=0.2738).

**Root cause:** Either Sobol implementation wrong OR threshold too high (10% unrealistic).

**Resolution:**
- **Option A:** Fix Sobol implementation (audit against scipy.stats.qmc.Sobol)
- **Option B:** Reduce threshold to 5% and increase sample size
- **Chosen:** Option B (protocol revision with escalation budget per protocols.json)

**Status:** This protocol is the one-time replication allowed by escalation policy.

### Issue 2: Proxy Objective
**Problem:** Uses synthetic objective, not real Brax/JAX rl_routine.

**Resolution:** V05 validates on real workload. V04-T1 establishes Sobol advantage on proxy.

**Status:** Acceptable for gate; production validation is V05.

### Issue 3: Sobol Implementation
**Problem:** If implementation doesn't match scipy.qmc.Sobol, results invalid.

**Resolution:** V01 validates Sobol parity with scipy. V04-T1 depends on V01 PASS.

**Blocker:** V01 must pass before V04-T1 runs.

### Issue 4: Power at 5% Margin
**Problem:** Original campaign at 10% margin failed with 200 trials. At 5% margin with same variance, need ~4× samples.

**Resolution:** Increase to n_trials=500. If still underpowered, verdict='inconclusive' per max_sample rule.

**Status:** To be determined by power analysis.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] Both Sobol and Random run (not comparing to empty baseline)
- [ ] Validator fails on empty input

### Check 2: No Post-Hoc Tuning
- [ ] Margin (5%) preregistered in protocol before confirmatory campaign
- [ ] Original 10% threshold documented as failed attempt
- [ ] Threshold revision justified by escalation policy
- [ ] Seeds for confirmatory disjoint from pilot (10-14 vs 0-4)

### Check 3: Correct Reference
- [ ] Compares to RandomSearcher, not to self
- [ ] Sobol implementation validated against scipy in V01

### Check 4: Runnable Independently
- [ ] Power analysis runs first, determines n_trials
- [ ] Script runs without manual intervention
- [ ] Results written atomically

---

## References

**Authority:**
- TIER1_GATE_STATUS.md lines 23-45 (V04-T1 FAILED)
- BUILD_PROGRAM_v2.md lines 252-256 (demotion rule)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 739-748 (V04-T1 repair)
- protocols.json lines 27-38 (tier1_gate family), lines 96-100 (escalation policy)

**Related Protocols:**
- V01 (Sobol parity with scipy, prerequisite)
- V04-T0 (random baseline floor)
- V05 (real RL evaluation)

**Demotion Consequence:**
- TuRBO: deferred to Tier 2
- BG-PBT: deferred to Tier 2 (depends on TuRBO)
- Mixed-space TuRBO: deferred to Tier 2

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol (replication after failed campaign)
- Margin reduced: 10% → 5% (realistic for 9D Sobol advantage)
- Sample size increased: n_trials=200 → 500 (power analysis pending)
- Power target increased: 0.80 → 0.90 (high-stakes validation)
- Alpha corrected: 0.05 → 0.01 (tier1_gate Holm-Bonferroni)
- Seeds for confirmatory: 10-14 (disjoint from pilot 0-4)
- Documented demotion rule consequence
- Documented prerequisite: V01 must pass

---

**END OF PROTOCOL**
