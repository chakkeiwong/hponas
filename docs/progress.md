# Build Progress Tracker

**Last updated:** 2026-08-26  
**Current phase:** Pre-development (Phase 0 not started)  
**Next milestone:** Codex review of build program, then Phase 0 start

---

## Phase 0: Setup and interface freeze (weeks 1–2)

**Status:** Not started  
**Target completion:** TBD (awaiting program approval)

- [ ] Environment installable (all tier-0 deps resolve)
- [ ] `StudySpec` parser (YAML → internal representation)
- [ ] `SearchSpace` schema with priors
- [ ] `Searcher` / `Scheduler` protocols with capability flags
- [ ] Run store schema (DDL + migration zero)
- [ ] Pinned validation tasks sized and recorded
- [ ] Empty harness runs (no-op study writes to store)
- [ ] **Checkpoint:** Interface freeze reviewed by stakeholders

---

## Tier 0: Wrapping campaign (weeks 3–6)

**Status:** Blocked on Phase 0 completion  
**Gate:** V01–V03, V05, V14

### Searcher wrappers (5d)
- [ ] Sobol/Random (Ray built-in, 0.5d)
- [ ] TPE (Optuna adapter, 2d)
- [ ] DEHB (vendor or wrap, 2.5d)

### Scheduler wrappers (3d)
- [ ] ASHA (Ray built-in, 1d)
- [ ] MedianStopper (Ray built-in, 1d)
- [ ] Capability flags (1d)

### Run store (8d)
- [ ] SQLite backend with tables (2d)
- [ ] Store client (CRUD + lineage, 3d)
- [ ] Standing diagnostics (convergence, best-by-fidelity, 2d)
- [ ] Unit tests (1d)

### Executor adapters (6d)
- [ ] RLlib adapter (checkpoint surgery, 3d)
- [ ] Generic adapter (user train_fn, 2d)
- [ ] Integration test (CartPole study, 1d)

### Workload templates (stubs) (2d)
- [ ] Four YAML skeletons (1d)
- [ ] Template registry (1d)

### Validation prep (3d)
- [ ] V01, V02, V03 implemented (2d)
- [ ] Campaign runner script (1d)

### Integration (3d)
- [ ] End-to-end smoke test (1d)
- [ ] Usage examples (quickstart, rl_cartpole, 1d)
- [ ] Docstrings and README (1d)

**Gate result (week 6):** _Pending_

---

## Tier 1: Method differentiators (weeks 7–12)

**Status:** Blocked on tier-0 gate  
**Gate:** V04, V09, V11

_(Breakdown omitted until tier 0 starts)_

---

## Tier 2: Flagship and freeze-thaw (weeks 13–30)

**Status:** Blocked on tier-1 gate  
**Gate:** V07, V08, V15

_(Breakdown omitted until tier 1 starts)_

---

## Risk flags (live)

_No flags yet (pre-development)_

When development starts, log risk tripwires here:
- **Week X:** [Risk category] — [Observed signal] → [Mitigation taken]

---

## Gate history

| Gate | Date | Tests run | Result | Notes |
|------|------|-----------|--------|-------|
| Tier 0 (week 6) | TBD | V01-V03, V05, V14 | Pending | - |
| Tier 1 (week 12) | TBD | V04, V09, V11 | Pending | - |
| Tier 2 (week 30) | TBD | V01-V15 (full) | Pending | - |

---

## Decisions logged

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-26 | Survey released for review | 106 pages, clean build, all decision boxes falsifiable |
| 2026-08-26 | Build program written | Three tiers, 42 eng-weeks, awaiting codex review |

_Add new decisions here as the build progresses._
