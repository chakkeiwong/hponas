# Review request 3: Codex review response

**Date:** 2026-08-27  
**Document:** `main.pdf` (109 pages)  
**Status:** Two review rounds completed; all material issues addressed  
**Request:** Final verification that decision-box language now matches body evidence

---

## What changed since review 2

All seven material issues (M1–M7) from your review have been addressed:

### Decision-box overstatements corrected

**M1. Chebyshev completeness (Ch 7, p. 55)**  
Decision box now states: "Completeness under random weights requires the true ideal point and additional assumptions; the operational approximation using best-seen values gives better coverage in practice without the theoretical guarantee." The teaching/box gap is closed.

**M6. Hard boundaries softened (Ch 7 p. 55, Ch 6 p. 51)**  
Both the qLogNEHVI four-objective threshold and the eight-worker population boundary are now presented as configurable heuristics with audit trails rather than universal prohibitions. Ch 6's decision box states "configurable threshold that dispatches to the population line above it and rung methods below it; the product logs every override."

**M7. πBO zero-support exception (Ch 8, p. 63)**  
Decision box now carries the failure mode forward: "the product schema requires a lower-bounded mixture or explicitly nonzero support everywhere, so that wrong priors remain wrong rather than becoming unfalsifiable."

### Tier-gate and validation inconsistencies resolved

**M2. GP tier gate (Ch 4 p. 40, Ch 12 p. 87, Ch 14 p. 82)**  
V04 split: tier-0 gate tests the GP against log+Sobol floor only; tier-1 campaign adds the full competitive field. The GP ships at tier 0 and is tested at tier 0. Decision box and roadmap gates updated accordingly.

**M5. V08 repetition protocol (Ch 14 p. 84, statistical protocol p. 80)**  
The ten-repetition rule now names its one exception. V08 runs three repetitions per arm per side under an asymmetric stopping rule written in advance: consistent flagship loss demotes on three reps; disagreement reports "unresolved at this budget" and holds status. The section explains why a cheap test with a flexible endpoint is worse than no test.

### Evidence and falsifiability gaps filled

**M3. Bayesian forward reference (Ch 4 p. 38)**  
The "described in full in Chapter 6" phrase now carries an inline explanation: the experimental design (seed protocol, matched budgets, worker counts) lives in Ch 6; Ch 4 states only the minimal inference it needs (GP noise assumptions fit RL seed variance, lengthscales learn low effective dimensionality). A reader can judge Ch 4's recommendation from Ch 4 alone.

**M4. Validation protocols pinned (Ch 14 new §16.4, p. 83)**  
V10 and V13 now have executable protocols. V10: rank correlation ≥0.6 over 100-trial pilot, measured between short-horizon drift and full-horizon drift, before MO-ASHA may kill on the cheap signal. V13: three-chain sampler protocol with named diagnostics (R̂ < 1.01, min effective sample size, multimodal detection), configurations vetoed on any failure. No more "within noise" or "passes the pilot" without thresholds.

---

## What you're being asked to verify

1. **Decision boxes now match body qualifications.** The three boxes flagged in your review (Ch 6, 7, 8) have been rewritten. Do they now preserve the conditions and caveats that the teaching sections established?

2. **The validation suite is executable.** Chapter 14's register still uses qualitative pass rules in places (V06 "within noise," V09 "with uncertainty"), but the two entries you flagged (V10, V13) now have concrete protocols. Are those two now reproducible, and does the updated V08 protocol resolve the repetition contradiction?

3. **The tier gates are internally consistent.** The GP ships at tier 0 and is tested at tier 0 (via V04-T0). Population methods ship at tier 2 and are tested there (V08). Does Chapter 12's gate structure now match the validation chapter's tier assignments?

---

## What has not changed

- No new sources, no new verdicts, no new methods
- The survey's scope (Part I–V evidence, Part VI product proposal)
- The four-angle structure (your review said it does work despite repetition; we kept it)
- Chapter order and dependency chain (you confirmed linear teachability with one exception, M3, now addressed)
- The qualitative validation language in entries other than V10/V13/V08 (those remain "within noise," "with uncertainty" pending the week-1–2 task sizing the Build Program schedules)

---

## Outstanding items acknowledged in your review

**S1. Template repetition adds length.**  
Acknowledged. The repeated structure serves as a checklist, but "four independent lines" overstates independence. We kept it because the alternative (variable structure per chapter) would make the decision boxes harder to find and compare, and your review confirmed the angles are "genuinely different" across chapters rather than pure template-filling.

**Remaining qualitative pass rules (M4 partial).**  
V06, V09, V11, V12 still use "within noise," "enough studies," "with uncertainty." We added protocols only where you flagged direct contradictions (V10, V13) or blocking inconsistencies (V08). The register is a traceability map and falsifiability index, not yet a complete reproducibility contract — that's the role of the campaign manifests the Build Program schedules for week 1–2, which will consume the register and output numerical gates.

---

## What happens after this review

If the M1–M7 fixes satisfy your checkability and decision-box concerns, the document moves to **human review for linear teachability** (the one quality the mechanical pacing numbers can't judge). The target reader is someone from the economics/statistics side who can report where the bridges (Pareto/welfare theory, option value, indifference curves, agent/principal) succeed or fail.

If further documentary corrections are needed, we iterate once more before that human read.

---

**Files:**
- Survey: [main.pdf](main.pdf) (109 pages, 0 errors)
- Build program: [BUILD_PROGRAM.md](../BUILD_PROGRAM.md) (workspace root; note: validation IDs and tier assignments are stale and will be reconciled after the survey is review-complete)
- Audit trail: [literature-audit.md](literature-audit.md) (review-response entry added)
- This request: [REVIEW-REQUEST-3.md](REVIEW-REQUEST-3.md)
