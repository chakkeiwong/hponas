# V03 Round 3 - Test Additions

**Date:** 2026-09-18  
**Session:** Continued from V03 survivor analysis  
**Goal:** Add targeted tests to reach 90% kill score

---

## Summary

**Starting point:** 85.67% kill score (1554/1814), need 78 more kills  
**Strategy:** Add high-value tests targeting known survivor categories  
**Tests added:** 9 new tests across 3 categories

---

## Tests Added

### 1. Scheduler State Serialization (5 tests)

**File:** `tests/unit/test_scheduler_state.py` (NEW)

**Target:** Copy vs deepcopy mutations in ASHAScheduler state_dict() and load_state_dict()

**Tests:**
1. `test_state_dict_deep_copies_rungs()`
   - Verifies rungs list is deep copied, not shallow copied
   - Mutates returned state dict and asserts original unchanged
   
2. `test_state_dict_deep_copies_trial_state()`
   - Verifies _trial_state dict is deep copied
   - Mutates trial state entries and asserts original unchanged
   
3. `test_state_dict_deep_copies_rung_populations()`
   - Verifies _rung_populations dict with nested lists is deep copied
   - Appends to inner lists and asserts original unchanged
   
4. `test_state_dict_deep_copies_fidelity_history()`
   - Verifies _fidelity_history dict with nested lists is deep copied
   - Mutates inner lists and asserts original unchanged
   
5. `test_load_state_dict_restores_complete_state()`
   - Verifies complete state restoration from state dict
   - Creates scheduler, saves state, loads into new scheduler, asserts equality

**Mutations targeted:**
- `copy.deepcopy(self.rungs)` → `copy.copy(self.rungs)`
- `copy.deepcopy(self._trial_state)` → `copy.copy(self._trial_state)`
- `copy.deepcopy(self._rung_populations)` → `copy.copy(self._rung_populations)`
- `copy.deepcopy(self._fidelity_history)` → `copy.copy(self._fidelity_history)`

**Expected kills:** 4-8 mutations (some may be equivalent for immutable values)

---

### 2. Scheduler Edge Cases (3 tests)

**File:** `tests/unit/test_schedulers.py` (MODIFIED - added to TestASHAScheduler class)

**Target:** Edge case logic in ASHAScheduler.promote()

**Tests:**
1. `test_promote_all_when_population_small()`
   - When population <= eta, all trials should be promoted
   - Tests with 2 trials and eta=3
   - Asserts all 2 trials promoted
   
2. `test_promote_minimum_one_trial()`
   - Promotion count is at least 1 even with large eta
   - Tests with 3 trials and eta=10
   - Asserts at least 1 promoted, best trial first
   
3. `test_promote_respects_ceiling_with_small_population()`
   - With 5 trials and eta=3, should promote ceil(5/3) = 2 trials
   - Asserts exactly 2 promoted
   - Asserts top 2 trials by performance

**Mutations targeted:**
- Line 147: `n_promote = n_pop` → `n_promote = None` (TypeError on slice)
- Line 149: `max(1, math.ceil(...))` → `max(2, math.ceil(...))` (wrong minimum)
- Other promote() logic mutations

**Expected kills:** 5-10 mutations

---

### 3. Sobol Integer Log-Scale (1 test)

**File:** `tests/unit/test_random_searcher.py` (MODIFIED - added to TestSobolArithmeticFormulas class)

**Target:** Integer log interpolation formula in SobolSearcher._sobol_to_config()

**Test:**
1. `test_integer_log_interpolation_formula()`
   - Parameter: n in range (10, 1000) with log_scale=True
   - Collects 64 samples
   - Asserts all are integers in bounds
   - Asserts geometric mean near sqrt(10 * 1000) = 100 (within 70-140)
   - Asserts samples span multiple decades (orders of magnitude)

**Mutations targeted:**
- `np.log(high) - np.log(low)` → `np.log(high) + np.log(low)` (wrong formula)
- Other arithmetic in log interpolation

**Expected kills:** 2-4 mutations

---

## Expected Impact

**Total new tests:** 9  
**Expected kills:** 11-22 mutations (conservative estimate)  
**Optimistic scenario:** +25 kills if all targeted mutations caught

**Gap analysis:**
- Current: 1554 kills (85.67%)
- Need: 1632 kills (90%)
- Gap: 78 kills
- Expected from tests: 11-22 kills (14-28% of gap)

**Remaining strategies if not sufficient:**
1. Document and skip string mutations (~45 survivors)
2. Add more edge case tests for legacy_searchers
3. Add executor error handling tests
4. Add space validation tests

---

## Mutation Testing Results

**Completed:** 2026-09-18  
**Kill Score:** 85.97% (1563/1818)  
**Previous:** 85.67% (1554/1814)  
**Improvement:** +0.30% (+9 kills)  
**Command:** `python -m mutmut run` (fresh cache)

### Actual vs Expected Impact

**Expected:** 11-22 kills  
**Actual:** 9 kills  
**Gap to 90%:** Still need 73 more kills (was 78, now 73)

### Why Tests Underperformed

1. **Equivalent Mutants in Scheduler Tests:**
   - `n_promote = None` → equivalent to `n_promote = n_pop` (Python `list[:None]` == `list[:]`)
   - `copy.copy(self.rungs)` → equivalent to `copy.deepcopy(self.rungs)` (rungs contains only immutable floats)
   - Several other promote() mutations are equivalent for edge cases

2. **State Tests Less Effective:**
   - Some copy vs deepcopy mutations are equivalent for immutable values
   - Tests correctly target nested mutables but miss other mutation types

3. **Sobol Test Limited Impact:**
   - Only 1 test, targets specific formula mutations
   - Many Sobol survivors are in different code paths

---

## Files Modified

### New Files
1. `tests/unit/test_scheduler_state.py` (120 lines, 5 tests)

### Modified Files
1. `tests/unit/test_schedulers.py` (added 3 tests to TestASHAScheduler)
2. `tests/unit/test_random_searcher.py` (added 1 test to TestSobolArithmeticFormulas)

---

## Next Steps After Mutation Testing Completes

1. **Analyze results:**
   - Calculate new kill score
   - Count how many targeted mutations were killed
   - Identify which mutations still survived

2. **If >= 90%:** ✅
   - Update V03_STATUS.md with PASS
   - Run validation script
   - Document final results

3. **If < 90%:** 🔄
   - Calculate remaining gap
   - If close (88-89%), add 1-2 more targeted tests
   - If further (86-87%), implement string mutation skipping strategy
   - If still far (<86%), reassess approach

---

## Confidence Assessment

**High confidence targets:**
- Scheduler edge case tests: Known mutations, clear test cases
- Sobol integer log test: Specific arithmetic formula mutation

**Medium confidence targets:**
- Scheduler state tests: Some may be equivalent mutants (immutable values)

**Risk factors:**
- Some copy vs deepcopy mutations may be equivalent
- Unknown survivors may be harder to kill than expected
- String mutations likely require skipping, not testing
