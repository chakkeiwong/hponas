# Master-program lineage and completion review

Reviewed 12 October 2026 against master revision 2.250 and executable source
`53c3d5ff21a63c7f78ecfe286aad4f72e99ad2a2b6faa186cf58af7691127cc3`.
This review supplies the correction in revision 2.251. The single execution
authority remains [CONSOLIDATED_MASTER_AUTHORITY.md](../../CONSOLIDATED_MASTER_AUTHORITY.md).

**The recovered program exists, but whole-product completion was not established.**
The recovery documentation milestone, implementation work and final qualification
are different accomplishments. The accepted package is valid for its declared
finite local scope. Mutation testing is one engineering gate within that package;
it was never the whole product goal. Revision 2.250 incorrectly treated completion
of an incomplete register as completion of every retained product obligation.

The product goal is an internal Python package for reliable hyperparameter tuning
and moderate architecture-coordinate search. A researcher should be able to
declare a study, run appropriate searchers and schedulers, recover its execution,
and obtain recorded objectives, evaluations, costs, diagnostics and provenance.
The current testing scope uses small, self-contained models with known answers.
It does not require dependencies on FinMarketing, MacroFinance or other projects,
new large PPO comparisons, general topology NAS, or a separate-machine test.

## Lineage: what each program was meant to complete

Dates below are document labels where available. Labels and old timeline estimates
are historical planning information, not verified execution dates or current
resource requests. The retained JSON inventory covers 356 archived register
snapshots and 337 distinct revision labels before this correction. It is not a
claim that every intermediate revision survives.

| Predecessor / record | Role and successor | Meaning of completion |
|---|---|---|
| Survey product, architecture, contracts and roadmap, chapters 14, 11, 15 and 12 | Original product contract; informs all build programs | Working study workflow, algorithms, adapters, storage, workload integration and objective validation |
| `archive/BUILD_PROGRAM_v1_REJECTED.md` | Original tiered build, superseded by v2 after RED review | Full internal tuner; V03 was explicitly a Tier-0 sabotage-detection gate |
| `BUILD_PROGRAM_REVIEW_VERDICT.md` (28 August) | Eight blockers and twelve approval requirements; authorized specification/spike repair | Corrected scope, contracts, feasibility and build plan; no blanket product certification |
| `BUILD_PROGRAM_v2.md` and its approval record (1 September) | Reconciled tiered build; later rebaselined as v3 | Foundations, core methods, population, operations and selective research bets |
| `HPO_NAS_RECOVERY_MASTER_PROGRAM.md` | Four-week recovery plan producing reconciled specifications, spikes, validation design and v3 | Recovery/approval readiness. Its explicit “Post-Approval Execution (Not Part of Recovery)” section retains Tier 0, Tier 1 and Tier 2 execution |
| `RECOVERY_PROGRAM_STATUS.md`, `RECOVERY_STATUS_AUDIT.md`, `RECOVERY_NEXT_STEPS.md` | Recovery documentation closure and warning that execution was still outstanding | Documentation complete did not mean all tests or product work complete |
| `archive/program-2026-09-28/BUILD_PROGRAM_v3.md` (September draft) | Rebaselined whole build following recovery | Seven Tier-0, nine Tier-1, five Tier-2 and six distributed component groups; historical 93-engineer-day estimate |
| `TIER0_EXECUTION_MASTER_PROGRAM.md` | Child execution plan under v3; expressly Tier 0 only | V01, V02, V03, V04-T0, V05, V14 and V16, plus their prerequisite repairs |
| `V03_R10_RESET_MEMO.md` and recovery V03-R/R9/R10 additions | Mutation debugging branch; reviewed against later raw evidence | Mutation remediation only. The later audit disproved the old zero-kill/cache interpretation |
| `MASTER_PROGRAM_UPDATE.md`, `MASTER_PROGRAM_UPDATE_V1.2.md` | Reconciliation attempts after mutation work dominated status | The v1.2 update still said the next phase was unknown and referred back to v3 |
| Archived consolidated authority v1.3, September audit/repair plan, 28 September review | One master replaces competing execution authorities; source documents retained | Reconcile implementation, evidence and continuation without dropping later tiers |
| `WHOLE_PROGRAM_REVIEW_2026_10_04.md` and `MASTER_REFRESH_REVIEW_2026_10_05.md` | Restored broader scope, dependencies, phase ownership and preparation | Explicitly warned that mutation closure was insufficient; later product execution remained |
| Consolidated revisions 1.90 through 2.87 | User-directed known-answer tests, finite capability contracts and local operations | Narrower scientific claims, opt-in methods and waived separate-machine testing; not an automatic waiver of unlisted API contracts |
| Revisions 2.249 and 2.250 | Final qualification, then closure wording | 35 registered work items and 177 stages closed; 17 fresh campaigns and five gates passed. The register was not a complete product-contract inventory |
| Revision 2.251, this review | Preserve qualification; restore missing product obligations as PRD-01 | Whole master remains incomplete until the explicit product reconciliation and repair sequence closes |

Git commit `c6bd99e2f32a483debf73eb4d35d8a35658c8e68` preserves the original
build, work-breakdown and reconciliation documents under `archive/`; they were
not lost. The original approval record contains an unsigned block. This review
does not invent a historical signature; current repair authorization is already
present in the user's instructions.

## What is actually complete

The [final accepted package](evidence/2026-10-12/final-qualification-11/accepted-package.json)
binds 17 fresh campaigns and five final gates to the source named above. This
includes foundations, eight finite Tier-1 entries, population, DEHB, warm starts,
workload dispositions and retained local operations. Thus the work after recovery
was substantially broader than mutation debugging alone.

The final V03 population contains 9,437 mutants, with a 96.1879% adjusted kill
score and zero unproved critical survivors. These are mutation-adequacy results,
not proof that every intended feature exists. The earlier critical-survivor FAIL
remains retained. ifBO feasibility remains FAIL and its integration remains
cancelled. Optional methods have no automatic performance-based default
promotion; separate-machine testing was waived, not passed. Supervised local
research qualification does not establish unattended production readiness.

## Why the completion claim drifted

The 93 old requirement rows comprise 63 algorithm/workload decision rows, 18 audit
findings and 12 approval items. `tools/program_state.py` checks that those known
IDs are mapped, and `tools/program_continuation.py` reports completion when the
listed work and stages are complete. Neither check discovers a contract sentence
that never became a requirement. Chapters 11 and 15 and the legacy product
register were not even hash-bound source inputs, although chapter 14 was.

The legacy `hpo-survey/product_register.json` contains 38 rows. Its final row
incorrectly folds several workload families into “RL, routine budgets”; some
validation IDs and tier labels are obsolete. The accompanying trace maps its 37
method rows to their current decision rows and splits the final row across all
eight chapter-9 decisions. It preserves the old file as evidence instead of using
it as a second authority. Counting those rows still cannot establish semantic
coverage of chapters 11, 14 and 15.

The previous 21 “deferred” labels also mix watchlist methods, later-tier features
that were subsequently implemented, and cancelled research bets. The trace records
each current disposition and owner. PRD-01 must reconcile those meanings without
silently reopening watchlists or treating cancellation as a scientific PASS.

## Product obligations that need repair or explicit reconciliation

| New requirement | Source and finding | Concrete completion criterion |
|---|---|---|
| PRD-DECL | Ch15 study declaration; `Study.__init__` records direction but has no general objective identity/evaluation-protocol declaration | Mandatory objective identity, direction and evaluation semantics are persisted and checked on resume; scalar/vector behavior is explicit |
| PRD-SEEDS | Ch11 seed aggregation and Ch14/15 default seed protocol; `Study` assigns a seed per suggestion and returns the search best. V14 has a workload-specific final evaluation | General tuning-seed aggregation, frozen selection, disjoint final evaluation and recorded opt-out; final data cannot feed search; cheap known-answer and leakage counterexamples |
| PRD-BUDGET | Ch15 full-run equivalents, worker capacity and population boundary | Declared units and capacity, explicit eligibility/advice and opt-in limits; reconcile old eight-worker/default promises with the finite local scope without claiming empirical evidence |
| PRD-BATCH | Ch15 `propose(n,state)` and pending trials; public GP uses q=1 and no pending acquisition inputs; Study fills concurrency through repeated single suggestions | Joint batch acquisition and pending-trial treatment, or a justified recorded contract revision; deterministic independent checks and recovery of pending state |
| PRD-CAPABILITIES | Ch15 static capabilities; base searcher currently infers supported kinds from the supplied space. Some implementations do refuse unsupported inputs | Uniform declarations and early refusals for kinds, conditions, objectives, priors, fidelity and architecture axes; partial method checks cannot stand in for the full matrix |
| PRD-DIAGNOSTICS | Ch14/15 require automatic rung-versus-final rank correlation; store comments/raw observations do not implement the statistic | Persist per-rung diagnostics with pair counts, ties, censoring and explicit insufficient-data outcomes; never fabricate missing finals |
| PRD-ADAPTER | Ch11/15 specify Ray Tune protocol mapping; public adapter uses Ray Core; legacy Tune code exists | Compare execution/checkpoint/lineage guarantees and explicitly retain, integrate or amend the backend contract within local scope; no assumption that Core qualification proves Tune integration |
| PRD-CONFIG | Ch14 configured studies; qualified small workload callables/examples are real, but do not close all study-level promises | Maintained self-contained study entry points exercise declaration, selection, evaluation, resume and reporting through the public API |
| PRD-OUTPUTS | Ch15 complete declarations, learning curves, vetoes, schedules, fronts and cost queries | Clause-by-clause store/report checks through public studies; reuse existing evidence where it actually covers the contract; repair demonstrated gaps |
| PRD-TRACE | Product's four anchors: contract, test, schedule and cost | Every normative clause and old build group has a current owner, evidence or explicit authorized disposition; synchronized documentation; completion cannot rely only on the old decision-ID count |

The trace distinguishes observed implementation gaps from requirements needing
reconciliation or end-to-end verification. This is not a claim that all ten rows
are wholly absent. It also inventories the remaining search-space, scheduler,
storage and architecture-factory clauses and links their existing implementation
owners. Stored data, a test name or a passing generic campaign alone is not a
substitute for a behavioral contract check.

## Where the rest of the original build went

The structured trace has one disposition for each of the 27 numbered v3 component
groups. Its two “removed from Tier 1” headings are transfers to Tier 2, not lost
extra components. The mapping includes all twelve recovery approval items and all
63 current source-decision requirements.

| Original build group | Current continuation / retained result |
|---|---|
| Tier-0 GP, baselines, executors, RL, test/validation repairs and gate | RPR/SPEC/TST/PKG/WL-00/REL-01 and final package; general study contracts now PRD-01 |
| ASHA, MO-ASHA, qLogNEHVI, Chebyshev, NSGA-II, cost, priors | T1-MF/T1-MO/T1-COST/PRI-01 finite results; defaults remain opt-in |
| ifBO | Reassigned to selective Tier 3; retained failed feasibility and cancelled integration |
| TuRBO, mixed-space trust regions, BG-PBT | T1-TRUST/T2-POP finite acceptance; no empirical dominance or cluster scaling conclusion |
| Warm starts and diagnostics | T1-WARM/V12 and finite T1-MF/T1-MO; automatic general study diagnostics remain PRD-01 |
| Distributed-beta storage, backups, monitoring, scale, security and budgets | OPS-01 local PostgreSQL/Ray qualification under D-LOCAL-OPERATIONS-SCOPE; detailed stronger historical claims need explicit dispositions |

In particular, the old distributed chapter names migration rollback, incremental
and point-in-time backup, automated schedules, live alert delivery, 100-study /
50-worker scale, application user roles, and user GPU-hour quotas. The local
qualification does not prove all of those sentences. The trace marks them for
itemized reconciliation under the adopted supervised-local scope. It neither
silently waives them nor schedules an expensive production/remote test suite.

## Repair sequence within the same master

PRD-01 depends on the completed REL-02 baseline and owns this sequence:

1. Retain the lineage review, then finalize clause-level contracts and disposition
   choices against the existing scope amendments, using small independent examples.
2. Repair the general declaration and tuning/final-evaluation workflow.
3. Reconcile capability declarations, budget units and method eligibility.
4. Close joint GP batching and pending-trial handling.
5. Compute and persist study diagnostics with explicit missing-data behavior.
6. Resolve the adapter discrepancy and complete configured-workload/store outputs.
7. Synchronize the overview, approval checklist and requirement dispositions;
   enforce clause coverage in the completion review.
8. Review the integrated product against every retained obligation and qualify
   affected source changes under prospectively specified checks.

At each boundary: retain evidence, repair what failed, refresh dependent work,
then continue. No new broad performance study or mutation run is allocated by
this audit. Future source edits require appropriate requalification; the accepted
baseline remains intact in its snapshot. Objective tests and declared scope
determine completion; no human vote sets a scientific success threshold.

## Evidence and limits

The [structured trace](evidence/2026-10-12/master-lineage-review-01/trace.json)
contains document hashes, lineage edges, observed amendment transitions, every
old product-register row, every v3 component group, the twelve approval items and
the interface-clause inventory. The
[archive inventory](evidence/2026-10-12/master-lineage-review-01/archive-inventory.json)
retains snapshot hashes. Revision 2.250 is preserved in the
[pre-correction archive](../../archive/program-2026-10-12/before-master-lineage-review-01/manifest.json).
The [program-check receipt](evidence/2026-10-12/master-lineage-review-01/program-checks-01/receipt.json)
records the six required consistency/continuation checks after the correction.

This is a source/evidence lineage audit, with specific implementation inspection;
it is not fresh functional acceptance of every clause. It repairs the false
completion boundary and makes the remaining work visible and executable. The
master must not be declared complete until PRD-01's semantic product review and
required repairs have evidence-backed terminal dispositions.
