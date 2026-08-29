# HPO Tuner Build Program
**Target:** Workspace-internal hyperparameter tuning system serving RL, Hamiltonian networks, samplers, and multi-objective finance models  
**Base:** Ray Tune execution layer + custom searchers/schedulers  
**Timeline:** 42 engineer-weeks to tier-2 complete, three decision gates  
**Repo:** `/home/ubuntu/workspace/hponas`

---

## Executive summary

Three-tier build with gates at weeks 6, 12, and 30 (one-engineer assumption). Each gate is a validation campaign; passing advances to the next tier, failing triggers the registered demotion or cancellation. Tier 0 wraps audited components and wires the database; tier 1 builds the method differentiators (MO acquisition, priors, trust-region BO); tier 2 delivers the population flagship and freeze-thaw scheduling.

**Budget:** ~42 engineer-weeks of implementation + a few GPU-weeks of validation campaigns (V01–V15 priced in Ch14). **Risk mitigation:** tier gates enforce "fail early" discipline; demotion rules were fixed before code started; alternatives are named for every load-bearing bet.

**Approval requested:**
1. Fund tier 0 to week-6 gate (~6 weeks, wrapping only, low risk)
2. Contingent on gate pass: fund tier 1 to week-12 gate (~6 more weeks, first method campaign)

---

## Phase 0: Setup and interface freeze (weeks 1–2)

**Goal:** Locked interfaces, sized tasks, empty harness running.

### Deliverables
- Environment installable (`setup/environment.yml` complete, all tier-0 dependencies resolve)
- Interface contracts frozen as code: `StudySpec` (YAML schema), `SearchSpace` with priors, `Searcher` / `Scheduler` protocols with capability flags
- Run store schema designed (DDL + migration zero)
- Pinned validation tasks sized to compute envelope and recorded in `validation/tasks/` with cost estimates
- Layer-one harness running: a no-op study that declares a space, writes to the store, and exits cleanly

### Work breakdown
- `src/contracts/`: study spec parser (1d), search-space schema with prior fields (2d), searcher/scheduler protocols (1d)
- `src/store/`: SQLite schema DDL (1d), store client with CRUD (2d)
- `validation/tasks/`: Size PPO/Brax to 16-run budget, Hamiltonian 2-obj to 32 evals, sampler veto to 8 chains (2d)
- Integration: wire a toy study end-to-end (1d)

**Decision point (week 2):** Interfaces reviewed by stakeholders; if contracts need rework, pause here and iterate before proceeding.

---

## Tier 0: The wrapping campaign (weeks 3–6, gate at week 6)

**Goal:** Deliver the routine-budget floor — wrapping audited components, zero new method research.

### What ships
- **Searchers (wrapped):** Random/Sobol (Ray native), TPE (Optuna adapter per Ch4 box), DEHB (vendored or thin wrap per Ch5 evidence)
- **Schedulers (wrapped):** ASHA (Ray native), MedianStopper (Ray native)
- **Workload templates (empty shells):** `rl_routine`, `rl_large_parallel`, `hamiltonian_mo`, `sampler_neutra` — interface exists, body is `NotImplementedError`
- **Run store:** trial logging, lineage tracking, standing diagnostics (best-so-far, convergence flag)
- **Executor adapters:** RLlib adapter (checkpoint surgery, resume), generic train-loop adapter

### Work breakdown (6 weeks = 30 eng-days, one engineer)
1. **Searcher wrappers** (5d)
   - Sobol/Random: Ray Tune built-in, expose via our `Searcher` protocol (0.5d)
   - TPE: Optuna `OptunaSearch` adapter with our schema (2d)
   - DEHB: vendor or wrap ConfigSpace-based DEHB, test on 2D Branin (2.5d)

2. **Scheduler wrappers** (3d)
   - ASHA: Ray `ASHAScheduler` exposed, config validation (1d)
   - MedianStopper: Ray `MedianStoppingRule`, test on toy curve (1d)
   - Scheduler capability flags: `supports_resume`, `requires_monotonic_metric` (1d)

3. **Run store** (8d)
   - SQLite backend with tables: `studies`, `trials`, `observations`, `checkpoints` (2d)
   - Store client: `log_trial()`, `get_best()`, `query_lineage()`, `get_incumbent()` (3d)
   - Standing diagnostics: convergence detector (coefficient-of-variation on trailing window), best-tracked-by-fidelity (2d)
   - Unit tests for CRUD and lineage queries (1d)

4. **Executor adapters** (6d)
   - RLlib adapter: wrap `RLlib.train()`, checkpoint load/save/resume, multi-fidelity via `training_iteration` (3d)
   - Generic adapter: user supplies `train_fn(config, reporter)`, we wire the reporter to store (2d)
   - Integration test: run a 4-trial ASHA+TPE study on CartPole (1d)

5. **Workload templates (stubs)** (2d)
   - Four YAML skeletons with schema validation, raise `NotImplementedError` on `.run()` (1d)
   - Template registry and dispatcher (1d)

6. **Validation prep** (3d)
   - Implement V01 (wrapped searchers match reference implementations on tabular benchmarks), V02 (scheduler async correctness via replay), V03 (planted defects caught by suite), V05 (log-warped GP must not lose vs unwarped), V14 (day-one walk reproducible end-to-end) (2d)
   - Campaign runner script: `python validation/run_campaign.py --tests V01,V02,V03,V05,V14` (1d)

7. **Integration and documentation** (3d)
   - End-to-end smoke test: declare study, run 16 trials, query store (1d)
   - Usage examples: `examples/quickstart.py`, `examples/rlll_cartpole.py` (1d)
   - Docstrings and README (1d)

**Gate criteria (week 6):** V01 (implementation parity), V02 (async correctness), V03 (sabotage detection), V05 (log-warping effectiveness), V14 (day-one walk reproduction) pass. Additionally, V04 tier-0 component: TPE and log+Sobol GP must beat random baseline on pinned high-dim task. **Demotion rule:** If wrapped implementations fail parity (V01), block tier-1 and diagnose wiring. If log-warping shows no benefit (V05), demote to opt-in feature. If tier-0 searchers fail to beat random (V04), identify and fix before proceeding.

---

## Tier 1: The method differentiators (weeks 7–12, gate at week 12)

**Goal:** Build what makes this tuner worth using — MO acquisition, priors, trust-region BO.

### What ships
- **Searchers (built):** Trust-region BO (TuRBO adaptation, Ch4), qLogEI with priors (πBO-style, Ch8), qLogNEHVI (Ch7)
- **Schedulers (built):** MO-ASHA (veto gates per Ch7), PriorBand (prior-weighted rung sampling, Ch8)
- **Workload templates (filled):** `hamiltonian_mo` and `sampler_neutra` production-ready
- **Warm-start engine:** query historical trials, fit RGPE or direct prior (Ch8)

### Work breakdown (6 weeks = 30 eng-days)
1. **Trust-region BO** (7d)
   - Adapt BoTorch TuRBO: mixed-space kernel, trust-region state manager (3d)
   - Integrate with our `SearchSpace` schema (1d)
   - Test on Ackley-10D, Rosenbrock-15D (1d)
   - V04 tier-1 campaign: TuRBO and other tier-1 searchers beat log+Sobol floor on pinned tasks (2d)

2. **Prior-aware qLogEI** (5d)
   - Extend BoTorch qLogEI: prior mean as GP mean function, prior variance as obs noise floor (2d)
   - Prior parser: YAML → BoTorch prior objects (1d)
   - Test recovery from wrong prior on Branin (1d)
   - V11 campaign prep: good prior accelerates, wrong prior recovers (1d)

3. **qLogNEHVI** (6d)
   - BoTorch qLogNEHVI wrapper (already exists, adapt to our schema) (2d)
   - Hypervolume reference-point auto-selection (worst-seen + margin) (1d)
   - Test on 2-obj ZDT1, compare vs random-weight Chebyshev scalarization (2d)
   - V09 campaign prep: qLogNEHVI vs scalarization on Hamiltonian pinned task (1d)

4. **MO-ASHA scheduler** (4d)
   - Extend ASHA: accept multi-objective trials, veto by cheap-fidelity dominance (2d)
   - Veto correctness check: dominated-at-rung-1 must stay dominated at full fidelity (1d)
   - V10 rank-correlation pilot, V13 veto-correctness suite (1d)

5. **PriorBand scheduler** (3d)
   - ASHA + prior-weighted rung sampling: sample next config from top-K prior density (2d)
   - Test on toy prior-informative space (1d)

6. **Warm-start engine** (3d)
   - Query engine: `store.get_similar_studies(space, top_k=50)` (1d)
   - RGPE-light: fit GP to pooled historical + current trials, weight by space similarity (1d)
   - V12 prep: measure trial savings on synthetic history (1d)

7. **Workload templates (production)** (2d)
   - `hamiltonian_mo`: 2-obj (prediction + drift), qLogNEHVI + MO-ASHA, 32-eval budget (1d)
   - `sampler_neutra`: ESS metric, veto gate at 100 steps, MedianStopper fallback (1d)

**Gate criteria (week 12):** V04 tier-1 searchers (TuRBO and prior-aware qLogEI beat log+Sobol floor), V09 (qLogNEHVI beats scalarization or ties and gets demoted), V11 (priors help under good advice, recover under wrong advice). **Demotion rule:** qLogNEHVI failure → demote to tier-2 option, Hamiltonian study defaults to scalarization. TuRBO failure → defer population line (BG-PBT depends on TR for explore step), reassess tier-2 scope. Prior failure → demote πBO/PriorBand to opt-in.

---

## Tier 2/3: The flagship and frontier bets (weeks 13–30, gate at week 30)

**Goal:** Deliver the population flagship (BG-PBT, survey tier 2) and the frontier bets (ifBO curve model and DEHB for small-budget RL, survey tier 3).

### What ships
- **Schedulers (built):** PB2-Mix (continuous PB2 + categorical bandit, Ch6), BG-PBT (population + TR explore, Ch6)
- **Curve model (built):** ifBO learning-curve surrogate, freeze-thaw scheduler (Ch5)
- **Workload template (filled):** `rl_large_parallel` production-ready (8+ workers, BG-PBT default)
- **Full validation suite:** V01–V15 runnable, campaign cost dashboard

### Work breakdown (18 weeks = 90 eng-days, suggests 1.5–2 engineers or extended timeline)

**Phase 2A: PB2-Mix** (weeks 13–16, 4 weeks)
1. PB2 continuous (BoTorch wrapper, exploit/explore as acquisition) (1w)
2. Categorical bandit (Thompson sampling over discrete dims) (1w)
3. Integration + checkpoint surgery for population (Ray Tune PBT primitives) (1.5w)
4. Test on mixed-space toy problem, compare vs fixed-category PB2 (0.5w)

**Phase 2B: BG-PBT** (weeks 17–22, 6 weeks)
1. Population manager: maintain N agents, track lineage (1w)
2. Exploit step: clone best, copy weights (Ray checkpoint primitives) (1w)
3. Explore step: TR BO over mixed space, resume from checkpoint (1.5w)
4. Generational transfer: age-weighted selection (the theory gap, implement heuristic) (1w)
5. Integration: wire to RLlib, test on single Brax task (1w)
6. V08 campaign prep: BG-PBT vs DEHB/BO+ASHA at 8-worker and 16-run boundaries (0.5w)

**Phase 2C: ifBO curve model** (weeks 23–27, 5 weeks)
1. Learning-curve dataset collection (fit public RL benchmarks, cache) (1w)
2. Power-law + saturation curve family, Bayesian inference (gpytorch) (2w)
3. Freeze-thaw scheduler: predict curve, decide pause/resume/kill (1w)
4. V15 gate prep: ifBO vs ASHA on HPOBench learning-curve tasks (1w)

**Phase 2D: Full validation suite** (weeks 28–30, 3 weeks)
1. Implement remaining tests: V06 (ASHA early stopping is nearly free—reaches same quality at fraction of compute), V07 (small-budget RL: DEHB vs BO+ASHA at 16-run budget), V08 (population line does not lose in home regime—above 8 workers), V10 (cheap MO fidelity signals may cull—rung correlation pilot), V12 (warm-start trial savings measured), V13 (sampler veto correctness—no divergent/high-Rhat configs promoted) (1.5w)
2. Campaign dashboard: cost tracking, sabotage-entry flagging, statistical protocol (0.5w)
3. Run full suite, collect results, write validation report (1w)

**Gate criteria (week 30):** V06 (ASHA reaches full-fidelity quality at ≤1/3 compute), V07 (DEHB or BO+ASHA wins at 16-run routine budget), V08 (BG-PBT does not lose in home regime: above 8 workers vs DEHB and BO+ASHA; 3-rep exception with asymmetric demotion rule), V10 (drift-at-rung correlates with drift-at-end, ρ > 0.6 lower bound), V12 (warm start saves ≥20% trials), V13 (no veto-failing configs promoted; survivors ranked by ESS/gradient; pilot agrees with reference posterior), V15 (ifBO matches ASHA at half compute on curve-informative benchmarks). **Demotion rule:** BG-PBT consistent home loss → demote to option, rl_large_parallel defaults to DEHB. ifBO failure → cancel build, reallocate tier-2 slot. ASHA fraction-of-three failure → block promotion, diagnose correlation assumptions. Sampler veto failure → block sampler workload shipping.

---

## Post-tier-2: Hardening and deployment (weeks 31–36, optional)

- Kubernetes Ray cluster setup (production execution, not dev env)
- API server wrapper (REST study submission)
- Monitoring and alerting (study stalls, trial failures)
- Multi-user run store (Postgres migration from SQLite)
- Documentation site (Sphinx, auto-generated from docstrings)

**Budget:** ~6 weeks, productionization work, depends on usage scaling.

---

## Risk register and tripwires

| Risk | Likelihood | Impact | Mitigation | Tripwire |
|------|-----------|--------|------------|----------|
| BG-PBT fails V08 boundary trial | Medium | High (flagship demoted) | Demotion rule pre-committed; fallback is DEHB | Week 22: if informal tests show <50% win rate, flag early |
| Trust-region BO unstable on mixed spaces | Low | High (blocks PB2-Mix, BG-PBT explore) | BoTorch TuRBO is production-tested; our adaptation is thin | Week 9: if V04 shows high variance, add restart logic |
| ifBO curve model needs >2w of campaign compute | Medium | Medium (gate cost overrun) | V15 budget capped at 2 GPU-weeks; failure → cancel, not debug | Week 25: if model training needs >100 curves, defer to post-tier-2 |
| ASHA rank correlations fail on real RL tasks | Low | High (tier-0 floor collapses) | Chapter 5 evidence shows 0.7+ correlation is typical | Week 10: pilot V06 early; if <0.5, revisit fidelity definition |
| Validation campaigns blocked by Brax env install | Low | Medium (delays gates) | Install Brax at week 7 start, not week 12 | Week 7: test `import brax` and run one episode |
| Store schema needs migration mid-build | Medium | Low (1–2d disruption) | Design with extensibility (JSON blob for method-specific metadata) | Any week: if schema change needed, write migration and re-seed test data |

---

## Dependencies and sequencing

```
Tier 0 (weeks 3-6)
├─ Searcher wrappers (Sobol/TPE/DEHB)
├─ Scheduler wrappers (ASHA/Median)
├─ Run store
└─ Executor adapters ──> [GATE: V01-V05, V14, V04-T0]

Tier 1 (weeks 7-12)
├─ Trust-region BO ──────────┐
├─ Prior-aware qLogEI        │
├─ qLogNEHVI                 │
├─ MO-ASHA                   │
├─ PriorBand                 │
└─ Warm-start engine ────────┴──> [GATE: V04-T1, V09, V11]

Tier 2/3 (weeks 13-30)
├─ PB2-Mix (depends on TuRBO)
├─ BG-PBT (depends on TuRBO + PB2-Mix)
├─ ifBO curve model (independent)
└─ Full validation ──────────────> [GATE: V06-V08, V10, V12-V13, V15]
```

**Critical path:** TuRBO → PB2-Mix → BG-PBT (16 weeks). ifBO runs in parallel (5 weeks). If TuRBO is delayed or demoted, PB2-Mix/BG-PBT slip or cancel.

---

## Cost summary (from Ch15)

| Tier | Engineer-weeks | GPU-weeks (campaigns) | Decision point |
|------|---------------|---------------------|----------------|
| 0    | 6             | 0.5 (V01-V05, V14, V04-T0) | Week 6         |
| 1    | 6             | 1.5 (V04-T1, V09, V11) | Week 12        |
| 2/3  | 30            | 3 (V06-V08, V10, V12-V13, V15, full suite) | Week 30 |
| **Total** | **42**    | **5**               | Three gates    |

Assumes one engineer through tier 1, scaling to 1.5–2 for tier 2 (or extended timeline). Campaign compute: modest by 2026 standards (5 GPU-weeks = ~$2k–5k cloud cost depending on instance type).

---

## What success looks like (week 30)

- Four workload templates production-ready, each tested on its pinned task
- 15 validation tests passing, results logged, no sabotage entries promoted
- Ray Tune execution layer proven stable for our usage (checkpoint surgery works, RLlib integration clean)
- Run store holds lineage and diagnostics for every trial run during validation
- Documentation sufficient for a colleague to declare a study and interpret results
- One decision: whether to fund post-tier-2 hardening or ship tier 2 as-is for internal use

---

## How to use this program

1. **Weeks 1–2:** Execute Phase 0, freeze interfaces, get stakeholder sign-off before tier-0 start.
2. **Weeks 3–6:** Build tier 0 per breakdown, run gate campaign week 6.
3. **Week 6 decision:** If gate passes, continue to tier 1; if gate fails, diagnose per demotion rules and re-plan.
4. **Weeks 7–12:** Build tier 1, run gate campaign week 12.
5. **Week 12 decision:** If gate passes, commit to tier 2 (larger scope); if gate fails, ship tier 1 as-is or cancel.
6. **Weeks 13–30:** Build tier 2, run full validation week 30.
7. **Week 30 decision:** Ship for internal use, or fund productionization (weeks 31–36).

**Live tracking:** Update `docs/progress.md` weekly with completed items, gate results, and risk flag changes.

---

For questions or scope changes, see the survey Chapter 15 (build plan detail) and Chapter 14 (validation suite specification).
