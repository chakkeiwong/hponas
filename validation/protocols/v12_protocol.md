# V12 Protocol: Mixed-Space TuRBO

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 2 (conditional on V04-T1 fix)  

---

## Claim

Mixed-space TuRBO (trust region with categorical + continuous knobs) beats continuous-only TuRBO on mixed-space tasks.

**Operational requirement:** NAS and many practical tasks have mixed spaces (activation functions, layer types, etc.).

---

## Hypothesis

### H0 (Null Hypothesis)
Mixed-space TuRBO does not beat continuous-only TuRBO on mixed-space tasks.

### H1 (Alternative Hypothesis)
Mixed-space TuRBO beats continuous-only TuRBO by at least δ margin.

### Test Type
**Superiority test** (one-sided) - mixed-space must beat continuous-only.

---

## Preregistration

### Task
**Benchmark:** Mixed-space NAS or RL task
- Categorical: activation ∈ {relu, tanh, swish}
- Continuous: learning_rate, weight_decay
- Ordinal: hidden_dim, n_layers

**Baseline:** Continuous-only TuRBO (ignores categorical, uses ordinal as continuous)

### Seeds
**Preregistered seeds:** 0, 1, 2, 3, 4 (5 seeds)

### Margin
**Superiority margin:** δ = 0.05 (5% improvement required)

**Justification:** Mixed-space handling adds complexity. 5% improvement justifies implementation.

### Alpha
α = 0.05 (one-sided test)

**Family correction:** V12 in dist_beta_gate family (per protocols.json lines 46-50), sole member (m=1).

### Power
- Target: 0.80
- Method: Simulation under mixed-space task

### Sample Size
**Preregistered:**
- n_trials = 100 per seed
- n_seeds = 5

---

## Decision States

### PASS
**All of the following must be true:**
1. Improvement ≥ 5%
2. p < 0.05
3. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. Improvement < 5%
2. p ≥ 0.05

**Consequence:** Remove mixed-space TuRBO (ship continuous-only).

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max sample
2. V04-T1 not fixed (TuRBO baseline depends on Sobol)

**Status:** V12 blocked until V04-T1 resolved.

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v12_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v12_results.json

### Log
- **Path:** validation/results/v12_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v12_mixed_space_turbo.py (to be created)
- **Validator:** validation/validators/v12_validator.py (V16-compliant)

### Dependencies
- hponas.turbo (TuRBO implementation)
- Mixed-space benchmark

---

## Known Issues

### Issue 1: Blocked on V04-T1
**Status:** Per BUILD_PROGRAM_v2.md lines 252-256, mixed-space TuRBO depends on TuRBO baseline, which depends on V04-T1.

**Resolution:** V12 cannot run until V04-T1 PASSED.

### Issue 2: Status Unknown
**Problem:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md line 812 lists V12 as "status unknown."

**Resolution:** This protocol establishes V12 specification for Tier 2.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] Mixed-space and continuous-only both run

### Check 2: No Post-Hoc Tuning
- [ ] Margin (5%) preregistered
- [ ] Task selected before campaign

### Check 3: Correct Reference
- [ ] Compares to continuous-only TuRBO (not self)

### Check 4: Runnable Independently
- [ ] Script runs standalone

---

## References

**Authority:**
- protocols.json lines 46-50 (dist_beta_gate family)
- BUILD_PROGRAM_v2.md lines 252-256 (depends on TuRBO)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md line 812 (V12 status unknown)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Blocked on V04-T1
- Margin: 5%
- n_trials: 100, n_seeds: 5

---

**END OF PROTOCOL**
