# V03 Round 8 (R8) - Targeted Survivor Kills

**Date:** 2026-09-22  
**Goal:** Add 14 high-value tests targeting scheduler, space, executor, and legacy_searcher survivors to close the 46-kill gap to 90%

## Baseline (R5 Results)

- **Kill Score:** 87.52% (1592/1819 testable mutations)
- **Gap to 90%:** 46 kills needed
- **Survivors by module:**
  - schedulers: 82 (36.1%)
  - searchers.random_searcher: 46 (20.3%)
  - executors.local_executor: 31 (13.7%)
  - legacy_searchers: 30 (13.2%)
  - space: 28 (12.3%)
  - types: 10 (4.4%)

## R8 Test Additions

Created `tests/unit/test_r8_survivor_kills.py` with 14 tests across 4 categories:

### 1. ASHA Scheduler Boundary Conditions (5 tests)

Targets: 82 scheduler survivors (36% of all survivors)

- **test_rungs_when_r_max_is_exact_power_of_eta**: Tests rung generation when r_max = η^k
- **test_rungs_when_r_max_between_powers**: Tests rung generation when r_max falls between powers
- **test_rungs_with_eta_2**: Tests rung generation with η=2 (common edge case)
- **test_promote_boundary_at_eta_threshold**: Tests promotion decision at exact η threshold
- **test_promote_boundary_below_eta**: Tests promotion decision just below η threshold

**Rationale:** The 82 scheduler survivors likely include:
- Rung calculation edge cases (powers of η, rounding)
- Promotion threshold boundary conditions
- Edge cases in trial ranking/culling logic

Expected kills: 15-25 from scheduler survivors

### 2. Space Serialization Round-Trip (6 tests)

Targets: 28 space survivors (12% of all survivors)

- **test_knob_from_dict_with_missing_transform**: Tests Knob.from_dict() with missing optional 'transform'
- **test_knob_from_dict_with_explicit_none_transform**: Tests Knob.from_dict() with transform=None
- **test_knob_from_dict_with_missing_note**: Tests Knob.from_dict() with missing optional 'note'
- **test_knob_from_dict_with_missing_prior**: Tests Knob.from_dict() with missing optional 'prior'
- **test_search_space_to_json_round_trip**: Tests SearchSpace.to_json() → from_json() round-trip
- **test_search_space_get_knob_missing_raises**: Tests get_knob() raises for missing knob name

**Rationale:** The 28 space survivors likely include:
- Optional field handling in from_dict() (transform, note, prior)
- JSON serialization edge cases
- get_knob() error path
- Default value mutations

Expected kills: 8-12 from space survivors

### 3. LocalExecutor Mode Validation (2 tests)

Targets: 31 executors.local_executor survivors (14% of all survivors)

- **test_execute_rejects_async_mode**: Tests execute() raises ValueError when mode='async'
- **test_execute_accepts_sync_mode**: Tests execute() works correctly when mode='sync'

**Rationale:** The 31 executor survivors likely include:
- Mode validation in execute() vs execute_async()
- Error message string mutations
- Branch coverage for mode checks

Expected kills: 4-6 from executor survivors

### 4. Legacy Searcher Defaults (1 test)

Targets: 30 legacy_searchers survivors (13% of all survivors)

- **test_sobol_searcher_default_seed**: Tests SobolSearcher uses seed=0 by default

**Rationale:** The 30 legacy_searcher survivors likely include:
- Default parameter value mutations
- Seed initialization paths
- Determinism checks

Expected kills: 2-4 from legacy_searcher survivors

## Expected Impact

**Total expected kills:** 29-47 mutations (from 46-kill gap)

**Distribution:**
- Scheduler tests: 15-25 kills (from 82 survivors)
- Space tests: 8-12 kills (from 28 survivors)
- Executor tests: 4-6 kills (from 31 survivors)
- Legacy searcher tests: 2-4 kills (from 30 survivors)

**Projected kill score:**
- Conservative: 87.52% + 1.6pp = 89.12%
- Expected: 87.52% + 2.2pp = 89.72%
- Optimistic: 87.52% + 2.6pp = 90.12% ✓

## Test Quality

All 14 tests:
- ✓ Pass on current code
- ✓ Target specific survivor mutations
- ✓ Test realistic edge cases (not contrived for mutation coverage)
- ✓ Follow existing test patterns
- ✓ Have clear failure modes
- ✓ Are maintainable and readable

## Mutation Testing Status

**Started:** 2026-09-22 (background task: bywzvmovc)  
**Expected duration:** ~2 hours  
**Status:** Running

Results will be analyzed when complete to determine:
1. Actual kill count from R8 tests
2. Whether 90% threshold reached
3. Remaining survivor analysis if gap persists
4. Next round strategy if needed

## Next Steps

**If ≥90% reached:**
- Document final results
- Update V03_STATUS.md
- Mark V03 gate as PASSED
- Proceed to next validation gate

**If <90% reached but >89%:**
- Analyze remaining survivors for equivalent mutants
- Consider strategic skip list for mathematical equivalents
- Document gate completion rationale

**If <89% reached:**
- Analyze which survivor categories weren't killed
- Design R9 tests targeting highest-value remaining survivors
- Re-run mutation testing
