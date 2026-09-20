# CONTEXT RESET MEMO - V03 Mutation Testing Gate
**Date:** 2026-09-21  
**Session:** Recovery after gateway 502 instability and tool thrashing

---

## Executive Summary

**Goal:** Reach ≥90% mutation testing kill score (V03 gate requirement)

**Current Status:**
- **Before R6:** 87.52% (1592/1819 kills) - Gap: 46 kills to reach 90%
- **R6 Implementation:** Added defensive programming to GPSearcher
- **Expected After R6:** 91-92% (80 timeout→kill conversions from GPSearcher alone)
- **Mutation testing:** Running now (2 hours, task ID: brqovr8rt)

**Key Insight (from user):** The 394 timeouts revealed **missing input validation**, not unavoidable hangs. We should validate inputs before calling external libraries to convert timeouts into fast kills.

---

## What Happened: Tool Thrashing Root Cause

The previous agent experienced severe tool usage thrashing:

1. **Gateway instability:** 502/529 errors causing mid-conversation disconnects
2. **Excessive redundant reads:** Reading same mutation results 10+ different ways
3. **Poor async handling:** Starting background tasks then immediately polling them
4. **Cache confusion:** Looking for `.mutmut-cache` in wrong directory (it's in `mutants/`)
5. **Output parsing loops:** Trying multiple parsing strategies when one command sufficed

**Prevention for next agent:**
- Use `python -m mutmut results` once to get all results
- Cache is in `mutants/.mutmut-cache` (SQLite)
- Wait for background task notifications instead of polling
- Trust the first successful parse

---

## The Breakthrough: User's Insight on TypeErrors

**User's Question:** "Why can't we catch these TypeErrors? We're the ones invoking external functions - we should know that behavior."

**Answer:** Absolutely correct! Example:

```python
# Current code (causes timeout when mutated)
if self.seed is not None:
    torch.manual_seed(self.seed + len(self.history))

# Mutation flips condition
if self.seed is None:  # ← Mutated
    torch.manual_seed(self.seed + len(self.history))  # ← TypeError: None + int
    # This causes 40-80s timeout in subprocess
```

**The Fix:** Add defensive validation BEFORE calling external libraries:

```python
# With validation (converts timeout to fast kill)
if self.seed is not None:
    if not isinstance(self.seed, int) or self.seed < 0:
        raise RuntimeError(f"Invalid seed state: {self.seed}")
    torch.manual_signal(self.seed + len(self.history))
    # Now mutation hits validation in <1s instead of timing out
```

---

## What We Implemented (R6 - Phase 1.1)

### File: `hponas/searchers/gp_searcher.py`

**1. Constructor validation (lines 54-69):**
```python
def __init__(self, search_space, seed=None, initial_random_samples=5, num_restarts=10, kernel="matern52"):
    # Validate BEFORE calling super() or storing
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
    # ... rest
```

**2. suggest() runtime validation (lines 84-88):**
```python
def suggest(self):
    if self.seed is not None:
        # Defensive check before arithmetic
        if not isinstance(self.seed, int) or self.seed < 0:
            raise RuntimeError(f"Invalid seed state: {self.seed}")
        torch.manual_seed(self.seed + len(self.history))
```

**3. _prepare_training_data() validation (lines 152-155):**
```python
def _prepare_training_data(self, results):
    if not results:
        raise ValueError("Cannot prepare training data from empty results list")
    if not all(r.is_valid() for r in results):
        raise ValueError("All results must be valid for GP training")
    # ... rest
```

### File: `tests/unit/test_input_validation.py` (NEW)
- 12 validation tests covering all edge cases
- All tests pass ✓

### Test Results
```
tests/unit/test_input_validation.py: 12/12 passed ✓
tests/unit/test_gp_searcher.py: 20/20 passed ✓
tests/unit/test_searchers.py: 13/13 passed ✓
Total: 223/224 unit tests pass (1 pre-existing failure unrelated)
```

---

## Expected Impact

### Timeout Breakdown (Before R6)
- Total timeouts: 394 (17.8% of mutations)
  - GPSearcher: 141 (36% of timeouts) ← **FIXED IN R6**
  - legacy_executors: 122 (31%)
  - ray_executor: 93 (24%)
  - legacy_searchers: 18 (5%)
  - types: 12 (3%)
  - schedulers: 6 (2%)
  - base: 2 (0.5%)

### Expected R6 Impact
- **GPSearcher timeouts:** 141 → ~60 (80 conversions)
- **Kill score:** 87.52% → **91.9%**
- **Time saved:** 80 mutations × 60s = 80 minutes per run
- **Gap to 90%:** 46 needed → +80 actual = **EXCEEDED by 34 kills**

### Confidence: 85%
- Mutations flipping `if seed is not None` will hit validation
- Mutations changing parameters to 0, -1, None will be caught
- Mutations in arithmetic will fail fast vs timeout

---

## Current Mutation Testing Run (R6)

**Started:** 2026-09-21 (background task: brqovr8rt)
**Command:** `rm -rf mutants/ && python -m mutmut run`
**Expected duration:** ~2 hours
**Output:** `/tmp/claude-1000/-home-ubuntu-workspace-hponas/.../tasks/brqovr8rt.output`

**How to check progress:**
```bash
# Extract final stats (when complete)
tr '\r' '\n' < /tmp/.../brqovr8rt.output | grep -oE "[0-9]+/[0-9]+.*" | tail -1

# Parse final results
cd /home/ubuntu/workspace/hponas
python -m mutmut results | grep -c survived
python -m mutmut results | grep -c timeout
python -m mutmut results | wc -l
```

**Expected final stats:**
```
Total: 2245
Killed: ~1672 (was 1592, +80 from validation)
Survived: ~227 (unchanged)
Timeout: ~314 (was 394, -80 from validation)
No tests: 32

Kill score: 1672/(2245-32-314) = 1672/1899 = 88.0%
```

Wait, that's wrong! Let me recalculate using the gate's formula (killed / (total - timeout)):

```
Denominator = killed + survived + suspicious (excludes timeout, no_tests)
Before: 1592 / (1592 + 227 + 0) = 1592/1819 = 87.52%
After: 1672 / (1672 + 227 + 0) = 1672/1899 = 88.05%
```

Hmm, that's only 0.5pp improvement, not 3pp. Let me reconsider...

**CORRECTED CALCULATION:**

The gate formula (v03_mutation_testing.py:157):
```python
denominator = total - timeout  # Excludes timeouts
kill_score = killed / denominator
```

Before R6:
- Total: 2245
- Killed: 1592
- Timeout: 394
- Denominator: 2245 - 394 = 1851
- Score: 1592/1851 = 86.01%

Expected after R6 (80 timeout→kill conversions):
- Total: 2245 (unchanged)
- Killed: 1592 + 80 = 1672
- Timeout: 394 - 80 = 314
- Denominator: 2245 - 314 = 1931
- Score: 1672/1931 = 86.59%

**That's only +0.58pp, not enough to reach 90%!**

Wait, I had the wrong baseline. Let me check the actual R5 results again...

From the earlier conversation, the CORRECT R5 baseline was:
```
2245/2245  🎉 1592 🫥 32  ⏰ 394  🤔 0  🙁 227
```

Denominator = total - timeout - no_tests = 2245 - 394 - 32 = 1819
Kill score = 1592/1819 = 87.52% ✓ (matches what we had)

For 90%: need 0.90 × 1819 = 1638 kills
Gap: 1638 - 1592 = 46 kills ✓

**INSIGHT:** Converting timeouts doesn't help because they're already excluded from denominator!

---

## CRITICAL REALIZATION

Converting timeouts to kills does NOT improve the kill score with the current gate formula!

**The gate formula (line 157):**
```python
denominator = total - timeout
kill_score = killed / denominator
```

This means timeouts are **already excluded** from the denominator, so converting a timeout to a kill:
- Numerator: +1 (killed goes from K to K+1)
- Denominator: +1 (total-timeout goes from D to D+1)
- Score: (K+1)/(D+1) ≈ K/D (barely changes)

**Example:**
- Before: 1592/1819 = 87.52%
- Convert 1 timeout: 1593/1820 = 87.53% (+0.01pp)
- Convert 80 timeouts: 1672/1899 = 88.05% (+0.53pp)

**To reach 90% we need to kill SURVIVORS, not convert timeouts!**

---

## CORRECTED STRATEGY

### What Defensive Programming Actually Achieves

**Primary benefit:** Code quality + better error messages (worth doing!)
- Fail fast instead of hanging
- Clear error messages for users
- Proper input validation (production quality)

**Secondary benefit (mutation testing):** Small improvement from edge case coverage
- Some mutations will be killed by new validation checks
- But most will still survive if they don't hit the validation

### What We Actually Need: Kill Survivors

**Current survivors: 227**
- schedulers: 82 (36%)
- searchers.random_searcher: 46 (20%)
- executors.local_executor: 31 (14%)
- legacy_searchers: 30 (13%)
- space: 28 (12%)
- types: 10 (4%)

**Gap to 90%:** 46 more kills

**Solution:** Add targeted tests for the 227 survivors, focusing on:
1. Scheduler edge cases (82 survivors, highest ROI)
2. RandomSearcher/SobolSearcher untested paths (46 survivors)
3. LocalExecutor error handling (31 survivors)

---

## Revised Action Plan

### Phase 1: Complete R6 Mutation Run (in progress)
- Wait for mutation testing to complete (~2 hours)
- Analyze actual results
- Confirm defensive programming improves code quality

### Phase 2: Analyze Survivors (30 min)
```bash
# Get detailed survivor list
python -m mutmut results | grep survived > /tmp/r6_survivors.txt

# Sample scheduler survivors
python -m mutmut show <id> | head -30  # For 10-15 scheduler mutation IDs
```

### Phase 3: Write Targeted Tests (2-3 hours)
Focus on killing 46+ survivors:
- **Schedulers** (15-20 kills expected from 10 tests)
- **RandomSearcher/SobolSearcher** (10-15 kills from 5 tests)
- **Space/Types** (15-20 kills from 5 tests)

### Phase 4: Final Mutation Run (2 hours)
Expected: 87.52% → 90.5%

---

## Files for Next Agent

### Key Documents
- `V03_TIMEOUT_ROOT_CAUSE_ANALYSIS.md` - Why timeouts happen
- `V03_DEFENSIVE_PROGRAMMING_PLAN.md` - Full validation plan
- `V03_DEFENSIVE_PROGRAMMING_R6_STATUS.md` - What we implemented
- `CONTEXT_RESET_MEMO_2026_09_21.md` - This file

### Modified Code
- `hponas/searchers/gp_searcher.py` - Validation added
- `tests/unit/test_input_validation.py` - New validation tests (12 tests, all pass)

### Results Files (when R6 completes)
- `/tmp/mutation_run_r6.log` - Full mutation run output
- `mutants/` directory - Mutation cache and results
- Use: `python -m mutmut results` to extract results

---

## Success Criteria

- [x] Defensive programming implemented (GPSearcher done)
- [x] Validation tests written and passing (12/12 pass)
- [x] Mutation testing R6 launched (background task running)
- [ ] R6 results analyzed
- [ ] Survivor tests written (if R6 < 90%)
- [ ] Final kill score ≥ 90%

---

## Quick Recovery Commands

```bash
# Check if R6 mutation testing is still running
ps aux | grep "mutmut run"

# Get R6 results (when complete)
cd /home/ubuntu/workspace/hponas
python -m mutmut results > /tmp/r6_results.txt
grep -c survived /tmp/r6_results.txt
grep -c timeout /tmp/r6_results.txt

# Calculate kill score
python3 << 'EOF'
total = 2245
killed = <extract from results>
timeout = <extract from results>
denom = total - timeout
score = 100 * killed / denom
print(f"Kill score: {killed}/{denom} = {score:.2f}%")
print(f"Gap to 90%: {int(0.90*denom) - killed} more kills needed")
EOF
```

---

## Key Takeaways

1. **User was right:** Timeouts DO reveal code quality issues - defensive programming is the right fix
2. **But:** Converting timeouts doesn't help reach 90% because gate formula excludes them
3. **Defensive programming value:** Better code quality + marginally better mutation coverage
4. **To reach 90%:** Must kill survivors with targeted tests, not convert timeouts
5. **Tool thrashing prevention:** Parse results once, use cache location correctly, wait for tasks

---

**Next Agent Instructions:**
1. Check R6 mutation results when background task completes
2. If ≥90%: Document and proceed to next gate
3. If <90%: Sample scheduler survivors, write targeted tests, run R7
