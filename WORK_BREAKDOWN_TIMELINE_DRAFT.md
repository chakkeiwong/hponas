# Work Breakdown and Timeline Reconstruction
**Status:** DRAFT - awaiting traceability matrix completion  
**Based on:** Codex review corrections + survey specifications  
**Methodology:** Bottom-up from tasks, not top-down from milestones

---

## Methodology

This timeline is built from:
1. **Traceability matrix** (in progress) — every decision → implementation task
2. **Codex review corrections** — missing items from B2 (scope mismatches)
3. **Test layer requirements** — from B5 (test strategy gaps)
4. **Realistic effort estimates** — including integration contingency
5. **Resource capacity modeling** — realistic utilization, not 100%

**Units clearly defined:**
- **Engineer-days**: 1 person-day of implementation/test work (planning unit)
- **Calendar weeks**: Elapsed time accounting for dependencies, reviews, blockers
- **Accelerator-hours**: GPU/TPU time for validation campaigns (compute budget)
- **Wall-clock hours**: Campaign elapsed time accounting for parallelism

---

## Phase R0: Specification Correction (CURRENT)

**Duration:** 2 weeks (calendar)  
**Effort:** ~5 engineer-days (spread across multiple people)  
**Status:** In progress (day 1)

| Task | Owner | Effort | Duration | Status |
|------|-------|--------|----------|--------|
| NAS scope decision | Sponsor | 0d | 1 day | Analysis complete, decision pending |
| Statistical reviewer hire | Lead | 0.5d | 3 days | Not started |
| LaTeX validation corrections | Author + reviewer | 2d | 7 days | Draft complete, review pending |
| V08 semantics clarification | Author | 0.5d | 2 days | Specified in draft |
| Knob-kind ambiguity resolution | Author | 0.5d | 2 days | Not started |
| Traceability matrix generation | Tech lead | 1.5d | 5 days | Agent in progress |
| V01-V15 protocol corrections | Validation lead + reviewer | 3d | 7 days | Draft complete, review pending |
| Timeline rebuild | Lead + tech leads | 2d | 3 days | This document (draft) |
| product_register_v2 generation | Author | 0.5d | 2 days | Not started |

**Total effort:** ~10.5 engineer-days  
**Critical path:** Statistical reviewer availability → validation corrections finalized  
**Exit criteria:** All corrections reviewed and committed, traceability matrix complete

---

## Phase R1: Executable Architecture Spike

**Duration:** 3 weeks (calendar, was 2 in plan)  
**Effort:** 27 engineer-days  
**Rationale:** Must prove crash recovery and conformance before freezing interfaces

### Core spike components

| Component | Effort | Dependencies | Deliverable |
|-----------|--------|--------------|-------------|
| **Minimal SearchSpace** | 3d | None | Mixed continuous/ordinal/categorical, transforms, conditions |
| **Sobol searcher** | 2d | SearchSpace | Wraps Sobol + log-scale, batch propose |
| **ASHA scheduler** | 3d | None | Rung promotion, async event handling |
| **Ray executor adapter** | 4d | None | Trial launch, reporter, checkpoint |
| **Local executor adapter** | 3d | None | Same semantics as Ray, subprocess isolation |
| **Store with recovery** | 5d | None | SQLite + serialized writer, crash recovery, lineage queries |
| **Seed separation** | 2d | SearchSpace, Store | Tuning seeds never reach test-seed evaluation |
| **Architecture factory stub** | 2d | SearchSpace | build/measure/compatible/transfer stubs for Option A |
| **State-machine tests** | 3d | All above | Out-of-order events, duplicates, restart |

**Total effort:** 27 engineer-days  
**Parallelization:** 2 engineers → 15 calendar days, but staging required  
**Realistic calendar:** 3 weeks (includes review, iteration, integration)

### Deliverables for R1

1. **One real study end-to-end**
   - 2D Branin optimization, 16 trials
   - Sobol searcher + ASHA scheduler
   - Runs on both Ray and local executor
   - Same results (determinism test)
   - Survives coordinator crash and resume

2. **Test suite (foundational)**
   - Contract tests: SearchSpace validation, seed separation, budget arithmetic
   - State-machine tests: ASHA promotion under async events
   - Conformance tests: Ray vs local produce equivalent trials
   - Recovery tests: Store crash and restart without duplicate observations

3. **Package infrastructure**
   - pyproject.toml with dependencies
   - Conda lock for CPU profile
   - pytest configuration
   - CI workflow (lint, type, unit tests)
   - Clean install smoketest

4. **Interface freeze review**
   - Stakeholder demo of spike
   - Known limitations documented
   - Interfaces frozen for Tier 0 (or adjusted based on spike findings)

### Exit criteria for R1

- [ ] End-to-end study runs on Ray and local executors
- [ ] Coordinator crash and resume demonstrated without duplicate observations
- [ ] Foundational test suite passes (contract, state-machine, conformance, recovery)
- [ ] Clean install from lock on 2+ machines
- [ ] Stakeholder review complete, interfaces approved for Tier 0 build

---

## Tier 0: Foundation (CORRECTED)

**Duration:** 8-10 weeks (calendar, was 4 weeks in rejected plan)  
**Effort:** ~65 engineer-days (was 30 in rejected plan)  
**Rationale:** Must include GP+qLogEI, both executors, real rl_routine per survey

### Tier 0 scope (corrected per Codex B2)

**Searchers:**
- Random (trivial, validation baseline only)
- Sobol + log-scale (already in R1 spike, refine)
- TPE via Optuna wrapper (~4d)
- GP + qLogEI via BoTorch (~8d) — **ADDED**, was missing
- Dimension-scaled lengthscale priors (~1d) — **ADDED**, was missing

**Schedulers:**
- ASHA (already in R1 spike, refine)
- Median stopping rule (~2d)
- PASHA option (~3d) — **ADDED**, was missing

**Executors:**
- Ray adapter (already in R1 spike, refine for RLlib)
- Local adapter (already in R1 spike, refine)
- RLlib integration (~5d) — checkpoint surgery, resume, fidelity mapping

**Store:**
- Already in R1 spike, add: diagnostic logging, front tracking, artifact URIs

**Workload templates:**
- **rl_routine** (~5d implementation + 3d validation fixtures) — **REAL**, not stub
- rl_large_parallel (stub with schema validation, raises NotImplementedError)
- hamiltonian_mo (stub)
- sampler_neutra (stub)

**Test infrastructure:**
- Extend contract tests (~2d)
- Property tests for searcher ask/tell (~3d)
- Store migration framework (~2d)
- Mutation testing for V03 (~3d)
- Development task set sizing and documentation (~2d)

**Validation prep:**
- Size pinned tasks and record cost estimates (~3d)
- Implement corrected V01-V05, V14 (~8d)
- Campaign runner with manifest generation (~3d)

### Work breakdown (Tier 0)

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **Searchers** | Refine Sobol/Random, TPE wrapper, GP+qLogEI+priors | 15d | GP is core build (~8d) |
| **Schedulers** | Refine ASHA, Median, PASHA | 7d | ASHA mostly done in R1 |
| **Executors** | Refine Ray/local, RLlib integration | 8d | Checkpoint surgery non-trivial |
| **Store** | Diagnostics, fronts, artifact tracking | 3d | Extends R1 foundation |
| **Workload** | rl_routine production build | 8d | Real PPO/Brax day-one walk |
| **Tests** | Contract/property/migration/mutation | 10d | Foundation for all tiers |
| **Validation** | Task sizing, V01-V05/V14, runner | 14d | Corrected protocols |
| **Total** | | **65d** | |

### Parallelization and calendar

**With 1 engineer:**
- 65 days = 13 weeks at 100% utilization
- Realistic: 15-16 weeks with integration overhead

**With 2 engineers (recommended):**
- Independent tracks: (1) searchers/schedulers, (2) executors/workloads
- Some serialization required (tests depend on implementations)
- Realistic: 8-10 weeks with reviews and integration

**Critical path:** GP+qLogEI → V04 validation → gate decision

### Tier 0 gate: V01-V05, V14, V04-T0

**Validation entries:**
- V01: Implementation parity (corrected: distributional regression)
- V02: Async correctness (corrected: state-machine tests added)
- V03: Sabotage detection (corrected: mutation testing)
- V04 (T0 component): TPE and GP+qLogEI beat random on development tasks, meet non-inferiority on acceptance tasks
- V05: Log-warping effectiveness (corrected: positive gain on scale-sensitive tasks)
- V14: Day-one walk reproduction (corrected: real rl_routine, not stub)

**Campaign cost estimate:**
- V01-V03: Deterministic tests, negligible compute
- V04: 10 reps × 3 methods × 2 tasks × ~20 trials = ~600 trials on development RL task
  - If 1 trial = 2 accel-hours, ~1,200 accel-hours (~7 accel-days)
- V05: 10 reps × 2 arms × 1 task × ~30 trials = ~600 trials, ~1,200 accel-hours
- V14: 1 end-to-end walk, ~50 trials, ~100 accel-hours
- **Total: ~2,500 accel-hours (~15 accel-days, ~0.5 GPU-week)**

**Wall-clock with 4 GPUs:** ~4 days for campaigns after implementation complete

### Exit criteria for Tier 0

- [ ] All T0 searchers/schedulers implemented with unit tests
- [ ] Both executors pass conformance suite
- [ ] rl_routine template production-ready with documented example
- [ ] Development and acceptance task sets documented
- [ ] V01-V05, V14, V04-T0 validation complete (may have demotions per protocol)
- [ ] Gate report with manifest, results, and promotion/demotion decisions
- [ ] No blockers (block state in any validation entry stops tier)

---

## Tier 1: Method Differentiators (CORRECTED)

**Duration:** 8-10 weeks (calendar, was 6 in rejected plan)  
**Effort:** ~70 engineer-days (was 30 in rejected plan)  
**Rationale:** Must include full MO stack, EI-per-cost, correct piBO/PriorBand implementations

### Tier 1 scope (corrected per Codex B2)

**Multi-objective:**
- qLogNEHVI via BoTorch (~4d)
- Chebyshev scalarization (~2d) — **ADDED**, was missing
- NSGA-II wrapper (~3d) — **ADDED**, was missing for V09
- Hypervolume and front reporting (~2d)
- MO-ASHA with veto gates (~5d)

**Priors and transfer:**
- πBO with decaying acquisition multiplier (~5d) — **CORRECTED**, was GP mean substitution
- PriorBand with rung portfolio (~4d) — **CORRECTED**, was top-K sampling
- Nonzero-support guard (~1d)
- Warm-start query engine (~3d) — ranked/quantile, NOT RGPE yet

**Cost-aware:**
- EI-per-cost with cooling (~4d) — **ADDED**, was omitted
- Predictive cost model (GP on log wall-clock) (~3d) — **ADDED**

**Workloads:**
- hamiltonian_mo production build (~5d)
- sampler_neutra production build (~5d)
- finance_mo template if in scope (~5d) — **CONDITIONAL on R0 decision**

**Tests:**
- Property tests for MO-ASHA veto correctness (~3d)
- Prior recovery tests (wrong prior doesn't break) (~2d)
- Cost model tests (~2d)

**Validation:**
- V04-T1: TuRBO and prior-aware qLogEI validation (~5d campaign)
- V06: ASHA nearly-free on real RL (~5d campaign) — **MOVED from T2**
- V09: qLogNEHVI vs Chebyshev vs NSGA-II (~4d campaign)
- V10: MO-ASHA rung correlation pilot (~3d campaign) — **MOVED from T2**
- V11: Prior safety (good helps, wrong recovers) (~4d campaign)
- V13: Sampler veto correctness (~5d campaign) — **MOVED from T2**

### Work breakdown (Tier 1)

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **MO stack** | qLogNEHVI, Chebyshev, NSGA-II, reporting, MO-ASHA | 16d | Complete fallback path |
| **Priors** | Correct πBO, correct PriorBand, nonzero guard, warm-start | 13d | Faithful implementations |
| **Cost-aware** | EI-per-cost, predictive cost model | 7d | Was missing entirely |
| **Workloads** | hamiltonian_mo, sampler_neutra, finance (cond.) | 15d | Production-ready with examples |
| **Tests** | MO veto, prior recovery, cost model | 7d | Correctness before campaigns |
| **Validation** | V04-T1, V06, V09-V11, V13 campaigns | 12d | Moved V06/V10/V13 from T2 per survey |
| **Total** | | **70d** | Excludes finance if out of scope (-5d) |

### Parallelization and calendar

**With 2 engineers:**
- Track 1: MO stack + validation
- Track 2: Priors/cost + workload templates
- Realistic: 8-10 weeks with reviews and campaigns

### Tier 1 gate: V04-T1, V06, V09-V11, V13

**Campaign cost estimate:**
- V04-T1: 10 reps × 2 methods × 2 tasks × ~30 trials = ~1,200 trials, ~2,400 accel-hours
- V06: 10 reps × 2 arms × 2 tasks × ~50 trials = ~2,000 trials, ~4,000 accel-hours
- V09: 10 reps × 3 methods × 1 task × ~32 trials = ~960 trials, ~1,920 accel-hours
- V10: 1 pilot × 100 configs × 1 seed = ~133 full-run-equivalents, ~266 accel-hours
- V11: 10 reps × 3 prior conditions × 1 task × ~30 trials = ~900 trials, ~1,800 accel-hours
- V13: 4 chains × ~10 configs × long runs = ~500 accel-hours (MCMC, different cost model)
- **Total: ~10,900 accel-hours (~65 accel-days, ~2.3 GPU-weeks)**

**Wall-clock with 8 GPUs:** ~8 days for campaigns

### Exit criteria for Tier 1

- [ ] Complete MO stack with fallback paths (qLogNEHVI, Chebyshev, NSGA-II)
- [ ] Correct πBO and PriorBand implementations with recovery tests
- [ ] EI-per-cost with predictive cost model
- [ ] Production workload templates for all in-scope domains
- [ ] V04-T1, V06, V09-V11, V13 validation complete
- [ ] Gate report with decisions (may include demotions per protocol)

---

## Tier 2: Population Line (CORRECTED)

**Duration:** 14-18 weeks (calendar, was 18 in rejected plan but poorly phased)  
**Effort:** 70 engineer-days (was claimed 90 but actually 58 in rejected plan)  
**Rationale:** Must include mixed-space TuRBO first (T2 prerequisite per roadmap), then architecture support if NAS in scope

### Tier 2 scope (corrected per Codex B2, B6)

**Prerequisites (must complete first):**
- Mixed-space trust-region BO (TuRBO) (~10d) — **MOVED from T1**, is T2 prerequisite per roadmap 12:199-205

**Population methods:**
- PB2 continuous (~5d)
- PB2-Mix (continuous + categorical bandit) (~5d)
- BG-PBT population manager (~8d)

**Architecture support (if moderate NAS in scope per R0):**
- Architecture factory contract (~3d) — typed axes, validity, construction
- Compatibility policy (~2d) — when can checkpoints transfer?
- Distillation protocol (~6d) — teacher selection, loss, schedule, rollback
- Architecture proposal (~3d) — how explore generates new architectures
- Measured objectives (~2d) — parameter count, FLOPs from model

**Tests:**
- TuRBO restart and mixed-space correctness (~3d)
- Population checkpoint compatibility (~2d)
- Distillation correctness (same-arch transfer, cross-arch distill) (~3d)
- Architecture validity and construction (~2d)

**Workload:**
- rl_large_parallel production build (~6d) — 8+ workers, BG-PBT default

**Validation:**
- V08: Population home-regime test (~10d campaign, 3-rep pilot + analysis)

### Work breakdown (Tier 2)

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **TuRBO (prerequisite)** | Mixed-space trust-region BO | 10d | Moved from T1, roadmap week 13-20 |
| **Population core** | PB2, PB2-Mix, BG-PBT manager | 18d | Faithful implementation |
| **Architecture** | Factory, compatibility, distillation, proposal, objectives | 16d | Option A approved 2026-08-28 |
| **Tests** | TuRBO, population, distillation, architecture | 10d | Correctness before expensive campaign |
| **Workload** | rl_large_parallel production | 6d | BG-PBT showcase |
| **Validation** | V08 campaign | 10d | 3-rep pilot, analysis, report |
| **Total** | | **70d** | Option A approved |


### Phasing (internal to Tier 2)

**Phase 2A: TuRBO prerequisite (weeks 1-3)**
- Mixed-space TuRBO implementation and tests
- No BG-PBT work begins until TuRBO complete (dependency per roadmap)

**Phase 2B: Population core (weeks 4-9)**
- PB2, PB2-Mix, BG-PBT with or without architecture support
- Parallelize: population logic + architecture contracts (if in scope)

**Phase 2C: Workload and validation (weeks 10-14+)**
- rl_large_parallel production build
- V08 campaign (expensive, needs full population stack)

### Tier 2 gate: V08

**Campaign cost estimate:**
- V08 (3-rep pilot): 3 reps × 3 arms × 2 sides × 8 workers × full runs
- If 1 full run = 2 accel-hours, and side is ~32 full-run-equivalents in budget:
  - 3 × 3 × 2 × (32 equiv = 256 accel-hours per arm-rep) = ~4,600 accel-hours
- **Total: ~4,600 accel-hours (~27 accel-days, ~1 GPU-week for pilot)**
- Full sequential campaign (if pilot inconclusive): up to ~15,000 accel-hours (~3 GPU-weeks)

**Wall-clock with 16 GPUs:** ~12 days for pilot, ~40 days for full if needed

### Exit criteria for Tier 2

- [ ] TuRBO mixed-space implementation complete with tests
- [ ] BG-PBT population line complete (with or without architecture support)
- [ ] Architecture contracts and distillation (Option A approved)
- [ ] rl_large_parallel production-ready
- [ ] V08 validation complete (may be hold/demote/pass per protocol)
- [ ] Gate report with recommendation (promote to default, keep as option, or demote)

---

## Distributed Beta Hardening (NEW, MANDATORY)

**Duration:** 4-5 weeks (calendar)  
**Effort:** ~35 engineer-days  
**Rationale:** Operational correctness is not optional (Codex B7, B8)

This gate sits between Tier 2 validation and internal beta launch.

### Scope

| Component | Effort | Deliverable |
|-----------|--------|-------------|
| **Persistent store** | 5d | Serialized SQLite writer (local) OR Postgres (cluster) with transactions |
| **Coordinator recovery** | 4d | Crash and restart without duplicate observations or budget debit |
| **Idempotent events** | 3d | Observation, promotion, stop, checkpoint registration idempotent |
| **Monitoring** | 4d | Study stalls, trial failures, budget overrun alerts |
| **Hard budget controls** | 3d | Study-level and trial-level measured usage enforcement |
| **Fault tests** | 5d | Worker loss, preemption, duplicate/late events, corrupt checkpoint |
| **Scale tests** | 3d | Proposal latency, event throughput, concurrent trials at target load |
| **Artifact retention** | 2d | Checkpoint GC policy, backup/restore |
| **Security review** | 3d | Path handling, deserialization, secrets, resource exhaustion |
| **Runbook** | 3d | User guide, operations manual, support ownership |
| **Total** | **35d** | |

### Exit criteria for Distributed Beta

- [ ] Persistent store with crash recovery proven
- [ ] Monitoring and alerts deployed
- [ ] Hard budget controls enforced (trials stop when limit reached)
- [ ] Fault injection tests pass (worker loss, preemption, duplicates)
- [ ] Scale test meets SLOs (proposal <1s p95, 100+ concurrent trials)
- [ ] Security review complete with mitigations implemented
- [ ] Runbook complete, support owner assigned

**This gate is MANDATORY before internal beta. Kubernetes/REST remain optional.**

---

## Tier 3: Electives (POST week-35)

**Duration:** Per-item, independent decisions  
**Effort:** ~15-20 engineer-days per item  
**Rationale:** Each has go/no-go gate based on feasibility or demand

### Tier 3 items (from roadmap, deferred past Tier 2)

**DEHB reimplementation (V07):**
- Reimpl against owned interfaces, NOT vendor wrap
- ~10d implementation + 5d validation campaign
- V07: DEHB vs BO+ASHA at 16-run budget on RL
- Decision: If V07 shows no winner or DEHB loses, skip; if DEHB wins, ship

**ifBO curve model adoption (V15):**
- Split into V15a (feasibility) and V15b (integration)
- V15a: Published pretrained ifBO model matches/beats ASHA (~3d test)
- If V15a passes: V15b integration (~8d) + parity tests (~3d)
- If V15a fails: CANCEL, do not integrate

**HEBO-style robustness:**
- Warping and ensembles on GP (~8d)
- Validation: beats base GP on messy objectives (~5d campaign)
- Decision: If no projects have "messy" objectives, defer

**CMA-ES wrapper:**
- Low priority, Hamiltonian-only regime
- ~2d wrap + 2d validation
- Decision: If Hamiltonian users request, ship; otherwise skip

---

## Summary timeline (all phases)

| Phase | Calendar weeks | Engineer-days | Accelerator-hours | Wall-clock (campaigns) |
|-------|----------------|---------------|-------------------|----------------------|
| **R0 (spec)** | 2 | 10.5 | 0 | 0 |
| **R1 (spike)** | 3 | 25 | 0 | 0 |
| **Tier 0** | 8-10 | 65 | 2,500 | ~4 days (4 GPUs) |
| **Tier 1** | 8-10 | 70 | 10,900 | ~8 days (8 GPUs) |
| **Tier 2** | 14-18 | 70 (NAS) / 54 (no NAS) | 4,600-19,600 | ~12-40 days (16 GPUs) |
| **Dist. beta** | 4-5 | 35 | 0 | 0 |
| **Tier 3 (per item)** | 2-4 each | 15-20 each | ~2,000 each | ~3 days each |
| **TOTAL to internal beta** | **39-48 weeks** | **275-310 days** | **17,000-33,000** | **~24-52 days campaigns** |

**With 2 engineers average:** ~140-155 engineer-weeks → ~35-39 calendar months at realistic utilization

**Realistic calendar estimate: 39-48 weeks (9-11 months) from R0 start to internal beta launch**

This assumes:
- 2 engineers through Tier 0-1
- 2-3 engineers for Tier 2 (population + architecture if in scope)
- 1 engineer for distributed hardening
- Parallelism where possible
- 25-30% contingency for integration, reviews, rework

---

## Contingency and risk buffers

**Built-in contingencies:**
- 25% integration overhead (implementations don't compose perfectly first try)
- 15% operational overhead (reviews, meetings, documentation, onboarding)
- Pilot campaigns before full campaigns (can adjust based on variance)
- Inconclusive state in validation (no forced binary decisions)

**Risk buffers not included:**
- Dependency breakage (Optuna, BoTorch, Ray API changes)
- Hardware availability (assume target GPU count available)
- Staff turnover (assume continuity)
- Scope creep (assume R0 scope holds)

**If risks materialize, add:**
- Dependency breakage: +2-4 weeks per major update
- Reduced GPU availability: campaigns take proportionally longer
- Staff turnover: +4-8 weeks onboarding + knowledge transfer
- Scope additions: rebaseline entirely

---

## Next steps

1. **Complete R0** (current phase)
2. **Finalize with traceability matrix** (agent in progress)
3. **Review with statistical reviewer** (blocking)
4. **Generate BUILD_PROGRAM_v2** (incorporates this timeline)
5. **Approval for R1 spike** (after R0 complete)

---

## Status

**Document status:** DRAFT  
**Awaiting:** Traceability matrix completion, statistical reviewer assignment, NAS scope decision  
**Confidence:** Medium-high (based on corrected scope, but still estimates until R1 spike validates)

This timeline will be refined after R1 spike provides real implementation data.
