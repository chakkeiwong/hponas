# R1 Executable Architecture Spike — Charter

**Phase:** R1 Executable Architecture Spike  
**Duration:** 3 weeks (calendar)  
**Effort:** 27 engineer-days  
**Status:** Ready to begin  
**Dependencies:** R0 complete (all exit criteria met)

---

## Purpose

Prove the corrected interfaces work end-to-end before Tier 0 commits to them. Build the minimal executable stack: one real study running on both Ray and local executors, with crash recovery demonstrated, architecture factory stubs in place, and conformance tests passing. If the spike reveals interface holes, fix them now rather than after weeks of Tier 0 work.

---

## Scope

**In scope:**
- Minimal SearchSpace (continuous, ordinal, categorical, transforms, conditions)
- Sobol searcher (wraps scipy Sobol + log-scale, batch propose)
- ASHA scheduler (rung promotion, async event handling, budget tracking)
- Ray executor adapter (trial launch, reporter, checkpoint surgery)
- Local executor adapter (same semantics, subprocess isolation)
- Store with crash recovery (SQLite, serialized writes, lineage queries)
- Seed separation (tuning seeds never reach test-seed evaluation)
- Architecture factory stubs (build/measure/compatible/transfer for Option A typed coordinates)
- State-machine tests (out-of-order events, duplicates, restart)
- One real end-to-end study: 2D Branin optimization, 16 trials, both executors produce same results
- Crash-and-resume demonstration

**Out of scope (Tier 0 work):**
- GP+qLogEI searcher
- TPE wrapper
- Median stopping rule
- RLlib integration
- Real workload templates (rl_routine, etc.)
- Full validation suite (V01-V05, V14)
- Product packaging

---

## Deliverables

### 1. Runnable study (end-to-end)
**File:** `examples/spike_branin.py`  
**Spec:**
- 2D Branin function (standard optimization benchmark)
- SearchSpace: 2 continuous axes in [-5, 10] and [0, 15], log-transform on one
- 16 trials total
- Sobol searcher (8 initial Sobol points, then random)
- ASHA scheduler (η=3, r_min=1, r_max=27, median stopping disabled for simplicity)
- Runs on both Ray and local executors
- Determinism test: same seed → same trials → same incumbent (within floating-point tolerance)

### 2. Crash recovery demonstration
**File:** `examples/spike_crash_recovery.py`  
**Spec:**
- Same Branin study as above
- Coordinator crashes after trial 8
- Study restarted from SQLite store
- Trials 9-16 continue without re-running 1-8
- No duplicate observations in store
- Final result matches the no-crash baseline

### 3. Architecture factory stubs
**File:** `hponas/architecture.py`  
**Spec:**
- Four stub functions: `build(config)`, `measure(model)`, `compatible(cfg_a, cfg_b)`, `transfer(parent, child)`
- Typed coordinates from Option A: width (ordinal), depth (ordinal), activation (categorical), normalization (categorical)
- `build` returns a dummy object with `width`, `depth`, `activation`, `normalization` attributes
- `measure` returns `(params=width*depth*100, flops=width*depth*1e6)` as a simple mock
- `compatible` returns True if width and depth match, False otherwise
- `transfer` policy enum: `RESTART` (always, distillation deferred to Tier 2)
- Docstrings reference survey Ch 9 scope boundary and Ch 15 contract

### 4. Test suite (foundational)
**File:** `tests/`  
**Coverage:**
- **Contract tests:** SearchSpace validation (reject invalid bounds, transforms, conditions), seed separation (tuning seeds never reach evaluation), budget arithmetic (ASHA rung calculations)
- **State-machine tests:** ASHA promotion under async events (trials finish out of order, stragglers, early stops)
- **Conformance tests:** Ray executor vs local executor produce equivalent trials (same seeds → same configs proposed → same incumbent)
- **Recovery tests:** store crash and restart without duplicate observations; lineage queries survive restart
- **Architecture tests:** factory stubs enforce compatibility correctly; incompatible pairs refuse checkpoint surgery

**Target:** >80% line coverage on spike code (not Tier 0 target, just spike validation)

### 5. Package infrastructure
**Files:** `pyproject.toml`, `environment.yml`, `.github/workflows/ci.yml`  
**Spec:**
- `pyproject.toml`: dependencies (numpy, scipy, botorch, gpytorch, ray, sqlalchemy), package metadata, pytest config
- `environment.yml`: conda lock for CPU profile (no CUDA in spike)
- CI workflow: lint (ruff), type check (mypy on strict), unit tests (pytest with coverage report), smoketest (examples/spike_branin.py runs in <60s)
- Clean install test: `conda env create -f environment.yml && pip install -e . && pytest` on 2 machines (Linux, macOS if available)

### 6. Interface freeze review
**File:** `docs/SPIKE_REVIEW.md`  
**Attendees:** Project sponsor, tech lead, 1-2 engineers who will build Tier 0  
**Agenda:**
- Demo: spike_branin.py on both executors, determinism check, crash recovery
- Contract walk: SearchSpace schema, searcher.propose/observe, scheduler.report/promote, executor adapter hooks, architecture factory
- Known limitations: what the spike does *not* validate (GP+qLogEI kernel choices, RLlib checkpoint surgery, real workload fidelity mappings)
- Interface change requests: if Tier 0 implementers see a hole or a contract that won't generalize, flag it now
- Go/no-go for Tier 0: freeze these interfaces and start the 8-10 week build, or iterate the spike first?

**Deliverable:** Signed-off `SPIKE_REVIEW.md` with decision: "Approved for Tier 0" or "Iterate spike (specific changes)"

---

## Work breakdown

| Component | Effort | Dependencies | Owner | Notes |
|-----------|--------|--------------|-------|-------|
| **Minimal SearchSpace** | 3d | None | Eng 1 | Mixed continuous/ordinal/categorical, transforms, conditions |
| **Sobol searcher** | 2d | SearchSpace | Eng 1 | Wraps scipy Sobol + log-scale, batch propose |
| **ASHA scheduler** | 3d | None | Eng 1 | Rung promotion, async event handling, budget tracking |
| **Ray executor adapter** | 4d | None | Eng 2 | Trial launch, reporter, checkpoint save/load/copy |
| **Local executor adapter** | 3d | None | Eng 2 | Same semantics as Ray, subprocess isolation |
| **Store with recovery** | 5d | None | Eng 2 | SQLite + serialized writer, crash recovery, lineage queries |
| **Seed separation** | 2d | SearchSpace, Store | Eng 1 | Tuning seeds never reach test-seed evaluation |
| **Architecture factory stubs** | 2d | SearchSpace | Eng 1 | build/measure/compatible/transfer for Option A |
| **State-machine tests** | 3d | All above | Both | Out-of-order events, duplicates, restart; conformance |
| **Total** | **27d** | | | |

**Parallelization:**
- Week 1: Eng 1 (SearchSpace + Sobol + ASHA start), Eng 2 (executors + store)
- Week 2: Eng 1 (ASHA finish + seed separation + architecture stubs), Eng 2 (store recovery + executor conformance)
- Week 3: Both (state-machine tests, examples, CI, interface review)

**Critical path:** Store recovery → crash demo → interface review

---

## Entry criteria (all met)

- [x] R0 complete (all corrections applied, NAS scope decided, work breakdown with realistic timeline)
- [x] Survey builds clean (114 pages, 0 errors)
- [x] Traceability matrix complete (63 decisions, validation mappings filled)
- [x] Product register regenerated (47 entries, 0 TBD contracts)
- [x] Work breakdown updated with Option A as unconditional (+16 engineer-days in Tier 2)

---

## Exit criteria

- [ ] One real study (spike_branin.py) runs end-to-end on both Ray and local executors
- [ ] Determinism test passes: same seed → same results
- [ ] Crash recovery demonstrated: coordinator dies, restarts, continues without duplicates
- [ ] Foundational test suite passes (contract, state-machine, conformance, recovery, architecture)
- [ ] Clean install from lock on 2 machines (Linux required, macOS nice-to-have)
- [ ] Architecture factory stubs enforce compatibility correctly (pure hyperparameter changes transfer, width/depth changes refuse)
- [ ] Stakeholder review complete: interfaces approved for Tier 0 build (signed SPIKE_REVIEW.md)

---

## Known limitations (documented, accepted for spike)

The spike validates that the interfaces *can* express the required operations. It does **not** validate:
- GP+qLogEI kernel choices (no BoTorch in spike; Sobol only)
- RLlib checkpoint surgery mechanics (no RLlib; local executor uses toy process isolation)
- Real workload fidelity mappings (Branin has no fidelity axis)
- ASHA promotion logic under high-concurrency async (16 trials is too small to stress-test)
- Store query performance at scale (SQLite with 16 rows is not a real benchmark)
- Architecture factory build/measure with real neural networks (stubs return mocks)
- Distillation transfer policy (deferred to Tier 2; spike only implements RESTART)

These are Tier 0 work, not spike work. The spike proves the contracts are sufficient; Tier 0 fills them with production implementations.

---

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Interface hole discovered during spike | Medium | High | Expected; fix interface now, cheaper than after Tier 0 |
| Ray executor adapter harder than estimated | Medium | Medium | Local executor is the fallback; Ray can slip to early Tier 0 if needed |
| Crash recovery reveals SQLite locking issue | Low | High | Use WAL mode from day 1; test concurrent writes in state-machine suite |
| Clean install fails on macOS | Low | Low | Linux is the primary target; macOS nice-to-have, not gating |
| Stakeholder review requests interface changes | Low | Medium | Iterate spike week 4 if changes are small; escalate to sponsor if fundamental |

---

## Success criteria

**Minimum (required for Tier 0 handoff):**
- One study runs end-to-end on both executors with same results
- Crash recovery works without duplicates
- Test suite passes on Linux
- Stakeholders approve interfaces

**Target (preferred):**
- Above + clean install on macOS
- Above + >80% line coverage
- Above + CI green (lint, type, test, smoketest)

**Stretch (nice-to-have, not gating):**
- Architecture factory stubs match real Flax/Haiku model construction patterns
- Store lineage queries exercise by a simple "show me the hyperparameter schedule" notebook
- Conformance tests include a stochastic objective (not just deterministic Branin) with seed separation verified

---

## Handoff to Tier 0

**On spike approval:**
- Interfaces are frozen
- Tier 0 begins (8-10 weeks, 65 engineer-days)
- Spike code becomes the foundation: SearchSpace/Sobol/ASHA refined, executors extended for RLlib, store gains diagnostics/fronts/artifacts

**If spike requires iteration:**
- Stakeholder review document lists required changes
- Iterate spike (1-2 weeks depending on scope)
- Re-review before Tier 0 starts

---

## Schedule

**Week 1 (days 1-5):**
- SearchSpace + Sobol searcher + ASHA start (Eng 1)
- Ray + local executors + store foundation (Eng 2)
- Daily standup: interface questions surfaced early

**Week 2 (days 6-10):**
- ASHA finish + seed separation + architecture factory stubs (Eng 1)
- Store recovery + executor conformance (Eng 2)
- Mid-spike checkpoint: can we run spike_branin.py end-to-end yet?

**Week 3 (days 11-15):**
- State-machine tests, crash recovery demo (both)
- CI setup, clean install test (both)
- Stakeholder review prep: slides, demo script, known-limitations doc (Eng 1)
- Interface review meeting (day 14 or 15)
- SPIKE_REVIEW.md signed off

**Slack (days 16-21 if needed):**
- Interface iteration if review requests changes
- Otherwise: documentation cleanup, stretch goals, or early start on Tier 0 packaging

---

**R1 Spike Charter approved:** 2026-08-28  
**Ready to begin:** Yes  
**Next milestone:** Week 3 interface review → Tier 0 handoff
