# Traceability Matrix v1.0

**Date:** 2026-09-09  
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 1 Day 4-6  
**Purpose:** Map LaTeX specifications → implementation → tests → validations  

---

## Matrix Structure

Each entry maps:
- **LaTeX Reference:** Section, equation, algorithm line in hpo-survey/
- **Claim/Requirement:** Exact text or mathematical specification
- **Implementation:** File:line in hponas/
- **Unit Test:** File:line in tests/unit/
- **Integration Test:** File:line in tests/integration/
- **Validation:** V01-V15 campaign ID
- **Status:** ✓ match / ❌ violation / ⚠️ missing
- **Notes:** Additional context, known issues

---

## Tier 0: Baseline Methods

### Random Search

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/03-model-free.tex:73-88 |
| **Claim** | "Uniform random sampling from search space, seed-deterministic" |
| **Implementation** | hponas/searchers/random_searcher.py:11-46 (RandomSearcher class) |
| **Unit Test** | tests/unit/test_random_searcher.py:50-70 (test_random_deterministic_with_seed) |
| **Integration Test** | tests/integration/test_study_baseline.py:15-30 (test_random_study) |
| **Validation** | V04-T0 (Random vs Sobol baseline floor) |
| **Status** | ✓ MATCH |
| **Notes** | Implementation verified Phase 1 Day 1, 19 unit tests passing, 97% coverage |

### Sobol Quasi-Random

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/03-model-free.tex:51-72 |
| **Claim** | "Quasi-random low-discrepancy sequence using scipy.stats.qmc.Sobol" |
| **Implementation** | hponas/searchers/random_searcher.py:49-159 (SobolSearcher class) |
| **Unit Test** | tests/unit/test_random_searcher.py:135-160 (test_sobol_better_coverage) |
| **Integration Test** | tests/integration/test_study_baseline.py:50-75 (test_sobol_study) |
| **Validation** | V04-T0 (Sobol beats Random on benchmark) |
| **Status** | ✓ MATCH |
| **Notes** | Implementation verified Phase 1 Day 1, log-scale supported, gap variance test passing |

### GP+qLogEI Baseline

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/04-bayesian.tex:Section 3.1 "Baseline Methods" |
| **Claim** | "Gaussian Process with Matérn 5/2 kernel, q-Expected Improvement with log transform" |
| **Implementation** | hponas/searchers/gp_searcher.py:1-205 (GPSearcher class) |
| **Unit Test** | tests/unit/test_gp_searcher.py:1-366 (20 tests, 99% coverage) |
| **Integration Test** | tests/integration/test_study_gp.py:1-197 (8 tests) |
| **Validation** | V01 (Vendor parity vs BoTorch) |
| **Status** | ✓ MATCH (after Phase 0 fixes) |
| **Notes** | Phase 0 recovery: fixed NotImplementedError, trial mapping, Y_train shape. FIXED: _prepare_training_data() implemented, RNG serialization fixed |

---

## Tier 0: Executors

### LocalExecutor

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md:98-122 (interface contract) |
| **Claim** | "Synchronous/async local execution with error handling: NaN, inf, exceptions, timeouts" |
| **Implementation** | hponas/executors/local_executor.py:1-149 (LocalExecutor class) |
| **Unit Test** | tests/unit/test_local_executor.py:1-366 (23 tests, 95% coverage) |
| **Integration Test** | tests/integration/test_study_baseline.py (uses LocalExecutor) |
| **Validation** | Contract tests (W2.3) |
| **Status** | ✓ MATCH |
| **Notes** | Phase 1 Day 2 verified, sync/async modes operational, error capture working |

### RayExecutor

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md:124-147 (distributed execution contract) |
| **Claim** | "Distributed Ray execution with fault tolerance: retry failed trials, handle worker crashes" |
| **Implementation** | hponas/executors/ray_executor.py:1-255 (RayExecutor class) |
| **Unit Test** | tests/unit/test_ray_executor_tier0.py:1-366 (24 tests, 84% coverage) |
| **Integration Test** | ⚠️ MISSING (Study-level Ray integration test) |
| **Validation** | Contract tests (W2.3) |
| **Status** | ✓ MATCH (after Phase 1 Day 3 fixes) |
| **Notes** | Phase 1 Day 3 fixes: contract violation (dict→Result), retry logic implemented, dead code removed. Uncovered: import guard (64-65), remote worker body (211-230), shutdown exception (252-253) |

---

## Tier 0: Workloads

### rl_routine (Brax Ant)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/09-workloads.tex + BUILD_PROGRAM_v3.md:149-179 |
| **Claim** | "9-knob RL policy search space on Brax Ant: width, depth, activation, optimizer, lr, batch_size, dropout, weight_decay, lr_schedule" |
| **Implementation** | workloads/rl_routine.py:1-250 (rl_routine function) |
| **Unit Test** | ⚠️ MISSING (unit test for rl_routine interface) |
| **Integration Test** | ⚠️ MISSING (Study + rl_routine end-to-end) |
| **Validation** | V05 (workload correctness), V14 (day-one walk seed isolation) |
| **Status** | ✓ MATCH (after Phase 0 brax upgrade) |
| **Notes** | Phase 0 fix: upgraded brax from GitHub source for JAX 0.11.1 compat, fixed inference API to provide key_sample. JAX_AVAILABLE=True, workload functional |

---

## Tier 1: Core Methods

### TPE (Tree-structured Parzen Estimator)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/04-bayesian.tex (TPE section) |
| **Claim** | "Tree-structured Parzen Estimator using Optuna backend" |
| **Implementation** | hponas/legacy_searchers.py:150-245 (TPESearcher class, OLD API) |
| **Unit Test** | ⚠️ MISSING (no Tier 0 TPE tests) |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V01 (Vendor parity: hponas.TPE vs Optuna.TPE) |
| **Status** | ⚠️ MISSING (Tier 1 task T1.1, not yet implemented in new API) |
| **Notes** | OLD API exists in legacy_searchers.py, needs migration to hponas/searchers/ package for Tier 1 |

### ASHA (Asynchronous Successive Halving)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/05-multifidelity.tex (ASHA algorithm) |
| **Claim** | "Asynchronous successive halving with geometric rung spacing, promotion on top-K" |
| **Implementation** | ⚠️ NOT IMPLEMENTED (Tier 1 task T1.2) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V06 (ASHA vs median stopping) |
| **Status** | ⚠️ MISSING (Tier 1 core, 3 eng-days) |
| **Notes** | Scheduler interface needs definition, ASHA is Tier 1 dependency for MO-ASHA |

### MO-ASHA (Multi-objective ASHA)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/07-multiobjective.tex + 05-multifidelity.tex |
| **Claim** | "Multi-objective variant of ASHA with hypervolume-based promotion" |
| **Implementation** | ⚠️ NOT IMPLEMENTED (Tier 1 task T1.3) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V07 (MO-ASHA early stopping quality) |
| **Status** | ⚠️ MISSING (Tier 1 core, 2 eng-days, depends on T1.2) |
| **Notes** | Requires ASHA base + multi-objective promotion logic |

### qLogNEHVI (Multi-objective Bayesian Optimization)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/07-multiobjective.tex (qLogNEHVI algorithm) |
| **Claim** | "BoTorch-based multi-objective BO with log expected hypervolume improvement" |
| **Implementation** | hponas/searchers_mo.py:60-350 (qLogNEHVISearcher class, OLD API) |
| **Unit Test** | ⚠️ MISSING (no unit tests for qLogNEHVI) |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V09 (qLogNEHVI vs Chebyshev vs NSGA-II) |
| **Status** | ✓ IMPLEMENTATION EXISTS (Phase 0 import fix), ⚠️ TESTS MISSING |
| **Notes** | OLD API in searchers_mo.py functional (V09 validation passing), needs migration to new API + unit tests for Tier 1 |

---

## Tier 1: Priors & Transfer Learning

### πBO (Prior-weighted Bayesian Optimization)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/08-priors-transfer.tex (πBO algorithm) |
| **Claim** | "Prior-guided BO: multiply acquisition function by prior weight, NOT GP mean" |
| **Implementation** | hponas/legacy_searchers.py or similar (location TBD) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V15 (Prior encoding validation) |
| **Status** | ❌ VIOLATION - "Uses GP mean as weight instead of acquisition function value" |
| **Notes** | **KNOWN SPECIFICATION VIOLATION** per BUILD_PROGRAM_REVIEW_VERDICT.md line 66. Must fix: change from GP mean → acquisition multiplier. Tier 1 task T1P.1 (3d) |

### PriorBand (Prior-aware Successive Halving)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/08-priors-transfer.tex (PriorBand algorithm) |
| **Claim** | "Prior-guided ASHA: use portfolio sampler (randomized weighted selection), NOT top-K" |
| **Implementation** | hponas/searchers_priorband.py (location TBD) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V11 (PriorBand effectiveness) |
| **Status** | ❌ VIOLATION - "Uses top-K promotion instead of portfolio sampler" |
| **Notes** | **KNOWN SPECIFICATION VIOLATION** per BUILD_PROGRAM_REVIEW_VERDICT.md line 67. Must fix: change from top-K → randomized weighted selection. Tier 1 task T1P.2 (3d) |

### ifBO (Iterative Feature Bayesian Optimization)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/08-priors-transfer.tex (ifBO section) |
| **Claim** | "Transfer learning with pretrained surrogate model, NOT custom power-law" |
| **Implementation** | ⚠️ NOT IMPLEMENTED or WRONG (location TBD) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | ⚠️ TBD (no validation defined yet) |
| **Status** | ❌ VIOLATION - "Builds custom power-law model instead of using pretrained surrogate" |
| **Notes** | **KNOWN SPECIFICATION VIOLATION** per BUILD_PROGRAM_REVIEW_VERDICT.md line 68. Must fix: use pretrained surrogate. Tier 1 task T1P.3 (4d) |

### Warm-start Transfer Learning

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/08-priors-transfer.tex (RGPE section) |
| **Claim** | "Query ranked/quantile samples FIRST, build RGPE only AFTER query" |
| **Implementation** | hponas/warm_start.py (location TBD) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V13 (Warm-start effectiveness) |
| **Status** | ❌ VIOLATION - "Builds RGPE immediately instead of querying first" |
| **Notes** | **KNOWN SPECIFICATION VIOLATION** per BUILD_PROGRAM_REVIEW_VERDICT.md line 69. Must fix: ranked query → RGPE build. Tier 1 task T1P.4 (3d) |

---

## Tier 1: Advanced Methods

### TuRBO (Trust Region Bayesian Optimization)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/04-bayesian.tex (TuRBO local modeling) |
| **Claim** | "Trust region BO with local GP models, adaptive trust region sizing" |
| **Implementation** | ⚠️ NOT IMPLEMENTED (Tier 1 task T1.5) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V11 (TuRBO local trust region behavior) |
| **Status** | ⚠️ MISSING (Tier 1 core, 5 eng-days) |
| **Notes** | Requires local GP + trust region logic, GPU validation planned |

### Chebyshev Scalarization

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/07-multiobjective.tex (scalarization baseline) |
| **Claim** | "Multi-objective scalarization using Chebyshev distance with random weights" |
| **Implementation** | hponas/searchers_mo.py:400-550 (ChebyshevSearcher, OLD API) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V09 (Chebyshev vs qLogNEHVI comparison) |
| **Status** | ✓ IMPLEMENTATION EXISTS (Phase 0 import fix), ⚠️ TESTS MISSING |
| **Notes** | Used in V09 validation (passing), needs migration + unit tests for Tier 1 task T1.6 (2d) |

### NSGA-II

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/07-multiobjective.tex (evolutionary MO baseline) |
| **Claim** | "Non-dominated Sorting Genetic Algorithm II for multi-objective optimization" |
| **Implementation** | hponas/searchers_mo.py:600-860 (NSGAIISearcher, OLD API) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V09 (NSGA-II vs qLogNEHVI comparison) |
| **Status** | ✓ IMPLEMENTATION EXISTS (Phase 0 import fix), ⚠️ TESTS MISSING |
| **Notes** | Used in V09 validation (passing), needs migration + unit tests for Tier 1 task T1.7 (2d) |

### EI-per-cost

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/08-priors-transfer.tex roadmap-12 (cost-aware BO) |
| **Claim** | "Cost-aware BO: divide acquisition by predicted cost^T with temperature annealing" |
| **Implementation** | hponas/searchers_cost.py:1-432 (CostAwareSearcher, OLD API) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V12 (EI-per-cost efficiency validation) |
| **Status** | ✓ IMPLEMENTATION EXISTS (Phase 0 import fix), ⚠️ TESTS MISSING |
| **Notes** | OLD API functional, needs migration + unit tests for Tier 1 task T1.8 (3d) |

---

## Tier 2: Population & Advanced

### BG-PBT (Population-based Training)

| Field | Value |
|-------|-------|
| **LaTeX Reference** | hpo-survey/sections/06-population.tex (PBT algorithm) |
| **Claim** | "Population-based training with exploit/explore dynamics" |
| **Implementation** | ⚠️ NOT IMPLEMENTED (Tier 2 task T2.1) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | V04-T1 (CONDITIONAL - PBT effectiveness) |
| **Status** | ⚠️ MISSING (Tier 2, 8 eng-days, CONDITIONAL on V04-T1 resolution) |
| **Notes** | Depends on V04-T1 passing, population line demotion triggered by V04-T1 failure |

### Mixed-space TuRBO

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 2 scope |
| **Claim** | "TuRBO extended to categorical + continuous hyperparameters" |
| **Implementation** | ⚠️ NOT IMPLEMENTED (Tier 2 task T2.2) |
| **Unit Test** | ⚠️ MISSING |
| **Integration Test** | ⚠️ MISSING |
| **Validation** | ⚠️ TBD |
| **Status** | ⚠️ MISSING (Tier 2, 5 eng-days) |
| **Notes** | Extension of T1.5 TuRBO to mixed search spaces |

---

## Validation Protocol Traceability

### V01: Vendor Parity

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 remediation |
| **Claim** | "hponas.GP matches BoTorch.GP, hponas.TPE matches Optuna.TPE" |
| **Implementation** | validation/v01_wrapper_parity.py |
| **Test Protocol** | validation/protocols/v01_protocol.md (to be created Week 3) |
| **Status** | ❌ NEEDS FIX - "Current V01 compares two internal implementations, not vendor" |
| **Notes** | Week 3 task W3.2 (1d): Fix to compare against declared vendors, not internal |

### V02: State Replay

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 remediation |
| **Claim** | "Deterministic save/load/replay: resume from checkpoint produces identical results" |
| **Implementation** | validation/v02_state_replay.py |
| **Test Protocol** | validation/protocols/v02_protocol.md (to be created Week 3) |
| **Status** | ⚠️ MISSING - "Not implemented" |
| **Notes** | Week 3 task W3.3 (3d): Implement deterministic replay test |

### V03: Mutation Testing

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 remediation + Approval Checklist Item 8 |
| **Claim** | "Mutation score ≥0.9 on searcher/scheduler core logic" |
| **Implementation** | validation/v03_mutation_testing.py |
| **Test Protocol** | validation/protocols/v03_protocol.md (to be created Week 3) |
| **Status** | ⚠️ MISSING - "No mutation tests exist" |
| **Notes** | Week 3 task W3.4 (3d): Implement mutmut-based mutation testing |

### V04-T0: Baseline Floor

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 gate criterion |
| **Claim** | "GP+qLogEI beats Sobol by ≥5% on Branin (preregistered threshold)" |
| **Implementation** | validation/v04_t0_baseline_floor.py |
| **Test Protocol** | validation/protocols/v04_t0_protocol.md (to be created Week 3) |
| **Status** | ❌ NEEDS RE-RUN - "Post-hoc tuned threshold, needs preregistration" |
| **Notes** | Week 3 task W3.5 (2d): Re-run with preregistered 5% threshold + correct impl |

### V04-T1: Population Line

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 1 gate criterion |
| **Claim** | "BG-PBT effectiveness validation" |
| **Implementation** | validation/v04_performance_check.py (existing, FAILED) |
| **Test Protocol** | validation/protocols/v04_t1_protocol.md (needs power analysis) |
| **Status** | ❌ FAILED - "Underpowered, demotion rule triggered" |
| **Notes** | Week 2 task W2.6 (2d): Investigate failure (GP floor violation or test bug). Tier 2 CONDITIONAL on resolution |

### V05: Workload Correctness

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 rl_routine requirement |
| **Claim** | "Real rl_routine workload (Brax Ant) produces valid results" |
| **Implementation** | validation/v05_log_warping.py |
| **Test Protocol** | validation/protocols/v05_protocol.md (to be created Week 3) |
| **Status** | ✓ FUNCTIONAL (after Phase 0 brax upgrade) - ⚠️ NEEDS RE-RUN |
| **Notes** | Week 3 task W3.6 (1d): Re-run V05 with real rl_routine (not proxy). Phase 0: upgraded brax, workload operational |

### V06: ASHA vs Median Stopping

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 1 ASHA validation |
| **Claim** | "ASHA early stopping quality vs median stopping baseline" |
| **Implementation** | validation/v06_asha_vs_median.py (passing per TIER1_GATE_STATUS.md) |
| **Test Protocol** | validation/protocols/v06_protocol.md (to be created Week 3) |
| **Status** | ✓ PASSED (per prior gate report) |
| **Notes** | Tier 1 task T1.9 (2d): Re-run after ASHA implementation (T1.2). GPU: A100 x1 x3d |

### V09: qLogNEHVI vs Scalarization

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 1 MO validation |
| **Claim** | "qLogNEHVI beats Chebyshev and NSGA-II on hypervolume" |
| **Implementation** | validation/v09_qlogNEHVI_vs_scalarization.py (passing after Phase 0 fix) |
| **Test Protocol** | validation/protocols/v09_protocol.md (to be created Week 3) |
| **Status** | ✓ PASSED (Phase 0 verification: qLogNEHVI beats both baselines, p<0.05) |
| **Notes** | Multi-seed validation operational. Tier 1 task T1.12 (2d): Re-run after new API migration |

### V14: Day-one Walk

| Field | Value |
|-------|-------|
| **LaTeX Reference** | BUILD_PROGRAM_v3.md Tier 0 seed isolation requirement |
| **Claim** | "rl_routine seed isolation: protected test seeds never reach searcher" |
| **Implementation** | validation/v14_day_one_walk.py |
| **Test Protocol** | validation/protocols/v14_protocol.md (to be created Week 3) |
| **Status** | ✓ FUNCTIONAL (after Phase 0 brax upgrade) - ❌ NEEDS RE-RUN - "Vacuous: zero trial budgets" |
| **Notes** | Week 3 task W3.7 (0.5d): Re-run with non-zero trial budgets |

---

## Summary Statistics

### Coverage by Status

- **✓ MATCH:** 6 items (Random, Sobol, GP+qLogEI, LocalExecutor, RayExecutor, rl_routine)
- **✓ IMPLEMENTATION EXISTS, ⚠️ TESTS MISSING:** 4 items (qLogNEHVI, Chebyshev, NSGA-II, EI-per-cost)
- **❌ VIOLATION:** 4 items (πBO, PriorBand, ifBO, Warm-start) - ALL DOCUMENTED
- **⚠️ MISSING:** 6 items (TPE, ASHA, MO-ASHA, TuRBO, BG-PBT, Mixed-space TuRBO)

### Coverage by Tier

- **Tier 0:** 6/6 implemented, 4/6 fully tested
- **Tier 1 Core:** 4/7 implemented (OLD API), 0/7 tested
- **Tier 1 Priors/Transfer:** 0/4 correct (all have spec violations)
- **Tier 2:** 0/2 implemented

### Validation Protocol Status

- **Passing:** V06 ✓, V09 ✓
- **Functional, needs re-run:** V05 ✓, V14 ✓
- **Needs fix:** V01 ❌, V04-T0 ❌, V04-T1 ❌
- **Not implemented:** V02 ⚠️, V03 ⚠️

---

## Known Specification Violations (Complete List)

Per BUILD_PROGRAM_REVIEW_VERDICT.md lines 66-70, the following violations are DOCUMENTED:

1. **πBO:** Uses GP mean as weight → MUST use acquisition function value as multiplier
2. **PriorBand:** Uses top-K promotion → MUST use portfolio sampler (randomized weighted selection)
3. **ifBO:** Builds custom power-law model → MUST use pretrained surrogate model
4. **Warm-start:** Builds RGPE immediately → MUST query ranked/quantile samples first

**Action:** Fix during Tier 1 scope correction (Week 4 Day 1-2, tasks T1P.1-T1P.4)

BUILD_PROGRAM_REVIEW_VERDICT.md mentions "11 more" violations beyond these 4, but they are not explicitly listed in available documents. Week 1 Day 4-6 task is to DOCUMENT all 15+, so further investigation is needed.

---

## Next Steps

1. **Complete this traceability matrix:** Investigate remaining 11 specification violations mentioned in BUILD_PROGRAM_REVIEW_VERDICT.md line 68
2. **Week 3 Day 1-3:** Create validation protocol files (validation/protocols/v{01-15}_protocol.md)
3. **Week 3 Day 4-5:** Create test pyramid document (TEST_PYRAMID_v1.md)
4. **Week 4 Day 1-2:** Amend BUILD_PROGRAM_v3.md with traceability corrections

---

**Document Status:** DRAFT (Week 1 Day 4 in progress)  
**Next Update:** Completion of remaining violation investigation  
**Satisfies:** Approval Checklist Item 2 (partial), Item 5 (partial)
