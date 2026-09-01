# Response: Statistical Protocol Review

**Date:** 2026-09-01
**Reviewed request:** [MEMO_TO_CODEX_STATISTICAL_REVIEW.md](MEMO_TO_CODEX_STATISTICAL_REVIEW.md)
**Primary source:** [hpo-survey/sections/16-validation.tex](hpo-survey/sections/16-validation.tex)
**Supporting sources:** [BUILD_PROGRAM_v2.md](BUILD_PROGRAM_v2.md), [RESPONSE_TO_CODEX_REVIEW.md](RESPONSE_TO_CODEX_REVIEW.md)

## Verdict

**RED: do not run confirmatory gate campaigns under the current protocol text.**

The chapter has the right overall instincts: preregistration, held-out tasks, explicit margins, cluster-level uncertainty, measured cost, and a non-default outcome for inconclusive evidence. However, several rules are not executable as written, and some current rules contradict corrections that were previously accepted. The problems are repairable before the campaign, but the document should not be signed off as statistically complete yet.

## Findings first

### F1. RED - The implemented chapter has drifted from accepted V01-V15 corrections

`RESPONSE_TO_CODEX_REVIEW.md` states that V09 would freeze normalization and use paired non-inferiority, V10 would use multiple seeds/tasks and gate on top-k recall and false-cull probability, and V13 would use simulation-based calibration, MCSE-aware comparisons, and automated mode diagnostics (lines 257-269). The current chapter instead:

- Uses CI overlap with the Chebyshev result as a V09 demotion rule (16-validation.tex, lines 223-227). Overlap of two marginal intervals is not a test of their difference, and the reference point/normalization is not frozen in the V09 protocol.
- Uses 100 configurations at one fixed seed and Spearman correlation alone for V10 (lines 439-452). A high rank correlation does not bound the probability of culling a future good or Pareto-optimal configuration.
- Relies on visual inspection and reinitialization for multimodality in V13 (lines 474-477), and compares posterior means within one standard error (lines 481-492), neither of which is a reproducible automated correctness criterion.

These are not merely wording differences: they change the estimand and the failure mode being tested. Reconcile the source chapter, the response commitments, and the generated register before any campaign manifest is signed.

### F2. RED - Confirmatory error control and sample-size rules are not reproducible

The text says that every entry has one primary endpoint at uncorrected alpha 0.05 and that only secondary endpoints receive Holm-Bonferroni correction (16-validation.tex, lines 309-327). It never defines the confirmatory family across the 15 entries, the gates, the two V04 components, or multiple comparator/budget looks. If all 15 primary nulls are true and treated as independent, uncorrected alpha 0.05 gives a family-wise false-positive probability of approximately `1 - 0.95^15 = 0.537`; even six entries in one gate give approximately 0.265.

Likewise, the power section says to estimate variance from a pilot and derive a repetition count, but does not specify the estimand, sidedness, variance estimator, allocation, minimum pilot size, or calculation method (lines 127-157). A future implementer cannot produce the same `n` from the document.

### F3. RED - V06 and V08 cannot be decided from the stated metrics

V06 calls queue wait and wall-clock part of the bill, then says the threshold follows accelerator-seconds (lines 200-215). Queue time has no accelerator-seconds unless it is converted to a separately defined billed-resource quantity. V08 calls a three-repetition ordering a demotion tripwire but provides no formal tie, effect, missing-run, or side-combination rule (lines 392-423). These ambiguities can change a gate result without changing the data.

## Summary of the eight requested items

| Item | Rating | Assessment |
|---|---|---|
| 1. Non-inferiority margins | Yellow | Direction and product meaning are not pinned; the current symmetric rule is equivalence, not ordinary one-sided non-inferiority. |
| 2. Power and sample size | Red | No reproducible calculation or operational consequence for an inconclusive result. |
| 3. Hierarchical bootstrap | Red | Pairing, task-level inference, adaptive configurations, and fallback rules are under-specified. |
| 4. Development vs acceptance tasks | Yellow | The separation is sound, but selection and rotation are not independently reproducible. |
| 5. Multiple comparisons | Red | Primary endpoints and repeated looks are not controlled as a confirmatory family. |
| 6. V06 cost accounting | Red | Units, overhead attribution, and uncertainty for the cost ratio are inconsistent. |
| 7. Artifact immutability | Red | Signature, key, canonicalization, large-object storage, and verification are unspecified. |
| 8. V08 release semantics | Red | The declared exception cannot produce pass, while hold is allowed to complete the tier without a funded expiry. |

## 1. Non-inferiority margins - Yellow

The proposed 5% V06 and 10% V11 margins cannot be judged from observed noise alone. They are product tolerances and need a domain justification: what change in return, regret, or recovery would alter the default recommendation? The memo correctly notes that the pilot cannot establish that choice (MEMO, lines 66-76).

The current test is a symmetric 95% interval for a difference lying wholly in `[-delta, +delta]` (16-validation.tex, lines 184-198). That is an equivalence-style criterion. If the claim is only that ASHA or a prior is not worse than a comparator, use a direction-normalized one-sided non-inferiority estimand. If both materially better and materially worse outcomes are excluded, call it equivalence and use a two-one-sided-test rule or an explicitly conservative confidence interval. The power calculation must use the same sidedness and alpha.

The percentage scale is also unsafe when the baseline objective is zero or negative, and it is ambiguous whether the denominator is a fixed pilot value or a noisy value estimated in the campaign. V11's phrase "recovery within noise" additionally needs a fixed endpoint and horizon: final value, area under regret, time to recover, or another predeclared statistic.

**Required amendment:** define a direction-normalized difference, a fixed baseline and scale, the decision margin justification, the exact one-sided/equivalence test, and this action rule: an inconclusive result keeps the capability non-default and permits at most a pre-budgeted replication; after that cap it becomes hold or opt-in/demote according to the entry's register.

## 2. Power and sample size - Red

The pilot-to-80%-power idea is appropriate as a planning framework, but the protocol is not executable (MEMO, lines 78-94; 16-validation.tex, lines 127-157):

- It does not state whether the calculation is paired or unpaired, one- or two-sided, mean- or curve-based, or based on absolute, relative, or transformed differences.
- A pilot of three repetitions per arm is a very noisy estimate of variance, especially with nested tasks, seeds, and adaptive HPO runs. Ten planned repetitions are explicitly only a heuristic, which is correct, but no conservative treatment of pilot variance uncertainty is given.
- There is no minimum pilot size, variance estimator, allocation rule, simulation procedure, or numeric maximum per entry.
- Alpha 0.05 is not reconciled with the multiplicity plan, and the text does not say whether pilot observations enter the confirmatory estimate.
- "Inconclusive at budgeted precision" means only that the capability does not become a default (lines 144-149); it does not say whether the gate holds, who funds an escalation, or when escalation ends.

**Suggested replacement:** preregister the estimand, design, alpha, margin, minimum pilot, variance estimator, maximum sample, and an algorithm (preferably simulation or a conservative upper confidence bound for pilot variance). Keep pilot and confirmatory data separate unless the analysis explicitly accounts for reuse. Add a decision tree: at the maximum sample, pass, fail/demote, or hold/non-default; any extra replication must have a fixed budget, owner, and stopping rule before the first result is seen. Select 80% versus 90% power based on the asymmetric cost of false promotion and false demotion, and document that choice.

## 3. Hierarchical bootstrap and pseudoreplication - Red

The chapter correctly identifies optimizer, workload, evaluation, task, and configuration levels (16-validation.tex, lines 240-251), and correctly rejects treating individual trials as independent. The actual resampling prescription is still incomplete (lines 253-272):

- In a paired comparison, the resampling unit must be a paired block containing the corresponding arms, task, and seed. Resampling tuning runs independently by arm destroys the covariance that pairing was meant to use.
- With one pinned task per workload family, a task-level bootstrap has one cluster and cannot estimate task-to-task variation. The claim must be limited to that task or the acceptance set must contain multiple independent tasks.
- Searcher configurations are adaptively selected and differ by arm. They are not iid observations that can be freely resampled or compared as common candidates. Use complete-study replicates, common random numbers where valid, and a prespecified aggregation statistic.
- "Fall back to unpaired if seed-level correlation breaks" is a post hoc switch unless "breaks" is defined before data collection. Missing or stopped trials also need an explicit estimand and censoring rule.
- Ten thousand bootstrap draws do not repair a cluster count of roughly ten, nor do they supply task-level generalization.

**Suggested replacement:** specify a cluster bootstrap algorithm that samples task clusters, then complete paired study blocks within task, retaining arm pairing; for unpaired designs, sample the same hierarchy independently. Do not resample individual trials. Freeze the pairing rule before data collection, state how failed/stopped runs contribute, and report the estimand as pinned-task or task-population inference according to the available number of tasks.

## 4. Development vs acceptance tasks - Yellow

The separation and the diagnostic use of the development/acceptance gap are sound (MEMO, lines 113-127; 16-validation.tex, lines 274-298). The selection mechanism is not yet reproducible:

- "Chosen by an engineer not implementing the capability" is a role separation, not a sampling design. The task universe, eligibility filters, stratification, random seed, and tie-breaking rule are absent.
- Revealing tasks at gate time protects blinding, but selecting them after implementation can still introduce discretion. Commit a hash or signed registry of the selection algorithm and candidate set before the implementation freeze; reveal the selected IDs later.
- Migrating old development tasks into acceptance for the next tier can leak tuning information into a later claim. A task used for development or acceptance must have a recorded exposure history, and prior acceptance results must not be silently recycled as new evidence.
- One task per family cannot support a broad workload-family claim. Either add independent tasks or narrow the claim to the pinned task.

**Required amendment:** create a versioned task registry with immutable task/data/seed hashes, an independent custodian, a precommitted selection rule, and a no-reuse policy for each claim. Record exactly when implementers, analysts, and reviewers gain access.

## 5. Multiple comparisons and endpoints - Red

Holm-Bonferroni is appropriate for a declared family of secondary tests, but correcting only secondary comparisons does not control the primary claims (16-validation.tex, lines 300-327). Specific gaps are:

- The 15 entry-level primaries are not assigned to a global family, per-gate families, or a hierarchical gatekeeping procedure.
- V04 has multiple searchers, tiers, tasks, and budget points. V09 has two comparators and a final hypervolume plus a curve. The text does not say whether success means beating both comparators, one comparator, or an intersection of tests.
- Choosing a budget point after inspecting a performance-over-budget curve is a multiple look. A final point and a curve band need a prespecified summary functional or simultaneous inference.
- V09's rule "demote if the interval overlaps" the Chebyshev interval is not a valid comparison of methods. Test the paired difference (or a prespecified non-inferiority/equivalence margin) directly, with the hypervolume normalization and reference point frozen before data.
- V13's many marginal diagnostics create their own multiplicity problem; a hard safety veto may be intentionally conservative, but that choice and its false-veto consequences must be stated.

**Suggested replacement:** define confirmatory families and alpha allocation before any gate, including whether the product-wide claim is controlled across gates. Use an intersection-union test when a method must beat both comparators, or adjust the family when either comparator suffices. Preselect one scalar endpoint or use simultaneous bands for curves; apply adjusted intervals to every decision-bearing secondary. Keep descriptive plots explicitly outside the decision path.

## 6. V06 cost accounting - Red

The protocol's intent to charge real user-facing overhead is good, but its quantities conflict (MEMO, lines 145-159; 16-validation.tex, lines 200-215):

- Accelerator-seconds, elapsed wall-clock, queue wait, CPU time, checkpoint I/O, and optimizer overhead are different quantities. Queue wait cannot be included in accelerator-seconds without a stated billing conversion.
- The text says both metrics are reported but the gate follows accelerator-seconds, even though the claim is that early stopping is "nearly free" for users. That can pass a run with low active GPU time but unacceptable queue or wall-clock cost.
- It does not define attribution of shared startup/queue time, retries, preemptions, failed trials, idle devices, heterogeneous hardware, or concurrency. The arms must be exposed to the same scheduling and accounting policy.
- The full-run-equivalent denominator is the mean cost of a baseline trial (lines 207-210), but uncertainty in that denominator is ignored. A point estimate of a one-third ratio is not enough for a gate.

**Suggested replacement:** preregister separate columns for active accelerator-seconds, billed resource-seconds/cost, CPU-seconds, storage/network overhead, and elapsed wall-clock/queue time. Choose one primary cost estimand that matches the product claim and keep the others secondary. Attribute shared overhead deterministically, include all allocated work and retries, and use a paired cluster bootstrap for the cost ratio. Pass only when the quality non-inferiority condition and the prespecified upper confidence bound for cost both clear their thresholds.

## 7. Immutable artifacts and preregistration - Red

The manifest contents are a strong start (16-validation.tex, lines 329-348), but "signed" and "immutable" are not operational definitions:

- No signature algorithm, key owner, public-key location, rotation/revocation procedure, or verification command is named. SHA-256 is an integrity digest, not an authenticity mechanism by itself.
- JSON canonicalization is unspecified, so equivalent key ordering or whitespace can produce different signatures/hashes.
- "Full dependency lock" needs to include exact package versions and hashes, channels/indexes, OS, Python, CUDA/driver, container/image digest, Ray cluster/runtime, and hardware topology where relevant.
- Git history is not immutable if force-pushed, and 10 GB checkpoints cannot be reliably governed by ordinary Git. The protocol provides no object-store URI, retention, backup, access, or deletion policy.
- The ordering between committing the analysis, creating/signing the manifest, starting the run, and embedding the manifest hash in results is not defined. Clock timezone and trusted timestamp are also absent.
- The text requires `validation/artifacts/`, but the repository currently has no schema or verification tool for the manifest/result pair.

**Suggested replacement:** use canonical JSON plus a named signature scheme and verification tool; sign an immutable commit/tag and the manifest; publish the verification key through a separate trusted channel; generate a machine-readable lock/SBOM; store large artifacts in a content-addressed, retention-controlled object store with the manifest URI and digest; and define an append-only reanalysis/version policy. Add a pre-run check that fails if the signed manifest, code commit, task registry, or lock cannot be verified.

## 8. V08 release semantics - Red

The chapter is honest that three repetitions cannot support a normal promotion claim, but the resulting state machine is not a usable gate (MEMO, lines 177-194; 16-validation.tex, lines 376-432):

- "All three repetitions agree in ordering" has no formal definition for ties, partial orders among three arms, missing runs, effect size, or the two sides of the worker boundary.
- The three-repetition exception can produce demote or hold, while pass is reachable only through a later full campaign (lines 409-423). The register nevertheless presents V08 as a Tier 2 gate, and Tier 2 completion explicitly accepts hold (lines 425-432). This means the campaign cannot make the flagship green at the declared gate.
- A consistent ordering in three noisy repetitions is not, by itself, evidence that the population method loses. The asymmetric demotion rationale does not quantify the false-demotion risk.
- "Home regime" and the role of the lower side of the eight-worker boundary are not defined. The fallback to whichever method won V07 is also undefined if V07 ties or is inconclusive.
- Hold has no owner, expiry, budget, or required follow-up. It can therefore leave an experimental capability indefinitely adjacent to a release decision.

**Suggested replacement:** make the 3-repetition run explicitly an exploratory tripwire. Predefine the exact arm/side ordering statistic, minimum loss margin, missing-data rule, and a conservative demotion trigger; do not call it promotion evidence. Define `pass`, `demote`, `hold`, and `implementation-fail` in the register, with a named owner, deadline, and budget for a powered follow-up. If hold is allowed to complete Tier 2, state that the capability ships only as opt-in, with an expiry and no default dispatch; otherwise make hold block the beta gate. A full powered campaign must be the only route to promotion.

## Protocol-specific gaps requiring explicit repair

### V10: correlation is not a safety guarantee

The one-seed, one-hundred-configuration design (16-validation.tex, lines 439-457) estimates association on a finite draw, not the operational error of early culling. It omits training-seed variability, task variability, and the probability of removing a configuration that would later be top-k or Pareto-optimal. Replace or supplement rho with preregistered top-k survivor recall, false-cull probability, regret, and out-of-sample validation across multiple seeds/tasks. Select the rung before acceptance data and keep the signal advisory unless all safety criteria pass.

### V13: correctness cannot rely on visual or one-standard-error checks

The absolute vetoes are appropriately conservative, but visual multimodality inspection and reinitialization after inspection (lines 459-477) are researcher degrees of freedom. A candidate mean within one standard error of a finite reference mean (lines 481-492) is also a weak agreement test and is not simultaneous across marginals. Add simulation-based calibration fixtures, automated mode/trace diagnostics, rank-normalized R-hat plus bulk/tail ESS, MCSE and interval-based comparisons, and a rule for multiple marginals. Freeze the reference posterior artifact before candidates are evaluated.

## Minimum amendments before a campaign

1. Reconcile the current chapter with the accepted V09, V10, V13, and repetition-unit commitments; regenerate the validation register.
2. Add one machine-readable protocol record per entry containing estimand, direction, comparator, primary endpoint, repetition unit, task/seed sets, margin, alpha/family, power method, maximum sample, missingness, stopping rule, and release consequence.
3. Freeze task and seed registries through a signed pre-run manifest and an independent selection procedure.
4. Define paired cluster resampling and the exact cost/quality statistics; run pilot simulations to check coverage and power under the observed hierarchy.
5. Freeze hypervolume normalization/reference point and all V10/V13 safety thresholds before acceptance data.
6. Specify artifact signing, key verification, lock contents, large-object storage, retention, and reanalysis versioning.
7. Resolve V08's state machine, follow-up funding, and whether hold blocks beta or permits time-limited opt-in only.
8. Obtain the intended level of sign-off. This review is a text-level engineering/statistical review, not credentialed external statistical certification.

## Decision and residual risk

**Decision:** protocol revision is required before confirmatory validation campaigns or a claim that the statistical reviewer gate is complete. Tier implementation and cheap harness work may proceed as engineering work, but the team should not spend the planned campaign budget against the current text.

The memo correctly limits this review's scope: pilot data are still needed to choose defensible margins and repetitions, and a human statistician may still be required for external scientific credibility (MEMO, lines 222-233). A future green review should be conditional on the amendments above plus a pilot report showing the planned estimators, coverage, power, and budget behavior.

## Status note

The memo says Tier 0 implementation is underway (lines 14-18), while the current repository progress tracker says Tier 0 is pending approval. Update that project status before assigning campaign dates; it does not change the statistical findings above.
