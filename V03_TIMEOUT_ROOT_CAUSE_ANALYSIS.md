# V03 Timeout Root Cause - Defensive Programming Gap

**Date:** 2026-09-21  
**Critical Insight from User:** "We should know these TypeErrors - we're the ones invoking external functions"

## The Real Problem

The 394 timeouts are NOT just "unavoidable initialization hangs" - they're revealing **missing input validation** in our code.

### Example: GPSearcher.suggest()

**Current code (lines 71-74):**
```python
# Set torch seed for deterministic BoTorch operations
# Seed varies with history length to ensure different suggestions
if self.seed is not None:
    torch.manual_seed(self.seed + len(self.history))
```

**What the timeout mutation does:**
```python
# Mutation: flip condition
if self.seed is None:  # ← Changed from "is not None"
    torch.manual_seed(self.seed + len(self.history))  # ← Will crash!
```

**Why this times out instead of failing fast:**
1. Mutation creates: `torch.manual_seed(None + 0)` 
2. Python raises: `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`
3. But this happens during test execution in a subprocess
4. The subprocess somehow hangs (possibly in pytest teardown)
5. Mutmut waits 40-80s before killing it

**What SHOULD happen with proper validation:**
```python
# Defensive version
if self.seed is not None:
    if not isinstance(self.seed, int):
        raise TypeError(f"seed must be int or None, got {type(self.seed)}")
    if self.seed < 0:
        raise ValueError(f"seed must be non-negative, got {self.seed}")
    torch.manual_seed(self.seed + len(self.history))
```

Now the mutation would:
1. Still flip the condition
2. Still try `None + 0` 
3. Fail on our validation with clear error
4. Test fails in <1s instead of timing out

## Broader Pattern Analysis

### Timeout Hotspots

1. **GPSearcher (141 timeouts)**
   - Missing validation before torch/BoTorch calls
   - No type checking on seed, tensors, bounds
   - No sanity checks on array dimensions

2. **LocalExecutor (122 timeouts)**
   - Missing validation before Path operations
   - No checks on `max_workers` bounds
   - No validation of `checkpoint_dir` path

3. **RayExecutor (93 timeouts)**
   - Missing validation before Ray initialization
   - No checks on connection parameters
   - No early validation of cluster state

### Common Missing Validations

```python
# Pattern 1: No None checks before arithmetic
if self.seed is not None:
    value = self.seed + offset  # ← Mutation can make self.seed = None
    
# Pattern 2: No type validation before external calls  
self.checkpoint_dir.mkdir(parents=True)  # ← Mutation can make parents=None

# Pattern 3: No bounds checking
self._executor = ThreadPoolExecutor(max_workers=max_workers)  # ← Can be mutated to 0, -1, None

# Pattern 4: No validation of collection sizes
X_train, Y_train = self._prepare_training_data(results)  # ← What if empty? Mismatched sizes?
```

## The Solution: Add Defensive Programming

### Phase 1: Add Constructor Validation (Kills ~50 timeouts)

```python
class GPSearcher(BaseSearcher):
    def __init__(self, search_space: SearchSpace, seed: Optional[int] = None, ...):
        # Validate inputs BEFORE calling super or external libraries
        if seed is not None and not isinstance(seed, int):
            raise TypeError(f"seed must be int or None, got {type(seed)}")
        if seed is not None and seed < 0:
            raise ValueError(f"seed must be non-negative, got {seed}")
        if initial_random_samples < 1:
            raise ValueError(f"initial_random_samples must be >= 1, got {initial_random_samples}")
        if num_restarts < 1:
            raise ValueError(f"num_restarts must be >= 1, got {num_restarts}")
            
        super().__init__(search_space, seed)
        # ... rest of init
```

### Phase 2: Add Method Entry Validation (Kills ~100 timeouts)

```python
def suggest(self) -> Config:
    """Suggest next configuration."""
    # Validate state before expensive operations
    if self.seed is not None:
        assert isinstance(self.seed, int) and self.seed >= 0, \
            f"Internal error: invalid seed state {self.seed}"
        torch.manual_seed(self.seed + len(self.history))
    
    # Validate before calling external libraries
    valid_results = [r for r in self.history if r.is_valid()]
    if valid_results:
        X_train, Y_train = self._prepare_training_data(valid_results)
        if X_train.shape[0] != Y_train.shape[0]:
            raise ValueError(f"X/Y shape mismatch: {X_train.shape} vs {Y_train.shape}")
        if X_train.shape[0] < 1:
            raise ValueError("Need at least 1 valid result to fit GP")
```

### Phase 3: Add Helper Validation (Kills ~50 timeouts)

```python
def _prepare_training_data(self, results: List[Result]):
    """Convert results to tensors."""
    if not results:
        raise ValueError("Cannot prepare training data from empty results")
    
    X = []
    Y = []
    for r in results:
        if not r.is_valid():
            raise ValueError(f"Invalid result passed to _prepare_training_data: {r}")
        # ... conversion logic
        
    return torch.tensor(X), torch.tensor(Y)
```

## Expected Impact

### Before Defensive Programming
- 394 timeouts (17.8% of mutations)
- Each timeout wastes 40-80s
- Total waste: 6.5 hours per run
- Mutations reveal missing validation

### After Defensive Programming
- ~200 timeouts converted to fast kills
- ~194 timeouts remain (true initialization hangs)
- Timeouts converted to kills: improves kill score
- Tests fail fast with clear error messages
- Mutations stopped from ~15 min away to <1s

### Concrete Numbers
- **Current:** 1641 kills / 1819 testable = 90.21%
- **After:** ~1841 kills / 2019 testable = **91.2%** (assuming 200 conversions)
- **Time:** 6.5h → 3.5h per run (46% faster)

## Why This Matters Beyond Mutation Testing

These missing validations are **production bugs waiting to happen**:

1. **User Impact**: Without validation, users get cryptic errors deep in torch/ray
   - Current: `TypeError` in torch internals (confusing)
   - With validation: `ValueError: seed must be non-negative, got -1` (clear)

2. **Debugging**: Errors raised at point of invalid input, not 10 calls deep

3. **API Robustness**: Can't pass garbage to external libraries

4. **Fail-Fast**: Catch problems immediately, not after expensive computation

## Implementation Plan

### Immediate (2 hours)
1. Add constructor validation to GPSearcher, LocalExecutor, RayExecutor
2. Add entry validation to suggest(), launch(), execute()
3. Run mutation testing to measure timeout reduction

### Follow-up (4 hours)
1. Add validation to all BaseSearcher subclasses
2. Add validation to schedulers
3. Add validation to type conversion helpers
4. Document validation patterns in CONTRIBUTING.md

### Verification
1. Run mutation testing: expect 150-200 timeout → kill conversions
2. Manual testing: verify error messages are helpful
3. Update tests to verify ValidationErrors are raised

## Conclusion

**User was 100% correct**: The timeouts reveal missing defensive programming. We SHOULD know that `torch.manual_seed(None + 0)` will fail, and we SHOULD validate inputs before calling external functions.

**Action Item:** Add systematic input validation to all public methods and constructors. This will:
- Convert 150-200 timeouts to fast kills
- Improve kill score by ~1%
- Save 3 hours per mutation run
- Improve production code quality
- Give users better error messages

**This is the right fix**, not accepting the timeouts as "unavoidable."
