# R0: Specification Correction Phase
**Status:** IN PROGRESS  
**Started:** 2026-08-28  
**Duration:** 2 weeks  
**Owner:** Implementation team

---

## Phase objectives

1. Fix LaTeX validation statistics (non-inferiority vs CI-overlap, power analysis, sampling hierarchy)
2. Reconcile survey vs BUILD_PROGRAM scope mismatches (13 material deviations identified)
3. Decide NAS boundary explicitly (moderate architecture coordinates only, or out of scope)
4. Rebuild timeline from work-breakdown with contingency
5. Generate traceability matrix from survey decision boxes
6. Correct V01-V15 protocols with statistical reviewer input
7. Produce corrected BUILD_PROGRAM_v2 specification

---

## Week 1 tasks

### Task 1.1: NAS scope decision (CRITICAL PATH)
**Owner:** Project sponsor + technical lead  
**Deadline:** Day 3  
**Status:** DECISION REQUIRED

**Question:** Is the product:
- **Option A:** HPO with moderate architecture coordinates (width/depth/flags only), OR
- **Option B:** General large-scale NAS (requires new governing document)

**Evidence from survey (09-workloads.tex:234-270, 12-roadmap.tex:151-160):**
- Survey explicitly supports "width, depth, and a few structural flags included as ordinal and categorical axes"
- Explicitly excludes: topology search, one-shot supernets, DARTS-style differentiable NAS, grammar spaces, zero-cost proxy subsystem
- Rationale: "covers every architecture question our current projects actually ask, at a small fraction of the complexity"

**Recommendation:** Option A (moderate architecture coordinates)
- Matches survey evidence base
- Serves stated users (RL with BG-PBT, Hamiltonian networks)
- Deliverable within corrected timeline
- General NAS (Option B) requires separate 6-12 month scoping/survey effort

**Decision needed:** Approve Option A, or STOP for new governing document

**Action after decision:**
- [ ] Document scope boundary in survey (new subsection in 09-workloads.tex)
- [ ] Add architecture contracts to 15-contracts.tex (typed axes, validity, construction)
- [ ] Add architecture support to BG-PBT work breakdown (factory, compatibility, distillation)

---

### Task 1.2: Hire/assign statistical reviewer
**Owner:** Project lead  
**Deadline:** Day 5  
**Status:** NOT STARTED

**Requirements:**
- Background in experimental design, hypothesis testing, bootstrap/resampling methods
- Familiar with HPO/AutoML evaluation methodology (or willing to read Eimer et al. 2023)
- Available for 10-15 hours over 2 weeks (protocol review + iteration)

**Scope of work:**
- Review current V01-V15 protocols in survey sections/16-validation.tex
- Flag statistical errors (non-inferiority vs CI-overlap, power, sampling hierarchy, multiplicity)
- Review corrected protocols before campaign execution

**Deliverable:** Statistical reviewer assigned with availability confirmed

---

### Task 1.3: Begin LaTeX validation corrections
**Owner:** Survey author + statistical reviewer (once assigned)  
**Deadline:** End of week 1 (draft), end of week 2 (final)  
**Status:** NOT STARTED

**Files to correct:** hpo-survey/sections/16-validation.tex

**Specific corrections required:**

#### 1. Non-inferiority/equivalence (lines 165-175)
**Current (WRONG):**
```
"Within noise" (V06, V11): The 95% bootstrap confidence interval of the 
difference in means overlaps zero.
```

**Corrected:**
```
"Within noise" (V06, V11): The 95% bootstrap confidence interval of the 
difference in means lies entirely within the preregistered equivalence margin 
[-δ, +δ]. For V06, δ = 5% of full-fidelity final quality (the minimum 
practically important difference). For V11, δ = 10% of no-prior baseline 
performance. A CI overlapping zero without falling within the margin is 
inconclusive, not evidence of equivalence.
```

#### 2. Power and repetition policy (lines 127-139)
**Current (INCOMPLETE):**
```
At least ten repetitions of every comparison, reported as 
performance-over-budget curves with uncertainty bands.
```

**Corrected:**
```
Every layer-two comparison runs a minimum of ten repetitions unless a pilot 
variance estimate and preregistered minimum detectable effect justify fewer. 
The protocol may specify adaptive sequential analysis with a maximum sample 
size; if the maximum is reached without reaching a decision threshold, the 
result is recorded as "inconclusive at budgeted precision" rather than forced 
to a binary claim. Pilot variance estimates are recorded before full campaigns 
and are not updated during the campaign.
```

#### 3. Sampling hierarchy (NEW SECTION after line 199)
**Add:**
```
\subsection{Sampling levels and paired designs}

HPO comparisons have multiple sampling levels: tuning-run seeds, workload 
training seeds, evaluation seeds, task selection, and configuration draws. 
Analysis must match the hierarchy to avoid pseudoreplication. Where valid, 
use paired designs: common random seeds across methods, common task/environment 
instances, and common baseline configurations. Uncertainty is computed via 
hierarchical bootstrap: resample complete tuning runs with replacement, then 
compute the statistic of interest on each bootstrap sample, taking empirical 
percentiles over 10,000 iterations.
```

#### 4. Development vs held-out tasks (NEW SECTION after sampling hierarchy)
**Add:**
```
\subsection{Development and acceptance tasks}

Each workload family has development tasks used during implementation and 
informal testing, plus held-out acceptance tasks used only in gate campaigns. 
Development tasks are specified in week 1 of Tier 0; acceptance tasks are 
selected by an engineer not involved in the implementation, revealed only at 
gate time, and recorded in the immutable gate manifest. Task rotation follows 
a versioned process: new tasks enter development after a full tier completes, 
and old development tasks may migrate to acceptance in the next tier. This 
protocol bounds in-sample overfitting to the validation set itself.
```

#### 5. Multiplicity control (NEW SECTION)
**Add:**
```
\subsection{Multiple comparisons}

V04 tests several searchers across tasks and budget points; V09 tests multiple 
objectives and comparators. Where multiple hypotheses are tested and ranking 
claims made, predeclare one primary endpoint (the claim the tier's completion 
depends on) and control family-wise error rate at α=0.05 via Holm-Bonferroni 
for secondary comparisons. Purely descriptive comparisons with no release 
decision attached need no correction.
```

#### 6. Budget accounting (lines 171-175)
**Current (IDEALIZED):**
```
"A fraction of compute" (V06): Early stopping reaches the same final quality 
at no more than one-third the total compute of full-fidelity search. Compute 
is measured in full-run equivalents, charging partial runs proportionally.
```

**Corrected:**
```
"A fraction of compute" (V06): Early stopping reaches the same final quality 
at no more than one-third the total compute of full-fidelity search. Compute 
is measured in actual accelerator-seconds and wall-clock time, with full-run 
equivalents reported as a normalized secondary measure. Actual measurement 
includes startup, evaluation, checkpoint, queue wait, and optimizer overhead. 
The one-third threshold applies to accelerator-seconds; if wall-clock differs 
materially due to scheduling, both are reported.
```

#### 7. Artifacts and preregistration (NEW SECTION)
**Add after line 199:**
```
\subsection{Immutable artifacts and preregistration}

Every gate campaign produces an immutable manifest before execution begins, 
containing: protocol version, task checksums (code + data), seed sets, analysis 
script with decision thresholds, environment digest (full dependency versions 
+ hardware), and the signed commit of the code under test. Results are recorded 
in versioned JSON with the manifest hash, stored in the artifact registry (not 
ignored by .gitignore), and cannot be reanalyzed without producing a new 
manifest version. This discipline makes "p-hacking" and "researcher degrees of 
freedom" auditable rather than invisible.
```

**Action items:**
- [ ] Statistical reviewer review current protocols (day 6-7)
- [ ] Draft corrections (day 8-10)
- [ ] Statistical reviewer review corrections (day 11-12)
- [ ] Finalize and commit LaTeX changes (day 13-14)

---

### Task 1.4: Fix V08 green/release semantics
**Owner:** Survey author  
**Deadline:** Day 10  
**Status:** NOT STARTED

**Problem:** V08 is explicitly a falsifier ("consistent loss demotes") but tier 2 completion requires "green." The protocol can reject but cannot promote on 3-rep evidence.

**Current text (16-validation.tex:218-249):**
- 3 reps/arm/side (too low power to confirm)
- Asymmetric stopping: unanimous loss demotes, disagreement reports "unresolved"
- Called a "falsifier" explicitly

**But:** Tier 2 gate presumably requires evidence the population line works, not just "not falsified yet"

**Correction needed:**
Define V08 result states and release semantics:
- `pass`: Evidence the population line does not lose in home regime (requires more than 3 reps, or V08 stays at its initial cautious status)
- `hold`: Unresolved at this budget (disagreement in 3-rep pilot)
- `demote`: Consistent home loss (unanimous across 3 reps)
- `block`: Implementation/correctness failure

**Proposed text change:**
```
V08's initial status is "hold: insufficient evidence." Three-repetition 
unanimous home loss is sufficient to demote the flagship. Promotion to default 
requires a full sequential campaign (maximum 10 reps/arm/side) with 
preregistered non-inferiority margin and decision boundaries. The three-rep 
pilot is a tripwire for early cancellation, not the full validation. Tier 2 
completion requires V08 not in "block" or "demote" state; "hold" is acceptable 
for a late-tier experimental capability.
```

**Action:**
- [ ] Survey author draft V08 semantics correction
- [ ] Review with project sponsor (day 8-9)
- [ ] Commit change to 16-validation.tex (day 10)

---

### Task 1.5: Clarify knob-kind ambiguity (continuous/ordinal/categorical/integer)
**Owner:** Survey author  
**Deadline:** Day 7  
**Status:** NOT STARTED

**Problem:** Product chapter (14-product.tex:48-50) says "four knob kinds" but contracts chapter (15-contracts.tex:58-83) lists three (continuous, ordinal, categorical). Is integer distinct from ordinal?

**Investigation needed:**
- Read 14-product.tex:48-50 and 15-contracts.tex:58-83
- Check if integer is used distinctly anywhere in survey
- Decide: integer is a distinct type, OR integer is ordinal with unit step

**Recommendation:** Integer is ordinal with unit step (simpler, matches BoTorch)

**Action:**
- [ ] Read both sections (day 5)
- [ ] Decide semantics (day 6)
- [ ] Make both sections consistent (day 7)
- [ ] Document in 15-contracts.tex exactly how integers are represented

---

## Week 2 tasks

### Task 2.1: Generate traceability matrix
**Owner:** Technical lead  
**Deadline:** End of week 2  
**Status:** NOT STARTED

**Scope:** Every decision box item from survey chapters 3-9 → contracts, implementation, tests, validation entry, tier, owner, effort, fallback

**Format:** Machine-readable (JSON or CSV) + human-readable (Markdown table)

**Columns:**
- Decision ID (e.g., D-MF-01 for model-free chapter, decision 1)
- Capability (e.g., "Log-scale sampling + Sobol")
- Verdict (e.g., "T0: always on")
- Source (chapter + section + decision box line reference)
- Contract section (15-contracts.tex reference)
- Implementation module (planned, e.g., src/searchers/sobol.py)
- Unit tests (planned module, e.g., tests/test_searchers.py::test_sobol_log_scale)
- Validation entry (e.g., V04, V05)
- Tier (T0/T1/T2/T3)
- Owner (TBD during R1)
- Effort estimate (engineer-days)
- Fallback if demoted (e.g., "opt-in feature", "remove from defaults")

**Process:**
1. Extract all decision boxes from chapters 3-9 (use grep/ripgrep for decision box markers)
2. Cross-reference with Table 12.1 (roadmap decisions)
3. Map to validation entries V01-V15
4. Identify gaps (decision without validation, validation without decision)
5. Flag all current BUILD_PROGRAM deviations

**Deliverable:** traceability-matrix.json + TRACEABILITY.md with human-readable view

**Action:**
- [ ] Extract decision boxes (day 8-9)
- [ ] Map to validation (day 10-11)
- [ ] Generate matrix (day 12-13)
- [ ] Review and flag deviations (day 14)

---

### Task 2.2: Correct V01-V15 individual protocols
**Owner:** Validation lead + statistical reviewer  
**Deadline:** End of week 2  
**Status:** NOT STARTED

**Scope:** Implement every protocol correction from Codex review Table (pages 196-212)

**Per-test rewrites required:**

**V01: Implementation parity**
- Replace "0.5% tolerance + exact rank" with distributional regression
- For stochastic references: test distribution of configs/decisions, not point values
- For deterministic wrappers: exact state-transition comparison under fixed events
- Add: versioned benchmark snapshots, tied-rank policy

**V02: Async correctness**
- Current: replay on recorded curves
- Add: state-machine/property tests for out-of-order, duplicate, late events, stragglers, worker loss, pause/resume, recovery

**V03: Sabotage detection**
- Replace "three planted defects" with mutation testing framework
- Require mutation score ≥80% on contract/state-machine code
- Add mutants: objective direction, inactive conditionals, seed leakage, duplicate observation, checkpoint mismatch, cost accounting

**V04: Searcher earns complexity**
- Define capability-specific home regimes (not "beats Sobol everywhere")
- Separate tests: GP+qLogEI vs random, TPE vs random, TuRBO vs log+Sobol
- Multiple development + held-out tasks per regime
- Non-inferiority margins per regime
- Inconclusive state if margin not met

**V05: Transform effectiveness**
- Replace "must not lose" with positive material gain on scale-sensitive tasks
- Non-inferiority across broad tasks
- Define exact input/output transform and invalid-domain behavior

**V06: ASHA nearly free**
- Replace CI-overlap with quality non-inferiority margin
- Actual cost accounting (not just full-run-equivalents)
- Performance-over-budget curves
- Test slow-starter recall (don't just average)
- Multiple tasks with different fidelity definitions

**V07: Small-budget RL**
- Test at low/mid budget points (not just exactly 16 runs)
- Multiple tasks or held-out ARLBench set
- Include random/TPE floor
- Paired seeds, overhead measured
- Explicit win/tie/inconclusive decision rules

**V08: Population home regime**
- Define initial status ("hold: insufficient evidence")
- Test both sides of boundary (e.g., 4 workers and 8/16 workers)
- Matched compute AND wall-time endpoints
- Multiple tasks
- Non-inferiority margin
- Sequential maximum sample (3-rep is early-stop tripwire only)

**V09: Premium MO earns tier**
- Freeze direction, normalization, feasibility, reference point from domain bounds
- Use paired differences with non-inferiority
- Include NSGA-II wrapper as comparator
- Test finance workload if retained in scope

**V10: Cheap fidelity culling**
- Multiple seeds/tasks, out-of-sample configs
- Gate on top-k/Pareto survivor recall AND false-cull probability (not just correlation)
- Measure regret from false culls
- Select rung before acceptance data

**V11: Priors safe to default**
- Test actual πBO decaying multiplier (not GP mean substitution)
- Test actual PriorBand rung portfolio (not top-K sampling)
- Require nonzero support guard
- Predefine early-gain margin (good prior) and worst-case recovery margin (wrong prior)
- Report regret over budget

**V12: Warm start pays**
- Define task/space compatibility rules, prevent leakage
- Leave-one-study-out or leave-one-task-out evaluation
- Freeze target before observing new study
- Measure cost/time-to-target with uncertainty (not just trial count)
- Keep `not_eligible` state until real history exists (no synthetic history)

**V13: Sampler correctness**
- Use SBC (simulation-based calibration) fixtures where possible
- Rank-normalized R-hat plus bulk and tail ESS
- MCSE-aware two-sample comparisons with multiplicity control
- Explicit variance/distribution agreement metrics (not just one-SE mean comparison)
- Automated mode diagnostics (not visual/subjective)
- Separate scheduler veto unit tests from scientific validation

**V14: Day-one walk**
- Build one real `rl_routine` in Tier 0 (not NotImplementedError stub)
- Specify every asserted artifact
- Test that test seeds never reach searcher
- Use replay/audit or censoring-aware diagnostics for stopped trials
- Reproduce full walk from 14-product.tex:60-125

**V15: ifBO feasibility**
- Split into two sub-tests:
  - V15a (pre-build): Published pretrained ifBO model matches/beats ASHA on curve-informative benchmarks
  - V15b (post-integration): Adapter parity, overhead, recovery after integration
- Cancel integration if V15a fails (this is the go/no-go gate)

**Action:**
- [ ] Statistical reviewer + validation lead draft all 15 corrections (day 8-12)
- [ ] Technical review (day 13)
- [ ] Commit to 16-validation.tex (day 14)

---

### Task 2.3: Rebuild timeline from work breakdown
**Owner:** Project lead + technical leads  
**Deadline:** End of week 2  
**Status:** NOT STARTED

**Process:**
1. Start from traceability matrix (task 2.1 output)
2. For each decision/capability, estimate:
   - Implementation effort (engineer-days)
   - Test development (unit/property/conformance)
   - Validation campaign (if applicable)
3. Add missing items flagged by Codex review:
   - GP+qLogEI with dimension-scaled priors (T0, ~5d implementation + 2d tests)
   - Local executor adapter (T0, ~3d)
   - CMA-ES wrapper (T0 or T3, ~2d)
   - PASHA scheduler (T0, ~2d)
   - Chebyshev scalarization (T1, ~2d)
   - NSGA-II wrapper (T1, ~2d)
   - EI-per-cost acquisition (T1, ~4d)
   - Architecture factory if NAS in scope (T2, ~5d)
   - Distillation protocol if NAS in scope (T2, ~6d)
   - Correct πBO implementation (T1, +2d over current plan)
   - Correct PriorBand implementation (T1, +1d)
   - Pretrained ifBO adoption (T3, ~3d, not building new model)
4. Add test-layer infrastructure:
   - Contract/unit test framework (~3d)
   - Property/state-machine test framework (~4d)
   - Store migration tests (~2d)
   - Adapter conformance suite (~3d)
   - Fault injection framework (~5d)
   - Artifact registry + manifest tooling (~3d)
5. Add distributed hardening workstream:
   - Coordinator crash recovery (~4d)
   - Idempotent event handling (~3d)
   - Store serialization (SQLite writer) or Postgres migration (~5d)
   - Monitoring/alerting (~4d)
   - Hard budget controls (~3d)
   - Scale tests (~3d)
   - Security review scope (~2d)
6. Map dependencies
7. Assign to engineer profiles (backend, ML, infra)
8. Calculate critical path
9. Add 30% integration contingency, 15% operational contingency
10. Generate calendar with realistic utilization (not 100%)

**Deliverable:** work-breakdown.xlsx + timeline-gantt.png + effort-summary.md

**Preliminary estimates (will be refined):**
- R0 (spec): 2 weeks (current phase)
- R1 (spike): 2-3 weeks
- Tier 0: 8-10 weeks (not 6)
- Tier 1: 8-10 weeks (not 6)
- Tier 2: 14-18 weeks (not 18, but more realistic sub-phasing)
- Distributed hardening: 4-5 weeks (new, mandatory)
- Tier 3 (per item): 3-5 weeks each, post-week-35
- **Total to internal beta: 38-46 calendar weeks from R0 start**

**Action:**
- [ ] Technical leads review traceability matrix and estimate effort (day 10-12)
- [ ] Project lead build work breakdown with dependencies (day 13)
- [ ] Generate timeline with contingency (day 14)

---

### Task 2.4: Regenerate product_register.json
**Owner:** Survey author  
**Deadline:** End of week 2  
**Status:** NOT STARTED

**Problem:** Current product_register.json is stale (DEHB/ifBO listed as T2, not T3; all workloads collapsed into one malformed RL row)

**Requirements:**
- One row per decision from Table 12.1 (roadmap)
- Tier assignments match corrected survey
- Workload rows separate (RL, Hamiltonian, sampler, finance-if-in-scope)
- Anchors field populated (which validation entries gate this decision)
- Schema version + generation timestamp

**Action:**
- [ ] Write generation script from 12-roadmap.tex Table 12.1 (day 11-12)
- [ ] Generate product_register_v2.json (day 13)
- [ ] Validate against traceability matrix (day 14)

---

## Exit criteria for R0

R0 is complete when ALL of the following are true:

- [ ] NAS scope decided explicitly (moderate arch coordinates, or out of scope)
- [ ] Statistical reviewer assigned and available
- [ ] LaTeX validation corrections drafted and reviewed
- [ ] V08 green/release semantics clarified
- [ ] Knob-kind ambiguity resolved
- [ ] Traceability matrix generated (decision → implementation → tests → validation)
- [ ] All 15 V-test protocols corrected per Codex review
- [ ] Timeline rebuilt from work breakdown with contingency
- [ ] product_register.json regenerated and validated
- [ ] BUILD_PROGRAM scope deviations documented with LaTeX amendments OR corrected

**Deliverables for R0 → R1 handoff:**
1. Corrected hpo-survey/ LaTeX (validation chapter, NAS scope, V08 semantics, knob kinds)
2. traceability-matrix.json + TRACEABILITY.md
3. work-breakdown.xlsx + timeline-gantt.png
4. product_register_v2.json
5. R0_COMPLETION_REPORT.md (summary of changes, remaining risks, R1 readiness)

---

## Current status summary

**Phase:** R0 Week 1, Day 1  
**Completed:** 0/5 week-1 tasks, 0/4 week-2 tasks  
**Blocking:** Task 1.1 (NAS scope decision) is critical path  
**Next action:** Project sponsor decision on NAS scope (Option A recommended)

Once NAS scope is decided, parallel execution of statistical reviewer hire, LaTeX corrections, and traceability matrix generation can begin.
