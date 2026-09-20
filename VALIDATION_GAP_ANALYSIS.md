# Validation Gap Analysis & Action Plan

**Date:** 2026-09-21  
**Issue:** Missing input validation causes 394 mutation timeouts  
**Solution:** Systematic validation policy + enforcement tests

---

## Current State ✓

### What We Have

**1. Policy Document:** `INPUT_VALIDATION_POLICY.md`
- Defines validation requirements
- Provides examples and templates
- Documents rollout plan

**2. Enforcement Test:** `tests/unit/test_validation_coverage.py`
- Automatically detects missing validation tests
- Currently **FAILING** (by design)
- Shows 20 classes need validation

**3. Example Implementation:** `GPSearcher` ✓
- 12 validation tests
- Covers all parameters
- Tests both valid and invalid inputs

### Coverage Status

**Total Tier 0 classes:** 21  
**With validation tests:** 1 (GPSearcher) ✓  
**Missing validation tests:** 20 ❌

```
✓ hponas.searchers.gp_searcher.GPSearcher (12 tests)

❌ hponas.searchers.base.BaseSearcher
❌ hponas.searchers.random_searcher.RandomSearcher
❌ hponas.searchers.random_searcher.SobolSearcher
❌ hponas.executors.local_executor.LocalExecutor
❌ hponas.executors.ray_executor.RayExecutor
❌ hponas.schedulers.ASHAConfig
❌ hponas.schedulers.ASHAScheduler
❌ hponas.schedulers.MOASHAConfig
❌ hponas.schedulers.MOASHAScheduler
❌ hponas.schedulers.PASHAConfig
❌ hponas.schedulers.PASHAScheduler
❌ hponas.types.Config
❌ hponas.types.MultiObjectiveResult
❌ hponas.types.Parameter
❌ hponas.types.ParameterType
❌ hponas.types.Result
❌ hponas.types.SearchSpace
❌ hponas.types.Trial
❌ hponas.space.Knob
❌ hponas.space.SearchSpace
```

---

## The Gap: Why This Matters

### Problem 1: Mutation Testing Timeouts

**Current:** 394 timeouts (17.8% of mutations)
- Each timeout wastes 60 seconds
- Total waste: 6.5 hours per mutation run
- Makes mutation testing impractical

**With validation:** Expected <100 timeouts
- Invalid inputs fail fast (<1s)
- Time saved: ~5 hours per run
- Mutation testing becomes viable

### Problem 2: Production Quality

**Current user experience:**
```python
>>> executor = LocalExecutor(max_workers=-1)
# 60s hang, then cryptic error from deep in thread pool
```

**With validation:**
```python
>>> executor = LocalExecutor(max_workers=-1)
ValueError: max_workers must be positive, got -1
```

### Problem 3: Future Prevention

**Without enforcement test:**
- Developers forget validation
- Same mistakes repeated
- No systematic coverage

**With enforcement test:**
- CI fails if validation missing
- Impossible to merge without validation
- Systematic coverage guaranteed

---

## Action Plan

### Phase 1: Immediate (This Session) ✓

**Done:**
- [x] Created `INPUT_VALIDATION_POLICY.md`
- [x] Created `tests/unit/test_validation_coverage.py`
- [x] Implemented GPSearcher validation (example)
- [x] Documented the gap (20 classes)

**Status:** Foundation complete, enforcement test in place

### Phase 2: Critical Classes (Next Session)

**Priority 1: Schedulers** (highest survivor count)
- ASHAScheduler + ASHAConfig
- MOASHAScheduler + MOASHAConfig  
- PASHAScheduler + PASHAConfig

**Expected effort:** 2-3 hours  
**Impact:** 
- Kills 15-25 scheduler survivors
- Reduces timeouts by ~20

**Priority 2: Searchers**
- RandomSearcher
- SobolSearcher
- BaseSearcher

**Expected effort:** 1-2 hours  
**Impact:**
- Kills 10-15 searcher survivors
- Reduces timeouts by ~15

**Priority 3: Executors**
- LocalExecutor
- RayExecutor

**Expected effort:** 1-2 hours  
**Impact:**
- Reduces timeouts by ~200+ (executors cause most timeouts)

### Phase 3: Remaining Classes (Future)

**Priority 4: Core Types**
- Config, Result, Trial
- Parameter, SearchSpace

**Expected effort:** 2-3 hours  
**Impact:**
- Foundation classes
- Prevents future issues

**Priority 5: Space Types**
- Knob, SearchSpace

**Expected effort:** 1 hour  
**Impact:**
- User-facing API
- Better error messages

---

## ROI Analysis

### Time Investment

**Policy + enforcement:** 2 hours (done ✓)  
**20 remaining classes:** ~10-12 hours  
**Total investment:** ~14 hours

### Time Saved

**Per mutation run:**
- Before: 6.5 hours wasted on timeouts
- After: ~1 hour wasted on timeouts
- **Saved: 5.5 hours per run**

**Break-even:** 3 mutation runs (we've done 6+ already)

### Quality Impact

**Developer experience:**
- Clear error messages at point of error
- No cryptic stack traces from libraries
- Faster debugging

**Production robustness:**
- Invalid inputs rejected immediately
- No silent failures
- Contract enforcement

---

## Implementation Guide

### Template for Each Class

```python
class Test<ClassName>Validation:
    """Validation tests for <ClassName>."""

    # For each parameter, test:
    # 1. Invalid type (if typed)
    # 2. Invalid value (if range-constrained)
    # 3. Valid value (positive test)

    def test_rejects_negative_<param>(self):
        with pytest.raises(ValueError, match="<param> must be"):
            <ClassName>(<param>=-1)

    def test_rejects_wrong_type_<param>(self):
        with pytest.raises(TypeError, match="<param> must be"):
            <ClassName>(<param>="invalid")

    def test_accepts_valid_<param>(self):
        obj = <ClassName>(<param>=<valid_value>)
        assert obj.<param> == <valid_value>
```

### Process

1. **Pick a class** from the list above
2. **Add validation** to the actual class code
3. **Write tests** using the template
4. **Verify tests pass** with `pytest tests/unit/test_input_validation.py -v`
5. **Check coverage** with `python tests/unit/test_validation_coverage.py`
6. **Repeat** until coverage test passes

---

## Quick Commands

```bash
# Check current coverage
python tests/unit/test_validation_coverage.py

# Run validation tests
pytest tests/unit/test_input_validation.py -v

# Run coverage enforcement
pytest tests/unit/test_validation_coverage.py -v

# Full test suite
pytest tests/unit/ -v
```

---

## Success Criteria

### Short Term (V03 Gate)
- [ ] 10+ classes with validation (50% coverage)
- [ ] Timeouts reduced to <200 (from 394)
- [ ] 90% mutation kill score achieved

### Medium Term (Next Sprint)
- [ ] All 21 Tier 0 classes with validation (100% coverage)
- [ ] Validation coverage test passes
- [ ] CI enforces validation on new code

### Long Term (Production)
- [ ] Policy adopted team-wide
- [ ] Zero validation-related bugs in production
- [ ] Developer feedback: clearer error messages

---

## Integration with V03 Gate

### Current Plan (R7)

**Focus:** Kill survivors to reach 90%
1. Analyze scheduler survivors (82 survivors)
2. Write targeted behavior tests
3. Run R7 mutation testing

**Problem:** Won't address timeout root cause

### Enhanced Plan (R7 + Validation)

**Parallel tracks:**

**Track 1:** Kill survivors (reaches 90%)
- Write scheduler behavior tests
- Write random_searcher tests
- Run R7

**Track 2:** Add validation (improves quality)
- Add scheduler validation
- Add searcher validation
- Add executor validation

**Combined impact:**
- R7: 87.52% → 90.5% (survivor tests)
- R8: 90.5% → 91.5% (validation reduces timeouts)
- Code quality: Much improved

---

## Recommendation

### For This Session (Already Done)
✓ Foundation laid
✓ Policy documented
✓ Enforcement test created
✓ Example implementation (GPSearcher)

### For Next Session (When R6 Completes)

**Path A: Focus on 90% Only**
- Write survivor tests for schedulers/searchers
- Run R7
- Reach 90%, move to next gate
- **Time:** 4-5 hours
- **Risk:** Timeouts remain, quality gaps persist

**Path B: Combined Approach (Recommended)**
- Add validation to top 3 timeout classes (schedulers, executors, searchers)
- Write survivor tests
- Run R7
- Reach 90% + improve quality
- **Time:** 6-8 hours
- **Benefit:** Sustainable quality improvement

### For Future Sessions

- Complete remaining 17 classes
- Enable CI enforcement
- Make policy standard practice

---

## Questions for Decision

1. **Should validation coverage be required for V03 gate?**
   - Pro: Ensures quality foundation
   - Con: Adds scope to V03
   - Recommendation: Optional enhancement, not gate requirement

2. **Should we implement validation in parallel with R7?**
   - Pro: Compounds improvements
   - Con: Longer session time
   - Recommendation: Yes for top 3 timeout classes

3. **Should we enable CI enforcement now or later?**
   - Pro: Prevents future gaps
   - Con: Blocks merges until all 20 done
   - Recommendation: Enable after 50% coverage

---

## Status Summary

**Policy:** COMPLETE ✓  
**Enforcement Test:** COMPLETE ✓  
**Example Implementation:** COMPLETE ✓  
**Documentation:** COMPLETE ✓  
**Coverage:** 5% (1/21 classes)  
**Next Step:** Prioritize high-impact classes for validation
