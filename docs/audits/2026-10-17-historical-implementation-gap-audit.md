# Historical implementation and completion audit

Reviewed 17 October 2026 (Asia/Shanghai). This audit supplements, and does not
replace, `CONSOLIDATED_MASTER_AUTHORITY.md` and `docs/program/program.json`.

## Verdict

**We have not implemented every capability promised across the historical
programs.** We have implemented and qualified a substantial HPO/coordinate-NAS
library and independent banking-family examples within a finite, supervised
local research scope. Completion of that adopted scope includes implemented
features, explicit limitations, exclusions, deferred research and a failed
research bet. Those outcomes must not all be called implementation completion.

Revision 2.397 records 37 completed work items, 196 completed continuation
stages and 113 requirement dispositions: 79 required, three optional, 21
deferred and ten excluded. Its active work item is null. These are register
facts, not proof that every original sentence was delivered. In particular,
the public multi-objective joint-batch promise has no specific closure or
amendment in the lineage and final trace entries inspected below.

The accepted package remains valid for its stated tested envelope. This audit
does not overturn its numerical results. It does challenge using that package
or the closed register to imply complete delivery of the broader original
product.

## Basis and limits

- Repository commit: `d766dd513d3a8c87323e547b7fa7f750ae2faaae`.
- Master/register revision: `2.397`.
- Qualified source: `de68ddcd7998344333c3349b0d36accf5096f618c81ab12ce6a314bd7c0a6b2c`.
- Final evidence: `docs/program/evidence/2026-10-16/bank-final-qualification-08/accepted-package.json` and `coverage-qualified.json`.
- The working tree was clean before this audit. Only audit documentation is
  added; scientific code, the register and accepted evidence are unchanged.
- Review used the existing historical inventory, original contract/build
  sources, successor scope decisions, current public code, retained tests and
  final evidence. The 12 October inventory covers 356 archived register
  snapshots and 337 revision labels. This audit does not claim an independent
  reread of every snapshot.
- No new functional acceptance, performance campaign or mutation run was
  performed. Explicit source refusals, capability declarations and call paths
  establish the integration limits below. This is not an exhaustive proof of
  absence of bugs.

The companion `2026-10-17-historical-implementation-gap-sources.json` records
hashes of key inspected sources and implementation anchors.

## Program lineage

| Program / transition | Intended outcome | What completion establishes |
|---|---|---|
| Survey chapters 11, 14, 15 and 12 | Reusable study workflow, methods, evaluation, storage, architecture and roadmap | Original obligations; some later narrowed or omitted from early registers |
| Rejected v1, review verdict, v2 | Correct the build and execute foundations, methods, populations and operations | Specification and implementation lineage, not final product certification |
| Recovery master and recovery status | Reconcile specifications, spikes, validation and v3 | Recovery readiness; its post-approval section explicitly leaves build execution outside recovery |
| Original v3 | Tier 0, Tier 1, Tier 2 and distributed beta | Seven, nine, five and six component groups; individual promises exceed current support |
| Tier-0 master and V03 reset/repair | Core correctness and mutation qualification | Engineering milestones; mutation is one gate, never the whole tool |
| October 4/5 whole-program refresh | Restore later tiers, dependencies, resources and continuation | Re-established broader execution after mutation dominated status |
| Known-answer/local amendments | Independent small models, objective answers, bounded compute, no separate-machine test | Changes to validation and claims; no automatic waiver of unrelated APIs |
| Revisions 2.249–2.250 | Qualify and close 35 items / 177 stages | Finite baseline qualified; the next review found omitted product contracts |
| Revision 2.251 / PRD-01 | Recover declarations, seed/final workflow, budgets, batching, diagnostics and traceability | Substantial interface repairs delivered; remaining limits below |
| Revision 2.252 onward / BANK-01 | Independent configured bank-family workflows | Prediction, causal, inference, solver, decision and coordinate-NAS examples implemented and qualified |
| Revision 2.397 | Final finite local package and publication reconciliation | Adopted stages closed; not every historical feature or application/deployment claim delivered |

Primary references: `docs/program/MASTER_PROGRAM_LINEAGE_REVIEW_2026_10_12.md`,
`docs/program/evidence/2026-10-12/master-lineage-review-01/trace.json`,
`archive/program-2026-09-28/BUILD_PROGRAM_v3.md`,
`HPO_NAS_RECOVERY_MASTER_PROGRAM.md`, and the current consolidated authority.

## Delivered capabilities

The implementation is substantially broader than mutation repair. It includes
declared scalar/vector studies; persisted model/data/objective/protocol
identities; tuning and protected final evaluation; capability and budget
checks; durable checkpoints, recovery and reporting; Local and local Ray Core
execution; SQLite/PostgreSQL; scalar joint qLogEI; multi-objective search and
constraints; scheduler and cost/prior/trust methods within declared envelopes;
ranked warm starts; finite DEHB and population controllers; real architecture
builders and checkpoint compatibility; and independent banking-family workflows.

The bank examples cover ridge/Bernoulli/censored prediction, chronological
forecasting, structural causal analysis, linear-Gaussian inference and native
tuner handoff, constrained neural solving, valuation/censoring/bounds, exact
two-asset allocation with tuned statistical inputs, and coordinate NAS in
prediction and solver profiles. Their synthetic generators and mathematical
references do not depend on sibling repositories, as the user requested.

## Remaining gaps

### G01 — Public multi-objective joint batching

**Demonstrated integration gap; specific historical subclause closure not found.**
Original v3 requires qLogNEHVI batch acquisition with `q > 1`
(`archive/program-2026-09-28/BUILD_PROGRAM_v3.md:549–559`). The maintained
`MultiObjectiveBayesSearcher` has only `suggest()`, inherits `joint_batch=False`,
and calls `optimize_acqf_discrete(..., q=1, ...)`
(`hponas/searchers/multi_objective.py:65–157`). Pending points are represented;
that does not establish the promised joint-batch interface.

Legacy `hponas/searchers_mo.py:131–214` does have `propose(n)` and `q=n`, but is
explicitly marked old code. The scalar legacy adapter rejects vector objectives
(`hponas/searchers/adapter.py:10–15`). The gap is maintained public Study
integration and its evidence, not absence of all q>1 algorithm code.

PRD-BATCH repaired scalar qLogEI. The final trace maps the broad original
qLogNEHVI group to finite V09 and C01–C33 without a specific q>1 implementation
or amendment in that entry. A group-level PASS does not close this subclause.

**Owners:** T1-MO; PRD-01/GP-BATCH-PENDING; PRD-01/DOCUMENTATION-TRACEABILITY.
Completion requires a vector batch API, pending/recovery and duplicate policy,
and an independently enumerated small joint-acquisition test, or a specific
prospective scope disposition. Sequential calls must not be relabelled joint.

### G02 — Protected repeated evaluation cannot use streaming objectives

**Documented supported-envelope limitation; remaining original workflow capability.**
The original day-one walk combines a searcher, ASHA and a default seed/final
evaluation protocol (`hpo-survey/sections/14-product.tex:85–110`). Current
`EvaluationController` refuses objectives accepting `reporter`
(`hponas/evaluation.py:229–241`). `docs/EVALUATION.md:69–79` explicitly says
repeated-stream orchestration is pending. Streaming exists separately.

Endpoint repeated evaluation, including fidelity promotions and per-repetition
restart/resume checkpoints, is implemented. The missing combination is live
reports, fold/seed aggregation, scheduling and protected final evaluation.

**Owners:** PRD-01/STUDY-SEED-WORKFLOW and ADAPTER-WORKLOAD-CLOSURE. A small
completion test can cover two repetitions with unequal report times, a failed
repetition, promotion/pause, crash recovery, exact aggregation and no final
evaluation feedback into search.

### G03 — The primary API does not require an explicit evaluation opt-out

**Historical contract narrowing/default-interface gap; results are honestly labelled.**
The original declaration is mandatory and the seed protocol is the default
(`hpo-survey/sections/15-contracts.tex:25–41`). Current `Study.__init__` accepts
`declaration=None` and `maximize=True` (`hponas/study.py:75–90`). Omission enters
the legacy path and reports `legacy_unqualified`; no explicit compatibility
flag or written reason is required. Declared deterministic fixtures do have
an explicit `opt_out_reason`.

PRD deliberately retained compatibility. Nevertheless, the ordinary entry
point does not enforce the original default scientific workflow.

**Owners:** PRD-01/STUDY-SEED-WORKFLOW; PRD-DECL/PRD-SEEDS. Reconcile the default:
require a declaration for ordinary studies, with a named compatibility path
and persisted opt-out reason; preserve old checkpoints through a versioned policy.

### G04 — Searcher/scheduler composition remains limited

**Documented capability boundaries; integration backlog.**
`hponas/capabilities.py:74–79` rejects a scheduler when the searcher lacks partial
fidelity support. Scalar GP, TPE and CMA-ES therefore refuse scheduled Study
use. The original TPE+ASHA day-one combination is unavailable through this
public route. Trust/cost methods retain sequential limits; robust GP refuses
declared evaluation because it has `failed_observations=False`
(`hponas/searchers/robust_gp_searcher.py:33–34`). Warm/cost wrappers do not
automatically inherit GP joint batching.

**Owners:** PRD-01/CAPABILITY-BUDGET-ROUTING and relevant T1 methods. Prioritize
the promised TPE+ASHA route and define which fidelity observations train each
model. Removing guards without that contract would be incorrect; arbitrary
method combinations need not be valid.

### G05 — Population methods are specialized rather than general adapters

**Real finite local implementations; broader reuse remains outside their contract.**
PBT/PB2-Mix/BG-PBT exist. Their substrate is a single-writer CPU CoordinateMLP
with bounded dimensions, float64 models and SGD learning-rate/momentum options
(`hponas/population.py:1–61`). Controllers use a specialized policy/value
objective. `hponas/bg_pbt.py:1–6` explicitly requires adapters for separate
policy/value architectures, PPO simulators and distributed workers. The
general repeated Study protocol does not automatically apply to this controller.

This is narrower than the original reusable population/RL line. Waiving a
separate-machine test does not implement arbitrary local model/optimizer
adapters or protected population evaluation.

**Owners:** T2-POP; PRD-01/ADAPTER-WORKLOAD-CLOSURE; BANK-01/PROFILE-CONTRACTS.
Broader reuse needs train/checkpoint/restore/evaluate/transfer interfaces and
two different tiny model/optimizer demonstrations. No cluster is needed to
establish that local interface.

### G06 — Original distributed-beta operations are only partially delivered

**Explicitly unqualified or unsupplied stronger capabilities.**
Original v3 promises schema migration/rollback, incremental and point-in-time
restore, automated backups, live alerts, large scale/latency targets, application
roles, secrets/encryption and GPU-hour/currency quotas
(`archive/program-2026-09-28/BUILD_PROGRAM_v3.md:1090–1307`).

Current support supplies local durability, full snapshots, cooperative
execution, role boundaries and measured accounting. `docs/OPERATIONS.md:69–72`
provides no automatic schema migration. The operational disposition table in
`docs/program/PRODUCT_REPAIR_CONTRACT_2026_10_12.md` and `docs/PRODUCT_SUPPORT.md`
explicitly retain the stronger features as unqualified integrations. Large
capacity is unverified, not disproved by a missing large test.

**Owners:** OPS-01; PRD-01/LOCAL-OPERATIONS-CLOSURE. Distinguish absent features,
unqualified capacity and waived remote testing. D-LOCAL-OPERATIONS-SCOPE quotes
a user waiver of separate-machine testing; that quotation alone is not
evidence of acceptance of every other feature deletion. The current bank
contract expressly adopts supervised local research, so production expansion
is not an immediate repair requirement within that scope.

### G07 — Research branches were deferred or cancelled

**Terminal dispositions, not all implemented features or bugs to conceal.**

- ifBO feasibility failed under its frozen rule; V15b integration was cancelled.
  A completed research disposition does not deliver the proposed integration.
- Ranked warm starts exist; RGPE surrogate transfer does not
  (`hponas/warm_start.py:1–5`). Original v3 explicitly requested RGPE after
  ranked initial queries (`archive/program-2026-09-28/BUILD_PROGRAM_v3.md:961–984`);
  the current contract moves it to an evidence-dependent watchlist.
- SAASBO, SMAC product integration, FIRE/MF-PBT/IPBT/SEARL, MORBO/HVKG, broader
  PFNs, CARBS and muP/scaling-law work remain watchlists. Historical mention
  alone does not make all of them mandatory current implementation work.
- DEHB, population methods and selected GP robustness are implemented within
  their envelopes despite historical deferred requirement labels. All 21
  deferred rows must not be counted as missing features.

**Owners:** T1-WARM, T3-01, SCOPE-01. Preserve distinct scope, implementation,
qualification and terminal-outcome fields; reopening a research bet needs
a prospective reason and plan, not a favorable rerun of failed evidence.

### G08 — Workload coverage is finite; application usefulness is unestablished

**Evidence/reuse breadth limit, consistent with the requested test design.**
The core accepts caller adapters. Supplied profiles use independent small
models, not actual bank deployment data. The maintained Hamiltonian example
is a quadratic-feature fit; learned transport is a small tanh coupling;
general HNN/posterior calibration is unestablished (`docs/WORKLOADS.md`).
Native inference handoff does not certify posterior convergence.

This does not invalidate known-answer validation or justify huge generic
benchmarks. It means all sibling project models are not already integrated
or empirically qualified. Sibling imports, data and services must remain
unnecessary. General topology/cell NAS, supernets, weight sharing and
differentiable NAS were explicitly excluded and are not accidental omissions.

**Owners:** WL-01; BANK-01/INTEGRATED-REVIEW. A small caller-adapter example
outside the fixture hierarchy can demonstrate greater reuse. Empirical
effectiveness requires a separate named-task study and is not an implicit
completion threshold or a campaign authorized by this audit.

### G09 — Completion and traceability still contain semantic drift

**Demonstrated documentation/governance gap; first priority alongside G01.**
`examples/README.md:9–13` still says PRD qualification and bank examples are
pending; its table omits `bank_tuning.py` and `bank_inference_handoff.py`. The
master is closed while its generated phase remains `tier1_development`,
explained as a historical boundary. Several requirement reasons retain
Tier-0 deferral language for methods since implemented.

The immutable final trace retains row prose saying qualification remains open
or banking work is forthcoming, despite complete top-level qualification.
Preserve those bytes and add a current interpretation. Older dated planning
documents may properly retain future tense; current usage guidance should
not present it as current status.

`tools/product_trace.py:47–79` checks known row keys, owners, paths, hashes
and open statuses. It cannot discover omitted subclauses inside broad groups.
G01 shows why another count-based completion claim is insufficient.

**Owners:** PRD-01/DOCUMENTATION-TRACEABILITY; GOV-01. Break compound original
requirements into atomic behaviors. Each needs original source, current
scope decision, implementation state, supported combinations, evidence and
owner. Record absence, refusal, cancellation and waiver separately; generate
current guidance from that view.

### G10 — Examples are not shipped with the wheel

**Documented packaging/usability limit; lower priority.**
`examples/README.md:3–7` and `pyproject.toml` make examples source-checkout
scripts. The installed library works, but the wheel alone does not provide
`python -m examples.bank_tuning`. This does not mean the installed core is broken.

**Owners:** PKG-01; BANK-01/NAS-PORTABILITY. Distribute examples/an entry point
or make the checkout requirement clear with an installed-package quick start;
verify outside the checkout.

## Repair sequence within the existing master

This is an audit recommendation, not a newly activated campaign or a second
master. No user-selected scientific success threshold, separate-machine test
or broad benchmark is required for G01–G04/G09.

1. **PRD-01/DOCUMENTATION-TRACEABILITY + GOV-01:** register atomic clauses for
   demonstrated gaps, separate implementation from dispositions, and refresh
   current guidance. Preserve the accepted baseline. This repairs master
   completeness; it does not change the product direction.
2. **T1-MO + PRD-01/GP-BATCH-PENDING:** resolve G01 with the finite vector batch
   contract/test or a specific prospective disposition. This is an inherited
   promise, not a new algorithm research program.
3. **PRD-01/STUDY-SEED-WORKFLOW + CAPABILITY-BUDGET-ROUTING:** reconcile explicit
   default/legacy semantics, then TPE+ASHA and repeated-stream evaluation with
   tiny independent examples, versioned compatibility and crash recovery.
4. **T2-POP + BANK-01/PROFILE-CONTRACTS:** if broader population reuse remains
   adopted, build local adapters and the evaluation bridge. Keep that distinct
   from the already qualified finite V08 contract.
5. **PRD-01/INTEGRATED-PRODUCT-REVIEW + BANK-01/INTEGRATED-REVIEW:** verify changed
   public combinations, installation, recovery and reporting; perform the
   source-affected qualification required by existing rules. Development
   checks do not alone requalify changed scientific source.

OPS-01 production expansion, cancelled ifBO and optional algorithms are not
silently added to this repair sequence. At each authorized phase boundary,
retain adverse results, repair demonstrated defects and refresh the next stage.

## Warranted completion statement

The adopted finite local package and bank-family examples are recorded as
qualified and complete. The broader historical promise is only partially
implemented: parts were narrowed, deferred or cancelled, and at least one
concrete public-integration subclause needs renewed closure review. This audit
is complete; it has not silently reopened or executed implementation stages.
