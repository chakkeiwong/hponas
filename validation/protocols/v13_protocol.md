# V13 Protocol: Warm-Start Effectiveness

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 2 (deferred from Tier 1)  

---

## Claim

Warm-start transfer learning correctly vets failing configs, ranks survivors by ESS/gradient, and pilot agrees with reference posterior.

**Operational requirement:** Transfer learning must not promote known-bad configs or mis-rank good configs.

---

## Hypothesis

### H0 (Null Hypothesis)
Warm-start sampler promotes veto-failing configs or mis-ranks survivors.

### H1 (Alternative Hypothesis)
Warm-start sampler satisfies three criteria:
1. Zero veto-failing configs promoted
2. Survivors ranked by ESS/gradient (correlation ρ > 0.8)
3. Pilot posterior matches reference posterior (KL divergence < 0.1)

### Test Type
**Composite veto + correlation + calibration** - all three criteria must pass.

---

## Preregistration

### Task
**Benchmark:** Transfer learning scenario
- Source tasks: 3 related tasks with historical data
- Target task: New task, warm-started from source
- Configs: 100 candidate configs

**Veto criteria:**
- NaN objective
- Diverged training (gradient explosion)
- Out-of-bounds constraint violation

### Seeds
**Preregistered seeds:** 0, 1, 2, 3, 4 (5 seeds)

### Thresholds

**Criterion 1 (veto):** Zero veto-failing configs promoted (hard constraint)  
**Criterion 2 (ranking):** Spearman ρ > 0.8 between sampler rank and ESS/gradient rank  
**Criterion 3 (calibration):** KL divergence < 0.1 between pilot posterior and reference posterior

### Alpha
α = 0.05 (per criterion where applicable)

**Family correction:** V13 deferred to Tier 2, separate family.

### Power
- Target: 0.80
- Method: Simulation under transfer scenario

### Sample Size
**Preregistered:**
- n_configs = 100 (candidate pool)
- n_seeds = 5
- n_source_tasks = 3

---

## Decision States

### PASS
**All of the following must be true:**
1. Zero veto-failing configs promoted
2. Spearman ρ > 0.8 (ranking by ESS/gradient)
3. KL divergence < 0.1 (calibration)
4. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. Any veto-failing config promoted
2. ρ ≤ 0.8
3. KL divergence ≥ 0.1

### INCONCLUSIVE
**Any of the following:**
1. Transfer learning infrastructure not implemented
2. Reference posterior not available

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v13_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v13_results.json

### Log
- **Path:** validation/results/v13_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v13_warmstart_effectiveness.py (to be created)
- **Validator:** validation/validators/v13_validator.py (V16-compliant)

### Dependencies
- hponas.transfer (warm-start sampler)
- RGPE (Rank-weighted GP Ensemble)

---

## Known Issues

### Issue 1: Deferred to Tier 2
**Status:** BUILD_PROGRAM_DRIFT_REPORT.md line 34 deferred V13 to Week 30 (Tier 2).

**Reason:** "Sampler veto correctness deferred 18 weeks."

### Issue 2: Not Implemented
**Status:** No V13 implementation files found in validation/.

**Resolution:** To be implemented during Tier 2.

### Issue 3: Specification Violation
**Problem:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 105-109 document warm-start specification violation:
- WRONG: Build RGPE immediately
- RIGHT: Query ranked/quantile samples first, then build RGPE

**Resolution:** Fix implementation during Tier 2 execution per traceability matrix.

**Blocker:** V13 cannot run until warm-start implementation fixed.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_configs > 0, n_seeds > 0
- [ ] At least one veto criterion applied

### Check 2: No Post-Hoc Tuning
- [ ] Thresholds (ρ>0.8, KL<0.1) preregistered
- [ ] Veto criteria preregistered

### Check 3: Correct Reference
- [ ] Reference posterior defined and computed

### Check 4: Runnable Independently
- [ ] Script runs without manual intervention

---

## References

**Authority:**
- TIER1_GATE_STATUS.md lines 136-148 (V13 deferred)
- BUILD_PROGRAM_DRIFT_REPORT.md line 34 (18-week deferral)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 105-109 (specification violation)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 817-823 (V13 repair)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Deferred to Tier 2 (Week 30)
- Not yet implemented
- Specification violation documented (RGPE sequencing)
- Three criteria: veto, ranking, calibration

---

**END OF PROTOCOL**
