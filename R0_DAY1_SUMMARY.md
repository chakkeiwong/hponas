# R0 Progress Summary
**Phase:** Specification Correction
**Day:** 2 of 14 (2-week phase)
**Date:** 2026-08-28
**Overall status:** Ahead of plan — both Day-1 blockers cleared, survey corrections applied and building clean

---

## Decisions taken (were blocking, now resolved)

### Decision 1: NAS scope — **Option A approved**
**Approved by:** Project sponsor, 2026-08-28
**Scope:** Moderate architecture coordinates — width and depth as ordinal axes, a small number
of structural flags as categorical axes, parameter count and measured FLOPs as objectives,
architecture mutation through the ordinary explore step.
**Excluded:** topology/cell search, one-shot or weight-sharing supernets, zero-cost proxy
subsystem, grammar-based or hierarchical spaces, differentiable search.
**Effort:** +16 engineer-days (see work breakdown).
**Record:** [NAS_SCOPE_DECISION.md](NAS_SCOPE_DECISION.md)

### Decision 2: Statistical review — **reordered, not a blocker**
The 8 validation items were under-specification, not open statistical questions, so waiting on a
reviewer to derive them was a self-imposed dependency. They are now fully specified in the survey.
The reviewer role changes from *author of the specification* to **end-of-R0 verification gate**:
a reviewer validates finished, written protocols rather than deriving them from a draft.
This removes the R0 critical path's only external dependency.

---

## Completed (Day 1–2)

### ✅ Task 1.1: NAS scope analysis and decision
Analysis complete, Option A approved, scope boundary now written into the survey itself
(see Task 1.6/1.7 below).

### ✅ Task 1.3 + 2.2: Validation corrections **applied to LaTeX**
All 8 corrections are in [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex),
written as prose in the document's register rather than pasted as bullet lists:

| # | Correction | Location |
|---|-----------|----------|
| 1 | Non-inferiority margins replace CI-overlap for V06/V11 (δ=5%, δ=10%); "inconclusive" named as a distinct outcome | 16-validation.tex:184 |
| 2 | Repetition count derived from pilot variance at 80% power; ten-repetition floor demoted to planning heuristic; "inconclusive at budgeted precision" is a verdict with a consequence | 16-validation.tex:127 |
| 3 | New subsection: sampling levels, pseudoreplication, paired designs with fallback, hierarchical bootstrap | 16-validation.tex:240 |
| 4 | New subsection: development vs held-out acceptance tasks, chosen by a non-implementer, versioned rotation | 16-validation.tex:274 |
| 5 | New subsection: one primary endpoint per entry at uncorrected α=0.05; secondary ranking claims under Holm–Bonferroni; descriptive comparisons exempt | 16-validation.tex:300 |
| 6 | V06 cost measured in actual accelerator-seconds and wall-clock incl. startup, checkpointing, queue wait; full-run equivalents demoted to normalized secondary measure | 16-validation.tex:200 |
| 7 | New subsection: immutable signed manifests, `validation/artifacts/` explicitly not gitignored | 16-validation.tex:329 |
| 8 | V08 release semantics: demote / hold / pass; Tier 2 completion requires only "not demoted, not blocked" | 16-validation.tex:409 |

Citations `holm1979simple` and `simmons2011false` added to
[hpo-survey/refs.bib](hpo-survey/refs.bib).

### ✅ Task 1.4: V08 semantics clarified in survey
Folded into correction 8 above — three named states with their release consequences, and an
explicit statement that a three-repetition run is a tripwire rather than promotion evidence.

### ✅ Task 1.5: Knob-kind ambiguity resolved
**Resolution:** three *typed* kinds (continuous, ordinal, categorical); conditionality is
structural, not a kind, and lives in the schema's `condition` field. Integer-valued knobs **are**
ordinals — the ordinal kind is defined as an integer with a natural order, so there is no
separate integer kind.
- [15-contracts.tex:59](hpo-survey/sections/15-contracts.tex#L59) now states three values and explains why that is not a contradiction of Chapter 2's four kinds.
- [14-product.tex:49](hpo-survey/sections/14-product.tex#L49) changed "four knob kinds" → "three knob kinds".
- Chapter 2's four-kind tour is unchanged; it was never wrong, only differently sliced.

### ✅ Task 1.6: Architecture scope written into the survey
[09-workloads.tex](hpo-survey/sections/09-workloads.tex), after the "in moderation" conclusion:
the inside/outside boundary stated as a scope rather than a mood, plus the weight-inheritance
consequence that makes distillation part of the population line's price rather than free.

### ✅ Task 1.7: Architecture factory contract added
New section in [15-contracts.tex](hpo-survey/sections/15-contracts.tex) (`sec:archfactory`) with
four verbs — `build`, `measure`, `compatible`, `transfer` — plus one added searcher capability
flag. The contract is what makes the excluded methods excluded by construction: a coordinates→model
map has no place to put a supernet. `compatible` is conformance-tested in both directions because a
wrong answer produces silent garbage.

### ✅ Task 2.1: Traceability matrix extraction
**Correction to the Day 1 report:** this was listed as "IN PROGRESS — agent running." It had in
fact completed. [hpo-survey-decisions.json](hpo-survey-decisions.json) holds 63 extracted decisions
with source file, line, chapter, verdict, tier, cost estimate, and rationale.
Remaining: most `validation_entries` arrays are empty, so the decision→validation mapping and the
gap analysis still need filling.

### ✅ Task 2.3: Work breakdown and timeline drafted
[WORK_BREAKDOWN_TIMELINE_DRAFT.md](WORK_BREAKDOWN_TIMELINE_DRAFT.md) — 39–48 weeks to internal
beta. Needs the +16 engineer-days from the Option A approval folded in.

### ✅ Survey builds clean
114 pages, 0 errors, 0 undefined references, bibliography resolved (pdflatex + bibtex ×3;
no latexmk on this machine).

---

## Remaining in R0

| Task | Status | Notes |
|------|--------|-------|
| Task 2.1b: decision → impl → test → validation mapping | Open | 63 decisions extracted; `validation_entries` mostly empty |
| Task 2.4: regenerate `product_register.json` | Open | Existing file is the 2026-08-26 generation; needs architecture-factory rows and the corrected validation semantics |
| Work breakdown: fold in +16 engineer-days | Open | Option A now approved, so this is no longer conditional |
| R1 spike: add architecture factory prototype | Open | Per the Option A next-steps list |
| Statistical review as verification gate | Open | End of R0, on finished text |
| BUILD_PROGRAM_v2 | Open | After matrix and register |
| R0 completion report | Open | Last item |

---

## Environment note

`/home/ubuntu/workspace/hponas` is **not a git repository**. Two things depend on that and
currently have no substrate:
1. The correction checklist's "git commit" step.
2. The manifest discipline just written into the survey, which requires analysis scripts
   "committed to version control before results exist" and artifacts under a
   deliberately-not-gitignored path.

Initialising a repository here is a prerequisite for the preregistration discipline being real
rather than aspirational. Flagging rather than doing, since it affects how the whole tree is
tracked.

---

## Summary metrics

**Completed:** 8/9 original tasks, plus 2 added by the Option A approval (1.6, 1.7)
**Open:** matrix mapping, register regeneration, work-breakdown update, R1 spike update
**Blocked:** none
**Critical path:** traceability matrix mapping → product_register regeneration → BUILD_PROGRAM_v2

**Risk status:** the two Day-1 risks (reviewer unavailable, NAS decision delayed) are both closed.
The remaining risk is ordinary execution risk on the matrix and register work.

---

## Exit criteria for R0

- [x] NAS scope decided and documented
- [x] Statistical review sequenced (verification gate, not a specification dependency)
- [x] LaTeX validation corrections applied and building clean
- [x] V08 semantics clarified in survey
- [x] Knob-kind ambiguity resolved
- [x] Architecture scope and contract written into the survey
- [ ] Traceability matrix complete (decision → impl → test → validation)
- [ ] Timeline reconciled with the +16 engineer-days and contingency
- [ ] `product_register_v2.json` generated and validated
- [ ] BUILD_PROGRAM scope deviations documented
- [ ] Statistical reviewer verification pass on the finished chapter

---

## Communication to stakeholders

**For project sponsor:**
> "Option A approved and already in the survey: the architecture boundary is written into
> Chapter 9 with an explicit exclusion list, and Chapter 15 has the four-verb architecture factory
> contract behind it. +16 engineer-days confirmed. The statistical-reviewer blocker is gone —
> the protocols are now fully specified in the document, so a reviewer verifies finished text
> instead of writing it. No open decisions."

**For project lead:**
> "R0 has no blockers left. All 8 statistical corrections are applied to the validation chapter
> and the survey builds clean at 114 pages. Knob-kind contradiction resolved. Remaining R0 work is
> the traceability matrix mapping, product_register regeneration, and folding +16 engineer-days
> into the timeline. One flag: the workspace is not under version control, which the new
> preregistration discipline assumes."

**For engineering team:**
> "Unchanged: do not begin Tier 0 under the rejected BUILD_PROGRAM. Two things now settled that
> affect you — architecture search is width/depth/flags only, with a `build`/`measure`/
> `compatible`/`transfer` factory contract owned by the workload, not the tuner; and validation
> gates now have three outcomes, not two, since 'inconclusive at budgeted precision' is a real
> verdict. Distillation-based weight transfer is tier 2; before that, an incompatible architecture
> change means restart."

---

**End of Day 2 summary**
