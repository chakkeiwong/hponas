# V03 Next Steps - Path to 90%

**Date:** 2026-09-18  
**Current Status:** 85.67% (1554/1814 kills)  
**Target:** 90% (1632 kills)  
**Gap:** 78 kills needed

---

## Strategic Options

### Option A: Target Schedulers (86 survivors) - HIGHEST IMPACT
**Rationale:** Schedulers have 86 survivors (33% of total), highest concentration.

**Approach:**
1. Analyze scheduler survivors by method
2. Add targeted tests for promotion logic, rung management, stopping decisions
3. Focus on ASHA, PASHA, MOASHA methods beyond report()

**Estimated kills:** 40-60 (enough to reach 90% if we get ~55+)

**Estimated effort:** 2-3 hours of focused test writing

**Risk:** Medium - schedulers are complex, may have equivalent mutants

---

### Option B: Target legacy_searchers (58 survivors) - FAMILIAR TERRITORY
**Rationale:** Already familiar with SobolSearcher code, know the patterns.

**Approach:**
1. Examine which specific Sobol mutations survived despite fix
2. Add tests for edge cases: boundary values, categorical handling, log-scale
3. May reveal additional bugs (like the division bug we just found)

**Estimated kills:** 30-45 (may not be enough alone, but high confidence)

**Estimated effort:** 1-2 hours

**Risk:** Low - already understand this code well

---

### Option C: Combined Strategy - BALANCED APPROACH
**Rationale:** Attack two highest targets for diversified progress.

**Phase 1 - legacy_searchers (1 hour):**
- Examine survived Sobol mutations
- Add edge case tests
- Target: +30 kills

**Phase 2 - Schedulers (1.5 hours):**
- Add scheduler tests for promotion/stopping
- Target: +48 kills

**Total estimated: +78 kills (exactly what we need!)**

**Estimated effort:** 2.5 hours total

**Risk:** Medium - depends on both targets yielding expected kills

---

### Option D: Investigate Survivors First - SURGICAL APPROACH
**Rationale:** Don't guess, examine actual survived mutations to see what's testable.

**Approach:**
1. Use `mutmut show` to examine 10-20 survived mutations across top files
2. Categorize: dead code, equivalent mutants, untested logic, edge cases
3. Write targeted tests only for testable survivors
4. Document equivalent mutants for skipping

**Estimated kills:** 60-80 (high precision targeting)

**Estimated effort:** 3-4 hours (includes investigation time)

**Risk:** Low - data-driven, no wasted effort

---

## Recommendation

**Immediate next step:** Option D (Investigate Survivors First)

**Why:**
1. We don't actually know WHY these 260 mutants survived
2. Some may be equivalent mutants (unkillable without false positives)
3. Some may be dead code we haven't found yet
4. Writing tests blindly wastes effort if mutations aren't testable
5. Investigation gives us the data to make optimal test-writing decisions

**Process:**
1. Sample 5-10 survivors from each major file
2. Use `mutmut show <id>` to see exact mutations
3. Categorize each:
   - ✅ Testable - write a test
   - ⚠️ Equivalent - document and skip
   - 🔍 Dead code - remove code
   - ❓ Unclear - investigate further
4. Extrapolate from sample to full survivor set
5. Execute targeted test writing for testable survivors

**Expected timeline:**
- Investigation: 1 hour
- Test writing: 2 hours
- Mutation re-run: 1.5 hours
- Total: 4.5 hours to completion

---

## Detailed Investigation Plan

### Step 1: Sample Schedulers (30 minutes)
```bash
# Get scheduler survivor IDs
python -m mutmut results | grep "hponas.schedulers" | grep "survived" | head -10

# Examine each with mutmut show
mutmut show <id>
```

**Questions to answer:**
- Which scheduler methods have survivors?
- Are they in promotion logic, stopping logic, or rung management?
- Are any in error messages or logging?
- Any dead code patterns?

### Step 2: Sample legacy_searchers (20 minutes)
```bash
# Get legacy_searchers survivor IDs
python -m mutmut results | grep "legacy_searchers" | grep "survived" | head -10
```

**Questions to answer:**
- Which Sobol mutations survived despite arithmetic fix?
- Are they in edge cases (bounds, empty choices, log-scale with negatives)?
- Any categorical handling gaps?
- Any state serialization issues?

### Step 3: Sample searchers/random_searcher (15 minutes)
```bash
# Get random_searcher survivor IDs
python -m mutmut results | grep "searchers/random_searcher" | grep "survived" | head -10
```

**Questions to answer:**
- New API vs old API compatibility issues?
- State management gaps?
- RNG seeding edge cases?

### Step 4: Sample executors/local_executor (15 minutes)
```bash
# Get local_executor survivor IDs
python -m mutmut results | grep "local_executor" | grep "survived" | head -10
```

**Questions to answer:**
- Error handling gaps?
- Resource management untested?
- Process lifecycle issues?

### Step 5: Sample space (10 minutes)
```bash
# Get space survivor IDs
python -m mutmut results | grep "hponas/space" | grep "survived" | head -10
```

**Questions to answer:**
- Knob validation gaps?
- Bounds checking edge cases?
- Type conversion issues?

---

## After Investigation

Based on investigation results, create targeted test plan:

### Template for Each Testable Survivor
```markdown
**Mutation ID:** <id>
**File:** <file>:<line>
**Method:** <method>
**Mutation:** <original> → <mutated>
**Category:** Testable
**Test to write:** <description>
**Estimated effort:** <minutes>
```

### Template for Equivalent Mutants
```markdown
**Mutation ID:** <id>
**File:** <file>:<line>
**Method:** <method>
**Mutation:** <original> → <mutated>
**Category:** Equivalent
**Reason:** <why it's equivalent>
**Action:** Document and skip
```

### Template for Dead Code
```markdown
**Mutation ID:** <id>
**File:** <file>:<line>
**Method:** <method>
**Code:** <snippet>
**Category:** Dead code
**Action:** Remove from source
```

---

## Execution Checklist

- [ ] Step 1: Sample and categorize 50 survivors (1 hour)
- [ ] Step 2: Create prioritized test-writing plan (15 minutes)
- [ ] Step 3: Write tests for top N testable survivors (2 hours)
- [ ] Step 4: Remove any dead code found (15 minutes)
- [ ] Step 5: Document equivalent mutants (15 minutes)
- [ ] Step 6: Run mutation testing (1.5 hours)
- [ ] Step 7: Analyze results and iterate if needed (30 minutes)

**Total estimated:** 5.5 hours to 90% or data-driven decision to stop

---

## Alternative: Accept 85.67% as "Good Enough"

**Case for stopping:**
- 85.67% is strong test quality (research prototype, not production system)
- +198 kills improvement shows commitment to test quality
- Fixed critical production bug (main value of this exercise)
- Remaining 78 kills may be mostly equivalent mutants or edge cases
- Diminishing returns - each additional kill gets harder

**Case for continuing:**
- V03 gate explicitly requires 90%
- User said "we should not defer the problem"
- Only 78 kills away (4.33% gap)
- Investigation may reveal more bugs (like the Sobol bug)

**Recommend:** Continue to investigation phase, then decide based on what we find.
