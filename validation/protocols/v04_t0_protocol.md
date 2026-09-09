# V04-T0 Protocol: Random Baseline Floor

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

Random search beats pathological configurations on real workloads, establishing that random is a valid baseline comparator.

**Operational requirement:** If random search is worse than doing nothing, it cannot serve as a floor for other methods.

---

## Hypothesis

### H0 (Null Hypothesis)
Random search does not improve over a pathological default configuration on real RL workload.

### H1 (Alternative Hypothesis)
Random search improves over pathological default by at least δ margin.

### Test Type
**Superiority test** (one-sided) - random must beat pathological default.

---

## Preregistration

### Task
**Benchmark:** rl_routine (simplified 3-knob version for Tier 0)
- learning_rate ∈ [1e-5, 1e-2] (log scale)
- batch_size ∈ [64, 512] (ordinal)
- entropy_cost ∈ [0.0, 0.1] (continuous)

**Pathological default:** Worst known configuration
- learning_rate = 1e-5 (too low, learning stalls)
- batch_size = 64 (too small, high variance)
- entropy_cost = 0.1 (too high, exploration dominates)

**Objective:** Synthetic RL objective (proxy for real Brax/JAX evaluation)

### Seeds
Preregistered seeds: 0, 1, 2, 3, 4 (5 seeds)

### Margin
**Superiority margin:** δ = 0.05 (5% improvement required)

**Justification:** 5% improvement over pathological config is minimal bar for "random search works."

### Alpha
α = 0.05 (one-sided test)

**Family correction:** Per protocols.json lines 19-26, V04-T0 is in tier0_gate family with V05 (m=2).
- Holm-Bonferroni corrected α: α₁ = 0.05/2 = 0.025 (most significant), α₂ = 0.05/1 = 0.05

### Power
- Target: 0.80
- Method: Simulation under task hierarchy (per protocols.json lines 85-86)
- Pilot: 5 replicates minimum (per protocols.json line 87)

### Sample Size
**Preregistered:**
- n_trials = 50 per seed
- n_seeds = 5
- Total studies = 5

**Rationale:** 50 trials sufficient for random search to explore 3D space.

### Analysis

**Primary endpoint:** Area under incumbent curve (AUC) - measures convergence speed.

**Statistical test:** Mann-Whitney U test (one-sided)
- Compare random_auc vs pathological_auc
- Alternative: 'greater' (random > pathological)

**Pass criteria:**
- Improvement = (mean(random_auc) - mean(pathological_auc)) / mean(pathological_auc)
- Improvement ≥ 0.05 (5% margin)
- p-value < α_corrected (0.025 after Holm-Bonferroni)

---

## Decision States

### PASS
**All of the following must be true:**
1. Improvement ≥ 5%
2. p < 0.025 (Holm-Bonferroni corrected, assuming V04-T0 tests first)
3. V16 audit: non-vacuous, threshold preregistered (not post-hoc tuned)

### FAIL
**Any of the following:**
1. Improvement < 5%
2. p ≥ 0.025
3. V16 audit fails (post-hoc tuning detected)

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max sample
2. Pilot variance too high to size confirmatory
3. Real RL workload not available (proxy only)

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v04_t0_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v04_t0_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v04_t0",
    "timestamp": "ISO8601",
    "random_auc_mean": float,
    "pathological_auc_mean": float,
    "improvement": float,
    "p_value": float,
    "alpha_corrected": 0.025,
    "passed": bool,
    "n_trials": 50,
    "n_seeds": 5,
    "margin": 0.05,
    "random_auc": [float, ...],
    "pathological_auc": [float, ...],
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Log
- **Path:** validation/results/v04_t0_log.txt
- **Format:** Append-only text log

---

## Implementation

### Scripts
- **Main:** validation/v04_performance_check.py (modify for pathological baseline)
- **Validator:** validation/validators/v04_t0_validator.py (V16-compliant)

### Execution
```python
# Pathological config
pathological_config = {
    "learning_rate": 1e-5,
    "batch_size": 64,
    "entropy_cost": 0.1
}

# Run random search
random_auc = run_optimization(RandomSearcher, space, objective, n_trials=50, seeds=[0,1,2,3,4])

# Run pathological baseline (fixed config, repeated n_trials times)
pathological_auc = run_pathological(pathological_config, objective, n_trials=50, seeds=[0,1,2,3,4])

# Compare
improvement, p_value = compare(random_auc, pathological_auc)
```

### Dependencies
- hponas.searchers (RandomSearcher)
- scipy.stats (mannwhitneyu)

---

## Known Issues

### Issue 1: Post-Hoc Tuned Threshold
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md line 733 identified V04-T0 as post-hoc tuned.

**Resolution:** Threshold now preregistered in protocol at 5% before any data collection.

**Status:** Fixed in this protocol version.

### Issue 2: Proxy Objective
**Problem:** validation/v04_performance_check.py uses synthetic objective, not real Brax/JAX rl_routine.

**Resolution:** Noted in INCONCLUSIVE criteria. Real RL validation is V05.

**Status:** Acceptable for Tier 0 (V05 validates on real workload).

### Issue 3: Pathological Config Definition
**Problem:** "Pathological" is subjective.

**Resolution:** Preregistered specific values known to be poor:
- lr=1e-5 (too low)
- batch_size=64 (too small)
- entropy_cost=0.1 (too high)

**Status:** Defined in protocol.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] Pathological config is distinct from random samples
- [ ] Validator fails on empty input

### Check 2: No Post-Hoc Tuning
- [ ] Threshold (5%) matches protocol exactly
- [ ] Threshold not changed after seeing data
- [ ] Pathological config preregistered, not selected after experiments

### Check 3: Correct Reference
- [ ] Compares to explicitly bad config, not to self
- [ ] Pathological config justification documented

### Check 4: Runnable Independently
- [ ] Script runs without manual intervention
- [ ] All parameters from protocol
- [ ] Results written atomically

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md lines 733-738 (post-hoc tuning issue)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 733-738 (V04-T0 repair)
- protocols.json lines 19-26 (tier0_gate family with V05)

**Related Protocols:**
- V04-T1 (Sobol vs Random on real workload)
- V05 (real RL evaluation, not proxy)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- Fixed post-hoc tuning: threshold preregistered at 5%
- Pathological config preregistered: lr=1e-5, batch=64, entropy=0.1
- Seeds preregistered: 0, 1, 2, 3, 4
- Sample size: n_trials=50, n_seeds=5
- Holm-Bonferroni correction: α=0.025 (tier0_gate family)

---

**END OF PROTOCOL**
