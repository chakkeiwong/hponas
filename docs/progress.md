# Build Progress Tracker

**Last updated:** 2026-08-31  
**Current phase:** R1 complete (gate PASS) → Tier 0 pending program v2  
**Next milestone:** Generate and approve `BUILD_PROGRAM_v2.md`, then start Tier 0

> Maintenance note: this file is currently hand-maintained and has drifted twice.
> It should be generated from ground truth (git tags, gate reports, test output) by
> `tools/update_progress.py` — see [../GOVERNANCE_IMPLEMENTATION.md](../GOVERNANCE_IMPLEMENTATION.md).
> Until that script exists, verify claims here against `tools/gate_check.py` output.

---

## Phase R0: Specification correction

**Status:** ✅ Complete (2026-08-28)  
**Effort:** 2 days actual (14 planned)  
**Report:** [../R0_COMPLETION_REPORT.md](../R0_COMPLETION_REPORT.md)

- [x] All 8 statistical corrections applied; survey builds clean at 118 pages (114 at R0 close, before the protocol amendments of 2026-08-31)
- [x] NAS scope decided (Option A: moderate architecture coordinates, +16 eng-days)
- [x] Knob-kind ambiguity resolved (three typed kinds; conditionality is structural)
- [x] Architecture factory contract written into survey Ch 15 (`sec:archfactory`)
- [x] Traceability matrix: 63 decisions with validation mappings
- [x] `product_register.json` regenerated (48 entries)
- [x] Git repository initialized (R0 report's outstanding environment note now closed)
- [ ] **Statistical reviewer verification** — still open, see Risk flags below

---

## Phase R1: Executable architecture spike

**Status:** ✅ Complete — gate PASS (2026-08-31)  
**Gate report:** [../gate_reports/r1_gate_2026-08-31.md](../gate_reports/r1_gate_2026-08-31.md)  
**Interface review:** [SPIKE_REVIEW.md](SPIKE_REVIEW.md)  
**Charter:** [../R1_SPIKE_CHARTER.md](../R1_SPIKE_CHARTER.md)

### Deliverables
- [x] `SearchSpace` (continuous/ordinal/categorical, transforms, conditions declared)
- [x] `SobolSearcher` (scipy Sobol + log-scale, batch propose)
- [x] `ASHAScheduler` (rung promotion, async event handling, budget tracking)
- [x] `LocalExecutor` (in-process; subprocess isolation deferred to Tier 0)
- [x] `RayExecutor` (stub — real Ray Tune scoped to Tier 0 per charter)
- [x] `Store` (SQLite + WAL, crash recovery, lineage queries)
- [x] Architecture factory stubs (`build`/`measure`/`compatible`/`transfer`)
- [x] `examples/spike_branin.py` — 16 trials, determinism verified
- [x] `examples/spike_crash_recovery.py` — crash at 8, resume to 16
- [x] `docs/SPIKE_REVIEW.md` — interfaces approved for Tier 0
- [x] Test suite: 56 tests, 93% coverage

### Findings resolved during close-out
1. **Sobol state loss on resume (correctness bug).** `SobolSearcher` held QMC state in
   `self._sobol` with a no-op `observe()`, so a rebuilt searcher restarted the sequence:
   16 trials covered only 8 distinct points, each evaluated twice. The example's own
   assertion tested `trial_id` uniqueness, which is trivially true and always passed.
   **Fixed:** added `state_dict()`/`load_state_dict()` to the `Searcher` protocol,
   implemented for Sobol via `fast_forward()`, persisted per-trial in the example, and
   strengthened the assertion to compare configs. Resumed sequence now equals the
   uninterrupted run point-for-point. 4 new contract tests.
2. **RayExecutor is a stub**, so the local-vs-Ray conformance check was local-vs-local.
   **Resolved as scope:** real Ray Tune is Tier 0 work (~4d) per the charter; recorded as
   a known limitation in SPIKE_REVIEW.md rather than an unmet criterion.

**Interface change carried into Tier 0:** every searcher (GP+qLogEI, TPE, TuRBO) must
implement the state serialization contract. Counter-based fast-forward will not
generalize to surrogate-carrying searchers — they need real state capture.

---

## Tier 0: Wrapping campaign

**Status:** ⛔ Blocked — awaiting `BUILD_PROGRAM_v2.md` approval  
**Gate:** V01–V03, V05, V14, plus V04 tier-0 component

Not started. Scope and effort figures pending program v2 generation, because
`BUILD_PROGRAM.md` (v1) carries effort numbers that were reviewed RED, while the
corrected figures live in `WORK_BREAKDOWN_TIMELINE_DRAFT.md` (still DRAFT).

---

## Tier 1: Method differentiators

**Status:** ⛔ Blocked on Tier 0 gate  
**Gate:** V04 (tier-1 searchers), V09, V11

---

## Tier 2/3: Flagship and frontier bets

**Status:** ⛔ Blocked on Tier 1 gate  
**Gate:** V06, V08, V10, V12, V13, V15

---

## Risk flags (live)

| Opened | Risk | Signal | Status |
|--------|------|--------|--------|
| 2026-08-28 | Statistical reviewer verification not done | R0 sequenced it as non-blocking, overlapping R1 wks 1–2; that window has closed | **OPEN** — decide before Tier 0: chase or formally waive in v2 approval |
| 2026-08-31 | Competing planning documents | v1 program, corrected timeline draft, and reconciliation memo all claim authority | **OPEN** — resolved by generating v2 |
| 2026-08-31 | Gate criteria that cannot fail | R1's crash-recovery check asserted on trial_id, passing over a real duplicate-config bug | **MITIGATED** — `tools/gate_check.py` now verifies configs; apply the lesson when authoring Tier 0 criteria |
| 2026-08-31 | Session stalls mistaken for repo damage | Gateway 502/529 retry storms killed 4 sessions; one left a merge half-done | **MITIGATED** — recovery procedure documented; git state is ground truth |

---

## Gate history

| Gate | Date | Criteria | Result | Report |
|------|------|----------|--------|--------|
| R0 | 2026-08-28 | 9 exit criteria (1 deferred) | PASS | [R0_COMPLETION_REPORT.md](../R0_COMPLETION_REPORT.md) |
| R1 | 2026-08-31 | 8 mechanical criteria | **PASS** | [r1_gate_2026-08-31.md](../gate_reports/r1_gate_2026-08-31.md) |
| Tier 0 (week 6) | TBD | V01–V03, V05, V14, V04-T0 | Pending | — |
| Tier 1 (week 12) | TBD | V04-T1, V09, V11 | Pending | — |
| Tier 2/3 (week 30) | TBD | V01–V15 (full) | Pending | — |

---

## Decisions logged

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-26 | Survey released for review | Clean build, decision boxes falsifiable |
| 2026-08-26 | Build program v1 written | Three tiers, 42 eng-weeks; later reviewed RED on effort |
| 2026-08-28 | NAS scope: Option A | Moderate architecture coordinates, +16 eng-days |
| 2026-08-28 | Statistical reviewer = verification gate, not author | Removed critical-path dependency |
| 2026-08-31 | Merge two disjoint git roots | Repo had two root commits; `--allow-unrelated-histories` was correct, merged as `88e2fea` |
| 2026-08-31 | Adopt mechanical gate checks | Drift went undetected three times because plan facts lived in unverifiable prose |
| 2026-08-31 | Add searcher state serialization to contract | Crash recovery is untrustworthy without it; found by strengthening the R1 gate |
| 2026-08-31 | Ray executor deferred to Tier 0 | Charter already scoped it there; recorded as known limitation, not unmet criterion |

_Add new decisions here as the build progresses._
