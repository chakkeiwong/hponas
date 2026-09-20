# V03 Defensive Programming Implementation Plan

**Date:** 2026-09-21  
**Goal:** Add input validation to convert 150-200 timeouts into fast kills, reaching 90%+ kill score

## Current Status
- Kill score: 87.52% (1592/1819)
- Gap to 90%: 46 kills
- Timeouts: 394 (17.8%)
- Target conversions: 150-200 timeouts → kills
- Expected final score: 91-92%

## Implementation Strategy

### Phase 1: High-Impact Validation (1 hour, ~100 timeout conversions)

Add validation to the 3 modules with highest timeout counts:

#### 1.1 GPSearcher (141 timeouts → ~80 kills)

**File:** `hponas/searchers/gp_searcher.py`

**Constructor validation:**
```python
def __init__(
    self,
    search_space: SearchSpace,
    seed: Optional[int] = None,
    initial_random_samples: int = GP_DEFAULT_INITIAL_RANDOM,
    num_restarts: int = GP_DEFAULT_NUM_RESTARTS,
    kernel: str = GP_DEFAULT_KERNEL,
):
    # Validate BEFORE calling parent or storing
    if seed is not None:
        if not isinstance(seed, int):
            raise TypeError(f"seed must be int or None, got {type(seed).__name__}")
        if seed < 0:
            raise ValueError(f"seed must be non-negative, got {seed}")
    
    if not isinstance(initial_random_samples, int) or initial_random_samples < 1:
        raise ValueError(f"initial_random_samples must be positive int, got {initial_random_samples}")
    
    if not isinstance(num_restarts, int) or num_restarts < 1:
        raise ValueError(f"num_restarts must be positive int, got {num_restarts}")
    
    if kernel != "matern52":
        raise ValueError(f"Only matern52 kernel supported, got {kernel}")
    
    super().__init__(search_space, seed)
    # ... rest unchanged
```

**suggest() validation:**
```python
def suggest(self) -> Config:
    # Validate before arithmetic operations
    if self.seed is not None:
        if not isinstance(self.seed, int) or self.seed < 0:
            raise RuntimeError(f"Invalid seed state: {self.seed}")
        torch.manual_seed(self.seed + len(self.history))
    
    # ... rest unchanged
```

**_prepare_training_data() validation:**
```python
def _prepare_training_data(self, results: List[Result]):
    if not results:
        raise ValueError("Cannot prepare training data from empty results list")
    
    if not all(r.is_valid() for r in results):
        raise ValueError("All results must be valid for GP training")
    
    # ... rest unchanged
```

#### 1.2 LocalExecutor (122 timeouts → ~70 kills)

**File:** `hponas/executors/local_executor.py`

**Constructor validation:**
```python
def __init__(
    self,
    max_workers: int = 4,
    checkpoint_dir: Optional[str] = None,
):
    if not isinstance(max_workers, int) or max_workers < 1:
        raise ValueError(f"max_workers must be positive int, got {max_workers}")
    
    if checkpoint_dir is not None:
        if not isinstance(checkpoint_dir, str):
            raise TypeError(f"checkpoint_dir must be str or None, got {type(checkpoint_dir).__name__}")
        # Validate it's a reasonable path (no null bytes, etc.)
        if '\x00' in checkpoint_dir:
            raise ValueError("checkpoint_dir contains invalid characters")
    
    self.max_workers = max_workers
    self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
    
    # Validate Path operations will work
    if self.checkpoint_dir is not None:
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, TypeError, AttributeError) as e:
            raise ValueError(f"Cannot create checkpoint_dir {checkpoint_dir}: {e}")
    
    self._executor = ThreadPoolExecutor(max_workers=max_workers)
```

#### 1.3 RayExecutor (93 timeouts → ~50 kills)

**File:** `hponas/executors/ray_executor.py`

**Constructor validation:**
```python
def __init__(
    self,
    num_cpus: Optional[int] = None,
    num_gpus: Optional[int] = None,
    address: Optional[str] = None,
):
    if num_cpus is not None:
        if not isinstance(num_cpus, int) or num_cpus < 0:
            raise ValueError(f"num_cpus must be non-negative int or None, got {num_cpus}")
    
    if num_gpus is not None:
        if not isinstance(num_gpus, int) or num_gpus < 0:
            raise ValueError(f"num_gpus must be non-negative int or None, got {num_gpus}")
    
    if address is not None:
        if not isinstance(address, str):
            raise TypeError(f"address must be str or None, got {type(address).__name__}")
        # Basic validation: should look like "host:port" or "auto"
        if address != "auto" and ":" not in address:
            raise ValueError(f"address must be 'auto' or 'host:port', got {address}")
    
    # ... rest unchanged
```

### Phase 2: Scheduler Validation (30 min, ~20 timeout conversions)

**File:** `hponas/schedulers.py`

Add validation to:
- `ASHAScheduler.__init__()`: validate `max_t`, `reduction_factor`, `min_t`
- `FIFOScheduler.__init__()`: validate `max_concurrent`
- `promote()` methods: validate rung indices

### Phase 3: Legacy Modules (30 min, ~30 timeout conversions)

**Files:** `hponas/legacy_searchers.py`, `hponas/legacy_executors.py`

Add similar validation patterns as above.

### Phase 4: Type Validation (30 min, ~20 timeout conversions)

**File:** `hponas/types.py`

Add validation to `Result`, `Config` constructors.

## Testing Strategy

### 1. Unit Tests for Validation (30 min)

Create `tests/unit/test_input_validation.py`:

```python
import pytest
from hponas.searchers.gp_searcher import GPSearcher
from hponas.executors.local_executor import LocalExecutor
from hponas.space import Knob

def test_gp_searcher_rejects_negative_seed():
    space = [Knob(name='x', kind='continuous', bounds=(0.0, 1.0))]
    with pytest.raises(ValueError, match="seed must be non-negative"):
        GPSearcher(space, seed=-1)

def test_gp_searcher_rejects_string_seed():
    space = [Knob(name='x', kind='continuous', bounds=(0.0, 1.0))]
    with pytest.raises(TypeError, match="seed must be int or None"):
        GPSearcher(space, seed="42")

def test_gp_searcher_rejects_zero_initial_samples():
    space = [Knob(name='x', kind='continuous', bounds=(0.0, 1.0))]
    with pytest.raises(ValueError, match="initial_random_samples must be positive"):
        GPSearcher(space, initial_random_samples=0)

def test_local_executor_rejects_zero_workers():
    with pytest.raises(ValueError, match="max_workers must be positive"):
        LocalExecutor(max_workers=0)

def test_local_executor_rejects_negative_workers():
    with pytest.raises(ValueError, match="max_workers must be positive"):
        LocalExecutor(max_workers=-1)

def test_local_executor_rejects_none_workers():
    with pytest.raises((ValueError, TypeError), match="max_workers must be positive"):
        LocalExecutor(max_workers=None)
```

### 2. Verify Tests Pass

```bash
pytest tests/unit/test_input_validation.py -v
```

### 3. Run Mutation Testing

```bash
rm -rf mutants/ && python -m mutmut run
```

Expected results:
- Timeouts: 394 → ~200 (50% reduction)
- Killed: 1592 → ~1792 (200 conversions)
- Kill score: 87.52% → 91.2%
- Time: ~2 hours per run (down from ~3 hours)

## Success Criteria

- [ ] Kill score ≥ 90%
- [ ] Timeout count < 250 (down from 394)
- [ ] All validation tests pass
- [ ] No regression in existing tests
- [ ] Mutation testing completes in < 2.5 hours

## Timeline

**Total: 3.5 hours**

1. Phase 1 (GPSearcher, LocalExecutor, RayExecutor): 1 hour
2. Phase 2 (Schedulers): 30 min
3. Phase 3 (Legacy modules): 30 min
4. Phase 4 (Types): 30 min
5. Testing: 30 min
6. Mutation testing run: 2 hours (automated)
7. Analysis: 30 min

## Next Steps After Validation

If we don't reach 90% after defensive programming:

1. Analyze remaining ~227 survivors
2. Focus on scheduler survivors (82 mutations, 36%)
3. Add 10-15 targeted scheduler tests
4. Final mutation run

Expected final score: **91-92%** ✓

## Implementation Order

**Start with Phase 1.1 (GPSearcher)** - highest ROI:
- 141 timeouts (36% of all timeouts)
- ~80 expected conversions
- Single file to modify
- Clear validation patterns

Then proceed sequentially through remaining phases.
