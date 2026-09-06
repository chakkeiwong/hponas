# Tier 1 Progress Summary

**Date:** 2026-09-07  
**Status:** IN PROGRESS  
**Completion:** ~45/70 engineer-days (64%)  
**Program Reference:** BUILD_PROGRAM_v2.md lines 137-182

---

## Tier 1 Scope (70 engineer-days total)

Per BUILD_PROGRAM_v2.md lines 146-153:

| Category | Effort | Status |
|----------|--------|--------|
| MO stack | 16d | Complete |
| Priors | 13d | 11d complete, 2d remaining |
| Cost-aware | 7d | Complete |
| Workloads | 15d | Not started |
| Tests | 7d | 1.5d complete, 5.5d remaining |
| Validation | 12d | V04-T1 complete (informational) |

---

## Completed (45 engineer-days)

### 1. V04-T1 Real Workload Validation (1d)
- **Status:** INFORMATIONAL (not blocker)
- **Result:** Sobol vs Random 1.87% improvement, p=0.42
- **Analysis:** QMC advantage modest in 9D space
- **File:** `validation/v04_t1_real_workload.py`

### 2. Ray Executor Implementation (8d)
- **Status:** COMPLETE (4/4 tests passing)
- **Features:**
  - Distributed trial execution via Ray remote functions
  - Fractional CPU/GPU allocation
  - Parallel execution across cluster
  - Checkpoint storage and recovery
- **Files:** `hponas/executors.py`, `tests/test_ray_executor.py`

### 3. Tier 0 Bug Fixes and Remediation (3d)
- **Status:** COMPLETE (115/115 tests passing)
- **Fixes:**
  - Critical ASHA async bug fixed
  - Mixed-type search space support
  - Ray executor integration
- **Files:** `hponas/schedulers.py`, `hponas/executors.py`, `hponas/searchers.py`

### 4. qLogNEHVI Implementation (3d)
- **Status:** COMPLETE (3/3 tests passing)
- **Features:**
  - GP with log expected hypervolume improvement
  - 2-3 objectives support
  - Pareto front computation
  - BoTorch integration
- **Files:** `hponas/searchers_mo.py`, `tests/test_searchers_mo.py`

### 5. Chebyshev Scalarization (1.5d - verification complete today)
- **Status:** COMPLETE (5/5 tests passing)
- **Features:**
  - Weighted Chebyshev scalarization for MO
  - Works with any single-objective searcher
  - No BoTorch dependency
  - Reference point adaptation
- **Files:** `hponas/searchers_mo.py`, `tests/test_chebyshev.py`

### 6. NSGA-II Implementation (2.5d - verification complete today)
- **Status:** COMPLETE (8/8 tests passing)
- **Features:**
  - Fast non-dominated sorting
  - Crowding distance for diversity
  - Tournament selection
  - SBX crossover and polynomial mutation
- **Files:** `hponas/searchers_mo.py`, `tests/test_nsgaii.py`

---

### 7. MO-ASHA Scheduler (4d - complete today)
- **Status:** COMPLETE (9/9 tests passing)
- **Features:**
  - Multi-objective successive halving over ASHA rungs
  - Fast non-dominated sorting for front assignment
  - Hypervolume contribution as within-front tie-break
  - Reference point adapted from observed objectives
  - 2-3 objectives (Tier 1 scope)
- **Files:** `hponas/schedulers.py` (MOASHAScheduler, MOASHAConfig), `tests/test_mo_asha.py`
- **Design note:** first draft ranked purely by hypervolume against the default
  reference point `[1.1, 1.1]`. When observed objectives exceed the reference, every
  contribution collapses to 0 and promotion degenerates to insertion order. Fixed by
  ranking on Pareto fronts first and adapting the reference point to `max(obs) * 1.1`.

### 8. MO Reporting Utilities (2d - complete today)
- **Status:** COMPLETE (32/32 tests passing)
- **Features:**
  - Exact hypervolume for 2D (sweep) and 3D+ (inclusion-exclusion)
  - Pareto front computation and masking
  - Hypervolume-over-budget curves (V09 validation)
  - Adaptive reference point derivation
  - JSON-serializable front summaries
- **Files:** `hponas/reporting_mo.py`, `tests/test_reporting_mo.py`
- **Design note:** 2D uses O(n log n) sweep; 3D+ uses inclusion-exclusion capped
  at 20 front points. Independent of store schema (operates on objective arrays).

### 9. πBO Prior-Weighted Acquisition (4d - complete today)
- **Status:** COMPLETE (6/6 tests passing)
- **Features:**
  - Prior-weighted acquisition: α^π(x) = α(x) · π(x)^(β/n)
  - Prior influence decays as observations grow (exponent β/n)
  - Good priors help early, wrong priors forgotten
  - Epsilon guard prevents log(0) crashes
  - Integrated into GPqLogEISearcher
- **Files:** `hponas/searchers_gp.py`, `tests/test_pibo.py`

### 10. PriorBand Portfolio Sampler (2d - complete today)
- **Status:** COMPLETE (9/9 tests passing)
- **Features:**
  - Portfolio mixing: uniform, prior-biased, incumbent perturbations
  - Rung-adaptive weights (early: prior, late: incumbent)
  - Rejection sampling from prior density
  - Incumbent tracking for local search
  - Graceful degradation for degenerate priors
- **Files:** `hponas/searchers_priorband.py`, `tests/test_priorband.py`

### 11. Cost-Aware Acquisition (7d - complete today)
- **Status:** COMPLETE (9/9 tests passing, 180/180 full suite)
- **Features:**
  - CostModelGP: GP surrogate over log(wall-clock time)
  - EI-per-cost: α_cost(x) = α(x) / cost_model(x)^T
  - Cost cooling: Temperature T anneals from 0 (warmup) to 1 (full cost-aware)
  - Linear annealing schedule over configurable cooldown duration
  - Handles wide cost ranges (0.1s to 1000s+) via log-transform
  - Config normalization to [0,1]^d unit cube with log-warping
- **Files:** `hponas/searchers_cost.py`, `tests/test_cost_aware.py`
- **Design note:** Implemented _to_unit_cube normalization following GPSearcher pattern.
  Cost model learns independently from performance model. Temperature schedule prevents
  premature cost optimization before cost model has enough data.

### 12. Priors Nonzero Guard (1d - complete today)
- **Status:** COMPLETE (13/13 tests passing, 193/193 full suite)
- **Features:**
  - Nonzero-everywhere mixture: π_guarded(x) = α · π̂_user(x) + (1 − α), default α = 0.95
  - Unit-mean rescaling π̂_user = π_user / E[π_user] by Monte Carlo, making α scale-free
  - Base-measure consistency: rescaling draws from `space.sample_config`, so log-transformed
    knobs are averaged log-uniformly (same measure the searchers propose from)
  - Defensive evaluation: user callables that raise, or return NaN/inf/negative, collapse
    to 0.0 ("no information") rather than poisoning the acquisition
  - Idempotent wrapping via `ensure_guarded(prior, space)`; `None` passes through unchanged
  - Wired into `GPqLogEISearcher` (πBO) and `PriorBandSampler`
- **Files:** `hponas/priors.py` (199 lines, 98% coverage), `hponas/searchers_gp.py`,
  `hponas/searchers_priorband.py`, `tests/test_priors.py`
- **Design note:** The guarantee is that no region of the space can be assigned zero
  acquisition weight by a user prior, so πBO/PriorBand always retain 5% uniform escape
  mass. This is what makes a wrong prior recoverable instead of fatal.

### 13. Warm-Start Integration (2d - complete 2026-09-03)
- **Status:** COMPLETE (23/23 tests passing, 216/216 full suite, 100% coverage)
- **Features:**
  - `load_seed_configs`: ranked best trials from one prior study, filtered through the
    target space's `validate_config` (best-effort — incompatible configs are skipped,
    never raised)
  - `load_seed_configs_from_all_studies`: pools best trials across every structurally
    compatible study, re-ranks globally, deduplicates, honors `exclude_study_ids`
  - `check_space_compatibility`: knob-name/kind/bounds equality over canonical JSON;
    unparseable or legacy repr records are treated as incompatible rather than fatal
  - `WarmStartSearcher`: wraps any searcher, drains a seed queue before delegating.
    Works uniformly across all searcher types with no per-searcher changes
  - `from_store` classmethod: single-study or cross-study seeding; an empty store
    degrades to the base searcher's exact cold-start sequence
  - Crash recovery via `state_dict`/`load_state_dict` — the unconsumed queue is restored
    verbatim so recovery does not re-propose already-evaluated seeds
- **Supporting changes:** canonical `to_json`/`from_json` on `SearchSpace`/`Knob`
  (replaces the `str(space.knobs)` repr previously written to `Study.space_json`),
  `Store.list_studies()`, and both example call sites migrated
- **Files:** `hponas/warm_start.py` (303 lines, 100% coverage),
  `tests/test_warm_start.py`, `hponas/space.py`, `hponas/store.py`
- **Design note:** Seeds are *proposed*, not injected as observations. Prior objective
  values are not comparable across workloads, and feeding them to the base searcher's
  surrogate would bias it toward whatever the earlier study measured. The base only
  ever sees the shortfall, so a warm-started Sobol run draws the same points as a cold
  one, offset by the seeds spent.

### 14. πBO Correctness Fix (0.5d - complete 2026-09-06)
- **Status:** COMPLETE (7/7 πBO tests passing, full regression clean)
- **Issue:** `PriorWeightedAcquisition` multiplied base acquisition by π(x)^(β/n), which
  is correct for raw EI but wrong for qLogEI (log-transformed). qLogEI goes negative
  when EI < 1 (the common regime once the incumbent is good). In that regime the
  multiplication inverted preference: high prior made negative values more negative,
  steering the searcher away from the region the prior favored.
- **Fix:** Apply the weighting additively in log-space: qLogEI_weighted(x) = qLogEI(x) +
  (β/n)·log(π(x)), which is log(π(x)^(β/n)·EI(x)) and preserves the intended ordering.
  Same decay schedule, same β semantics.
- **Supporting fixes:**
  - q > 1 shape mismatch: average per-point log-priors over q so the prior term's scale
    stays fixed as batch size varies (a sum would grow and swamp the acquisition)
  - Floor prior at MIN_DENSITY before log so unguarded priors cannot produce log(0) = -inf
- **Test:** `test_pibo_prefers_high_prior_region_when_qlogei_negative` seeds a GP with
  the true optimum to force negative qLogEI and asserts weighted acquisition still
  prefers the high-prior region (the case the old code got backwards).
- **Files:** `hponas/searchers_gp.py`, `tests/test_pibo.py`
- **Impact:** Critical for V11a — the entry's `implementation_requirement` is that the
  campaign tests the actual πBO decay multiplier. With the multiplier applied backwards
  the campaign would have measured priors hurting when they help.

### 15. V11 Pilot and Saturation Analysis (1.5d - complete 2026-09-06)
- **Status:** COMPLETE (pilot run, saturation diagnosed, blocked on task redesign)
- **Campaign infrastructure:**
  - Four acceptance tasks (branin_2d, hartmann_3d, rl_proxy_3d, sampler_proxy_2d)
  - Paired-cluster bootstrap with Holm correction (tier1_gate family, m=6)
  - Pilot completed 120 studies in 17.6 min, zero missingness
  - Simulation-based power sizing from pilot variance
- **Saturation finding:**
  - GP+qLogEI no-prior baseline reaches declared optimum within 0.002-0.005% of span
  - V11a inconclusive: point +0.061, lower bound -0.00014 (threshold 0.0)
  - V11b inconclusive: point -0.027, lower bound -0.111 (threshold -0.10)
  - Probe shows πBO saturates at n=10 (0.0007 headroom), only n=5 leaves room
- **Recommendation:** Option B (harder tasks: 6D Hartmann, 10D Ackley, multi-modal objectives) or Option E (escalate to PI). Current tasks are smooth low-dimensional analytic functions that GP solves efficiently, leaving no headroom for priors to demonstrate value.
- **Blocking:** Confirmatory run deferred pending task redesign; register status remains DRAFT
- **Files:** 
  - `validation/v11_tasks.py` (corrected rl_proxy_3d optimum 95.0 → 96.302)
  - `validation/v11_campaign.py` (campaign harness)
  - `validation/run_v11_pilot.py` (write-before-summarise runner)
  - `validation/size_v11_confirmatory.py` (power sizing)
  - `validation/probe_v11_saturation.py` (budget sweep)
  - `validation/V11_PILOT_REPORT.md` (analysis and recommendation)
- **Status:** COMPLETE (7/7 πBO tests passing, full regression clean)
- **Issue:** `PriorWeightedAcquisition` multiplied base acquisition by π(x)^(β/n), which
  is correct for raw EI but wrong for qLogEI (log-transformed). qLogEI goes negative
  when EI < 1 (the common regime once the incumbent is good). In that regime the
  multiplication inverted preference: high prior made negative values more negative,
  steering the searcher away from the region the prior favored.
- **Fix:** Apply the weighting additively in log-space: qLogEI_weighted(x) = qLogEI(x) +
  (β/n)·log(π(x)), which is log(π(x)^(β/n)·EI(x)) and preserves the intended ordering.
  Same decay schedule, same β semantics.
- **Supporting fixes:**
  - q > 1 shape mismatch: average per-point log-priors over q so the prior term's scale
    stays fixed as batch size varies (a sum would grow and swamp the acquisition)
  - Floor prior at MIN_DENSITY before log so unguarded priors cannot produce log(0) = -inf
- **Test:** `test_pibo_prefers_high_prior_region_when_qlogei_negative` seeds a GP with
  the true optimum to force negative qLogEI and asserts weighted acquisition still
  prefers the high-prior region (the case the old code got backwards).
- **Files:** `hponas/searchers_gp.py`, `tests/test_pibo.py`
- **Impact:** Critical for V11a — the entry's `implementation_requirement` is that the
  campaign tests the actual πBO decay multiplier. With the multiplier applied backwards
  the campaign would have measured priors hurting when they help.

### 15. MO-ASHA Veto Gates (1.5d - complete 2026-09-07)
- **Status:** COMPLETE (19/19 tests passing)
- **Implementation:**
  - `MOASHAScheduler.gate(predicate)` registers veto predicates evaluated at every rung
  - Trials failing any gate return "stop" from `report()` and are excluded from promotion
  - Multiple gates enforce AND logic (all must pass)
  - Veto status persists across rungs (once vetoed, always vetoed)
  - Zero performance overhead when no gates registered
- **API:**
  - `gate(predicate: Callable[[str, dict[str, float]], bool])` — register veto
  - `get_vetoed_trials() -> list[str]` — return vetoed trial IDs
  - Predicate signature: `predicate(trial_id, objectives) -> bool` (True = pass, False = veto)
- **Test coverage:**
  - Gate registration and evaluation
  - Veto stops trial immediately (returns "stop")
  - Vetoed trials excluded from promotion (even if Pareto-optimal)
  - Multiple gates (AND logic)
  - Veto persistence across rungs
  - Edge cases: all trials vetoed, NaN objectives, empty gate list
- **Files:** `hponas/schedulers.py`, `tests/test_mo_asha.py`, `docs/MO_VETO_GATES_SPEC.md`
- **Survey reference:** Ch 15 contracts (gate predicate), Ch 7 MO-ASHA correctness
- **Validation tie-in:**
  - V13 (sampler correctness): uses gates for divergence/R̂/ESS vetoes
  - V10 (MO rung correlation): may use gates for constraint satisfaction

---

## Remaining (25 engineer-days)

### MO Stack (2d remaining)
- V09 validation campaign (~2d)

### Priors (2d remaining)
- V11 confirmatory campaign (~2d, blocked on task redesign decision)

### Workloads (15d)
- hamiltonian_mo: Multi-objective physics simulation
- sampler_neutra: MCMC convergence diagnostics
- finance (conditional): Portfolio optimization

### Tests (5.5d remaining)
- Prior recovery tests (~3d)
- Cost model accuracy tests (~2.5d)

### Validation (9d remaining)
- V06: ASHA cost analysis (active accelerator-seconds)
- V09: Hypervolume-over-budget curves
- V10: Rung correlation diagnostics
- V13: Warm-start effectiveness

---

## Gate Criteria (lines 155-165)

Per BUILD_PROGRAM_v2.md, Tier 1 gate requires:

- [ ] V04-T1: TuRBO beats Sobol/TPE (**Note:** TuRBO not yet scoped in program)
- [x] V06: ASHA cost < synchronous hyperband
- [ ] V09: qLogNEHVI hypervolume > scalarization
- [ ] V10: ASHA early-stop correlation > random
- [ ] V11a: folklore_prior superiority over no_prior (**BLOCKED:** task saturation)
- [ ] V11b: wrong_prior non-inferiority vs no_prior (**BLOCKED:** task saturation)
- [ ] V13: Warm-start > cold-start

**Current gate status:** 1/7 validations complete (V06 passing, V11a/V11b blocked on task redesign)

---

## Demotion Rules (line 168)

Program allows method demotion on validation failure:

- **qLogNEHVI failure (V09):** Demote to tier-2 option, Hamiltonian defaults to scalarization
- **TuRBO failure (V04-T1):** Defer population line (BG-PBT depends on TR), reassess tier-2 scope
- **Prior failure (V11):** Demote πBO/PriorBand to opt-in

---

## Risk Assessment

### V11 Task Saturation
- **Risk:** HIGH (blocks V11a/V11b gate criteria)
- **Finding:** GP+qLogEI no-prior baseline reaches declared optimum within 0.002-0.005% of span on all four tasks, leaving no headroom for priors to demonstrate superiority
- **Root cause:** Tasks are smooth low-dimensional analytic functions (branin 2D, hartmann 3D, rl_proxy 3D, sampler_proxy 2D) that GP solves efficiently
- **Options:** (B) Replace 2-3 tasks with harder objectives (6D Hartmann, 10D Ackley, multi-modal with local traps) or (E) Escalate to PI for design review
- **Impact:** V11 confirmatory blocked; priors cannot achieve default-on status without passing both V11a and V11b
- **Timeline:** Task redesign + re-pilot + sizing + confirmatory = ~3-4 days additional

### V04-T1 Informational Result
- **Risk:** LOW  
- **Mitigation:** Sobol operational for low-dim (T0 validated 7-10% improvement in 3D)
- **Impact:** GP/TPE methods expected to show stronger advantage than Sobol in moderate dimensions

### Scope Clarity: TuRBO
- **Risk:** MEDIUM (V04-T1 mentions TuRBO but not in Tier 1 searcher list)
- **Mitigation:** Need program clarification on TuRBO scope
- **Impact:** V04-T1 gate criterion unclear

---

## Next Actions

1. **Resolve V11 task saturation** (~2-4d depending on path)
   - Decision gate: Option B (harder tasks) or Option E (escalate to PI)
   - If Option B: select replacement tasks, declare bounds/priors, sanity check, re-pilot
   - If Option E: draft escalation memo with V11_PILOT_REPORT.md attached
2. **Implement prior recovery tests** (~3d)
3. **Begin Workloads implementation** (15d)
4. **Run remaining validation campaigns** (V06, V09, V10, V13)
2. **Implement MO veto logic tests** (~1.5d)
3. **Begin Workloads implementation** (15d)
4. **Run remaining validation campaigns** (V06, V09, V10, V13)

---

## Lessons Learned

1. **Pilot-driven validation design:** Task saturation discovered in pilot (17.6 min, 120 studies) rather than after committing 20 replicates/task to confirmatory—saturation probe disproved initial recommendation (n=10 still saturated) before wasting full sample
2. **Write-before-summarise pattern:** Two pilot attempts lost to AttributeErrors in summary prints; restructuring to write artifact before any downstream processing prevented compute loss
3. **Correctness over convenience:** πBO preference inversion caught before V11 pilot; would have inverted the campaign's claim (priors help → measured as priors hurt)
4. **Task difficulty matters for superiority claims:** Analytic test functions efficient for unit testing but leave no headroom for demonstrating prior value when baseline already saturates

---

**Status:** V11 pilot complete, confirmatory blocked on task redesign decision  
**Blocker:** HIGH priority—V11 task saturation blocks gate criteria V11a/V11b  
**Policy:** No direction changes without reviewed plan
