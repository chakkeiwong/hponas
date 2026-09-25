# Revised V03 Strategy: Kill Timeouts, Not Just Survivors

## Critical Insight

**You were right to question the timeout explanation.** The 18% timeout rate reveals **missing defensive code and tests**. We should:

1. Write tests that force these mutations to fail fast (convert timeout → killed)
2. Add defensive checks so broken invariants raise immediately
3. This simultaneously improves kill score AND code quality

## Current Status

- Kill Score: 87.52% (1592/1819)
- Gap to 90%: 46 more kills
- Timeouts: 415 (18%)
- Survivors: 227

## The Opportunity

**Timeouts are killable mutations we're currently not testing.**

### Timeout Categories

1. **__init__ validation (52 timeouts)**
   - Missing tests for invalid seed types
   - Missing boundary value tests
   - Missing None parameter tests

2. **State serialization (8 timeouts)**
   - Missing tests for corrupted state dicts
   - No tests for None instead of dict
   - No tests for missing keys

3. **External library init (10 timeouts)**
   - No tests for Ray init failures
   - No mocked error paths for BoTorch

4. **Other operations (345 timeouts)**
   - Various defensive checks missing

### Impact Analysis

If we write tests to kill timeouts:

| Scenario | Timeouts Killed | New Score | Result |
|----------|----------------|-----------|---------|
| Conservative (50 timeouts) | 50 | 1642/1819 = 90.3% | ✅ PASS |
| Moderate (100 timeouts) | 100 | 1692/1819 = 93.0% | ✅ EXCELLENT |
| Aggressive (150 timeouts) | 150 | 1742/1819 = 95.8% | ✅ OUTSTANDING |

**We only need 46 more kills to reach 90%, but killing 50 timeouts gives us buffer.**

## Revised Plan

### Phase 1: Kill High-Value Timeouts (Target: 60 kills)

**1. Add GPSearcher Validation Tests** (20-25 kills)
```python
def test_gp_searcher_invalid_seed_type():
    """Test that GPSearcher rejects non-int seed."""
    space = SearchSpace([Knob("x", "continuous", (0, 1))])
    with pytest.raises(TypeError, match="seed must be int"):
        GPSearcher(search_space=space, seed="invalid")

def test_gp_searcher_negative_seed():
    """Test that GPSearcher rejects negative seed."""
    space = SearchSpace([Knob("x", "continuous", (0, 1))])
    with pytest.raises(ValueError, match="non-negative"):
        GPSearcher(search_space=space, seed=-1)

def test_gp_searcher_zero_initial_random():
    """Test boundary: initial_random_samples=0 should fail."""
    space = SearchSpace([Knob("x", "continuous", (0, 1))])
    with pytest.raises(ValueError, match="initial_random_samples"):
        GPSearcher(search_space=space, initial_random_samples=0)

def test_gp_searcher_one_initial_random():
    """Test boundary: initial_random_samples=1 should work."""
    space = SearchSpace([Knob("x", "continuous", (0, 1))])
    searcher = GPSearcher(search_space=space, initial_random_samples=1)
    assert searcher.initial_random_samples == 1
```

**2. Add State Corruption Tests** (10-15 kills)
```python
def test_gp_searcher_set_state_none_dict():
    """Test that set_state rejects None for trials dict."""
    searcher = GPSearcher(search_space=space, seed=42)
    corrupted_state = searcher.get_state()
    corrupted_state["trials"] = None
    
    with pytest.raises((TypeError, AttributeError)):
        searcher.set_state(corrupted_state)

def test_gp_searcher_set_state_missing_key():
    """Test that set_state rejects dict with missing keys."""
    searcher = GPSearcher(search_space=space, seed=42)
    corrupted_state = searcher.get_state()
    del corrupted_state["num_restarts"]
    
    with pytest.raises(KeyError):
        searcher.set_state(corrupted_state)
```

**3. Add Random/Sobol Validation Tests** (15-20 kills)
```python
def test_random_searcher_invalid_seed():
    """Test RandomSearcher with invalid seed types."""
    space = SearchSpace([Knob("x", "continuous", (0, 1))])
    
    with pytest.raises(TypeError):
        RandomSearcher(search_space=space, seed=[1, 2, 3])
    
    with pytest.raises(TypeError):
        RandomSearcher(search_space=space, seed=1.5)

def test_sobol_searcher_none_space():
    """Test that SobolSearcher catches None space early."""
    # This requires adding defensive check to legacy_searchers.py
    with pytest.raises((TypeError, AttributeError)):
        searcher = SobolSearcher(space=None, seed=0)
        searcher.propose(1)  # Should fail immediately
```

**4. Add Scheduler Validation Tests** (10-15 kills)
```python
def test_asha_scheduler_invalid_eta():
    """Test ASHA with invalid eta values."""
    with pytest.raises(ValueError):
        ASHAScheduler(ASHAConfig(r_min=1, r_max=27, eta=0))
    
    with pytest.raises(ValueError):
        ASHAScheduler(ASHAConfig(r_min=1, r_max=27, eta=-3))
```

### Phase 2: Add Defensive Code (Optional, if tests reveal gaps)

If tests show code doesn't fail fast, add defensive checks:

```python
# Example: Add to legacy_searchers.py SobolSearcher.__init__
def __init__(self, space: SearchSpace, seed: int = 0):
    if space is None:
        raise TypeError("space cannot be None")
    if not isinstance(space, SearchSpace):
        raise TypeError(f"space must be SearchSpace, got {type(space)}")
    self.space = space
    self.seed = seed
    self._rng = np.random.default_rng(seed)
```

### Phase 3: Run Mutation Testing

After adding tests, run mutation testing. Expected results:
- Timeouts: 415 → ~355 (-60)
- Killed: 1592 → ~1652 (+60)
- Kill Score: 87.52% → 90.9%

## Why This Is Better

**Original Plan (Option A):**
- Write 20 tests for survivors
- Expected: +20-25 kills, reach ~90%
- Time: 2-3 hours

**Revised Plan:**
- Write 20 tests for timeout/validation
- Expected: +50-60 kills, reach ~91%
- Time: 2-3 hours
- **Bonus: More robust code, better error messages**

## Next Steps

1. Create `tests/unit/test_validation_robustness.py`
2. Add 20 validation tests targeting timeout mutations
3. Run pytest to verify tests pass
4. Run mutation testing (~2 hour wait)
5. Analyze results and iterate if needed

## Success Criteria

- Kill score ≥ 90%
- Timeout rate stays < 20%
- All new tests pass
- Code fails fast on invalid input
