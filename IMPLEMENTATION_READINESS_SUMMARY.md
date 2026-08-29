# HPO Survey Implementation Readiness Assessment
**Date:** 2026-08-28  
**Status:** BUILD_PROGRAM reconciled; three gaps remain before implementation-ready

---

## Current state

The HPO survey is **review-ready** for human approval:
- All 8 M-items from REVIEW-REQUEST-3 have been resolved
- Document builds clean at 111 pages with zero errors
- Validation register (sections/16-validation.tex) specifies all 15 protocols with concrete pass rules
- Handoff documentation complete (HANDOFF_CODEX_REVIEW_RESPONSE.md)

BUILD_PROGRAM.md has been **reconciled** with the survey register:
- All protocol descriptions updated to match survey specifications
- Tier-gate assignments corrected (V04 split, all 15 tests accounted for)
- Drift analysis documented in BUILD_PROGRAM_DRIFT_REPORT.md
- Reconciliation completion notes in BUILD_PROGRAM_RECONCILIATION_COMPLETE.md

---

## Three gaps blocking implementation-ready status

### 1. Gate timing ambiguity (requires Phase 0 decision)

Four validation entries assigned to different gates in survey vs BUILD_PROGRAM:

| Entry | Survey gate | BUILD_PROGRAM gate | Issue |
|-------|-------------|-------------------|-------|
| V06 | T1 (week 12) | Week 30 | Can ASHA test on real RL run at week 12, or must it wait for full tier-2 RL infrastructure? |
| V10 | T1 (week 12) | Week 30 | Can 100-trial Hamiltonian pilot run at week 12, or does it need week-30 full suite? |
| V13 | T1 (week 12) | Week 30 | Can sampler veto test run at week 12, or must workload template be production-ready first? |

**Decision point:** Phase 0 (weeks 1-2) must size pinned tasks and determine:
- If V06/V10/V13 can feasibly run at week 12, accelerate their implementation
- If not, document gate-timing exception in survey's validation chapter with justification

**Impact if unresolved:** Tier-1 gate (week 12) claims capabilities (ASHA correctness, MO-ASHA rung correlation, sampler veto correctness) that won't be tested until week 30

### 2. Test harness gap (needs verification)

Survey protocols reference specific infrastructure that hasn't been verified to exist:

**Benchmarks and datasets:**
- YAHPO-Gym, HPOBench, ARLBench (layer-1 tabular benchmarks for V01)
- Recorded learning curves for Syne Tune-style replay (V02)
- PriorBand multi-fidelity benchmark suite (V01/V02)
- bank-marketing dataset (referenced in product chapter's day-one walk, V14)
- Brax locomotion environments (V07, V08)
- Hamiltonian network task with 2 objectives: prediction error + energy drift (V09, V10)
- Reference posterior for sampler pilot (V13, must be computed once at great length)

**Dependency versions and APIs:**
- BoTorch version and qLogEI/qLogNEHVI API stability
- Optuna version and OptunaSearch adapter compatibility with Ray Tune
- DEHB availability (vendor or wrap? ConfigSpace dependency?)
- Ray Tune checkpoint surgery for population methods (V08)
- RLlib integration points (training_iteration fidelity, resume from checkpoint)

**Audit needed:**
1. Does `/home/ubuntu/workspace/hponas` contain stubs, datasets, or wiring for any of the above?
2. Are benchmark dependencies installable and API-stable as of 2026-08?
3. Are pinned task definitions (PPO/Brax, Hamiltonian 2-obj, sampler veto) specified anywhere beyond the survey text?

**Decision:** Run Phase 0 environment audit (week 1) to identify missing pieces before committing to timeline

### 3. Human review of M-item fixes (quality gate)

BUILD_PROGRAM reconciliation assumes the survey register is correct, but the survey hasn't had human review yet. Specific risks:

**V08 three-rep exception:** Changed from "boundary sits where we say" (M2 overclaim) to "does not lose in its home regime" with asymmetric stopping rule. The protocol is now a **falsifier** rather than a confirmation test. Human should verify this framing is acceptable before implementation builds to it.

**V10 bootstrap protocol expansion:** Changed from unspecified to 100 trials with bootstrap 95% CI on Spearman ρ, lower bound must clear 0.6. The threshold (0.6) is "a judgment, not a result from the literature" per survey text. Human should confirm this is defensible.

**V13 MCMC protocol details:** Expanded to 4 chains, 2000 warmup + 2000 retained per chain, split-R̂ ≤ 1.01, ESS > 400. These match Vehtari et al. 2021 recommendations, but human should verify the thresholds fit the sampler workload before a campaign is run.

**Recommendation:** Human reviews sections/16-validation.tex (validation chapter) and approves protocols before Phase 0 begins. If changes needed, update BUILD_PROGRAM to match.

---

## Path to implementation-ready

| Step | Owner | Deadline | Deliverable |
|------|-------|----------|-------------|
| 1. Human review survey validation chapter | Human reviewer | Before Phase 0 | Approve protocols or flag changes needed |
| 2. Phase 0: Interface freeze + task sizing | Engineer | Week 2 | Pinned task cost estimates, V06/V10/V13 gate decision, environment audit |
| 3. Reconcile any human-review changes | Engineer | Week 2 | Update BUILD_PROGRAM if survey protocols change |
| 4. Verify test harness coverage | Engineer | Week 2 | Audit benchmark availability, dataset access, dependency versions |
| 5. Write Phase 0 completion memo | Engineer | End week 2 | Gate timing decision documented, missing infrastructure flagged |

**Then:** Week 3 begins tier-0 implementation with validated plan

---

## Summary

**Review-ready:** Yes (survey document)  
**Implementation-ready:** Not yet

**Blocking items:**
1. Gate timing decision (V06/V10/V13: week 12 or week 30?)
2. Test harness verification (do benchmarks/datasets/dependencies exist?)
3. Human approval of validation protocols (especially V08/V10/V13 expansions)

**Next action:** Human reviews [sections/16-validation.tex](hpo-survey/sections/16-validation.tex) and [REVIEW-REQUEST-3.md](hpo-survey/REVIEW-REQUEST-3.md), then approves survey for publication or flags further changes. After approval, Phase 0 work begins with task sizing and environment audit.

---

## Files ready for human review

- **Survey PDF:** [hpo-survey/main.pdf](hpo-survey/main.pdf) (111 pages, builds clean)
- **Review request:** [hpo-survey/REVIEW-REQUEST-3.md](hpo-survey/REVIEW-REQUEST-3.md) (M-items context)
- **Validation chapter:** [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex) (protocols, gates, thresholds)
- **Build program:** [BUILD_PROGRAM.md](BUILD_PROGRAM.md) (reconciled timeline and gate criteria)
- **Drift analysis:** [BUILD_PROGRAM_DRIFT_REPORT.md](BUILD_PROGRAM_DRIFT_REPORT.md) (what changed and why)
- **Reconciliation notes:** [BUILD_PROGRAM_RECONCILIATION_COMPLETE.md](BUILD_PROGRAM_RECONCILIATION_COMPLETE.md) (verification table)

All files in `/home/ubuntu/workspace/hponas/` except survey materials which are in `hpo-survey/` subdirectory.
