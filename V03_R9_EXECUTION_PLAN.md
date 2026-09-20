# V03-R9 Execution Plan - Kill the Killable

**Date:** 2026-09-20  
**Goal:** Raise unadjusted kill score from 87.52% to ≥95%  
**Target:** 104 killable mutations identified in R8 analysis

---

## Execution Order (Optimized for Dependency)

### Phase 1: Quick Wins (6-8 hours)

**R9.4: Serialization Round-Trips (3-4 hours)**
- Largest impact: ~35-40 kills from 11 sampled mutations
- No infrastructure needed
- Pattern is mechanical and repeatable
- Files: test_space.py, test_types.py, test_random_searcher.py, test_legacy_searchers.py

**R9.1: Tighten Assertions (1-2 hours)**
- Second largest: ~15-20 kills
- Simple edits to existing tests
- File: test_schedulers.py

**R9.2: De-correlate Test Data (1-2 hours)**
- ~10-15 kills
- Simple edits to existing tests
- File: test_schedulers.py

**Phase 1 Target:** 60-75 kills → ~91-92% unadjusted

---

### Phase 2: Infrastructure Work (4-6 hours)

**R9.3: Dependency Argument Capture (2-3 hours)**
- ~8-12 kills
- Requires mock/spy infrastructure
- Files: test_random_searcher.py, test_legacy_searchers.py

**R9.5: State Divergence Detection (2-3 hours)**
- ~15-20 kills
- Uses existing state methods, adds continuation logic
- Files: test_random_searcher.py, test_legacy_searchers.py, test_schedulers.py

**Phase 2 Target:** +23-32 kills → ~93-95% unadjusted

---

### Phase 3: Deep Cases (2-3 hours)

**R9.6: Deep Structure Edge Cases (2-3 hours)**
- ~10-15 kills
- Increase test complexity (4-5 rungs, multiple placements)
- File: test_schedulers.py

**Phase 3 Target:** +10-15 kills → ~95-97% unadjusted

---

## Detailed Task Breakdown

### R9.4: Serialization Round-Trips

**Files to update:**
1. `tests/unit/test_space.py`
   - Add `test_knob_serialization_all_fields_continuous()`
   - Add `test_knob_serialization_all_fields_ordinal()`
   - Add `test_knob_serialization_all_fields_categorical()`
   - Add `test_space_serialization_mixed_knobs()`
   - Add `test_knob_with_condition_serialization()`
   - Add `test_knob_with_prior_serialization()`

2. `tests/unit/test_types.py`
   - Add `test_trial_id_serialization()`
   - Add `test_config_serialization_all_types()`

3. `tests/unit/test_random_searcher.py`
   - Add `test_random_searcher_state_all_fields()`
   - Add `test_sobol_searcher_state_all_fields()`

4. `tests/unit/test_legacy_searchers.py`
   - Add `test_legacy_random_searcher_state_all_fields()`
   - Add `test_legacy_sobol_searcher_state_all_fields()`

**Pattern for each test:**
```python
def test_X_serialization_all_fields():
    """Verify all fields survive to_dict → from_dict round-trip."""
    # 1. Create instance with ALL fields populated (non-defaults)
    obj = X(field1=non_default, field2=non_default, ...)
    
    # 2. Serialize
    serialized = obj.to_dict()
    
    # 3. Deserialize
    restored = X.from_dict(serialized)
    
    # 4. Assert EVERY field matches
    assert restored.field1 == obj.field1
    assert restored.field2 == obj.field2
    ...
```

**Expected kills:** 35-40 (11 sampled × 3.2 extrapolation)

---

### R9.1: Tighten Assertions

**File:** `tests/unit/test_schedulers.py`

**Changes needed:**
1. Scan for `>=`, `<=`, `>`, `<` assertions
2. Replace with exact equality where deterministic
3. For non-deterministic, use tight upper+lower bounds

**Examples:**
- `assert len(promoted) >= 1` → `assert len(promoted) == 2` (if deterministic)
- `assert value > 0` → `assert value == expected_value`
- `assert budget >= 1` → `assert budget == rungs[rung_idx + 1]`

**Expected kills:** 15-20

---

### R9.2: De-correlate Test Data

**File:** `tests/unit/test_schedulers.py`

**Changes needed:**
1. Find tests that use sequential trial IDs with sequential values
2. Replace with non-correlated data:
   - Trial IDs: `"trial_a", "trial_b", "trial_c"`
   - OR use UUIDs
   - OR reverse score order: `[10.0, 5.0, 2.0]` for sequential IDs

**Examples:**
```python
# Before
trials = [("trial_0", 1.0), ("trial_1", 2.0), ("trial_2", 3.0)]

# After
trials = [("trial_a", 3.0), ("trial_b", 1.0), ("trial_c", 2.0)]
```

**Expected kills:** 10-15

---

### R9.3: Dependency Argument Capture

**Files:** `test_random_searcher.py`, `test_legacy_searchers.py`

**Infrastructure needed:**
```python
from unittest.mock import patch, MagicMock

def test_random_searcher_rng_seed_range():
    """Verify RNG initialized with seed in valid range [0, 2**31)."""
    with patch('numpy.random.default_rng') as mock_rng:
        mock_rng.return_value = MagicMock()  # Mock RNG instance
        
        searcher = RandomSearcher(space, seed=42)
        
        # Check seed argument
        mock_rng.assert_called_once()
        args, kwargs = mock_rng.call_args
        seed = args[0] if args else kwargs.get('seed')
        
        assert 0 <= seed < 2**31
```

**Tests to add:**
1. `test_random_searcher_rng_seed_range()`
2. `test_sobol_searcher_rng_seed_range()`
3. `test_legacy_random_searcher_rng_seed_range()`
4. `test_legacy_sobol_searcher_rng_seed_range()`

**Expected kills:** 8-12

---

### R9.5: State Divergence Detection

**Files:** `test_random_searcher.py`, `test_legacy_searchers.py`, `test_schedulers.py`

**Pattern:**
```python
def test_X_state_continuation():
    """Verify restored state continues same sequence as original."""
    # 1. Create instance, draw N samples
    obj = X(...)
    _ = [obj.suggest() for _ in range(5)]
    
    # 2. Save state
    state = obj.get_state()
    
    # 3. Continue from original
    expected = [obj.suggest() for _ in range(3)]
    
    # 4. Restore into fresh instance (different initial seed)
    obj2 = X(...)  # different seed
    obj2.set_state(state)
    
    # 5. Verify continuation matches
    actual = [obj2.suggest() for _ in range(3)]
    assert actual == expected
```

**Tests to add:**
1. `test_random_searcher_state_continuation()`
2. `test_sobol_searcher_state_continuation()`
3. `test_legacy_random_searcher_state_continuation()`
4. `test_legacy_sobol_searcher_state_continuation()`
5. `test_asha_state_continuation()`
6. `test_pasha_state_continuation()`

**Expected kills:** 15-20

---

### R9.6: Deep Structure Edge Cases

**File:** `tests/unit/test_schedulers.py`

**Changes needed:**
1. Increase rung count from 2-3 to 4-5
2. Place trials at different rungs explicitly
3. Test promotion from multiple source rungs
4. Test with paused trials at non-zero rungs

**New tests to add:**
1. `test_asha_promotion_from_middle_rungs()`
2. `test_asha_off_by_one_at_penultimate_rung()`
3. `test_pasha_promotion_with_multi_rung_paused()`
4. `test_asha_control_flow_with_4_rungs()`

**Expected kills:** 10-15

---

## Validation Strategy

After each phase:
1. Run affected test file: `pytest tests/unit/test_X.py -v`
2. Confirm all new tests pass
3. Run full test suite: `pytest tests/`
4. After Phase 3, run full mutation testing: `python -m mutmut run`

**Success Criteria:**
- All tests pass ✅
- Unadjusted kill score ≥ 95%
- Timeout rate ≤ 20%

---

## Time Estimate

- Phase 1: 6-8 hours (Day 1)
- Phase 2: 4-6 hours (Day 2 morning)
- Phase 3: 2-3 hours (Day 2 afternoon)
- Validation: 2-3 hours (mutation testing run)

**Total:** 14-20 hours over 2-3 days

---

## Status Tracking

- [ ] R9.4: Serialization Round-Trips
  - [ ] test_space.py (6 tests)
  - [ ] test_types.py (2 tests)
  - [ ] test_random_searcher.py (2 tests)
  - [ ] test_legacy_searchers.py (2 tests)
- [ ] R9.1: Tighten Assertions (test_schedulers.py)
- [ ] R9.2: De-correlate Test Data (test_schedulers.py)
- [ ] R9.3: Dependency Argument Capture (4 tests)
- [ ] R9.5: State Divergence Detection (6 tests)
- [ ] R9.6: Deep Structure Edge Cases (4 tests)
- [ ] Final mutation testing run
- [ ] Documentation update

---
