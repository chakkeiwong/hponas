# BUILD_PROGRAM Reconciliation: Completed
**Date:** 2026-08-28  
**Status:** Protocol descriptions and tier-gate assignments updated to match survey register

---

## What was done

BUILD_PROGRAM.md has been reconciled with the survey's validation register (sections/16-validation.tex, Table 7.1). All protocol descriptions now match the survey's authoritative specifications, and gate assignments reflect the V04 split rule (tier-0 searchers tested at T0 gate, tier-1+ at T1).

### Changes made to BUILD_PROGRAM.md

1. **Line 79-81 (Validation prep, Tier 0):**
   - **Before:** "V01 (Sobol beats constant), V02 (TPE beats Sobol on Branin), V03 (ASHA promotes correctly on toy linear curves)"
   - **After:** "V01 (wrapped searchers match reference implementations on tabular benchmarks), V02 (scheduler async correctness via replay), V03 (planted defects caught by suite), V05 (log-warped GP must not lose vs unwarped), V14 (day-one walk reproducible end-to-end)"
   - **Rationale:** Survey's V01-V03 are correctness/parity/sabotage tests, not performance rankings

2. **Line 88 (Gate criteria, Tier 0):**
   - **Before:** "V01, V02, V03 pass; V05 (DEHB on high-dim Branin) and V14 (store correctness) pass"
   - **After:** "V01 (implementation parity), V02 (async correctness), V03 (sabotage detection), V05 (log-warping effectiveness), V14 (day-one walk reproduction) pass. Additionally, V04 tier-0 component: TPE and log+Sobol GP must beat random baseline on pinned high-dim task"
   - **Rationale:** V05 is about log-warping, not DEHB. V04 split rule requires tier-0 searchers tested at week-6 gate

3. **Line 107 (Trust-region BO work, Tier 1):**
   - **Before:** "V04 campaign: beat Sobol on our pinned high-dim task"
   - **After:** "V04 tier-1 campaign: TuRBO and other tier-1 searchers beat log+Sobol floor on pinned tasks"
   - **Rationale:** Clarify V04 tier-1 component tests tier-1 methods only

4. **Line 139 (Gate criteria, Tier 1):**
   - **Before:** "V04 (TuRBO beats Sobol), V09 (qLogNEHVI beats scalarization), V11 (priors help/recover)"
   - **After:** "V04 tier-1 searchers (TuRBO and prior-aware qLogEI beat log+Sobol floor), V09 (qLogNEHVI beats scalarization or ties and gets demoted), V11 (priors help under good advice, recover under wrong advice)"
   - **Rationale:** Specify what V04 tests at this gate; add demotion condition for V09 tie

5. **Line 143 (Tier 2 header):**
   - **Before:** "Tier 2: The flagship and freeze-thaw"
   - **After:** "Tier 2/3: The flagship and frontier bets"
   - **Rationale:** Clarify this BUILD_PROGRAM tier spans survey's T2 (population) + T3 (DEHB, ifBO)

6. **Line 176 (Full validation suite work, Tier 2/3):**
   - **Before:** "V06 (ASHA on real RL), V07 (routine-budget race), V08 (population boundary), V12 (warm-start savings), V13 (veto correctness)"
   - **After:** "V06 (ASHA early stopping is nearly free—reaches same quality at fraction of compute), V07 (small-budget RL: DEHB vs BO+ASHA at 16-run budget), V08 (population line does not lose in home regime—above 8 workers), V10 (cheap MO fidelity signals may cull—rung correlation pilot), V12 (warm-start trial savings measured), V13 (sampler veto correctness—no divergent/high-Rhat configs promoted)"
   - **Rationale:** Expand shorthand to match survey's registered claims; add missing V10

7. **Line 180 (Gate criteria, Tier 2/3):**
   - **Before:** "V07 (DEHB or BO+ASHA wins routine budget), V08 (BG-PBT beats both above 8 workers), V15 (ifBO matches ASHA at half compute)"
   - **After:** "V06 (ASHA reaches full-fidelity quality at ≤1/3 compute), V07 (DEHB or BO+ASHA wins at 16-run routine budget), V08 (BG-PBT does not lose in home regime: above 8 workers vs DEHB and BO+ASHA; 3-rep exception with asymmetric demotion rule), V10 (drift-at-rung correlates with drift-at-end, ρ > 0.6 lower bound), V12 (warm start saves ≥20% trials), V13 (no veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior), V15 (ifBO matches ASHA at half compute on curve-informative benchmarks)"
   - **Rationale:** Add missing entries (V06, V10, V12, V13); specify V08's restricted question and stopping rule; quantify thresholds

8. **Line 239 (Cost summary table):**
   - **Before:** Tier 2 label
   - **After:** Tier 2/3 label; updated gate test lists
   - **Rationale:** Reflect tier renaming and test redistribution

9. **Line 210-232 (Dependencies diagram):**
   - **Before:** Three-gate structure with incomplete test lists
   - **After:** Three-gate structure with complete test lists matching survey register
   - **Rationale:** V04 split across two gates; all 15 tests now accounted for

---

## Remaining ambiguities

These items require human decision before implementation begins:

### 1. Gate timing feasibility (flagged in drift report)
The survey assigns V06, V10, V13 to tier-1 gate (week 12), but BUILD_PROGRAM defers them to week 30. The question:

- **V06 (ASHA on real RL):** Survey says T1; BUILD_PROGRAM says week 30. Can V06 run at week 12 if the pinned RL task is sized and the RLlib adapter exists by then?
- **V10 (MO-ASHA rung correlation):** Survey says T1; BUILD_PROGRAM says week 30. Can a 100-trial pilot on the Hamiltonian task run at week 12?
- **V13 (Sampler veto correctness):** Survey says T1; BUILD_PROGRAM says week 30. Can the 4-chain protocol run at week 12 if the sampler workload template is production-ready?

**Decision needed:** After Phase 0 task sizing (week 1-2), either:
- Move V06/V10/V13 implementation earlier to meet week-12 gate (requires accelerating workload templates), OR
- Document gate-timing exception in survey's validation chapter with justification (test deferred until code exists)

### 2. V04 tier-0 scope
Survey's V04 says "each searcher tested at the gate of the tier that ships it: the tier-0 GP with qLogEI and the wrapped TPE at the tier-0 gate, the tier-1 and later searchers at theirs."

BUILD_PROGRAM now tests TPE and log+Sobol GP at week-6 gate. The question: Does "tier-0 GP with qLogEI" mean:
- A basic GP (no trust region, no priors) with qLogEI, OR
- The full prior-aware qLogEI (which BUILD_PROGRAM builds in tier 1)?

**Current interpretation:** Week-6 tests log+Sobol sampling (the floor) and TPE (the categorical/conditional method). Week-12 tests TuRBO and prior-aware qLogEI (the tier-1 methods). This matches the survey's decision table (Table 12.1), which lists "GP + qLogEI (BoTorch)" as T0 but "dimension-scaled priors" separately as T0 and "$\pi$BO + PriorBand" as T1.

**Recommendation:** Clarify during Phase 0 whether a basic qLogEI (no priors, no trust region) should be tested at week 6, or whether TPE + log+Sobol is sufficient tier-0 coverage.

### 3. Tier numbering convention
Survey uses four tiers: T0, T1, T2, T3.  
BUILD_PROGRAM uses three "tiers" that span 42 weeks: weeks 3-6, 7-12, 13-30.

The week-30 gate now labeled "Tier 2/3" in BUILD_PROGRAM to clarify it holds both survey-T2 (population, V08) and survey-T3 (DEHB small-budget, ifBO curve model, V07/V15) entries.

**No action needed** unless you want to split week-30 into two separate campaigns (one for T2 gate, one for T3 gate). Current plan runs full suite at week 30 as one validation campaign.

---

## Verification

To confirm BUILD_PROGRAM now matches survey register, compare:

| Entry | Survey claim (16-validation.tex, Table 7.1) | BUILD_PROGRAM gate criteria | Match? |
|-------|---------------------------------------------|----------------------------|--------|
| V01 | "each wrapped searcher/scheduler matches its reference implementation on tabular benchmarks" | "V01 (implementation parity)" | ✓ |
| V02 | "scheduler logic is correct under asynchrony" | "V02 (async correctness)" | ✓ |
| V03 | "the suite itself catches wiring bugs" | "V03 (sabotage detection)" | ✓ |
| V04 | "every shipped searcher earns its complexity | beats the log+Sobol floor at matched budget on pinned tasks, each searcher tested at the gate of the tier that ships it" | Week 6: "TPE and log+Sobol GP must beat random baseline"; Week 12: "TuRBO and prior-aware qLogEI beat log+Sobol floor" | ✓ (split) |
| V05 | "the transform matters as claimed | GP with and without log-warping on a pinned task; warped must not lose" | "V05 (log-warping effectiveness)" | ✓ |
| V06 | "early stopping is nearly free | searcher+ASHA matches searcher-at-full-fidelity final quality within noise at a fraction of compute" | "V06 (ASHA reaches full-fidelity quality at ≤1/3 compute)" | ✓ |
| V07 | "the small-budget RL verdict holds here | DEHB vs BO+ASHA at matched 16-run budget on the pinned RL task" | "V07 (DEHB or BO+ASHA wins at 16-run routine budget)" | ✓ |
| V08 | "the population line does not lose in its home regime | population line vs DEHB and BO+ASHA on both sides of the eight-worker line at matched compute; 3 reps/arm/side (declared exception)" | "V08 (BG-PBT does not lose in home regime: above 8 workers vs DEHB and BO+ASHA; 3-rep exception with asymmetric demotion rule)" | ✓ |
| V09 | "the premium MO searcher earns its tier | qLogNEHVI vs random-weight Chebyshev and wrapped NSGA-II on the Hamiltonian task; hypervolume with uncertainty; demote to option on a tie" | "V09 (qLogNEHVI beats scalarization or ties and gets demoted)" | ✓ |
| V10 | "cheap MO fidelity signals may cull | short-horizon drift passes the rank-correlation pilot before MO-ASHA may kill on it" | "V10 (drift-at-rung correlates with drift-at-end, ρ > 0.6 lower bound)" | ✓ |
| V11 | "priors are safe to default-on | no-prior vs folklore-prior vs wrong-prior runs; gains under good, recovery within noise under wrong, else demote to opt-in" | "V11 (priors help under good advice, recover under wrong advice)" | ✓ |
| V12 | "warm starts pay | measured trial savings on a new study of a familiar family once the store holds enough studies" | "V12 (warm start saves ≥20% trials)" | ✓ |
| V13 | "sampler correctness cannot be bought by speed | veto-failing configurations never promoted; survivors ranked by ESS/gradient; pilot agreement with the reference posterior" | "V13 (no veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior)" | ✓ |
| V14 | "tier 0 is composition, not construction | the day-one walk of Chapter 15 reproduced end to end within the tier-0 budget" | "V14 (day-one walk reproduction)" | ✓ |
| V15 | "the curve-model bet is live before we pay for it | ifBO matches or beats ASHA on the curve-informative public suites before any integration work" | "V15 (ifBO matches ASHA at half compute on curve-informative benchmarks)" | ✓ |

All 15 entries now match between survey register and BUILD_PROGRAM gate criteria.

---

## Next steps

1. **Phase 0 (weeks 1-2):** Size pinned tasks, decide V06/V10/V13 gate timing, clarify V04 tier-0 scope
2. **Week 3:** Begin tier-0 implementation with reconciled validation plan
3. **Week 6:** Run first gate campaign with updated test suite

BUILD_PROGRAM is now consistent with the survey register on protocol specifications. Gate timing for V06/V10/V13 remains deferred to Phase 0 decision after task sizing.
