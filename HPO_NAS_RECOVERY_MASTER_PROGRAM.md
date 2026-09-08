# HPO-NAS Recovery Master Program v1.0

**Status:** RED → CONDITIONAL APPROVAL recovery path  
**Duration:** 4 weeks (3-4 week estimate)  
**Authority:** BUILD_PROGRAM_REVIEW_VERDICT.md lines 331-336  
**Goal:** Satisfy 12-item approval checklist, move from RED to CONDITIONAL APPROVAL  

**CRITICAL:** This document governs ALL recovery work. Any agent resuming after context compaction must read this file first and continue from the current phase marker.

---

## Current Phase Marker

**PHASE:** Week 2 Day 3-4 complete  
**WEEK:** 2  
**DAY:** 4  
**LAST COMPLETED:** Week 2 Day 3-4 - Missing contract semantics defined (W2.6 deliverable complete, 2026-09-04)  
**NEXT TASK:** Week 2 Day 5 - Batch Size Semantics (W2.7)  
**DATE:** 2026-09-04  

**Update this section after completing each day's work.**

---

## Recovery Context

### Why This Recovery Is Needed

BUILD_PROGRAM_REVIEW_VERDICT.md (2026-08-28) declared the build program **RED (not approved)** with blocking findings:

1. **Zero executable product tests exist** - validation scripts are not product tests
2. **Timeline/effort/staffing arithmetic irreconcilable** - claims 42 weeks but sums to 32; claims 5 GPU-weeks but V07 alone needs 3.8
3. **15+ specification violations** - algorithm implementations don't match LaTeX
4. **Tier 0 gate withdrawn** - recorded GATE NOT MET on 2026-09-02
5. **Validation methodology flawed** - confuses "no detected difference" with "proof of equivalence"; lacks power analysis
6. **Phase 0 contracts unfrozen** - missing semantics for schema migration, event ordering, NaN handling, failure policy, checkpoint format
7. **Gates can't establish claimed tier outcomes** - V10 critique applies to other validations
8. **NAS scope unclear** - moderate architecture coordinates vs general NAS?

### Current Build Program Status

- **Tier 0:** GATE NOT MET (2026-09-02), 17-day remediation blocked
- **Tier 1:** FAILING (2/4 passed: V06✅ V09✅, V04-T1❌ V11⚠️, V10⏸️ V13⏸️)
- **Tier 2:** Not started, scope depends on V04-T1 demotion resolution

### Triggered Demotion Rules

Per BUILD_PROGRAM_v2.md lines 252-256:

1. **V04-T1 failure** → Defer population line (BG-PBT depends on TR), reassess Tier 2 scope
2. **V11 weak effects** → Demote πBO/PriorBand to opt-in

---

## 12-Item Approval Checklist

**Source:** BUILD_PROGRAM_REVIEW_VERDICT.md lines 314-330  
**Purpose:** Move from RED to CONDITIONAL APPROVAL  

### Checklist Status

- [ ] **Item 1:** Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan
- [ ] **Item 2:** Governing LaTeX, product register, build program, README, progress tracker have one tier/test mapping
- [ ] **Item 3:** Timeline math and campaign capacity reconcile with named staffing and contingency
- [ ] **Item 4:** Tier 0 includes GP+qLogEI, required defaults, both adapters, functional day-one workload, or LaTeX amended
- [ ] **Item 5:** piBO, PriorBand, warm start, BG-PBT, ifBO descriptions match methods actually authorized
- [ ] **Item 6:** V01-V15 have preregistered tasks, seeds, margins, power/repetition policy, analysis, decision states, immutable artifacts
- [ ] **Item 7:** Non-inferiority/equivalence replaces "CI overlaps zero" wherever safety or matching is claimed
- [ ] **Item 8:** Deterministic unit/property/conformance/recovery tests exist below statistical campaigns
- [ ] **Item 9:** Package, environment locks, provenance, CI, migrations, clean-install tests exist
- [ ] **Item 10:** Store/control-plane semantics survive concurrency, duplicate events, restart
- [ ] **Item 11:** Distributed scale, fault, monitoring, hard-budget gates mandatory before broad internal use
- [ ] **Item 12:** Each supported workload (including finance if retained) has maintained template and held-out acceptance task

**Update after each item satisfied. Program moves to approval package when all 12 checked.**

---

## Algorithm Specification Violations (MUST FIX)

**Source:** BUILD_PROGRAM_REVIEW_VERDICT.md lines 66-70  

### πBO (Prior-weighted Bayesian Optimization)

- **WRONG:** Current implementation uses GP mean as weight
- **RIGHT:** Must use acquisition function value as multiplier
- **File:** (search for piBO/πBO implementation)
- **Traceability:** LaTeX spec → implementation → test → validation V11

### PriorBand (Prior-aware Successive Halving)

- **WRONG:** Current implementation uses top-K promotion
- **RIGHT:** Must use portfolio sampler (randomized weighted selection)
- **File:** (search for PriorBand implementation)
- **Traceability:** LaTeX spec → implementation → test → validation V11

### ifBO (Iterative Feature Bayesian Optimization)

- **WRONG:** Current implementation builds custom power-law model
- **RIGHT:** Must use pretrained surrogate model
- **File:** (search for ifBO implementation)
- **Traceability:** LaTeX spec → implementation → test → validation (TBD)

### Warm-Start Transfer Learning

- **WRONG:** Current implementation builds RGPE (Rank-weighted GP Ensemble) immediately
- **RIGHT:** Must query ranked/quantile samples first, build RGPE only after query
- **File:** (search for warm_start/transfer implementation)
- **Traceability:** LaTeX spec → implementation → test → validation V13

**Action:** Traceability matrix (Week 1) will document all 15+ violations. Fix during Tier 1 scope correction (Week 4).

---

## 4-Week Recovery Schedule

### Week 1: Specification Reconciliation (7 days)

**Goal:** Satisfy checklist items 1, 2, 3  

#### Day 1-3: Work Breakdown Spreadsheet (3 days)

**Deliverable:** `WORK_BREAKDOWN_v3.xlsx` or `.csv`

**Columns:**
- Task ID
- Task name
- Tier (0/1/2/distributed-beta)
- Effort (eng-days)
- Duration (calendar days with parallelism)
- Dependencies (task IDs)
- Staff assignment
- GPU requirements (type, count, days)
- Start week
- End week

**Requirements:**
- Timeline math must reconcile: sum(effort) with contingency = total eng-days, longest path with parallelism = calendar weeks
- GPU capacity must reconcile: sum(GPU-days) ≤ available capacity
- Staffing must be named: "2 senior engineers" not anonymous FTE
- Contingency explicit: 20-30% buffer for unknowns

**Acceptance:**
- No arithmetic contradictions
- All Tier 0/1/2 tasks from corrected scope included
- V16 validator audit at every gate
- Distributed-beta hardening present

**Updates checklist:** Item 3 ✓

#### Day 4-6: Traceability Matrix (3 days)

**Deliverable:** `TRACEABILITY_MATRIX_v1.md` or `.csv`

**Columns:**
- LaTeX spec reference (section, equation, algorithm line)
- Claim/requirement text
- Implementation file:line
- Unit test file:line
- Integration test file:line
- Validation campaign ID (V01-V15)
- Status (✓ match / ❌ violation / ⚠️ missing)
- Notes

**Scope:**
- GP+qLogEI baseline (Tier 0)
- Random, Sobol, TPE, ASHA, MO-ASHA, qLogNEHVI (Tier 1 core)
- πBO, PriorBand, ifBO, warm-start (Tier 1 priors/transfer)
- TuRBO, Chebyshev scalarization, NSGA-II, EI-per-cost (Tier 1 corrected)
- BG-PBT, mixed-space TuRBO (Tier 2 if V04-T1 resolved)

**Known violations to document:**
- πBO: GP mean not acquisition multiplier
- PriorBand: top-K not portfolio sampler
- ifBO: custom power-law not pretrained
- Warm-start: immediate RGPE not ranked/quantile query
- (11 more from BUILD_PROGRAM_REVIEW_VERDICT.md line 68)

**Acceptance:**
- Every algorithm in scope has LaTeX → implementation mapping
- All 15+ known violations documented
- Missing tests identified

**Updates checklist:** Item 2 ✓, Item 5 ✓

#### Day 7: NAS Scope Clarification (1 day)

**Deliverable:** `NAS_SCOPE_DECISION.md`

**Decision:**
- Option A: Moderate architecture-coordinate NAS only (2-10 knobs: width, depth, layers, activation, optimizer, LR, dropout, batch size)
- Option B: Retain general NAS, supply separately approved plan with cell search, weight sharing, supernets

**Acceptance:**
- Decision recorded in writing
- BUILD_PROGRAM_v3.md scope section updated
- Workload templates reflect decision (Item 12)

**Updates checklist:** Item 1 ✓

---

### Week 2: Contract & Risk Spikes (7 days)

**Goal:** Satisfy checklist items 8, 9, 10 (partial)  

#### Day 1-5: Executable Contract Conformance Tests (5 days)

**Deliverable:** `tests/conformance/` directory with passing tests

**Test Coverage:**

1. **Searcher Contract** (1 day)
   - File: `tests/conformance/test_searcher_contract.py`
   - Coverage: `suggest()` returns valid config, `observe()` accepts trial result, state serialization/deserialization, deterministic behavior given seed
   - Implements: GP+qLogEI reference searcher
   - Acceptance: pytest passes, mutation score ≥0.9 (Item 8 partial)

2. **Scheduler Contract** (1 day)
   - File: `tests/conformance/test_scheduler_contract.py`
   - Coverage: `schedule()` returns runnable trial, `observe()` updates state, promotion/culling decisions, state serialization
   - Implements: ASHA reference scheduler
   - Acceptance: pytest passes, mutation score ≥0.9

3. **Executor Contracts** (1 day)
   - File: `tests/conformance/test_executor_contract.py`
   - Coverage: Local executor (sync/async), Ray executor (distributed), handles NaN/inf, timeout, exception, checkpoint save/load
   - Acceptance: pytest passes, handles all failure modes

4. **Store Recovery** (1 day)
   - File: `tests/conformance/test_store_recovery.py`
   - Coverage: Crash-safe writes, idempotent operations, duplicate event handling, read-after-write consistency, concurrent writers
   - Acceptance: pytest passes, survives kill -9, no data corruption (Item 10 partial)

5. **Checkpoint Resume** (1 day)
   - File: `tests/conformance/test_checkpoint_resume.py`
   - Coverage: Save/load at arbitrary trial, deterministic resume, format versioning, backward compatibility
   - Acceptance: pytest passes, resume produces identical results

**Updates checklist:** Item 8 ✓ (partial), Item 10 ✓ (partial)

#### Day 6-7: Define Missing Semantics (2 days)

**Deliverable:** `CONTRACT_SEMANTICS_v1.md`

**Content:**

1. **Schema Migration** (0.5 day)
   - Checkpoint format versioning scheme
   - Forward/backward compatibility guarantees
   - Migration path for breaking changes
   - Acceptance: Documented policy, migration test exists

2. **Stable IDs** (0.5 day)
   - Trial ID generation (UUID? sequential? hash?)
   - Study ID uniqueness guarantees
   - ID persistence across restarts
   - Acceptance: Documented scheme, collision test exists

3. **Event Ordering** (0.5 day)
   - Concurrent `observe()` calls on same trial
   - Race between `suggest()` and `observe()`
   - Out-of-order event arrival in distributed setting
   - Acceptance: Documented ordering guarantees, happens-before test exists

4. **NaN/Inf Handling** (0.25 day)
   - Observation with NaN objective
   - Observation with inf objective
   - NaN in config parameter
   - Acceptance: Documented policy (reject? saturate? mark failed?), test exists

5. **Failure Policy** (0.25 day)
   - Trial crashes before first observation
   - Trial crashes after partial observations (multi-fidelity)
   - Executor unreachable
   - Acceptance: Documented policy (retry? mark failed? budget?), test exists

6. **Checkpoint Format** (0.5 day)
   - Required fields (version, study_id, trials, searcher_state, scheduler_state)
   - Optional fields (metadata, timestamps, git hash)
   - Serialization format (JSON? pickle? msgpack?)
   - Acceptance: Documented format, schema validation test exists

**Updates checklist:** Item 10 ✓ (complete)

---

### Week 3: Validation Protocol Repair (7 days)

**Goal:** Satisfy checklist items 6, 7, 8 (complete)  

#### Day 1-3: Repair V01-V15 Protocols (3 days)

**Deliverable:** `validation/protocols/` directory with preregistered protocols

**Template per validation:**

```markdown
# V{XX} Protocol

## Claim
[Exact claim from LaTeX/BUILD_PROGRAM]

## Hypothesis
- H0: [null hypothesis]
- H1: [alternative hypothesis]
- Type: [superiority / non-inferiority / equivalence]

## Preregistration
- Tasks: [list of benchmark names, must be held-out]
- Seeds: [exact seeds, e.g., 42, 123, 456, 789, 1011]
- Margin: [equivalence margin or superiority threshold, with justification]
- Alpha: [significance level, Bonferroni-corrected if multiple comparisons]
- Power: [target power, typically 0.8]
- Sample size: [trials per seed, seeds, total studies]
- Analysis: [statistical test, e.g., paired t-test, Wilcoxon, TOST]

## Decision States
- PASS: [criteria, e.g., p < 0.05 AND effect > margin]
- FAIL: [criteria, e.g., p ≥ 0.05 OR effect < margin]
- INCONCLUSIVE: [criteria, e.g., power < 0.8 at max sample]

## Immutable Artifacts
- Protocol: validation/protocols/v{XX}_protocol.md (this file, immutable after campaign starts)
- Results: validation/results/v{XX}_results.json (written once, never modified)
- Log: validation/results/v{XX}_log.txt (append-only)

## Implementation
- Script: validation/v{XX}_{name}.py
- Validator: validation/validators/v{XX}_validator.py (implements V16 audit protocol)
```

**V01-V15 Repairs Needed:**

| Validation | Current Issue | Repair Action |
|------------|---------------|---------------|
| V01 | Tautological (checks own output) | Compare TPE vs Optuna.TPE, GP vs BoTorch.GP (vendor parity) |
| V02 | Not implemented | State-machine replay test |
| V03 | Not implemented | Mutation testing ≥0.9 kill score |
| V04-T0 | Post-hoc tuned threshold | Preregister 5% threshold before campaign |
| V04-T1 | Failed, underpowered | Power analysis, increase to 500 trials if needed |
| V05 | Proxy workload | Use real rl_routine (jax/brax dependency) |
| V06 | ✓ No repair needed | Already passed |
| V07 | GPU capacity conflict | Reconcile 3.8 GPU-weeks with total budget |
| V08 | Unknown status | Check implementation, add protocol |
| V09 | ✓ No repair needed | Already passed, but was single-seed (add multi-seed per V10 critique) |
| V10 | Deferred to T2, single-seed | Add multi-seed, out-of-sample configs, gate on recall/false-cull/regret not just rho |
| V11 | Inconclusive, weak effects | Demotion rule applied, but protocol should specify confirmatory sizing policy |
| V12 | Unknown status | Check implementation, add protocol |
| V13 | Deferred to T2 | Add protocol for sampler veto correctness |
| V14 | Vacuous (zero trials) | Non-zero trial count preregistered |
| V15 | Unknown status | Check implementation, add protocol |

**Acceptance:**
- All V01-V15 have preregistered protocols following template
- Known issues (tautological V01, vacuous V14, post-hoc V04-T0) repaired
- Equivalence/non-inferiority tests use TOST where appropriate (Item 7)
- Power analysis documented for all statistical tests

**Updates checklist:** Item 6 ✓, Item 7 ✓

#### Day 4-5: Design Test Pyramid (2 days)

**Deliverable:** `TEST_PYRAMID_v1.md` + initial test implementations

**Layer 1: Unit / Property / Conformance (Bottom - Fastest)**

Purpose: Verify individual functions, contracts, invariants  
Runtime: Milliseconds to seconds  
Frequency: Every commit (CI)  
Coverage target: >80% line coverage  

Files:
- `tests/unit/` - Unit tests for individual functions
- `tests/property/` - Property-based tests (hypothesis library)
- `tests/conformance/` - Contract conformance tests (from Week 2 Day 1-5)

Examples:
- `test_gp_posterior()` - GP posterior mean/variance correct on synthetic data
- `test_acquisition_maximization()` - argmax within epsilon of known optimum
- `test_config_serialization()` - roundtrip serialization preserves value
- `test_searcher_contract()` - Searcher interface conformance

Count target: 200-300 tests  
Current count: 6 broken R1 tests need repair (BUILD_PROGRAM_v2.md line 155)

**Layer 2: Integration / Recovery / Scale (Middle - Slower)**

Purpose: Verify component interactions, failure recovery, resource limits  
Runtime: Seconds to minutes  
Frequency: Every PR (CI)  
Coverage target: All critical paths  

Files:
- `tests/integration/` - Multi-component interactions
- `tests/recovery/` - Crash recovery, checkpoint resume
- `tests/scale/` - Large config spaces, long horizons, many workers

Examples:
- `test_searcher_scheduler_interaction()` - Full optimization loop on Branin
- `test_checkpoint_resume_deterministic()` - Resume produces identical results
- `test_distributed_executor()` - 10 parallel workers on Ray cluster
- `test_store_concurrent_writes()` - 100 concurrent `observe()` calls

Count target: 50-100 tests  
Current count: Unknown (audit needed)

**Layer 3: Statistical Campaigns (Top - Slowest)**

Purpose: Verify method effectiveness claims, gate tier exit  
Runtime: Minutes to hours  
Frequency: Manual (gate validation)  
Coverage target: All V01-V15 claims  

Files:
- `validation/` - V01-V15 campaign scripts
- `validation/protocols/` - Preregistered protocols (from Day 1-3 above)
- `validation/results/` - Immutable result artifacts
- `validation/validators/` - V16-compliant validators

Examples:
- V06 ASHA Efficiency - 30 trials × 5 seeds, multi-fidelity Branin (~10 sec)
- V04-T1 Sobol vs Random - 200 trials × 5 seeds, rl_routine (~15 sec)
- V11 Prior Recovery - 120 studies, 25 trials each (~18 min)

Count: 15 validations (V01-V15)  
Current status: V06✅ V09✅ V04-T1❌ V11⚠️ V10⏸️ V13⏸️, others unknown

**Pyramid Ratio:** 
- Layer 1: ~80% of tests, <1% of runtime
- Layer 2: ~15% of tests, ~10% of runtime  
- Layer 3: ~5% of tests, ~90% of runtime

**Acceptance:**
- TEST_PYRAMID_v1.md documents all three layers
- Layer 1 has >100 tests implemented (includes Week 2 conformance tests)
- Layer 2 has >20 tests implemented
- Layer 3 has all V01-V15 protocols (from Day 1-3)

**Updates checklist:** Item 8 ✓ (complete)

#### Day 6: Add V16 to Every Gate (1 day)

**Deliverable:** V16 validator audit protocol enforced at all gates

**V16 Audit Protocol** (BUILD_PROGRAM_v2.md lines 165-189):

Each validator must implement `--audit` mode checking:

1. **Non-vacuity:** Validator fails on structurally empty input
   - Example: `validate(results=[])` → ERROR, not PASS
   - Example: `validate(results=[{trials: 0}])` → ERROR, not PASS

2. **No post-hoc tuning:** Thresholds recorded before campaign
   - Example: Protocol file preregisters `margin=0.05`, validator uses exactly 0.05
   - Example: Changing threshold after seeing results → AUDIT FAIL

3. **Correct reference:** Compare against declared vendor, not self
   - Example: V01 "GP matches BoTorch" must compare to BoTorch, not own GP
   - Example: Comparing two internal implementations → tautological

4. **Runnable independently:** Full protocol executes standalone
   - Example: `python validation/v06_asha_efficiency.py --audit` runs without human intervention
   - Example: Validator reads preregistered protocol, not command-line args

**Implementation:**

File: `validation/validators/base_validator.py`

```python
class ValidationProtocol:
    def audit(self) -> AuditReport:
        """Run V16 audit checks."""
        checks = [
            self._check_non_vacuity(),
            self._check_no_posthoc_tuning(),
            self._check_correct_reference(),
            self._check_runnable_independently(),
        ]
        return AuditReport(checks=checks, passed=all(checks))
```

**Gate Enforcement:**

- Tier 0 gate: V01, V02, V03, V04-T0, V05, V14, V16 (validator audit)
- Tier 1 gate: V04-T1, V06, V09, V11, V16
- Tier 2 gate: V10, V13, (others TBD), V16

**Acceptance:**
- `base_validator.py` implements V16 audit protocol
- All V01-V15 validators inherit from base and implement audit checks
- Gate reports include V16 audit results
- Any V16 audit failure blocks gate passage

**Updates checklist:** Item 6 ✓ (enforced)

---

### Week 4: Rebaselined Program v3.0 (7 days)

**Goal:** Produce BUILD_PROGRAM_v3.md and approval package  

#### Day 1-2: Tier 0 Corrected Scope (2 days)

**Deliverable:** BUILD_PROGRAM_v3.md Tier 0 section

**Requirements (Checklist Item 4):**
- GP+qLogEI baseline implementation (reference searcher)
- Required defaults (initial_random_samples, kernel, acquisition optimizer)
- Both executors (LocalExecutor, RayExecutor)
- Functional day-one workload (rl_routine with jax/brax)
- OR: LaTeX specification amended to remove above requirements

**Corrected Scope:**

| Component | Status | Effort | Notes |
|-----------|--------|--------|-------|
| GP+qLogEI baseline | Required | 3d | Reference implementation matching LaTeX |
| LocalExecutor | Required | 1d | Sync/async modes, error handling |
| RayExecutor | Required | 2d | Distributed execution, fault tolerance |
| rl_routine workload | Required | 1d | 9-knob RL proxy, jax/brax dependency (0.5d) |
| Random baseline | Required | 0.5d | Uniform sampling |
| Sobol baseline | Required | 0.5d | Quasi-random sampling |
| V01 vendor parity | Remediation | 1d | TPE vs Optuna, GP vs BoTorch |
| V02 state replay | Remediation | 3d | Deterministic replay test |
| V03 mutation testing | Remediation | 3d | ≥0.9 kill score |
| V04-T0 re-run | Remediation | 2d | Fixed 5% threshold |
| V05 re-run | Remediation | 1d | Real rl_routine workload |
| V14 re-run | Remediation | 0.5d | Non-zero trials |
| V16 validator audit | Remediation | 2d | Audit mode for all validators |
| Test repair | Remediation | 2d | Fix 6 broken R1 tests |
| Gate report | Remediation | 1d | Honest verdict |
| **REMOVED:** DEHB | Deferred | - | Move to Tier 3 (research flag) |

**Total Tier 0:** 17 days remediation (unchanged from BUILD_PROGRAM_v2.md) + 8 days original scope = 25 days

**Gate Criteria:** All of V01, V02, V03, V04-T0, V05, V14, V16 PASS

**Updates checklist:** Item 4 ✓

#### Day 3: Tier 1 Corrected Scope (1 day)

**Deliverable:** BUILD_PROGRAM_v3.md Tier 1 section

**Demotion Rules Applied:**
- V04-T1 failed → Remove TuRBO from Tier 1 (defer to Tier 2 after fixing)
- V11 weak effects → Demote πBO/PriorBand to opt-in (not default)

**Corrected Scope:**

| Component | Status | Effort | Validations | Notes |
|-----------|--------|--------|-------------|-------|
| **Core Methods (Required)** |
| ASHA | Required | 3d | V06✅ | Multi-fidelity successive halving |
| MO-ASHA | Required | 4d | V10⏸️(T2) | Multi-objective ASHA |
| qLogNEHVI | Required | 5d | V09✅ | Multi-objective acquisition |
| Chebyshev scalarization | NEW | 2d | V09 baseline | Was missing, needed for V09 |
| NSGA-II | NEW | 3d | - | Multi-objective evolutionary baseline |
| EI-per-cost | NEW | 2d | - | Cost-aware acquisition |
| **Prior/Transfer (Opt-in)** |
| πBO | Opt-in | 3d | V11⚠️ | FIX: acquisition multiplier not GP mean |
| PriorBand | Opt-in | 3d | V11⚠️ | FIX: portfolio sampler not top-K |
| ifBO | Opt-in | 4d | - | FIX: pretrained not custom power-law |
| Warm-start | Deferred | - | V13⏸️(T2) | FIX: ranked/quantile not immediate RGPE |
| **Removed from Tier 1** |
| TuRBO | → Tier 2 | - | V04-T1❌ | Trust region failed validation |
| BG-PBT | → Tier 2 | - | (depends TR) | Population method depends on TuRBO |

**Total Tier 1:** 29 days (was 24 days before corrections)

**Gate Criteria:** V04-T1 (revised), V06✅, V09✅, V11 (opt-in status doesn't block)

**Updates checklist:** Item 5 ✓

#### Day 4: Tier 2 Corrected Scope (1 day)

**Deliverable:** BUILD_PROGRAM_v3.md Tier 2 section

**Corrected Scope:**

| Component | Status | Effort | Validations | Notes |
|-----------|--------|--------|-------------|-------|
| **Deferred from Tier 1** |
| TuRBO | Must fix first | 5d | V04-T1 (re-run) | Fix Sobol implementation or protocol, re-validate |
| Mixed-space TuRBO | After TuRBO | 4d | V12 (new) | Categorical/continuous trust regions |
| BG-PBT | After TuRBO | 6d | V15 (new) | Population-based training |
| Warm-start | Required | 4d | V13⏸️ | FIX: ranked/quantile not immediate RGPE |
| **Deferred from Tier 1** |
| MO-ASHA diagnostics | Required | 2d | V10⏸️ | FIX: multi-seed, recall/regret not just rho |

**Conditional Scope:**
- If V04-T1 cannot be fixed → Remove TuRBO, mixed-space TuRBO, BG-PBT from roadmap
- If V04-T1 fixed → Proceed with full Tier 2 scope above

**Total Tier 2:** 21 days (conditional on V04-T1 resolution)

**Gate Criteria:** V10, V12, V13, V15, V16

#### Day 5: Distributed-Beta Hardening (1 day)

**Deliverable:** BUILD_PROGRAM_v3.md Distributed-Beta section

**Scope (Checklist Item 11):**

| Component | Effort | Notes |
|-----------|--------|-------|
| Persistent store | 3d | PostgreSQL or DynamoDB backend |
| Backup/restore | 2d | Snapshot + point-in-time recovery |
| Monitoring | 2d | Metrics (latency, throughput), alerts |
| Scale testing | 3d | 100+ concurrent studies, 1000+ trials |
| Security audit | 2d | Authentication, authorization, secrets |
| Hard-budget gates | 1d | Cost limits, quota enforcement |

**Total Distributed-Beta:** 13 days

**Gate Criteria (Item 11):** Scale, fault, monitoring, hard-budget tests PASS before broad internal use

**Updates checklist:** Item 11 ✓

#### Day 6-7: Approval Package (2 days)

**Deliverable:** Approval package for RED → CONDITIONAL APPROVAL

**Contents:**

1. **BUILD_PROGRAM_v3.md** (Day 6, 1 day)
   - Executive summary with reconciled timeline
   - Tier 0 corrected scope (25 days)
   - Tier 1 corrected scope (29 days)
   - Tier 2 corrected scope (21 days conditional)
   - Distributed-beta hardening (13 days)
   - Total: 88 days (13 weeks with parallelism and contingency)
   - All algorithm descriptions match LaTeX (Item 5)
   - One consistent tier/test mapping (Item 2)

2. **12-Item Checklist Verification** (Day 7, 0.5 day)
   - File: `APPROVAL_CHECKLIST_v1.md`
   - Each item: status, evidence file, notes
   - All 12 items checked ✓

3. **Reconciled Timeline** (Day 7, 0.5 day)
   - File: `TIMELINE_v3.xlsx` (from Week 1 Day 1-3)
   - Work breakdown with no arithmetic contradictions (Item 3)
   - GPU capacity reconciled
   - Staffing named and realistic

4. **Traceability Matrix** (from Week 1 Day 4-6)
   - File: `TRACEABILITY_MATRIX_v1.md`
   - LaTeX → implementation → tests → validations (Item 2)
   - All 15+ violations documented and tagged for fix (Item 5)

5. **Test Pyramid** (from Week 3 Day 4-5)
   - File: `TEST_PYRAMID_v1.md`
   - Layer 1/2/3 documented (Item 8)
   - Initial implementation started

6. **Validation Protocols** (from Week 3 Day 1-3)
   - Files: `validation/protocols/v01_protocol.md` through `v15_protocol.md`
   - All preregistered (Item 6)
   - Equivalence tests use TOST (Item 7)
   - V16 audit enforced (Item 6)

7. **Contract Semantics** (from Week 2 Day 6-7)
   - File: `CONTRACT_SEMANTICS_v1.md`
   - All missing semantics defined (Item 10)

8. **Request Letter** (Day 7, 0.5 day)
   - File: `APPROVAL_REQUEST_v1.md`
   - Request RED → CONDITIONAL APPROVAL
   - Summary of 4-week recovery work
   - All 12 checklist items satisfied
   - Proposed next steps (execute Tier 0 remediation)

**Acceptance:**
- All deliverables present
- No unresolved contradictions
- Stakeholder review scheduled

---

## Post-Approval Execution (Not Part of Recovery)

### Tier 0 Remediation (17 days)

**Source:** BUILD_PROGRAM_v2.md lines 137-227  
**Trigger:** After CONDITIONAL APPROVAL granted  

Execute as written in BUILD_PROGRAM_v2.md with V16 audit added to gate.

### Tier 1 Execution (29 days)

**Source:** BUILD_PROGRAM_v3.md Tier 1 section (created Week 4 Day 3)  
**Trigger:** After Tier 0 gate PASSED  

Execute with corrected scope (TuRBO removed, πBO/PriorBand opt-in).

### Tier 2 Execution (21 days conditional)

**Source:** BUILD_PROGRAM_v3.md Tier 2 section (created Week 4 Day 4)  
**Trigger:** After Tier 1 gate PASSED AND V04-T1 resolution determined  

If V04-T1 fixed: full scope  
If V04-T1 unfixable: remove TuRBO/BG-PBT line

---

## Validation Details (Reference)

### V01: Vendor Parity

**Claim:** Our implementations match reference vendors  
**Protocol:** Compare TPE vs Optuna.TPE, GP vs BoTorch.GP on standard benchmarks  
**Issue:** Currently tautological (compares to self)  
**Fix:** Week 3 Day 1-3 - add vendor comparison  
**Gate:** Tier 0

### V02: State Replay

**Claim:** Deterministic replay from event log  
**Protocol:** Record optimization run, replay events, verify identical state  
**Issue:** Not implemented  
**Fix:** Week 2 Day 1-5 conformance tests + Week 3 protocol  
**Gate:** Tier 0

### V03: Mutation Testing

**Claim:** Test suite detects real bugs  
**Protocol:** mutmut or cosmic-ray, achieve ≥0.9 kill score  
**Issue:** Not implemented  
**Fix:** Week 2 Day 1-5 + Week 3 protocol  
**Gate:** Tier 0

### V04-T0: Random Baseline Floor

**Claim:** Random search is a valid baseline  
**Protocol:** Random beats pathological config on real workload  
**Issue:** Post-hoc tuned threshold  
**Fix:** Preregister 5% threshold, re-run (Week 3)  
**Gate:** Tier 0

### V04-T1: Sobol vs Random

**Claim:** Sobol beats random on real RL workload  
**Status:** ❌ FAILED (2.42% improvement, p=0.2738)  
**Protocol:** 200 trials × 5 seeds, 9-knob rl_routine  
**Issue:** Underpowered or Sobol implementation wrong  
**Fix:** Power analysis, increase to 500 trials if needed (Week 3)  
**Consequence:** TuRBO/BG-PBT deferred to Tier 2  
**Gate:** Tier 1

### V05: Real Workload

**Claim:** Method works on real RL task  
**Protocol:** rl_routine with actual jax/brax evaluation  
**Issue:** Currently uses proxy objective  
**Fix:** Add jax/brax dependency (0.5d), use real evaluation (Week 3)  
**Gate:** Tier 0

### V06: ASHA Efficiency

**Claim:** ASHA reaches full-fidelity quality at ≤1/3 compute  
**Status:** ✅ PASSED (0.17% quality gap, 18.5% compute ratio)  
**Protocol:** 30 trials × 5 seeds, multi-fidelity Branin  
**Artifact:** results/v06_asha_efficiency.json  
**Gate:** Tier 1

### V07: GPU Campaign Capacity

**Claim:** Stated GPU budget sufficient for all campaigns  
**Protocol:** Sum all validation GPU-days, compare to available capacity  
**Issue:** V07 alone needs 3.8 GPU-weeks but total budget claims 5  
**Fix:** Reconcile in Week 1 Day 1-3 work breakdown  
**Gate:** Program-level (not tier-specific)

### V08: Status Unknown

**Action:** Audit during Week 3 Day 1-3 protocol repair  

### V09: qLogNEHVI vs Scalarization

**Claim:** qLogNEHVI beats scalarization baseline  
**Status:** ✅ PASSED (8.2% improvement, p=0.0159)  
**Protocol:** 50 trials × 10 seeds, Branin-Currin  
**Issue:** Single-seed protocol (per V10 critique)  
**Fix:** Add multi-seed version during Week 3 protocol repair  
**Artifact:** results/v09_qlogNEHVI_vs_scalarization.json  
**Gate:** Tier 1

### V10: Rung Correlation Diagnostics

**Claim:** Early-rung drift correlates with final-rung drift (ρ > 0.6)  
**Status:** ⏸️ DEFERRED to Tier 2 (Week 30)  
**Issue:** Single-seed protocol insufficient per BUILD_PROGRAM_REVIEW_VERDICT.md line 207  
**Fix:** Multi-seed, out-of-sample configs, gate on top-k recall / false-cull probability / regret (Week 3 protocol)  
**Gate:** Tier 2

### V11: Prior Recovery

**Claim:** Priors help under good advice, recover under wrong advice  
**Status:** ⚠️ INCONCLUSIVE (pilot complete, confirmatory undersized)  
**Protocol:** 120 studies (4 tasks × 2 methods × 3 priors × 5 reps), 25 trials  
**Results:**
- V11a (folklore beats none): point=+0.0604, lb=-0.0002, p=0.0195, inconclusive
- V11b (wrong recovers): point=-0.0249, lb=-0.1125, p=0.0172, inconclusive  
**Sizing:** Both hypotheses NOT SIZED (power <0.8 at max_sample=20)  
**Consequence:** πBO/PriorBand demoted to opt-in  
**Artifact:** results/v11_pilot_summary.json  
**Gate:** Tier 1 (opt-in status doesn't block)

### V12: Status Unknown

**Expected:** Mixed-space TuRBO validation  
**Action:** Audit during Week 3 Day 1-3 protocol repair  
**Gate:** Tier 2

### V13: Warm-Start Effectiveness

**Claim:** No veto-failing configs promoted, survivors ranked by ESS/gradient  
**Status:** ⏸️ DEFERRED to Tier 2 (Week 30)  
**Issue:** Not implemented  
**Fix:** Protocol during Week 3, implementation during Tier 2  
**Gate:** Tier 2

### V14: Non-Vacuous Validator

**Claim:** Validators detect real problems  
**Protocol:** Feed empty/trivial input, verify validator fails  
**Issue:** Vacuous (accepted zero trials)  
**Fix:** Re-run with non-zero trial count (Week 3)  
**Gate:** Tier 0

### V15: Status Unknown

**Expected:** BG-PBT validation  
**Action:** Audit during Week 3 Day 1-3 protocol repair  
**Gate:** Tier 2

### V16: Validator Audit Protocol (NEW)

**Claim:** All validators are non-vacuous, not post-hoc tuned, with correct references  
**Protocol:** Each validator implements `--audit` mode  
**Checks:**
1. Non-vacuity: fails on empty input
2. No post-hoc tuning: thresholds preregistered
3. Correct reference: compares to vendor not self
4. Runnable independently: full protocol executes standalone  
**Implementation:** Week 3 Day 6  
**Enforcement:** Added to every gate (T0, T1, T2)  
**Gate:** All gates

---

## File Path Reference

### Core Program Documents

- `HPO_NAS_RECOVERY_MASTER_PROGRAM.md` - This file (master recovery governance)
- `BUILD_PROGRAM_v2.md` - Current build program (RED status)
- `BUILD_PROGRAM_v3.md` - Corrected build program (deliverable Week 4 Day 6)
- `BUILD_PROGRAM_REVIEW_VERDICT.md` - Technical review declaring RED
- `BUILD_PROGRAM_DRIFT_REPORT.md` - Validation timing reconciliation
- `TIER1_GATE_STATUS.md` - Tier 1 validation results (2026-09-04)
- `SESSION_PROGRESS_REPORT_2026-09-04.md` - Session documentation

### Recovery Deliverables (To Be Created)

**Week 1:**
- `WORK_BREAKDOWN_v3.xlsx` - Reconciled timeline/effort/staffing
- `TRACEABILITY_MATRIX_v1.md` - LaTeX → implementation → tests → validations
- `NAS_SCOPE_DECISION.md` - Moderate vs general NAS decision

**Week 2:**
- `tests/conformance/test_searcher_contract.py` - Searcher conformance
- `tests/conformance/test_scheduler_contract.py` - Scheduler conformance
- `tests/conformance/test_executor_contract.py` - Executor conformance
- `tests/conformance/test_store_recovery.py` - Store crash recovery
- `tests/conformance/test_checkpoint_resume.py` - Checkpoint resume
- `CONTRACT_SEMANTICS_v1.md` - Missing semantics defined

**Week 3:**
- `validation/protocols/v01_protocol.md` through `v15_protocol.md` - Preregistered protocols
- `validation/validators/base_validator.py` - V16 audit implementation
- `TEST_PYRAMID_v1.md` - Three-layer test design

**Week 4:**
- `BUILD_PROGRAM_v3.md` - Corrected build program
- `APPROVAL_CHECKLIST_v1.md` - 12-item checklist verification
- `APPROVAL_REQUEST_v1.md` - RED → CONDITIONAL APPROVAL request

### Existing Validation Artifacts

- `results/v06_asha_efficiency.json` - V06 PASSED (18.5% compute ratio)
- `results/v06_asha_efficiency.log`
- `results/v04_t1_real_workload.json` - V04-T1 FAILED (2.42% improvement)
- `results/v04_t1_real_workload.log`
- `results/v09_qlogNEHVI_vs_scalarization.json` - V09 PASSED (8.2% improvement)
- `results/v11_pilot_summary.json` - V11 INCONCLUSIVE (weak effects)
- `results/v11_pilot.log`
- `validation/results/v11_pilot.json` - Full V11 pilot campaign data
- `validation/results/v11_sizing.json` - V11 confirmatory sizing analysis

### Implementation Files (To Be Audited/Fixed)

- (search for `piBO` or `πBO`) - FIX: use acquisition multiplier not GP mean
- (search for `PriorBand`) - FIX: use portfolio sampler not top-K
- (search for `ifBO`) - FIX: use pretrained not custom power-law
- (search for `warm_start` or `transfer`) - FIX: ranked/quantile query not immediate RGPE

---

## Decision Rules

### Gate Pass/Fail Criteria

**Tier 0 Gate:**
- All of V01, V02, V03, V04-T0, V05, V14 must PASS
- V16 audit must PASS for all validators
- Zero broken tests in CI
- Verdict: PASS / FAIL (no INCONCLUSIVE)

**Tier 1 Gate:**
- All of V04-T1, V06, V09 must PASS
- V11 may be INCONCLUSIVE (opt-in features don't block)
- V16 audit must PASS
- Zero broken tests in CI
- Verdict: PASS / FAIL / CONDITIONAL (if opt-in features inconclusive)

**Tier 2 Gate:**
- All of V10, V13, (V12/V15 if implemented) must PASS
- V16 audit must PASS
- Zero broken tests in CI
- Verdict: PASS / FAIL

### Demotion Rules (Pre-Committed)

**Source:** BUILD_PROGRAM_v2.md lines 252-256

1. **V04-T1 failure:** Defer population line (BG-PBT depends on TR), reassess Tier 2 scope
   - **Status:** TRIGGERED (2026-09-04)
   - **Action:** TuRBO/BG-PBT moved to Tier 2, conditional on V04-T1 fix

2. **V11 weak effects:** Demote πBO/PriorBand to opt-in
   - **Status:** TRIGGERED (2026-09-04)
   - **Action:** πBO/PriorBand marked opt-in in Tier 1 corrected scope

### Validation Verdict Interpretation

**PASS:** Claim validated, feature approved for tier  
**FAIL:** Claim rejected, apply demotion rule or remove feature  
**INCONCLUSIVE:** Insufficient evidence, apply demotion rule or upgrade protocol  

### Context Drift Recovery

**Problem:** User observed "whenever we compact context, we start to drift"  

**Solution:** This master program document

**Recovery Protocol:**
1. Read `HPO_NAS_RECOVERY_MASTER_PROGRAM.md` (this file) FIRST after context compaction
2. Check "Current Phase Marker" section for last completed work
3. Continue from "NEXT TASK" in phase marker
4. Update phase marker after completing each day's work
5. Never start a task from earlier phase if marker says it's complete

**Phase Marker Update Template:**

```markdown
**PHASE:** [Week X: Phase Name]  
**WEEK:** [1-4]  
**DAY:** [1-7]  
**LAST COMPLETED:** [Task name from schedule]  
**NEXT TASK:** [Next task name from schedule]  
**DATE:** [YYYY-MM-DD]
```

---

## Risk Register

### Risk 1: V04-T1 Cannot Be Fixed

**Probability:** Medium  
**Impact:** High (removes TuRBO/BG-PBT from roadmap)  

**Mitigation:**
- Week 3 Day 1-3: Power analysis determines if protocol underpowered
- If protocol adequate: audit Sobol implementation against scipy.stats.qmc.Sobol
- If implementation correct: accept demotion, document Tier 2 scope without TR/population

**Decision point:** End of Week 3

### Risk 2: Timeline Still Doesn't Reconcile

**Probability:** Medium  
**Impact:** High (approval blocked)  

**Mitigation:**
- Week 1 Day 1-3: Work breakdown spreadsheet with explicit arithmetic
- Include contingency (20-30%) in estimates
- Cut scope if arithmetic forces it (move features to Tier 3 or research flags)

**Decision point:** End of Week 1

### Risk 3: Traceability Matrix Reveals More Violations

**Probability:** High (only 15+ documented, likely more exist)  
**Impact:** Medium (extends Week 4 implementation time)  

**Mitigation:**
- Week 1 Day 4-6: Exhaustive audit of all algorithms
- Document ALL violations in matrix
- Prioritize fixes: Tier 0/1 first, Tier 2 second
- Accept some violations may require Tier 2+ deferral

**Decision point:** End of Week 1

### Risk 4: Conformance Tests Reveal Contract Gaps

**Probability:** High (contracts never formalized before)  
**Impact:** Medium (extends Week 2 implementation time)  

**Mitigation:**
- Week 2 Day 1-5: Implement tests incrementally, surface gaps early
- Week 2 Day 6-7: Document all missing semantics in CONTRACT_SEMANTICS_v1.md
- Accept some semantics may require architecture spike (add to Tier 0)

**Decision point:** End of Week 2

### Risk 5: V01-V15 Protocol Repair Takes Longer Than 3 Days

**Probability:** Medium (15 validations, some complex)  
**Impact:** Low (can extend to Week 3 Day 4 if needed, steal time from test pyramid)  

**Mitigation:**
- Week 3 Day 1-3: Use protocol template, parallelize where possible
- Focus on Tier 0/1 validations first (V01-V06, V09, V11)
- Tier 2 protocols (V10, V12, V13, V15) can be rougher drafts

**Decision point:** End of Week 3 Day 3

---

## Success Criteria

### Week 1 Success

- [ ] WORK_BREAKDOWN_v3.xlsx arithmetic reconciles (no contradictions)
- [ ] TRACEABILITY_MATRIX_v1.md documents all 15+ violations
- [ ] NAS_SCOPE_DECISION.md records scope decision
- [ ] Checklist items 1, 2, 3, 5 satisfied

### Week 2 Success

- [ ] tests/conformance/ has 5 passing test files (searcher, scheduler, executor, store, checkpoint)
- [ ] CONTRACT_SEMANTICS_v1.md defines all 6 missing semantics
- [ ] Checklist items 8 (partial), 9, 10 satisfied

### Week 3 Success

- [ ] validation/protocols/ has v01-v15 protocol files
- [ ] validation/validators/base_validator.py implements V16 audit
- [ ] TEST_PYRAMID_v1.md documents three layers
- [ ] Checklist items 6, 7, 8 (complete) satisfied

### Week 4 Success

- [ ] BUILD_PROGRAM_v3.md has corrected Tier 0/1/2/distributed-beta scope
- [ ] APPROVAL_CHECKLIST_v1.md shows all 12 items satisfied
- [ ] APPROVAL_REQUEST_v1.md submitted
- [ ] All 12 checklist items satisfied

### Final Success (Approval Granted)

- [ ] BUILD_PROGRAM status: RED → CONDITIONAL APPROVAL
- [ ] Zero blocking findings remain
- [ ] Tier 0 remediation ready to execute
- [ ] All deliverables archived and version-controlled

---

## Communication Protocol

### Stakeholder Updates

**Frequency:** End of each week  
**Format:** Email + attached gate report  
**Content:**
- Week completed
- Deliverables produced (with file paths)
- Checklist items satisfied this week
- Risks surfaced
- Next week plan

### Gate Reports

**Trigger:** After each validation campaign or gate decision  
**Format:** Markdown file  
**Content:**
- Gate name (Tier 0 / Tier 1 / Tier 2)
- Validations executed
- Pass/fail/inconclusive verdicts
- Demotion rules triggered
- Artifacts produced
- Gate verdict (PASS / FAIL / CONDITIONAL)

### Issue Escalation

**Trigger:** Any blocking issue or risk materialization  
**Channel:** Immediate notification  
**Content:**
- What's blocked
- Why it's blocked
- Options for resolution
- Recommendation
- Decision needed by (date)

---

## Appendix A: Full 12-Item Checklist Detail

**Source:** BUILD_PROGRAM_REVIEW_VERDICT.md lines 314-330

### Item 1: Scope Clarity

**Requirement:** Scope says moderate architecture-coordinate NAS or supplies separately approved general-NAS plan.

**Deliverable:** NAS_SCOPE_DECISION.md (Week 1 Day 7)

**Acceptance Criteria:**
- Decision recorded: moderate architecture coordinates (2-10 knobs) OR general NAS with separate approval
- Workload templates match scope decision
- LaTeX specification updated if needed
- No ambiguity remains about supported search space types

**Evidence:**
- [ ] NAS_SCOPE_DECISION.md exists
- [ ] BUILD_PROGRAM_v3.md scope section matches decision
- [ ] Workload templates updated (Item 12)

---

### Item 2: One Tier/Test Mapping

**Requirement:** Governing LaTeX, product register, build program, README, progress tracker have one tier/test mapping.

**Deliverable:** TRACEABILITY_MATRIX_v1.md (Week 1 Day 4-6)

**Acceptance Criteria:**
- No validation appears in multiple tiers across documents
- Every algorithm in LaTeX has exactly one implementation
- Every implementation has exactly one test suite
- Every claim has exactly one validation campaign
- No contradictions between BUILD_PROGRAM_v3.md and LaTeX

**Evidence:**
- [ ] TRACEABILITY_MATRIX_v1.md exists
- [ ] Matrix shows 1:1 mappings (no duplicates)
- [ ] All documents audited for consistency

---

### Item 3: Reconciled Arithmetic

**Requirement:** Timeline math and campaign capacity reconcile with named staffing and contingency.

**Deliverable:** WORK_BREAKDOWN_v3.xlsx (Week 1 Day 1-3)

**Acceptance Criteria:**
- sum(task effort) + contingency = total eng-days claimed
- longest-path(dependencies) with parallelism = calendar weeks claimed
- sum(GPU-days) ≤ available GPU capacity
- Staff is named ("Alice, Bob" not "2 FTE")
- Contingency explicit (20-30% for unknowns)
- No contradictions between effort/duration/calendar/staff

**Evidence:**
- [ ] WORK_BREAKDOWN_v3.xlsx exists
- [ ] Arithmetic verified (no contradictions)
- [ ] Staffing named
- [ ] Contingency explicit

---

### Item 4: Tier 0 Completeness

**Requirement:** Tier 0 includes GP+qLogEI, required defaults, both adapters, functional day-one workload, or LaTeX amended.

**Deliverable:** BUILD_PROGRAM_v3.md Tier 0 section (Week 4 Day 1-2)

**Acceptance Criteria:**
- GP+qLogEI baseline implemented (reference searcher)
- Required defaults defined: initial_random_samples, kernel, acquisition optimizer
- LocalExecutor and RayExecutor implemented
- rl_routine workload (9-knob RL) functional with jax/brax
- OR: LaTeX explicitly amended to remove above requirements

**Evidence:**
- [ ] BUILD_PROGRAM_v3.md Tier 0 section lists all components
- [ ] Implementation files exist or LaTeX amended
- [ ] V01-V05, V14 protocols reference Tier 0 components

---

### Item 5: Algorithm Descriptions Match Authorization

**Requirement:** piBO, PriorBand, warm start, BG-PBT, ifBO descriptions match methods actually authorized.

**Deliverable:** TRACEABILITY_MATRIX_v1.md + BUILD_PROGRAM_v3.md (Week 1 Day 4-6 + Week 4 Day 3)

**Acceptance Criteria:**
- πBO: acquisition multiplier NOT GP mean (LaTeX match)
- PriorBand: portfolio sampler NOT top-K (LaTeX match)
- ifBO: pretrained surrogate NOT custom power-law (LaTeX match)
- Warm-start: ranked/quantile query NOT immediate RGPE (LaTeX match)
- BG-PBT: description matches LaTeX (no additional violations)

**Evidence:**
- [ ] TRACEABILITY_MATRIX_v1.md documents violations as status=❌
- [ ] BUILD_PROGRAM_v3.md algorithm descriptions corrected
- [ ] Implementation fixes planned (Tier 1 Day X or later)

---

### Item 6: Preregistered Validations

**Requirement:** V01-V15 have preregistered tasks, seeds, margins, power/repetition policy, analysis, decision states, immutable artifacts.

**Deliverable:** validation/protocols/v01-v15_protocol.md (Week 3 Day 1-3)

**Acceptance Criteria:**
- Each validation has protocol file following template
- Tasks: preregistered benchmark names (held-out, not training)
- Seeds: exact seeds listed (e.g., 42, 123, 456, 789, 1011)
- Margins: equivalence margin or superiority threshold with justification
- Alpha: significance level (Bonferroni-corrected if multiple comparisons)
- Power: target power documented (typically 0.8)
- Sample size: trials/seed, seeds, total studies calculated
- Analysis: statistical test named (paired t-test, TOST, Wilcoxon, etc.)
- Decision states: PASS/FAIL/INCONCLUSIVE criteria explicit
- Immutable artifacts: protocol file frozen, results write-once

**Evidence:**
- [ ] validation/protocols/ has v01-v15_protocol.md files
- [ ] Each protocol follows template structure
- [ ] V16 audit can verify all fields present

---

### Item 7: Equivalence Tests

**Requirement:** Non-inferiority/equivalence replaces "CI overlaps zero" wherever safety or matching is claimed.

**Deliverable:** validation/protocols/ updated (Week 3 Day 1-3)

**Acceptance Criteria:**
- Any claim "method A matches method B" uses TOST (two one-sided tests) not overlap test
- Any claim "method A not worse than B" uses non-inferiority test
- Equivalence margin (delta) preregistered and justified
- No validation uses "CI overlaps zero" as pass criterion

**Evidence:**
- [ ] Grep validation/protocols/ for "overlaps zero" → zero hits
- [ ] V01 (vendor parity) uses TOST
- [ ] V06 (ASHA efficiency) uses equivalence test if claiming "matches full-fidelity"
- [ ] All safety/matching claims use proper equivalence tests

---

### Item 8: Deterministic Tests Below Statistical Campaigns

**Requirement:** Deterministic unit/property/conformance/recovery tests exist below statistical campaigns.

**Deliverable:** tests/ directory + TEST_PYRAMID_v1.md (Week 2 Day 1-5 + Week 3 Day 4-5)

**Acceptance Criteria:**
- Layer 1 (unit/property/conformance): >100 tests, <1 sec runtime each
- Layer 2 (integration/recovery/scale): >20 tests, <60 sec runtime each
- Layer 3 (statistical campaigns): 15 tests (V01-V15), minutes to hours
- All Layer 1/2 tests deterministic (given seed)
- All Layer 1/2 tests in CI (run on every commit/PR)
- pytest passes with >80% line coverage

**Evidence:**
- [ ] tests/unit/ exists with >50 tests
- [ ] tests/property/ exists with >20 tests
- [ ] tests/conformance/ exists with 5 contract tests
- [ ] tests/integration/ exists with >10 tests
- [ ] tests/recovery/ exists with >5 tests
- [ ] tests/scale/ exists with >5 tests
- [ ] TEST_PYRAMID_v1.md documents structure
- [ ] CI runs all Layer 1/2 tests

---

### Item 9: Package Infrastructure

**Requirement:** Package, environment locks, provenance, CI, migrations, clean-install tests exist.

**Deliverable:** Repository infrastructure (Week 2 + ongoing)

**Acceptance Criteria:**
- Package: setup.py or pyproject.toml with all dependencies
- Environment locks: requirements.txt or poetry.lock pinned versions
- Provenance: git hash in version string, build metadata
- CI: GitHub Actions or equivalent runs tests on every commit
- Migrations: Schema versioning for checkpoint format
- Clean-install test: Dockerfile or script that installs from scratch

**Evidence:**
- [ ] pyproject.toml or setup.py exists
- [ ] requirements.txt or poetry.lock with pinned versions
- [ ] .github/workflows/ or .gitlab-ci.yml exists
- [ ] Version string includes git hash
- [ ] Schema migration documented in CONTRACT_SEMANTICS_v1.md
- [ ] Dockerfile or install_test.sh exists

---

### Item 10: Store/Control-Plane Semantics

**Requirement:** Store/control-plane semantics survive concurrency, duplicate events, restart.

**Deliverable:** CONTRACT_SEMANTICS_v1.md + tests/conformance/test_store_recovery.py (Week 2 Day 6-7 + Day 1-5)

**Acceptance Criteria:**
- Schema migration: versioning scheme, forward/backward compatibility
- Stable IDs: trial/study ID generation, uniqueness, persistence
- Event ordering: concurrent observe, suggest/observe race, out-of-order arrival
- NaN/inf handling: policy for NaN/inf in objective or config
- Failure policy: crashed trial, partial observations, unreachable executor
- Checkpoint format: required fields, serialization format
- All policies tested in tests/conformance/test_store_recovery.py

**Evidence:**
- [ ] CONTRACT_SEMANTICS_v1.md defines all 6 semantics
- [ ] tests/conformance/test_store_recovery.py tests concurrency
- [ ] tests/conformance/test_store_recovery.py tests duplicate events
- [ ] tests/conformance/test_checkpoint_resume.py tests restart

---

### Item 11: Distributed Hardening

**Requirement:** Distributed scale, fault, monitoring, hard-budget gates mandatory before broad internal use.

**Deliverable:** BUILD_PROGRAM_v3.md Distributed-Beta section (Week 4 Day 5)

**Acceptance Criteria:**
- Persistent store: PostgreSQL or DynamoDB backend (not in-memory)
- Backup/restore: snapshot + point-in-time recovery tested
- Monitoring: metrics (latency, throughput, error rate), alerts configured
- Scale testing: 100+ concurrent studies, 1000+ trials, passes
- Security audit: authentication, authorization, secrets management reviewed
- Hard-budget gates: cost limits, quota enforcement implemented
- All gates PASS before broad internal use

**Evidence:**
- [ ] BUILD_PROGRAM_v3.md lists all 6 components
- [ ] Effort estimate for each component (13 days total)
- [ ] Gate criteria defined (scale/fault/monitoring/budget tests)
- [ ] Distributed-Beta tier separate from Tier 0/1/2

---

### Item 12: Workload Templates

**Requirement:** Each supported workload (including finance if retained) has maintained template and held-out acceptance task.

**Deliverable:** workloads/ directory (Week 1 Day 7 + ongoing)

**Acceptance Criteria:**
- rl_routine: 9-knob RL proxy, jax/brax, template script, held-out task
- (finance workload if retained): template script, held-out task
- (any other supported workload): template script, held-out task
- Template: runnable script showing how to use HPO-NAS on that workload
- Held-out task: benchmark NOT used in any V01-V15 validation
- Maintained: template kept up-to-date with API changes

**Evidence:**
- [ ] workloads/rl_routine/template.py exists
- [ ] workloads/rl_routine/heldout_task.json exists
- [ ] If finance retained: workloads/finance/ exists with template + heldout
- [ ] NAS_SCOPE_DECISION.md lists all supported workloads
- [ ] Each workload has README with usage instructions

---

## Appendix B: Governance Integration

**Source:** governance.md lines 1-50

### Relationship to Existing Governance

This recovery program (HPO_NAS_RECOVERY_MASTER_PROGRAM.md) is a **temporary governance document** for the 4-week recovery period.

**After recovery completes:**
- BUILD_PROGRAM_v3.md becomes the authoritative plan (replaces BUILD_PROGRAM_v2.md)
- governance.md system (decisions.json → generator → BUILD_PROGRAM) resumes
- This recovery program archived as historical context

### Generator Tool Integration

**Post-recovery:**
- Week 1 deliverables (WORK_BREAKDOWN_v3.xlsx, TRACEABILITY_MATRIX_v1.md) become inputs to generator
- Week 3 deliverables (validation/protocols/) become validation.tex input
- BUILD_PROGRAM_v3.md validated as output of generator(inputs)
- Any future changes go through generator, not manual edit

### Drift Prevention Post-Recovery

**Mechanisms:**
1. **Single source of truth:** BUILD_PROGRAM_v3.md (generator output)
2. **Immutable artifacts:** validation/results/ write-once, never modified
3. **Preregistration:** validation/protocols/ frozen before campaign
4. **Version control:** git tracks all changes, requires review
5. **V16 audit:** catches post-hoc tuning and vacuous validators
6. **Traceability matrix:** LaTeX ↔ BUILD_PROGRAM consistency enforced

---

## Appendix C: Cost Estimate

### Recovery Program Cost (4 Weeks)

**Assumptions:**
- 1 senior engineer full-time
- No GPU compute during recovery (planning phase only)
- CI infrastructure already exists

**Cost Breakdown:**

| Week | Days | Tasks | Engineer-Days |
|------|------|-------|---------------|
| 1 | 7 | Specification reconciliation | 7 |
| 2 | 7 | Contract & risk spikes | 7 |
| 3 | 7 | Validation protocol repair | 7 |
| 4 | 7 | Rebaselined program v3.0 | 7 |
| **Total** | **28** | | **28 eng-days** |

**Calendar Time:**
- Single engineer: 4 weeks (28 calendar days)
- Two engineers (parallelized): 2-3 weeks (dependencies limit parallelism)

### Post-Recovery Execution Cost

**From BUILD_PROGRAM_v3.md (to be created):**

| Phase | Days | Notes |
|-------|------|-------|
| Tier 0 remediation | 17 | From BUILD_PROGRAM_v2.md, unchanged |
| Tier 1 execution | 29 | Corrected scope (Week 4 Day 3) |
| Tier 2 execution | 21 | Conditional on V04-T1 resolution |
| Distributed-Beta | 13 | Week 4 Day 5 estimate |
| **Total** | **80** | **12-16 weeks with parallelism** |

**GPU Cost:**
- From WORK_BREAKDOWN_v3.xlsx (Week 1 Day 1-3)
- To be reconciled during recovery

### Total Program Cost

**Recovery + Execution:**
- 28 days recovery + 80 days execution = 108 eng-days
- ~22 weeks calendar time (5.5 months) with 1-2 engineers
- Plus GPU costs (to be reconciled in Week 1)

---

## Appendix D: Session Continuity After Compaction

### Problem Statement

User observation: "I notice that whenever we compact context, we start to drift."

**Examples of drift:**
- Executing Tier 1 validations while Tier 0 blocked
- Re-discovering V10/V13 deferrals multiple times
- Losing track of demotion rules and consequences
- Forgetting 12-item approval checklist requirements

### Root Cause

Context compaction loses:
- Current task state (what was just completed, what's next)
- Decision context (why a choice was made)
- Detailed requirements (exact acceptance criteria)
- File paths and artifact locations
- Cross-references between documents

### Solution: This Master Program

**Design Principles:**

1. **Self-contained:** All details in one file, no external dependencies
2. **Phase marker:** Explicit "Current Phase Marker" tracks progress
3. **Complete schedule:** Day-by-day tasks with acceptance criteria
4. **Full context:** Algorithm specs, file paths, validation details, decision rules
5. **Recovery protocol:** Explicit instructions for post-compaction resume

### Recovery Checklist (Post-Compaction)

After context compaction, agent must:

1. [ ] Read HPO_NAS_RECOVERY_MASTER_PROGRAM.md FIRST (before any other file)
2. [ ] Check "Current Phase Marker" section
3. [ ] Read "LAST COMPLETED" to understand what's done
4. [ ] Read "NEXT TASK" to understand what to do next
5. [ ] Read relevant week/day section for task details
6. [ ] Execute task following acceptance criteria
7. [ ] Update "Current Phase Marker" after completion
8. [ ] Commit updated master program to git

**NEVER:**
- Start from the beginning if phase marker shows progress
- Re-execute completed tasks
- Ignore phase marker and choose task independently
- Assume context from conversation history (it's compacted)

---

## Appendix E: Quick Reference

### Key Numbers

- **Recovery duration:** 4 weeks (28 eng-days)
- **Post-recovery execution:** 80 days (12-16 weeks)
- **Total validations:** 16 (V01-V16)
- **Approval checklist:** 12 items
- **Known algorithm violations:** 15+ (πBO, PriorBand, ifBO, warm-start, +11 more)
- **Tier 0 remediation:** 17 days (from BUILD_PROGRAM_v2.md)
- **Test pyramid:** Layer 1 >100 tests, Layer 2 >20 tests, Layer 3 15 campaigns

### Key Dates

- **2026-08-28:** BUILD_PROGRAM_REVIEW_VERDICT.md declared RED
- **2026-09-02:** Tier 0 gate report recorded GATE NOT MET
- **2026-09-04:** Tier 1 validations executed (V06✅ V04-T1❌ V11⚠️), demotion rules triggered
- **2026-09-09:** Recovery program created (this document)
- **TBD:** Recovery start date (user approval needed)
- **TBD + 4 weeks:** Recovery complete, approval request submitted

### Key Files (Absolute Paths)

**Current:**
- `/home/ubuntu/workspace/hponas/HPO_NAS_RECOVERY_MASTER_PROGRAM.md` - This file
- `/home/ubuntu/workspace/hponas/BUILD_PROGRAM_v2.md` - Current program (RED)
- `/home/ubuntu/workspace/hponas/BUILD_PROGRAM_REVIEW_VERDICT.md` - Review verdict
- `/home/ubuntu/workspace/hponas/TIER1_GATE_STATUS.md` - Tier 1 results
- `/home/ubuntu/workspace/hponas/SESSION_PROGRESS_REPORT_2026-09-04.md` - Session log

**To be created:**
- `/home/ubuntu/workspace/hponas/BUILD_PROGRAM_v3.md` - Corrected program (Week 4)
- `/home/ubuntu/workspace/hponas/WORK_BREAKDOWN_v3.xlsx` - Timeline (Week 1)
- `/home/ubuntu/workspace/hponas/TRACEABILITY_MATRIX_v1.md` - Specs (Week 1)
- `/home/ubuntu/workspace/hponas/CONTRACT_SEMANTICS_v1.md` - Semantics (Week 2)
- `/home/ubuntu/workspace/hponas/TEST_PYRAMID_v1.md` - Test design (Week 3)

### Key Commands

**Start recovery:**
```bash
# Update phase marker to Week 1 Day 1
# Begin work breakdown spreadsheet
```

**Check progress:**
```bash
grep "Current Phase Marker" -A 5 HPO_NAS_RECOVERY_MASTER_PROGRAM.md
```

**List deliverables:**
```bash
grep "Deliverable:" HPO_NAS_RECOVERY_MASTER_PROGRAM.md
```

**Check checklist:**
```bash
grep "\[ \]" HPO_NAS_RECOVERY_MASTER_PROGRAM.md | head -20
```

---

## Version History

**v1.0 - 2026-09-09**
- Initial master recovery program
- 4-week schedule with day-by-day tasks
- 12-item approval checklist detailed
- Algorithm specifications corrected
- Validation details documented
- Recovery protocol established
- Created in response to user observation of context drift

---

## Document Status

**Status:** DRAFT (awaiting user approval to begin recovery)  
**Owner:** HPO-NAS Build Program  
**Reviewers:** (TBD)  
**Approval:** Required before recovery execution begins  
**Version:** 1.0  
**Last Updated:** 2026-09-09  

**Next Actions:**
1. User reviews this master program document
2. User approves or requests changes
3. Upon approval, update "Current Phase Marker" to Week 1 Day 1
4. Begin recovery execution

---

**END OF MASTER PROGRAM**