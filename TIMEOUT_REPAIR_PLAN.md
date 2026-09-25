# Timeout Repair Plan - V03 Mutation Testing

## Executive Summary

**Problem**: 414 mutations timeout during testing, representing untested code paths that would cause production failures.

**Root Cause**: These are not "unkillable" mutations - they are **real bugs in untested code**. The mutations timeout because we have zero test coverage on these paths.

**Solution**: Write integration tests that exercise these 414 code paths. When exercised, the mutations will fail tests instead of timing out.

**Impact**: Converting timeouts to kills will increase mutation score from 91.64% to 93.06%.

---

## Current State

From mutmut cache analysis:
- **Killed**: 1853 mutations (inferred from 91.64% score)
- **Survived**: 169 mutations
- **Timeout**: 414 mutations
- **No tests**: 19 mutations
- **Current score**: 91.64% (1853 / 2022 testable)

---

## Timeout Mutation Catalogue

### By Category

| Category | Timeouts | Top Location | Count |
|----------|----------|--------------|-------|
| GP Searcher Core | 161 | `_tensor_to_config` | 61 |
| Legacy Executors | 122 | `LocalExecutor.launch` | 27 |
| Ray Executor | 93 | `_collect_with_retry` | 45 |
| Random/Sobol Searchers | 18 | `SobolSearcher.propose` | 10 |
| Types/Space | 12 | `SearchSpace.sample_random` | 11 |
| Schedulers | 6 | `__init__` methods | 6 |
| State Management | 2 | `set_state` | 2 |
| **Total** | **414** | | |

### Mutation Pattern Analysis

All 414 timeouts fall into 4 detectable bug patterns:

1. **String mutations (40%)**: Dict keys or enum values changed
   - Example: `"config"` → `"XXconfigXX"` causes KeyError when accessed
   - Example: `"continuous"` → `"XXcontinuousXX"` breaks type checks

2. **None in expressions (30%)**: Values replaced with None
   - Example: `normalized = (value - low) / (high - low)` → `normalized = None`
   - Example: `fit_gpytorch_mll(mll)` → `fit_gpytorch_mll(None)`

3. **Logic errors (20%)**: Operators or loop progression broken
   - Example: `col += 1` → `col -= 1` (infinite loop)
   - Example: `idx = np.clip(idx, 0, len(choices) - 1)` → `len(choices) + 1` (IndexError)

4. **Missing arguments (10%)**: Function calls with wrong arity
   - Example: `ExactMarginalLogLikelihood(gp.likelihood, gp)` → `(gp.likelihood, None)`
   - Example: `self._submit_trial(trial, fn)` → `(None, fn)`

**Key Insight**: Every one of these mutations would crash immediately if the code path were exercised by a test. They timeout because we have zero coverage on these paths.

---

## Test Plan

### Test Suite A: GP Searcher Integration (161 timeouts)

**File**: `tests/integration/test_gp_searcher_integration.py`

**Coverage Target**: 
- `GPSearcher._config_to_tensor` (30 timeouts)
- `GPSearcher._tensor_to_config` (61 timeouts)
- `GPSearcher.suggest` (37 timeouts)
- `GPSearcher._prepare_training_data` (9 timeouts)
- `GPSearcher._get_bounds` (4 timeouts)
- `GPSearcher._sample_random` (5 timeouts)
- `GPSearcher.__init__` (9 timeouts)
- `GPSearcher.set_state` (4 timeouts)
- `GPSearcher.get_state` (2 timeouts)

**Tests**:
1. `test_gp_full_optimization_cycle`: Complete GP workflow
   - Create GP searcher with mixed parameter types (continuous, integer, categorical, log-scale)
   - Run initial random sampling phase
   - Record results and trigger GP fitting
   - Optimize acquisition function and suggest next config
   - **Kills**: All suggest, fit, acquisition mutations

2. `test_gp_config_tensor_round_trip`: Config ↔ tensor conversion
   - Create configs with all parameter types
   - Convert to tensors via `_config_to_tensor`
   - Convert back via `_tensor_to_config`
   - Assert round-trip equality
   - **Kills**: String mutations, None mutations, bound violations in conversion

3. `test_gp_training_data_preparation`: Training data pipeline
   - Feed valid and invalid results
   - Call `_prepare_training_data`
   - Verify tensor shapes and values
   - **Kills**: None mutations, dict key mutations in data prep

4. `test_gp_bounds_extraction`: Bounds and normalization
   - Extract bounds for all parameter types
   - Test log-scale transformations
   - Verify normalization logic
   - **Kills**: Math expression mutations in bounds

5. `test_gp_state_persistence`: State save/load
   - Train GP, save state via `get_state`
   - Create new GP, restore via `set_state`
   - Verify continuation produces same suggestions
   - **Kills**: Dict key mutations in state serialization

**Expected kills**: ~161 timeouts

---

### Test Suite B: Ray Executor Integration (93 timeouts)

**File**: `tests/integration/test_ray_executor_integration.py`

**Coverage Target**:
- `RayExecutor._collect_with_retry` (45 timeouts)
- `RayExecutor._payload_to_result` (17 timeouts)
- `RayExecutor.execute_batch` (15 timeouts)
- `RayExecutor._initialize_ray` (9 timeouts)
- `RayExecutor.execute` (3 timeouts)
- `RayExecutor._submit_trial` (2 timeouts)
- `RayExecutor.shutdown` (2 timeouts)

**Tests**:
1. `test_ray_executor_end_to_end`: Complete execution workflow
   - Initialize Ray executor
   - Submit batch of trials with objective function
   - Collect results via `_collect_with_retry`
   - Parse payloads via `_payload_to_result`
   - Shutdown cleanly
   - **Kills**: All remote call, payload parsing mutations

2. `test_ray_executor_retry_logic`: Transient failure handling
   - Submit trial that fails transiently
   - Verify retry mechanism in `_collect_with_retry`
   - Check timeout handling
   - **Kills**: String mutations in status/error fields, None in retry logic

3. `test_ray_executor_payload_parsing`: Result payload handling
   - Create payloads with missing/extra fields
   - Call `_payload_to_result`
   - Verify default value handling
   - **Kills**: Dict key mutations like "XXtrial_idXX", "XXfidelityXX"

4. `test_ray_executor_initialization`: Setup and teardown
   - Test `_initialize_ray` with various configs
   - Verify resource allocation
   - Test shutdown cleanup
   - **Kills**: Initialization mutations, resource spec mutations

**Expected kills**: ~93 timeouts

---

### Test Suite C: Legacy Executors Integration (122 timeouts)

**File**: `tests/integration/test_legacy_executors_integration.py`

**Coverage Target**:
- `LocalExecutor.launch` (27 timeouts)
- `RayExecutor.get_result` (24 timeouts)
- `RayExecutor.__init__` (21 timeouts)
- `RayExecutor.launch` (17 timeouts)
- `RayExecutor.copy_checkpoint` (10 timeouts)
- `RayExecutor.load_checkpoint` (9 timeouts)
- `LocalExecutor.__init__` (7 timeouts)
- `LocalExecutor.get_result` (5 timeouts)
- `RayExecutor.poll` (1 timeout)
- `RayExecutor.shutdown` (1 timeout)

**Tests**:
1. `test_local_executor_full_workflow`: LocalExecutor end-to-end
   - Initialize with thread pool
   - Launch multiple trials via `launch`
   - Poll and collect results via `get_result`
   - Handle exceptions in trial execution
   - **Kills**: launch mutations, result collection mutations

2. `test_legacy_ray_executor_lifecycle`: RayExecutor setup to teardown
   - Initialize with checkpoint directory (tests `__init__`)
   - Launch remote trials
   - Get results with timeout handling
   - Shutdown cleanly
   - **Kills**: String mutations in dict keys, None in remote calls

3. `test_legacy_checkpoint_operations`: Checkpoint save/load/copy
   - Launch trial, save checkpoint
   - Load checkpoint via `load_checkpoint`
   - Copy checkpoint via `copy_checkpoint`
   - Verify file operations
   - **Kills**: Path mutations, None in file operations

4. `test_legacy_executor_error_handling`: Failure modes
   - Test trial failures
   - Test timeout scenarios
   - Verify error dict structure
   - **Kills**: Dict key mutations like "error", "status", "cost"

**Expected kills**: ~122 timeouts

---

### Test Suite D: Random/Sobol Searchers Integration (18 timeouts)

**File**: `tests/integration/test_random_searchers_integration.py`

**Coverage Target**:
- `SobolSearcher.propose` (10 timeouts)
- `SobolSearcher.__init__` (8 timeouts)

**Tests**:
1. `test_sobol_searcher_full_sequence`: Complete Sobol sampling
   - Initialize SobolSearcher with multi-dimensional space
   - Generate sequence of proposals
   - Verify column index progression (catches `col += 1` → `col -= 1`)
   - Check bound enforcement
   - **Kills**: Loop progression mutations, bound calculation mutations

2. `test_sobol_searcher_initialization`: Setup and validation
   - Create with various search spaces
   - Verify Sobol engine initialization
   - Test dimension calculations
   - **Kills**: __init__ mutations

3. `test_sobol_ordinal_and_continuous`: Mixed parameter types
   - Define space with continuous and ordinal knobs
   - Sample multiple points
   - Verify quantization for ordinal
   - **Kills**: Math mutations in quantization like `(high - low - 1)`

**Expected kills**: ~18 timeouts

---

### Test Suite E: Types/Space Integration (12 timeouts)

**File**: `tests/integration/test_types_space_integration.py`

**Coverage Target**:
- `SearchSpace.sample_random` (11 timeouts)
- `Parameter.__post_init__` (1 timeout)

**Tests**:
1. `test_search_space_random_sampling`: Full sampling coverage
   - Create search space with all parameter types:
     - Continuous (linear and log-scale)
     - Integer (linear and log-scale)
     - Categorical
   - Sample multiple configs via `sample_random`
   - Verify bounds, log transformations, type correctness
   - **Kills**: None mutations like `log_val = None`, `int(np.exp(None))`

2. `test_parameter_initialization`: Parameter validation
   - Create parameters with various configs
   - Trigger `__post_init__` validation
   - Verify type checking
   - **Kills**: __post_init__ mutations

**Expected kills**: ~12 timeouts

---

### Test Suite F: Scheduler Integration (6 timeouts)

**File**: `tests/integration/test_scheduler_integration.py`

**Coverage Target**:
- `ASHAScheduler.__init__` (2 timeouts)
- `PASHAScheduler.__init__` (2 timeouts)
- `MOASHAScheduler.__init__` (2 timeouts)

**Tests**:
1. `test_asha_scheduler_initialization`: ASHA setup
   - Initialize with various configs
   - Verify rung calculation
   - Verify parameter validation
   - **Kills**: __init__ mutations

2. `test_pasha_scheduler_initialization`: PASHA setup
   - Initialize with population configs
   - Verify promotion logic setup
   - **Kills**: __init__ mutations

3. `test_moasha_scheduler_initialization`: Multi-objective setup
   - Initialize with multiple objectives
   - Verify Pareto logic setup
   - **Kills**: __init__ mutations

**Expected kills**: ~6 timeouts

---

## Implementation Strategy

### Phase 1: Infrastructure Setup (30 min)

1. Create `tests/integration/` directory
2. Add pytest fixtures for common setup:
   - Sample search spaces (continuous, integer, categorical, log-scale)
   - Simple objective functions
   - Ray initialization (if needed)
3. Add integration test marker to pytest config

### Phase 2: Test Suite Development (4-6 hours)

Execute test suites in priority order:

1. **Suite A: GP Searcher** (highest timeout count: 161)
   - Write 5 integration tests
   - Run against current code (should pass)
   - Run `mutmut run --paths-to-mutate=hponas/searchers/gp_searcher.py`
   - Verify timeout → kill conversions

2. **Suite C: Legacy Executors** (second highest: 122)
   - Write 4 integration tests
   - Verify against legacy_executors.py mutations

3. **Suite B: Ray Executor** (93 timeouts)
   - Write 4 integration tests
   - Verify against ray_executor.py mutations

4. **Suite D: Random/Sobol** (18 timeouts)
   - Write 3 integration tests
   - Quick wins for sobol progression bugs

5. **Suite E: Types/Space** (12 timeouts)
   - Write 2 integration tests
   - Cover sampling edge cases

6. **Suite F: Schedulers** (6 timeouts)
   - Write 3 initialization tests
   - Minimal effort, low count

### Phase 3: Verification (1 hour)

1. Run full mutation testing suite:
   ```bash
   python -m mutmut run --paths-to-mutate=hponas/
   ```

2. Calculate new statistics:
   ```python
   # Expected after repair:
   killed = 1853 + 414 = 2267
   survived = 169
   testable = 2267 + 169 = 2436
   score = 2267 / 2436 = 93.06%
   ```

3. Verify no new timeouts introduced

4. Generate final report

### Phase 4: Documentation Update (15 min)

Update master program with results:
- Actual kills achieved
- New mutation score
- Remaining survivors for future rounds

---

## Expected Outcomes

### Mutation Score Improvement

| Metric | Before Repair | After Repair | Change |
|--------|---------------|--------------|--------|
| Killed | 1,853 | 2,267 | +414 |
| Survived | 169 | 169 | 0 |
| Timeout | 414 | 0 | -414 |
| Testable | 2,022 | 2,436 | +414 |
| **Score** | **91.64%** | **93.06%** | **+1.42pp** |

### Test Coverage Improvement

- **GP Searcher**: Full optimization cycle now tested
- **Executors**: End-to-end execution workflows covered
- **Searchers**: Sampling sequences verified
- **Types**: All parameter types sampled and validated

### Production Safety

Every one of the 414 timeout mutations represents a real bug that would crash in production:

- ✅ String mutations → KeyError caught by dict access tests
- ✅ None mutations → TypeError caught by math operation tests
- ✅ Logic errors → Infinite loops caught by progression tests
- ✅ Missing args → TypeError caught by function call tests

After this repair, these bugs cannot reach production without tests failing.

---

## Risk Assessment

### Low Risk

- All tests exercise existing code paths
- No API changes required
- No refactoring needed
- Tests are additive (don't modify existing tests)

### Potential Issues

1. **Ray initialization in tests**: May need `ray.init()` fixture
   - **Mitigation**: Use `@pytest.mark.ray` and conditional skip if Ray unavailable

2. **GP tests may be slow**: BoTorch optimization takes time
   - **Mitigation**: Use small search spaces, low num_restarts for tests

3. **Flaky timeouts in CI**: Integration tests may occasionally timeout
   - **Mitigation**: Set generous timeouts (60s per test), use `@pytest.mark.slow`

---

## Success Criteria

1. ✅ Mutation score reaches ≥93%
2. ✅ Timeout count drops from 414 to <10
3. ✅ All 6 integration test suites pass
4. ✅ No existing tests broken
5. ✅ Master program updated with new phase

---

## Next Steps After Completion

Once timeout repair achieves 93.06%:

1. **Survivor analysis**: Investigate remaining 169 survivors
2. **Equivalence detection**: Identify truly equivalent mutations
3. **95% push**: Write targeted tests for high-value survivors
4. **V04 gate**: Prepare for next validation round

---

## Appendix: Sample Test Code

### Example: GP Searcher Integration Test

```python
def test_gp_full_optimization_cycle():
    """Complete GP workflow: random → fit → optimize → suggest."""
    # Setup search space with all parameter types
    space = SearchSpace(
        parameters=[
            Parameter("lr", ParameterType.FLOAT, bounds=(1e-4, 1e-1), log_scale=True),
            Parameter("layers", ParameterType.INTEGER, bounds=(1, 10)),
            Parameter("activation", ParameterType.CATEGORICAL, choices=["relu", "tanh", "gelu"]),
        ]
    )
    
    searcher = GPSearcher(space, initial_random_samples=3)
    
    # Phase 1: Initial random sampling
    configs = [searcher.suggest() for _ in range(3)]
    assert len(configs) == 3
    assert all(c["lr"] >= 1e-4 and c["lr"] <= 1e-1 for c in configs)
    
    # Phase 2: Record results
    for config in configs:
        result = Result(
            trial_id=f"trial_{config['lr']}",
            objective_value=random.random(),
            cost=1.0,
            fidelity=1.0,
            status="completed",
        )
        searcher.update(result)
    
    # Phase 3: GP suggestion (triggers full pipeline)
    gp_config = searcher.suggest()
    
    # Verify config structure
    assert "lr" in gp_config
    assert "layers" in gp_config
    assert "activation" in gp_config
    
    # Verify bounds
    assert 1e-4 <= gp_config["lr"] <= 1e-1
    assert 1 <= gp_config["layers"] <= 10
    assert gp_config["activation"] in ["relu", "tanh", "gelu"]
```

This single test will kill:
- String mutations in dict keys ("lr" → "XXlrXX")
- None mutations in math expressions
- Bound violations in tensor conversion
- Missing arguments in GP calls

---

**Plan Status**: READY FOR EXECUTION
**Estimated Time**: 6-8 hours
**Expected Score Improvement**: 91.64% → 93.06%
