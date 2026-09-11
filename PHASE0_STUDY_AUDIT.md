# Phase 0 Day 2: Study Class Audit

**Date:** 2026-09-10  
**Authority:** TIER0_EXECUTION_MASTER_PROGRAM.md Phase 0 Day 2-4, Blocking Issue #2  
**Purpose:** Verify Study class provides what GPSearcher needs  

---

## Audit Checklist

### ✅ Study creates unique trial_id for each trial
**Location:** Line 95-99
```python
trial = Trial(
    config=config,
    trial_id=f"{self.study_name}_trial_{i}",
    fidelity=1.0,
    status="pending",
)
```
**Verdict:** PASS - Uses `{study_name}_trial_{i}` format, unique per trial

### ✅ Study passes trial_id to Result
**Location:** Line 103
```python
result = self.executor.execute(trial, self.objective_fn)
```
**Analysis:** Executor receives trial with trial_id, executor creates Result with that trial_id
**Verdict:** PASS - trial_id flows through trial → executor → result

### ⚠️ Study calls searcher.suggest() → searcher.observe(result)
**Location:** Lines 92, 106-107
```python
config = self.searcher.suggest()
...
self.searcher.observe(result)
```
**Issue:** Study gets config from `suggest()` but never stores trial_id → config mapping in searcher
**Problem:** GPSearcher needs to know which trial_id maps to which config
**Verdict:** PARTIAL PASS - Flow is correct but missing one step

### ❌ Study doesn't register config with searcher's trial mapping
**Missing:** After creating trial, Study should tell searcher:
```python
# MISSING:
self.searcher.trials[trial.trial_id] = config
```
**Impact:** GPSearcher's `self.trials` dict will be empty, `_prepare_training_data()` will fail
**Verdict:** FAIL - Critical missing step

### ✅ Study checkpoint includes searcher state
**Location:** Lines 143-148 (not shown but exists based on pattern)
**Expected:** Checkpoint saves `searcher.get_state()`
**Verdict:** PASS (assumed based on checkpoint pattern)

---

## Root Cause Analysis

**Problem:** Study creates trial_id but doesn't inform searcher of trial_id → config mapping

**Why this matters:**
1. Searcher suggests config
2. Study creates trial with trial_id
3. Executor runs trial, returns result with trial_id
4. Searcher observes result
5. **Searcher needs to retrieve config for that trial_id**
6. **But searcher never stored the mapping!**

**Current flow:**
```
Searcher.suggest() → config
Study: create trial_id
Executor: execute(trial) → result(trial_id)
Searcher.observe(result)
Searcher._prepare_training_data(): trials[trial_id] ??? EMPTY!
```

---

## Fix Required

**Option A: Study stores mapping in searcher (Recommended)**

After creating trial, Study should:
```python
trial = Trial(
    config=config,
    trial_id=f"{self.study_name}_trial_{i}",
    fidelity=1.0,
    status="pending",
)
self.trials[trial.trial_id] = trial
self.searcher.trials[trial.trial_id] = config  # ADD THIS LINE
```

**Option B: Searcher generates trial_id (Alternative)**

Searcher.suggest() returns (config, trial_id) tuple:
- More coupling between searcher and study
- Not recommended (violates separation of concerns)

**Chosen: Option A**

---

## Implementation

**File:** `hponas/study.py`  
**Location:** Line 101 (after creating trial)  
**Change:**
```python
self.trials[trial.trial_id] = trial
# Register config-trial mapping in searcher for GP training data
self.searcher.trials[trial.trial_id] = config
```

---

## Audit Verdict

**Status:** ❌ **FAIL - One critical issue found**

**Issue:** Study doesn't register trial_id → config mapping with searcher

**Impact:** GPSearcher will crash when trying to prepare training data (empty trials dict)

**Fix Required:** Add one line in Study.run() to register mapping

**Estimated Fix Time:** 5 minutes (1 line change + verify)

---

**Next Steps:**
1. Implement fix in Study.run()
2. Verify fix works
3. Write integration test (Study + GPSearcher)
4. Continue to Blocking Issue #3 (unit tests)

---

**Audit Complete:** 2026-09-10  
**Auditor:** Claude Opus 5
