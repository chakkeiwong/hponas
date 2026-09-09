# V10 Protocol: MO-ASHA Rung Correlation

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 2 (deferred from Tier 1)  

---

## Claim

Early-rung drift correlates with final-rung drift in multi-objective multi-fidelity optimization, justifying early culling decisions.

**Operational requirement:** MO-ASHA promotions depend on early fidelity being predictive of final fidelity.

---

## Hypothesis

### H0 (Null Hypothesis)
Early-rung drift (fidelity r₁) does not correlate with final-rung drift (fidelity r_max).

### H1 (Alternative Hypothesis)
Spearman correlation ρ > 0.6 between early-rung and final-rung drift rankings.

### Test Type
**Superiority test** (one-sided) - correlation must exceed threshold.

---

## Preregistration

### Task
**Benchmark:** Multi-objective Hamiltonian with multi-fidelity
- Objectives: prediction_error, drift
- Fidelities: {0.1, 0.3, 1.0}
- Early rung: fidelity=0.1
- Final rung: fidelity=1.0

**Enhanced requirements (per BUILD_PROGRAM_REVIEW_VERDICT.md line 207):**
- Multiple seeds (not single-seed)
- Out-of-sample configurations (not training set)
- Gate on top-k recall, false-cull probability, regret (not just Spearman ρ)

### Seeds
**Preregistered seeds:** 0, 1, 2, 3, 4 (5 seeds)

### Margin
**Correlation threshold:** ρ > 0.6 (Spearman rank correlation)

**Enhanced thresholds:**
- Top-k recall: ≥0.90 (90% of final Pareto configs promoted)
- False-cull probability: ≤0.10 (10% max false culls)
- Regret: ≤0.05 (5% hypervolume loss from early culling)

### Alpha
α = 0.05 (one-sided test)

**Family correction:** V10 deferred to Tier 2, separate family from tier1_gate.

### Power
- Target: 0.80
- Method: Simulation under correlation distribution

### Sample Size
**Preregistered:**
- n_configs = 100 (configurations sampled)
- n_seeds = 5
- Each config evaluated at all fidelities

---

## Decision States

### PASS
**All of the following must be true:**
1. Spearman ρ > 0.6
2. Top-k recall ≥ 0.90
3. False-cull probability ≤ 0.10
4. Regret ≤ 0.05
5. p < 0.05

### FAIL
**Any of the following:**
1. ρ ≤ 0.6
2. Top-k recall < 0.90
3. False-cull probability > 0.10
4. Regret > 0.05

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.80 at max sample
2. Multi-fidelity workload not available

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v10_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v10_results.json

### Log
- **Path:** validation/results/v10_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v10_rung_correlation.py (to be created)
- **Validator:** validation/validators/v10_validator.py (V16-compliant)

### Dependencies
- hponas.schedulers (MO-ASHA)
- workloads.hamiltonian_mo (multi-fidelity)

---

## Known Issues

### Issue 1: Deferred to Tier 2
**Status:** BUILD_PROGRAM_DRIFT_REPORT.md line 31 deferred V10 to Week 30 (Tier 2).

**Reason:** Multi-seed, out-of-sample requirements need full implementation.

### Issue 2: Enhanced Requirements
**Problem:** BUILD_PROGRAM_REVIEW_VERDICT.md line 207 requires more than simple correlation.

**Resolution:** Protocol includes top-k recall, false-cull probability, regret metrics.

**Status:** To be implemented during Tier 2.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_configs > 0, n_seeds > 0
- [ ] All fidelities evaluated

### Check 2: No Post-Hoc Tuning
- [ ] Thresholds (ρ>0.6, recall≥0.90, etc.) preregistered

### Check 3: Correct Reference
- [ ] Compares early vs final fidelity on same configs

### Check 4: Runnable Independently
- [ ] Script runs without manual intervention

---

## References

**Authority:**
- TIER1_GATE_STATUS.md lines 89-104 (V10 deferred)
- BUILD_PROGRAM_REVIEW_VERDICT.md line 207 (enhanced requirements)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 789-796 (V10 repair)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Deferred to Tier 2 (Week 30)
- Enhanced requirements: top-k recall, false-cull, regret
- Multi-seed: 5 seeds
- n_configs: 100

---

**END OF PROTOCOL**
