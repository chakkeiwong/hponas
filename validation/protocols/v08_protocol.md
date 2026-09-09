# V08 Protocol: BG-PBT Performance

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Preregistered  
**Tier:** 2 (conditional on V04-T1 fix)  

---

## Claim

BG-PBT (Backpropagation-Guided Population-Based Training) beats ASHA on population-suitable tasks, justifying flagship Tier 2 investment.

**Consequence:** BG-PBT is the largest campaign in the program. Failure wastes significant sunk cost.

---

## Hypothesis

### H0 (Null Hypothesis)
BG-PBT does not beat ASHA baseline on population-suitable tasks.

### H1 (Alternative Hypothesis)
BG-PBT beats ASHA by at least δ margin on population-suitable tasks.

### Test Type
**Superiority test** (one-sided) - BG-PBT must beat ASHA.

---

## Preregistration

### Task
**Benchmark:** Population-suitable RL task (TBD, requires V04-T1 Sobol fix)
- Multi-agent or population-based environment
- Benefit from sharing/mutation across population

**Baseline:** ASHA (multi-fidelity successive halving)

### Seeds
**Preregistered seeds:** TBD (at least 5 seeds)

### Margin
**Superiority margin:** δ = 0.10 (10% improvement required)

**Justification:** BG-PBT adds significant complexity (population management, backprop-guided mutations). 10% improvement justifies cost.

### Alpha
α = 0.05 (one-sided test)

**Family correction:** V08 is sole member of tier2_gate family (per protocols.json lines 40-45).
- No correction needed (m=1)

### Power
- **Target:** 0.90 (high target per protocols.json lines 82-84)
- **Rationale:** V08 is flagship campaign with highest sunk cost. False negative very expensive.
- **Method:** Simulation (not closed-form, per protocols.json line 85-86)

### Sample Size
**Preregistered:** TBD (power analysis after V04-T1 resolved)

**Conservative estimate:**
- n_trials = 200 per seed
- n_seeds = 5
- GPU cost: TBD (likely 3+ GPU-weeks, contributing to V07 capacity issue)

---

## Decision States

### PASS
**All of the following must be true:**
1. Improvement ≥ 10%
2. p < 0.05
3. Power ≥ 0.90
4. V16 audit: non-vacuous, threshold preregistered

### FAIL
**Any of the following:**
1. Improvement < 10%
2. p ≥ 0.05

**Consequence:** Remove BG-PBT from roadmap (sunk cost written off).

### INCONCLUSIVE
**Any of the following:**
1. Power < 0.90 at max sample
2. V04-T1 not fixed (BG-PBT depends on TuRBO/Sobol)

**Status:** V08 blocked until V04-T1 resolved.

---

## Immutable Artifacts

### Protocol (This File)
- **Path:** validation/protocols/v08_protocol.md
- **Status:** Immutable after campaign starts
- **Hash:** (git commit hash when frozen)

### Results
- **Path:** validation/results/v08_results.json

### Log
- **Path:** validation/results/v08_log.txt

---

## Implementation

### Scripts
- **Main:** validation/v08_bgpbt_performance.py (to be created)
- **Validator:** validation/validators/v08_validator.py (V16-compliant)

### Dependencies
- hponas.population (BG-PBT implementation)
- TuRBO (trust region, depends on V04-T1)
- Population-suitable RL environment

---

## Known Issues

### Issue 1: Blocked on V04-T1
**Status:** Per BUILD_PROGRAM_v2.md lines 252-256, BG-PBT depends on TuRBO, which depends on V04-T1.

**Resolution:** V08 cannot run until V04-T1 PASSED (Sobol vs random on real workload).

**Current V04-T1 status:** FAILED (2.42% improvement, p=0.2738). Replication protocol created.

### Issue 2: Largest Campaign
**Problem:** V08 is described as "largest campaign in the program" but size not yet determined.

**Resolution:** Week 4 Day 4 Tier 2 scope sizing determines n_trials, GPU requirements.

**Impact:** Contributes to V07 GPU capacity reconciliation issue.

### Issue 3: Population Task Not Defined
**Problem:** "Population-suitable task" not yet specified.

**Resolution:** Requires domain expert input to identify suitable benchmark.

**Status:** TBD during Tier 2 planning.

---

## V16 Audit Checklist

### Check 1: Non-Vacuity
- [ ] n_trials > 0, n_seeds > 0
- [ ] Both BG-PBT and ASHA run

### Check 2: No Post-Hoc Tuning
- [ ] Margin (10%) preregistered
- [ ] Task selected before campaign

### Check 3: Correct Reference
- [ ] Compares to ASHA baseline (not self)

### Check 4: Runnable Independently
- [ ] Script runs standalone

---

## References

**Authority:**
- protocols.json lines 40-45 (tier2_gate family, V08 as sole member)
- protocols.json lines 82-84 (high power target for V08)
- BUILD_PROGRAM_v2.md lines 252-256 (BG-PBT depends on TuRBO)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 833-838 (V15 as BG-PBT validation)

**Note:** V15 may be mislabeled V08 in some documents. This protocol follows tier2_gate structure.

---

## Changelog

**v1.0 - 2026-09-09**
- Initial protocol
- Blocked on V04-T1 (TuRBO dependency)
- High power target: 0.90
- Margin: 10%
- Largest campaign, GPU sizing TBD

---

**END OF PROTOCOL**
