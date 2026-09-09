# V01 Protocol: Vendor Parity

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 0  

---

## Claim

Our implementations match reference vendor implementations on standard benchmarks.

**Specific claims:**
1. Our Sobol implementation matches scipy.stats.qmc.Sobol distribution
2. Our TPE wrapper matches Optuna TPE performance
3. Our GP wrapper matches BoTorch GP performance

---

## Hypothesis

### H0 (Null Hypothesis)
Our implementation and vendor reference implementation produce statistically different distributions of optimization outcomes.

### H1 (Alternative Hypothesis)
Our implementation and vendor reference implementation produce statistically equivalent distributions of optimization outcomes.

### Test Type
**Equivalence test** (TOST - Two One-Sided Tests) for demonstrating matching behavior.

---

## Preregistration

### Tasks
**Benchmark:** 2D quadratic synthetic function (x0, x1 ∈ [0,1])
- Objective: f(x0, x1) = -(x0 - 0.3)² - (x1 - 0.7)²
- Global optimum: (0.3, 0.7)
- Used for TPE and GP wrapper tests

**Benchmark:** Uniform distribution test (Sobol only)
- d-dimensional unit hypercube [0,1]^d
- d = 5 dimensions
- Tests distributional properties, not optimization

**Held-out requirement:** These are synthetic benchmarks designed specifically for parity testing. Real workloads tested in V05.

### Seeds
- Sobol distributional test: seed=42
- TPE wrapper test: seed=42
- GP wrapper test: seed=43

### Margin (Equivalence Bound)

**For Sobol distributional test:**
- KS statistic < 0.05 (distributions are close)
- p-value > 0.05 (cannot reject same distribution)

**For wrapper parity tests (TPE, GP):**
- Equivalence margin δ = 0.10 (10% difference acceptable)
- TOST with α = 0.05 (two one-sided tests at 0.025 each)
- Justification: 10% performance difference is operationally negligible for a wrapper

**Fallback (if TOST not implemented):**
- KS statistic < 0.10 and p-value > 0.05
- Note: This is weaker than proper equivalence test; upgrade to TOST required per Checklist Item 7

### Alpha
- α = 0.05 (two-sided for KS test, one-sided per TOST direction)
- No Bonferroni correction needed (separate benchmarks, not multiple comparisons on same data)

### Power
- Target: 0.80
- Sample size calculation: Not applicable for distributional parity test (deterministic comparison)
- For wrapper tests: n_trials=30 provides reasonable power to detect δ=0.10 difference

### Sample Size

**Sobol distributional test:**
- n_samples = 1000 per dimension
- n_dims = 5
- Total samples = 1000

**TPE wrapper test:**
- n_trials = 30
- n_seeds = 1 (deterministic given seed)

**GP wrapper test:**
- n_trials = 30
- n_seeds = 1

### Analysis

**Sobol test:**
- Per-dimension Kolmogorov-Smirnov two-sample test
- Compare our_samples[dim] vs scipy_samples[dim]
- Report: max(KS_statistic) across dimensions, min(p_value) across dimensions

**Wrapper tests:**
- Kolmogorov-Smirnov two-sample test on final score distributions
- Compare our_scores vs vendor_scores after n_trials
- Future: Upgrade to TOST equivalence test (per Checklist Item 7)

---

## Decision States

### PASS
**All of the following must be true:**
1. Sobol test: max_KS < 0.05 AND min_p > 0.05
2. TPE test: KS < 0.10 AND p > 0.05 (or TOST confirms equivalence)
3. GP test: KS < 0.10 AND p > 0.05 (or TOST confirms equivalence)
4. V16 audit: non-vacuous, no post-hoc tuning, correct reference, runnable independently

### FAIL
**Any of the following:**
1. Sobol test: max_KS ≥ 0.05 OR min_p ≤ 0.05
2. TPE test: KS ≥ 0.10 OR p ≤ 0.05 (or TOST rejects equivalence)
3. GP test: KS ≥ 0.10 OR p ≤ 0.05 (or TOST rejects equivalence)
4. V16 audit fails
5. Vendor library not available (blocker)

### INCONCLUSIVE
**Any of the following:**
1. GP wrapper not yet implemented (partial pass: Sobol + TPE only)
2. V16 audit detects post-hoc threshold tuning
3. Test runs on zero trials (vacuous pass caught by V16)

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v01_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v01_results.json
- **Format:** JSON with structure:
  ```json
  {
    "validation_id": "v01",
    "timestamp": "ISO8601",
    "sobol_test": {"max_ks": float, "min_p": float, "passed": bool, "per_dimension": [...]},
    "tpe_test": {"ks": float, "p": float, "passed": bool, "our_mean": float, "ref_mean": float},
    "gp_test": {"ks": float, "p": float, "passed": bool, "our_mean": float, "ref_mean": float},
    "overall_passed": bool,
    "v16_audit": {"passed": bool, "checks": [...]}
  }
  ```
- **Write policy:** Write once, never modified

### Log
- **Path:** validation/results/v01_log.txt
- **Format:** Append-only text log
- **Content:** Per-trial details, timestamps, warnings

---

## Implementation

### Scripts
- **Main:** validation/v01_sobol_parity.py (Sobol distributional test)
- **Main:** validation/v01_wrapper_parity.py (TPE/GP wrapper tests)
- **Validator:** validation/validators/v01_validator.py (V16-compliant validator)

### Validator Interface
```python
class V01Validator:
    def audit(self) -> AuditReport:
        """Run V16 audit checks."""
        # Check 1: Non-vacuity (n_trials > 0, n_samples > 0)
        # Check 2: No post-hoc tuning (thresholds match protocol)
        # Check 3: Correct reference (scipy.qmc.Sobol, optuna.samplers.TPESampler, botorch)
        # Check 4: Runnable independently (no manual intervention)
        ...
```

### Dependencies
- scipy>=1.9.0 (qmc.Sobol with scramble support)
- optuna>=3.0.0 (TPESampler)
- botorch>=0.8.0 (GP reference, when implemented)

---

## Known Issues

### Issue 1: Tautological Comparison (FIXED)
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md line 66 identified V01 as tautological (comparing to self).

**Resolution:** Protocol now compares to external vendor references:
- Sobol: scipy.stats.qmc.Sobol
- TPE: optuna.samplers.TPESampler
- GP: botorch (when implemented)

**Status:** Fixed in this protocol version

### Issue 2: GP Wrapper Not Implemented
**Problem:** validation/v01_wrapper_parity.py line 141 has placeholder for GP test.

**Resolution:** V01 can pass with partial coverage (Sobol + TPE) if GP marked INCONCLUSIVE.

**Blocker for Tier 0 gate:** No (partial pass acceptable if Sobol + TPE pass)

### Issue 3: KS Test vs TOST
**Problem:** Current implementation uses KS two-sample test, not proper equivalence test.

**Resolution:** Checklist Item 7 requires TOST. Current protocol documents both:
- Current: KS < 0.10, p > 0.05 (weak equivalence claim)
- Required: TOST with δ=0.10, α=0.05 (proper equivalence)

**Action:** Upgrade analysis to TOST during Week 3 protocol repair.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] Sobol test: n_samples > 0, n_dims > 0
- [ ] TPE test: n_trials > 0
- [ ] GP test: n_trials > 0 (or marked not implemented)
- [ ] Validator fails with clear error if zero-input detected

### Check 2: No Post-Hoc Tuning
- [ ] Sobol thresholds (0.05, 0.05) match protocol exactly
- [ ] Wrapper thresholds (0.10, 0.05) match protocol exactly
- [ ] No command-line override of thresholds
- [ ] Thresholds hardcoded or read from this immutable protocol file

### Check 3: Correct Reference
- [ ] Sobol: compares to scipy.stats.qmc.Sobol, not internal implementation
- [ ] TPE: compares to optuna.samplers.TPESampler, not internal TPE
- [ ] GP: compares to botorch, not internal GP (when implemented)
- [ ] No self-comparison (tautological test)

### Check 4: Runnable Independently
- [ ] `python validation/v01_sobol_parity.py` runs without manual intervention
- [ ] `python validation/v01_wrapper_parity.py` runs without manual intervention
- [ ] All parameters from protocol (n_samples, n_trials, seeds, thresholds)
- [ ] Results written to validation/results/v01_results.json atomically

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md lines 66-67 (tautological issue)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 716-720 (V01 repair specification)

**Implementation:**
- validation/v01_sobol_parity.py (Sobol distributional test)
- validation/v01_wrapper_parity.py (TPE/GP wrapper tests)

**Related Protocols:**
- V05 (real workload performance, uses V01 implementations)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial preregistered protocol
- Fixed tautological comparison (now uses scipy/optuna/botorch references)
- Documented TOST upgrade path for Checklist Item 7
- Added V16 audit checklist
- Preregistered thresholds: Sobol (KS<0.05, p>0.05), Wrappers (KS<0.10, p>0.05)
- Preregistered sample sizes: Sobol n=1000, Wrappers n_trials=30
- Preregistered seeds: 42, 42, 43

---

**END OF PROTOCOL**
