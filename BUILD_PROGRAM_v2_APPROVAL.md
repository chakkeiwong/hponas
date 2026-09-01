# BUILD_PROGRAM v2.0 Approval Record

**Date:** 2026-09-01  
**Approver:** Project PI  
**Program version:** 2.0  
**Generator commit:** 4f51669

---

## Purpose

This document records approval of `BUILD_PROGRAM_v2.md` as the single authoritative build plan, superseding `BUILD_PROGRAM.md` (v1, rejected for effort underestimation) and `WORK_BREAKDOWN_TIMELINE_DRAFT.md` (corrected effort, but marked DRAFT).

---

## What changed from v1 (rejected plan)

1. **Effort corrections** — Tier 0: 30d → 65d; Tier 1: 30d → 70d; Tier 2: 42d → 70d. The v1 figures were reviewed RED for underestimating integration, test authoring, and RLlib adapter complexity.

2. **Gate assignment corrections** — V06, V10, V13 moved from Tier 2 gate (week 30) to Tier 1 gate (week 12) per survey assignments. V12 assigned to new Distributed Beta gate (after enough campaigns run to validate warm starts).

3. **Validation register completeness** — All 15 entries now render claim + pass rule + criteria with survey/program gate cross-reference. Catches drift between survey table and program gates.

4. **Traceability** — Every decision links back to `hpo-survey-decisions.json` with tier/validation/section. Every validation entry links to survey table and reconciliation doc.

---

## Inputs verified

- `hpo-survey-decisions.json` — 63 decisions, 48 in scope (T0/T1/T2/T3/workload/adopt)
- `WORK_BREAKDOWN_TIMELINE_DRAFT.md` — corrected effort and phasing
- `BUILD_PROGRAM_RECONCILIATION_COMPLETE.md` — validation register with survey/program criteria reconciled
- Survey chapter 16 (validation table) — 15 entries with claims and pass rules

---

## Generator quality checks passed

- [x] Effort figures match corrected timeline (not rejected v1)
- [x] V06/V10/V13 at Tier 1 gate (not week 30)
- [x] V12 at Distributed Beta gate (not dropped)
- [x] Gate coverage: all 15 validation entries assigned
- [x] Validation register: claim + pass rule + criteria complete for all entries
- [x] No LaTeX artifacts leaked (`\cite`, `\S`, `\ref`)
- [x] No v1 annotations leaked ("was 30 in rejected plan")
- [x] Regeneration is deterministic (`--verify` mode passes)

---

## Open items at approval time

1. **Statistical reviewer verification (R0 carryover)** — Sequenced as non-blocking to overlap R1 weeks 1-2; that window closed. **Decision: formally waived** — PI (professor in computational statistics, global ML head at major bank) is the statistical authority. External review is not cost-effective.

2. **Validation protocol sign-off** — Protocols repaired per Codex review findings F1-F3 and items 1-8. D4 and D5 resolved. **Awaiting:** Codex re-review of `validation/protocols.json`, pilot sizing report, PI certification.

3. **Progress.md generation** — Currently hand-maintained and has drifted twice. `tools/update_progress.py` should generate it from git tags + gate reports + test output per `GOVERNANCE_IMPLEMENTATION.md`. **Status:** deferred until Tier 0 starts (not blocking program approval).

---

## Release consequences

### Approved as authoritative

`BUILD_PROGRAM_v2.md` becomes the single source of truth for:
- Effort and timeline (replaces both v1 and corrected draft)
- Gate criteria and validation register (replaces reconciliation doc's table)
- Decision traceability (canonical links to survey)

### Archived as superseded

- `BUILD_PROGRAM.md` → `archive/BUILD_PROGRAM_v1_REJECTED.md` (RED review: effort too low)
- `WORK_BREAKDOWN_TIMELINE_DRAFT.md` → archive (corrections now in v2)
- `BUILD_PROGRAM_RECONCILIATION_COMPLETE.md` → archive (register now in v2)

### Git tag

Program approval is recorded as annotated tag `program-v2.0` at commit `4f51669`.

---

## Amendments (future)

Minor corrections that do not change tier boundaries, gate timing, or validation pass bars are v2.1, v2.2, etc. with amendment records. Changes that move gates or alter validation criteria require a new major version (v3.0) with full review.

Amendment record structure:
```
## Amendment v2.1 (YYYY-MM-DD)
**Change:** [one-line summary]
**Rationale:** [why]
**Impact:** [affected sections, gates, or entries]
**Approver:** [PI or delegate]
```

---

## Approval

I certify that `BUILD_PROGRAM_v2.md` (generated from structured inputs at commit `4f51669`) is reviewed, complete, and approved as the authoritative build plan for hponas.

**Signed:** [awaiting PI signature]  
**Date:** [pending]

---

## Next steps after approval

1. PI signs this document
2. Create git tag `program-v2.0` at `4f51669`
3. Archive superseded documents to `archive/`
4. Update `docs/progress.md` to reference v2.0 as current
5. Begin Tier 0 work per BUILD_PROGRAM_v2.md Phase 0
