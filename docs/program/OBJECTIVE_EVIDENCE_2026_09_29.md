# Objective scientific evidence — master revision 1.15

This amendment implements **D-OBJECTIVE-EVIDENCE** within **STAT-03/F / VAL-01**. The user's direction is: “I don't think we should design a scientific result by human evaluation. It has to be proved objectively and not decided by acceptance of a human.” It supersedes the former PI-ruling requirement and the request to appoint a holdout reviewer. The previously adopted outcome/scope, numerical criteria and workload obligations remain in force.

## What determines a result

Mathematical claims require a derivation with explicit assumptions. Empirical claims require fresh observations, a rule frozen before those observations, reproducible reconstruction and quantified uncertainty. A valid experiment may fail to establish superiority. A negative or inconclusive outcome is an objective scientific outcome, even when it does not permit release. Neither a human nor an automated approval label can make a desired result true.

Humans can choose the research question, resource allocation and release policy. The existing .05 error budget and .80 power target are design obligations, not facts deduced from data. They are retained; the superiority margin remains zero because the adopted claim is positive gain. Review may identify an error in a derivation or implementation, but the correction must stand on reproducible reasoning/evidence rather than the reviewer's credentials. No human acceptance field enters the scientific decision rule.

Resource permission is separate. `tier0_resource_authorization` binds the exact design, phase and resource envelope and has scope `resource_execution_only`. Its validation can permit spending only after scientific readiness. The old `tier0_design_certification` receipt and a `certifier` name are no longer accepted substitutes. No allocation or release has been authorized by this amendment.

## Existing mathematical guarantee and its limits

Let independent complete seed vectors give utilities X_s in [-1,1], with means mu_s and average mean at most zero under the component null. For each lambda in [0,1], independence and AM-GM give

\[
\mathbb E\!\left[\prod_{s=1}^n(1+\lambda X_s)\right]
=\prod_{s=1}^n(1+\lambda\mu_s)
\le (1+\lambda\bar\mu)^n\le1.
\]

Integrating against the fixed uniform mixture preserves this bound. Markov's inequality yields a valid p-value `min(1, 1/E)`. Coordinatewise lower bounds on missing utilities cannot increase E, so they remain conservative without a missing-at-random assumption. The maximum of V04's eight component p-values implements its intersection-union claim. Two-entry Holm controls the registered family error under arbitrary dependence between entries. The fixed count, complete-vector unit, bounded utility, independent vectors and preserved missing slots are essential assumptions. This proof establishes an error guarantee under those assumptions; it does not establish their physical truth or predict PPO success.

Power cannot be proved uniformly .80 against every arbitrarily small positive effect at a fixed sample cap. For example, in the independent binary model with win probability approaching .5 from above, finite-sample rejection probability is continuous and approaches its null size. It cannot remain at least .80. A detectable-effect frontier is a conditional mathematical result. Treating a point on that frontier as the expected workload effect would manufacture a power claim. The prospective rank sizing contract therefore remains unresolved until compatible evidence supports its planning assumptions; no user-supplied guess or signature resolves it.

## Executable repair

`validation/tier0_objectivity.py` replays the declared stratified selection from the exact exposure-ledger digest, 32-byte seed reveal/commitment, fixed strata counts and algorithm. It verifies both entries' selected tasks, refuses duplicates, changed seeds, task substitution and insufficient eligible counts, and excludes unknown/exposed rows. The replay does not consult a reviewer name or approval field.

Even a `documented_unexposed` row is an assertion until its supporting history is verified. A successful replay returns **INCONCLUSIVE**, explicitly listing unverified provenance obligations. A hash establishes byte identity, not date of creation, concealment, completeness of a history or independence. The code deliberately blocks campaign readiness while the exposure-history, anchored chronology and execution-isolation verifiers remain incomplete. This closes the former bypass in which nonempty `independence_basis`, `independent_selector` and `exposure_review` strings could satisfy these checks. Removing a blocker requires implementing and validating its evidence contract, not another status field.

`require_campaign_ready` computes scientific prerequisites before checking separate resource permission. A frozen source-bound design replaces the human-certified design label. The existing protected-outcome reconstruction, missingness vetoes, invalid-inference refusal and unresolved prospective-sizing guard remain. `tools/check_protocols.py` rejects drift back to a human scientific override or PI-based D5 rule.

The new candidate is `validation/designs/tier0_candidate_v2_1.json`; v2.0 and the actual outcome approval remain immutable. Protocols V04-T0/V05 are version 3.1. The previous authority/source is preserved in `archive/program-2026-09-29/stat-03-before-objective-evidence/manifest.json`. Historical certificates and reviews are records of what was believed or authorized, not exceptions to current evidence requirements.

## Remaining objective obligations

| Obligation | Evidence that closes it | Current state |
|---|---|---|
| Exposure and task selection | Scoped development/exposure and lineage records, justified frame/strata/counts, selection replay against committed inputs | Source package and replay prepared; full history/lineage verification incomplete; no acceptance tasks selected |
| Selection chronology | Independently anchored commitment, implementation freeze and reveal ordering; evidence of seed concealment without discretionary retries | No anchored event chain or verifier yet; local timestamps/signatures cannot supply it |
| Execution independence | Frozen randomness model plus verified reset/isolation and ordering records; no cross-vector feedback or protected-data leakage | Disjoint namespaces and protected-score isolation tested; full operational evidence/verifier incomplete |
| Prospective power | Mathematically valid sizing rule under supported positive alternatives, applied prospectively | Conditional sensitivity available; compatible alternative and sizing contract unresolved |
| V01 conformance | Reference-derived scheduler and searcher traces plus a valid equivalence argument for the registered claim | Six artificial-table searcher loops prepared; scheduler traces and equivalence contract incomplete |
| V02 fault correctness | Independent reconstruction of outcomes for the frozen event/fault population | Input/source binding prepared; crash/concurrency reconstruction incomplete |
| Resources and final freeze | Measured runtimes, enforceable caps, exact frozen inputs and resource-only execution authorization | Measurements/allocation absent; no workload campaign run |

These are implementation, mathematical and factual dependencies owned by the program. The user is not asked to decide whether the evidence is true, provide an expected effect, choose a threshold or appoint a scientific arbiter. Continue the eligible repairs in the existing master. The master remains incomplete and release remains BLOCKED.

## Verification

The final affected suite passed **301 tests**, with no failures, errors or skips and two existing Torch deprecation warnings. The first run retained one obsolete reviewer-name assertion (300 passed, one failed); the corrected assertion now requires exposure-history, chronology and execution-isolation evidence. Both test reports are preserved. Ruff, protocol/program consistency, generated views, whitespace and archive/rule preservation checks passed. `objective-readiness.json` records 23 explicit candidate gaps, while `objective-v02-bound-candidate-contract.json` refreshes the unexecuted V02 input/source binding. Reproduce those records with `prepare_objective_evidence.py --output-dir <fresh-repository-directory>`. This is engineering verification; no empirical superiority, workload execution or scientific readiness is claimed.
