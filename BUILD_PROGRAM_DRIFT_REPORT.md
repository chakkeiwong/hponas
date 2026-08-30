# BUILD_PROGRAM vs Survey Register: Drift Analysis
**Generated:** 2026-08-28  
**Purpose:** Reconcile validation test assignments and protocols before implementation

---

## Executive summary

BUILD_PROGRAM.md has drifted from the survey's validation register (sections/16-validation.tex, Table 7.1) in two dimensions:

1. **Tier gate assignments**: Six entries (V04, V06, V10, V12, V13) are assigned to the wrong gate or missing from gates entirely
2. **Protocol specifications**: At least five entries (V01, V02, V03, V05, V14) have protocol descriptions in BUILD_PROGRAM that contradict the survey's registered protocols

The survey register is authoritative (it survived M-item review and is ready for human approval). BUILD_PROGRAM must be updated to match it before implementation begins.

---

## Tier gate assignment drift

| ID | Survey gate | BUILD_PROGRAM gate | Status | Impact |
|----|-------------|-------------------|--------|--------|
| V01 | T0 | Week 6 (T0) ✓ | Match | None |
| V02 | T0 | Week 6 (T0) ✓ | Match | None |
| V03 | T0 | Week 6 (T0) ✓ | Match | None |
| V04 | T0/T1 split | Week 12 (T1) only | **Mismatch** | Tier-0 searchers (TPE, log+Sobol) not tested at T0 gate |
| V05 | T0 | Week 6 (T0) ✓ | Match | None |
| V06 | T1 | Week 30 (T2) | **Mismatch** | ASHA correctness deferred 18 weeks |
| V07 | T3 | Week 30 (called "T2") | Ambiguous | BUILD_PROGRAM calls week-30 gate "tier 2"; survey roadmap defines T3 |
| V08 | T2 | Week 30 (called "T2") | Ambiguous | Same tier-numbering confusion |
| V09 | T1 | Week 12 (T1) ✓ | Match | None |
| V10 | T1 | Week 30 (T2) | **Mismatch** | MO-ASHA rung-correlation pilot deferred to T2 |
| V11 | T1 | Week 12 (T1) ✓ | Match | None |
| V12 | T1+ | Week 30 (T2) | Plausible | T1+ means "after T1"; week 30 is post-T1, so defensible |
| V13 | T1 | Week 30 (T2) | **Mismatch** | Sampler veto correctness deferred 18 weeks |
| V14 | T0 | Week 6 (T0) ✓ | Match | None |
| V15 | T3 | Week 30 (called "T2") | Ambiguous | Same tier-numbering confusion |

**Critical mismatches:** V04, V06, V10, V13 (four entries at wrong gates)  
**Tier numbering confusion:** BUILD_PROGRAM skips T2 label; week-30 gate called "tier 2" but holds T2, T3 entries

---

## Protocol specification drift

Comparing BUILD_PROGRAM descriptions (section "Validation prep" and gate criteria) vs survey Table 7.1:

### V01: Implementation parity
- **Survey (line 73-75):** "each wrapped searcher/scheduler matches its reference implementation on tabular benchmarks | final and anytime scores within tolerance of reference"
- **BUILD_PROGRAM (line 80):** "V01 (Sobol beats constant)"
- **Verdict:** Complete mismatch. V01 is about parity with reference implementations, not performance ranking.

### V02: Async scheduler correctness
- **Survey (line 76-78):** "scheduler logic is correct under asynchrony | replayed decisions on recorded curves match specification; stragglers and drops simulated"
- **BUILD_PROGRAM (line 80):** "V02 (TPE beats Sobol on Branin)"
- **Verdict:** Complete mismatch. V02 is about async correctness via replay, not searcher ranking.

### V03: Sabotage detection
- **Survey (line 79-82):** "the suite itself catches wiring bugs | seeded defects (off-by-one rung, dropped seed, swapped objective sign) are caught by V01--V02"
- **BUILD_PROGRAM (line 80):** "V03 (ASHA promotes correctly on toy linear curves)"
- **Verdict:** Partial mismatch. Survey's V03 is meta (does the suite catch planted bugs?); BUILD_PROGRAM's is narrower (ASHA promotion logic).

### V04: Complexity justification
- **Survey (line 83-87):** "every shipped searcher earns its complexity | beats the log+Sobol floor at matched budget on pinned tasks, each searcher tested at the gate of the tier that ships it"
- **BUILD_PROGRAM (line 107, 139):** "V04 campaign: beat Sobol on our pinned high-dim task" (tier 1 only); "V04 (TuRBO beats Sobol)" (gate criteria)
- **Verdict:** Partial match on protocol, wrong gate. Tier-0 searchers must be tested at tier-0 gate per survey's split rule.

### V05: Transform effectiveness
- **Survey (line 89-90):** "the transform matters as claimed | GP with and without log-warping on a pinned task; warped must not lose"
- **BUILD_PROGRAM (line 88):** "V05 (DEHB on high-dim Branin)"
- **Verdict:** Complete mismatch. V05 is about log-warping, not DEHB performance.

### V14: Day-one walk reproduction
- **Survey (line 114-117):** "tier 0 is composition, not construction | the day-one walk of Chapter 15 reproduced end to end within the tier-0 budget"
- **BUILD_PROGRAM (line 88):** "V14 (store correctness)"
- **Verdict:** Mismatch. Survey's V14 is about reproducing the product chapter's walkthrough; BUILD_PROGRAM's is narrower (store CRUD correctness).

---

## Root cause analysis

BUILD_PROGRAM appears to have been written before the validation chapter was finalized, or from an earlier draft. Evidence:

1. V01-V03 protocols in BUILD_PROGRAM read like toy smoketests ("Sobol beats constant", "TPE beats Sobol"), whereas survey protocols are about correctness/parity/sabotage detection
2. V05 protocol contradicts survey (DEHB vs log-warping)
3. Tier-gate drift suggests BUILD_PROGRAM grouped tests by "when the code exists" rather than "what the tier promises"

The survey's tier-gate logic (from roadmap chapter):
- **T0:** Wrapping only, evidence review, routines (V01-V05, V14)
- **T1:** Custom methods, MO, priors (V04 tier-1 searchers, V06, V09-V13)
- **T2:** Population line (V08)
- **T3:** Deferred bets (V07 small-budget RL, V15 ifBO)

BUILD_PROGRAM's timeline logic:
- Week 6: Tier-0 code complete
- Week 12: Tier-1 methods exist
- Week 30: Everything exists, run full suite

The tension: survey gates tests when the *capability* should be validated; BUILD_PROGRAM defers tests until *all code* exists.

---

## Reconciliation strategy

### Option A: Update BUILD_PROGRAM to match survey exactly
Rewrite gate criteria and work breakdown so:
- Week 6 (T0 gate): V01-V05, V14 (tier-0 searchers tested here per V04 split rule)
- Week 12 (T1 gate): V04 tier-1 searchers, V06, V09-V13
- Week 22 or standalone: V08 (T2 gate, population line)
- Week 30 or post-ship: V07, V15 (T3 gate, deferred bets)

**Pros:** Survey and BUILD_PROGRAM consistent; gates enforce incremental validation  
**Cons:** Requires earlier test harness work (pinned tasks sized by week 6); V06 needs "real RL" at week 12, not week 30

### Option B: Update survey to match BUILD_PROGRAM timeline
Reassign V06, V10, V13 from T1 to T2 gates in the survey.

**Pros:** Matches implementation reality (can't test ASHA on real RL until RL adapter exists)  
**Cons:** Violates survey's tier-gate promise (T1 claims ASHA works, but test deferred to T2); requires re-opening survey after M-item closure

### Option C (Recommended): Hybrid — fix protocols now, defer gate timing to Phase 0
1. **Immediate:** Fix protocol descriptions in BUILD_PROGRAM to match survey (V01-V05, V14)
2. **Week 1-2 (Phase 0):** Reconcile gate timing after pinned tasks are sized and test harness scoped
3. **Outcome:** If pinned tasks are cheap enough, match survey gates; if not, document exception in survey's validation chapter

**Pros:** Fixes clear errors (protocol specs) without prematurely committing to infeasible timeline  
**Cons:** Leaves gate timing ambiguous for 2 weeks

---

## Immediate action items

1. **Fix protocol drift** (urgent, blocks week-3 start):
   - Rewrite BUILD_PROGRAM V01-V05, V14 descriptions to match survey Table 7.1
   - Add V04 tier-0 component to week-6 gate (TPE and log+Sobol tested at T0)
   
2. **Resolve tier-numbering confusion** (clarification):
   - Survey defines four tiers: T0, T1, T2, T3
   - BUILD_PROGRAM uses three: "tier 0" (weeks 3-6), "tier 1" (weeks 7-12), "tier 2" (weeks 13-30)
   - Map explicitly: BUILD_PROGRAM "tier 2" spans survey T2 + T3
   - Proposal: Rename BUILD_PROGRAM's "tier 2" to "tier 2/3" or split week-30 gate into two campaigns

3. **Phase 0 deliverable** (week 2):
   - Size pinned tasks (cost estimates for V06, V07, V10, V13)
   - Decide gate timing: can V06/V10/V13 run at week 12, or must they defer to week 30?
   - Document decision in both survey (if exception needed) and BUILD_PROGRAM

---

## Questions for human review

1. **Authority:** Confirm survey register (sections/16-validation.tex) is the source of truth for protocols and gate assignments.
2. **Timeline flexibility:** If sizing shows V06/V10/V13 cannot run at week 12 (survey's T1 gate), is deferring them to week 30 acceptable, or must the tier-1 scope shrink?
3. **V04 split:** Survey says tier-0 searchers test at T0 gate, tier-1+ searchers at their gates. Should BUILD_PROGRAM's week-6 gate test TPE and log+Sobol (the tier-0 methods), separate from TuRBO (tier-1)?

---

## Files to update after decision

- `/home/ubuntu/workspace/hponas/BUILD_PROGRAM.md` (gate criteria, validation prep, work breakdown)
- `/home/ubuntu/workspace/hponas/hpo-survey/sections/16-validation.tex` (only if gate timing exceptions approved)
- `/home/ubuntu/workspace/hponas/hpo-survey/sections/12-roadmap.tex` (if tier-gate promises change)
