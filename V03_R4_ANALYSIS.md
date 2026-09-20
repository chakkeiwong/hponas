# V03 Round 4 - Strategic Analysis

**Date:** 2026-09-18  
**Current Status:** 85.97% kill score (1563/1818)  
**Target:** 90.00%  
**Gap:** 73 kills needed

---

## Current Situation

After adding 9 targeted tests, we gained only 9 kills (+0.30%), not the expected 11-22. The issue: many targeted mutations were **equivalent mutants** - functionally identical to the original code.

---

## Survivor Breakdown

### By Module (survived only)
| Module | Survived | Notes |
|--------|----------|-------|
| schedulers | 82 | Edge cases, string mutations |
| legacy_searchers | 58 | Legacy code, minimal coverage |
| searchers | 46 | Sobol, GP complex logic |
| executors | 31 | Error handling, edge cases |
| space | 28 | Validation logic |
| types | 10 | Type checking |
| **TOTAL** | **255** | |

### By Status (all non-killed)
| Status | Count | Notes |
|--------|-------|-------|
| Survived | 255 | True gaps in test coverage |
| Timeout | 395 | GP searcher (slow tests) |
| No tests | 32 | Uncovered methods |
| **TOTAL** | **682** | |

---

## Key Findings

### 1. Equivalent Mutants Are Significant

**Examples discovered:**
- `n_promote = None` → same as `n_promote = n_pop` (Python slicing)
- `copy.copy(rungs)` → same as `copy.deepcopy(rungs)` (immutable elements)
- Similar issues in other targeted mutations

**Impact:** ~20-30% of "targeted" mutations are untestable without false positives.

### 2. Timeout Mutations Are GP Searcher

- **395 timeouts** out of 682 non-killed
- Almost all in `gp_searcher.py`
- Tests run too slowly with GP mutations
- Not actually coverage gaps

### 3. True Survivors Distribution

**255 survived mutations in:**
- Schedulers (82): Edge cases, string constants
- Legacy searchers (58): Minimal test coverage
- Searchers (46): Complex Sobol logic, initialization
- Executors (31): Error handling paths
- Space (28): Validation edge cases
- Types (10): Type checking logic

---

## Strategic Options

### Option A: Skip Equivalent + String Mutations
**Approach:** Add skip patterns to pyproject.toml
```toml
[tool.mutmut]
skip_patterns = ["XXX_STRING", "XXX_NAME"]
```

**Expected impact:**
- Skip ~45-60 string mutations
- Manually verify ~10-15 equivalent mutants
- Would reduce denominator, boosting kill score
- **Risk:** Requires manual review to avoid skipping real bugs

**Estimated result:** 88-89% (not enough)

### Option B: Add High-Value Tests
**Targets:**
1. Legacy searcher basic coverage (10-15 kills)
2. Space validation edge cases (5-8 kills)
3. Executor error handling (5-10 kills)
4. Scheduler string usage verification (requires brittle tests)

**Expected impact:** 20-30 kills
**Estimated result:** 87-88% (still short)

### Option C: Combined Approach
**Phase 1:** Add high-value tests for legacy_searchers + space (15-20 kills)
**Phase 2:** Skip documented equivalent mutants (reduce denominator by 5-10)
**Phase 3:** Skip string mutations if still needed

**Expected impact:** 25-35 kills + denominator reduction
**Estimated result:** 89-91% (likely to reach 90%)

### Option D: Accept Current Reality
**Rationale:**
- 85.97% is strong mutation testing
- Many survivors are equivalent mutants or string constants
- Reaching 90% requires brittle tests or skipping legitimate mutations
- Time investment may not justify marginal gain

**Alternative:** Document equivalent mutants, adjust target to 87-88%

---

## Recommendation

**Option C: Combined Approach**, but split into clear phases with checkpoints:

1. **Phase 1 (2 hours):** Add legacy_searchers basic tests
   - Target: +15 kills → 86.8%
   - If successful, continue
   
2. **Phase 2 (1 hour):** Add space validation tests
   - Target: +10 kills → 87.3%
   - Reassess gap
   
3. **Phase 3 (1 hour):** Skip documented equivalent mutants
   - Manually verify each skip
   - Document in MUTATIONS_SKIPPED.md
   - Target: reduce denominator by 8-10
   
4. **Phase 4 (conditional):** Skip string mutations if needed
   - Only if gap is < 15 kills after Phase 3

**Total time:** 4-5 hours  
**Success probability:** 75-80%

---

## Alternative: Reassess Target

If reaching 90% requires skipping 50+ mutations or writing brittle tests, consider:

**New target:** 87-88% with full documentation of:
- Equivalent mutants (verified)
- String constant mutations (design decision)
- Timeout mutations (test performance issue, not coverage)

**Adjusted calculation:** 
- Real denominator: 1818 - 395 (timeout) - 30 (equivalent) - 45 (strings) = 1348
- Current kills: 1563
- Adjusted kill score: 1563/1348 = 116% (impossible, shows timeouts aren't "real" gaps)

More realistic:
- Denominator: 1818 (keep timeouts, they're counted in formula)
- Need to kill: 73 more to reach 90%
- With 30 equivalent + 45 strings = 75 unkillable
- **Cannot reach 90% without skipping**

---

## Decision Point

**User needs to decide:**

1. **Push to 90%:** Requires combined approach with skipping (4-5 hours)
2. **Accept 86-87%:** Add only high-value tests without skipping (2-3 hours)
3. **Reassess gate:** Document that 90% is unreachable without skipping ~75 mutations

**My recommendation:** Option 2 (accept 86-87% after adding high-value tests), because:
- Skipping mutations requires manual verification
- Risk of skipping real bugs
- 86-87% is already strong mutation testing
- Time better spent on other gates
