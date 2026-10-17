# Sequential repair plan — master revision 1.6

This is an amendment to the existing master, not a new direction. The goal remains reliable HPO and moderate architecture-coordinate NAS with auditable acceptance. Tier 0 is not complete. Existing code repairs, installation evidence, failed experiments and later-tier obligations are retained.

## The problems

| Problem | Concrete evidence and consequence | Owner |
|---|---|---|
| The plan mixed preparation, implementation and certification | D-PROTOCOL/D-TIERS were dependencies even for preparing a concrete implementation choice. A complete proposal and a certified experiment are different deliverables. Repeatedly listing the aggregate blockers did not resolve them. | GOV-01; scoped decisions below |
| ASHA promotion does not match the proposed reference | At eta=3, one to three entrants all promote; the Syne Tune 0.13.0 reference waits for two observations and uses a quantile. Current code also permanently stops waiting candidates which the reference may promote after later arrivals. | SPEC-02A, SPEC-02 |
| Median stopping lacks the promised runtime contract | Live endpoint values substitute for running averages from completed trials. Study receives results only after endpoint evaluations finish, so a flag alone cannot implement stopping while training. | SPEC-02 |
| Some validators answer different questions from the register | V04-T0/V05 currently run random versus pathological PPO. The proposed governing claims require GP/TPE versus Sobol/random and warped versus unwarped GP. More executions of the current runner cannot establish these claims. V01/V02 also cover less than their full stated wrapper/event populations. | D-T0-CLAIMS, STAT-02, VAL-01 |
| Statistical design and compute planning are incomplete | Tasks, numerical bounds, independent study blocks, endpoint decisions and actual capacity must be fixed. Three studies cannot satisfy the current strict one-sided p<0.025 rule. Increasing trials inside each adaptive study does not add independent studies. | STAT-02, PILOT-01, CAP-01 |
| Pilot and final certification ordering is ambiguous | Register status awaits a pilot report, while D5 requires certification before any campaign spend. A pilot cannot be launched by assuming an exception, and measured pilot-based sizing cannot be required before permission to obtain pilot data. | D-PILOT-ORDER, D-PROTOCOL |
| Current acceptance evidence is absent | All six receipts are stale after repairs; V03 is a historical diagnostic. Historical V02's GP replay also diverges from repaired source. This is a reason for validation on the final implementation, not a reason to restore old bugs or erase results. V03 scope/operators/population still need reconciliation. | V03-03, PPO-01, REL-01 |
| Optional priors and later tiers contain separate unfinished work | Two prior-recovery diagnostics fail; the current PriorBand heuristic differs from the published method. Multi-objective orchestration, workload templates, population methods and distributed operations remain incomplete. | PRI-01 and retained later-tier items |

The shell/interpreter mismatch and sandbox Ray startup denials were resolved for the previous verification. The affected 34 Ray tests passed in a permitted environment. They are execution prerequisites to document, not new open algorithm defects. The release prerequisite bypass is repaired under GOV-02; do not repeatedly rebuild completed governance instead of addressing the remaining product gaps.

## Order of repair

| Order | Existing/newly explicit master item | Concrete deliverable | Closure evidence / next dependency |
|---|---|---|---|
| 1 | SPEC-02A | A narrow scheduler contract recommendation and independent examples, including late arrivals, ties and missing completion information. | Bound reference sources and observed disagreements. Preparation is authorized without campaign certification. |
| 2 | SPEC-02 | Implement the chosen scheduler contract in three slices: ASHA promotion/pause state; streamed metric/completion and continuation plumbing; median running-average rule. Preserve explicit compatibility behavior and checkpoint boundaries. | Independent reference cases, event/recovery tests and local/Ray integration. D-SCHEDULER settles the material contract choices; unrelated tier decisions do not gate the repair. |
| 3 | STAT-01 / STAT-02 | Resolve the narrow Tier 0 claim identity question, then write the complete proposed task/arm/endpoint/missingness/seed/scale design and deterministic sizing procedure, with an explicit pilot resource request. | Reviewable versioned manifests and analysis fixtures. This is design work; it does not include pilot spending or a claim of measured power. |
| 4 | VAL-01 | Repair campaign runners, registries and independent analyzers to exercise the agreed arms/endpoints; extend V01 wrappers and V02 event grammar. | Positive and deliberately failing fixtures, honest pilot/smoke labels and source-bound output. This source-changing work must precede final V03. |
| 5 | PILOT-01 | Run the independent pilot only after the PI resolves certification order, certifies the actual pilot design and assigns its compute envelope. | Disjoint pilot data, measured runtime/resource cost and preserved failures. No confirmation claim or data reuse. |
| 6 | CAP-01 | Apply the declared power/coverage simulations, derive sample counts and measured cost, and propose a funded confirmation/replication schedule. | Evidence that the required precision/power fits the sample caps and resource envelope, or an explicit infeasibility result. |
| 7 | V03-03 / PPO-01 / REL-01 | Certify the final applicable protocols, freeze source/tests/dependencies/analysis, then run the full mutation, wrapper, scheduler, real-workload and integration acceptance set. | Current recomputed campaign decisions and V16 audits. A failure returns to its named repair item; a source change invalidates affected receipts. |
| 8 | REL-01, then later tiers | Review all mandatory requirements and obtain the release decision before advancing. | Complete requirement/evidence matrix, explicit release authorization and a recorded phase transition. |

PRI-01 remains opt-in and outside the Tier 0 critical path unless a recorded scope decision requires it. Its failures and method gap remain visible. Later-tier work follows REL-01 and its own narrow decisions; no feature is silently removed to get a green gate.

This table is the preferred serial work order. A scientific decision can block its dependent implementation or experiment while unrelated authorized preparation continues. The register carries true dependencies; the table is not a blanket prohibition on preparing a later decision packet.

## How each problem is closed

For each problem, record the smallest failing example, the governing behavior or clearly marked proposal, the smallest implementation change, the independent verification, and the exact remaining claim. Ask for a ruling only on unresolved material design/scope/acceptance choices. Ordinary engineering repairs and preparation use the existing authorization. Do not substitute a large passing regression count for algorithm conformance or a scientific claim.

Review and update the master after each closure. Do not change seeds, acceptance thresholds, method names or required endpoints to force a PASS. Freeze acceptance only after source-changing repairs are finished. Preserve partial and failed runs at any resource limit. Calendar estimates remain uncommitted until real pilot measurements support them.

## Focused decisions

| Decision | What must be decided | What it does not authorize |
|---|---|---|
| D-SCHEDULER | The concrete reference/runtime contract in [SPEC-02A](SCHEDULER_CONTRACT_PROPOSAL_2026_09_29.md): promotion reference, waiting/ties, completed-trial running averages, streaming/continuation, and insufficient full-fidelity evidence. | Statistical certification, algorithm performance claims or a Tier 1 transition. |
| D-T0-CLAIMS | Whether V04-T0/V05 follow the reviewed register claims. Recommendation: use the register and retain the old PPO comparison as a diagnostic. | Automatic acceptance of unresolved numerical hypotheses, old results, or later-tier mappings. |
| D-PILOT-ORDER | Resolve D5's ordering explicitly. Recommendation: certify the frozen pilot protocol and resource cap first; then use its independent outcomes for final sizing and confirmation certification. | Unspecified pilot spending, weakening D5, or reusing pilot observations in confirmation. |
| D-PROTOCOL | Actual certification of the final applicable design(s), including V03 population/operator manifest and exact statistical definitions. | Release approval or an unassigned compute allocation. |
| D-TIERS / D-WORKLOADS | Remaining release scope, later-tier ownership and workload claims. | A reason to block independent Tier 0 contract preparation. |

The re-plan is authorized. The listed scientific/runtime rulings remain open. The former single broad claim/tier approval question is replaced by these concrete, ordered decisions; the user has not approved it by asking for this re-plan.
