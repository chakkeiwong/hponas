# V03 Phase 3 Preparation Complete

**Date:** 2026-09-21  
**Status:** Ready for survivor analysis when R6 completes

---

## What's Prepared

### 1. Quick Status Check Script ✓

**File:** `quick_mutation_check.py`

**Usage:**
```bash
python quick_mutation_check.py
```

**Output:**
- R6 mutation statistics
- Comparison to R5 baseline
- Gap to 90% target
- Next steps (automatic guidance)
- Defensive programming impact metrics

---

### 2. Survivor Analysis Script ✓

**File:** `analyze_survivors.py`

**Usage:**
```bash
# Full analysis
python analyze_survivors.py

# Focus on specific module
python analyze_survivors.py --module schedulers

# Show mutation diffs
python analyze_survivors.py --module schedulers --show-diffs
```

**Features:**
- Categorizes survivors by module
- Identifies top methods with most survivors
- Samples mutations for inspection
- Generates ROI-ranked test plan
- Saves plan to `/tmp/survivor_kill_plan.md`

---

### 3. Test Creation Guide ✓

**File:** `R7_TEST_CREATION_GUIDE.md`

**Contents:**
- 8-step workflow for survivor analysis
- Pattern identification guide (boundary, logic, state, error)
- 5 concrete scheduler test examples
- ROI estimates by module
- Quick reference commands

**Test patterns covered:**
- Boundary conditions (`>` ↔ `>=`, `<` ↔ `<=`)
- Logic inversions (`if x` ↔ `if not x`)
- Error handling (`raise` → `pass`)
- State transitions (rung promotions, trial status)

---

## Workflow When R6 Completes

### Step 1: Check Results (30 seconds)
```bash
python quick_mutation_check.py
```

**If ≥90%:** 🎉 Celebrate and proceed to next gate  
**If <90%:** Continue to Step 2

---

### Step 2: Analyze Survivors (5 minutes)
```bash
# Get full analysis
python analyze_survivors.py

# Output shows:
# - schedulers: 82 survivors (36%)
# - random_searcher: 46 survivors (20%)
# - etc.
```

---

### Step 3: Deep Dive Priority Module (10 minutes)
```bash
# Focus on highest-count module (likely schedulers)
python analyze_survivors.py --module schedulers --show-diffs

# Sample output:
# Methods:
#   ASHAScheduler.promote             18
#   ASHAScheduler.decide              14
#   FIFOScheduler._get_next            8
```

---

### Step 4: Inspect Sample Mutations (15 minutes)
```bash
# Inspect individual mutations
python -m mutmut show hponas.schedulers.xǁASHASchedulerǁpromote__mutmut_42
python -m mutmut show hponas.schedulers.xǁASHASchedulerǁpromote__mutmut_58
python -m mutmut show hponas.schedulers.xǁASHASchedulerǁdecide__mutmut_71
```

**Look for:**
- Boundary conditions not tested
- Logic paths not covered
- Edge cases missed

---

### Step 5: Write Targeted Tests (2-3 hours)

Follow `R7_TEST_CREATION_GUIDE.md` examples:

**For schedulers (priority 1):**
- 10 tests targeting rung boundaries, promotion logic, empty rungs
- Expected: 15-25 kills (18-30% of 82 survivors)

**For random_searcher (priority 2):**
- 5 tests targeting boundary clamps, state consistency
- Expected: 10-15 kills (22-33% of 46 survivors)

**For space/types (priority 3):**
- 5 tests targeting validation, type conversions
- Expected: 10-15 kills (26-40% of 38 survivors)

**Total: 20 tests → 35-55 kills (enough to reach 90%)**

---

### Step 6: Verify Tests (10 minutes)
```bash
# Run new tests
pytest tests/unit/test_schedulers.py -v

# Should all pass
```

---

### Step 7: Run R7 (2 hours)
```bash
rm -rf mutants/ && python -m mutmut run
```

---

### Step 8: Check R7 Results (5 minutes)
```bash
python quick_mutation_check.py

# Expected: 87.5% → 90.5%
```

---

## Files Created for Phase 3

1. **`quick_mutation_check.py`**
   - Fast results checker
   - Automatic guidance on next steps

2. **`analyze_survivors.py`**
   - Comprehensive survivor analysis
   - ROI-ranked priorities
   - Sample selection for inspection

3. **`R7_TEST_CREATION_GUIDE.md`**
   - Step-by-step workflow
   - Pattern templates
   - Concrete examples
   - ROI estimates

4. **`CONTEXT_RESET_MEMO_2026_09_21.md`** ⭐
   - Complete recovery context
   - Formula analysis
   - Tool thrashing prevention

5. **`V03_INVESTIGATION_SUMMARY.md`**
   - Executive summary
   - Answers to all questions

---

## Expected Timeline

**R6 completion → 90% achieved:**
- Check results: 1 minute
- Analyze survivors: 20 minutes
- Write tests: 2-3 hours
- Run R7: 2 hours (automated)
- Total: 4-5 hours

---

## Success Criteria for Phase 3

- [x] Scripts prepared and tested
- [x] Guide written with examples
- [x] Workflow documented
- [ ] R6 results analyzed (when complete)
- [ ] Survivors sampled (when <90%)
- [ ] R7 tests written (when <90%)
- [ ] 90% kill score achieved

---

## Key Insights for Phase 3

### Why Focus on Survivors, Not Timeouts

**Gate formula:** `kill_score = killed / (total - timeout)`

Converting timeout → kill:
- Numerator: +1
- Denominator: +1 (total - timeout increases)
- Score: Barely changes

Killing survivor → kill:
- Numerator: +1
- Denominator: 0 (survivor was already in denominator)
- Score: Directly improves

**Example:**
- 1 timeout→kill: 87.52% → 87.53% (+0.01pp)
- 1 survivor→kill: 87.52% → 87.58% (+0.06pp)
- **6x more impact!**

### Defensive Programming Value

**Primary:** Code quality improvement
- Fail fast vs timeout (80 min saved per run)
- Clear error messages
- Production robustness

**Secondary:** Marginal mutation score improvement
- Some edge case coverage
- Not the path to 90%

### Test Writing Strategy

**High ROI:** Focus on methods with most survivors
- 1 test can kill 3-5 similar mutations
- Boundary tests especially effective

**Medium ROI:** Cover different patterns
- Logic inversions
- State transitions
- Error handling

**Low ROI:** One-off mutations
- String constants
- Comments
- Logging

---

## All Preparation Complete ✓

Phase 3 preparation is ready. When R6 mutation testing completes, run:

```bash
python quick_mutation_check.py
```

This will automatically guide the next steps based on whether 90% was reached.

**Estimated R6 completion:** ~2 hours from start  
**Background task ID:** brqovr8rt
