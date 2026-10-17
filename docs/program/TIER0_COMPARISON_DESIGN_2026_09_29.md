# STAT-02 candidate design and VAL-01 execution contract

Revision 1, 2026-09-29. D-T0-CLAIMS was accepted by the user's “yes. Continue the execution.” This supersedes the pending-decision wording in the earlier hash-bound design-input note; that historical note is unchanged. This document is engineering design, not PI certification.

## Identity and estimand

V04-T0 requires **both** GP+qLogEI and TPE to beat **both** log+Sobol and random. All four comparisons include final objective and the decision-bearing normalized regret AUC: eight components must clear. V05 compares the same main GP implementation with and without log coordinates, using the same five frozen physical initial configurations, charged separately in both arms. Its final-objective component must clear. Both GP arms then use the same model, acquisition and numerical controls; only encoding differs. Random fallback after failed initialization cannot silently change the estimand: a failed study is missing.

The candidate manifest is `validation/designs/tier0_candidate_v1.json`. It reserves separate pilot (10000–10004), confirmation (20000–20019) and replication (30000–30019) optimizer-seed pools. These are new future campaigns, not changed seeds for an unsuccessful old campaign. CAP-01 must select and freeze the confirmation count before execution. Every task/seed block contains all entry arms. Individual adaptive trials are never independent statistical replicates.

Final-objective superiority uses normalized margin zero, the registered positive-gain hypothesis. The V04-T0 AUC threshold remains **null**, because the register never specified it. The historical 5% random/pathological margin and 15% synthetic sampling diagnostic are preserved under their actual identities; neither is translated into a normalized GP/TPE effect. Missing thresholds refuse execution.

## Candidate tasks and inputs still required

The catalog proposes Brax PPO Ant, HalfCheetah and Hopper at 100,000 training steps with explicit physical domains and complete training settings. This is a reviewable selection proposal, not an assertion of task independence, pinned environment assets or achieved returns. All three have unresolved task/environment versions and asset hashes, independence justification, scale bounds, regret references, pre-observation objective, measured study budget and overshoot limit. Frozen initial configurations are absent. No invented bounds or pilot measurements fill these fields.

The current workload source is hash-bound. STAT-03 must bind the actual dependency versions, environment assets, full fixed configuration, task identity and resource policy. It also owns V01's tabular task catalog/equivalence bands and the final protocol freeze. Having three environment names does not by itself establish a family-wide result or adequate bootstrap coverage.

## Budget and endpoint rules

One arm runs sequentially under the same resource allocation. Measured elapsed time includes searcher construction, model fitting, suggestion, evaluation and observation; it is **not active accelerator time**. Arm order rotates by optimizer-seed index before results are seen. The trial limit is a safety ceiling: reaching it before the time endpoint makes the study incomplete, not a matched-budget success.

Only evaluations completed by the declared budget count toward final objective. An evaluation crossing the endpoint is still charged in measured elapsed time, but cannot improve that endpoint. Overshoot beyond the predeclared limit, failures, lower-bound accounting and studies without an eligible final observation are missing. The runner does not retry or substitute seeds. The final outcome is the incumbent among completed full-fidelity evaluations; no scheduler or low-fidelity substitution is used in these method comparisons.

The proposed AUC grid is 101 fixed fractions from 0 to 1. At each fraction, take the incumbent available at that time, using the predeclared initial objective before the first observation. Convert to regret relative to the frozen reference and divide by the frozen scale span. Integrate by the left rectangle rule on this fixed grid. No interpolation uses future observations, and no observed extrema redefine the denominator. Regret is not clipped. All component improvements are oriented so positive is better.

## Missingness, inference and sizing

Every planned task/seed/arm is accounted for, including absent records. More than 10% missing in any arm voids the entry. Exclude a block from **every** component if any arm is missing. Exactly 10% is allowed. Do not apply the 10% rule to the union of different arms' missing blocks. Duplicate blocks, changed identities, wrong phase, nonfinite observations and altered initialization are invalid evidence.

Resample independent tasks, then paired study blocks within each selected task. Every component uses the same bootstrap indices. The estimand gives equal weight to tasks. Use 10,000 draws, entry p-value equal to the maximum component p-value, and Holm across the two entry p-values at family alpha .05. A separately analyzed entry retains the two-entry denominator (.025); the second Holm step needs both raw entries recomputed together. Candidate/synthetic and pilot reports remain INCONCLUSIVE even when a candidate numerical criterion clears.

The joint sizing implementation simulates the full conjunctive entry at conservative family alpha .025. It does not size each component separately at .80 and claim .80 joint power. It requires at least five complete independent pilot blocks per task, uses the predeclared planning alternative rather than the observed pilot effect, and reports joint power, Monte Carlo standard error and component interval coverage for each candidate count, capped at 20. Full planning uses 2,000 simulations and 10,000 bootstrap draws per simulation. Small fixture counts explicitly carry `engineering_fixture=true`.

**Scientific review needed:** the planning model uses Gaussian task/block effects, marginal upper-80% chi-square variance bounds, and empirical component correlations. Task-mean noise is retained conservatively; within-task variance uses the largest task-specific upper bound. These marginal bounds do not constitute a simultaneous covariance bound or prove coverage with few task clusters. The method and adequacy of the selected task count must be certified before interpreting a sizing receipt as evidence of power. Measured pilot execution remains PILOT-01, and CAP-01 owns final sizing/capacity.

## Resource request and certification boundary

For three tasks and the candidate five pilot seeds, the two entries require **90 complete studies**: 3 × 5 × (4 + 2). Each V05 study charges its five shared initial configurations; observations are not reused between arms or between entries. The proposed safety ceiling is 50 evaluations per study, not a prediction of completed evaluations. A resource request must sum the per-task study budget plus permitted overshoot over all 90 studies, then add separately measured orchestration overhead. Numerical hours, owner, allocation ID and the aggregate cap remain absent, so the pilot is not executable.

The command `python tools/verify_manifest.py validation/designs/tier0_candidate_v1.json --design-only` reports incompleteness. Without `--design-only`, it also requires accepted program prerequisites, current source identity, and hash-bound PI certification of this exact design and phase. Setting `status=certified` in a caller-supplied JSON file is insufficient. D5 in `validation/protocols.json` still requires: “PI certifies the final protocol set before any campaign spend.” D-PILOT-ORDER and a named resource envelope remain open.

STAT-02's candidate schema, analysis and sizing procedure are now implemented. Its deterministic mechanics tests initially passed 23 cases after correcting JSON list-to-tuple knob reconstruction. The broader review and verification receipt are recorded with VAL-01. STAT-03 keeps the scientific design freeze incomplete; no engineering completion waives those missing inputs.
