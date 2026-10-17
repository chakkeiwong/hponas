> Revision 1.20: [scope adoption and current review](SCOPE_ADOPTION_REVIEW_2026_10_01.md) supersedes pending-scope, pre-pilot-effect and unmeasured-installation status below. Follow the structured continuation queue and current master; historical outcomes are retained.

# Revision 1.19 execution and whole-program review

The review found internal work incorrectly described as external blockers. The repair has executed: phase-specific contracts, a positive pilot-readiness path, raw-pilot sizing verification, local freeze/launch chronology, one-use campaign directories, explicit per-entry resource caps, development profiling and V01 source investigation. The implementation does not promote incomplete evidence into scientific acceptance.

## Whole-program disposition

All 93 requirements remain mapped, including 63 survey decisions and all twelve approval requirements. All 19 protocol identities remain bound. The program now has 30 work items because STAT-03P separately owns pilot readiness and removes a semantic dependency cycle.

| Work | Current disposition and remaining obligation |
|---|---|
| GOV-01/02, RPR-01, SCOPE-01 | Completed engineering/governance scope retained. Reconciliation passes; release is separate. |
| SPEC-01/02/02A/03 | Completed GP/searcher/scheduler contract repairs retained. Current-source acceptance must be rerun at the dependent final freeze. |
| TST-01, PKG-01 | Existing bounded test/installation deliverables retained; these are not universal platform or production certification. |
| STAT-01/02 | Existing inference safeguards and candidate mechanics retained. The invalid legacy percentile path remains refused. |
| STAT-03 | Framework repair executed; prospective scope and resource preparation remain explicit. Pilot observations are no longer a prerequisite for preparing its framework. |
| STAT-03P → PILOT-01 → CAP-01 | Exact pilot freeze, then separate pilot, then confirmation sizing/capacity. Neither pilot readiness nor its schema needs an already observed pilot effect. The five-vector plan fails the prospective sizing screen and is not launched. |
| VAL-01 | Protected comparison adapters and finite conformance machinery remain implemented. V01 data coverage changes need scope authorization; proposed known-exposure sampling is separate from approval of rank outcomes. |
| V03-01/02 → V03-03 | Mutation accounting/triage repairs retained. Final full mutation acceptance remains unexecuted on the final source; old counts or focused diagnostics cannot close it. |
| PPO-01 → REL-01 | Actual fresh confirmation, full gates, defaults/release authority remain incomplete. No scientific PASS or release follows from this repair. |
| PRI-01 | Optional, opt-in and uncertified; not promoted into the critical acceptance path. |
| T1-MO, T1-COST, T1-WARM, T2-POP, WL-01, OPS-01, T3-01 | Retained later-tier capabilities, workloads and operational obligations. None is silently removed or declared complete to finish Tier 0. |

## Evidence and scientific limits

The affected suite passed 367 tests. Follow-up checks after the final launch/resource safeguards passed 196 tests; these overlap the earlier suite and must not be summed. The initial failing assertion and all intermediate reports remain recorded. Two existing Torch deprecation warnings remain.

The original HalfCheetah CSV is byte-identical to its pinned upstream version. It contains 4,517 missing observations, including 421 at seed 0; the available source does not distinguish lost records from training failures. All 187 seed-0 configurations finite at every recorded fidelity enter the proposed supplemental domain. All nine independently reconstructed supplemental trajectories complete and agree. The original 36-case V01 result stays INCONCLUSIVE; the new engineering evidence cannot change that historical result or the current acceptance contract by itself.

The CPU compatibility profile completed training and separate checkpoint evaluation in 27.57 seconds, including startup (16.41 search/training and 7.78 separate evaluation). The actual 100k-step Ant recipe timed out at 120.27 seconds. Its retained learning curve reached 122,880 steps at roughly 100 seconds because the trainer rounds its batches; no completed policy/evaluation timing exists. The timeout is a lower bound, not a full campaign forecast. GPU readiness is being repaired in an isolated environment; current inventory alone is not a measurement or allocation.

The new sufficient sizing rule uses independent pilot confidence bounds, retains missingness and ignores supplied SIZED/PASS labels. An ideal five- or twenty-vector pilot cannot satisfy it. It first succeeds at 277 ideal vectors; this conservative-rule screen is not an optimum or a resource recommendation. A separate exact binary submodel gives a necessary all-win pilot bound of 25 for a 95% lower power guarantee at the isolated 20-vector test: near the .80-power frontier, five wins occur with probability .53665. Thus a tiny perfect pilot cannot establish the proposed assurance even in that favorable submodel. Neither derivation identifies actual PPO effects. Cost-veto uncertainty remains an explicit condition of the power statement and an actual acceptance veto.

## Continuation boundary

The [V01 coverage proposal](V01_DATA_COVERAGE_PROPOSAL_2026_09_30.md) and [prospective suite proposal](PROSPECTIVE_SUITE_PROPOSAL_2026_09_30.md) are concrete and reviewed. They alter existing approved scope, so their adoption awaits the requested scope decision. This is administrative authorization of the question investigated, not a human ruling on its result. Independent environment and bounded resource preparation continue while that decision is pending.

Source changes make the earlier V01/V02 receipts stale for future acceptance. Their original verdicts, raw artifacts and V16 reports remain preserved. Revalidate at the dependent final freeze after scope changes, rather than repeatedly running the same campaigns during intermediate preparation. The structured continuation queue and generated master views distinguish this from a claim that the master is complete.

The first conservative screen required 575 ideal vectors because it bounded any unresolved vector as a veto. The final repair uses the actual >10% allowance: at most floor(.1 n) incomplete vectors cannot exceed the loss cap in any arm. The exact binomial upper tail under the stated independent stationary-vector model reduces the ideal sufficient count to 277. The original 575-vector report is retained; `pilot-feasibility-r2.json` records the reviewed rule. No observed pilot data informed this repair.
