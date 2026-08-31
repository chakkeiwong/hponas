# Governance Implementation Summary

**Date:** 2026-08-31  
**Purpose:** Actionable next steps to establish governance before Tier 0 starts

---

## Current state (as of 2026-08-31)

R0 and R1 implementation are substantively done:
- Survey: 114 pages, building clean
- R1 code: examples run, 52 tests pass, 93% coverage
- Work merged and pushed to `origin/main` at commit `88e2fea`

**However:**
- R1 exit gate has **2 blockers** (Sobol state bug, missing SPIKE_REVIEW.md) and 1 warning (stale README)
- Planning documents overlap and contradict (BUILD_PROGRAM.md v1 vs WORK_BREAKDOWN_TIMELINE_DRAFT.md)
- Progress tracking is manual and stale (`docs/progress.md` says "Phase 0 not started")

**Governance gap:** No mechanical checks prevent shipping incomplete phases or drifting from spec.

---

## Immediate actions (before Tier 0 starts)

### 1. Close R1 properly (3-5 days)

#### A. Fix the Sobol state serialization bug (1-2 days)

**Problem:** `SobolSearcher` keeps QMC state in `self._sobol`, but `observe()` is a no-op. On crash recovery, searcher is rebuilt with the same seed → sequence restarts → duplicate configs.

**Evidence:**
```
trials in store: 16
unique configs : 8
trial_8 repeats trial_0, trial_9 repeats trial_1, ...
```

**Fix:**
1. Add state serialization to `Searcher` protocol:
   ```python
   class Searcher(Protocol):
       def state_dict(self) -> dict[str, Any]: ...
       def load_state_dict(self, state: dict[str, Any]) -> None: ...
   ```

2. Implement for `SobolSearcher`:
   ```python
   def state_dict(self) -> dict[str, Any]:
       return {
           "seed": self.seed,
           "n_proposed": self._n_proposed,
       }
   
   def load_state_dict(self, state: dict[str, Any]) -> None:
       self.seed = state["seed"]
       self._n_proposed = state["n_proposed"]
       # Rebuild Sobol with correct state
       self._sobol = qmc.Sobol(d=self._dim, scramble=True, seed=self.seed)
       # Fast-forward to skip already-proposed points
       if self._n_proposed > 0:
           _ = self._sobol.random(self._n_proposed)
   ```

3. Update `examples/spike_crash_recovery.py` to save/load searcher state alongside store

4. Re-run: `python3 tools/gate_check.py --phase r1 --mode dry-run` until uniqueness check passes

**Acceptance:** Gate check reports "16 unique configs in 16 trials"

#### B. Document Ray executor scope decision (0.5 day)

**Problem:** `RayExecutor` is a stub, conformance test is local-vs-local, but exit criterion says "runs on both Ray and local executors."

**Options:**
1. Wire `RayExecutor` to real Ray Tune now (~2 days)
2. Restate criterion as "local executor validated, Ray deferred to Tier 0"

**Recommendation:** Option 2 — the spike charter explicitly scopes real Ray to Tier 0. Document in SPIKE_REVIEW.md as a known limitation.

#### C. Write SPIKE_REVIEW.md (1 day)

**Template:**
```markdown
# R1 Spike Interface Review

**Date:** 2026-XX-XX  
**Attendees:** [Project sponsor, tech lead, Tier 0 implementers]  
**Verdict:** [Approved for Tier 0 | Iterate spike]

## Demo results
- spike_branin.py: 8 trials, determinism ✓
- spike_crash_recovery.py: 16 unique trials, no duplicates after fix ✓
- Test suite: 52 tests, 93% coverage ✓

## Contract walk
### SearchSpace
- Mixed continuous/ordinal/categorical: ✓ implemented
- Transforms (log-scale): ✓ tested
- Conditionals: limited (no cross-knob conditions yet)

### Searcher protocol
- propose(n) / observe(trial): ✓
- state_dict() / load_state_dict(): ✓ (added after crash bug)
- Capabilities dict: ✓

[... continue for Scheduler, Executor, Store, Architecture]

## Known limitations (accepted for spike)
1. RayExecutor is stub → Tier 0 will wire real Ray Tune
2. Sobol only handles continuous knobs → Tier 0 adds ordinal/categorical
3. No GP+qLogEI yet → Tier 0 builds it
4. No real RLlib integration → Tier 0 checkpoint surgery

## Interface change requests
[None | List any holes found during review]

## Decision
✅ Interfaces approved for Tier 0 build
Signed: [Names, date]
```

**Deliverable:** Commit `docs/SPIKE_REVIEW.md`, obtain actual stakeholder sign-offs

#### D. Update stale docs (0.5 day)

Fix these mechanical staleness issues:

**README.md:**
- Line ~4: "106 pages" → "114 pages"
- Line ~5: "Phase 0 not started" → "R1 spike complete, Tier 0 ready"

**docs/progress.md:**
- Generate from ground truth using `tools/update_progress.py` (to be written)
- Or hand-update for now: R0 complete, R1 complete with date, blockers resolved

**Archive dead artifacts:**
- `src/` empty skeleton → delete (real code is in `hponas/`)
- `BUILD_PROGRAM.md` (v1) → `archive/BUILD_PROGRAM_v1_REJECTED.md`

**Acceptance:** `python3 tools/gate_check.py --phase r1` returns exit code 0 (PASS)

---

### 2. Write governance tools (2-3 days)

**Priority order:** Start with what unblocks decision-making, elaborate later.

#### A. `tools/gate_check.py` — DONE ✓

Already written and working. Demonstrated it catches the Sobol bug.

**Next:** Add `check_tier0_gate()` implementation after Tier 0 scope finalized.

#### B. `tools/generate_build_program.py` (1-2 days)

**Input files:**
- `hpo-survey-decisions.json` (63 decisions with tier/validation mappings)
- `WORK_BREAKDOWN_TIMELINE_DRAFT.md` (effort, phasing, gate criteria)
- `hpo-survey/sections/16-validation.tex` (V01-V15 protocols)

**Output:**
- `BUILD_PROGRAM_v2.md` (the authoritative plan)

**Algorithm:**
1. Parse decisions.json → group by tier
2. Parse timeline → extract phase/tier effort tables
3. Parse validation.tex → extract V01-V15 criteria
4. Generate markdown with:
   - Phase/tier breakdowns (effort + calendar)
   - Gate criteria (pass/fail/hold conditions)
   - Traceability tables (decision → task → test)
   - Risk register from timeline
   - Cost summary

**Acceptance:** Generate BUILD_PROGRAM_v2.md, diff against v1, verify all V01-V15 match survey register

#### C. `tools/update_progress.py` (1 day)

**Input:**
- Git tags (what phases are locked?)
- Gate reports (`gate_reports/*.md`)
- Test results (pytest --json)
- File existence checks

**Output:**
- `docs/progress.md` (auto-generated, not hand-edited)

**Acceptance:** Generated progress.md matches reality (R0 complete, R1 complete, blockers listed)

#### D. `tools/generate_tasks.py` (0.5 day, low priority)

Can defer until Tier 0 starts. For now, use decisions.json directly.

---

### 3. Generate and approve BUILD_PROGRAM_v2 (1 day)

**Sequence:**

1. **Run generator:**
   ```bash
   python3 tools/generate_build_program.py \
     --decisions hpo-survey-decisions.json \
     --timeline WORK_BREAKDOWN_TIMELINE_DRAFT.md \
     --validation hpo-survey/sections/16-validation.tex \
     --output BUILD_PROGRAM_v2.md
   ```

2. **Review:**
   - You + stakeholders read BUILD_PROGRAM_v2.md
   - Compare against v1: what changed? (effort, phasing, validation criteria)
   - Verify V01-V15 match survey register
   - Check tier dependencies (TuRBO prerequisite for Tier 2, etc.)

3. **Approve:**
   - Write `BUILD_PROGRAM_v2_APPROVAL.md`:
     ```markdown
     # BUILD_PROGRAM v2.0 Approval
     
     **Date:** 2026-XX-XX  
     **Approved by:**
     - [Name], Project Sponsor
     - [Name], Tech Lead
     
     ## Scope
     - 39-48 weeks to internal beta
     - 275-310 engineer-days
     - R0/R1 complete, Tier 0-2 + Distributed Beta
     
     ## Key changes from v1
     - Effort: 42 weeks → 39-48 weeks (more realistic contingency)
     - Phasing: Added R0/R1, mandatory Distributed Beta gate
     - TuRBO moved to Tier 2 (prerequisite per roadmap)
     
     **Decision:** Approved for execution. Next phase: Tier 0.
     ```

4. **Lock:**
   ```bash
   git add BUILD_PROGRAM_v2.md BUILD_PROGRAM_v2_APPROVAL.md
   git commit -m "BUILD_PROGRAM v2.0: approved plan for Tier 0-2"
   git tag program-v2.0
   git push origin main --tags
   ```

5. **Archive v1:**
   ```bash
   mkdir -p archive
   git mv BUILD_PROGRAM.md archive/BUILD_PROGRAM_v1_REJECTED.md
   git mv BUILD_PROGRAM_RECONCILIATION_COMPLETE.md archive/
   # WORK_BREAKDOWN_TIMELINE_DRAFT stays until folded into v2
   ```

**Acceptance:** One authoritative plan exists, tagged, approved, and locked

---

### 4. Set up CI governance checks (0.5 day)

Add `.github/workflows/governance.yml` (see full governance.md for template).

**Three checks:**
1. Verify BUILD_PROGRAM_v2 regenerates identically from inputs (no drift)
2. Verify progress.md regenerates identically from ground truth
3. Run current-phase gate check in dry-run (show findings, don't block CI)

**Acceptance:** PR that changes decisions.json without regenerating BUILD_PROGRAM_v2 fails CI

---

## Timeline for governance setup

| Task | Effort | Dependencies |
|------|--------|--------------|
| Fix Sobol state bug | 1-2d | None |
| Ray executor scope decision | 0.5d | None |
| Write SPIKE_REVIEW.md | 1d | Bug fix complete |
| Update stale docs | 0.5d | SPIKE_REVIEW signed |
| Write generate_build_program.py | 1-2d | None (parallel) |
| Write update_progress.py | 1d | None (parallel) |
| Generate + approve BUILD_PROGRAM_v2 | 1d | Generator ready |
| CI governance checks | 0.5d | v2 approved |
| **Total** | **7-10 days** | |

**Critical path:** Sobol fix → SPIKE_REVIEW → gate pass → v2 generation → approval

**Parallelizable:** Tool writing (generate_build_program.py, update_progress.py) can overlap with R1 fixes

---

## What this buys you

After these 7-10 days:

1. **R1 properly closed** — gate passed, interfaces reviewed, blockers resolved
2. **Single authoritative plan** — BUILD_PROGRAM_v2.md, versioned, approved, tagged
3. **Mechanical drift detection** — gate checks before phase close, CI enforces regeneration
4. **Ground-truth progress** — docs/progress.md auto-generated, never stale
5. **Execution contract** — Tier 0 starts with a frozen, approved program

**Tier 0 can start** with confidence that:
- Interfaces are solid (spike validated them)
- Plan is coherent (generated from structured inputs, approved)
- Drift will be visible (CI checks, gate checks)
- Phase close is mechanical (gate scripts, not judgment calls)

---

## How to use this document

**Immediate (today):**
- Read [governance.md](governance.md) — the full rationale and system design
- Read this summary — the concrete 7-10 day plan
- Decide: commit to governance setup before Tier 0, or start Tier 0 without it?

**If committing to governance:**
- Day 1-2: Fix Sobol bug
- Day 2-3: Write generate_build_program.py
- Day 3: Write SPIKE_REVIEW.md, obtain sign-offs
- Day 4: Generate BUILD_PROGRAM_v2, review
- Day 5: Approve v2, set up CI
- Day 6-7: Write update_progress.py, verify everything works
- Day 8+: Tier 0 starts from a solid foundation

**If starting Tier 0 without governance:**
- Accept risk of drift recurring
- Plan to retrofit governance after first phase slip or drift event
- Budget 2x the setup time (retrofits are harder than greenfield)

---

## Open questions

1. **Statistical reviewer verification** — R0's one outstanding item. Waive, or chase before Tier 0?

2. **V06/V10/V13 gate timing** — Survey says T1 gate (week 12), BUILD_PROGRAM deferred to week 30. Size tasks during Phase 0, then decide timing.

3. **V04 tier-0 scope** — Does "tier-0 GP with qLogEI" mean basic GP (no priors), or full prior-aware qLogEI? Clarify during Tier 0 start.

---

**Recommendation:** Do the 7-10 days. Governance setup is cheaper than recovering from the next drift event.
