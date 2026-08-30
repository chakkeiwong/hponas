# Technical Review Verdict: `BUILD_PROGRAM.md`

**Review date:** 2026-08-28  
**Primary document:** `BUILD_PROGRAM.md`  
**Governing specification:** `hpo-survey/main.tex`, especially Chapters 11-15 (`14-product.tex`, `11-architecture.tex`, `15-contracts.tex`, `16-validation.tex`, and `12-roadmap.tex`)  
**Other artifacts checked:** `hpo-survey/product_register.json`, `setup/environment.yml`, `setup/INSTALL.md`, `README.md`, `docs/progress.md`, the current source/test tree, and prior reconciliation notes

## Executive verdict

**RED - do not approve interface freeze, Tier 0 execution, or the week-30 product claim as currently written.**

The proposed high-level direction is defensible: Ray Tune as the distributed executor, owned searcher/scheduler interfaces, a run store, workload-specific defaults, and evidence gates are a reasonable product shape. The current build program is not a valid executable derivation of the governing LaTeX, however. It omits required Tier 0 foundations, changes several specified algorithms, moves Tier 3 research into the Tier 2 critical path, has irreconcilable staffing arithmetic, cannot execute its own early gates, and treats statistical validation campaigns as a substitute for software correctness, recovery, and scale testing.

The governing validation chapter also needs correction before it can be authoritative. Several rules confuse failure to detect a difference with proof of equivalence, key thresholds lack power/effect-size policy, and important system properties are outside V01-V15. Copying the LaTeX into the build program would fix drift but would not by itself produce a sound test strategy.

The current workspace has **zero executable product tests**: `pytest -q` and `pytest --collect-only -q` both return exit code 5 with no tests collected. The only files under `tests/` and `validation/` are `.gitkeep` placeholders. There is no package metadata, CI configuration, validation manifest, pinned task, schema migration, or implementation file.

For NAS, the scope must be stated plainly. The survey deliberately supports only moderate joint HPO/NAS over width, depth, and structural flags, and explicitly excludes topology search, one-shot supernets, grammar spaces, and a zero-cost proxy subsystem (`09-workloads.tex:234-270,299-388`; `12-roadmap.tex:151-160`). The program is therefore **not a plan for a general large-scale NAS product**. It is not yet sufficient even for the narrower BG-PBT architecture-coordinate use case because architecture transitions, distillation, compatibility, FLOP/parameter objectives, and validation are missing.

## What is sound

These decisions should be retained while the program is rewritten:

- Separating search intelligence from Ray execution is a sound ownership boundary (`11-architecture.tex:46-95`).
- Making objectives, seeds, fidelity, costs, vetoes, and lineage first-class is correct for the stated workloads (`15-contracts.tex:20-50,163-205`).
- A cheap deterministic layer, realistic workload campaigns, and standing production diagnostics are useful distinct test layers (`16-validation.tex:16-50`).
- Precommitted demotion rules are better than treating every experimental method as a permanent feature (`16-validation.tex:337-348`).
- The survey's restrained NAS scope is sensible for the currently named projects. It should not be marketed as broader NAS coverage.
- The LaTeX source is mechanically buildable: a diagnostic `pdflatex` run completed successfully and produced 111 pages. It emits duplicate page-destination warnings, but no content-blocking LaTeX error.

## Blocking findings

### B1. Timeline, effort, and staffing do not reconcile

The program states 42 engineer-weeks through week 30 (`BUILD_PROGRAM.md:4,13,237-246`), but its detailed work adds to 32 engineer-weeks:

| Segment | Stated calendar | Listed work | Actual listed effort |
|---|---:|---:|---:|
| Phase 0 | weeks 1-2 | 10 engineer-days | 2 engineer-weeks |
| Tier 0 | weeks 3-6 | 30 engineer-days | 6 engineer-weeks in a 4-week window |
| Tier 1 | weeks 7-12 | 30 engineer-days | 6 engineer-weeks |
| Tier 2/3 | weeks 13-30 | 90 engineer-days | 18 engineer-weeks, not the 30 charged in the cost table |
| Total | weeks 1-30 | 160 engineer-days | 32 engineer-weeks, not 42 |

The likely source of the 42-week number is the governing roadmap: about 6 weeks through Tier 0, 6 for Tier 1, 18 for Tier 2, and about 12 for selective Tier 3 (`12-roadmap.tex:213-225`). That roadmap places Tier 3 at week 31 onward, while the build program charges its 12 weeks before week 30 without scheduling them.

The phrase "one-engineer assumption" also conflicts with the Tier 2 note requiring 1.5-2 engineers (`BUILD_PROGRAM.md:11,153,246`). The dependency diagram says the critical path is 16 weeks, but the directly listed TuRBO, PB2-Mix, and BG-PBT durations total about 11.4 weeks (`BUILD_PROGRAM.md:103-107,155-167,233`).

The compute envelope is not reconciled either. The program budgets five GPU-weeks for all campaigns (`BUILD_PROGRAM.md:237-246`), while the validation chapter's own V07 illustration is 640 accelerator-hours (`16-validation.tex:206-216`), about 3.8 168-hour accelerator-weeks before V08 or any other layer-two test. "GPU-week" is not defined as aggregate device time, node time, or campaign wall time, and no capacity or contingency turns several GPU-weeks of aggregate work into a one-week gate campaign.

**Required correction:** Rebuild the plan from a work-breakdown spreadsheet with one unit, named owners, dependencies, utilization, campaign wall time, and 25-40% integration/operational contingency. Report engineer-weeks, accelerator-hours, and calendar weeks separately. Do not retain the week-6/week-12/week-30 dates until resource capacity and the task pilots support them.

### B2. The program is materially inconsistent with the governing roadmap

The previous reconciliation fixed some V-test labels, but it did not reconcile product scope or algorithms. The following are substantive mismatches:

| Governing requirement | Governing source | Current program | Consequence |
|---|---|---|---|
| GP + qLogEI ships in Tier 0 | `12-roadmap.tex:29-34,51-67`; `04-bayesian.tex:840-866` | No GP implementation task or shipped Tier 0 GP; nevertheless V04/V05 invoke one (`BUILD_PROGRAM.md:46-88`) | Tier 0 cannot pass V04 or V05 |
| Dimension-scaled GP lengthscale priors are Tier 0 and always on | `12-roadmap.tex:33-34`; `04-bayesian.tex:864-866` | Omitted | Governing default is absent |
| CMA-ES is a low-priority wrapped method | `03-model-free.tex:264-267`; `12-roadmap.tex:51-60` | Omitted | Register row has no schedule slot |
| PASHA is an ASHA option | `05-multifidelity.tex:504-506`; `15-contracts.tex:140-144` | Omitted | Specified scheduler capability is absent |
| DEHB is a Tier 3 reimplementation against owned interfaces | `05-multifidelity.tex:497-503`; `12-roadmap.tex:42,139-143,213-216` | Moved to Tier 0 as a vendor/thin wrap (`BUILD_PROGRAM.md:47,54-57`) | Changes tier, risk, ownership, and V07 ordering |
| Mixed-space trust-region work is the Tier 2 prerequisite in weeks 13-20 | `12-roadmap.tex:199-205` | Moved into the six-week Tier 1 bundle (`BUILD_PROGRAM.md:92-107`) | Crowds out Tier 1 and changes the governing calendar |
| Tier 1 includes Chebyshev fallback, wrapped NSGA-II, Pareto/front and hypervolume reporting | `07-multiobjective.tex:527-568`; `12-roadmap.tex:74-81` | Only qLogNEHVI is shipped; scalarization appears only as a comparator and NSGA-II/reporting are absent | The demotion fallback and V09 oracle do not exist |
| Priors use the decaying piBO acquisition multiplier and nonzero-support guard | `08-priors-transfer.tex:14-41,368-380` | Prior is put into the GP mean and observation-noise floor (`BUILD_PROGRAM.md:109-113`) | Implements a different, unjustified method and conflates an optimum-location prior with observation noise |
| PriorBand uses a rung-dependent portfolio of uniform, prior, and incumbent samplers | `08-priors-transfer.tex:76-91,381-384` | Samples from "top-K prior density" (`BUILD_PROGRAM.md:126-128`) | Removes the mechanism intended to recover from bad advice |
| First-wave warm start is a ranked/quantile query; RGPE is second wave | `08-priors-transfer.tex:93-142,385-390` | Builds an "RGPE-light" pooled GP immediately (`BUILD_PROGRAM.md:130-133`) | Adds unbudgeted research before enough history exists |
| EI-per-cost with cooling and a predictive/censored cost model is Tier 1 | `12-roadmap.tex:40,94-113`; `08-priors-transfer.tex:396-403` | Omitted | Cost-aware HPO promise is not delivered or tested |
| ifBO uses the published pretrained surrogate and is tested before integration | `05-multifidelity.tex:279-306,507-528`; `08-priors-transfer.tex:391-395` | Collects curves and builds a power-law/saturation model, then runs V15 (`BUILD_PROGRAM.md:169-173`) | This is a different research project and reverses the go/no-go gate |
| HEBO-style robustness is selective Tier 3 | `12-roadmap.tex:43-44,143-147,213-218` | Omitted from the combined Tier 2/3 scope | The "full" 42-week scope is not full |
| Architecture requires Ray and local executor adapters | `11-architecture.tex:62-67`; `15-contracts.tex:192-205` | Lists an RLlib adapter and a generic callback adapter, not the two executor-conformance adapters (`BUILD_PROGRAM.md:70-73`) | Local low-overhead execution and executor parity are unplanned |

The generated register is also stale relative to the LaTeX: it labels DEHB and ifBO as Tier 2 (`product_register.json:119-137`), while the current roadmap and validation table place them in Tier 3. It therefore cannot serve as the claimed machine-readable authority.

**Required correction:** Build a generated traceability matrix from every decision-box item to contract, implementation, deterministic tests, validation entry, tier, owner, effort, and fallback. Any intentional deviation must first change the governing LaTeX and register in the same review.

### B3. Phase 0 does not freeze the contracts the survey says are load-bearing

The governing contracts specify much more than a YAML parser and capability flags:

- `StudySpec`: objective vector, direction, evaluation protocol, tuning/test seed separation, full-run-equivalent budget, concurrency, and boundary override (`15-contracts.tex:20-50`).
- `SearchSpace`: continuous/ordinal/categorical semantics, transforms, conditions, priors, and capability rejection (`15-contracts.tex:52-88`). The product chapter says "four knob kinds," while the contract lists three, so the governing document itself must clarify whether integer is distinct from ordinal (`14-product.tex:48-50`; `15-contracts.tex:58-83`).
- `Searcher`: batch `propose`, partial-result `observe`, pending-trial behavior, capabilities, and state snapshot/restore (`15-contracts.tex:90-127`).
- `Scheduler`: report/continue/stop/pause, promotion, veto gates, exploit/explore, and decision reasons (`15-contracts.tex:129-161`).
- Store: complete declarations, vector objectives, per-rung curves/costs, vetoes, lineage, fronts/incumbents over time, diagnostic values, and query surfaces (`15-contracts.tex:163-190`).
- Executors: save/copy/resume semantics and measured cost (`15-contracts.tex:192-205`).

`BUILD_PROGRAM.md:25-38` does not specify most of these. It also omits essential engineering semantics not resolved by the LaTeX: stable IDs, schema/version migration, canonical configuration hashing, inactive conditional values, duplicate proposals, event ordering, idempotent retries, NaN/Inf/missing metrics, failure/cancellation policy, checkpoint format/version, artifact retention, resource requests, and compatibility across restore.

Freezing interfaces before small executable spikes is especially risky. The survey itself says construction can falsify the contracts (`15-contracts.tex:207-218`).

**Required correction:** Make Phase 0 a contract-and-risk-spike phase, not a freeze-first phase. Require executable conformance tests for one searcher, one scheduler, both executor adapters, store recovery, and checkpoint resume before stakeholder freeze.

### B4. The declared gates cannot establish the claimed tier outcomes

1. Tier 0 declares all four workload templates as `NotImplementedError`, but V14 requires the real PPO/Brax day-one walk, seed protocol, store, scheduler, and final held-out evaluation (`BUILD_PROGRAM.md:49,75-88`; `14-product.tex:60-125`; `16-validation.tex:114-116`). `rl_routine` is never later filled, yet week-30 success claims all four templates are production-ready (`BUILD_PROGRAM.md:99,135-137,150,252`).
2. Brax is scheduled for a week-7 import spike, after the week-6 V14 gate, and `setup/INSTALL.md` defers it until V07/V08 (`BUILD_PROGRAM.md:204`; `setup/INSTALL.md:50-55`).
3. Tier 1 ships MO-ASHA and sampler veto behavior but does not gate V06, V10, or V13 until week 30 (`BUILD_PROGRAM.md:121-139,175-180`). The governing roadmap gates them at week 12 (`12-roadmap.tex:190-197`). A capability may not be called production-ready 18 weeks before its correctness gate.
4. V09 requires qLogNEHVI against both Chebyshev and wrapped NSGA-II; the program omits NSGA-II (`16-validation.tex:101-103`; `BUILD_PROGRAM.md:115-119,139`).
5. V08 requires both sides of the worker boundary, while the gate only states the above-eight home regime (`16-validation.tex:96-100,218-249`; `BUILD_PROGRAM.md:176,180`). Concurrency and total run budget are also conflated as "8-worker and 16-run boundaries" (`BUILD_PROGRAM.md:167`).
6. V15 is a pre-integration feasibility gate in the survey but a post-build campaign in the program.
7. "15 validation tests passing" conflicts with legitimate demotion, cancellation, unresolved, and insufficient-history outcomes (`BUILD_PROGRAM.md:252-253`). A successful simpler product may correctly record V09 as demoted or V12 as not yet eligible.
8. Repository guidance still advertises the old incomplete gates: Tier 1 is only V04/V09/V11 and Tier 2 is only V07/V08/V15 in `README.md:46-56` and `docs/progress.md:25-101`. A builder following the progress tracker will not execute the current build program, much less the LaTeX.

**Required correction:** Define gate result states (`pass`, `demote`, `block`, `unresolved`, `not eligible`, `not applicable`) and the permitted release state for every entry. Nothing ships as a default before its deterministic tests and tier validation are complete.

### B5. Current testing is absent, and the planned testing is not a software test strategy

The work breakdown budgets one day for store CRUD/lineage unit tests, one CartPole integration test, and statistical campaigns (`BUILD_PROGRAM.md:64-86`). It does not budget unit/property tests for contracts, transforms, conditional spaces, searcher state, acquisition behavior, scheduler state machines, vetoes, checkpointing, cost metering, objective direction, seed isolation, or adapter conformance.

Statistical method campaigns answer "does this method earn its default on these tasks?" They cannot establish thread safety, retry semantics, persistence, replay determinism, or recovery. V01-V15 should sit above a conventional correctness and reliability suite, not replace it.

**Required correction:** Add the test layers and release gates described below, with explicit engineering allocation. A realistic foundation will take materially more than the current three Tier 0 validation-prep days.

### B6. The BG-PBT and NAS implementation outline is not faithful enough to be valid

The governing BG-PBT description requires mixed continuous/ordinal/categorical modeling, trust-region expansion/shrink/restart, generation changes on stagnation, architecture proposals, and on-policy distillation into changed architectures (`06-population.tex:187-241`; `12-roadmap.tex:115-130`). The program instead lists weight copying, a trust-region explore step, and an unexplained "age-weighted selection" heuristic (`BUILD_PROGRAM.md:161-167`).

Raw checkpoint copying cannot generally transfer weights or optimizer state when widths/depths change. Distillation is not optional glue; it is the mechanism that makes architecture changes feasible. The program has no architecture factory contract, tensor-shape compatibility policy, teacher/student protocol, architecture proposal stage, parameter/FLOP objective, latency/memory measurement, or failure tests for invalid architectures.

The dependency graph is also confused: PB2-Mix's original continuous PB2 plus categorical bandit is not the same searcher as mixed-space TuRBO, yet the plan calls TuRBO a hard PB2-Mix dependency while implementing continuous PB2 separately (`BUILD_PROGRAM.md:155-159,227-229`). This must be resolved at the design level.

**Required correction:** Either implement faithful BG-PBT with a separately budgeted distillation/architecture-transfer workstream and reference parity tests, or reduce scope to fixed-architecture PBT/PB2 and call it that. For broader topology NAS, create a new governing document and product program; it is explicitly outside this one.

### B7. Large-scale execution and persistence are deferred out of the product

SQLite plus direct trial reporters is not a credible unspecified write path for many concurrent Ray trials (`BUILD_PROGRAM.md:64-73`). SQLite can be acceptable for a single-user local beta only if all writes are serialized through one durable writer and recovery is tested. PostgreSQL, monitoring, stall detection, and deployment are currently optional after the product is declared successful (`BUILD_PROGRAM.md:184-192,250-257`). At large scale, durable coordination, observability, retry policy, and resource enforcement are core correctness.

The program does not cover:

- Ray driver death, worker/node loss, preemption, network partitions, duplicate events, late reports, or checkpoint corruption.
- Scheduler/searcher snapshot recovery and exactly-once logical observation under at-least-once execution.
- Backpressure, proposal throughput, database write throughput, queue growth, or study-level fairness.
- CPU/GPU/memory/custom-resource declarations, placement groups, heterogeneous accelerators, autoscaling, or quotas.
- Artifact/checkpoint storage, checksums, retention, garbage collection, and disaster recovery.
- Study cancellation, hard cost caps, runaway-trial termination, and budget reconciliation.
- Metrics, logs, alerts, runbooks, support ownership, compatibility policy, and upgrade tests.
- Security boundaries for user-supplied train functions, YAML/file paths, credentials, and untrusted checkpoints.

**Required correction:** Define a mandatory "distributed internal beta" gate before the week-30 ship decision. REST and Kubernetes can remain optional if users submit Python locally, but persistence, monitoring, recovery, resource policy, and a tested cluster deployment cannot.

### B8. The package and environment are not reproducible or installable as a product

There is no `pyproject.toml`, package namespace, lock file, build command, CI workflow, lint/type policy, coverage configuration, or release artifact. The declared `src/` directories are empty. The `.git` directory in this workspace is empty, so there is no usable repository history or commit identity to record in study provenance.

The environment specification does not satisfy its own Tier 0 claim:

- `ray[tune]` is listed, but the plan requires RLlib; the RLlib extra is not declared (`setup/environment.yml:14-16`).
- Brax, DEHB, YAHPO-Gym, HPOBench, ARLBench, and replay fixtures needed by the gates are absent (`setup/INSTALL.md:50-55`; `16-validation.tex:21-39`).
- Ray alone is pinned exactly; Torch, BoTorch, GPyTorch, Optuna, ConfigSpace, pandas, scikit-learn, and others are open-ended lower bounds (`setup/environment.yml:16-25`), contrary to the governing promise of pinned versions and upgrade parity (`12-roadmap.tex:237-255`).
- No schema/migration, validation, property-test, benchmark, or database dependency is declared.
- The handoff reports dry-run dependency resolution, but no `hponas` conda environment is installed now; dry-run resolution is not an import, CUDA, RLlib, checkpoint, or runtime compatibility test.

**Required correction:** Add a normal Python package, lock the full environment per supported CPU/CUDA profile, record all component/hardware versions in studies, and make a clean-machine build plus smoke study a CI/release requirement.

### B9. Workload coverage does not match the stated users

The target names RL, Hamiltonian networks, samplers, and multi-objective finance (`BUILD_PROGRAM.md:2`), but the only concrete multi-objective template is Hamiltonian. Finance has no template, pinned task, schema extension, or validation. The generated `product_register.json` compounds this: it claims no anchors are pending (`product_register.json:4`) but collapses all workload decisions into one malformed RL row (`product_register.json:266-270`), losing separate sampler, Hamiltonian, finance, and NAS traceability.

The program also calls two templates production-ready after one engineer-day each (`BUILD_PROGRAM.md:135-137`). That estimate excludes domain fixtures, reference outputs, data/versioning, seed protocols, failure cases, user documentation, and acceptance runs.

**Required correction:** Decide whether finance is a fifth configured workload, a parameterization of the Hamiltonian multi-objective template, or out of scope. Give each supported workload its own owner, task manifest, acceptance criteria, maintained example, and contract/register row.

### B10. The risk register and success definition are not decision-operational

The six risks in `BUILD_PROGRAM.md:196-205` have no owner, exposure estimate, evidence source for likelihood, contingency reserve, or committed follow-up action. Several tripwires are mistimed or unmeasurable:

- The BG-PBT trigger is an "informal" win rate below 50% with no task, sample size, uncertainty, or matched-budget definition, and its DEHB fallback is itself moved between tiers.
- The mixed-space TuRBO risk is rated low because the adaptation is called thin and production-tested, while the governing roadmap budgets weeks for ordinal/categorical mixed-space work (`12-roadmap.tex:115-130,199-205`).
- The ifBO trigger occurs during model construction, even though V15 is supposed to decide whether any integration work begins.
- The ASHA pilot is scheduled for week 10, but the program does not allocate V06 implementation until weeks 28-30 (`BUILD_PROGRAM.md:175-180,203`).
- The Brax import trigger occurs after the gate that needs the Brax day-one study.

The week-30 success list likewise has no availability, recovery-time, maximum lost-work, throughput, submission latency, budget-overshoot, reproducibility, or support target (`BUILD_PROGRAM.md:250-257`). "Ray Tune proven stable" and "documentation sufficient" are not auditable acceptance criteria.

**Required correction:** Give every material risk an owner, leading indicator, exact measurement, trigger, decision deadline, funded response, and residual risk. Define internal-beta service and science SLOs before calling templates production-ready.

## Validation-suite soundness review

### Cross-cutting statistical defects

The validation chapter's discipline is a good starting point, but the following must be fixed before results can drive release decisions:

1. **Non-significance is not equivalence.** V06 and V11 define "within noise" as a 95% bootstrap interval of the difference overlapping zero (`16-validation.tex:165-175`). That only means a difference was not detected. Use a preregistered non-inferiority/equivalence margin and a confidence interval entirely inside it, or a TOST-style decision.
2. **Ten repetitions is not a power analysis.** The protocol fixes at least ten repetitions but gives no minimum detectable effect, variance estimate, or adaptive/sequential rule (`16-validation.tex:127-139`). Run pilots, estimate variance, and set repetitions from the decision margin. Keep a maximum budget and inconclusive state.
3. **The sampling hierarchy is underspecified.** Optimizer RNG seeds, workload/training seeds, evaluation/test seeds, tasks/environments, and configurations are different sampling levels. A flat bootstrap over runs can be pseudoreplication. Use paired/common-random-number designs where valid and hierarchical bootstrap/mixed-effects analysis across tuner runs and tasks.
4. **One pinned task per family invites benchmark overfitting.** Development and acceptance on the same task turns the suite into a target. Use development tasks plus held-out acceptance tasks/environments, and rotate only through a versioned process.
5. **No multiplicity policy exists.** V04 tests many searchers/tasks/curves and V09 multiple comparators/objectives. Predeclare primary endpoints and control family-wise error or false discovery where ranking claims are made.
6. **Budget units are too idealized.** Charging a partial run proportionally assumes linear cost and omits startup, evaluation, checkpoint, queue, and optimizer overhead (`16-validation.tex:171-175`). Report actual accelerator-seconds, CPU-seconds, wall clock, energy/cost if available, and full-run equivalents as a normalized secondary measure.
7. **Artifacts and preregistration are not operationalized.** There is no manifest format, task checksum, immutable seed set, analysis script, environment digest, or signed gate report. JSON/CSV validation results are ignored by `.gitignore:42-49` without an alternative artifact registry.
8. **The repetition rule is internally ambiguous.** The chapter says every layer-two comparison has at least ten repetitions and V08 is the only exception (`16-validation.tex:127-139`), but V10 is defined as one 100-configuration, single-seed pilot and V13 does not state ten independent campaign repetitions (`16-validation.tex:256-309`). The unit of repetition must be explicit per test.

### V01-V15 findings

| Test | Assessment | Required improvement |
|---|---|---|
| V01 | A stochastic optimizer's final value within 0.5% and exact rank equality is not a reliable wrapper-parity oracle; relative tolerance is undefined near zero and awkward for negative objectives (`16-validation.tex:159-163`). | For identical code paths, compare proposed configurations/state transitions under fixed event streams. For stochastic references, use distributional regression with absolute+relative tolerances, tied-rank policy, and versioned benchmark snapshots. |
| V02 | Recorded-curve replay is valuable but covers only a clean event order. | Add state-machine/property tests for simultaneous reports, out-of-order/duplicate/late events, stragglers, worker loss, pause/resume, retry, snapshot restore, and deterministic decisions after recovery. |
| V03 | Three planted defects are too narrow, and a dropped seed is not clearly guaranteed to be caught by V01/V02 (`16-validation.tex:79-81,311-320`). | Use mutation testing against contract/state-machine code and require a mutation score. Include objective direction, inactive conditional values, seed leakage, duplicate observation, checkpoint mismatch, and cost-accounting mutants. |
| V04 | "Every shipped searcher beats log+Sobol" ignores method home regimes and has no effect-size, task aggregation, or inconclusive policy. No optimizer can be expected to dominate on every task. The build also calls the floor a "log+Sobol GP" and compares it to random (`BUILD_PROGRAM.md:88`). | Define capability-specific home regimes and non-inferiority/superiority margins. Use several development and held-out tasks. Keep log+Sobol as the floor, and separately test the Tier 0 GP+qLogEI and TPE. |
| V05 | "Warped must not lose" can pass on a tie, so it does not establish that the transform matters as claimed (`16-validation.tex:88-89`). | Require non-inferiority across broad tasks and a positive material gain on preregistered scale-sensitive tasks; define the exact input/output transform and invalid-domain behavior. |
| V06 | CI overlap is not equivalence, and one-third normalized compute may not be one-third actual cost. | Use a quality non-inferiority margin, actual cost accounting, performance-over-budget curves, slow-starter recall, and multiple tasks/fidelity definitions. Gate ASHA before calling Tier 1 production-ready. |
| V07 | One PPO/Brax task at exactly 16 full runs does not support the stated 10-64 run routine-RL regime (`05-multifidelity.tex:497-503`). A winner/tie rule is missing. | Test at least low/mid budget points and more than one representative task or a held-out ARLBench set. Include random/TPE floor, paired seeds, overhead, and explicit win/tie/inconclusive decisions. |
| V08 | Three repetitions and unanimous ordering have very low power. The protocol can falsify but explicitly cannot promote on weak evidence (`16-validation.tex:218-249`), yet T2 completion requires green. Exact below/above worker counts, population sizes, wall-clock target, and non-inferiority margin are absent. | Define the initial status and what green means, both sides (for example 4 and 8/16 workers), matched compute and wall-time endpoints, task set, effect margin, and sequential maximum sample. Treat three-rep unanimous loss only as an early stop, not the whole analysis. |
| V09 | Hypervolume depends strongly on objective normalization and a fixed reference point. The build's "worst-seen + margin" changes between methods/runs and can bias comparison (`BUILD_PROGRAM.md:115-119`). CI-band overlap is not a valid equivalence test (`16-validation.tex:183-187`). | Freeze direction, normalization, feasibility policy, and reference point from domain bounds or an independent pilot. Use paired differences/non-inferiority, include NSGA-II, and test finance if it remains a customer. |
| V10 | Spearman rho on 100 configurations at one fixed seed does not measure the costly failure mode: culling a future Pareto-optimal slow starter (`16-validation.tex:256-274`). A rho above 0.6 can coexist with unacceptable top-set false negatives. | Use multiple seeds/tasks and out-of-sample configurations. Gate on top-k/Pareto survivor recall, false-cull probability, and regret as well as rank correlation. Select the rung before acceptance data. |
| V11 | The build does not implement piBO or PriorBand faithfully. "Good prior helps" has no minimum benefit, and wrong-prior recovery again uses non-significance as safety. | Test the actual decaying multiplier and rung portfolio over several prior qualities, require nonzero support, predefine early gain and worst-case recovery margins, and report regret over budget. |
| V12 | Ten vaguely "similar" studies do not establish transfer validity (`16-validation.tex:189-193`). Synthetic history in the build bypasses the registered real-history precondition (`BUILD_PROGRAM.md:130-133`). Trial count also ignores unequal cost. | Define task/space compatibility and leakage rules, use leave-one-study/task-out evaluation, freeze the target before observing the new study, and measure cost/time-to-target with uncertainty. Keep `not eligible` until real history exists. |
| V13 | Visual multimodality detection and post-hoc reinitialization are subjective (`16-validation.tex:276-309`). A one-standard-error mean rule has about 68% nominal coverage even for a correct sampler, worsens across many marginals, ignores uncertainty in both estimates, and leaves variance agreement unquantified. | Separate scheduler veto unit tests from scientific validation. Use known-target/SBC fixtures where possible, rank-normalized R-hat plus bulk/tail ESS, MCSE-aware two-sample comparisons with multiplicity policy, explicit variance/distribution metrics, and automated mode diagnostics. |
| V14 | The executable workload does not exist. The standing rung-to-final correlation is unobservable for killed trials and is biased if calculated only on survivors (`14-product.tex:105-118`). | Build one real `rl_routine` vertical slice in Tier 0, specify every asserted artifact, and use replay/audit full-run samples or censoring-aware diagnostics for stopped trials. Add an explicit test that test seeds never reach the searcher. |
| V15 | Public-suite feasibility before integration and adapter correctness after integration are different claims. The program performs the first after building a different curve model. | Split V15 into pre-build feasibility of the published pretrained ifBO model and post-integration parity/overhead/recovery tests. Cancel before integration if feasibility fails. |

### Missing test layers

The following suites are required in addition to V01-V15:

| Layer | Minimum coverage | Cadence |
|---|---|---|
| Contract/unit | Schema validation, canonical serialization, conditions, transforms, prior support, objective direction/vector, seed split, budget arithmetic, NaN/failure semantics | Every change |
| Property/state-machine | Searcher ask/tell and pending points; scheduler rung/promotion/veto; idempotency; invariants under arbitrary event order | Every change |
| Store/migration | Transactions, concurrent writers or serialized writer, crash recovery, migration forward/back, indexes, lineage/front queries, backup/restore | Every change/nightly |
| Adapter conformance | Same study semantics on local and Ray; resource mapping; reporter events; cancel/pause/resume; checkpoint hash/state compatibility | Every change/nightly |
| Fault/chaos | Worker/node/driver loss, duplicate/late results, preemption, full disk, corrupt checkpoint, database disconnect, retry exhaustion | Nightly/release |
| Load/scale | Proposal latency, event throughput, DB throughput, queue/backpressure, memory, control-plane stability at target concurrent trials and study count | Release/capacity change |
| Reproducibility | Clean install, environment lock, deterministic replay, study manifest, code/data/container/hardware provenance, artifact checksum | Release |
| Workload acceptance | Real maintained example for every supported template, held-out seeds/tasks, budget cap, expected output/audit report | Tier/release |
| Dependency upgrade | V01/V02 plus adapter/checkpoint migration across every proposed Ray/Optuna/BoTorch update | Dependency PR |
| Security/abuse | Path handling, unsafe deserialization, secrets/log redaction, resource exhaustion, authorization if multi-user | Release |

## Architecture changes required for large-scale HPO

### Control plane and event semantics

Use one authoritative study coordinator per study. Give every report and scheduler decision a stable event ID and monotonic per-trial sequence. Observation, promotion, stop, pause, checkpoint registration, and budget debit must be idempotent. Persist searcher and scheduler snapshots with a version and the last applied event ID, then prove deterministic replay after coordinator restart.

### Store and artifacts

Do not let arbitrary trial workers contend on SQLite. For a laptop mode, serialize writes through the coordinator/writer actor with WAL, transactions, timeouts, backup, and crash tests. For a distributed internal beta, use PostgreSQL or another supported concurrent store from the start of cluster acceptance. Store checkpoint/artifact URIs and hashes in the database, not large blobs; define immutable manifests, retention, and garbage collection.

### Resource and budget model

Add trial resource bundles (CPU, GPU, accelerator type, memory, custom resources), placement constraints, checkpoint cost, and evaluator resources to `StudySpec`. Enforce hard study and trial budgets from measured usage. RL fidelity should be environment steps or another workload resource, not blindly `training_iteration` (`BUILD_PROGRAM.md:71`), whose cost can vary with configuration.

### Reproducibility and provenance

Record package/algorithm versions, source commit, dirty-state digest, schema version, environment/container digest, task/data checksum, hardware, optimizer seed, training seeds, test-seed policy, and full study declaration. Retry must not accidentally reuse or change a logical seed. Protected test seeds must be inaccessible to searcher/scheduler code until selection is frozen.

### Multi-objective and constraints

Freeze objective direction, normalization, missing/failure semantics, constraint feasibility, reference point, and front tie policy in Phase 0. Hypervolume-over-budget and Pareto-front output are product features, not campaign-only calculations.

## NAS-specific product boundary

The product can reasonably support **moderate joint HPO/NAS** if it adds:

- Typed width/depth/flag axes, validity/forbidden constraints, and deterministic model construction.
- Parameter count, FLOPs, peak memory, latency/throughput, and hardware identity as measured outputs/objectives.
- Architecture-aware checkpoint compatibility and a refusal to raw-copy incompatible tensors.
- A defined generation/stagnation trigger, architecture proposal method, teacher selection, distillation loss/schedule, and rollback on failed transfer.
- Baselines that include random architecture search plus ASHA and fixed-architecture HPO at matched cost.
- Held-out retraining from scratch of selected architectures to distinguish search benefit from weight inheritance.

It cannot claim general large-scale NAS without a new scope that covers hierarchical/topology spaces, architecture validity, distributed model construction, weight-sharing bias if introduced, hardware-aware objectives, benchmark protocol, and a substantially larger compute/engineering budget. That broader claim would contradict the present governing survey.

## Recommended re-plan

### R0. Specification correction and scope decision

Do not freeze interfaces yet. First decide whether the target is internal large-scale HPO with moderate architecture axes, or general NAS. Repair the LaTeX validation statistics, Tier 3 timing, four-vs-three knob-kind ambiguity, V08 release semantics, and finance-workload status. Regenerate a valid product register with one row per decision.

Exit criteria:

- One authoritative versioned requirements/validation manifest.
- Every decision has contract, implementation, tests, tier, effort, owner, fallback, and artifact destination.
- V01-V15 analysis plans reviewed by an engineer plus a statistically qualified reviewer.
- Calendar recomputed from staffed dependencies and measured task pilots.

### R1. Executable architecture spike

Build the smallest real vertical slice before interface freeze: one `StudySpec`, a mixed/conditional `SearchSpace`, Sobol or random searcher, ASHA, local executor, Ray executor, serialized store writer, checkpoint/resume, seed-separated objective aggregation, and a real small workload. Add state-machine, restart, and conformance tests.

Exit criteria:

- Clean install from a lock on CPU and the target CUDA profile.
- Local and Ray runs produce semantically equivalent audit records.
- Coordinator/store crash and resume are proven without duplicate observations or budget debit.
- Stakeholders review interfaces informed by executable failures.

### T0. Foundation and honest day-one product

Implement the actual governing Tier 0: random/Sobol/log transforms, TPE, GP+qLogEI with dimension-scaled priors, ASHA/median/PASHA, Ray/local adapters, store/provenance, and a functional `rl_routine`. Keep DEHB in Tier 3 unless the governing roadmap is explicitly revised. Treat CMA-ES as low priority but account for it.

Gate deterministic correctness first, then corrected V01-V05 and V14. V06 may occur at the next campaign as the survey states, but ASHA must not be marketed as validated on real workloads before it passes.

### T1. Multi-objective, priors, transfer, and cost

Ship complete fallback paths: qLogNEHVI, Chebyshev, wrapped NSGA-II, front/hypervolume reporting, MO-ASHA/veto, piBO, faithful PriorBand, ranked warm-start query, and EI-per-cost. Do not build RGPE until enough history exists. Give Hamiltonian, sampler, and finance-if-in-scope real templates.

Gate corrected V04, V06, V09, V10, V11, and V13. Mark V12 not eligible until its data precondition is real.

### T2. Population line only

Build mixed-space trust-region search, expose PBT, then PB2-Mix and a faithful BG-PBT path with architecture transfer/distillation. Run a checkpoint/architecture compatibility gate before full campaigns. V08 is the T2 method gate, with a statistically defensible sequential protocol and both sides of the boundary.

### T3. Independent electives after week 30

Run V07 before choosing whether to reimplement DEHB. Run the ifBO feasibility half of V15 before integration, adopt the pretrained model rather than train a replacement, then run post-integration tests. Add HEBO-style robustness only after the base GP is stable. Each item has an independent funding and release decision.

### Mandatory distributed-beta hardening

Before broad internal use, require persistent multi-process storage, backup/restore, monitoring/alerts, failure/retry policy, hard budget controls, scale/load results, artifact retention, security review, user runbook, and support ownership. Kubernetes and REST can remain optional deployment choices; operational correctness cannot.

## Approval checklist

The program can move from RED to conditional approval only when all of the following are true:

- [ ] Scope says moderate architecture-coordinate NAS or supplies a separately approved general-NAS plan.
- [ ] Governing LaTeX, product register, build program, README, and progress tracker have one tier/test mapping.
- [ ] Timeline math and campaign capacity reconcile with named staffing and contingency.
- [ ] Tier 0 includes GP+qLogEI, its required defaults, both adapters, and a functional day-one workload, or the LaTeX is amended.
- [ ] piBO, PriorBand, warm start, BG-PBT, and ifBO descriptions match the methods actually authorized.
- [ ] V01-V15 have preregistered tasks, seeds, margins, power/repetition policy, analysis, decision states, and immutable artifacts.
- [ ] Non-inferiority/equivalence replaces "CI overlaps zero" wherever safety or matching is claimed.
- [ ] Deterministic unit/property/conformance/recovery tests exist below the statistical campaigns.
- [ ] Package, environment locks, provenance, CI, migrations, and clean-install tests exist.
- [ ] Store/control-plane semantics survive concurrency, duplicate events, and restart.
- [ ] Distributed scale, fault, monitoring, and hard-budget gates are mandatory before broad internal use.
- [ ] Each supported workload, including finance if retained, has a maintained template and held-out acceptance task.

## Final recommendation

Authorize only a **corrective specification and architecture-spike phase**, not the current interface freeze or Tier 0 schedule. Preserve the architecture direction and evidence-gate philosophy, but rebaseline the product from the governing decisions, repair the validation statistics, and make distributed reliability a core deliverable.

After those changes, the project can be a credible internal large-scale HPO system with moderate NAS coordinates. As written, it would more likely deliver a collection of method prototypes with an unauditable gate history, and it does not support a claim of general large-scale NAS.
