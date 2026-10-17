# Whole-program review and execution repair

This review continues GOV-01/GOV-02 under the user's standing instruction to
repair, refresh and execute the existing master. It supersedes the incomplete
revision 1.52 ownership/coverage conclusions. Revision 1.52 and its evidence
remain archived unchanged. Scientific campaigns, numerical rules and the
running attempt09 source remain unchanged.

## Goal and completion boundary

The goal remains reliable HPO over moderate architecture and training axes,
with reproducible execution, recovery and independently audited acceptance.
General topology/cell/supernet NAS remains excluded. A passed mutation suite
establishes its finite fault-detection contract; it cannot establish empirical
PPO superiority or complete the broader product. Tier 0, later capabilities,
distributed service readiness and the whole master have separate exit criteria.

## Findings and required repairs

| Finding | Evidence and implication | Repair owner |
|---|---|---|
| Coverage was syntactic | `tools/program_continuation.py` checks only listed stages. A completed decision packet was counted as coverage while its decision stayed open. The original `any(external_dependency(...))` can hide independent internal prerequisites behind a resource blocker. | GOV-02 adds an executable supplemental graph audit now; it joins work, stages and decision resolvers and refuses uncovered work, internal leaves and cross-graph cycles. |
| Revision 1.52 misassigned V13 | `validation/protocols.json` defines sampler vetoes/calibration. The old markdown title incorrectly calls it warm-start effectiveness. | Restore WL-01 as accountable V13 owner; T1-WARM owns V12 only. Preserve the unresolved markdown identity until a prospective protocol repair. |
| V04-T1 has no relation to cost cooling | The register compares TuRBO and prior-aware qLogEI with log+Sobol. The historical markdown instead compares Sobol/random with a post-failure margin change. | T1-TRUST owns the registered campaign, with PRI-01 supplying its prior-aware arm. T1-COST needs its own objective contract; V04-T1 cannot certify it. |
| Tier dependencies were flattened | Every later item depended only on REL-01, allowing population and ifBO integration without method/reference prerequisites. | Add explicit Tier-1 reconciliation, trust-region-before-population, checkpoint-before-integration and V15a-before-V15b stages. V12's real-history precondition precedes execution, not Tier-1 implementation. |
| Core workloads were wholly deferred | `NAS_SCOPE_DECISION.md` and the build review require a Tier-0 real RL vertical slice with real architecture axes. REQ-ch09-01/05 pointed only to later WL-01. | Add WL-00 for the Tier-0 supported workload/template contract; map the broader DEHB/population portions to their later owners. A one-trial V14 demo cannot certify every template obligation. |
| Median default is unresolved | Survey chapter 5 calls for always-on ASHA/median; `ASHAConfig.median_stopping` is false, and enabled streamed median requires a report grid. V06 gates the evidence for default early stopping. | REL-01 owns a concrete default-disposition stage before release. Keep the existing unresolved requirements visible until contract/default/evidence agree; do not flip a boolean during a frozen run or infer performance from tests. |
| Global protocol status couples phases | The release checker requires a globally FROZEN register while later protocols remain draft; PPO-01 also depends on broad D-PROTOCOL. No work-only cycle exists, but this is an unresolved phase-scope requirement. | GOV-02 must prepare and verify phase-specific closure semantics that preserve every applicable entry, raw-verdict check and open-decision veto. Do not merely set global status to FROZEN or weaken the gate. |
| Source-changing repair was queued after successful mutation | A repair that depends on PASS can never become eligible when the run fails. Applying it after PASS makes that source receipt stale. | Stage repairs now; adopt only after retained campaign closure, regardless of verdict. After adoption, rebind and refresh all affected acceptance before release. |
| Pilot cost was a scenario | The 828-study, 1,899.8-hour scenario is not an optimized request or a lower bound. The bound of fifty selected policies is a safety ceiling. | STAT-03P retains the exact sensitivity analysis and has a cost-repair stage before asking for actual allocation. |
| Readiness was called completion | A protocol review, allocation, empirical outcome, audited verdict and release are different deliverables. | Define resolution stages and terminal work stages separately. Preparation never closes a scientific result. |

## Protocol ownership and ordering

| Registered entries | Accountable owner | Required ordering / limitation |
|---|---|---|
| V01, V02, V14 | RPR-01 with VAL-01 refresh | Current finite reference/runtime/integration evidence; V14 is limited to its bounded demo. |
| V03 | V03-03 | Frozen complete inventory, controls, raw reconstruction and unchanged acceptance rules. |
| V04-T0, V05 | PPO-01 | Concrete pilot freeze and allocation, independent pilot, fixed sizing, fresh confirmation freeze and allocation, then audited comparison. |
| V04-T1 | T1-TRUST | Register claim includes trust-region and prior-aware methods; exact protocol reconciliation and PRI-01 method readiness precede the campaign. |
| V06 | T1-MF | Registered non-inferiority **and** cost bound; a high p-value from a difference test is not equivalence. |
| V09, V10 | T1-MO | Complete MO orchestration; Hamiltonian/sampler contracts and independent fidelity-selection data before their gate. |
| V11a, V11b | PRI-01 | Faithful published method, independent good/wrong-prior recovery and fixed per-method claims; optional/opt-in until evidence supports more. |
| V12 | T1-WARM | Distributed-beta gate and at least ten eligible real same-family studies; no fabricated history. |
| V13 | WL-01 | Sampler correctness/vetoes and calibration; ordinary HMC must not be labelled learned transport. |
| V08 | T2-POP | Trust-region, PBT/PB2-Mix, faithful BG-PBT, architecture/checkpoint compatibility, both worker regimes and fixed resource allocation. |
| V07, V15a, V15b | T3-01 | Reference feasibility before an owned DEHB implementation; pretrained ifBO V15a before adapter/integration V15b. |
| V16 | VAL-01 | Independent audit of every campaign; audited FAIL/INCONCLUSIVE cannot become PASS. |

This assigns accountability. It does not declare mismatched protocols aligned.
D-TIERS closes only when this mapping and all retained source obligations are
reconciled; the concrete protocol-identity/design work is separately tracked.

## Exact pilot feasibility and cost

The independent rational reconstruction in
`evidence/2026-10-04/program-repair-02/pilot-feasibility.json` reproduces the
fixed sizing rule: 46 pilot vectors per entry is the ideal minimum and requires
all 46 to be jointly good. It uses the existing .95 simultaneous planning
confidence, .80 power target and maximum 20 confirmation vectors. It changes
no endpoint, threshold, task, seed or frozen rule.

At a **hypothetical** true joint-good probability .95, one entry sizes with
probability .95^46 = .094468. If both entries had independent outcomes with
that same probability, both would size with probability .008924. Without that
extra independence assumption, their joint probability is bounded between
zero and .094468. These are sensitivities, not empirical estimates.

For sequentially fully evaluated vectors, stopping at the first definitively
bad vector is sufficient to prove futility under this minimum-size rule. Its
expected vector count is `(1 - p^46)/(1 - p)`, or 18.11 at hypothetical p=.95.
The current implemented shortcut detects irretrievable **search loss** before
protected evaluation. It does not implement this broader sequential rule:
the existing experiment freezes all search traces before protected outcomes.
Changing that chronology needs a prospective proof and implementation review.
The analytical expectation must not be quoted as current measured runtime.

At the historical search/overshoot budgets, sixty seconds of coordinator
allowance per study and three distinct protected policies per study, scenario
work is 1,035.0 hours; at fifty policies it is 1,899.8 hours. The shared per-entry
reservation schema multiplies these totals by 4/3. Three policies is a
sensitivity, not a guaranteed ceiling. Reducing accounting over-reservation
does not remove the search work. One measured Ant GP study cannot establish
the timing or statistical effect for every arm/task/configuration.

There is no mathematical theorem that guarantees an arbitrary optimizer has
a positive empirical advantage. More generally, with a zero superiority
margin, no finite fixed sample has .80 power uniformly over all positive
effects: for Bernoulli alternatives `p=.5+epsilon`, the sample distribution
approaches the null as epsilon approaches zero; total variation is bounded
by `sqrt(n * KL(p || .5) / 2)`, so power is at most alpha plus that bound.
Exact analysis can establish feasibility conditional on an effect; it cannot
invent that effect. A scientifically terminal infeasible or inconclusive
result must be retained, not followed by repeated favorable attempts.

## Execution and source freshness

Attempt09 continues under its original source, controls, four-worker limit
and six-hour cap. The existing coordinator retains/reconstructs it and advances
its finite conformance/readiness branch only after objective acceptance.
The supplemental graph audit and analytical review run outside that source
inventory; their exact hashes are registered as governance evidence. This is
not a change to source hashing or scientific acceptance.

All independent document, proof and staged repair work remains eligible now.
Source adoption waits for retained run closure. Any resulting source change
invalidates applicable freshness and requires a new bound baseline/installation
and validation plan before acceptance. No valid PASS is discarded silently;
its original source-specific result remains evidence.

At each phase boundary, record raw outcome and terminal scope, audit the
combined graph, repair what is eligible, refresh the next phase inputs and
continue. Stop only after full completion, an explicit pause, or when every
remaining eligible branch truly depends on evidenced external input. Merely
finishing the coordinator's current branch does not finish the master.
