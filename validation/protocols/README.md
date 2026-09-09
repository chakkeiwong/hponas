# Validation Protocols

**Created:** 2026-09-09  
**Status:** Week 3 Day 1-2 protocols (V01-V14 complete)  
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 3 Day 1-3  

---

## Overview

This directory contains preregistered validation protocols for the HPO-NAS build program. Each protocol follows the template specified in the master recovery program and includes:

1. **Claim** - What the validation demonstrates
2. **Hypothesis** - Statistical framework (H0/H1, test type)
3. **Preregistration** - Tasks, seeds, margins, alpha, power, sample size (immutable)
4. **Decision States** - PASS/FAIL/INCONCLUSIVE criteria
5. **Immutable Artifacts** - Protocol file, results files, logs
6. **Implementation** - Scripts, dependencies
7. **V16 Audit Checklist** - Non-vacuity, no post-hoc tuning, correct reference, runnable independently

---

## Validation Suite Status

### Tier 0 (Gate: Week 8)

| ID | Name | Status | Protocol | Issues |
|----|------|--------|----------|--------|
| V01 | Vendor Parity | To run | [v01_protocol.md](v01_protocol.md) | Fixed tautological comparison |
| V02 | State Replay | To implement | [v02_protocol.md](v02_protocol.md) | Event log infrastructure needed |
| V03 | Mutation Testing | To implement | [v03_protocol.md](v03_protocol.md) | Test suite prerequisite |
| V04-T0 | Random Baseline Floor | To run | [v04_t0_protocol.md](v04_t0_protocol.md) | Fixed post-hoc tuning |
| V05 | Real Workload | To implement | [v05_protocol.md](v05_protocol.md) | Brax/JAX dependency |
| V14 | Day-One Walk | To run | [v14_protocol.md](v14_protocol.md) | Fixed vacuity |

### Tier 1 (Gate: Week 12)

| ID | Name | Status | Protocol | Issues |
|----|------|--------|----------|--------|
| V04-T1 | Sobol vs Random | ❌ FAILED | [v04_t1_protocol.md](v04_t1_protocol.md) | Replication protocol, 2.42% improvement |
| V06 | ASHA Efficiency | ✅ PASSED | [v06_protocol.md](v06_protocol.md) | 0.17% gap, 18.5% compute |
| V09 | qLogNEHVI vs Scalarization | ✅ PASSED | [v09_protocol.md](v09_protocol.md) | 8.2% improvement |
| V11a | Folklore Prior Helps | ⚠️ INCONCLUSIVE | [v11_protocol.md](v11_protocol.md) | Undersized, πBO/PriorBand demoted |
| V11b | Wrong Prior Recovers | ⚠️ INCONCLUSIVE | [v11_protocol.md](v11_protocol.md) | Undersized, πBO/PriorBand demoted |

### Tier 2 (Gate: Week 30)

| ID | Name | Status | Protocol | Issues |
|----|------|--------|----------|--------|
| V10 | MO-ASHA Rung Correlation | ⏸️ DEFERRED | [v10_protocol.md](v10_protocol.md) | Enhanced requirements |
| V13 | Warm-Start Effectiveness | ⏸️ DEFERRED | [v13_protocol.md](v13_protocol.md) | Not implemented, spec violation |

### Tier 3 / Distributed-Beta (Electives)

| ID | Name | Status | Protocol | Issues |
|----|------|--------|----------|--------|
| V07 | GPU Campaign Capacity | To audit | TBD | Reconcile 3.8 GPU-weeks |
| V08 | BG-PBT Performance | TBD | TBD | Flagship campaign |
| V12 | Mixed-Space TuRBO | TBD | TBD | Depends on V04-T1 |
| V15a | ifBO Pretrained Surrogate | TBD | TBD | Spec violation documented |
| V15b | ifBO Fallback | TBD | TBD | Fixed-sequence pair |

### Meta-Validation

| ID | Name | Status | Protocol | Issues |
|----|------|--------|----------|--------|
| V16 | Validator Audit | To implement | TBD | Enforced at all gates |

---

## Protocol Repair Summary (Week 3 Day 1-3)

### Fixed Issues

1. **V01 (Tautological):** Now compares to scipy/optuna/botorch, not self
2. **V04-T0 (Post-hoc tuning):** Threshold preregistered at 5%
3. **V04-T1 (Underpowered):** Replication protocol with increased sample size
4. **V06 (No repair needed):** PASSED, documented retroactively
5. **V09 (Single-seed):** Multi-seed campaign (10 seeds), PASSED
6. **V11 (Weak effects):** INCONCLUSIVE documented, demotion applied
7. **V14 (Vacuous):** Non-vacuity check added (n_trials > 0)

### Remaining Work

1. **V02, V03, V05:** Implementation blocked on dependencies (event log, test suite, Brax/JAX)
2. **V10, V13:** Deferred to Tier 2 per drift report
3. **V07, V08, V12, V15, V16:** Protocols to be created (Tier 3 / meta-validation)

---

## Preregistration Policy

**Per protocols.json and Checklist Item 6:**

1. **Tasks:** Held-out benchmarks, not training tasks
2. **Seeds:** Exact seeds listed, disjoint for pilot/confirmatory
3. **Margins:** Preregistered with justification
4. **Alpha:** Family-corrected (Holm-Bonferroni per gate)
5. **Power:** Target 0.80 (0.90 for high-stakes)
6. **Sample size:** From power analysis, max_sample rule
7. **Analysis:** Statistical test prespecified
8. **Decision states:** PASS/FAIL/INCONCLUSIVE criteria immutable

**Immutability:** Protocol files frozen before campaign starts. Thresholds, seeds, margins not adjusted after data collection.

---

## V16 Audit Protocol

Every validation must implement `--audit` mode checking:

1. **Non-vacuity:** Fails on structurally empty input (n_trials=0, n_seeds=0)
2. **No post-hoc tuning:** Thresholds match protocol exactly
3. **Correct reference:** Compares to declared vendor/baseline, not self
4. **Runnable independently:** Full protocol executes standalone without human intervention

**Gate enforcement:** V16 audit runs at every gate (Tier 0, 1, 2). Any V16 failure blocks gate passage.

---

## File Naming Convention

- **Protocol:** `v{XX}_protocol.md` (e.g., v01_protocol.md, v04_t1_protocol.md)
- **Implementation:** `validation/v{XX}_{name}.py` (e.g., v06_asha_efficiency.py)
- **Results:** `validation/results/v{XX}_results.json`
- **Log:** `validation/results/v{XX}_log.txt`
- **Validator:** `validation/validators/v{XX}_validator.py`

---

## References

**Authority:**
- BUILD_PROGRAM_REVIEW_VERDICT.md (12-item approval checklist)
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 3 Day 1-3 (protocol repair specification)
- protocols.json (validation register, policy, families)
- TIER1_GATE_STATUS.md (current validation status)

**Template:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 297-331 (protocol template)

---

**Last Updated:** 2026-09-09 (Week 3 Day 2)
