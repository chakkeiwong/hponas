# HPO Tuner Build Program v2.0

**Generated:** 2026-09-01
**Sources:** hpo-survey-decisions.json, WORK_BREAKDOWN_TIMELINE_DRAFT.md, BUILD_PROGRAM_RECONCILIATION_COMPLETE.md
**Status:** APPROVED
**Repo:** `/home/ubuntu/workspace/hponas`

> **IMPORTANT:** This is a generated document. To modify the program, edit the source files and regenerate.
> Manual edits to this file will be overwritten. See [governance.md](governance.md) for details.

---

## Executive Summary

Three-tier build with gates at end of Tier 0, Tier 1, and Tier 2, plus mandatory Distributed Beta hardening before internal beta launch. Each gate runs a validation campaign; pass advances, fail triggers registered demotion rules.

**Phases:**
- **R0 (complete):** Specification correction (2 days actual, 8 statistical corrections applied)
- **R1 (complete):** Executable spike (3 weeks, interfaces frozen, gate PASS)
- **Tier 0:** Foundation—wrap audited components, wire database, build GP+qLogEI (~65 engineer-days)
- **Tier 1:** Method differentiators—MO stack, priors, cost-aware acquisition (~70 engineer-days)
- **Tier 2:** Population flagship—TuRBO, BG-PBT, architecture support (70 engineer-days)
- **Distributed Beta:** Hardening—persistent store, crash recovery, monitoring, security (~35 engineer-days)
- **Tier 3:** Electives—post-beta features gated individually (DEHB reimpl, ifBO curve model)

**Total to internal beta:** 39-48 weeks, 275-310 engineer-days, 17k-33k accelerator-hours (see Summary Timeline below)

**Budget:** ~275-310 engineer-days + ~17k-33k accelerator-hours (campaigns). **Risk mitigation:** tier gates enforce fail-early; demotion rules pre-committed; alternatives named for every load-bearing bet.

**Approval:** See [BUILD_PROGRAM_v2_APPROVAL.md](BUILD_PROGRAM_v2_APPROVAL.md)

---

## Phase R0: Specification Correction (COMPLETE)

**Duration:** 2 weeks (calendar)
**Effort:** ~5 engineer-days (spread across multiple people)
**Status:** ✅ Complete (2026-08-28)
**Report:** [R0_COMPLETION_REPORT.md](R0_COMPLETION_REPORT.md)

### Deliverables
- All 8 statistical corrections applied to survey Chapter 16
- NAS scope decided (Option A: moderate architecture coordinates, +16 eng-days)
- Architecture factory contract written (Ch 15 `sec:archfactory`)
- Traceability matrix: 63 decisions with tier/validation mappings
- `product_register.json`: 48 in-scope entries
- Survey builds clean at 118 pages

### Exit criteria
- [x] All corrections reviewed and committed
- [x] Traceability matrix complete
- [x] NAS scope decision made
- [ ] Statistical reviewer verification (deferred, non-blocking)

---

## Phase R1: Executable Architecture Spike (COMPLETE)

**Duration:** 3 weeks (calendar, was 2 in plan)
**Effort:** 27 engineer-days
**Status:** ✅ Complete — gate PASS (2026-08-31)
**Gate report:** [gate_reports/r1_gate_2026-08-31.md](gate_reports/r1_gate_2026-08-31.md)
**Interface review:** [docs/SPIKE_REVIEW.md](docs/SPIKE_REVIEW.md)

### Deliverables
- Minimal SearchSpace, SobolSearcher, ASHAScheduler
- LocalExecutor (in-process), RayExecutor (stub—real Ray Tune deferred to Tier 0)
- Store with crash recovery (SQLite + WAL)
- Architecture factory stubs
- Searcher state serialization contract (`state_dict`/`load_state_dict`)
- Test suite: 56 tests, 93% coverage
- Examples: spike_branin.py, spike_crash_recovery.py

### Exit criteria
- [x] End-to-end study runs on local executor
- [x] Crash recovery without duplicate configs
- [x] Foundational test suite passes (56 tests, 93%)
- [x] Architecture factory stubs enforce compatibility
- [x] Interface review signed off
- [x] Gate PASS

### Findings resolved
1. **Sobol state serialization bug** — fixed by adding state_dict/load_state_dict to Searcher protocol
2. **RayExecutor stub** — accepted as known limitation per charter

---

## Tier 0: Foundation

**Duration:** 8-10 weeks (calendar, was 4 weeks in rejected plan)
**Effort:** ~65 engineer-days
**Rationale:** Must include GP+qLogEI, both executors, real rl_routine per survey

### Scope

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **Searchers** | Refine Sobol/Random, TPE wrapper, GP+qLogEI+priors | 15d | GP is core build (~8d) |
| **Schedulers** | Refine ASHA, Median, PASHA | 7d | ASHA mostly done in R1 |
| **Executors** | Refine Ray/local, RLlib integration | 8d | Checkpoint surgery non-trivial |
| **Store** | Diagnostics, fronts, artifact tracking | 3d | Extends R1 foundation |
| **Workload** | rl_routine production build | 8d | Real PPO/Brax day-one walk |
| **Tests** | Contract/property/migration/mutation | 10d | Foundation for all tiers |
| **Validation** | Task sizing, V01-V05/V14, runner | 14d | Corrected protocols |
| **Total** |

### Gate: V01-V05, V14, V04-T0

**Validation entries:**

- **V01:** implementation parity
- **V02:** async correctness
- **V03:** sabotage detection
- **V04 (T0 component):** Week 6: "TPE and log+Sobol GP must beat random baseline"
- **V05:** log-warping effectiveness
- **V14:** day-one walk reproduction

**Campaign cost estimate:** ~2,500 accelerator-hours (~15 accel-days, ~0.5 GPU-week)

**Demotion rules:**
- If wrapped implementations fail parity (V01): block tier-1, diagnose wiring
- If log-warping shows no benefit (V05): demote to opt-in feature
- If tier-0 searchers fail to beat random (V04-T0): identify and fix before proceeding

### Exit criteria
- [ ] All T0 searchers/schedulers implemented with unit tests
- [ ] Both executors pass conformance suite
- [ ] rl_routine template production-ready
- [ ] V01-V05, V14, V04-T0 validation complete
- [ ] Gate report with results and demotion decisions
- [ ] No blockers

**Decisions mapped to Tier 0:** 14 capabilities from traceability matrix

---

## Tier 0 Remediation (BLOCKING)

**Context:** Tier 0 gate report (2026-09-02) recorded GATE NOT MET after withdrawing an
earlier false CONDITIONAL PASS. V14 was a vacuous pass (zero trials executed, validator
checked only `999 not in SELECT seed FROM trials` on an empty table), V01 was
tautological (scipy compared to scipy), V04-T0 threshold was tuned post-hoc (10%→5%),
and V02/V03 were never implemented. This remediation block is the actual Tier 0 exit.

**Duration:** 2-3 weeks  
**Effort:** ~18 engineer-days

### Scope

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **Dependencies** | Install jax/brax for rl_routine, or declare substitute workload | 0.5d | Unblocks V14, V04-T0, V05 |
| **V01 completion** | Run TPE vs Optuna, GP vs BoTorch parity | 1d | Current V01 is Sobol-vs-scipy (tautological) |
| **V02 implementation** | State-machine replay: out-of-order/duplicate/late/dropped events | 3d | Property tests exist but replay harness doesn't |
| **V03 implementation** | Mutation testing with ≥0.9 kill score | 3d | Never started |
| **V04-T0 re-run** | TPE and GP vs random+log-Sobol floor, fixed threshold | 2d | Current run tuned threshold mid-campaign |
| **V05 re-run** | Log-warping on acceptance task (not synthetic Gaussian in log-space) | 1d | Current result is informative but not conclusive |
| **V14 re-run** | Day-one walk with real rl_routine execution | 0.5d | After dependencies resolved |
| **Test repair** | Fix 6 broken R1 tests (RayExecutor AttributeError, spike/capability mismatches) | 2d | Tests never re-run after Tier 0 changes |
| **Validator audit** | V16: non-vacuous validator enforcement | 2d | New protocol (see below) |
| **Gate report** | Honest Tier 0 gate verdict with corrected protocols | 1d | No tuning, no vacuous passes |
| **Program sync** | Update this document with actual completion state | 1d | Remove "Tier 0 complete" claims |
| **Total** | | ~17d | |

### V16: Validator Audit Protocol (NEW)

**Claim:** Validators detect the failure modes they exist to catch; they cannot pass vacuously.

**Pass rule:** All validators in the active tier pass the audit criteria below.

**Criteria:**

1. **Non-vacuity:** Every validator must fail when given structurally empty input:
   - Performance validators: fail on zero trials
   - Parity validators: fail when reference and implementation produce zero samples
   - Property validators: fail when zero events are replayed
   - Mutation validators: fail when zero mutants are generated

2. **No post-hoc tuning:** Performance validators (V04, V05, V06, V09, V10) must record
   their threshold/hypothesis **before** the campaign runs. Lowering a threshold or
   changing an objective after seeing results is forbidden and causes FAIL.

3. **Correct reference:** Parity validators (V01) must compare the wrapped implementation
   against the declared vendor reference (TPE→Optuna, GP→BoTorch), not against itself.

4. **Runnable independently:** `python validation/vXX_*.py` must execute the full protocol
   and report PASS/FAIL without requiring manual setup beyond installing dependencies
   declared in the validator's docstring.

**Implementation:** Each validator gets a `--audit` mode that:
- Runs the validator on deliberately empty input and asserts it returns FAIL
- Checks that thresholds are read from a committed file, not computed in the script
- Verifies reference implementations are imported from external packages

**Gate assignment:** V16 runs at every gate starting with Tier 0 remediation. A validator
that passes V16 can be trusted; one that doesn't is presumed vacuous until fixed.

### Gate: V01-V05, V14, V04-T0, V16

Same as original Tier 0 gate (line 107) plus V16 (validator audit).

### Exit criteria
- [ ] jax/brax installed OR substitute workload declared and V14/V04-T0/V05 re-scoped
- [ ] V01 run against Optuna (TPE) and BoTorch (GP), not scipy (tautological)
- [ ] V02 state-machine replay implemented, scheduler property tests passing
- [ ] V03 mutation testing implemented with ≥0.9 kill score
- [ ] V04-T0 re-run with fixed threshold, on real workload, TPE+GP vs floor
- [ ] V05 re-run on acceptance task (not synthetic)
- [ ] V14 re-run with non-zero trials executed
- [ ] 6 broken R1 tests fixed (full suite ≥109 passed)
- [ ] V16 audit: all T0 validators pass non-vacuity/no-tuning/correct-reference checks
- [ ] Gate report with honest verdict (no conditional passes)
- [ ] BUILD_PROGRAM_v2.md synchronized with actual state

**Blocking dependency for Tier 1:** This remediation block must complete before Tier 1
work begins. Tier 1 MO/prior/cost-aware work is built on top of Tier 0 searchers and
executors; if those aren't validated, Tier 1 results are meaningless.

---

## Tier 1: Method Differentiators

**Duration:** 8-10 weeks (calendar, was 6 in rejected plan)
**Effort:** ~70 engineer-days
**Rationale:** Must include full MO stack, EI-per-cost, correct piBO/PriorBand implementations

### Scope

| Category | Tasks | Effort | Notes |
|----------|-------|--------|-------|
| **MO stack** | qLogNEHVI, Chebyshev, NSGA-II, reporting, MO-ASHA | 16d | Complete fallback path |
| **Priors** | Correct πBO, correct PriorBand, nonzero guard, warm-start | 13d | Faithful implementations |
| **Cost-aware** | EI-per-cost, predictive cost model | 7d | Was missing entirely |
| **Workloads** | hamiltonian_mo, sampler_neutra, finance (cond.) | 15d | Production-ready with examples |
| **Tests** | MO veto, prior recovery, cost model | 7d | Correctness before campaigns |
| **Validation** | V04-T1, V06, V09-V11, V13 campaigns | 12d | Moved V06/V10/V13 from T2 per survey |
| **Total** |

### Gate: V04-T1, V06, V09-V11, V13

**Validation entries:**

- **V04 (T1 component):** Week 12: "TuRBO and prior-aware qLogEI beat log+Sobol floor"
- **V06:** ASHA reaches full-fidelity quality at ≤1/3 compute
- **V09:** qLogNEHVI beats scalarization or ties and gets demoted
- **V10:** drift-at-rung correlates with drift-at-end, ρ > 0.6 lower bound
- **V11:** priors help under good advice, recover under wrong advice
- **V13:** no veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior

**Campaign cost estimate:** ~10,900 accelerator-hours (~65 accel-days, ~2.3 GPU-weeks)

**Demotion rules:**
- qLogNEHVI failure (V09): demote to tier-2 option, Hamiltonian defaults to scalarization
- TuRBO failure (V04-T1): defer population line (BG-PBT depends on TR), reassess tier-2 scope
- Prior failure (V11): demote πBO/PriorBand to opt-in

### Exit criteria
- [ ] Complete MO stack with fallback paths
- [ ] Correct πBO and PriorBand implementations
- [ ] EI-per-cost with predictive cost model
- [ ] Production workload templates for all in-scope domains
- [ ] V04-T1, V06, V09-V11, V13 validation complete
- [ ] Gate report with demotion decisions

**Decisions mapped to Tier 1:** 16 capabilities from traceability matrix

---

## Tier 2: Population Line

**Duration:** 14-18 weeks (calendar, was 18 in rejected plan but poorly phased)
**Effort:** 70 engineer-days
**Rationale:** Must include mixed-space TuRBO first (T2 prerequisite per roadmap), then architecture support if NAS in scope

### Scope

**Prerequisites (must complete first):**
- Mixed-space TuRBO (~10d) — moved from T1, is T2 prerequisite per roadmap

**Population methods:**
- PB2, PB2-Mix, BG-PBT population manager

**Architecture support (Option A approved 2026-08-28):**
- Architecture factory, compatibility policy, distillation protocol
- Architecture proposal, measured objectives

**Tests:** TuRBO mixed-space, population checkpoint compatibility, distillation correctness

**Workload:** rl_large_parallel production build

### Gate: V08

**Validation entries:**

- **V08:** BG-PBT does not lose in home regime: above 8 workers vs DEHB and BO+ASHA; 3-rep exception with asymmetric demotion rule

**Campaign cost estimate:** ~4,600-19,600 accelerator-hours (pilot to full)

**Demotion rules:**
- BG-PBT consistent home loss (V08): demote to option, rl_large_parallel defaults to DEHB

### Exit criteria
- [ ] TuRBO mixed-space implementation complete
- [ ] BG-PBT population line complete with architecture support
- [ ] rl_large_parallel production-ready
- [ ] V08 validation complete (may be hold/demote/pass)
- [ ] Gate report with recommendation

**Decisions mapped to Tier 2:** 3 capabilities from traceability matrix

---

## Distributed Beta Hardening (MANDATORY)

**Duration:** 4-5 weeks (calendar)
**Effort:** ~35 engineer-days
**Rationale:** Operational correctness is not optional (Codex B7, B8)

This gate sits between Tier 2 validation and internal beta launch.

### Scope
- Persistent store (serialized SQLite writer or Postgres with transactions)
- Coordinator recovery (crash and restart without duplicates or budget debit)
- Idempotent events (observation, promotion, stop, checkpoint registration)
- Monitoring (study stalls, trial failures, budget overrun alerts)
- Hard budget controls (study-level and trial-level measured usage enforcement)
- Fault tests (worker loss, preemption, duplicate/late events, corrupt checkpoint)
- Scale tests (proposal latency, event throughput, concurrent trials at target load)
- Artifact retention (checkpoint GC policy, backup/restore)
- Security review (path handling, deserialization, secrets, resource exhaustion)
- Runbook (user guide, operations manual, support ownership)

### Validation entries

- **V12:** warm start saves ≥20% trials

### Exit criteria
- [ ] Persistent store with crash recovery proven
- [ ] V12 warm-start savings validated
- [ ] Monitoring and alerts deployed
- [ ] Hard budget controls enforced
- [ ] Fault injection tests pass
- [ ] Scale test meets SLOs (proposal <1s p95, 100+ concurrent trials)
- [ ] Security review complete
- [ ] Runbook complete, support owner assigned

**This gate is MANDATORY before internal beta. Kubernetes/REST remain optional.**

---

## Tier 3: Electives (post-internal-beta)

**Duration:** Per-item, independent decisions
**Effort:** ~15-20 engineer-days per item

Each has go/no-go gate based on feasibility or demand:

1. **DEHB reimplementation (V07):** Reimpl against owned interfaces, NOT vendor wrap (~10d impl + 5d validation)
2. **ifBO curve model adoption (V15):** Split into V15a (feasibility) and V15b (integration); cancel if V15a fails
3. **HEBO-style robustness:** Warping and ensembles on GP (~8d + 5d campaign); defer if no messy objectives
4. **CMA-ES wrapper:** Low priority, Hamiltonian-only (~2d wrap + 2d validation); ship if users request

**Decisions mapped to Tier 3:** 5 capabilities from traceability matrix

---

## Summary Timeline

| Phase | Calendar weeks | Engineer-days | Accelerator-hours | Status |
|-------|----------------|---------------|-------------------|--------|
| R0 (spec) | 2 | 10.5 | 0 | ✅ Complete |
| R1 (spike) | 3 | 27 | 0 | ✅ Complete, gate PASS |
| Tier 0 | 8-10 | 65 | 2,500 | ⛔ Blocked on program approval |
| Tier 1 | 8-10 | 70 | 10,900 | ⛔ Blocked on Tier 0 gate |
| Tier 2 | 14-18 | 70 | 4,600-19,600 | ⛔ Blocked on Tier 1 gate |
| Dist. beta | 4-5 | 35 | 0 | ⛔ Blocked on Tier 2 gate |
| Tier 3 (per item) | 2-4 each | 15-20 each | ~2,000 each | ⛔ Post-internal-beta |
| **TOTAL to beta** | **39-48 weeks** | **275-310 days** | **17k-33k** | |

**With 2 engineers average:** ~140-155 engineer-weeks → ~35-39 calendar months at realistic utilization

**Realistic calendar: 39-48 weeks (9-11 months) from R0 start to internal beta launch**

Assumes:
- 2 engineers through Tier 0-1
- 2-3 engineers for Tier 2 (population + architecture)
- 1 engineer for distributed hardening
- Parallelism where possible
- 25-30% contingency for integration, reviews, rework

---

## Validation Register

Complete test suite V01-V15:

### V01

**Claim:** each wrapped searcher/scheduler matches its reference implementation on tabular benchmarks

**Pass rule:** final and anytime scores within tolerance of reference

**Gate criteria:** V01 (implementation parity)

**Program gate:** Tier 0 gate

**Survey gate:** T0

### V02

**Claim:** scheduler logic is correct under asynchrony

**Pass rule:** replayed decisions on recorded curves match specification; stragglers and drops simulated

**Gate criteria:** V02 (async correctness)

**Program gate:** Tier 0 gate

**Survey gate:** T0

### V03

**Claim:** the suite itself catches wiring bugs

**Pass rule:** seeded defects (off-by-one rung, dropped seed, swapped objective sign) are caught by V01–V02

**Gate criteria:** V03 (sabotage detection)

**Program gate:** Tier 0 gate

**Survey gate:** T0

### V04

**Claim:** every shipped searcher earns its complexity

**Pass rule:** beats the log+Sobol floor at matched budget on pinned tasks, each searcher tested at the gate of the tier that ships it

**Gate criteria:** Week 6: "TPE and log+Sobol GP must beat random baseline"; Week 12: "TuRBO and prior-aware qLogEI beat log+Sobol floor"

**Program gate:** Tier 0 gate + Tier 1 gate

**Survey gate:** T0/T1

### V05

**Claim:** the transform matters as claimed

**Pass rule:** GP with and without log-warping on a pinned task; warped must not lose

**Gate criteria:** V05 (log-warping effectiveness)

**Program gate:** Tier 0 gate

**Survey gate:** T0

### V06

**Claim:** early stopping is nearly free

**Pass rule:** searcher+ASHA matches searcher-at-full-fidelity final quality within noise at a fraction of compute

**Gate criteria:** V06 (ASHA reaches full-fidelity quality at ≤1/3 compute)

**Program gate:** Tier 1 gate

**Survey gate:** T1

### V07

**Claim:** the small-budget RL verdict holds here

**Pass rule:** DEHB vs BO+ASHA at matched 16-run budget on the pinned RL task

**Gate criteria:** V07 (DEHB or BO+ASHA wins at 16-run routine budget)

**Program gate:** Tier 3 (per-item, post-beta)

**Survey gate:** T3

### V08

**Claim:** the population line does not lose in its home regime

**Pass rule:** population line vs DEHB and BO+ASHA on both sides of the eight-worker line at matched compute; 3 reps/arm/side (declared exception)

**Gate criteria:** V08 (BG-PBT does not lose in home regime: above 8 workers vs DEHB and BO+ASHA; 3-rep exception with asymmetric demotion rule)

**Program gate:** Tier 2 gate

**Survey gate:** T2

### V09

**Claim:** the premium MO searcher earns its tier

**Pass rule:** qLogNEHVI vs random-weight Chebyshev and wrapped NSGA-II on the Hamiltonian task; hypervolume with uncertainty; demote to option on a tie

**Gate criteria:** V09 (qLogNEHVI beats scalarization or ties and gets demoted)

**Program gate:** Tier 1 gate

**Survey gate:** T1

### V10

**Claim:** cheap MO fidelity signals may cull

**Pass rule:** short-horizon drift passes the rank-correlation pilot before MO-ASHA may kill on it

**Gate criteria:** V10 (drift-at-rung correlates with drift-at-end, ρ > 0.6 lower bound)

**Program gate:** Tier 1 gate

**Survey gate:** T1

### V11

**Claim:** priors are safe to default-on

**Pass rule:** no-prior vs folklore-prior vs wrong-prior runs; gains under good, recovery within noise under wrong, else demote to opt-in

**Gate criteria:** V11 (priors help under good advice, recover under wrong advice)

**Program gate:** Tier 1 gate

**Survey gate:** T1

### V12

**Claim:** warm starts pay

**Pass rule:** measured trial savings on a new study of a familiar family once the store holds enough studies

**Gate criteria:** V12 (warm start saves ≥20% trials)

**Program gate:** Distributed Beta gate

**Survey gate:** T1+

### V13

**Claim:** sampler correctness cannot be bought by speed

**Pass rule:** veto-failing configurations never promoted; survivors ranked by ESS/gradient; pilot agreement with the reference posterior

**Gate criteria:** V13 (no veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior)

**Program gate:** Tier 1 gate

**Survey gate:** T1

### V14

**Claim:** tier 0 is composition, not construction

**Pass rule:** the day-one walk of Chapter 15 reproduced end to end within the tier-0 budget

**Gate criteria:** V14 (day-one walk reproduction)

**Program gate:** Tier 0 gate

**Survey gate:** T0

### V15

**Claim:** the curve-model bet is live before we pay for it

**Pass rule:** ifBO matches or beats ASHA on the curve-informative public suites before any integration work

**Gate criteria:** V15 (ifBO matches ASHA at half compute on curve-informative benchmarks)

**Program gate:** Tier 3 (per-item, post-beta)

**Survey gate:** T3

### V16

**Claim:** validators detect the failure modes they exist to catch; they cannot pass vacuously

**Pass rule:** all validators pass non-vacuity, no-tuning, and reference-correctness audits

**Gate criteria:** V16 (validator audit)

**Program gate:** Tier 0 Remediation

**Survey gate:** meta-validation

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation | Tripwire |
|------|-----------|--------|------------|----------|
| BG-PBT fails V08 boundary trial | Medium | High (flagship demoted) | Demotion rule pre-committed; fallback is DEHB | Week 22: if informal tests show <50% win rate, flag early |
| Trust-region BO unstable on mixed spaces | Low | High (blocks PB2-Mix, BG-PBT explore) | BoTorch TuRBO production-tested; our adaptation is thin | Week 9: if V04 shows high variance, add restart logic |
| ASHA rank correlations fail on real RL tasks | Low | High (tier-0 floor collapses) | Chapter 5 evidence shows 0.7+ correlation typical | Week 10: pilot V06 early; if <0.5, revisit fidelity definition |
| Validation campaigns blocked by Brax env install | Low | Medium (delays gates) | Install Brax at Tier 0 start, not week 12 | Week 7: test `import brax` and run one episode |
| Store schema needs migration mid-build | Medium | Low (1-2d disruption) | Design with extensibility (JSON blob for method-specific metadata) | Any week: if schema change needed, write migration and re-seed test data |

---

## Traceability: Decisions → Tiers

### T0

- **roadmap-01:** Sobol + log sampling (validation: V04, V05)
- **roadmap-02:** Random-search baseline (validation: V04)
- **roadmap-03:** ASHA + median rule (validation: V06)
- **roadmap-04:** TPE (wrap Optuna) (validation: V01, V04)
- **roadmap-05:** GP + qLogEI (BoTorch) (validation: V01, V04)
- **roadmap-06:** Dimension-scaled priors (validation: V04)
- **ch03-01:** Log-scale and Sobol sampling (validation: V04, V05)
- **ch03-02:** Random search (validation: V04)
- **ch03-04:** CMA-ES (validation: V01, V04)
- **ch04-01:** GP searcher with qLogEI on BoTorch (validation: V01, V04)
- **ch04-02:** TPE by wrapping Optuna (validation: V01, V04)
- **ch04-05:** Dimension-scaled lengthscale priors (validation: V04)
- **ch05-01:** ASHA plus the median stopping rule (validation: V02, V06)
- **ch05-05:** PASHA (validation: V02)

### T1

- **roadmap-07:** qLogNEHVI (validation: V09)
- **roadmap-08:** Chebyshev scalarization (validation: V09)
- **roadmap-09:** MO-ASHA + veto gates (validation: V10, V13)
- **roadmap-10:** πBO + PriorBand (validation: V11)
- **roadmap-11:** Warm start from run store (validation: V12)
- **roadmap-12:** EI-per-cost + cooling (validation: V04)
- **ch04-06:** Trust-region searcher with mixed-space kernels (validation: V04, V08)
- **ch06-01:** PBT (validation: V02)
- **ch07-01:** qLogNEHVI on BoTorch (validation: V09)
- **ch07-02:** Chebyshev scalarization with random weights (validation: V09)
- **ch07-04:** NSGA-II by wrapping Optuna (validation: V09)
- **ch07-05:** MO-ASHA with veto gates (validation: V10, V13)
- **ch08-01:** πBO's prior-weighted acquisition (validation: V11)
- **ch08-02:** PriorBand (validation: V11)
- **ch08-03:** Warm starts from the run store (validation: V12)
- **ch08-06:** EI-per-cost with cost cooling (validation: V04)

### T2

- **roadmap-13:** PB2-Mix, then BG-PBT (validation: V08)
- **ch06-02:** PB2 extended to mixed spaces (validation: V08)
- **ch06-03:** BG-PBT (validation: V08)

### T3

- **roadmap-14:** DEHB (validation: V07)
- **roadmap-15:** ifBO scheduler (validation: V15)
- **roadmap-16:** HEBO-style robustness (validation: V04)
- **ch05-04:** DEHB, implemented against our interfaces (validation: V07)
- **ch05-06:** Learning-curve scheduling, specifically ifBO (validation: V15)

---

## How to Use This Program

1. **Current phase:** Check Summary Timeline for current blocking phase
2. **Next gate:** Review gate criteria and validation entries
3. **Task tracking:** Use `tools/generate_tasks.py --phase tierX` to generate work breakdown
4. **Progress:** Check `docs/progress.md` (auto-generated from ground truth)
5. **Amendments:** Changes produce v2.1, v2.2 with explicit deltas—see [governance.md](governance.md)

**Live tracking:** Run `python3 tools/update_progress.py` weekly to regenerate progress from ground truth.

---

## Program Amendments

| Version | Date | Changes | Approved by |
|---------|------|---------|-------------|
| v2.0 | 2026-09-01 | Initial generated version | [BUILD_PROGRAM_v2_APPROVAL.md](BUILD_PROGRAM_v2_APPROVAL.md) |

_Future amendments will be logged here with explicit deltas._

---

**For questions or scope changes, see:**
- Survey Chapter 15 (build plan detail)
- Survey Chapter 14 (validation suite specification)
- [governance.md](governance.md) (change control process)
