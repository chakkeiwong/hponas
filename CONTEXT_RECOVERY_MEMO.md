# V03 Mutation Testing - Context Recovery Memo

**Date:** 2026-09-22  
**Session:** Recovery from context thrashing  
**Phase:** V03 Gate - Mutation Testing

---

## Problem Diagnosed

The other agent experienced **context thrashing** due to:

1. **Tool usage inefficiency** - Made 10+ attempts to parse mutation results using different approaches instead of single `mutmut results` command
2. **Redundant file reads** - Repeatedly read the same output files trying different parsing methods
3. **Poor async handling** - Started 2-hour mutation test in background, then immediately polled it repeatedly
4. **Cache confusion** - Looked for `.mutmut-cache` in wrong directory (it's in `mutants/` subdirectory)
5. **Gateway 502/529 errors** - API instability compounded the thrashing

---

## Current Status Summary

### Mutation Testing Results (Round 5 Complete)

**Kill Score: 87.52%** (1592 killed / 1819 testable)
- Total mutations: 2245
- Killed: 1592 ✅
- Survived: 227 🙁
- Timeout: 394 ⏰ (17.6%, below 20% threshold)
- No tests: 32 🫥
- Suspicious: 0

**Gap to 90% target: 46 more kills needed**

**Formula (from v03_mutation_testing.py:157):**
```python
denominator = total - timeout - no_tests
kill_score = killed / denominator
= 1592 / (2245 - 394 - 32)
= 1592 / 1819
= 87.52%
```

### Progress History

| Round | Tests Added | Killed | Score | Change |
|-------|-------------|--------|-------|--------|
| Baseline | - | 1563 | 85.97% | - |
| R5 | 15 legacy_searchers tests | 1592 | 87.52% | +1.55pp |
| **Target** | **?** | **1638+** | **90%+** | **+2.48pp** |

---

## Key Insight from User

**User asked:** "Why can't we fix the problems that produce broken code?"

**This revealed:** The 394 timeout mutations are NOT just "slow operations" - they represent:
- Missing defensive validation in `__init__` methods
- Missing error handling for external libraries (BoTorch, Ray)
- Missing tests for corrupted state
- Code that hangs instead of failing fast

**Critical realization:** We can KILL timeout mutations by adding validation tests.

---

## The Opportunity

### Timeout Mutation Analysis

**Timeout budget:** 164 seconds (30x clean runtime of 4.47s) - MORE than sufficient

**Why timeouts occur:**
1. **Error message mutations** - String changes in error messages → wrong error shown → downstream code hangs
2. **Invariant violations** - `self.space = None` → every method call fails → test retry loops infinitely
3. **Logic inversions** - `if not ray.is_initialized()` → `if ray.is_initialized()` → initialization loop
4. **Type mutations** - `dict.get("key", {})` → `dict.get("key", None)` → `None.items()` raises → retry loop

**Timeout categories:**
- `__init__` validation: 52 timeouts
- State serialization: 8 timeouts  
- External lib init: 10 timeouts
- Other: 345 timeouts

---

## Revised Strategy

### Instead of: Kill 46 survivors (hard)

**Do: Kill 50-60 timeout mutations (easier and better)**

### Why This Is Better

1. **Higher yield** - Validation tests kill multiple related mutations
2. **Better code** - Forces defensive programming and fail-fast behavior
3. **Easier to write** - Validation tests are straightforward
4. **Compound benefit** - Improves both kill score AND code robustness

### Expected Impact

| Approach | Kills | New Score | Result |
|----------|-------|-----------|--------|
| Original (survivors) | +25 | 88.9% | Close but risky |
| **Validation tests** | **+60** | **90.8%** | **✅ Clear pass** |

---

## Next Steps

### Immediate Actions

1. **Create validation test file:**
   - `tests/unit/test_validation_robustness.py`
   - Target: 20 tests for `__init__` and state validation
   - Expected kills: 50-60 timeout mutations

2. **Test categories to add:**
   - GPSearcher `__init__` with invalid types (seed as string, float, list)
   - GPSearcher `__init__` with boundary values (seed=-1, seed=0, initial_random=0)
   - RandomSearcher/SobolSearcher invalid parameters
   - State corruption tests (None instead of dict, missing keys)
   - Scheduler validation (eta<=0, r_max<r_min)

3. **Run mutation testing:**
   - After tests pass, run: `rm -rf mutants/ && python -m mutmut run`
   - Wait ~2 hours for completion
   - Check results show 90%+ kill score

### Success Criteria

- ✅ Kill score ≥ 90%
- ✅ Timeout rate < 20%
- ✅ All new tests pass
- ✅ Code fails fast on invalid input

---

## Files to Reference

- **Current results:** `/tmp/r5_results.txt` (653 lines, already parsed)
- **Mutation output:** `/tmp/claude-1000/.../tasks/bsapi2ll9.output`
- **Gate validator:** `validation/v03_mutation_testing.py`
- **Test file to extend:** `tests/unit/test_searchers.py` OR create new validation file
- **Strategy doc:** `REVISED_STRATEGY.md`
- **Timeout analysis:** `TIMEOUT_ANALYSIS.md`

---

## Survivor Breakdown (For Reference)

Still 227 survivors, but **lower priority** now:

| Module | Survivors | % |
|--------|-----------|---|
| schedulers | 82 | 36.1% |
| searchers.random_searcher | 46 | 20.3% |
| executors.local_executor | 31 | 13.7% |
| legacy_searchers | 30 | 13.2% |
| space | 28 | 12.3% |
| types | 10 | 4.4% |

---

## Tool Usage Guidelines for Next Agent

**DO:**
- ✅ Use `mutmut show <id>` to inspect specific mutations
- ✅ Write tests, verify with pytest, then run mutation testing ONCE
- ✅ Wait for background tasks (you'll get notification when complete)
- ✅ Use single commands to get data (don't try multiple parsing approaches)

**DON'T:**
- ❌ Poll background mutation testing (it takes 2 hours, you'll be notified)
- ❌ Try multiple ways to parse the same data
- ❌ Look for `.mutmut-cache` (it's actually `mutants/mutmut-stats.json`)
- ❌ Re-run mutation testing multiple times to "check progress"

---

## Master Program Phase

**Current:** V03 Gate - Mutation Testing  
**Status:** 87.52% (46 kills from target)  
**Next:** Write validation tests → Kill timeouts → Reach 90%+ → Move to V04 gate

---

## Summary

The user's question revealed the real path forward: **Kill timeout mutations by adding defensive validation tests.** This is both easier and better than chasing survivors. We need 60 timeout kills to comfortably pass 90%, and validation tests targeting `__init__` methods and state corruption will get us there.

**Ready to execute: Write validation tests, run mutation testing, achieve 90%+.**
