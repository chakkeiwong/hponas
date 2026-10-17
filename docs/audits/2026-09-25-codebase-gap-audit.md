# Codebase gap audit — 2026-09-25

**Audited commit:** `990408947c3ae0db5876fef37229b4f1dbcf7dc4` (`main`). The working tree was clean before the audit. This audit adds documentation and evidence only.

**Verdict: the stated Tier 0 goal is not yet met.** There is substantial working implementation, but incorrect gate checks, broken composition of public components, recovery defects, and incomplete real-workload validation prevent certification. The reset memo misdiagnoses the mutation counts; resetting to R8 is not supported by that diagnosis.

## 1. Goal and scope

The target is moderate architecture-coordinate HPO/NAS over roughly 2–10 architectural and training knobs, as defined in [NAS_SCOPE_DECISION.md](/home/ubuntu/workspace/hponas/NAS_SCOPE_DECISION.md:12). General cell search, supernets, weight sharing, and differentiable NAS are explicitly outside this program.

[BUILD_PROGRAM_v3.md](/home/ubuntu/workspace/hponas/BUILD_PROGRAM_v3.md:31) defines the immediate Tier 0 exit as **V01, V02, V03, V04-T0, V05, V14, and V16 all passing**. Its implementation scope includes GP+qLogEI, Random/Sobol, local/Ray execution, a functional RL workload, and reproducible state. Tier 1 adds ASHA, MO-ASHA, multi-objective search and cost-aware acquisition; priors remain opt-in. Tier 2 and distributed hardening are later milestones.

These documents do not agree everywhere. The audit uses the explicit scope and gate requirements to assess readiness, and flags disagreements rather than selecting whichever definition yields a pass. Some scheduler work is nominally Tier 1, but V02 already requires scheduler correctness under adversarial event ordering at the Tier 0 gate.

The review covered the library, both API generations, workloads and examples, tests, mutation tools, validation runners and protocols, packaging, CI, and status authorities. Runtime evidence distinguishes reproduced defects, static findings, and unexecuted campaigns. All 164 tracked Python files were checked for compilation; 882 tests were collected and a broad selection was executed. This is not a fresh full mutation, real GPU workload, or multi-node certification campaign.

## 2. Correction to V03_R10_RESET_MEMO.md

### The 588 mutants are the non-killed results

The memo reports 588 total mutants and zero kills, then infers a generation/execution failure and recommends resetting to `cb5b7e3` ([memo](/home/ubuntu/workspace/hponas/V03_R10_RESET_MEMO.md:107)). Installed **mutmut 3.8.0 hides killed mutants in `mutmut results` by default**. Its implementation explicitly skips `status == "killed"` unless `all` is enabled ([installed CLI](/home/ubuntu/miniforge3/lib/python3.13/site-packages/mutmut/__main__.py:1103)).

Both commands were executed against the retained cache:

```bash
/home/ubuntu/miniforge3/bin/python -m mutmut results
/home/ubuntu/miniforge3/bin/python -m mutmut results --all true
```

| Result | Default output | Output with `--all true` |
|---|---:|---:|
| Killed | Hidden | 1,699 |
| Survived | 169 | 169 |
| Timeout | 400 | 400 |
| No tests | 19 | 19 |
| Listed mutants | **588** | **2,287** |

**588 = 2,287 − 1,699.** The raw per-mutant output agrees with the retained `.py.meta` files. The apparent 68.03% timeout rate becomes **17.49%** when all mutants are counted. These observations explain the memo's final numbers without a missing-generation hypothesis. They do not substantiate its speculation that the R8 population was fabricated, or prove that every historical run was healthy.

**Provenance limitation:** `mutants/mutmut-stats.json` names commit `cb5b7e30e2adb9a5cec7a29ccb3d9abfd8af179c`. The `hponas/` sources have no diff between that commit and audited HEAD, but tests and mutation configuration have changed. These are **retained cache results**, not a newly reproduced mutation score for HEAD.

### Correct counting still does not establish a V03 pass

The [V03 protocol](/home/ubuntu/workspace/hponas/validation/protocols/v03_protocol.md:75) requires an overall score of at least 90%, **each in-scope module at least 90%**, zero unaccounted critical-path survivors, reviewed equivalent exclusions, and non-vacuity. Its denominator is `total − timeout − confirmed_equivalents`. It does not authorize dropping “no tests.” With no equivalent exclusions applied:

| In-scope module | Killed | Survived | Timeout | No tests | Protocol score |
|---|---:|---:|---:|---:|---:|
| `executors/local_executor.py` | 100 | 31 | 0 | 0 | **76.34%** |
| `executors/ray_executor.py` | 84 | 0 | 93 | 0 | 100.00% |
| `legacy_executors.py` | 60 | 0 | 124 | 9 | **86.96%** |
| `legacy_searchers.py` | 236 | 31 | 18 | 0 | **88.39%** |
| `schedulers.py` | 438 | 80 | 6 | 0 | **84.56%** |
| `searchers/base.py` | 35 | 1 | 2 | 0 | 97.22% |
| `searchers/gp_searcher.py` | 214 | 0 | 145 | 0 | 100.00% |
| `searchers/random_searcher.py` | 232 | 21 | 0 | 0 | 91.70% |
| `space.py` | 208 | 5 | 0 | 0 | 97.65% |
| `types.py` | 92 | 0 | 12 | 10 | 90.20% |
| **Total** | **1,699** | **169** | **400** | **19** | **90.04%** |

The two 100% scores exclude substantial timeout populations; they do not mean every mutant was killed. Four modules fall below 90%. The cache also contains three survivors in `ASHAScheduler.promote` and 23 in `LocalExecutor._execute_impl`, methods implementing protocol critical paths. Individual diffs still need equivalence review; a count alone does not show whether each survivor changes behavior.

The R8 figures quoted by the memo give **1,685 / (2,287 − 414) = 89.96%**, not 90.88%. The reported 90.88% comes from also removing the 19 “no tests” mutants. The current aggregate is **1,699 / 1,887 = 90.04%**; dropping no-tests would instead produce 90.95%. Neither aggregate overrides the module and critical-path criteria.

### V03 tooling itself has gaps

- **Parser incompatible with installed CLI.** [parse_mutmut_results](/home/ubuntu/workspace/hponas/validation/v03_mutation_testing.py:107) searches for capitalized aggregate lines such as `Killed`; mutmut emits individual names with lowercase statuses. Invoking the parser on the actual retained results returned zero for every field. It also calls the default output that hides kills and has no “no tests” field.
- **Required criteria are absent.** [analyze_results](/home/ubuntu/workspace/hponas/validation/v03_mutation_testing.py:147) checks only aggregate criteria. [write_results](/home/ubuntu/workspace/hponas/validation/v03_mutation_testing.py:212) writes empty per-module and critical-survivor arrays and hardcodes two audit checks to true. `CRITICAL_PATHS` names nonexistent `should_stop`, `_promote_trial`, and `submit` methods and is not used to enforce a verdict.
- **Configuration does not mean what the memo assumes.** [pyproject.toml](/home/ubuntu/workspace/hponas/pyproject.toml:70) sets `timeout = 120`, but installed mutmut reads `timeout_multiplier` and `timeout_constant`. Effective defaults are 15.0 and 1.0; this is not a configured fixed 120-second timeout. The registered source set also omits Study, Store, events/replay, architecture, workloads, and later searcher implementations. A V03 score cannot certify those omitted components.
- **Static classification is not a test kill.** [mutation_static_analyzer.py](/home/ubuntu/workspace/hponas/mutation_static_analyzer.py:37) also mistakes the default CLI listing for all mutants. Its “trivially killable” classification does not establish that tests execute or detect those mutations; `--apply` is an unimplemented TODO. The memo's proposed 124 pre-kills should not count as measured kills.
- **Equivalent exclusions are unresolved.** The [amendment](/home/ubuntu/workspace/hponas/validation/protocols/v03_protocol_amendment.md:6) remains PROPOSED. It requires individually confirmed entries but later asks to use extrapolated population estimates. That cannot supply a verified exclusion register for the current cache.

**Closure:** use one declared mutmut version and supported configuration, inventory the actual source population and critical methods, parse all statuses, review survivors individually, and preserve a fresh run tied to source, tests, environment, and protocol hashes. Apply every protocol criterion before recording a pass. Preserve the current evidence before any cache replacement; a git reset is not needed to repair this accounting.

## 3. Immediate gaps, in priority order

Priority here measures impact on the stated goal: **P0** invalidates a gate or an optimization result; **P1** blocks a documented capability or its reproducibility. These are audit findings, not implementation changes made in this session.

### A01 — P0: the validation system can accept unsupported passes

[V16Enforcer._check_decision_adherence](/home/ubuntu/workspace/hponas/validation/v16_audit_enforcer.py:199) validates a verdict label and the presence of `decision_criteria`, but never recomputes a verdict from the metrics. A synthetic artifact claiming `PASS` with **zero mutants and kill score zero** passed all error-level V16 checks in the audit. Protocol hash equality and file presence are useful checks, but they cannot establish that the experiment ran or met its thresholds.

[tools/gate_check.py](/home/ubuntu/workspace/hponas/tools/gate_check.py:253) uses validator source audits instead of campaign results. Those validators inspect strings in source code; for example, [V02's reference check](/home/ubuntu/workspace/hponas/validation/validators/v02_validator.py:94) accepts the presence of “original” and “replay.” The actual Tier 0 gate invocation was **blocked on V01/V05**, but marked V02 and V03 “met” despite V02's blocked scenarios and V03's broken parser. This is not a claim that the whole gate currently passes.

The parallel [task registry](/home/ubuntu/workspace/hponas/validation/task_registry.py:79) contains hardcoded passing V01/V04/V05/V14 results. They return fabricated success metrics even for zero trials or a nonexistent workload path. [ValidationRunner](/home/ubuntu/workspace/hponas/validation/runner.py:124) ignores unrecognized numeric criteria and treats every p-value as “lower is better,” contrary to its parity criterion; its Tier 0 list also omits V02/V03/V16. The audit wrapper's CLI only prints integration instructions.

**Closure:** a single executable gate must load immutable campaign artifacts, verify their provenance and schema, recompute all metrics/verdicts, and reject missing, empty, skipped, stale, or contradictory evidence. Exercise it with deliberately invalid artifacts and threshold-boundary cases. Source lint audits must remain distinguishable from experiment passes.

### A02 — P0: checkpoint resume can corrupt Study results and exceed budget

[Study.run](/home/ubuntu/workspace/hponas/hponas/study.py:91) restarts at `range(self.budget)` after loading `n_completed`. It reuses trial IDs, overwrites trial/result dictionaries, and appends new observations to the old searcher history. A completed three-trial study, saved and resumed, reported **six completed trials**, six searcher observations, but only three stored results. Its returned best value was **0.837388**, while the returned best configuration evaluated to **0.799553**.

[load_checkpoint](/home/ubuntu/workspace/hponas/hponas/study.py:180) also reconstructs `Trial(**v)` without rebuilding nested `Config`, leaving `trial.config` as a dictionary. Checkpoints directly overwrite their destination with JSON, without atomic replacement or durability handling. Automatic saves occur only every ten iterations, with no final save in `run`.

**Closure:** resume from a durable trial ledger with unique IDs and the remaining budget, reconstruct all nested types, preserve result/config identity, and write checkpoints atomically. An interrupted run and an uninterrupted run must agree on suggestions, completed evaluations, costs, and incumbent/config pairs. Resuming an already finished study must schedule zero new evaluations.

### A03 — P0: GP minimization optimizes in the wrong direction

[GPSearcher.suggest](/home/ubuntu/workspace/hponas/hponas/searchers/gp_searcher.py:105) trains on untransformed values, takes `Y_train.max()`, and uses the default maximizing qLogEI objective. `Study(maximize=False)` only changes final best-result selection; it does not change the acquisition. A four-trial minimization of `x` on `[0,1]` produced the **identical proposal trace** to maximization, including movement toward larger `x` in the acquisition phase.

The same source claims a Matérn 5/2 kernel and validates that option but never constructs the requested kernel. In the audited BoTorch environment, `SingleTaskGP(X, Y)` constructed an **RBFKernel**. This is a dependency-sensitive conformance defect; older library defaults cannot substitute for an explicit implementation.

**Closure:** define objective direction at the shared searcher/study boundary, apply it consistently to model training, acquisition, and reporting, and explicitly construct the declared kernel. Validate against an independent BoTorch reference in both directions.

### A04 — P1: the public API does not compose across the declared search space

There are two incompatible search-space types (`types.SearchSpace/Parameter` and `space.SearchSpace/Knob`), two searcher interfaces (`suggest` with `Config/Result` and `propose` with dictionaries), and separate Store trial/study models. Partial adapters do not cover the advertised combinations.

With `Knob('depth', 'ordinal', (1, 5))`, the audit reproduced:

| Component | Result |
|---|---|
| New RandomSearcher | `AttributeError`: a `RandomState` is passed to code expecting `.integers()` |
| New SobolSearcher | `UnboundLocalError`: checks for `integer`, while the Knob schema uses `ordinal` |
| New GPSearcher encoding depth 3 | `ValueError`: treats `(1,5)` as categorical choices |
| New GPSearcher decoding | Selects bound endpoints instead of the integer domain |
| GP with an inactive conditional `lr` | `KeyError: 'lr'` because every knob is read unconditionally |

Sources: [Random/Sobol adapters](/home/ubuntu/workspace/hponas/hponas/searchers/random_searcher.py:35), [GP encoding](/home/ubuntu/workspace/hponas/hponas/searchers/gp_searcher.py:209), and [Knob schema](/home/ubuntu/workspace/hponas/hponas/space.py:17).

The [README quick start](/home/ubuntu/workspace/hponas/README.md:47) also imports unexported `GPSearcher`/`LocalExecutor` and nonexistent `hponas.workloads`, omits the required GP search space, and supplies unsupported Study keywords. [Package exports](/home/ubuntu/workspace/hponas/hponas/__init__.py:12) expose only Study and the version.

**Closure:** select one canonical public schema and interface, provide explicit adapters where compatibility is retained, and run the documented quick start. Exercise continuous, ordinal, categorical, log-transformed, and conditional dimensions through the actual Study path. This is necessary for width/depth/activation NAS, even at modest dimensionality.

### A05 — P1: Study is not the promised execution and persistence coordinator

[Study](/home/ubuntu/workspace/hponas/hponas/study.py:50) accepts no scheduler, persistent Store, or event log. It always creates fidelity 1.0 trials and immediately calls synchronous `execute`, so runs are serial even with Ray. `LocalExecutor(mode='async')` fails in Study with **“Use execute_async() for async mode.”** The scalar objective callback also needs a manual adapter for workload functions that return metrics, cost, and artifacts.

The standalone SQLite [Store](/home/ubuntu/workspace/hponas/hponas/store.py:64) has useful WAL-backed CRUD, observations, artifacts, and lineage, but it is not connected to Study recovery. Its [get_pareto_front](/home/ubuntu/workspace/hponas/hponas/store.py:251) ignores the requested objective names and instead compares scalar `value` and `cost`, both as minimization objectives. It cannot persist or query the advertised general multi-objective result through that contract.

**Closure:** connect proposals, execution completions, observation updates, events, and persistence through one study lifecycle. Add fidelity/promotion coordination for Tier 1 and objective vectors/directions for multi-objective studies. Demonstrate public local, async, and Ray workflows using the same result and checkpoint semantics.

### A06 — P1: event replay does not establish deterministic recovery

[record_optimization_run](/home/ubuntu/workspace/hponas/hponas/replay.py:164) never registers the config-to-trial mapping required by GP training. Recording three trials with a two-observation warmup fails at the first model-based suggestion with **“No valid training data found.”** The verifier also omits these mappings.

[replay_suggestions](/home/ubuntu/workspace/hponas/hponas/replay.py:43) merely returns stored configurations. The separate verifier does call the searcher, but reconstructs observation timing from a numeric suffix in `trial_id` rather than replaying actual ordered events, and does not replay scheduler decisions. This cannot certify arbitrary IDs, delayed results, duplicate reports, or concurrent event ordering.

**Closure:** replay typed events in their recorded order into fresh searcher/scheduler state, with complete mappings and checkpoints. Detect a deliberately altered event or proposal, and reproduce the post-warmup GP path, promotions, and resumed execution under the V02 adversarial cases.

### A07 — P1: observation and scheduler semantics break under duplicate delivery and restore

[BaseSearcher.observe](/home/ubuntu/workspace/hponas/hponas/searchers/base.py:58) appends duplicate results although the [contract](/home/ubuntu/workspace/hponas/CONTRACT_SEMANTICS_v1.md:33) says “last wins.” Reporting value 10 followed by value 1 for the same trial leaves both entries and still returns 10 as best.

[ASHAScheduler.report](/home/ubuntu/workspace/hponas/hponas/schedulers.py:114) appends repeat reports to the rung population. Six unique trials normally yield two promotions; repeating the worst trial's report six times changes that to **four promotions**. [Scheduler checkpointing](/home/ubuntu/workspace/hponas/hponas/schedulers.py:172) omits `median_stopping`, does not restore the saved config, and leaves JSON string keys in fidelity history. A restored scheduler kept `eta=3` instead of the saved 2 and changed the next median decision from **stop** to **continue**. Constructors also lack validation against non-advancing rung sequences such as `eta=1` or `r_min=0` (static finding; the hanging cases were not launched).

**Closure:** make duplicate handling follow the declared identity/update contract; count unique eligible trials in promotion quotas. Restore complete config and typed state, reject invalid rung parameters, and test decisions after restore and under duplicate/out-of-order deliveries. These defects are relevant to V02 even before Tier 1 performance claims.

### A08 — P1: executor resource controls are incomplete

[LocalExecutor](/home/ubuntu/workspace/hponas/hponas/executors/local_executor.py:80) stores `timeout` but never applies it to execution. A 0.06-second objective with a 0.01-second timeout returned **completed**. Catching an objective-raised `TimeoutError` is not deadline enforcement.

[RayExecutor.execute_batch](/home/ubuntu/workspace/hponas/hponas/executors/ray_executor.py:82) submits every trial; `num_workers` is stored but unused as an in-flight limit. The timeout starts at each sequential `ray.get`, rather than using an execution deadline for each submitted trial. Failed infrastructure attempts report zero cost and their consumed compute is not carried into a later successful result. Retry handling and resource annotations do exist, and the bounded local Ray recheck passed.

**Closure:** define deadline, cancellation, in-flight concurrency, and retry-cost semantics, then enforce them at the public execution boundary. Demonstrate the required four-worker Study flow and failure recovery. The audit did not establish multi-node fault tolerance; the build program lists such acceptance both under Tier 0 Ray and later hardening, which needs one explicit placement.

### A09 — P1: the real architecture/workload path is incomplete

[architecture.build](/home/ubuntu/workspace/hponas/hponas/architecture.py:31) still returns `ModelStub`. Parameter/FLOP measurements are formulas over width and depth, not measurements of a constructed network. Real measurement is explicitly later-tier work in that file, but its declared Tier 0 real model build is also absent.

[rl_routine](/home/ubuntu/workspace/hponas/workloads/rl_routine.py:97) does contain real Brax PPO training and uses hidden-layer sizes, but extracts `activation` and never passes it to the network factory. It returns in-memory policy parameters without a maintained checkpoint/learning-curve artifact lifecycle. Its returned optimization `value` is evaluated on `test_seed` when supplied. Feeding that value to a searcher would expose protected evaluation performance to selection; keeping the seed number out of the configuration does not prevent this feedback.

The default V14 path is the [fast mock example](/home/ubuntu/workspace/hponas/examples/v14_day_one_walk_fast.py:106): it creates an empty checkpoint directory, fixes architecture to `[256,256]`, and never calls searcher `observe`. The [validator](/home/ubuntu/workspace/hponas/validation/v14_day_one_walk.py:45) checks directory existence and training seed columns, not loadable checkpoints, learning curves, or protected-metric flow. Its nonempty-trial check is a real improvement, but the result is still insufficient evidence for the real workload requirements.

**Closure:** demonstrate a maintained real workload through the public Study API, with architectural choices that actually alter the model, separate search/validation and held-out acceptance measurements, and loadable policy/checkpoint/curve artifacts. Verify that held-out measurements cannot alter subsequent proposals. Document which of the example NAS knobs are implemented rather than claiming the whole template.

### A10 — P1: installation, environment and CI do not reproduce the claimed baseline

Calling the declared setuptools build backend to prepare wheel metadata failed with **“Multiple top-level packages discovered in a flat-layout.”** [pyproject.toml](/home/ubuntu/workspace/hponas/pyproject.toml:1) has no explicit package discovery. Several conflicting top-level directories are tracked, so ignoring the local mutation cache alone does not resolve the layout. The documented `[all]` extra is absent; Ray/Brax/Optuna support is not fully declared by the public extras.

[requirements.txt](/home/ubuntu/workspace/hponas/requirements.txt:6) pins NumPy 1.24.3, BoTorch 0.9.2, and mutmut 2.4.3, while `pyproject.toml` requests mutmut ≥3 and NumPy <2, and the working runtime has NumPy 2.5.2, BoTorch 0.18.1, and mutmut 3.8.0. These are materially different environments: kernel defaults, mutation CLI behavior, and APIs such as `np.trapz` differ. Passing tests here cannot certify the declared install environment.

[CI's mutation job](/home/ubuntu/workspace/hponas/.github/workflows/ci.yml:75) uses old CLI options, swallows failure with `|| true`, and has `continue-on-error: true`; it never enforces V03's criteria. Governance checks validate document presence/structure, and their critical lint paths omit `validation/`. This lets the campaign syntax failure in A11 escape those checks.

**Closure:** make clean installation and the README example succeed in one declared supported environment; define optional extras and package discovery explicitly. Align version constraints with the actual APIs, capture the environment in campaign artifacts, and make mandatory CI gate failures fail the job.

### A11 — P1 for optional-prior certification: V11 cannot currently import

[validation/v11_campaign.py:560](/home/ubuntu/workspace/hponas/validation/v11_campaign.py:560) contains a top-level `return path`, producing **SyntaxError: 'return' outside function**. It was the sole compile failure across the 164 tracked Python files. Statistical helpers, task definitions and pilot work exist, but the present campaign module is not executable. `manifest_digest` also remains optional and the run is not wired to enforce manifest verification. [Signature verification](/home/ubuntu/workspace/hponas/tools/verify_manifest.py:223) only warns that cryptographic verification is unimplemented.

**Closure:** restore a runnable campaign, connect the required manifest checks and result provenance, and execute the registered confirmatory design before certifying prior-method performance. V11 is opt-in/non-blocking for the immediate Tier 0 release; its syntax failure is still a repository health and later certification gap.

## 4. Gate-by-gate evidence against the goal

“Not established” means the current implementation/artifacts do not prove the stated claim. It is not a substituted statistical FAIL for an experiment that was never run.

| Gate | Audit status | Gap to the stated claim |
|---|---|---|
| **V01** | Not established | [GP parity](/home/ubuntu/workspace/hponas/validation/v01_wrapper_parity.py:50) compares GPSearcher to another GPSearcher with the same seed, not an independent vendor reference. TPE is skipped but marked `passed=True`. This can demonstrate repeatability, not wrapper parity. |
| **V02** | Blocked implementation; real defects reproduced | [Four substantive scenarios](/home/ubuntu/workspace/hponas/validation/v02_state_replay.py:77) hardcode blocked/False; only the vacuity check returns True. Component tests do not replace GP, scheduler, crash/resume and concurrent replay campaigns. A02/A06/A07 provide counterexamples. |
| **V03** | Pass unsupported | Retained population exists and aggregate is 90.04%, but four module scores are below threshold, critical survivors are unreviewed, the reporter is broken, and no fresh HEAD campaign was run. See section 2. |
| **V04-T0** | Blocked reproducibility; protocol mismatch | [Baseline loader](/home/ubuntu/workspace/hponas/validation/v04_t0_baseline_floor.py:45) fails because `validation/baselines/rl_routine_baseline.json` is missing. Analysis uses absolute AUC difference and p<0.05; markdown specifies relative improvement and corrected p<0.025. `np.trapz` also does not exist in installed NumPy. The protocol both permits a proxy and labels proxy-only evidence inconclusive. |
| **V05** | Definition unresolved; pass unsupported | [Script](/home/ubuntu/workspace/hponas/validation/v05_log_warping.py:38) measures log sampling on a designed synthetic objective with unseeded global noise. The [markdown protocol](/home/ubuntu/workspace/hponas/validation/protocols/v05_protocol.md:34) requires real Brax random-vs-pathological comparison, while the JSON register describes log-warping and gate text calls it Hyperband. These are different claims. |
| **V14** | Mock composition evidence only | Default fast example does not train a policy, search architecture, update a searcher from results, or save a real checkpoint. Current checks cannot establish real-workload reproduction or protected-metric isolation (A09). |
| **V16** | Enforcement inadequate | Synthetic zero-work PASS accepted; source-string checks substitute for campaign execution; multiple runners disagree about required gates (A01). |
| **V04-T1** | Definition/campaign reconciliation needed | Historic real-workload Sobol-vs-Random code and results exist, while build-program text also uses V04-T1 for TuRBO decisions. No consistent current campaign was certified in this audit. |
| **V06** | Currently unimportable; statistical/cost claim unsupported | [Script](/home/ubuntu/workspace/hponas/validation/v06_asha_efficiency.py:35) imports missing public exports. It labels fidelity sums accelerator-seconds, excludes full-fidelity reevaluation cost, and treats a nonsignificant Mann–Whitney test as equivalence. The protocol calls for an equivalence design, not failure to reject a difference. |
| **V09** | Superiority claim unsupported | [Chebyshev comparator](/home/ubuntu/workspace/hponas/validation/v09_qlogNEHVI_vs_scalarization.py:230) uses a random base searcher, so scalarized observations do not guide proposals. The endpoint is final HV after equal trial counts, while cost curves end at each method's different spend; it does not establish common-compute superiority. Raw paired tests also do not implement the declared family analysis. Algorithm defects below further undermine the comparison. |
| **V10** | Explicitly blocked | [Rung-correlation campaign](/home/ubuntu/workspace/hponas/validation/v10_rung_correlation.py:118) returns BLOCKED for missing multi-fidelity workload infrastructure. |
| **V11** | Unexecutable current campaign | Syntax failure and incomplete manifest enforcement; pilot results are not a substitute for confirmatory execution (A11). |
| **V12/V13** | Identity drift; implementation/campaign gap | JSON defines V12 warm-start and V13 sampler; other documents/validators use V12 mixed-space TuRBO and V13 warm-start. The [warm-start campaign](/home/ubuntu/workspace/hponas/validation/v13_warmstart_effectiveness.py:94) remains BLOCKED even though store-based warm-start code exists. |
| **V07/V08/V15 and distributed acceptance** | Later roadmap work, not certified | Protocols/validator scaffolding exist, but the corresponding full algorithms/campaigns and production hardening are not established. They should not be silently represented as present-day passes or added wholesale to the immediate Tier 0 scope. |

The “master authority” itself claims [V03 passed](/home/ubuntu/workspace/hponas/CONSOLIDATED_MASTER_AUTHORITY.md:31), later retains older V03-in-progress language, and claims V02/V04/V05/V14 passes that do not match executable evidence. `validation/protocols.json` is still **DRAFT**. `tools/check_program_sync.py` and `tools/check_protocols.py --quiet` both passed during this audit despite the semantic drift.

Only four historic JSON summaries under `results/` are tracked. `validation/results/*.json` and the mutation cache are ignored. Ignoring generated data is reasonable if there is an external immutable artifact store, but no authoritative, hash-bound V03 artifact was available here. The local ignored V09 result file is truncated invalid JSON; this is distinct from the tracked historic `results/v09_qlogNEHVI_vs_scalarization.json` and does not imply that the tracked file is corrupt.

**Closure for the table:** assign one stable ID, claim, endpoint, comparator, gate, and artifact schema to each validation. Reconcile the authorities before freezing the next campaign. Generate status from verified results; documentation assertions and old timestamps are insufficient.

## 5. Additional Tier 1 and workload gaps

These findings matter to the whole program, but should not all be treated as reasons to expand the immediate Tier 0 mutation campaign.

| Finding | Evidence and impact | Acceptance needed |
|---|---|---|
| **T01: qLogNEHVI direction is wrong for the advertised minimization API** | [Search implementation](/home/ubuntu/workspace/hponas/hponas/searchers_mo.py:163) sends raw minimized outcomes and a positive anti-ideal reference into BoTorch's maximizing acquisition, with no objective/sign conversion. A bounded probe intercepted the actual call and confirmed those inputs. | Consistent objective directions and reference transformation across fitting, acquisition, Pareto reporting and baselines; compare a small known front to independent BoTorch behavior. |
| **T02: batched cost penalty multiplies costs** | [CostAwareAcquisition](/home/ubuntu/workspace/hponas/hponas/searchers_cost.py:241) sums log costs where its contract says to sum costs. A q=2 probe with costs 2 and 3 penalized **6**, rather than **5**. The existing q=1 log-acquisition correction is present and does not fix this batch case. | Apply the declared sum-of-costs model, including nonunit temperature and batch shapes, and validate decisions at equal measured compute. |
| **T03: MO-ASHA does not rank by exclusive hypervolume contribution** | [Ranking](/home/ubuntu/workspace/hponas/hponas/schedulers.py:573) uses each point's rectangular dominated volume and silently adapts the reference instead of honoring the configured one. With front `[(0,8),(4,4),(5,3),(8,0)]` and reference `(10,10)`, helper scores are `[20,36,35,20]`; true exclusive contributions are `[8,4,3,6]`. Promotion ordering differs. | Implement the declared exclusive-contribution rule or explicitly preregister a different heuristic and validate it; honor reference semantics. |
| **T04: multi-objective RNG state does not resume** | [qLogNEHVI state](/home/ubuntu/workspace/hponas/hponas/searchers_mo.py:277) and [NSGA-II state](/home/ubuntu/workspace/hponas/hponas/searchers_mo.py:832) reseed rather than restore RNG position. Both replayed their first proposal, `0.374540`, instead of the expected next `0.950714`. | Full RNG/sampler/model state and uninterrupted-vs-resumed proposal equivalence, including the model-based/evolutionary phases. |
| **T05: scalarization and TPE contracts do not align** | [Chebyshev](/home/ubuntu/workspace/hponas/hponas/searchers_mo.py:380) labels its scalar as minimized distance to an anti-ideal point, while GP and TPE bases have different direction conventions. The reference moves after observations, leaving old scalar labels on different scales. Its random variant cannot learn from weights. [TPE](/home/ubuntu/workspace/hponas/hponas/searchers_tpe.py:107) calls nonexistent `knob.choices` for categorical dimensions; the probe raised AttributeError. | One explicit scalar objective convention/reference policy, consistent stored labels, a comparator whose proposals depend on observations, and categorical support through the canonical schema. |
| **T06: sampler diagnostics can certify a stuck sampler** | [compute_ess](/home/ubuntu/workspace/hponas/workloads/sampler_neutra.py:125) estimates from between/within-chain variance without autocorrelation. Four constant 100-sample chains returned **ESS=400, R-hat=1**; strongly correlated chains also received approximately full ESS. The workload implements ordinary HMC without the learned transport advertised by “NeuTra.” | Trusted autocorrelation-aware ESS and robust convergence checks with degenerate-chain handling, reference agreement, and either a real neural transport or an accurately scoped HMC workload. |

The Hamiltonian workload contains real Torch training and the reporting module has actual Pareto/hypervolume machinery. This audit did not independently establish their full held-out performance or calibrate their resource measurements.

## 6. What is present, and what is legitimately deferred

Useful completed work includes continuous-space GP execution, Random/Sobol components with state support, local execution, working local Ray execution, SQLite WAL storage, events, numerous contract checks, guarded priors, additive prior weighting in log acquisition space, and ranked store-based warm-start seeding. The current prior guard and log-space corrections are implemented; older documents that say they are absent should not drive remediation. The warm-start file's introductory claim that it immediately builds RGPE is also stale relative to its implementation.

Tier 2 TuRBO/mixed-space TuRBO and BG-PBT, along with the optional ifBO path, do not have complete implementations/campaigns in the inspected library. Persistent multi-user service integration, monitoring/alerts, backup/restore drills, strict compute-budget enforcement, and full multi-node scale/fault campaigns remain distributed-hardening work. A standalone SQLite implementation or a synthetic scale test is not evidence for that later operational milestone.

General NAS remains outside the approved scope. Its absence is not a gap against this program.

## 7. Repair order and completion criteria

1. **Restore evidence integrity.** Reconcile protocol IDs/claims and required gates; fix V03 accounting, remove hardcoded passes, and make gates recompute results from complete artifacts. Preserve source/test/environment hashes and distinguish BLOCKED, FAIL and INCONCLUSIVE.
2. **Make the advertised installation and API usable.** Resolve packaging and dependency constraints, choose the canonical space/result/searcher contracts, and execute a maintained public example that includes architectural dimensions.
3. **Fix optimization and lifecycle correctness.** Address objective signs, mixed/conditional encoding, observation identity, Study resume, complete scheduler state, replay, and execution controls. Verify actual public workflows beyond each searcher's random warmup.
4. **Establish the real workload evidence.** Implement effective architecture knobs, durable artifacts, protected acceptance metrics, independent vendor parity, and executable V02/V04/V05/V14 protocols under the reconciled definitions.
5. **Re-run the declared Tier 0 mutation and validation campaigns.** Target the affected behaviors with meaningful tests, review the existing survivors, and apply module/critical-path requirements. A high aggregate score or test count does not replace those criteria.
6. **Complete Tier 1 mathematics and comparisons, then later tiers.** Repair multi-objective directions, HV contribution, batched cost and state restoration before relying on V06/V09. Certify optional priors/sampler/warm-start separately, then execute the deferred distributed acceptance plan.

Each step has a concrete reviewable outcome. None requires lowering the mutation bar or resetting the repository on the strength of the R10 memo.

## 8. Verification and evidence

Runtime: `/home/ubuntu/miniforge3/bin/python`, Python **3.13.13**; NumPy **2.5.2**, Torch **2.13.0**, BoTorch **0.18.1**, GPyTorch **1.15.2**, Ray **2.58.0**, JAX **0.11.1**, Brax **0.14.2**, pytest **9.1.1**, mutmut **3.8.0**. The default shell Python is a different environment and lacked required audit dependencies. Full versions and raw probe results are in [audit-evidence.json](/home/ubuntu/workspace/hponas/docs/audits/evidence/2026-09-25/audit-evidence.json).

| Check | Observed result |
|---|---|
| Test collection | 882 tests |
| Unit + conformance, excluding the dedicated Tier 0 Ray test file | 475 passed, 16 skipped |
| Integration + recovery | 36 passed, 1 skipped |
| Remaining non-slow selection, excluding scale and dedicated Ray files | 305 passed, 1 skipped, 7 deselected; three Ray startup failures inside sandbox |
| Those three Ray cases, outside sandbox on a bounded two-CPU local cluster | 3 passed |
| Unique passing tests across these selections | **819** |
| Other test coverage limits | 18 selected skips, 7 slow deselections, 38 other excluded tests; this was not the complete 882-test suite |
| Compile all tracked Python sources | 163 compiled; V11 failed at line 560 |
| Critical Ruff checks | V11 syntax/undefined-name errors, plus unresolved `ray`/`Any` annotations |
| Packaging metadata generation | Failed flat-layout package discovery |
| Program/protocol structural checks | Both passed despite the semantic discrepancies identified above |
| Bounded behavioral probes | Reproduced the defects reported above; qLogNEHVI input probe intercepted model/acquisition calls rather than running a performance campaign |
| Mutation evidence | CLI/cache inventory only; **no full mutation rerun** |

The tests establish a useful foundation, but some current checks permit weaker behavior than their stated contracts. For example, [duplicate-observation conformance](/home/ubuntu/workspace/hponas/tests/conformance/test_searcher_contract.py:403) allows either deduplication or duplication despite “last wins,” and the [no-duplicate-resume check](/home/ubuntu/workspace/hponas/tests/conformance/test_checkpoint_resume.py:181) only verifies restored history length. This explains how the passing suite can coexist with the concrete counterexamples.

The [evidence directory](/home/ubuntu/workspace/hponas/docs/audits/evidence/2026-09-25/README.md) preserves the probe code, observed results, selected test output, package failure, environment, and all 2,287 retained mutant statuses. Real GPU training, a clean dependency-resolved installation, full mutation execution, scale tests, and multi-node fault injection remain unverified by this audit.
