# V03 Mutation Testing Status

**Date:** 2026-09-17  
**Target:** Kill score ≥ 0.90 (90%)  
**Current Status:** ❌ BLOCKED

---

## Current State

### Full Mutation Run (2026-09-17, post-dead-code fixes)
- **Total mutants:** 2243
- **Killed:** 1356 (60.5% of total)
- **Skipped:** 226 (10.1%)
- **Timeout:** 373 (16.6%)
- **Survived:** 288 (12.8%)
- **Eligible (non-skipped, non-timeout):** 1644
- **Kill score:** 1356 / 1644 = **82.48%**
- **Status:** ❌ FAIL (need ≥90%, gap = 124 kills)

**Progress:** +36 kills from baseline (79.76% → 82.48%)

### Survivor Distribution (Top Files)
1. SobolSearcher: 75 survivors
2. MOASHAScheduler: 52 survivors  
3. RandomSearcher: 44 survivors
4. LocalExecutor: 37 survivors
5. PASHAScheduler: 24 survivors
6. ASHAScheduler: 23 survivors
7. Knob: 22 survivors
8. SearchSpace: 11 survivors

### V03-R.2 Audit Results (Dead Code Search)
**Conclusion:** No additional dead code patterns found beyond the three scheduler bugs.

**288 survivors categorized:**
1. **Error message strings** (~40): Unkillable without asserting message text (brittle)
2. **Untested init parameters** (~60): Default values, seed propagation
3. **Arithmetic in formulas** (~50): Sobol mapping, hypervolume calculations
4. **Edge case logic** (~80): Boundary conditions, small populations
5. **Equivalent mutants** (~58): Should document and skip

**Strategic pivot:** Dead code audit complete. Remaining 124-kill gap requires targeted testing of arithmetic/edge cases, not more code review.

### Method-Level Results (Surgical Targeting)

#### ASHAScheduler.report() — ✅ COMPLETE
- 41 mutants → 41/41 killed (100%)
- Previously: 35/41 survivors; fixed by removing dead code at lines 108-112, 125

#### PASHAScheduler.report() — ✅ COMPLETE  
- 33 mutants → 33/33 killed (100%)
- Previously: 20/33 survivors; fixed by removing dead code at lines 289-306

#### MOASHAScheduler.report() — ✅ COMPLETE
- 40 mutants → 39/40 killed (97.5%), 1 documented equivalent
- Previously: 40/40 survivors; fixed by removing dead code at lines 479-496
- Equivalent: mutation 8 (`self._gates and` → `self._gates or`: vetoed trials short-circuit before gate loop)
- **Bug fixed:** Vetoed trials re-reporting now correctly return "stop" (added guard at line 484)
- **Kill score:** 0.5361 (53.61%)
- **Status:** FAIL - high timeout rate due to slow GPSearcher tests

---

## Work Completed This Session

### 1. Fixed SobolSearcher API Compatibility ✅
**Problem:** SobolSearcher used old API (`space.dim()`, `space.parameters`)  
**Solution:** Made SobolSearcher polymorphic to support both APIs:
- `__init__`: Check for `dim()` method vs `knobs` attribute
- `_sobol_to_config`: Support both `parameters` dict and `knobs` list

**Files changed:**
- `hponas/searchers/random_searcher.py` (lines 98-234)

**Commit:** 90a673a "Make SobolSearcher polymorphic and add comprehensive contract tests"

### 2. Added SobolSearcher Contract Tests ✅
**Problem:** SobolSearcher had ZERO test coverage in contract suite  
**Solution:** Added 9 comprehensive tests in `TestSearcherContractSobolBaseline`:

1. `test_sobol_suggest_valid` - Returns valid configs
2. `test_sobol_deterministic` - Seed determinism with scrambling
3. `test_sobol_bounds_continuous` - Strict bounds checking (100 samples)
4. `test_sobol_bounds_log_scale` - Log-warped bounds
5. `test_sobol_categorical_edge_case` - Handles u=1.0 edge case
6. `test_sobol_state_serialization` - JSON serializability
7. `test_sobol_state_deserialization_produces_identical_sequence` - Behavioral equivalence ⭐
8. `test_sobol_integer_bounds` - Integer type and bounds
9. `test_sobol_mixed_space` - Combined continuous/ordinal/categorical

**Key innovation:** Test #7 verifies that deserialized state produces **identical suggestion sequences**, not just that the state is JSON-serializable. This catches mutations like `rng_state[3] → rng_state[4]` that corrupt state.

**Files changed:**
- `tests/conformance/test_searcher_contract.py` (added 139 lines)

**Test results:**
- All 33 contract tests pass (was 24 passed, 1 skipped)
- New SobolSearcher tests: 9/9 pass

### 3. Added Behavioral State Tests for RandomSearcher ✅
Added `test_random_state_deserialization_produces_identical_sequence` to verify that RandomSearcher state restoration produces identical suggestion sequences.

---

## Root Cause Analysis

The V03 failure is **NOT** primarily about searchers (only 8% of survived mutants in random_searcher when scoped). The problem is **systemic test coverage gaps** across the entire mutation testing scope.

### Distribution of 342 Survived Mutants (Full Scope)
```
159 (46%)  hponas.schedulers           ← BIGGEST PROBLEM
69  (20%)  hponas.executors.local_executor
59  (17%)  hponas.space
59  (17%)  hponas.legacy_searchers     ← includes Sobol (now partially fixed)
29  (8%)   hponas.searchers.random_searcher
6   (2%)   hponas.types
```

### Specific Gaps Identified

#### 1. Schedulers (46% of survived mutants)
- 159 survived mutants
- Likely ASHA promotion logic, rung management, trial stopping decisions
- **Critical:** Lines 48-49 in `validation/v03_mutation_testing.py` list ASHA methods as "zero survivors allowed"

#### 2. Executors (20% of survived mutants)
- 69 survived mutants
- LocalExecutor.launch/submit error handling
- **Critical:** Lines 51-52 list executor methods as "zero survivors allowed"

#### 3. Space (17% of survived mutants)
- 59 survived mutants
- SearchSpace knob validation, bounds checking, transform logic

#### 4. State Serialization (Cross-cutting)
- Current tests only check JSON serializability
- Do NOT verify behavioral equivalence (identical sequences after deserialization)
- **Fixed for:** RandomSearcher, SobolSearcher
- **Still needed for:** GPSearcher, schedulers, executors

#### 5. SobolSearcher (Partially Fixed)
- 60 survived mutants in searchers-only run (out of 595 testable)
- Many in `_sobol_to_config` arithmetic and bounds logic
- New tests should kill some, but not all (need more targeted tests for specific mutations)

---

## Timeout Issue

The searchers-only run had **216 timeout mutants (36%)** due to GPSearcher tests being slow:
- `_tensor_to_config`: 48 timeouts
- `_config_to_tensor`: 44 timeouts
- `_prepare_training_data`: 6 timeouts
- GP model fitting tests are expensive

**Why this matters:** Timeout rate > 20% fails V03 protocol (line 26: `MAX_TIMEOUT_RATE = 0.20`)

**Options:**
1. Mark slow tests with `@pytest.mark.slow` and exclude from mutation testing
2. Use faster test fixtures for mutation testing
3. Accept higher timeout rate for Tier 0 (negotiate with protocol)

---

## Path Forward

### Option A: Achieve 90% Kill Score (Full Protocol Compliance)
**Required work:**
1. ✅ Add SobolSearcher tests (DONE)
2. Add comprehensive scheduler tests (ASHA promotion, stopping, rung management)
3. Add comprehensive executor tests (launch, error handling, resource management)
4. Add SearchSpace tests (knob validation, bounds, transforms)
5. Strengthen state serialization tests across all components
6. Address timeout issue (mark slow tests or optimize fixtures)

**Estimated effort:** 3-4 days of focused test writing  
**Likelihood:** Low without dedicated time

### Option B: Narrow V03 Scope to Searchers Only (Protocol Amendment)
**Required work:**
1. ✅ Add SobolSearcher tests (DONE)
2. Investigate and fix 60 survived mutants in searchers
3. Address timeout issue for GPSearcher
4. Document protocol deviation in validation results

**Estimated effort:** 1-2 days  
**Likelihood:** Medium, requires user approval to deviate from protocol

### Option C: Defer V03 to Post-Tier-0 (Gate Redefinition)
**Rationale:**
- 6/7 Tier 0 gates pass (86%)
- V03 is about test quality, not system correctness
- Mutation testing is expensive and may not be critical for research prototype
- Can achieve 90% incrementally over time

**Estimated effort:** 0 days (defer decision)  
**Likelihood:** High if user agrees mutation testing is not gate-critical

---

## Recommendation

**Short term (this session):**
- Commit the SobolSearcher improvements (DONE ✅)
- Document V03 status (this file ✅)
- Present options to user for decision

**Medium term (if pursuing Option A):**
Priority order based on survived mutant distribution:
1. **Schedulers tests** (159 survived, 46%) - highest impact
2. **Executors tests** (69 survived, 20%) - second highest
3. **Space tests** (59 survived, 17%)
4. **Strengthen searcher tests** to kill remaining 60 survivors

**Long term:**
- V03 as continuous improvement metric
- Target 90% incrementally as codebase matures
- Revisit protocol thresholds based on research prototype needs

---

## Key Files

### Source Code
- `hponas/searchers/random_searcher.py` - RandomSearcher, SobolSearcher
- `hponas/searchers/gp_searcher.py` - GPSearcher
- `hponas/schedulers.py` - ASHA, other schedulers
- `hponas/executors/local_executor.py` - LocalExecutor
- `hponas/space.py` - SearchSpace, Knob
- `hponas/types.py` - Type definitions

### Tests
- `tests/conformance/test_searcher_contract.py` - Searcher contract tests (33 tests)
- Need: `tests/conformance/test_scheduler_contract.py`
- Need: `tests/conformance/test_executor_contract.py`
- Need: `tests/conformance/test_space_contract.py`

### Validation
- `validation/v03_mutation_testing.py` - V03 validation script
- `validation/protocols/v03_protocol.md` - Protocol specification
- `pyproject.toml` - Lines 60-81: mutmut configuration

---

## User Decision Required

The user explicitly stated: **"We should not defer the problem"** (from previous session).

However, the problem scope is much larger than initially apparent:
- Not just searchers (8% of problem)
- Systemic coverage gaps in schedulers (46%), executors (20%), space (17%)
- Estimated 3-4 days of test writing to achieve 90%

**Questions for user:**
1. Should we pursue full 90% kill score (Option A)?
2. Should we narrow scope to searchers only (Option B)?
3. Should we reconsider V03 as a gate blocker (Option C)?
4. What is the priority of V03 vs other work?
