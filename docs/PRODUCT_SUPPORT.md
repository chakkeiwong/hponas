# Product support and evidence

The product is a reusable HPO and moderate coordinate NAS workflow for
universal-bank model families. The core accepts caller-owned data/model
adapters; the implemented bank examples use independent synthetic generators and
mathematical references. The [16 October product package](program/evidence/2026-10-16/bank-final-qualification-08/accepted-package.json)
is the qualified finite local baseline. The master is now incomplete:
[GAP-01](program/GAP_CLOSURE_PROGRAM_2026_10_18.md) repairs ten historical gaps,
with current-source qualification and an independent completion audit last.

The 12 October baseline remains attached to its original source. The
16 October product package binds fresh applicable scientific gates, finite bank
references and configured workflows, installed use and live local evidence. The [semantic trace](program/evidence/2026-10-16/bank-final-qualification-08/coverage-qualified.json)
maps the previously inventoried interface groups, product rows, build components,
approval items and deferred methods. The [atomic gap ledger](program/gap_closure.json)
adds the missing subclauses and distinguishes implementation from dispositions.
The original survey remains design history. The repair and banking contracts
record the adopted interpretations; this page gives current usage guidance.

| Interface | Current behavior and boundary | Reference |
|---|---|---|
| Declaration/evaluation | Require a declaration or an explicit persisted legacy reason. Aggregate complete fold/seed cohorts at declared streaming barriers; freeze scalar winner or feasible front before disjoint final evaluation. | [Evaluation](EVALUATION.md) |
| Budgets/capabilities | Validate method kinds, conditionals, fidelity, vectors and architecture axes before dispatch. Reserve tuning/final work independently and retain failed/lost work. Endpoint time caps can overshoot by the last call. | [Budgets](BUDGETS.md) |
| GP proposals | Real joint qLogEI; pending locations share posterior samples. Finite unordered sets are bounded at 4096; batches at eight. Mixed/unbounded discrete joint optimization is refused. | [GP batching](GP_BATCH.md) |
| Diagnostics | Per-rung midrank correlation with observed completed full-fidelity tuning pairs, counts and censoring reasons. Protected final data is excluded. No automatic pruning-safety claim. | [Diagnostics](DIAGNOSTICS.md) |
| Reports/artifacts | Full scalar/vector history, curves, lineage, constraints, observed-cost/work trajectories and role-labelled artifacts; tuning/final mean, sample spread and repetition counts come from raw records. Failed/incomplete repetitions cannot become a reduced successful mean. Strict JSON exports refuse overwrite. Reports are distinct from restart checkpoints. | [Reports/adapters](REPORTS_AND_ADAPTERS.md) |
| Local execution | Local and Ray Core endpoint/streaming paths, cooperative stop/pause, checkpoint restart/resume and replay. Declared Ray budgets require no hidden executor retries. Legacy Tune compatibility is separate. | [Reports/adapters](REPORTS_AND_ADAPTERS.md) |
| Persistence/operations | SQLite and PostgreSQL atomic checkpoints/projections, report queries, every committed tuning/final artifact and full backup. The local managed service adds versioned migration/rollback, incremental event replay, scheduled local backup/alerts, application roles and declared device/currency quotas. | [Operations](OPERATIONS.md), [PostgreSQL](POSTGRES.md) |
| Population/NAS | Retained local PBT/PB2-Mix/BG-PBT plus a model/optimizer-neutral local population adapter with repeated protected evaluation, saved schedules and charged transfer. Architecture coordinates build different models; compatibility gates checkpoint copies. | [Examples](../examples/README.md), [NAS scope](../NAS_SCOPE_DECISION.md) |

Searcher support is inspectable through its `support`/`capabilities` contract.
Random/Sobol support mixed and conditional coordinates and partial observations;
TPE supports ASHA when `model_fidelity` equals the full scheduler endpoint,
retaining low rungs while fitting Optuna only on complete endpoint measurements.
Scalar GP/CMA-ES refuse scheduled partial-fidelity Study use. Trust/cost/
robust GP retain sequential constraints, and robust GP refuses the declared
workflow because it lacks the required failed-observation support. Vector
methods require their explicit ObjectiveSpec. Priors use a declared law;
Knob.prior text is not silently made into a sampling distribution.

| Method/interface | Scheduler composition | Declared repeated evaluation |
|---|---|---|
| Random/Sobol | Scalar ASHA/PASHA | Endpoint or declared streaming barriers |
| Optuna TPE | Scalar ASHA; model fidelity must equal configured maximum | Endpoint or declared streaming barriers; root identity binds duplicate asks |
| Scalar GP/CMA-ES | Refused | Endpoint; streaming barriers without a scheduler |
| Vector random, qLogNEHVI/Chebyshev, NSGA-II | Matching `MultiObjectiveScheduler`; Bayesian model fidelity equals maximum | Named vector endpoint or barrier reports; constraints checked for every repetition |
| PriorBand variants | Matching prior scheduler required | Retain their explicit prior law and sampler restrictions |
| Trust/cost wrappers | Refuse external scheduling; sequential proposals | Retain wrapper-specific controls |
| Robust GP | Refuses scheduler and concurrency | Refused because failed-repetition handling is unsupported |
| RGPE | Refuses scheduler and concurrency | Scalar endpoint with matching declared source/target protocols and protected final roles |

These are development-verified interfaces. GAP-01 scientific requalification
remains open. TPE checkpoints use identity-bound version 3; version 2 replay
requires the retained source or an explicit migration. Direct dictionary TPE
observations must name `trial_number` when equal configurations are pending.

Finite optional-method evidence remains opt-in. DEHB and population controllers
are implemented; the old word “deferred” is not their current implementation
status. The bounded fixed-kernel RGPE searcher now supplies ranked initialization
and actual surrogate transfer with development evidence; see
[warm starts](WARM_START.md). ifBO feasibility failed and integration was
cancelled. [Method outcomes](METHOD_OUTCOMES.md) enumerates each implemented,
failed/cancelled and watchlist method separately. A cost predictor does not
implement CARBS. The trainable small coupling fixture does not establish general
posterior calibration. No empirical optimizer superiority or automatic default
promotion follows from these finite examples.

Operational scope is trusted supervised local research. The new local service
has development evidence for committed-prefix PITR, incremental/scheduled backup,
local alerts, application roles, caller-provided backup keys and authenticated
encrypted event artifacts, plus cooperative measured device-time/currency quotas.
Final source qualification remains open. Live databases remain plaintext;
authentication, external secret vaults, external alert delivery and hostile
tenant isolation are separate integrations. The bounded eight-study/four-local-
worker measurement does not qualify the original 100-study/50-distributed-worker
or production throughput/p99 targets. Separate-machine testing is waived, not
passed. Local role/TLS tests do not establish remote fault tolerance or
production banking readiness.

The [bank profiles](BANK_PROFILES.md) now implement the following finite local
workflows. Each has independent reference checks, adverse cases, public
selection/evaluation, resume and reporting tests. Their 16 October baseline
source passed BANK-01/INTEGRATED-REVIEW. The changed GAP-01 source still requires
BANK-01/GAP-QUALIFICATION and the last-phase complete audit.

| Model family | Implemented finite support | Explicit limit |
|---|---|---|
| Prediction | Ridge, Bernoulli and right-censored geometric hazard; fold-local preprocessing and held-out scoring | Synthetic finite targets; no real-bank accuracy claim |
| Forecasting | AR folds with chronological order, information gap and available features | No general forecasting or nonstationarity guarantee |
| Causal/policy | Cross-fitted finite structural example; identified effect or conservative bounds | Predictive fit cannot establish overlap or identification |
| Inference | Linear-Gaussian filtering; native numerical candidate verification and fresh handoff; affine density correction | All verified pairs retained; posterior R-hat/ESS/MCSE never rank candidates and posterior convergence remains unassessed |
| Constrained solvers | Constructed neural ODE solution with independent value, derivative and boundary constraints | Small normalized training loss cannot override failed task feasibility |
| Valuation/wallet | Signed discounted cashflows, censor-aware hazard and latent-tail bounds | Unidentified point values refused; synthetic units only |
| Allocation | Exact two-asset constrained QP with tuned statistical mean shrinkage and interval uncertainty | Exact optimization remains the solver; no empirical return claim |
| Coordinate NAS | Prediction and solver networks with changed arrays/computation, size/work meters, artifact reload and compatible transfer | Moderate architecture coordinates; no arbitrary topology, device latency or energy claim |

The bank workflow uses deterministic fitting with an explicit seed opt-out and
disjoint tuning/final roles. Its 32-proposal ceiling does not promise complete
enumeration or a feasible winner. Empty fronts, failed trials, uncertain work
and unsupported identification remain visible. Separate final work is reserved.
Core adapters remain caller-owned and require no sibling imports, services or
private data. Python 3.12/3.13 installation evidence is bound to its tested
source. GAP-01 refreshes installed-workflow evidence before its own qualification.
The wheel ships [two independent caller models](CALLER_MODELS.md) through
`python -m hponas.quickstart`: fitted ReLU readout coordinate NAS and a tuned
projected-gradient allocation solver. Their exact finite references and
deterministic repetitions demonstrate public contracts; they do not establish
empirical usefulness or stochastic precision.

At every phase boundary, retain failures, repair demonstrated defects and
refresh affected evidence and the next bounded plan. The trace guard detects
omitted rows, broken bindings and missing owners. Its success proves recorded
consistency only; mathematical checks, behavioral tests and scientific gates
retain their separate meanings.
