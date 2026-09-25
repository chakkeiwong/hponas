# V03-R10 Fast Unit Test Strategy for Timeout Repair

## Root Cause Analysis - Confirmed

The timeout mutations are NOT caused by missing test coverage. They're caused by **slow test execution**.

**Evidence:**
1. Full test suite takes >40 seconds to run
2. Mutmut timeout is 40 seconds per mutation
3. Every mutation triggers full test suite → every mutation times out
4. Integration tests (3-7s each) make the problem **worse**, not better

**Original assumption was WRONG:**
- ❌ "Timeouts = untested code paths"
- ✅ "Timeouts = test suite too slow for mutmut's timeout"

## The Real Problem

Mutmut runs the ENTIRE test suite for each mutation:
```
Mutation 1 → Run all tests → Takes 42s → TIMEOUT
Mutation 2 → Run all tests → Takes 42s → TIMEOUT
...
Mutation 414 → Run all tests → Takes 42s → TIMEOUT
```

The 414 timeout mutations in V03 baseline had test coverage, but the tests were too slow to complete within 40s.

## The Solution: Fast Isolated Unit Tests

**Goal:** Make the test suite complete in <30 seconds so mutations can be tested within the 40s timeout.

**Strategy:**
1. **Identify slow tests** - Profile current test suite
2. **Speed up critical paths** - Replace slow integration tests with fast unit tests
3. **Add missing unit tests** - For any genuinely untested code paths
4. **Optimize test execution** - Use pytest-xdist, reduce fixtures, mock heavy dependencies

## New Plan: Test Suite Performance Optimization

### Phase 1: Measure & Identify (2 hours)
**Objective:** Find what's making the test suite slow

```bash
# Profile test execution
pytest --durations=50 tests/

# Identify bottlenecks
# - Tests that use Ray/distributed execution
# - Tests that train actual GPs
# - Tests with heavy torch/botorch operations
# - Tests with sleep/wait calls
```

**Expected findings:**
- Integration tests: 3-7s each
- Property tests: might be slow with hypothesis
- Tests with actual GP training: expensive
- Tests with Ray: startup overhead

### Phase 2: Fast Unit Test Architecture (4 hours)
**Objective:** Create minimal, fast unit tests that kill timeout mutations

**Design principles:**
1. **Isolation** - Test one method at a time
2. **Mocking** - Mock expensive dependencies (GP models, Ray, torch operations)
3. **Minimal data** - Use small tensors, few iterations
4. **No I/O** - No file operations, no network
5. **Target: <100ms per test**

**Example - Fast unit test for `_tensor_to_config` (61 timeouts):**
```python
def test_tensor_to_config_bounds():
    """Test tensor conversion respects bounds - fast unit test."""
    space = SearchSpace(parameters={
        "x": Parameter("x", ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
    })
    searcher = GPSearcher(space)
    
    # Edge case: tensor at 0
    config = searcher._tensor_to_config(torch.tensor([0.0]))
    assert config["x"] == 0.0
    
    # Edge case: tensor at 1
    config = searcher._tensor_to_config(torch.tensor([1.0]))
    assert config["x"] == 1.0
    
    # Test takes <10ms, catches 20+ mutations
```

**vs Current slow integration test:**
```python
def test_gp_full_optimization_cycle():  # 3.94s
    """Complete GP workflow: random → fit → optimize → suggest."""
    # Creates GP, fits model, runs acquisition...
    # Slow but comprehensive
```

### Phase 3: Create Fast Unit Test Suite (6 hours)

**Target files with timeouts:**

#### 1. GP Searcher (145 timeouts) - 2 hours
Create `tests/unit/test_gp_searcher_unit.py`:
- `test_tensor_to_config_*` - 10 tests, <100ms total, kills 61 timeouts
- `test_config_to_tensor_*` - 8 tests, <100ms total, kills 30 timeouts
- `test_prepare_training_data_*` - 4 tests, <100ms total, kills 9 timeouts
- `test_get_bounds_*` - 2 tests, <50ms total, kills 4 timeouts
- `test_sample_random_*` - 2 tests, <50ms total, kills 5 timeouts
- `test_state_serialization_*` - 3 tests, <50ms total, kills 6 timeouts
- `test_suggest_logic_*` - 5 tests, mock GP, <100ms total, kills 30 timeouts

**Key technique:** Mock the expensive GP operations:
```python
@patch('hponas.searchers.gp_searcher.SingleTaskGP')
@patch('hponas.searchers.gp_searcher.fit_gpytorch_mll')
def test_suggest_with_gp_mocked(mock_fit, mock_gp):
    """Test suggest logic without actually training GP."""
    # Fast: no real GP training
    # Still catches mutations in suggest() logic
```

#### 2. Ray Executor (93 timeouts) - 1.5 hours
Create `tests/unit/test_ray_executor_unit.py`:
- Mock Ray initialization (slow startup)
- Test task submission logic without actual Ray cluster
- Test result retrieval logic with fake futures
- Test cleanup without real actor termination

#### 3. Legacy Executors (122 timeouts) - 1.5 hours
Create `tests/unit/test_legacy_executors_unit.py`:
- Mock subprocess calls
- Test state machine logic
- Test error handling paths
- No actual process spawning

#### 4. Other modules (48 timeouts) - 1 hour
- `test_types_unit.py` - SearchSpace sampling logic
- `test_schedulers_unit.py` - ASHA/Hyperband logic with mocked trials
- `test_space_unit.py` - Parameter conversion logic

### Phase 4: Optimize Existing Tests (2 hours)
**Objective:** Make current tests faster

1. **Add pytest markers for slow tests:**
```python
@pytest.mark.slow
def test_gp_full_optimization_cycle():
    ...
```

2. **Update pytest configuration:**
```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

3. **Configure mutmut to skip slow tests:**
```toml
[tool.mutmut]
pytest_add_cli_args = [
    "-m", "not slow",  # Skip slow tests during mutation testing
    # ... other args
]
```

4. **Use pytest-xdist for parallel execution:**
```toml
[tool.mutmut]
pytest_add_cli_args = [
    "-n", "auto",  # Parallel test execution
    "-m", "not slow",
]
```

### Phase 5: Validate & Measure (2 hours)

1. **Verify test suite speed:**
```bash
pytest tests/unit/ -m "not slow" --durations=20
# Target: Complete in <20 seconds
```

2. **Run mutation test on GP searcher only:**
```bash
# Configure to test only GP searcher
rm -rf .mutmut-cache mutants/
python -m mutmut run
```

3. **Expected results:**
- GP searcher: 145 timeouts → <20 timeouts
- Fast tests catch mutations quickly
- Slow integration tests still exist for confidence but aren't run during mutation testing

4. **Scale to full suite:**
```bash
# Full mutation test with fast unit tests
python -m mutmut run
```

**Expected final score:**
- Baseline: 1853 killed / 2022 testable = 91.64%, 414 timeouts
- After optimization: 2000+ killed / 2022 testable = 98.9%, <20 timeouts

## Implementation Timeline

**Total: 17.5 hours = 2-3 days**

### Day 1 (6 hours): Analysis & GP Searcher
- ✅ Profile test suite (1 hour)
- ✅ Design fast unit test architecture (1 hour)
- ✅ Write GP searcher fast unit tests (2 hours)
- ✅ Validate GP improvements (1 hour)
- ✅ Update master program (1 hour)

### Day 2 (6 hours): Executors & Other Modules
- ✅ Write Ray executor fast unit tests (1.5 hours)
- ✅ Write Legacy executor fast unit tests (1.5 hours)
- ✅ Write Types/Schedulers/Space fast unit tests (1 hour)
- ✅ Optimize existing tests (2 hours)

### Day 3 (5.5 hours): Validation & Final Run
- ✅ Full test suite optimization validation (1 hour)
- ✅ Run complete mutation test (2 hours)
- ✅ Analyze results (1 hour)
- ✅ Update master program with final scores (0.5 hour)
- ✅ V03 Gate checkpoint (1 hour)

## Key Success Metrics

1. **Test suite speed:** <30 seconds for full run (excluding slow-marked tests)
2. **Mutation test timeout reduction:** 414 → <20 timeouts
3. **Kill rate improvement:** 91.64% → 98.9%+
4. **Fast unit test count:** 100+ new tests, all <100ms
5. **Test coverage maintained:** No reduction in actual coverage

## Risk Mitigation

**Risk 1:** Fast unit tests might miss integration issues
**Mitigation:** Keep slow integration tests but mark them `@pytest.mark.slow`, run them separately in CI

**Risk 2:** Mocking might make tests less realistic
**Mitigation:** Use property-based testing for mocked components, ensure mocks match real behavior

**Risk 3:** Test suite might still be too slow
**Mitigation:** Profile after each phase, adjust strategy, consider pytest-xdist parallelization

## Comparison: Old Plan vs New Plan

### Old Plan (WRONG):
- ❌ Add integration tests (slower)
- ❌ Assumed timeouts = missing coverage
- ❌ Would make problem worse
- ❌ Expected: 414 → 10 timeouts (FALSE)

### New Plan (CORRECT):
- ✅ Add fast unit tests (faster)
- ✅ Optimize test execution speed
- ✅ Mock expensive operations
- ✅ Expected: 414 → <20 timeouts (REALISTIC)

## Next Steps

1. Archive incorrect V03-R10 work
2. Update master program with new strategy
3. Begin Day 1 implementation
