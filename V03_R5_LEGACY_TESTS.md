# V03 Round 5 - Legacy Searcher Tests

**Date:** 2026-09-19  
**Session:** Continued from Round 4 analysis  
**Goal:** Add high-value legacy searcher tests to close gap to 90%

---

## Summary

**Starting point:** 85.97% kill score (1563/1818), need 73 more kills  
**Strategy:** Add comprehensive legacy_searchers tests (58 survivors, 23% of total)  
**Tests added:** 15 new tests across RandomSearcher and SobolSearcher

---

## Tests Added

### File: `tests/unit/test_legacy_searchers.py` (NEW - 223 lines)

---

### 1. RandomSearcher Log Transform Tests (3 tests)

**Target:** Log-scale transform logic in RandomSearcher.propose()

**Tests:**
1. `test_log_transform_produces_log_uniform_distribution()`
   - Verifies log-scale produces geometric distribution
   - 64 samples from lr in (1e-5, 1e-1) with transform="log"
   - Asserts geometric mean near sqrt(1e-5 * 1e-1) = 0.001
   - Asserts samples span multiple decades

2. `test_log_transform_crashes_on_invalid_bounds()`
   - Verifies log(0) fails cleanly with OverflowError
   - Tests x in (0.0, 1.0) with transform="log"
   - Catches np.log(0) → -inf → uniform() overflow

3. `test_log_vs_linear_produces_different_distributions()`
   - Verifies log vs linear produce different medians
   - Same bounds (1.0, 100.0), different transforms
   - Log median < 20, linear median > 40

**Mutations targeted:**
- `np.log(low)` → `np.log(high)` in log transform
- `np.exp(...)` → `np.sqrt(...)` in inverse transform
- Arithmetic in log/exp operations

---

### 2. RandomSearcher Ordinal Tests (2 tests)

**Target:** Ordinal integer sampling in RandomSearcher.propose()

**Tests:**
1. `test_ordinal_covers_full_range()`
   - Verifies ordinals sample full range (0, 100)
   - 200 samples should see min < 10 and max > 90

2. `test_ordinal_bounds_inclusive()`
   - Verifies high bound is inclusive
   - Range (9, 10) with 20 samples should see both 9 and 10

**Mutations targeted:**
- `rng.integers(low, high+1)` → `rng.integers(low, high)` (exclusive high)
- Ordinal clamping logic

---

### 3. RandomSearcher Categorical Tests (2 tests)

**Target:** Categorical choice sampling in RandomSearcher.propose()

**Tests:**
1. `test_categorical_covers_all_choices()`
   - Verifies all 4 choices appear in 40 samples
   - Choices: ["sgd", "adam", "rmsprop", "adagrad"]

2. `test_categorical_rejects_invalid_choice()`
   - Verifies load_state_dict rejects invalid categorical value
   - Attempts to load "invalid_opt" not in choices

**Mutations targeted:**
- `rng.choice(choices)` → `rng.choice(choices[:-1])` (drops last)
- Categorical validation logic

---

### 4. RandomSearcher State Recovery Tests (2 tests)

**Target:** State dict validation in RandomSearcher.load_state_dict()

**Tests:**
1. `test_state_dict_rejects_wrong_kind()`
   - Saves RandomSearcher state, tries to load into SobolSearcher
   - Should raise ValueError

2. `test_load_state_dict_advances_rng_for_all_knob_kinds()`
   - Verifies RNG state restoration across continuous/ordinal/categorical
   - Saves after 10 proposals, loads into new searcher, asserts next proposal matches

**Mutations targeted:**
- `if state["kind"] != "random"` → `if state["kind"] == "random"` (inverted check)
- RNG state restoration logic

---

### 5. SobolSearcher Ordinal Tests (2 tests)

**Target:** Ordinal sampling in SobolSearcher._sobol_to_config()

**Tests:**
1. `test_sobol_ordinal_covers_range()`
   - Verifies Sobol ordinals cover full range (0, 50)
   - 64 samples should see min < 5 and max > 45

2. `test_sobol_ordinal_clamps_at_boundary()`
   - Verifies clamping at boundaries
   - Range (4, 6), all values in {4, 5, 6}

**Mutations targeted:**
- `int(low + u * (high - low + 1))` → `int(low + u * (high - low))` (exclusive)
- `min(result, high)` → `result` (no clamping)

---

### 6. SobolSearcher Log Transform Tests (1 test)

**Target:** Log-scale transform in SobolSearcher._sobol_to_config()

**Test:**
1. `test_sobol_log_produces_geometric_distribution()`
   - Verifies Sobol log-scale produces geometric distribution
   - 64 samples from lr in (1e-4, 1e-1)
   - Geometric mean near 0.01, spans 2+ decades

**Mutations targeted:**
- `np.log(high) - np.log(low)` → `np.log(high) + np.log(low)` (wrong formula)
- `np.exp(...)` mutations in inverse transform

---

### 7. SobolSearcher State Recovery Tests (3 tests)

**Target:** State dict validation in SobolSearcher.load_state_dict()

**Tests:**
1. `test_sobol_state_dict_rejects_wrong_kind()`
   - Saves SobolSearcher state, tries to load into RandomSearcher
   - Should raise ValueError

2. `test_sobol_state_dict_rejects_space_mismatch()`
   - Saves with 2-knob space, tries to load into 1-knob searcher
   - Should raise ValueError

3. `test_sobol_load_state_dict_handles_categorical_rng()`
   - Verifies categorical RNG state restoration
   - Mixed space with continuous + categorical

**Mutations targeted:**
- `if state["kind"] != "sobol"` → `if state["kind"] == "sobol"` (inverted)
- Space dimension validation logic
- Categorical RNG restoration

---

## Expected Impact

**Total new tests:** 15  
**Expected kills:** 20-35 mutations

**Breakdown by mutation category:**
- Log/exp arithmetic: 8-12 kills (multiple tests verify geometric distribution)
- Ordinal bounds: 4-6 kills (inclusive/exclusive high bound)
- Categorical sampling: 2-4 kills (choice logic)
- State validation: 6-10 kills (kind checks, space validation)
- RNG restoration: 3-5 kills (state restore logic)

**Gap analysis:**
- Current: 1563 kills (85.97%)
- Need: 1636 kills (90%)
- Gap: 73 kills
- Expected from 15 tests: 20-35 kills (27-48% of gap)
- Projected result: 87.1-88.9%

**Likely outcome:** Will get very close to 90%, may need 5-10 more strategic tests or accept 88-89% as strong result given equivalent mutants.

---

## Mutation Testing Status

**Running:** Full mutation testing with all 15 new tests  
**Started:** 2026-09-19  
**Expected duration:** ~2 hours  
**Command:** `rm -f .mutmut-cache && python -m mutmut run`  
**Task ID:** bl3e7gqpv

---

## Next Steps After Completion

1. **Analyze results:**
   - Calculate new kill score
   - Count how many legacy_searchers survivors were killed
   - Identify remaining survivor categories

2. **If >= 90%:** ✅
   - Update V03_STATUS.md with PASS
   - Run validation script
   - Document final results

3. **If 88-89%:** 🔄
   - Add 5-10 targeted space validation tests
   - Add 2-3 executor error handling tests
   - Final push to 90%

4. **If < 88%:** 🔍
   - Analyze which mutations still survive
   - Consider equivalent mutant analysis
   - Reassess approach

---

## Confidence Assessment

**High confidence targets:**
- Log transform tests: Clear arithmetic formulas
- Ordinal bounds tests: Known inclusive/exclusive mutations
- State validation tests: Simple boolean checks

**Medium confidence targets:**
- Categorical tests: May have equivalent mutations
- RNG restoration: Complex state, some may be equivalent

**Risk factors:**
- Some survivors may be equivalent mutants
- String mutations in error messages still won't be caught
- Some edge cases may require very specific test conditions
