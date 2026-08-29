# Response to Codex Technical Review
**Date:** 2026-08-28  
**Review verdict:** RED - do not approve as written  
**Response author:** Implementation team  
**Status:** Acknowledged; corrective action plan proposed

---

## Executive response

We accept the RED verdict and will not proceed with Phase 0 interface freeze or Tier 0 execution under the current BUILD_PROGRAM. The review identifies fundamental gaps in scope definition, timeline arithmetic, test strategy, and faithfulness to governing specifications that would lead to prototype collection rather than production system.

We propose the **corrective specification and architecture-spike phase** recommended in the review's final section, with the following commitments:

1. **Specification correction first** (R0): Repair LaTeX validation statistics, reconcile survey vs BUILD_PROGRAM scope mismatches, decide NAS boundary, fix timeline arithmetic
2. **Executable spike before freeze** (R1): Build minimal vertical slice with both executors, prove crash recovery, validate interfaces against real failures
3. **Rebaselined tiers** (T0-T3): Match governing LaTeX exactly, add missing test layers, defer Tier 3 past week 30
4. **Mandatory hardening gate**: Distributed reliability, monitoring, hard budget controls required before internal beta, not optional post-ship

We will produce a revised BUILD_PROGRAM_v2 after completing R0+R1, with reconciled effort, calendar, and scope. Estimated timeline for corrective phase: 3-4 weeks before Tier 0 can validly begin.

---

## Blocking findings: acknowledgment and proposed corrections

### B1. Timeline/effort arithmetic (ACCEPTED)

**Finding:** 32 actual engineer-weeks listed vs 42 claimed; Tier 2 shows 18 weeks work in 18 weeks calendar but claims 30 weeks effort; "one engineer" conflicts with "1.5-2 engineers"; GPU-weeks undefined and underestimated.

**Root cause:** BUILD_PROGRAM was drafted from calendar milestones backward rather than from work-breakdown forward. Tier 3 effort (DEHB reimplementation, HEBO robustness, ifBO integration) was included in 42-week total but not scheduled.

**Correction committed:**
- Rebuild from spreadsheet with named owners, dependencies, utilization
- Separate engineer-weeks (effort), accelerator-hours (compute), calendar weeks (elapsed)
- Add 25-40% integration/operational contingency
- Remove week-6/12/30 dates until resource capacity supports them
- Defer Tier 3 items to explicit post-week-30 decision gates

**Owner:** Project lead  
**Deadline:** End of R0 phase (week 3 of corrective work)

### B2. Scope mismatches with governing LaTeX (ACCEPTED)

**Finding:** 13 material inconsistencies including: GP+qLogEI missing from Tier 0, DEHB moved from T3 to T0, TuRBO moved from T2 prerequisite into T1 bundle, πBO/PriorBand implementations differ from governing specs, EI-per-cost omitted, ifBO changed from pretrained adoption to new research.

**Root cause:** BUILD_PROGRAM was written without line-level traceability to LaTeX decision boxes. Several "simplifications" were made without recognizing they changed the method being validated.

**Correction committed:**
- Generate traceability matrix: every decision-box item → contract, implementation, tests, validation entry, tier, effort, fallback
- Flag every intentional deviation for explicit LaTeX amendment before proceeding
- Specific fixes required:
  - Restore GP+qLogEI with dimension-scaled priors to Tier 0
  - Move DEHB back to Tier 3 (reimplementation, not vendor wrap)
  - Budget mixed-space TuRBO as Tier 2 prerequisite (weeks 13-20 per roadmap)
  - Implement actual πBO decay multiplier, not GP mean substitution
  - Implement actual PriorBand rung portfolio, not top-K sampling
  - Build EI-per-cost with predictive cost model
  - Use pretrained ifBO surrogate; V15 feasibility before integration
  - Add CMA-ES, PASHA, Chebyshev, NSGA-II wrapper per register
  - Add both executor adapters (Ray + local), not just RLlib

**Owner:** Technical lead + survey author  
**Deadline:** End of R0 phase

### B3. Phase 0 contract incompleteness (ACCEPTED)

**Finding:** Phase 0 lists "YAML parser and capability flags" but governing contracts specify objective vectors, seed separation, transforms, conditions, priors, capability rejection, batch propose, veto gates, lineage, fronts, checkpoints, and executors. Engineering semantics (stable IDs, schema migration, canonical hashing, inactive conditionals, duplicate proposals, NaN handling, failure policy, idempotency, resource requests) are omitted.

**Root cause:** Phase 0 was sized as "interface design" rather than "contract validation spike."

**Correction committed:**
- Rename to R1: Executable architecture spike
- Build minimal vertical slice: one real mixed/conditional SearchSpace, Sobol, ASHA, Ray + local executors, store with crash recovery, seed-separated evaluation
- Add state-machine tests, restart tests, executor conformance tests
- Freeze interfaces only after executable failures inform stakeholders
- Budget 3-4 weeks for R1, not 2 weeks for old Phase 0

**Owner:** Implementation lead  
**Deadline:** End of R1 (before Tier 0 start)

### B4. Gate/tier misalignments (ACCEPTED)

**Finding:** Eight specific gate failures including: V14 requires real day-one walk but Tier 0 ships NotImplementedError stubs, Brax import after V14 gate, Tier 1 capabilities shipped 18 weeks before their validation gates, V09 missing NSGA-II comparator, V08 protocol incomplete, V15 post-build instead of pre-integration, success definition assumes all pass rather than allowing legitimate demotion.

**Root cause:** Gates were attached to calendar milestones rather than to capability completion. "Production-ready" was defined as "code exists" rather than "validated and deterministically tested."

**Correction committed:**
- Define gate result states: `pass`, `demote`, `block`, `unresolved`, `not_eligible`, `not_applicable`
- Nothing ships as default before deterministic tests + tier validation complete
- V06/V10/V13 moved back to Tier 1 gate (survey is authoritative)
- Build one real `rl_routine` in Tier 0 for V14
- Add NSGA-II wrapper for V09, complete V08 protocol for both sides of boundary
- Split V15: feasibility (pre-build) → decision → integration (post-build) → parity tests
- Rewrite week-30 success as: "Tier 0-2 validation complete with recorded outcomes; tier completions and demotions traced to register"

**Owner:** Validation lead  
**Deadline:** End of R0 (specification) and validated in revised T0-T2 plans

### B5. Test strategy is statistical campaigns only (ACCEPTED)

**Finding:** Work breakdown budgets 1 day for store unit tests, 1 CartPole integration test, then only statistical campaigns. No budget for contract/transform/space/state/acquisition/veto/checkpoint/cost/adapter tests. V01-V15 cannot establish thread safety, retry, persistence, replay determinism, or recovery.

**Root cause:** Treated HPO as pure method research rather than distributed systems engineering. Validation chapter (survey) focuses on method validation; BUILD_PROGRAM should have added software correctness layers but didn't.

**Correction committed:**
- Add test layers per review Table (page 217-229):
  - Contract/unit: every change
  - Property/state-machine: every change
  - Store/migration: every change, nightly
  - Adapter conformance: every change, nightly
  - Fault/chaos: nightly, release
  - Load/scale: release, capacity change
  - Reproducibility: release
  - Workload acceptance: tier gate, release
  - Dependency upgrade: every dep PR
  - Security/abuse: release
- Budget engineering time for test infrastructure (estimated +8-12 engineer-weeks across tiers)
- V01-V15 sit above correctness suite, do not replace it

**Owner:** Test infrastructure lead (assign)  
**Deadline:** Tier 0 includes foundation test layers; full suite by Tier 2 gate

### B6. BG-PBT implementation outline not faithful (ACCEPTED)

**Finding:** Program lists weight copying, TR explore, unexplained age-weighted heuristic. Survey requires architecture proposals, distillation into changed architectures, generation changes, compatibility policy. Raw checkpoint copy cannot transfer across width/depth changes. PB2-Mix dependency graph confused (continuous PB2 ≠ mixed TuRBO).

**Root cause:** BG-PBT scope minimized to fit calendar without recognizing that distillation is mechanism, not glue. NAS boundaries undefined.

**Correction committed:**
- Decide NAS scope in R0: moderate architecture-coordinate NAS (width/depth/flags) only, or out of scope
- If in scope, add to Tier 2:
  - Architecture factory contract (typed axes, validity constraints, deterministic construction)
  - Compatibility policy (when can checkpoints transfer?)
  - Distillation protocol (teacher selection, loss, schedule, rollback on failure)
  - Architecture proposal stage (how does explore step generate new architectures?)
  - Parameter/FLOP objectives as measured outputs
  - Parity tests against reference fixed-architecture PBT
- If out of scope, reduce to fixed-architecture PB2/PBT and document limitation
- Clarify PB2-Mix dependencies: does it need mixed TuRBO or reimplements continuous PB2?
- Budget distillation/architecture workstream separately (estimated +4-6 weeks if NAS in scope)

**Owner:** Population-methods lead + NAS scope decision (project lead)  
**Deadline:** NAS scope decided in R0; architecture contracts in Tier 2 (if in scope)

### B7. Large-scale execution deferred to optional post-ship (ACCEPTED)

**Finding:** SQLite + direct trial writes not credible for concurrent Ray trials; Postgres/monitoring/deployment optional; no coverage of driver death, worker loss, duplicate events, backpressure, resource policy, artifact retention, cost caps, security.

**Root cause:** Treated distributed reliability as deployment concern rather than core correctness.

**Correction committed:**
- Add mandatory "distributed internal beta" gate before week-30 ship decision
- Required before internal use:
  - Persistent store (serialized SQLite writer for local, Postgres for cluster)
  - Coordinator crash recovery with deterministic replay
  - Idempotent observation/decision/checkpoint/budget
  - Monitoring/alerts (study stalls, trial failures, budget overrun)
  - Hard budget controls (study-level, trial-level, measured usage)
  - Fault tests (worker loss, preemption, duplicate/late events)
  - Scale tests (proposal latency, event throughput, concurrent trials)
  - Artifact retention policy (checkpoint GC, backup/restore)
  - Security review (path handling, deserialization, secrets, resource exhaustion)
  - User runbook and support ownership
- Kubernetes/REST remain optional deployment choices; operational correctness mandatory

**Owner:** Infrastructure lead (assign)  
**Deadline:** Distributed beta gate between Tier 2 validation and internal launch

### B8. Package/environment not reproducible (ACCEPTED)

**Finding:** No pyproject.toml, lock file, CI, lint/type policy; .git directory empty; RLlib extra missing; Brax/DEHB/benchmarks absent; only Ray pinned; no migration/test dependencies.

**Root cause:** Treated as research prototype rather than production package.

**Correction committed:**
- Add immediately (R0/R1):
  - pyproject.toml with package metadata, entry points, dependencies
  - Lock files for CPU and target CUDA profiles (conda-lock or pip-tools)
  - CI workflow (lint, type check, unit tests, smoke study)
  - Git repository initialization with commit provenance
- Add to environment:
  - ray[tune,rllib] (not just ray[tune])
  - Brax, YAHPO-Gym, HPOBench, ARLBench, replay fixtures
  - Pin all dependencies with tested upper bounds (not just Ray)
  - Property test, benchmark, migration, database dependencies
- Record versions in study provenance: package, commit, environment digest, hardware
- Make clean-machine install + smoke study a CI/release requirement

**Owner:** DevOps lead (assign)  
**Deadline:** End of R1 (executable spike must install cleanly)

### B9. Workload coverage mismatch (ACCEPTED)

**Finding:** Finance listed as target but has no template, task, or validation; product_register.json collapses all workload decisions into one malformed RL row; templates budgeted 1 day each without domain fixtures, reference outputs, seed protocols, acceptance.

**Root cause:** Workload list copied from project context without validating actual requirements or budget.

**Correction committed:**
- Decide in R0: Is finance a fifth configured workload, a Hamiltonian parameterization, or out of scope?
- If in scope: add finance template, pinned multi-objective task, schema extensions, validation, maintained example
- Give each supported workload:
  - Own owner and task manifest
  - Acceptance criteria (reference outputs, budget caps, seed protocol)
  - Maintained documented example
  - Separate product_register.json row with traceability
- Increase per-workload template budget from 1 day to realistic 3-5 days including domain work

**Owner:** Workload leads (assign per domain: RL, Hamiltonian, sampler, finance-if-retained)  
**Deadline:** Scope decided in R0; templates completed per tier schedule

### B10. Risk register not decision-operational (ACCEPTED)

**Finding:** Six risks have no owner, exposure estimate, measurable trigger, or funded contingency; several tripwires mistimed (BG-PBT informal <50%, ifBO during construction, ASHA week-10 pilot but week-28 implementation, Brax after gate needing Brax); success definition has no SLOs.

**Root cause:** Risk register written for process compliance rather than actual decision-making.

**Correction committed:**
- Rewrite risk register with per-risk:
  - Owner and reviewer
  - Exposure (cost × probability)
  - Leading indicator (what to measure)
  - Trigger threshold and measurement schedule
  - Decision deadline
  - Funded contingency response
  - Residual risk after response
- Retune tripwires to match revised timeline
- Define internal-beta SLOs before declaring templates production-ready:
  - Availability target
  - Maximum lost work (checkpoint frequency)
  - Recovery time objective
  - Throughput (studies/hour, trials/minute)
  - Submission latency
  - Budget overshoot tolerance
  - Reproducibility (study manifest → identical results)

**Owner:** Risk manager (assign or project lead)  
**Deadline:** End of R0; updated after each tier

---

## Validation suite corrections (ACCEPTED)

We accept all cross-cutting statistical defects and V01-V15 findings. Specific commitments:

### Cross-cutting fixes
1. **Non-significance ≠ equivalence:** Replace "CI overlaps zero" with TOST or preregistered non-inferiority margin
2. **Power analysis:** Run pilots, estimate variance, set repetitions from decision margin and maximum budget
3. **Sampling hierarchy:** Use paired/common-random designs where valid; hierarchical bootstrap across runs and tasks
4. **Held-out tasks:** Development tasks + held-out acceptance tasks per family, versioned rotation
5. **Multiplicity:** Predeclare primary endpoints, control family-wise error or FDR for ranking claims
6. **Actual cost accounting:** Report accelerator-seconds, wall-clock, full-run-equivalents as normalized secondary
7. **Preregistration artifacts:** Manifest format, task checksums, immutable seed sets, signed gate reports
8. **Repetition unit explicit:** State per-test whether repetition is optimizer run, task, or campaign

### Per-test corrections

Every V01-V15 entry will be rewritten with the review's required improvements before any campaign runs. Survey's validation chapter (sections/16-validation.tex) will be amended with corrected protocols. Key examples:

- **V01:** Distributional regression for stochastic references, not 0.5% tolerance
- **V02:** Add state-machine/property tests for out-of-order/duplicate/late events, not just clean replay
- **V03:** Mutation testing with score requirement, not three planted defects
- **V04:** Capability-specific regimes, non-inferiority margins, multiple tasks, separate GP vs TPE vs random
- **V06:** Quality non-inferiority (not CI overlap), actual cost, performance-over-budget curves
- **V08:** Define initial status and green meaning, both sides (e.g. 4 and 8/16 workers), sequential maximum sample
- **V09:** Freeze normalization/reference from domain bounds, use paired non-inferiority, include NSGA-II
- **V10:** Multiple seeds/tasks, gate on top-k recall and false-cull probability (not just correlation)
- **V11:** Test actual πBO/PriorBand, require nonzero support, predefine gain and recovery margins
- **V13:** Use SBC fixtures, rank-normalized R-hat, bulk/tail ESS, MCSE-aware comparisons, automated mode diagnostics
- **V14:** Build real rl_routine, specify artifacts, test that test seeds never reach searcher
- **V15:** Split into pre-build feasibility (published model) + post-integration parity

**Owner:** Validation lead + statistical reviewer (hire/assign)  
**Deadline:** Corrected protocols in revised survey by end of R0; no campaign runs with old protocols

---

## NAS scope decision (REQUIRED IN R0)

The review correctly identifies that the survey "deliberately supports only moderate joint HPO/NAS over width, depth, and structural flags, and explicitly excludes topology search, one-shot supernets, grammar spaces, and a zero-cost proxy subsystem."

**Decision needed:** Is the product:
1. **HPO with moderate architecture coordinates** (width/depth/flags only), OR
2. **General large-scale NAS** (requires new governing document, substantially larger scope/budget)

**Proposed decision:** Option 1 (moderate architecture coordinates). Rationale:
- Matches current survey scope and evidence base
- Serves stated users (RL with BG-PBT architecture search, Hamiltonian networks)
- Avoids claims the product cannot support
- General NAS requires topology search, weight-sharing, hardware-aware objectives, separate validation strategy — all out of current scope

**If moderate NAS (Option 1):** Add to Tier 2 per B6 corrections (architecture factory, compatibility, distillation, measured parameter/FLOP objectives).

**If general NAS (Option 2):** STOP; create new governing document and product program before proceeding.

**Owner:** Project sponsor + technical lead  
**Deadline:** Week 1 of R0 phase

---

## Corrective action timeline

| Phase | Duration | Deliverables | Gate |
|-------|----------|--------------|------|
| **R0: Specification correction** | 2 weeks | Repaired LaTeX validation statistics; reconciled survey/BUILD_PROGRAM scope; NAS boundary decided; timeline arithmetic fixed; traceability matrix generated; V01-V15 protocols corrected; effort/calendar/staffing reconciled | Spec review with statistical reviewer |
| **R1: Executable spike** | 2 weeks | Minimal vertical slice (mixed space, Sobol, ASHA, Ray+local, store+recovery, seed separation); state-machine/restart/conformance tests passing; clean install from lock; stakeholder interface review | Spike review: interfaces validated against real failures |
| **BUILD_PROGRAM_v2** | 1 week | Rebaselined plan: corrected tier scope per traceability matrix, test layers budgeted, distributed beta gate mandatory, Tier 3 deferred post-week-30, contingency added | Approval for Tier 0 start |
| **Tier 0 (revised)** | ~6-8 weeks | Foundation per governing LaTeX: GP+qLogEI with priors, TPE, ASHA/PASHA/median, Ray+local adapters, real rl_routine, deterministic test suite, corrected V01-V05/V14 | Tier 0 gate |
| **Tier 1 (revised)** | ~6-8 weeks | Complete per traceability matrix: qLogNEHVI, Chebyshev, NSGA-II, MO-ASHA, πBO, PriorBand, warm start, EI-per-cost; templates for all workloads; corrected V04/V06/V09-V11/V13 | Tier 1 gate |
| **Tier 2 (revised)** | ~12-16 weeks | Mixed-space TuRBO first (4-6w), then PB2-Mix, then BG-PBT with architecture support if in scope; corrected V08 | Tier 2 gate |
| **Distributed beta hardening** | ~4 weeks | Persistent store, monitoring, fault/scale tests, hard budget controls, security review, runbook | Internal beta gate |
| **Tier 3 (post week-30)** | Per item | DEHB reimplementation (V07), ifBO feasibility then integration (V15), HEBO robustness; each has independent go/no-go | Per-item decision |

**Total to internal beta:** Estimated 30-40 calendar weeks from R0 start (vs 30 in rejected plan), with realistic staffing and contingency.

---

## Approvals and commitments

We commit to:

- [ ] Not proceeding with current BUILD_PROGRAM Phase 0 or Tier 0
- [ ] Completing R0 specification correction with statistical reviewer sign-off
- [ ] Completing R1 executable spike with crash recovery proven
- [ ] Producing BUILD_PROGRAM_v2 with reconciled effort/calendar/scope
- [ ] Seeking re-approval before Tier 0 begins
- [ ] Implementing all test layers, not just statistical campaigns
- [ ] Making distributed beta hardening mandatory, not optional
- [ ] Correcting all V01-V15 protocols before running campaigns
- [ ] Deciding NAS scope explicitly in R0 week 1

**Project sponsor sign-off required before R0 begins.**

---

## Next immediate actions

1. **Week 1 R0:**
   - NAS scope decision (moderate or out of scope)
   - Hire/assign statistical reviewer for validation protocols
   - Begin LaTeX corrections (validation statistics, V08 semantics, knob-kind ambiguity)
   - Start traceability matrix generation from survey decision boxes

2. **Week 2 R0:**
   - Complete LaTeX corrections and regenerate product register
   - Finish traceability matrix (decision → contract → implementation → tests → tier)
   - Rebuild timeline from work-breakdown with contingency
   - Rewrite V01-V15 protocols with corrected statistics

3. **Week 3-4 R1:**
   - Build minimal vertical slice with real failures
   - Add package metadata, lock files, CI skeleton
   - Prove crash recovery and executor conformance
   - Stakeholder interface review

4. **Week 5 BUILD_PROGRAM_v2:**
   - Incorporate R0+R1 learnings
   - Document revised scope, timeline, test strategy
   - Submit for re-approval

**This response will be reviewed with project sponsor before R0 begins.**
