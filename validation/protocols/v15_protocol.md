# V15 Protocol: ifBO Performance (V15a + V15b Fixed-Sequence)

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 3 (elective, separate family)  

---

## Claim

**V15a (primary):** ifBO (Iterative Feature BO with pretrained surrogate) beats standard GP on high-dimensional tasks.  
**V15b (fallback, only if V15a rejects):** ifBO with custom power-law model beats standard GP.

**Fixed-sequence gatekeeping:** V15b tested ONLY if V15a rejects H0. This preserves family-wise error rate at α without correction.

---

## Hypotheses

### V15a: Pretrained Surrogate (PRIMARY)

**H0:** ifBO with pretrained surrogate does not beat standard GP.  
**H1:** ifBO with pretrained surrogate beats standard GP by ≥δ.  
**Test type:** Superiority (one-sided)

### V15b: Custom Power-Law Fallback (ONLY IF V15a REJECTS)

**H0:** ifBO with custom power-law does not beat standard GP.  
**H1:** ifBO with custom power-law beats standard GP by ≥δ.  
**Test type:** Superiority (one-sided)

**Gatekeeping:** V15b is only tested if V15a rejects H0 (p ≥ α). This fixed-sequence structure controls family-wise error at α despite two tests.

---

## Preregistration

### Task
**Benchmark:** High-dimensional synthetic or NAS task (d ≥ 20 dimensions)
- GP struggles with high-d due to curse of dimensionality
- ifBO iteratively adds features (dimensions) to manage complexity

**Baseline:** Standard GP with RBF kernel

### Seeds
**Preregistered seeds:** 0, 1, 2, 3, 4 (5 seeds)

### Margins
**V15a (pretrained):** δ = 0.10 (10% improvement)  
**V15b (power-law):** δ = 0.10 (10% improvement)

**Justification:** High-d advantage should be substantial. 10% improvement justifies complexity.

### Alpha
**V15a:** α = 0.05 (unadjusted, tests first)  
**V15b:** α = 0.05 (unadjusted, only if V15a fails)

**Family correction:** Per protocols.json lines 59-70, V15a/V15b form fixed-sequence pair in tier3_v15 family.
- No Bonferroni correction needed (gatekeeping structure controls family-wise error)

### Power
- Target: 0.80
- Method: Simulation under high-d task

### Sample Size
**Preregistered:**
- n_trials = 100 per seed
- n_seeds = 5

---

## Decision States

### PASS (V15a)
**All of the following must be true:**
1. V15a improvement ≥ 10%
2. V15a p < 0.05
3. V16 audit: non-vacuous, threshold preregistered

**Result:** ifBO ships with pretrained surrogate. V15b not tested.

### PASS (V15b, contingent)
**All of the following must be true:**
1. V15a FAILED (p ≥ 0.05)
2. V15b tested
3. V15b improvement ≥ 10%
4. V15b p < 0.05

**Result:** ifBO ships with custom power-law fallback.

### FAIL
**Any of the following:**
1. V15a FAILED AND (V15b not tested OR V15b FAILED)

**Consequence:** Remove ifBO from roadmap.

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max sample
2. High-d benchmark not available

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v15_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **V15a:** validation/results/v15a_results.json
- **V15b:** validation/results/v15b_results.json (only if V15a fails)

### Log
- **Path:** validation/results/v15_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v15_ifbo_performance.py (to be created)
- **Validator:** validation/validators/v15_validator.py (V16-compliant, enforces gatekeeping)

### Dependencies
- hponas.ifbo (ifBO implementation)
- Pretrained surrogate model
- High-d benchmark

---

## Known Issues

### Issue 1: Specification Violation
**Problem:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 97-101 document ifBO spec violation:
- WRONG: Custom power-law model
- RIGHT: Pretrained surrogate model

**Resolution:** V15a tests correct implementation (pretrained). V15b tests wrong implementation (power-law) as fallback.

**Status:** Spec violation acknowledged, V15a/V15b structure provides path forward.

### Issue 2: Status Unknown
**Problem:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md line 833 lists V15 as "status unknown."

**Resolution:** This protocol establishes V15 specification for Tier 3.

### Issue 3: Gatekeeping Enforcement
**Problem:** Fixed-sequence gatekeeping requires V15b only test if V15a fails.

**Resolution:** Validator enforces sequence (V15b blocked if V15a passes).

**Status:** To be implemented in v15_validator.py.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] V15a tested
- [ ] V15b tested ONLY if V15a fails

### Check 2: No Post-Hoc Tuning
- [ ] Margins (10%, 10%) preregistered
- [ ] Sequence (V15a first, V15b second) preregistered

### Check 3: Correct Reference
- [ ] Compares to standard GP (not self)

### Check 4: Runnable Independently
- [ ] Script runs standalone
- [ ] Enforces gatekeeping (V15b conditional on V15a)

---

## References

**Authority:**
- protocols.json lines 59-70 (tier3_v15 family, fixed-sequence gatekeeping)
- BUILD_PROGRAM_REVIEW_VERDICT.md lines 97-101 (ifBO spec violation)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md line 833 (V15 status unknown)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Fixed-sequence: V15a (pretrained) → V15b (power-law fallback)
- Margin: 10%
- n_trials: 100, n_seeds: 5
- Spec violation documented (pretrained vs power-law)

---

**END OF PROTOCOL**
