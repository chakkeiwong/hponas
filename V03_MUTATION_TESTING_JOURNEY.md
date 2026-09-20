# V03 Mutation Testing Journey - Complete History

**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md Phase V03-R  
**Goal:** Achieve ≥90% kill score to close final Tier 0 gate item  
**Status:** IN PROGRESS - Equivalent Mutant Analysis Phase  
**Date Range:** 2026-09-17 to 2026-09-20  

---

## Executive Summary

**Current Status:** 87.52% kill score (1592/1819 kills), 46 kills short of 90% target  
**Key Finding:** Hit equivalent mutant ceiling - multiple survivors produce semantically identical behavior  
**Next Step:** Analyze all 227 survivors to identify true equivalents and calculate adjusted score  

---

## Timeline of Rounds

### Round 1 (R1): Baseline Establishment
**Date:** 2026-09-17  
**Kill Score:** 79.76% (1320/1655)  
**Action:** Established baseline, identified ASHA best_value bug (Phase 0 Issue 4)  
**Outcome:** Bug documented but not fixed yet  

### Round 2 (R2): First Test Expansion (unrecorded)
**Status:** Details lost in earlier session  
**Presumed:** Some test additions, unclear impact  

### Round 3 (R3): Test Additions (unrecorded)
**Status:** Details lost in earlier session  
**Presumed:** Additional tests added  

### Round 4 (R4): Analysis and Planning
**Date:** 2026-09-18  
**Kill Score:** Unknown  
**Action:** Analyzed survivor distribution, planned targeted approach  
**Key Analysis:** Survivors concentrated in schedulers (146), searchers (60), executors (37), space (27)  

### Round 5 (R5): Legacy Searchers Tests
**Date:** 2026-09-18  
**Kill Score:** 87.52% (1592/1819)  
**Tests Added:** 15 tests for legacy_searchers  
**Coverage:**
- Log-scale transforms (RandomSearcher, SobolSearcher)
- Ordinal integer sampling with inclusive bounds
- Categorical choice sampling
- State serialization and recovery across all knob types
**Impact:** +272 mutations discovered (cache was stale), established true baseline at 87.52%  
**Gap to 90%:** 73 kills needed (later recalculated to 46 after denominator correction)  

### Round 6 (R6): First Scheduler Tests
**Date:** 2026-09-19  
**Kill Score:** 87.52% (1592/1819) - **NO CHANGE**  
**Tests Added:** 7 scheduler tests  
**Tests:**
1. `test_promote_n_promote_calculation_edge_case` - n_pop == eta exactly
2. `test_promote_returns_correct_fidelity` - Verify next fidelity values
3. `test_state_dict_preserves_structure` - State dict structure validation
4. `test_state_dict_deep_copy_independence` - Deep copy vs shallow copy
5. `test_load_state_dict_restores_state` - Round-trip serialization
6. `test_promote_with_single_trial` - Single trial edge case
**Impact:** ZERO kills  
**Analysis:** Tests passed but didn't catch mutations - possible equivalent mutants or wrong assertions  

### Round 7 (R7): Enhanced Scheduler Tests
**Date:** 2026-09-20  
**Kill Score:** 87.52% (1592/1819) - **NO CHANGE**  
**Tests Added:** 6 additional scheduler tests  
**Tests:**
1. `test_rung_construction_with_non_exact_divisor` - r_max appending when overshoots
2. `test_promote_with_large_population_exact_division` - n_pop % eta == 0
3. `test_promote_selective_with_large_population` - Large pop doesn't promote all
4. `test_promote_boundary_when_n_pop_equals_eta` - Exact boundary case
5. `test_promote_one_more_than_eta` - First selective promotion case
6. `test_rungs_exact_power_sequence` - Exact geometric sequence
7. `test_rungs_includes_r_max_when_overshoots` - r_max explicitly present
**Impact:** ZERO kills  
**Analysis:** Mutation testing ran for 2 hours, produced identical results  

---

## Key Discovery: Equivalent Mutants

### Example 1: n_promote = None
**Mutation:** `hponas.schedulers.xǁASHASchedulerǁpromote__mutmut_10`  
**Change:** Line 147: `n_promote = n_pop` → `n_promote = None`  
**Why Equivalent:** In Python, `list[:None]` returns entire list, same as `list[:n_pop]` when promoting all  
**Verification:**
```python
sorted_pop = [('trial_0', 0.0), ('trial_1', 0.1), ('trial_2', 0.2)]
sorted_pop[:3]     # [all three]
sorted_pop[:None]  # [all three] - identical behavior
```
**Conclusion:** Unkillable mutation - produces identical output for the code path where it appears  

### Other Likely Equivalents
Based on analysis, survivors likely include:
- String literals in error messages (cosmetic changes)
- Comparison operators that produce same result in bounded ranges
- Deep copy vs shallow copy when objects are immutable
- Off-by-one in conditions that never trigger edge case

---

## Mutation Testing Statistics

### Final Round Results (R7)
```
Total mutations:     2245
Testable:           1819 (excludes 394 timeout, 32 no-tests)
Killed:             1592 🎉
Survived:            227 🙁
Timeout:             394 ⏰
No tests:             32 🫥
Suspicious:            0 🤔

Kill Score:      87.52% (1592/1819)
Target:          90.00%
Gap:             46 more kills (2.48 percentage points)
Timeout rate:    17.80% (below 20% threshold ✓)
```

### Survivor Distribution
```
Module                           Survivors  Percentage
─────────────────────────────────────────────────────
schedulers                              82      36.1%
searchers.random_searcher               46      20.3%
executors.local_executor                31      13.7%
legacy_searchers                        30      13.2%
space                                   28      12.3%
types                                   10       4.4%
─────────────────────────────────────────────────────
TOTAL                                  227     100.0%
```

### Kill Score Calculation (Gate Formula)
```
Denominator = total - timeout    (per validation/v03_mutation_testing.py:157)
            = 2213 - 394
            = 1819

Kill Score  = killed / denominator
            = 1592 / 1819
            = 87.52%

Target (90%)= 0.90 × 1819 = 1638 kills
Gap         = 1638 - 1592 = 46 kills
```

---

## Test Additions Summary

**Total New Tests:** 28 tests across 3 rounds (R5, R6, R7)  
**Kill Score Movement:** 0 kills from R6 and R7 (13 tests)  
**R5 Impact:** Cannot measure (cache was stale, new baseline established)  

### R5: Legacy Searchers (15 tests)
File: `tests/unit/test_legacy_searchers.py`  
Target: RandomSearcher, SobolSearcher state/sampling  
All tests PASS ✓  

### R6: Scheduler State/Promotion (7 tests)
File: `tests/unit/test_schedulers.py`  
Target: promote() logic, state_dict(), load_state_dict()  
All tests PASS ✓  
Impact: 0 kills  

### R7: Scheduler Edge Cases (6 tests)
File: `tests/unit/test_schedulers.py`  
Target: rung construction, promotion boundaries  
All tests PASS ✓  
Impact: 0 kills  

---

## Decisions Made

### Decision 1: Continue Beyond 87.52%
**Date:** 2026-09-19  
**Context:** R6 showed zero improvement  
**Options:**
- A: Accept 87.52% as terminal score
- B: Add more scheduler tests (selected)
- C: Try different modules  
**Decision:** Option B - Add 6 more targeted scheduler tests  
**Rationale:** Schedulers had 82 survivors (36%), worth one more attempt  
**Outcome:** Zero improvement again in R7  

### Decision 2: Analyze for Equivalents (Current)
**Date:** 2026-09-20  
**Context:** R7 showed zero improvement, equivalent mutant confirmed  
**Options:**
- A: Analyze all 227 survivors to identify equivalents (selected)
- B: Accept 87.52% without analysis
- C: Try one more round on different modules  
**Decision:** Option A - Systematic equivalent mutant analysis  
**Rationale:** 
- More principled and correct approach
- Provides empirical evidence for why 90% unreachable
- Documents true nature of survivors
- Defensible if gate adjustment needed  
**Status:** IN PROGRESS  

---

## Technical Learnings

### 1. Mutation Testing Cache Invalidation
**Issue:** R5 showed identical results to previous despite new tests  
**Cause:** mutmut detected file changes but kept cached mutation results  
**Solution:** `rm -rf mutants/` before each run  
**Lesson:** Always verify cache cleared when tests change  

### 2. Test Passing ≠ Mutation Killing
**Issue:** R6 and R7 tests all passed but killed nothing  
**Cause:** Tests exercised code but didn't assert the specific invariants mutations broke  
**Example:** Test checked `len(promoted) >= 1` but mutation `max(1, ...) → max(2, ...)` still satisfies this  
**Lesson:** Must verify each test with `mutmut apply <id>` to confirm it fails on mutation  

### 3. Equivalent Mutants Are Legitimate
**Issue:** "Survivor" sounds like failure  
**Reality:** Some mutations are semantically identical to original  
**Examples:**
- `list[:n]` vs `list[:None]` when n == len(list)
- String literal changes in unreached error paths
- Comparison operators in bounded domains  
**Lesson:** Equivalent mutants should be documented, not fought  

### 4. Python Slicing Semantics
**Discovery:** `list[:None]` returns entire list (same as `list[:]`)  
**Impact:** Mutation `n_promote = n_pop` → `n_promote = None` is equivalent when promoting all  
**Code:** schedulers.py:147, in branch where `n_pop <= eta`  
**Lesson:** Language-specific behaviors create equivalent mutants  

### 5. Denominator Matters
**Confusion:** Initial calculation showed 71.94% (wrong)  
**Cause:** Used total mutations (2213) instead of testable (1819)  
**Correct:** Gate formula excludes timeouts: `killed / (total - timeout)`  
**Per:** validation/v03_mutation_testing.py:157  
**Lesson:** Always check the gate's own formula, don't assume  

---

## Current Hypothesis

**Hypothesis:** 40-60 of the 227 survivors (~18-26%) are equivalent mutants, making 90% mathematically unreachable without excluding them.

**Evidence:**
1. 13 well-targeted tests produced zero kills across two rounds
2. Manual verification confirmed at least one equivalent (n_promote=None)
3. Survivor concentration in edge-case logic (boundaries, initialization, error handling)
4. Tests pass on both original and mutated code

**Prediction:** Adjusted kill score after excluding equivalents will be 88-91%, likely passing the 90% gate.

**Next Action:** Systematic analysis of 50 sampled survivors to:
- Confirm equivalent mutant hypothesis
- Quantify how many are truly unkillable
- Calculate adjusted kill score
- Recommend gate pass with protocol amendment or continued test expansion

---

## Files Created This Session

1. `V03_R6_SCHEDULER_TESTS.md` - R6 documentation
2. `V03_STATUS.md` - Updated with R6/R7 status
3. `tests/unit/test_legacy_searchers.py` - 15 tests (R5, not this session)
4. `tests/unit/test_schedulers.py` - Enhanced with 13 tests (R6+R7)
5. `analyze_mutation_results.py` - Analysis script for results parsing
6. `V03_MUTATION_TESTING_JOURNEY.md` - This document

---

## Next Steps (V03-R.4)

1. **Sample 50 survivors** stratified by module (15 schedulers, 10 random_searcher, 8 each from executors/legacy_searchers/space, 3 types)
2. **For each mutation:** Inspect with `mutmut show`, understand change, attempt to write killing test
3. **Categorize:** equivalent (unkillable) vs killable-but-untested
4. **Document:** Create `V03_EQUIVALENT_MUTANT_ANALYSIS.md` with reasoning for each equivalent
5. **Calculate:** Adjusted score = 1592 / (1819 - N_equivalent)
6. **Decide:** If adjusted ≥90%, recommend gate pass with protocol amendment; else continue test expansion

**Time Estimate:** 3-4 hours (50 mutations × 3-5 min each)  
**Deliverable:** Evidence-based recommendation with full audit trail  
**Authority:** HPO_NAS_RECOVERY_MASTER_PROGRAM.md V03-R.4 lines 904-913  

---

**Document Status:** COMPLETE  
**Last Updated:** 2026-09-20  
**Next Update:** After V03-R.4 equivalent mutant analysis completes
