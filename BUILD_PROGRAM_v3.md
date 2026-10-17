# HPO-NAS build specification — reconciled reference

**Revision:** 3.5, banking vision and contract reconciliation dated 2026-10-12 (Asia/Shanghai).

**Execution authority:** [CONSOLIDATED_MASTER_AUTHORITY.md](CONSOLIDATED_MASTER_AUTHORITY.md). This reference defines capability obligations. Current status, dependencies and next actions come from the master and its structured register. The [unmodified v3.0](archive/program-2026-09-28/BUILD_PROGRAM_v3.md) is historical; its dates, effort estimates and PASS claims are superseded.

## Product goal and boundaries

Build reusable HPO and moderate architecture-coordinate NAS for a universal retail bank: prediction/forecasting, causal and policy analysis, financial inference, constrained neural solvers, valuation and allocation. The [bank product contract](docs/program/BANK_HPO_NAS_PRODUCT_CONTRACT.md) defines the supported families, evaluation rules and independent known-answer examples. Approximately 2–10 coordinates describe the initial qualified envelope; larger spaces require explicit method capabilities and verification. Preserve the general-NAS exclusions in [NAS_SCOPE_DECISION.md](NAS_SCOPE_DECISION.md). The product composes search, scheduling, local/Ray execution, declared evaluation, persistent identity, selection, final reporting and recovery without sibling-project dependencies. Universal reuse does not promise universal optimality or production deployment.

## Requirements and tier obligations

| Stage | Capability obligations | Acceptance and limitations |
|---|---|---|
| Tier 0 foundation | Canonical mixed/conditional/log/logit spaces; Random/Sobol; GP+qLogEI; TPE adapter; local/Ray execution; study ledger, events, atomic checkpoints, resume; real RL vertical slice | Current executable campaigns: V01, V02, V03, V04-T0, V05, V14, each audited by V16. The exact finite local baseline is qualified; PRD-01 retains omitted general product contracts. |
| Tier 0 specification closure | Dimension-scaled GP priors, CMA-ES's low-priority disposition, ASHA/median and faithful PASHA, full workload/template contract | These requirements appear in the governing survey but were missing or misdescribed in the previous execution plan. They have explicit work/decision records; a passing narrow campaign cannot waive them. |
| Tier 1 core | Multi-objective search and study output, qLogNEHVI, Chebyshev fallback, wrapped NSGA-II, MO-ASHA/vetoes, hypervolume reporting; predictive/censored cost model and cooling; ranked/quantile warm starts | Preserve the survey/register's V04-T1, V06, V09, V10, V11a/b and V13 obligations, with V12 dependent on a sufficiently populated store. Current finite qualification is retained in final-qualification-11; broader comparative claims are unestablished. |
| Optional priors | Faithful prior-weighted acquisition, guarded support and decay, PriorBand sampling portfolio | Finite V11a/b accepted, opt-in only. Historical failures remain retained; broader effectiveness is unestablished. |
| Population line | Mixed-space trust regions; PBT/PB2-Mix; faithful BG-PBT with restarts, checkpoint/architecture compatibility and distillation hooks | Finite local V08 is qualified; no population superiority or distributed-scaling claim. Correct owner/mappings are retained. |
| Distributed beta | Durable multi-user service state, schema migration, backup/restore, monitoring, access control, scale/fault tests, global hard budgets | D-LOCAL-OPERATIONS-SCOPE qualifies trusted supervised local PostgreSQL/Ray. Separate-machine testing is waived. PRD-01 reconciles stronger historical operational subclauses; broad multi-node/unattended service readiness is unqualified. |
| Selective later work | DEHB through owned interfaces; pretrained ifBO feasibility before integration; selective GP robustness | Native DEHB finite V07 and selective robust-GP evidence retained. ifBO V15a failed; V15b integration cancelled. |
| Banking product profiles | PRD-01 study/capability/budget/batch/diagnostic repair, followed by BANK-01 prediction, causal, inference, constrained-solver, valuation/allocation and cross-profile NAS workflows | Planned implementation and finite end-to-end qualification; the accepted engine baseline does not establish these profiles or bank application performance. |
| Workloads | Routine RL, large-parallel RL, Hamiltonian networks, sampler correctness, moderate architecture coordinates; explicit finance disposition | D-WORKLOAD-FINITE supports small known-answer finance, Hamiltonian, Gaussian and learned-tanh-transform models. Generalization/calibration is unaccepted; PRD-01 closes the general configured-study workflow. |

## Contract and correctness obligations

- Searcher direction, kernels and priors must be explicit. Mixed-coordinate encoding must preserve legal configurations, transformations and conditional activation.
- Trial identity binds configurations, results, costs, events and artifacts. Duplicate observation policy is explicit. Resume cannot redispatch committed work; pending external side effects require objective idempotency.
- Checkpoint schema, scheduler state, concurrency width and observation order belong to the replay contract. Exact replay is not replaced by a numerical tolerance to hide a defect.
- Executors bound submissions and deadlines, distinguish objective failures from infrastructure retries, and account for retry cost. An external runtime may not silently retry outside the ledger.
- Multi-objective directions, reference points, exclusive hypervolume contributions and scalarization must agree. Scalar Study does not establish end-to-end multi-objective orchestration.
- Protected evaluation is separated from search feedback. Model knobs change the actual trained model and produce reloadable artifacts.
- Packaging and maintained examples must run outside the source checkout. Existing-environment wheel verification is not a dependency-resolved clean-environment certification.

## Acceptance ownership

The structured program binds **every exact protocol ID** to its register entry hash and individual protocol. Split entries V04-T0/T1, V11a/b and V15a/b cannot be collapsed into an aggregate token. Adopted finite phase identities and results are bound. New contract repairs require their own appropriate verification; broader unadopted claims remain outside acceptance. Neither this reference nor a generator may change thresholds to make observed results pass.

V03 retains its 90% overall and per-module requirement, critical-survivor veto, reviewed-equivalence rules and timeout/abnormal-outcome rules in the protocol. Uncovered mutants remain in its denominator. Full campaign inputs must be frozen; focused mutation diagnostics are not full gate evidence.

V04-T0/V05 v4 require finite conformance on self-contained models with known tuning answers. V04-T0 covers eight fixed ridge/quadratic/filter/bottleneck cases, four methods, two seeds and sixteen proposals (1,024 trials). V05 covers two ridge cases, two GP coordinate arms, two seeds and sixteen proposals (128 trials), with identical physical initialization. Independent analytic and intermediate-output oracles check numerical results; method/seed replay, coordinate formulas, best-result selection, work and timing records complete the finite contract. Search regret is reported in each fixture's units without a superiority threshold. PASS establishes finite correctness and does not promote method or transform defaults.

This prospective amendment under D-SELF-CONTAINED-VALIDATION retires the former PPO superiority claim and its pilot, power, sizing and allocation obligations for these two entries. Historical evidence remains unchanged. No stochastic population inference is claimed for the fixed exposed fixtures; alpha/power apply to later comparison claims where appropriate. Known-answer acceptance does not waive the remaining workload templates, actual architecture effects, installed environments or current mutation requirement. V01 retains its separate adopted finite-corpus contract.

V01 requires exact observable trace agreement and complete evidence for the prospectively frozen finite corpus and explicitly named references; neither KS nonrejection nor TOST certifies it. Original missing cells and their v1 INCONCLUSIVE result remain retained. D-V01-COVERAGE-SCOPE adopts the v2 finite corpus: 36 complete trajectories and nine exact original-missing-cell refusals, with all 187 eligible seed-0 HalfCheetah configurations included. This is an explicit geometry change with no distributional equivalence claim. Later finite claims have adopted phase-specific contracts; any broader claim must be reconciled prospectively before campaign execution. V16 verifies an outcome; an audited FAIL or INCONCLUSIVE outcome keeps the program gate closed.

## Work breakdown, resources and release

[The master](CONSOLIDATED_MASTER_AUTHORITY.md) and [work register](docs/program/program.json) replace the inconsistent historical schedules. They include the repair workstream and all twelve approval requirements. Source-level repair can proceed without treating a missing historical signature as a new authorization request, because the user explicitly authorized this work. Scientific results must be recomputed from frozen rules and raw evidence under explicit assumptions. Human review cannot approve missing evidence into validity. Resource/release authorization is separate and remains unclaimed.

Tier 0 closure requires mandatory requirement coverage, resolved applicable protocol decisions, deterministic verification and current audited campaign acceptance. Later-tier implementation or a historical tag cannot bypass this transition. A dependency-ordered, measured resource plan must precede any full statistical campaign; no unsupported completion date is supplied here.

## Restored original product contracts

The [lineage review](docs/program/MASTER_PROGRAM_LINEAGE_REVIEW_2026_10_12.md) found that the completed 93-row register did not enumerate every obligation in survey chapters 11, 14 and 15. PRD-01 now owns general objective/seed evaluation, budget and capability declarations, joint GP batching and pending trials, automatic diagnostics, adapter reconciliation and configured-study outputs. These are part of the original product goal. Completion of the qualified finite local baseline does not waive them.

The [public repair contract](docs/program/PRODUCT_REPAIR_CONTRACT_2026_10_12.md) now reconciles every restored clause, including local operational guarantees and stronger unqualified deployment clauses. The [fixed operations manifest](docs/PROGRAM_OPERATIONS.md) supplies bounded exact commands and a scoped approval installation. These are part of the same master, not a separate program.
