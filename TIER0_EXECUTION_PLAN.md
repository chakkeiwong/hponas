# Tier 0 Execution Plan

**Created:** 2026-08-31  
**Phase:** Tier 0 Foundation  
**Status:** IN PROGRESS  
**Ground truth:** BUILD_PROGRAM_v2.md lines 88-134

---

## Overview

Tier 0 builds on R1 spike foundation to deliver production-ready core capabilities:
- **Duration:** 8-10 weeks
- **Effort:** ~65 engineer-days
- **Gate:** V01-V05, V14, V04-T0 (~2,500 accelerator-hours)

---

## Work Breakdown

### 1. Searchers (15 engineer-days)

**Refine existing:**
- Sobol: mixed-space support (ordinal/categorical), conditional handling
- Random: complete implementation with proper sampling

**New implementations:**
- TPE wrapper (Optuna) — ~4d
- GP + qLogEI (BoTorch) — ~8d (core build)
  - Dimension-scaled lengthscale priors
  - Log-warping for scale-sensitive parameters
  - Multi-output GP for multi-fidelity

**Exit criteria:**
- All searchers pass V01 (implementation parity)
- State serialization for crash recovery
- Capabilities accurately declared

---

### 2. Schedulers (7 engineer-days)

**Refine existing:**
- ASHA: production hardening from R1 spike

**New implementations:**
- Median stopping rule — ~3d
- PASHA (promotion-based ASHA) — ~4d

**Exit criteria:**
- All schedulers pass V02 (async correctness)
- Property tests for out-of-order/duplicate/late events
- Budget tracking accurate

---

### 3. Executors (8 engineer-days)

**Refine existing:**
- LocalExecutor: production hardening

**New implementation:**
- RayExecutor with RLlib integration — ~6d
  - Checkpoint surgery for state recovery
  - Resource allocation
  - Fault tolerance

**Exit criteria:**
- Both executors pass conformance suite
- RLlib checkpoint compatibility verified
- Resource tracking accurate

---

### 4. Store (3 engineer-days)

**Extensions to R1 foundation:**
- Diagnostic queries (trial history, convergence metrics)
- Pareto front tracking for multi-objective
- Artifact tracking (checkpoint paths, metrics)

**Exit criteria:**
- Schema supports all tier-0 queries
- Migration path from R1 schema if needed
- Performance adequate for validation campaigns

---

### 5. Workload Templates (8 engineer-days)

**rl_routine production build:**
- Real PPO/Brax integration (not stub)
- Day-one walk from Chapter 15
- Seed isolation (protected seeds never reach searcher)
- Configuration validation

**Exit criteria:**
- V14 (day-one walk reproduction) passes
- Template documented and ready for validation campaigns
- Artifact outputs match specification

---

### 6. Tests (10 engineer-days)

**Test infrastructure:**
- Contract tests for all protocols
- Property tests for schedulers (async correctness)
- Mutation testing (V03 requirement)
- Migration tests for store schema

**Exit criteria:**
- V03 (sabotage detection) passes with >0.9 kill score
- Coverage maintained at >90%
- All mutation operators implemented

---

### 7. Validation Campaign Infrastructure (14 engineer-days)

**Task registry:**
- Size acceptance task set
- Freeze scale bounds per task
- Generate seed sets (pilot and confirmatory separate)

**Campaign runner:**
- Manifest generation and verification
- Paired cluster bootstrap implementation
- Result collection and analysis pipeline

**Protocol execution:**
- V01: distributional regression vs vendor references
- V02: state-machine property tests
- V03: mutation testing with kill score
- V04-T0: superiority test vs log+Sobol floor and random
- V05: log-warping gain test
- V14: end-to-end walk reproduction

**Exit criteria:**
- All validation entries V01-V05, V14, V04-T0 complete
- Gate report generated
- Demotion decisions (if any) recorded

---

## Execution Sequence

### Week 1-2: Foundation Extensions
- Refine Sobol/Random for mixed-space
- Harden LocalExecutor
- Extend store schema

### Week 3-4: Core Searchers
- TPE wrapper implementation
- Begin GP + qLogEI (BoTorch integration)

### Week 5-6: Complete Searchers + Schedulers
- Complete GP implementation
- Median stopping rule
- PASHA scheduler

### Week 7: Executors + Workload
- RayExecutor with RLlib
- rl_routine production build

### Week 8: Validation Prep
- Task registry finalization
- Campaign runner implementation
- Manifest tooling

### Week 9-10: Validation Campaigns
- Run V01-V05, V14, V04-T0
- Analyze results
- Generate gate report

---

## Gate Criteria

**Pass conditions:**
- [ ] V01: All wrappers match reference implementations (distributional equivalence)
- [ ] V02: Schedulers correct under asynchrony (zero violations)
- [ ] V03: Test suite catches seeded defects (kill score ≥0.9)
- [ ] V04-T0: TPE and GP+qLogEI beat log+Sobol floor AND random (α=0.05, family-adjusted)
- [ ] V05: Log-warping helps on scale-sensitive tasks (α=0.05, family-adjusted)
- [ ] V14: Day-one walk reproduces, no seed leakage

**Demotion triggers:**
- V01 fail → Block Tier 1, diagnose wiring
- V04-T0 fail → Identify and fix before proceeding
- V05 fail → Demote log-warping to opt-in

---

## Dependencies

**From R1:**
- Spike interfaces (frozen per SPIKE_REVIEW.md)
- SQLite store with crash recovery
- Architecture factory stubs
- Test foundation (56 tests, 93% coverage)

**For Tier 1:**
- Production executors (both Ray and local)
- GP foundation for TuRBO and priors
- Store schema finalized

---

## Risks

| Risk | Mitigation |
|------|------------|
| BoTorch integration complexity | Allocate 8d; start early (week 3) |
| RLlib checkpoint surgery | Prototype in week 7; 2d contingency |
| Validation campaign blocks on env install | Install Brax at start, test import week 1 |
| V04-T0 fails (searchers don't beat floor) | Investigate immediately; replan tier 1 if needed |

---

## Progress Tracking

Track via `docs/progress.md` (auto-generated from ground truth):
```bash
python3 tools/update_progress.py
```

Task generation:
```bash
python3 tools/generate_tasks.py --phase tier0
```

---

## Next Steps

Starting Tier 0 execution:
1. Create work branches for parallel tracks
2. Set up validation task registry
3. Begin searcher implementations (TPE, GP)
4. Extend test infrastructure
