# Test Pyramid v1.0

**Version:** 1.0  
**Created:** 2026-09-09  
**Status:** Active  
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Week 3 Day 4-5

---

## Overview

Three-layer test architecture balancing speed, coverage, and statistical rigor.

**Pyramid ratio:**
- Layer 1: ~80% of tests, <1% of runtime
- Layer 2: ~15% of tests, ~10% of runtime
- Layer 3: ~5% of tests, ~90% of runtime

**Philosophy:** Fast feedback loops at the bottom (unit/property/conformance), slower integration checks in the middle, expensive statistical campaigns at the top.

---

## Layer 1: Unit / Property / Conformance

**Purpose:** Verify individual functions, contracts, invariants

**Runtime:** Milliseconds to seconds  
**Frequency:** Every commit (CI)  
**Coverage target:** >80% line coverage  
**Count target:** 200-300 tests

### Directories

```
tests/unit/          # Unit tests for individual functions
tests/property/      # Property-based tests (hypothesis library)
tests/conformance/   # Contract conformance tests
```

### Examples

**Unit tests:**
- `test_gp_posterior()` - GP posterior mean/variance correct on synthetic data
- `test_acquisition_maximization()` - argmax within epsilon of known optimum
- `test_config_serialization()` - roundtrip serialization preserves value
- `test_sobol_sequence()` - Sobol generator produces expected first 10 points

**Property tests:**
- `test_gp_positive_definite()` - Covariance matrix always PD for random kernels
- `test_acquisition_monotonic()` - EI non-decreasing as uncertainty increases
- `test_search_space_bounds()` - Generated configs always within declared bounds

**Conformance tests:**
- `test_searcher_contract()` - All searchers implement Searcher interface
- `test_scheduler_contract()` - All schedulers implement Scheduler interface
- `test_acquisition_contract()` - All acquisitions implement Acquisition interface
- `test_kernel_contract()` - All kernels implement Kernel interface

### Current Status

**Week 2 conformance tests:** 6 tests created (searcher, scheduler, acquisition contracts)

**Known issues:**
- BUILD_PROGRAM_v2.md line 155 documents 6 broken R1 tests needing repair
- Unit test coverage audit needed (current coverage unknown)

### Acceptance Criteria

- [ ] >100 tests implemented
- [ ] >80% line coverage achieved
- [ ] All tests pass in <10 seconds total
- [ ] CI runs on every commit

---

## Layer 2: Integration / Recovery / Scale

**Purpose:** Verify component interactions, failure recovery, resource limits

**Runtime:** Seconds to minutes  
**Frequency:** Every PR (CI)  
**Coverage target:** All critical paths  
**Count target:** 50-100 tests

### Directories

```
tests/integration/   # Multi-component interactions
tests/recovery/      # Crash recovery, checkpoint resume
tests/scale/         # Large config spaces, long horizons, many workers
```

### Examples

**Integration tests:**
- `test_searcher_scheduler_interaction()` - Full optimization loop on Branin-Hoo
- `test_gp_acquisition_pipeline()` - GP fit → acquisition → suggest → observe
- `test_executor_store_integration()` - Executor writes results to Store correctly
- `test_multi_objective_end_to_end()` - qLogNEHVI search on 2D Pareto front

**Recovery tests:**
- `test_checkpoint_resume_deterministic()` - Resume produces identical results
- `test_crash_during_suggest()` - Recover from crash mid-suggest
- `test_crash_during_observe()` - Recover from crash mid-observe
- `test_store_corruption_detection()` - Detect and reject corrupted checkpoints

**Scale tests:**
- `test_distributed_executor()` - 10 parallel workers on Ray cluster
- `test_store_concurrent_writes()` - 100 concurrent `observe()` calls
- `test_large_search_space()` - 100-dimensional continuous space
- `test_long_horizon()` - 1000-trial optimization run

### Current Status

**Known issues:**
- Integration test count unknown (audit needed)
- Recovery tests depend on V02 state replay protocol
- Scale tests may require GPU/cluster resources

### Acceptance Criteria

- [ ] >20 tests implemented
- [ ] All critical paths covered (GP, ASHA, TuRBO, MO)
- [ ] All tests pass in <5 minutes total
- [ ] CI runs on every PR

---

## Layer 3: Statistical Campaigns

**Purpose:** Verify method effectiveness claims, gate tier exit

**Runtime:** Minutes to hours  
**Frequency:** Manual (gate validation)  
**Coverage target:** All V01-V15 claims  
**Count:** 15 validations

### Directories

```
validation/            # V01-V15 campaign scripts
validation/protocols/  # Preregistered protocols
validation/results/    # Immutable result artifacts
validation/validators/ # V16-compliant validators
```

### Campaigns

**Tier 0 (6 validations):**
- V01: Vendor parity (Sobol/TPE/GP match scipy/optuna/botorch)
- V02: State replay (deterministic recovery)
- V03: Mutation testing (≥0.90 kill score)
- V04-T0: Random baseline floor (>5% vs pathological)
- V05: Real workload (Brax/JAX evaluation)
- V14: Day-one walk (non-vacuous first-day sanity check)

**Tier 1 (4 validations):**
- V04-T1: Sobol vs random (replication after FAILED campaign)
- V06: ASHA efficiency (PASSED: 0.17% gap, 18.5% compute)
- V09: qLogNEHVI vs scalarization (PASSED: 8.2% improvement)
- V11: Prior recovery a/b (INCONCLUSIVE, πBO/PriorBand opt-in)

**Tier 2 (2 validations):**
- V10: MO-ASHA rung correlation (deferred, enhanced requirements)
- V13: Warm-start effectiveness (deferred, spec violation)

**Tier 3 / Program-level (3 validations):**
- V07: GPU capacity audit
- V08: BG-PBT performance (blocked on V04-T1)
- V12: Mixed-space TuRBO (blocked on V04-T1)
- V15: ifBO a/b fixed-sequence

**Meta-validation:**
- V16: Validator audit (4 checks: non-vacuity, no post-hoc tuning, correct reference, runnable independently)

### Runtime Estimates

**Fast (<1 min):**
- V02: State replay (deterministic, no sampling)
- V14: Day-one walk (smoke test)

**Medium (1-15 min):**
- V06: ASHA efficiency (~10 sec, 30 trials × 5 seeds)
- V04-T1: Sobol vs random (~15 sec, 200 trials × 5 seeds)
- V09: qLogNEHVI vs scalarization (~5 min, 100 trials × 10 seeds)

**Slow (15 min - 1 hour):**
- V11: Prior recovery (~18 min, 120 studies × 25 trials)
- V03: Mutation testing (depends on test suite size)

**Very slow (>1 hour):**
- V08: BG-PBT (TBD, likely 3+ GPU-weeks)
- V07: GPU capacity audit (resource reconciliation, not runtime)

### Current Status

**Completed:**
- ✅ V06 ASSED (2026-09-04)
- ✅ V09 PASSED (2026-09-04)

**Failed:**
- ❌ V04-T1 FAILED (2.42% improvement, p=0.2738, replication protocol created)

**Inconclusive:**
- ⚠️ V11 INCONCLUSIVE (underpowered, demotion applied)

**Deferred:**
- ⏸️ V10 (Tier 2)
- ⏸️ V13 (Tier 2)

**Blocked:**
- 🔒 V08 (blocked on V04-T1)
- 🔒 V12 (blocked on V04-T1)

**Unknown:**
- ❓ V01, V02, V03, V04-T0, V05, V07, V14, V15, V16

### Acceptance Criteria

- [ ] All V01-V15 protocols created (✓ completed Week 3 Day 1-3)
- [ ] All Tier 0 validations PASSED
- [ ] All Tier 1 validations resolved (PASSED or demoted)
- [ ] V16 audit enforced at all gates

---

## Implementation Plan

### Phase 1: Layer 1 Foundation (Week 3 Day 4-5)

**Goal:** >100 tests, >80% coverage

**Tasks:**
1. Audit existing tests (count, coverage, pass rate)
2. Repair 6 broken R1 tests (BUILD_PROGRAM_v2.md line 155)
3. Add unit tests for core modules (searchers, schedulers, acquisitions)
4. Add property tests for invariants (PD kernels, monotonic acquisitions)
5. Verify conformance tests from Week 2

**Deliverables:**
- `tests/unit/test_searchers.py`
- `tests/unit/test_schedulers.py`
- `tests/unit/test_acquisitions.py`
- `tests/unit/test_kernels.py`
- `tests/property/test_invariants.py`
- Coverage report (>80% target)

### Phase 2: Layer 2 Integration (Week 3 Day 4-5)

**Goal:** >20 tests, all critical paths

**Tasks:**
1. Audit existing integration tests
2. Add end-to-end tests (Branin, Hartmann6)
3. Add recovery tests (checkpoint resume)
4. Add scale tests (concurrent, distributed)

**Deliverables:**
- `tests/integration/test_end_to_end.py`
- `tests/recovery/test_checkpoint_resume.py`
- `tests/scale/test_distributed.py`
- `tests/scale/test_concurrent.py`

### Phase 3: Layer 3 Campaigns (Tier 0 gate, Week 4+)

**Goal:** All Tier 0 validations PASSED

**Priority order:**
1. V02 State replay (prerequisite for others)
2. V01 Vendor parity (foundational)
3. V04-T0 Random baseline floor (corrected post-hoc tuning)
4. V05 Real workload (not proxy)
5. V03 Mutation testing (slowest, run last)
6. V14 Day-one walk (smoke test)

**Deliverables:**
- 6 campaign scripts (`validation/v0X_*.py`)
- 6 V16-compliant validators (`validation/validators/v0X_validator.py`)
- 6 result artifacts (`validation/results/v0X_results.json`)

---

## V16 Enforcement

Every validator must implement `--audit` mode with 4 checks:

### Check 1: Non-Vacuity
Validator fails on structurally empty input (not PASS).

### Check 2: No Post-Hoc Tuning
Thresholds preregistered in protocol, not adjusted after results.

### Check 3: Correct Reference
Compares against declared vendor/baseline, not self.

### Check 4: Runnable Independently
Full protocol executes standalone without human intervention.

**Implementation:** Base validator class in `validation/validators/base_validator.py`

```python
class ValidationProtocol:
    def audit(self) -> AuditReport:
        """Run V16 audit checks."""
        checks = [
            self._check_non_vacuity(),
            self._check_no_posthoc_tuning(),
            self._check_correct_reference(),
            self._check_runnable_independently(),
        ]
        return AuditReport(checks=checks, passed=all(checks))
```

---

## Test Execution

### Local Development

```bash
# Layer 1: Fast feedback (<10 sec)
pytest tests/unit tests/property tests/conformance

# Layer 2: Integration checks (<5 min)
pytest tests/integration tests/recovery tests/scale

# Layer 3: Full validation (manual)
python validation/v06_asha_efficiency.py
```

### CI Pipeline

**On every commit:**
- Layer 1 tests (unit/property/conformance)
- Linting (ruff, mypy)
- Coverage report

**On every PR:**
- Layer 1 tests
- Layer 2 tests (integration/recovery/scale)
- Coverage gate (>80%)

**Manual (gate validation):**
- Layer 3 statistical campaigns (V01-V15)
- V16 validator audit

---

## Known Issues

### Issue 1: Layer 1 Test Count Unknown
**Problem:** Current unit test count and coverage not audited.

**Resolution:** Week 3 Day 4-5 audit finds existing tests, measures coverage.

**Status:** To be audited.

### Issue 2: 6 Broken R1 Tests
**Problem:** BUILD_PROGRAM_v2.md line 155 documents 6 broken R1 tests.

**Resolution:** Week 3 Day 4-5 repairs broken tests.

**Status:** To be fixed.

### Issue 3: Layer 2 Test Count Unknown
**Problem:** Integration test count and critical path coverage not audited.

**Resolution:** Week 3 Day 4-5 audit finds existing integration tests.

**Status:** To be audited.

### Issue 4: V16 Not Yet Implemented
**Problem:** V16 audit protocol defined but validators not yet V16-compliant.

**Resolution:** Week 3 Day 6 adds V16 audit to every validator.

**Status:** Scheduled Week 3 Day 6.

---

## References

**Authority:**
- HPO_NAS_RECOVERY_MASTER_PROGRAM.md lines 362-444 (Week 3 Day 4-5 specification)
- BUILD_PROGRAM_v2.md line 155 (6 broken R1 tests)
- validation/protocols/v16_protocol.md (V16 audit specification)

**Related:**
- validation/protocols/README.md (V01-V15 protocol suite)
- tests/conformance/ (Week 2 Day 1-5 contract tests)

---

## Changelog

**v1.0 - 2026-09-09**
- Initial test pyramid design
- Three layers: unit/property/conformance, integration/recovery/scale, statistical campaigns
- Pyramid ratio: 80% tests / <1% runtime (L1), 15% tests / ~10% runtime (L2), 5% tests / ~90% runtime (L3)
- Count targets: >100 (L1), >20 (L2), 15 (L3)
- V16 enforcement specified
- Known issues documented (audit needed, 6 broken R1 tests)

---

**END OF DOCUMENT**
