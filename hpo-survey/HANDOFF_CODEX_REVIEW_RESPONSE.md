# Handoff memo: HPO survey M-item corrections complete

**To:** Codex (or human review coordinator)  
**From:** Fable session 2026-08-27  
**Re:** All M-items resolved; survey ready for human review

---

## What was done

All eight M-items from REVIEW-REQUEST-3 have been resolved:

1. **V07 gate (M1)**: Moved from T2 to T3; roadmap note explains postponement ([16-validation.tex:93](sections/16-validation.tex#L93), [12-roadmap.tex:138](sections/12-roadmap.tex#L138))
2. **V08 exception (M2)**: Three-rep protocol documented with asymmetric stopping rule and falsifier framing ([16-validation.tex:96–143](sections/16-validation.tex#L96))
3. **Figure 7.1 float (M3)**: Table compressed to `\footnotesize` + `\arraystretch{0.95}` ([16-validation.tex:62–63](sections/16-validation.tex#L62))
4. **Log+Sobol nuance (M4)**: Expanded with transform scope, scrambling requirement, small-budget caveat ([03-model-free.tex:241–251](sections/03-model-free.tex#L241))
5. **Chebyshev condition (M5)**: Roadmap row qualified with "best-seen values proxy the ideal point" ([12-roadmap.tex:36](sections/12-roadmap.tex#L36))
6. **BG-PBT scope (M6)**: "Strongest published design" qualified to Brax locomotion, pop=8, generous budgets ([06-population.tex:367–371](sections/06-population.tex#L367))
7. **BUILD_PROGRAM staleness (M7)**: Review-request note flags drift from survey register ([REVIEW-REQUEST-3.md:12](REVIEW-REQUEST-3.md#L12))
8. **Reply consolidation (M8)**: Not actioned; reply-to-claude-3.md retained as historical record

Build verified clean: 111 pages, zero errors, zero overfull/underfull boxes, zero undefined references.

All M-items closed. The document is now ready for human review.

---

## Files ready for your review

- Survey: [main.pdf](main.pdf) (111 pages)
- Review request: [REVIEW-REQUEST-3.md](REVIEW-REQUEST-3.md)
- Audit trail: [literature-audit.md](literature-audit.md) (M-item pass dated 2026-08-27)
- Build program: [BUILD_PROGRAM.md](../BUILD_PROGRAM.md) (workspace root; note that its validation IDs and tier assignments have drifted from the survey register and should be reconciled after the survey is review-complete)

All are in `/home/ubuntu/workspace/hponas/hpo-survey/` except BUILD_PROGRAM.md which is at workspace root.
