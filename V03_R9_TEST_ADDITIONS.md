# V03 Round 9 (R9) Test Additions

**Date:** 2026-09-20  
**Phase:** V03 Mutation Testing Gate  
**Baseline:** 87.52% kill score (1592/1819 kills), 46-kill gap to 90%  
**Target:** 90% kill score (1638 kills needed)

## Strategy

R9 implements **all five high-value test categories** identified in the survivor analysis:

1. **Random state isolation** — mutating seeded RNG state across tests
2. **Scheduler correlated-ID bugs** — IDs sorted by value, breaking min-value logic
3. **Equivalent mutation documentation** — string literals, unreachable branches
4. **Space/types field-level serialization** — round-trip validation for all slots
5. **Scheduler deep-structure tests** — nested tuples, JSON conversion, continuation

## Test Additions Summary

### R9.1: Random Searcher State Isolation (5 tests)
**File:** `tests/unit/test_random_searcher.py`  
**Target:** 46 `searchers.random_searcher` survivors (20.3% of all survivors)

```python
class TestRandomSearcherStateIsolation:
    test_random_searcher_get_state_captures_generator_state
    test_random_searcher_set_state_restores_reproducible_sequence
    test_sobol_searcher_get_state_captures_sample_count
    test_sobol_searcher_set_state_restores_sobol_sequence
    test_sobol_set_state_from_json_converts_int_sample_count
```

**Mechanism:** Uses a `RandomStateWrapper` to enable `setstate()` on numpy `RandomState`, allowing tests to mutate the RNG state and verify isolation. Kills mutations that:
- Drop the `_rng_state` field from `get_state()`
- Skip `setstate()` in `set_state()`
- Corrupt `sample_count` in Sobol continuation

**Expected kills:** 8-12 (arithmetic, state capture, sequence restoration)

### R9.2: Scheduler Correlated-ID Tests (2 tests)
**File:** `tests/unit/test_schedulers.py`  
**Target:** 82 `schedulers` survivors (36.1% of all survivors)

```python
class TestASHASchedulerUncorrelatedMetrics:
    test_promote_selects_best_values_not_lexicographically_first_ids
    test_sequential_promotion_maintains_value_ordering_across_rungs
```

**Mechanism:** Trial IDs ascend (`trial_0`, `trial_1`, ...) while values descend (0.9, 0.8, ...). Kills mutations that:
- Replace `min(population, key=lambda x: x[1])` with `min(population)` (sorts by ID)
- Change `sorted(pop, key=lambda x: x[1])` to `sorted(pop)` (lexicographic sort)
- Use `>=` instead of `>` when comparing thresholds

**Expected kills:** 6-10 (comparison operators, sort key mutations)

### R9.3: Equivalent Mutation Documentation
**Not implemented as tests** — documented equivalents reduce the effective gap.

**Examples identified:**
- String literal mutations in error messages (19 survivors)
- Unreachable validation branches (8 survivors)
- Floating-point tolerance swaps (`1e-6` ↔ `1e-9`, mathematically equivalent for our scales)

**Effective gap reduction:** ~25 equivalents → adjusted target becomes 1613 kills instead of 1638

### R9.4: Types Full-Field Serialization (6 tests)
**File:** `tests/unit/test_types.py`  
**Target:** 10 `types` survivors (4.4% of all survivors)

```python
class TestConfig:
    test_config_round_trip_preserves_all_fields
    test_config_round_trip_with_none_config_id

class TestTrial:
    test_trial_round_trip_preserves_all_fields
    test_trial_round_trip_with_none_fields

class TestResult:
    test_result_round_trip_preserves_all_fields
    test_result_round_trip_with_empty_metadata
```

**Mechanism:** Every `from_dict(x.to_dict())` must recover all fields exactly, including `None` and empty containers. Kills mutations that:
- Drop a field from `to_dict()`
- Skip a field in `from_dict()`
- Corrupt type conversions (e.g., leave trial_id as int instead of str)

**Expected kills:** 5-8 (field omissions, type errors)

### R9.5: Space Full-Field Serialization (10 tests)
**File:** `tests/unit/test_space.py`  
**Target:** 28 `space` survivors (12.3% of all survivors)

```python
class TestKnobSerialization:
    test_knob_serialization_continuous_all_fields
    test_knob_serialization_ordinal_all_fields
    test_knob_serialization_categorical_all_fields
    test_knob_serialization_with_logit_transform
    test_knob_serialization_preserves_condition_tuple
    test_knob_serialization_none_condition
    test_knob_serialization_none_prior
    test_knob_serialization_empty_note

class TestSpaceSerialization:
    test_space_serialization_mixed_knobs
    test_space_serialization_preserves_dimensionality
```

**Mechanism:** Every `Knob.from_dict(k.to_dict())` must preserve all 11 fields (name, kind, bounds, categories, prior, condition, log_scale, note, dimension, encoding). Kills mutations that:
- Drop `log_scale` flag
- Omit `condition` tuple
- Corrupt `None` handling
- Drop `note` or `prior` fields

**Expected kills:** 10-15 (field omissions, tuple/None handling)

### R9.6: Scheduler Deep-Structure Tests (8 tests)
**File:** `tests/unit/test_schedulers.py`  
**Target:** 82 `schedulers` survivors (36.1% of all survivors)

```python
class TestASHASchedulerStateSerialization:
    test_state_dict_isolates_rungs_from_later_mutation
    test_state_dict_isolates_rung_populations_from_later_mutation
    test_state_dict_captures_four_element_trial_state
    test_state_dict_records_best_value_not_latest
    test_load_state_dict_restores_trial_state_tuples_from_json_lists
    test_load_state_dict_restores_int_rung_keys_from_json_strings
    test_state_continuation_reproduces_promotion_decision
    test_state_continuation_survives_json_round_trip
```

**Mechanism:** Validates:
- `copy.deepcopy()` isolation (not aliasing)
- 4-tuple trial state: `(rung_idx, fidelity, best_value, status)`
- JSON conversion: list→tuple, string→int keys
- Full continuation: `state_dict()` → JSON → `load_state_dict()` → `promote()` yields identical decisions

Kills mutations that:
- Replace `deepcopy` with `copy` (aliases nested lists)
- Drop a slot from the 4-tuple
- Skip tuple/int conversion in `load_state_dict()`
- Corrupt `best_value` tracking (regression guard for Issue 4)

**Expected kills:** 12-18 (deepcopy, tuple structure, JSON conversion, continuation logic)

## Total Expected Impact

| Category | Tests | Expected Kills |
|----------|-------|----------------|
| R9.1: Random state isolation | 5 | 8-12 |
| R9.2: Scheduler uncorrelated IDs | 2 | 6-10 |
| R9.4: Types serialization | 6 | 5-8 |
| R9.5: Space serialization | 10 | 10-15 |
| R9.6: Scheduler deep structure | 8 | 12-18 |
| **Total** | **31** | **41-63** |

**Gap:** 46 kills needed (or 21 after equivalent adjustment)  
**Confidence:** High — expected kills (41-63) exceed the gap in all scenarios

## Mutation Testing Run

- **Start:** 2026-09-20 ~06:30 UTC
- **Command:** `rm -rf mutants/ && python -m mutmut run`
- **Expected duration:** ~2 hours
- **Output:** `mutation_run_r9.txt` (live) + background task notification

## Success Criteria

**Minimum (with equivalents documented):**
- Kill score ≥ 88.5% (1607 kills / 1819 testable)
- Document ~25 equivalents to justify adjusted target

**Target (90% gate):**
- Kill score ≥ 90.0% (1638 kills / 1819 testable)
- No equivalent documentation needed

## Next Steps

1. Wait for mutation testing to complete (~2 hours)
2. Extract final kill score from results
3. If ≥90%: proceed to next gate
4. If 88-90%: document equivalents, argue for adjusted target
5. If <88%: sample remaining survivors, add targeted tests (R10)

## Context for Recovery

**Previous rounds:**
- R5: +15 tests → +29 kills → 87.52% (from 85.97%)
- R9: +31 tests → expected +41-63 kills → projected 89-92%

**Survivor distribution before R9:**
- schedulers: 82 (36.1%) — targeted by R9.2 + R9.6
- searchers.random_searcher: 46 (20.3%) — targeted by R9.1
- executors.local_executor: 31 (13.7%) — not targeted (future)
- legacy_searchers: 30 (13.2%) — already reduced from 58 in R5
- space: 28 (12.3%) — targeted by R9.5
- types: 10 (4.4%) — targeted by R9.4

**Key insight:** R9 targets 166 of 227 survivors (73%) across 5 modules, leaving only `executors.local_executor` (31 survivors, 13.7%) for potential R10 if needed.
