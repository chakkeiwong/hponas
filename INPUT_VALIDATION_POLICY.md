# Input Validation Policy & Testing Standard

**Status:** DRAFT - Needs team review and adoption  
**Purpose:** Prevent future validation gaps that cause timeouts and bugs

---

## The Problem

**Discovery:** V03 mutation testing revealed 394 timeouts caused by missing input validation.

**Example:**
```python
# No validation - mutation causes 60s timeout
def suggest(self):
    if self.seed is not None:
        torch.manual_seed(self.seed + len(self.history))  # TypeError if seed is None
```

**Root cause:** No policy requiring input validation or tests for it.

---

## Policy: All Public Methods Must Validate Inputs

### Scope

**MUST validate:**
- All `__init__()` constructors
- All public methods (no leading underscore)
- All methods that call external libraries (torch, ray, numpy, pathlib)

**MAY skip validation:**
- Private methods (leading underscore) IF caller validates
- Internal helpers called only by validated code

### Validation Requirements

**1. Type validation:**
```python
if seed is not None and not isinstance(seed, int):
    raise TypeError(f"seed must be int or None, got {type(seed).__name__}")
```

**2. Range validation:**
```python
if seed is not None and seed < 0:
    raise ValueError(f"seed must be non-negative, got {seed}")
```

**3. State validation:**
```python
if not self.is_initialized:
    raise RuntimeError("Cannot call suggest() before initialization")
```

**4. Collection validation:**
```python
if not results:
    raise ValueError("results list cannot be empty")
```

### When to Validate

**Early validation (preferred):**
- In `__init__()` before storing or calling parent
- At method entry before any processing
- Before calling external libraries

**Late validation (avoid):**
- After expensive operations
- After state changes
- Deep in call stack

---

## Testing Standard

### Rule 1: Every Validation Must Have a Test

For each validation check, write a test that:
1. Triggers the validation with invalid input
2. Verifies the correct exception type
3. Verifies the error message is helpful

**Example:**
```python
# Code
if seed is not None and seed < 0:
    raise ValueError(f"seed must be non-negative, got {seed}")

# Test
def test_rejects_negative_seed(self):
    with pytest.raises(ValueError, match="seed must be non-negative"):
        GPSearcher(space, seed=-1)
```

### Rule 2: Test Invalid Inputs Systematically

For each parameter, test:
- **None** (if not allowed)
- **Wrong type** (int vs str vs float vs list)
- **Boundary violations** (negative, zero, too large)
- **Invalid values** (empty string, empty list)

**Template:**
```python
class TestClassNameValidation:
    """Validation tests for ClassName."""
    
    def test_rejects_none_<param>(self):
        with pytest.raises((TypeError, ValueError)):
            ClassName(<param>=None)
    
    def test_rejects_wrong_type_<param>(self):
        with pytest.raises(TypeError, match="<param> must be"):
            ClassName(<param>="invalid")
    
    def test_rejects_negative_<param>(self):
        with pytest.raises(ValueError, match="<param> must be"):
            ClassName(<param>=-1)
    
    def test_accepts_valid_<param>(self):
        obj = ClassName(<param>=<valid_value>)
        assert obj.<param> == <valid_value>
```

### Rule 3: Validation Tests Are Mandatory

**CI/CD requirement:**
- Every public class must have a `TestClassValidation` test class
- Every parameter must have validation tests
- PR reviewers must check for validation tests

**Enforcement:**
```python
# tests/validation_coverage.py
def test_all_public_classes_have_validation_tests():
    """Ensure every public class has validation tests."""
    for module in MODULES:
        for cls in get_public_classes(module):
            test_class = f"Test{cls.__name__}Validation"
            assert test_class in test_module, \
                f"{cls.__name__} missing validation test class"
```

---

## Implementation Checklist

### Phase 1: Current Codebase (V03)

**Done:**
- [x] GPSearcher validation + tests

**TODO:**
- [ ] LocalExecutor validation + tests
- [ ] RayExecutor validation + tests
- [ ] ASHAScheduler validation + tests
- [ ] FIFOScheduler validation + tests
- [ ] PABOScheduler validation + tests
- [ ] RandomSearcher validation + tests
- [ ] SobolSearcher validation + tests
- [ ] BaseSearcher validation + tests
- [ ] Config validation + tests
- [ ] Result validation + tests
- [ ] SearchSpace validation + tests

**Estimated effort:** 2-3 days

### Phase 2: Enforcement

- [ ] Create `tests/test_validation_coverage.py`
- [ ] Add to CI/CD pipeline
- [ ] Document in CONTRIBUTING.md
- [ ] Add to PR review checklist

**Estimated effort:** 4 hours

### Phase 3: Future Code

- [ ] Add validation requirement to code review checklist
- [ ] Add validation tests to PR template
- [ ] Fail CI if validation tests missing

---

## Examples by Module

### Searchers

**GPSearcher:** ✓ Done (12 tests)

**RandomSearcher:** TODO
```python
class TestRandomSearcherValidation:
    def test_rejects_negative_seed(self):
        with pytest.raises(ValueError):
            RandomSearcher(space, seed=-1)
    
    def test_rejects_none_search_space(self):
        with pytest.raises(TypeError):
            RandomSearcher(None, seed=42)
```

**SobolSearcher:** TODO
```python
class TestSobolSearcherValidation:
    def test_rejects_negative_seed(self):
        with pytest.raises(ValueError):
            SobolSearcher(space, seed=-1)
    
    def test_rejects_zero_scramble(self):
        with pytest.raises(ValueError):
            SobolSearcher(space, scramble=0)
```

### Executors

**LocalExecutor:** TODO
```python
class TestLocalExecutorValidation:
    def test_rejects_zero_max_workers(self):
        with pytest.raises(ValueError, match="max_workers must be positive"):
            LocalExecutor(max_workers=0)
    
    def test_rejects_negative_max_workers(self):
        with pytest.raises(ValueError):
            LocalExecutor(max_workers=-1)
    
    def test_rejects_invalid_checkpoint_dir(self):
        with pytest.raises((ValueError, TypeError)):
            LocalExecutor(checkpoint_dir=123)  # Not a string
```

**RayExecutor:** TODO
```python
class TestRayExecutorValidation:
    def test_rejects_negative_num_cpus(self):
        with pytest.raises(ValueError):
            RayExecutor(num_cpus=-1)
    
    def test_rejects_string_num_cpus(self):
        with pytest.raises(TypeError):
            RayExecutor(num_cpus="4")
```

### Schedulers

**ASHAScheduler:** TODO
```python
class TestASHASchedulerValidation:
    def test_rejects_zero_max_t(self):
        with pytest.raises(ValueError, match="max_t must be positive"):
            ASHAScheduler(max_t=0)
    
    def test_rejects_reduction_factor_less_than_2(self):
        with pytest.raises(ValueError, match="reduction_factor must be >= 2"):
            ASHAScheduler(max_t=27, reduction_factor=1)
    
    def test_rejects_min_t_greater_than_max_t(self):
        with pytest.raises(ValueError, match="min_t must be <= max_t"):
            ASHAScheduler(max_t=27, min_t=30)
```

---

## Benefits

### 1. Mutation Testing

**Before validation:**
- 394 timeouts (17.5% of mutations)
- Each timeout wastes 60s
- Total waste: 6.5 hours per run

**After validation:**
- Timeouts → fast TypeErrors (<1s)
- Mutations killed by validation
- Time saved: ~5 hours per run

### 2. Production Quality

**User experience:**
```python
# Before
>>> searcher = GPSearcher(space, seed="42")
# 60s hang, then cryptic torch error

# After
>>> searcher = GPSearcher(space, seed="42")
TypeError: seed must be int or None, got str
```

**Debugging:**
- Errors at point of invalid input (not 10 calls deep)
- Clear error messages
- Stack traces point to caller, not library internals

### 3. API Robustness

**Contract enforcement:**
- Parameters have documented types/ranges
- Invalid inputs rejected immediately
- No silent failures or undefined behavior

---

## Migration Strategy

### Step 1: Audit (1 day)
```bash
# List all public classes
grep -r "^class [A-Z]" hponas/ | grep -v "^#"

# Check which have validation tests
ls tests/unit/test_*_validation.py
```

### Step 2: Prioritize (1 hour)
1. High-traffic classes (BaseSearcher, schedulers)
2. Classes with timeouts (LocalExecutor, RayExecutor)
3. User-facing APIs (Config, Result)
4. Internal helpers (low priority)

### Step 3: Implement (2 days)
- 1 class per hour
- Add validation to code
- Write 5-10 tests per class
- Run mutation testing to verify

### Step 4: Enforce (4 hours)
- Add coverage check
- Update CI/CD
- Document policy

---

## Rollout Plan

### Week 1: Foundation
- [ ] Document this policy
- [ ] Get team buy-in
- [ ] Add to CONTRIBUTING.md

### Week 2: Searchers
- [ ] RandomSearcher validation + tests
- [ ] SobolSearcher validation + tests
- [ ] BaseSearcher validation + tests

### Week 3: Executors & Schedulers
- [ ] LocalExecutor validation + tests
- [ ] RayExecutor validation + tests
- [ ] ASHAScheduler validation + tests
- [ ] FIFOScheduler validation + tests

### Week 4: Types & Enforcement
- [ ] Config validation + tests
- [ ] Result validation + tests
- [ ] SearchSpace validation + tests
- [ ] Add validation_coverage test
- [ ] Enable CI enforcement

---

## Success Metrics

### Coverage
- [ ] 100% of public classes have validation tests
- [ ] 100% of validation checks have tests
- [ ] CI fails if validation tests missing

### Quality
- [ ] Timeouts reduced to <100 (from 394)
- [ ] All TypeErrors caught at entry point
- [ ] User error messages are helpful

### Process
- [ ] Policy documented
- [ ] PR template includes validation checklist
- [ ] Code reviews check validation

---

## Appendix: Validation Coverage Test

```python
# tests/test_validation_coverage.py
"""Ensure all public classes have validation tests."""

import pytest
import inspect
import importlib
from pathlib import Path


MODULES = [
    'hponas.searchers.base',
    'hponas.searchers.gp_searcher',
    'hponas.searchers.random_searcher',
    'hponas.executors.local_executor',
    'hponas.executors.ray_executor',
    'hponas.schedulers',
    'hponas.types',
    'hponas.space',
]


def get_public_classes(module_name):
    """Get all public classes from a module."""
    module = importlib.import_module(module_name)
    classes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ == module_name and not name.startswith('_'):
            classes.append((name, obj))
    return classes


def has_validation_tests(class_name):
    """Check if validation tests exist for a class."""
    test_file = Path(f"tests/unit/test_input_validation.py")
    if not test_file.exists():
        return False
    
    content = test_file.read_text()
    return f"Test{class_name}Validation" in content


def test_all_public_classes_have_validation_tests():
    """All public classes must have validation test classes."""
    missing = []
    
    for module_name in MODULES:
        for class_name, cls in get_public_classes(module_name):
            if not has_validation_tests(class_name):
                missing.append(f"{module_name}.{class_name}")
    
    if missing:
        pytest.fail(
            f"Missing validation tests for {len(missing)} classes:\n" +
            "\n".join(f"  - {c}" for c in missing)
        )


def test_validation_test_naming_convention():
    """Validation tests must follow naming convention."""
    test_file = Path("tests/unit/test_input_validation.py")
    if not test_file.exists():
        pytest.skip("No validation tests file yet")
    
    content = test_file.read_text()
    
    # All test classes must be named Test*Validation
    for line in content.split('\n'):
        if line.startswith('class Test') and 'Validation' not in line:
            pytest.fail(f"Validation test class must end with 'Validation': {line}")
```

---

## Questions for Team Discussion

1. **Should we enforce 100% validation coverage?**
   - Pro: Catches all future gaps
   - Con: May slow development

2. **Should validation be opt-in or opt-out?**
   - Current: Opt-in (must explicitly add)
   - Proposal: Opt-out (required by default, can skip with justification)

3. **What error types to use?**
   - TypeError for wrong types
   - ValueError for invalid values
   - RuntimeError for invalid state
   - Custom exceptions?

4. **How to handle legacy code?**
   - Grandfather existing code?
   - Require validation on any changes?
   - Phased migration plan?

---

## Approval & Tracking

- [ ] Policy reviewed by team
- [ ] Timeline agreed
- [ ] Assigned owners
- [ ] Tracked in project board

**Status:** DRAFT - needs review
