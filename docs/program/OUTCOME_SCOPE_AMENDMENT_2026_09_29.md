# STAT-03/D–F: explicit outcome and scope amendment

**Status: reviewable proposal, not adopted.** This is preparation inside the master program. The accepted V04-T0/V05 raw-return claims and protocol register remain unchanged. The recommendation below changes what a successful experiment would establish; it cannot be activated by setting a method name or a certification flag. Revision 1.12 authority is preserved in `archive/program-2026-09-29/stat-03-before-outcome-amendment/`.

## Recommendation and its scientific cost

Offer a **paired win-probability claim on a named, independently selected finite task suite**, with raw returns, loss magnitudes and operational failures reported separately. Use final performance and the fraction of the budget during which the method delivers a better policy. This avoids inventing numerical return bounds, normalization anchors or a practical-effect threshold. It permits finite-sample inference and conservative treatment of missing outcomes. It does **not** establish higher expected raw return, lower raw-regret AUC, or superiority on an unspecified population of RL tasks.

This recommendation is appropriate only if the intended product claim is that an optimizer more reliably delivers the better result within a budget. If higher expected raw reward, including the magnitude of rare losses, is essential, retain that requirement and do not substitute this proposal. The current data and reward formulas do not supply defensible useful tail bounds for it. The exact counterexamples in `TASK_AND_INFERENCE_REVIEW_2026_09_29.md` explain why more resampling cannot solve that problem. A different bounded utility would also change the claim and would need scientifically defensible utility anchors; external 50M-step landscape extrema are unsuitable support bounds for our 100K-request recipe.

The tradeoff is substantial. A method gaining +1 in 19 of 20 cases and losing 1000 in the other case wins 95% of comparisons while its average raw improvement is −49.05. A regression explicitly prevents describing a rank-test success as mean superiority. Raw outcomes and failure severity remain mandatory reporting; rank superiority cannot discharge any existing safety obligation.

| Item | Accepted claim / current gap | Proposed replacement |
|---|---|---|
| Final endpoint | Mean range-normalized final objective; no useful support/tail justification | Mean paired win-minus-loss utility of independently evaluated, search-selected final policies |
| Anytime endpoint | Mean normalized regret AUC; initial score/reference/support unresolved | Left-rectangle integral of paired win-minus-loss utility on the existing fixed 101-point budget grid |
| Scope | Independent-task/family claim unsupported by three candidate names | Conditional on the named, frozen task suite, with equal task weights |
| Missing study | Whole-block exclusion, subject to 10% cap; selection bias remains possible | Retain all planned units; bound genuinely unknown outcomes adversely |
| Independent unit | Task/bootstrap interpretation not justified | One complete seed vector containing all tasks and paired arms; no flattening into tasks × seeds |
| Error policy | Eight-component V04 IUT, two-entry Holm, family .05 | Retained exactly; zero utility superiority null, not a user-selected percentage |
| Power | .80 at a justified positive planning alternative; no such alternative yet | Retained as an obligation. Exact sensitivity supplied; no invented alternative, no claim that a cap is powered |

Method identities remain GP+qLogEI and TPE against both log+Sobol and random, and the same GP with/without log coordinates. V05 retains identical physical initialization. Rank transformation is used for analysis only: searchers still receive their prescribed finite search objective, without test-seed feedback or an undisclosed transformed GP target.

## Endpoint definition

At each grid fraction g, select the highest **search-score** policy completed by gB, where B is the frozen measured search budget. Break exact ties by earliest completion. Do not select using future observations or protected test results. Freeze this entire incumbent schedule and checkpoint hashes before test evaluation. Evaluate each distinct selected policy once on its reserved protected episode seeds; reuse that evaluation wherever the same policy recurs. A later selected incumbent may have a worse protected score: do not take a maximum of the protected scores.

Let Y_a,t,s(g) be that policy's protected evaluation mean for arm a, task t and block s. A verified absence of a delivered policy is a separate ordered outcome, below every finite delivered policy. Define

    W_a,b,t,s(g) = +1 if candidate outranks comparator,
                   0 if they tie, including two absent policies,
                  −1 otherwise.

The final endpoint is W(1). The anytime endpoint is

    A = sum_j (g[j+1] − g[j]) W(g[j]).

Both lie in [−1,1] by definition. A corresponds to the method winning more often than losing at a budget interval sampled according to its duration. It is not the sign of a raw AUC difference. The first interval has no evaluated policies under this recipe, so on the current grid the largest fully observed anytime score is .99, not 1. Raw-return units and arbitrary external normalization are unnecessary for this ordinal comparison.

For component c, define X_s,c = mean_t W_t,s,c or mean_t A_t,s,c. The estimand is the average expectation of these **complete vector** outcomes over the fixed count of scheduled independent vectors, conditional on the frozen suite and execution recipe. Task effects can differ and tasks within a vector can be dependent. Distinct vectors must have independent random streams and execution noise under the declared experiment model. A common uncontrolled temporal shock or adaptive allocation can violate this model; seed labels alone do not establish independence. Arm order/resource isolation must be frozen and audited.

The resulting inference concerns noisy protected episode evaluation under the specified recipe, not the latent true policy return on infinitely many episodes. Episodes and adaptive trials are not additional study replicates.

## Failures, integrity and missingness

1. A method that stops retains every usable checkpoint delivered before it stopped. If its verified trace proves it delivered no usable policy by a grid point, record the no-policy outcome. No replacement seed, favorable retry or random-search fallback is inserted.
2. A test-evaluation failure does not become a successful subset of episodes. Preserve all planned episode slots; any nonfinite/missing episode makes that policy's test score unresolved under this conservative proposal. A separately justified reliability utility could classify some failures as no-policy, but is not silently assumed here.
3. An infrastructure loss, absent receipt or unresolved suffix is **unknown**, not an excluded study. For each component compute a feasible interval [L,U] over all completions. Both unknown gives [−1,1]; candidate absent against unknown gives [−1,0]; unknown against an absent comparator gives [0,1]. Preserve known prefixes. Average/integrate interval endpoints with the same fixed nonnegative weights.
4. Analyze the lower bounds for a superiority claim and report the full identified mean interval. Under the latent independent-vector model, L_s <= X_s pointwise. The bounded-mixture evidence is coordinatewise nondecreasing, so E(L) <= E(X). Thus its error guarantee remains conservative even when the missingness mechanism depends on outcomes or on other vectors. It does not require the missingness indicators themselves to be independent. This argument would not justify dropping rows or renormalizing the observed subset.
5. Duplicate/unplanned identities, altered hashes, wrong seeds, changed methods or false accounting are integrity failures. They are not an option to relabel adverse results as merely unknown. The previous 10% cap can remain an additional operational veto, but cannot be the justification for statistical validity. This proposal does not waive that veto.

`validation/tier0_rank_design.py` implements these interval operations and an explicitly nonaccepting preview. The full-family preview is currently a search-score engineering diagnostic. Its endpoints are labeled as such; protected curve evaluation is supplied separately for final integration. It retains every planned block, refuses duplicate/unplanned records and changed budgets, preserves all eight V04 components, and never reports an acceptance PASS.

## Inference, power and stopping

Use the previously proved fixed-count uniform mixture of product(1 + lambda X_s), lambda in [0,1], evaluated by deterministic quadrature. Average expectations may be heterogeneous. Component p is min(1,1/E), V04 entry p is the maximum of its eight component p-values, and Holm applies to the two entries at .05. An isolated entry retains .025. Confidence bounds at an entry's data-selected Holm threshold remain decision bounds, not simultaneous coverage of every component mean.

There is one confirmation analysis at its frozen count. The reserved replication seed pool is unused: its existence supplies neither spending authority nor another unadjusted test. No early success stopping is supported by the batch proof. A resource termination retains all planned missing slots and cannot be presented as a fully executed, adequately powered design. Any stronger sequential or repeated-testing rule would be a separate prospective amendment.

Exact binomial summation gives the following **conditional sensitivity of this particular test**. The artificial law makes every task in a vector agree and gives each component independent-across-vector outcomes ±a with win probability q. It assumes no ties/missingness. For anytime, a=.99 allows for the initial no-policy interval. Component dependence within a vector is unrestricted; the eight/nine-component figures use the sufficient union bound. They are neither actual PPO power nor universal lower limits on all possible valid tests.

| Independent vectors | Critical wins under this test | q for .80 power, single final component | q sufficient for .80 joint power, eight components (a=.99) |
|---|---|---|---|
| 5 | Cannot reject even with all wins | Unavailable | Unavailable |
| 10 | 10 | .977933 | .997471 |
| 20 | 17 | .882953 | .942666 |
| 60 | 42 | .738977 | .797424 |

At 20 vectors, a sufficient nine-component joint target across both entries needs q=.944694 in this model. The registered power policy is entry-specific; this extra row merely exposes the distinction between .80 per entry and .80 probability of both entries succeeding. The 60-vector row is sensitivity only: three tasks × 20 seeds do **not** create 60 vectors or authorize exceeding the 20-replicate cap.

These calculations are fast and require no bootstrap simulation or PPO training. They reveal that the candidate test can be conservative at the existing cap. They do not justify choosing q=.943 as a planning effect merely because it fits the cap. Search external comparable studies for a defensible alternative; if none exists, the correct report is a sensitivity curve and an unresolved .80-power obligation. Neither this agent nor the user can mathematically deduce an unknown actual advantage from a zero superiority threshold. Do not launch a pilot on the promise that it will manufacture that advantage. The external pilot, once certified, may estimate the prespecified nuisance/runtime quantities and test feasibility, but cannot select its own favorable effect target or task subset.

## Sampling and independent review procedure

The source audit now snapshots and hashes the installed Brax environment registry: **12 names**. This is a source frame, not a held-out sample. `fast` is diagnostic. Ant, HalfCheetah, Hopper, Humanoid and inverted_pendulum have known development/default/reference exposure and are not certified as fresh acceptance tasks. The other six names have unresolved exposure/backend/lineage review; absence of a matching local receipt is not proof of non-exposure. The three current candidate tasks remain a worked development/resource example, not a new holdout.

Freeze this procedure before method outcomes are consulted:

1. Enumerate every environment in the hash-bound source registry. Record backend support, fixed recipe, asset identities, source lineage and capability-specific exposure. Exclude `fast`; exclude any task developed against for a tested capability. Outcome performance, whether a method wins and observed variance are not eligibility filters. Complete missing exposure evidence before assigning eligibility.
2. An engineer independent of the capability implementation reviews those factual classifications, the final eligible frame and grouping. For a small explicitly finite suite, task independence is unnecessary for the vector inference, but lineage and scope still must be reported. No wider population inference follows from an independently selected subset.
3. Prespecify the intended count and any strata based on domain coverage, then commit the sorted eligible frame, selection algorithm and reviewer identity by hash. A concrete selection algorithm is: rank eligible IDs by SHA-256(secret 32-byte seed || NUL || UTF-8 task ID), break any exact collision lexicographically and take the prescribed count within each fixed stratum. The selector commits SHA-256(seed) before the method freeze and reveals the seed with the final task manifest. This is reproducible selection under a private random seed, not a proof of iid population sampling.
4. Freeze implementation before exposing acceptance outcomes. The independent selector/executor holds pilot task identities and method outcomes; return only the prespecified blinded feasibility/nuisance/resource receipt. Use disjoint confirmation seeds. If implementation changes in response to task-specific pilot performance, those tasks have become development data and require a fresh exposure disposition. A pilot is not a route for silently laundering development tasks into acceptance.
5. Reveal the selection, exposure ledger, exact task assets and allocation at the agreed gate and verify commitments. An independent role has not been appointed or simulated by an implementation agent. A transparent alternative needs explicit review against survey section 16; no claim of blinding is made without it.

This procedure is concrete, but the accepted holdout list is still empty. The agent owns catalog/exposure preparation; the user is not asked to nominate convenient task names.

## Protected evaluation repair and cost

Review found that `tier0_campaign.py`/`tier0_analysis.py` currently consume search returns for the comparison while `workloads/rl_routine.py` already offers `evaluate_checkpoint` for disjoint test episodes. Survey section 16 requires fixed tuning and disjoint test seeds. Selecting a favorable noisy incumbent and reusing its search score can reward noise. This is a separate VAL-01 repair under the existing program, regardless of whether the rank amendment is accepted.

`validation/tier0_protected_evaluation.py` now prepares a hash-bound incumbent plan from a complete search trace, selecting policies on search scores and ignoring over-budget improvements. It checks all episode seeds against the existing namespace, binds protected receipts to the exact plan/policy/seed, requires every planned episode slot, and reconstructs the search-selected curve without test-score reselection. This is executable preparation, not full campaign integration: the final runner must verify actual artifact bytes, evaluate trusted local checkpoints only, keep protected data out of search/replay feedback, persist the frozen plan before evaluation and handle incomplete traces under the reviewed failure contract.

The proposed protected namespace uses offsets [10000,100000) inside each existing 2^17 task/study slot. Training uses [0,10000); search evaluation starts at 100000. The exhaustive audit reserves **67,500 distinct protected episode seeds** across all 135 current task/phase/block slots and 50 possible policies × 10 episodes, disjoint from training and every actual search episode seed and below 2^32. Matching paired arms intentionally share corresponding seeds. Search windows overlap within an adaptive study; this does not create new independent studies. No seed pool was executed.

For T tasks, five pilot blocks require 30T studies. Confirmation requires T(4 n04 + 2 n05), with each n <= 20. The three-task illustration is **90 pilot studies** and at most **360 confirmation studies**. The GP arm cannot be reused across V04/V05 while their initialization recipes differ. Evaluate each distinct selected checkpoint once; with the 50-trial safety ceiling, protected evaluations are at most 4,500 policies/45,000 episodes for this illustrative pilot and 18,000 policies/180,000 episodes at the confirmation cap. These are ceilings, not predictions or allocations.

Cost is the sum of each study's frozen search budget and charged overshoot, **plus** measured protected evaluations, profiling, artifact verification and audit costs. The protected scoring stage is outside the search-selection budget and must be reported separately for both arms. Actual unique incumbents can be much fewer than trials or grid points. No assumed hourly rate, GPU reservation or speculative 20% multiplier fills the missing throughput. The project JAX installation still has no established GPU execution throughput; visible GPUs are not a cost measurement.

## V01/V02 preparation completed in this continuation

`validation/tabular_projection.py` closes the missing continuous-proposal-to-table mapping as an explicitly **projected finite benchmark**. It normalizes configuration coordinates only, uses a declared log coordinate for learning rate, selects the nearest recorded configuration, breaks exact ties by the lowest configuration ID and returns that recorded cell. Both wrapper and reference must use the same frozen projection. It preserves missing/nonfinite cells and has no training-time cost field. It does not interpolate rewards or pretend to run the original continuous PPO workload. All **1,024 physical configurations** across the four pinned external landscapes round-trip through this mapping without a physical-configuration mismatch. Unit counterexamples show that changing rewards cannot change the projection geometry or select a favorable tie.

The remaining V01 statistical issue is also explicit: failing to reject a KS equality null is not proof of equivalence. For one endpoint, a prospective two-sample DKW/union bound gives

    true CDF distance <= empirical CDF distance
                         + sqrt(log(4/gamma)/(2*n))
                         + sqrt(log(4/gamma)/(2*m))

with confidence at least 1−gamma under iid runs within each arm. Pairing across arms does not invalidate the union bound. At n=m=30 and illustrative gamma=.05, the added radius is about **.5405**. This is a conservative bound, not an adopted alpha allocation or a universal impossibility theorem. It cannot justify inventing an equivalence band of .55 merely to pass the cap.

The concrete V01 engineering recommendation is to compare **coupled traces under a frozen deterministic CPU recipe**: raw normalized proposals, selected table IDs, recorded outcomes/missing statuses and scheduler decisions against independent vendor paths. Exact identity of the table IDs/outcomes is testable without an arbitrary performance tolerance. This establishes conformance on the declared executed traces; do not describe it as proof of distributional equality for every possible seed. Its relationship to the accepted distributional-regression wording needs explicit protocol review. Final independent loops across all nine wrapper/reference components and held-out table selection remain VAL-01 obligations.

For V02, `v02-proposed-population.json` now freezes the actual **10,000 input cases**, generator hash, NumPy version, six event-kind counts, pinned reference hashes and eight named integration scenarios. No cases were selected for passing results. Its grammar covers bottom-rung ASHA in minimize mode; median/PASHA, higher-rung/runtime, Ray, crash and cancellation coverage remain explicit separate contracts. The input snapshot does not claim that 10,000 cases exhaust all asynchronous schedules or constitute a newly executed acceptance campaign. Final source/artifact binding and certification remain open.

Reproduce this preparation with `prepare_validator_contracts.py` in the STAT-03 evidence directory. `validator-preparation.json` binds both results. No HPO study or workload training was run.

## Remaining execution inside the master

STAT-03/D has produced a concrete alternative, failure policy and selection procedure. STAT-03/E has its exact conditional sensitivity and fixed stopping rule. Neither checkpoint is a final design freeze: adoption of the changed claim/scope, actual holdout selection, execution-independence evidence and a justified planning alternative remain unresolved.

Continue independent **STAT-03/F / VAL-01 preparation**: bind the prepared table mapping to full independent vendor loops, resolve the V01 claim/contract, complete V02's final integration bindings, and integrate protected evaluation plus resource accounting. These are existing master-program tasks. Complete the concrete phase protocol and costed profiling/pilot proposal before requesting D-PROTOCOL certification. The new `D-T0-OUTCOME-SCOPE` review concerns a substantive scientific claim change; it does not ask the user to choose a success threshold or pilot order. Acceptance and release remain blocked.

Reproduction: `env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /home/ubuntu/miniforge3/bin/python docs/program/evidence/2026-09-29/stat-03/review_outcome_amendment.py`. The receipt is `outcome-amendment-review.json`. This work used no workload evaluations, no Monte Carlo sizing and no GPU campaign.
