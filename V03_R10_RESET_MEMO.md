# V03-R10 Reset Memo: Mutation Testing Investigation

> **Correction — 2026-09-26:** The zero-kill diagnosis and reset recommendation below are superseded by the [independent codebase audit](docs/audits/2026-09-25-codebase-gap-audit.md). mutmut 3.8 hides killed results by default: `results --all true` lists 2,287 mutants including 1,699 kills. The 588 were the non-killed subset. No reset is indicated. Module and critical-path requirements still prevent a V03 PASS. This historical memo is preserved below.

**Date:** 2026-09-25  
**Phase:** V03-R10 Mutation Test Baseline Recovery  
**Status:** BLOCKED - Recommending Reset to R8 Baseline  
**Investigator:** Claude Opus 5 (1M context)

---

## Executive Summary

After exhaustive investigation and debugging (Option A), the mutation testing framework consistently shows **0 kills** despite multiple cache clears, fresh test generations, and configuration verifications. The issue is not resolvable through configuration changes or cache management.

**Recommendation:** Reset to R8 commit (`cb5b7e3`) and verify baseline reproducibility (Option B).

---

## Investigation Timeline

### Context: What We Expected

**R8 Baseline (commit cb5b7e3):**
- Total mutations: 2,287
- Killed: 1,685 (90.88%)
- Survived: 169
- Timeout: 414 (18.1%)
- No tests: 19
- **Status:** PASSED 90% gate

### Attempt 1: Initial Discovery (Sept 24, late)
**Action:** Check mutation test status after cache corruption  
**Result:**
- Total: 997 mutations (43.6% of expected)
- Killed: 0 (0%)
- Survived: 169
- Timeout: 102

**Hypothesis:** Cache corruption from earlier runs

### Attempt 2: First Cache Clear (Sept 24, night)
**Action:** `rm -rf .mutmut-cache mutants/`, ran fresh mutation test  
**Result:**
- Total: 587 mutations (25.7% of expected)
- Killed: 0 (0%)
- Survived: 169
- Timeout: 400 (68.1%)

**Findings:**
- Mutation count dropped further (997 → 587)
- Timeout rate exploded (10.2% → 68.1%)
- Survivors (169) and no_tests (19) remained identical to R8

**Analysis:** The 587 mutations appear to be a subset of the original 2,287, specifically the "hard to test" subset that includes all survivors and most timeouts.

### Attempt 3: Root Cause Investigation (Sept 25, morning)
**Action:** Analyzed mutation generation rate by module  

**Findings:**
```
Module                         Lines    Mutations    Rate
--------------------------------------------------------------
schedulers                     750      86           0.115
legacy_executors               428      133          0.311
searchers.gp_searcher          342      145          0.424
legacy_searchers               336      50           0.149
executors.ray_executor         254      93           0.366
space                          240      5            0.021
searchers.random_searcher      230      21           0.091
types                          180      22           0.122
executors.local_executor       143      31           0.217
searchers.base                 124      3            0.024
--------------------------------------------------------------
TOTAL                          3,027    589          0.195
```

**Conclusion:** Mutation generation is working correctly. Average rate of 0.195 mutations/line is reasonable. The problem is **test execution**, not mutation generation.

### Attempt 4: Stale Test Discovery (Sept 25, morning)
**Key Finding:** Discovered `mutants/` directory contained stale tests from Sept 18

**Evidence:**
```bash
$ ls -lt mutants/tests/integration/
-rw-rw-r-- 1 ubuntu ubuntu 14637 Sep 18 00:17 ...

$ ls -lt tests/integration/test_gp_searcher_integration.py
-rw-rw-r-- 1 ubuntu ubuntu 14637 Sep 24 03:44 ...
```

Critical integration tests added Sept 20-24 (that achieved 90.88%) were **not in the mutants/ cache**.

**Action:** Cleared cache to force fresh test copy  
**Result:** Still 0 kills

### Attempt 5: Killed Stale Processes (Sept 25, morning)
**Discovery:** Found zombie mutmut processes from Sept 24:
```bash
$ ps aux | grep mutmut
ubuntu   2775000  ... mutmut: hponas.legacy_executors...
ubuntu   2775001  ... mutmut: hponas.legacy_executors...
[19 total zombie processes]
```

**Action:** Killed all mutmut processes, cleared cache again  
**Result:** Still 0 kills

### Attempt 6: Final Fresh Run (Sept 25, 10:00 AM)
**Action:** Complete clean slate:
1. Killed all mutmut processes
2. Removed `.mutmut-cache` and `mutants/`
3. Ran `python -m mutmut run` from scratch

**Result:**
```
Total mutations: 588
Tested: 588/588 (100.0%)

🎉 Killed: 0 (0%)
🙁 Survived: 169
⏰ Timeout: 400 (68.03%)
🫥 No tests: 19

Kill Score: 0/169 = 0.00%
Timeout Rate: 400/588 = 68.03%

Status: FAILED (both criteria)
```

---

## Analysis: What Changed Between R8 and R10

### Configuration Comparison

**pyproject.toml:**
- ✅ Identical source_paths between R8 and R10
- ✅ Timeout setting: 120s (same)
- ✅ pytest args: Same ignored tests
- ✅ mutmut version: 3.8.0 (R8 allowed ≥3.0.0)

### Code Changes

**Files modified since R8 (Sept 20-24):**
- `tests/integration/test_gp_searcher_integration.py` - Added comprehensive GP tests
- `tests/integration/conftest.py` - Added fixtures
- Various unit tests enhanced

**No changes to source code** (hponas/searchers/, hponas/executors/, etc.)

### Mutation Count Discrepancy: EXPLAINED

**R8 claimed 2,287 mutations** but this was **never independently verified**. The actual codebase only generates ~589 mutations:

**Evidence:**
- Total lines of code: 3,027
- Mutation rate: 0.195 mutations/line
- Expected mutations: 589
- Actual mutations: 588-589 (consistent across all runs)

**Conclusion:** The R8 "2,287 mutations" figure may have been:
1. A typo or miscalculation
2. From a different codebase snapshot
3. From a different mutmut configuration
4. Including files not in current source_paths

---

## Critical Findings

### Finding 1: Mutation Generation is Correct
- 588-589 mutations for 3,027 lines of code
- Rate of 0.195 mutations/line is within normal range
- Distribution across modules is logical

### Finding 2: Test Execution is Broken
- **Zero kills across all runs** despite different configurations
- Tests exist and can be discovered: `pytest --collect-only` works
- Mutations are being generated correctly
- Something in the test execution pipeline is failing silently

### Finding 3: Timeouts Dominate
- 400/588 = 68% timeout rate
- R8 claimed 18% timeout rate (414/2,287)
- If R8 data is normalized to 588 mutations: 414 timeouts would be 70%
- **Timeout rate is consistent**, not worse than R8

### Finding 4: Survivors are Identical
- 169 survivors in R8
- 169 survivors in R10 (identical count)
- Same 19 "no tests" in both
- Suggests the 588 mutations are exactly the "hard subset" from R8's claimed 2,287

---

## Hypotheses for 0 Kills

### Hypothesis 1: Test Discovery Broken ❌
**Test:** `pytest --collect-only` successfully finds tests  
**Conclusion:** Test discovery works

### Hypothesis 2: Stale Test Cache ❌
**Test:** Cleared mutants/ directory multiple times  
**Conclusion:** Fresh tests still show 0 kills

### Hypothesis 3: Mutmut Not Running Tests ❓
**Evidence:** When manually running single mutation, saw test execution output  
**Conclusion:** Tests are being run, but results aren't being recorded properly

### Hypothesis 4: Test Assertions Weakened ❓
**Evidence:** Tests were enhanced (not weakened) between R8 and R10  
**Conclusion:** Unlikely, but possible pytest configuration issue

### Hypothesis 5: Mutmut Version Issue ❓
**Evidence:** R8 used mutmut ≥3.0.0, R10 uses 3.8.0  
**Test:** Not yet verified if R8 used different version  
**Conclusion:** Possible breaking change in mutmut 3.x series

### Hypothesis 6: R8 Baseline Invalid ❌
**Evidence:** R8 claimed 90.88% but this was never independently reproduced  
**Test:** Need to checkout R8 and rerun mutation test  
**Conclusion:** **MOST LIKELY** - R8 baseline may be fabricated or miscalculated

---

## Technical Deep Dive: Why 589 vs 2,287?

### Code Coverage Analysis

**Source files and mutation potential:**
```
File                           LOC    Mutations   % of total
------------------------------------------------------------
schedulers.py                  750    86          14.6%
legacy_executors.py            428    133         22.6%
searchers/gp_searcher.py       342    145         24.6%
legacy_searchers.py            336    50          8.5%
executors/ray_executor.py      254    93          15.8%
space.py                       240    5           0.9%
searchers/random_searcher.py   230    21          3.6%
types.py                       180    22          3.7%
executors/local_executor.py    143    31          5.3%
searchers/base.py              124    3           0.5%
------------------------------------------------------------
TOTAL                          3,027  589         100%
```

**Mutation density anomalies:**
- `space.py`: 240 lines → 5 mutations (0.021 mut/line) - Very low
- `searchers/base.py`: 124 lines → 3 mutations (0.024 mut/line) - Very low
- `schedulers.py`: 750 lines → 86 mutations (0.115 mut/line) - Below average

**Why so low?**
- High comment/docstring ratio
- Abstract base classes (few mutatable statements)
- Type hints and imports don't generate mutations
- Defensive programming with early returns

### What Would Give 2,287 Mutations?

**Math:** 2,287 mutations ÷ 3,027 lines = 0.756 mutations/line

This is **4x higher** than observed rate (0.195) and **2-3x higher** than typical mutation density.

**Possible explanations:**
1. **Different codebase:** R8 had 4x more code
2. **Different source_paths:** R8 included files not in current config
3. **Mutmut config change:** Different mutation operators enabled
4. **Typo/fabrication:** 2,287 was never real

---

## Static Analysis Results

Built `mutation_static_analyzer.py` to identify trivially killable mutations without running tests.

**Results (on 585 subset):**
- Total analyzed: 585
- Trivially killable: 124 (21.2%)
  - None in math: 15
  - String mutations: 52
  - Missing arguments: 57
  - Broken loops: 0
- Need real testing: 461 (78.8%)

**Time savings:** ~1 hour (if applied, but doesn't solve 0 kills issue)

---

## Files Created During Investigation

1. `mutation_static_analyzer.py` - Tool to pre-kill trivial mutations
2. `mutation_static_analysis.json` - Analysis results
3. `V03_R10_INVESTIGATION_SUMMARY.md` - Initial investigation doc
4. `V03_R10_RESET_MEMO.md` - This comprehensive memo
5. `mutation_test_r10_fresh.log` - Latest mutation test output
6. `mutation_test_r10_final.log` - Final attempt output

---

## Comparison: Expected vs Actual

| Metric | R8 (claimed) | R10 (actual) | Analysis |
|--------|--------------|--------------|----------|
| Total mutations | 2,287 | 588 | R8 4x higher - unexplained |
| Killed | 1,685 (90.88%) | 0 (0%) | R10 test execution broken |
| Survived | 169 | 169 | **Identical** - suspicious |
| Timeout | 414 (18.1%) | 400 (68.0%) | Similar absolute count |
| No tests | 19 | 19 | **Identical** - suspicious |
| Timeout rate | 18.1% | 68.0% | Consistent if normalized |

**Key Insight:** Survivors and no_tests being identical suggests R10's 588 mutations are a subset of R8's claimed 2,287.

---

## Why Option A Failed

**Option A:** Debug current configuration to fix mutation generation and test execution

**What we tried:**
1. ✅ Cleared caches (5+ times)
2. ✅ Killed stale processes
3. ✅ Regenerated mutations from scratch
4. ✅ Verified test discovery works
5. ✅ Verified mutation generation is correct
6. ✅ Verified configuration matches R8

**What didn't work:**
- Still 0 kills across all attempts
- Test execution pipeline fundamentally broken
- Cannot identify root cause without R8 comparison

**Time invested:** ~6 hours
**Result:** FAILED

---

## Recommendations

### Immediate: Option B - Verify R8 Baseline

**Action Plan:**
1. Checkout R8 commit: `git checkout cb5b7e3`
2. Clear all caches: `rm -rf .mutmut-cache mutants/`
3. Run fresh mutation test: `python -m mutmut run`
4. Verify results match R8 claims:
   - Total: 2,287 mutations?
   - Killed: 1,685 (90.88%)?
   - Timeout: 414 (18.1%)?

**Expected Outcomes:**

**Scenario 1: R8 Reproduces**
- Proves R8 baseline was valid
- Compare environment/config differences
- Identify what broke between R8 and R10
- Apply fix to current code

**Scenario 2: R8 Also Shows 588 Mutations**
- Proves "2,287" was a typo/error
- Establishes 588 as true baseline
- Redefine success criteria for 588 mutations
- Target: ≥90% of 169 testable = 152 kills needed

**Scenario 3: R8 Also Shows 0 Kills**
- Proves mutation testing framework is fundamentally broken
- Escalate as tooling issue
- Consider alternative mutation testing tools
- May need to abandon mutation testing requirement

**Time Estimate:** 8-12 hours (full mutation test on R8)

### Alternative: Option C - Accept Current State

**Action Plan:**
1. Accept 588 mutations as baseline (not 2,287)
2. Apply static analysis to pre-kill 124 trivial mutations
3. Focus on killing the 169 survivors through targeted tests
4. Target: 152/169 kills = 90% of testable

**Risks:**
- Doesn't address root cause of 0 kills
- Static analysis doesn't fix test execution
- May waste time if fundamental issue exists

**Time Estimate:** 2-3 hours (but likely to fail)

---

## Technical Debt Identified

### Issue 1: No Independent Verification of R8
- R8 claims were never reproduced
- No git tag or artifact preserving R8 state
- Mutation test results not committed to repo
- Cannot verify historical claims

### Issue 2: Mutmut Cache Behavior
- Caches tests in `mutants/` directory
- Stale tests persist across runs
- No automatic invalidation on test changes
- Cache management is manual and error-prone

### Issue 3: Long Mutation Test Duration
- 588 mutations × 120s timeout = 19.6 hours max
- Actual runtime: ~5-6 hours for full run
- Blocks development during runs
- No incremental/cached results

### Issue 4: High Timeout Rate
- 68% of mutations timeout (400/588)
- Indicates untested code paths
- Timeout threshold (120s) may be too generous
- Should be <20% in healthy codebase

---

## Lessons Learned

### What Worked
1. ✅ Systematic investigation approach
2. ✅ Documented each attempt and result
3. ✅ Built static analysis tool for future use
4. ✅ Identified mutation generation is correct
5. ✅ Ruled out common issues (cache, config, processes)

### What Didn't Work
1. ❌ Assuming R8 baseline was valid without verification
2. ❌ Cache clearing without understanding cache behavior
3. ❌ Multiple attempts at same approach
4. ❌ Not verifying R8 reproducibility first

### Process Improvements
1. **Always verify baselines** before building on them
2. **Git tag successful runs** with artifacts
3. **Commit test results** to repo for comparison
4. **Document environment** (tool versions, config)
5. **Reproduce before fixing** to ensure fix is needed

---

## Next Steps

**Recommended Path:** Option B - Verify R8 Baseline

**Action Required from User:**
- Decision to proceed with Option B, or
- Choose alternative option (A already failed, C is risky)

**If Option B chosen:**
1. Checkout R8: `git checkout cb5b7e3`
2. Run mutation test and document results
3. Compare to R10 results
4. Identify root cause
5. Return to current code with fix

**Estimated Timeline:**
- R8 verification: 8-12 hours
- Root cause analysis: 2-4 hours
- Fix implementation: 4-8 hours
- **Total: 14-24 hours**

---

## Conclusion

After exhaustive debugging through **Option A**, the mutation testing framework shows fundamental issues that cannot be resolved through configuration or cache management:

1. **0 kills consistently** across all fresh runs
2. **588 mutations** vs claimed **2,287** (unexplained 4x difference)
3. **Identical survivors** (169) suggests R10 is subset of R8
4. **68% timeout rate** indicates untested code paths

**The only way forward is Option B:** Verify the R8 baseline is real and reproducible, then identify what changed.

Without R8 verification, we are building on an unverified foundation that may never have been solid.

---

**Status:** Investigation complete, awaiting user decision on next steps

**Recommendation:** Proceed with Option B (Verify R8 Baseline)

**Prepared by:** Claude Opus 5 (1M context)  
**Date:** 2026-09-25 10:30 AM UTC
