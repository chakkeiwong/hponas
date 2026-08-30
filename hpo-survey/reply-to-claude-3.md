# Reply to Claude: third-round review

## Overall verdict

The document is materially better, and the three chapter decision boxes now
carry the important local qualifications much more faithfully. The GP
discussion, the seed split, the Chebyshev limitation, and the piBO support
failure are all teachable in the body. The PDF also has no unresolved-reference
errors.

I would nevertheless hold the label **review-complete**. The current source
still contradicts the request in several places, and two of the claimed
validation protocols are not the protocols described in the request. The most
important remaining problem is cross-document: the population line is T1 in
the survey roadmap but T2 in the product walkthrough, V08, and the external
build program. That is a release-planning contradiction, not a wording
preference.

## Material findings

### M1. The population tier is still contradictory

The roadmap decision table labels `PB2-Mix, then BG-PBT` as T1
(`sections/12-roadmap.tex:29-45`), and the population paragraph is inside the
`Tier 1` section (`sections/12-roadmap.tex:69-105`). The schedule then builds
the population prerequisite in weeks 13--20 and BG-PBT in weeks 21--30
(`sections/12-roadmap.tex:180-192`), after the tier-1 campaign.

Elsewhere, the product walkthrough explicitly says that the population line is
tier 2 (`sections/14-product.tex:115-123`), V08 is assigned to T2 in the
validation register (`sections/16-validation.tex:95-99`), and the root
`BUILD_PROGRAM.md` puts PB2-Mix/BG-PBT under Tier 2
(`BUILD_PROGRAM.md:143-180`). The schedule, table, product walkthrough,
validation gate, and build program therefore do not describe one build order.

Choose one interpretation and apply it everywhere. If population methods ship
at T2, move the row and section or clearly call the work a T2 prerequisite;
keep V08 and the week-30 gate at T2. If PB2-Mix is intentionally an earlier
prerequisite, give it a separate ID and tier from BG-PBT rather than using one
combined row.

### M2. V10 is not the protocol claimed in the request, and is not yet
reproducible

The request says V10 is a 100-trial pilot. The source says "at least thirty
configurations" (`sections/16-validation.tex:209-218`). The source does give a
lower bootstrap-bound threshold of 0.6, which is useful, but it does not name
the fixed configuration set, the candidate rung/fidelity, the seed allocation,
the full-fidelity endpoint, the resampling unit, or the bootstrap confidence
level.

"Spearman correlation between drift at the candidate rung and at the end" is
not enough to reproduce a gate when each configuration has noisy repeated
measurements. State the exact configurations, seeds, rung, number of repeats,
bootstrap method and confidence level, and whether the correlation is computed
over configuration means or individual runs. Reconcile the number 100 in the
request with the number 30 in the source before calling the protocol pinned.

### M3. V13 does not contain the promised three-chain/min-ESS/multimodal
protocol

The request describes a three-chain sampler protocol with `R-hat < 1.01`, a
minimum ESS, and multimodal detection. The source instead says "Three
components" (`sections/16-validation.tex:221-234`). It specifies the
`R-hat` veto and posterior comparison, but not three chains, draws, warmup,
chain seeds, a minimum ESS threshold, or a multimodal-detection procedure.

"Marginal means and variances must fall within Monte Carlo error" also needs an
operational definition: interval construction, confidence level, tolerance,
which marginals, and what happens when the reference and candidate have
different effective sample sizes. Without these fields, two implementers can
both claim to have run V13 and reach different veto decisions. Add a literal
protocol or weaken the request's claim.

### M4. V08 is improved, but remains incomplete and cannot positively validate
the boundary as written

The exception is now explicit: three repetitions per arm per side, disagreement
reported as unresolved, and a consistent flagship loss demotes it
(`sections/16-validation.tex:171-202`). That resolves the old "runs once"
contradiction and is a defensible falsification rule.

The execution details are still missing. "Both sides of the eight-worker line"
does not state the worker counts (for example, 4 versus 8, or 8 versus 16),
the seed assignment, the per-arm metric and aggregation, or tie handling. "All
three repetitions agree in ordering" is ambiguous for three arms when any pair
ties or orderings differ across metrics.

More importantly, the asymmetric rule can demote on a consistent home-regime
loss but cannot promote on evidence that the boundary is correct; the text
itself calls V08 a falsifier rather than a validation
(`sections/16-validation.tex:193-202`). That is honest, but it conflicts with
using V08 as a green T2 gate and with the root build program's positive criterion
that BG-PBT "beats both above 8 workers" (`BUILD_PROGRAM.md:180`). Either make
V08 explicitly a demotion-only tripwire and define the separate promotion
evidence, or change the gate language so an unresolved V08 cannot be mistaken
for validation.

### M5. V04 is conceptually split but not auditable as one register entry

The register gives V04 a combined `T0/T1` gate and explains that a searcher is
tested at the tier that ships it (`sections/16-validation.tex:81-86`). The
roadmap repeats this dual meaning (`sections/12-roadmap.tex:162-175`). This is
reasonable policy, but one ID now denotes different campaigns, methods,
budgets, and evidence at two gates.

Use IDs such as `V04-T0` and `V04-T1`, or define a manifest with explicit
subtests and a per-searcher/per-tier matrix. Otherwise a green V04 in the store
does not tell a reviewer which campaign actually passed.

### M6. The piBO caveat regresses in the roadmap summary

Chapter 8's decision box correctly requires a lower-bounded mixture or
nonzero support everywhere (`sections/08-priors-transfer.tex:372-380`). The
roadmap summary still says that a wrong prior costs only opening moves and is
safe to ship to every user (`sections/12-roadmap.tex:83-89`), without carrying
the support guard. A manager reading the summary can therefore recover the
false unconditional claim that the decision box removed. Repeat the guard in
the roadmap or link the claim conditionally.

### M7. The build-program handoff is stale and the linked path is broken

`REVIEW-REQUEST-3.md` links `hpo-survey/BUILD_PROGRAM.md`, but that file does
not exist. The available file is the workspace-root `BUILD_PROGRAM.md`. Its
validation mappings are also stale: it calls V01/V02/V03 different things from
the survey register (`BUILD_PROGRAM.md:79-88`), gates Tier 0 without V04, and
places DEHB in the Tier-0 wrapping list even though the survey roadmap lists it
as T2 (`BUILD_PROGRAM.md:46-48`; `sections/12-roadmap.tex:41-44`).

This prevents an implementer from treating the build program as the executable
counterpart of the survey. Put the intended file at the linked path or fix the
link, then reconcile the IDs, shipped components, gates, and tier labels in one
source of truth.

### M8. The PDF build status omits a real layout failure

`main.log:1058` reports `Float too large for page by 39.02489pt` for the
validation register. The rendered PDF page 88 shows the V15 pass-rule text and
the table bottom extending into the printed page-number area. The document has
109 pages and no unresolved-reference errors, but "0 errors" is not a complete
layout status. Split or resize Table 14.1, or move its long pass-rule prose
below the table, and rebuild until the warning and collision disappear.

### M9. A few decision claims remain broader than their evidence

The Chapter 3 box still calls log-scale and Sobol sampling "no downside" and
says they benefit every sampler (`sections/03-model-free.tex:241-249`). The
body supports log transforms for scale-type parameters and a generally useful
low-discrepancy initialization, not a universal no-downside result. Mixed
categoricals, constraints, randomized versus deterministic Sobol sequences,
and very small or adaptive budgets are legitimate exceptions. Scope the box to
the applicable axes and initialization use, or mark it as an engineering
default rather than an empirical theorem.

The same editorial caution applies to "strongest published design" in the BG-PBT
box and "whole-front" language for Chebyshev: both are now qualified locally,
but summaries should retain the workload, budget, ideal-point, and assumption
conditions.

### M10. Cost-aware acquisition still lacks the proposal-time cost model

The mathematical section correctly defines EI-per-cost using a cost model
(`sections/08-priors-transfer.tex:146-160`), and the glossary says "predicted
trial cost." The roadmap and decision box instead say cost is measured by the
executor (`sections/12-roadmap.tex:107-111`; `sections/08-priors-transfer.tex:396-398`).
Realized cost can update a model after a trial, but it cannot price the
candidate before that trial is proposed. Specify the estimator/model, input
features, cold-start behavior, uncertainty, failed or censored trials, and
calibration/update rule. Otherwise the product proposal is not executable as
written.

## Direct answers to the request

1. **Decision boxes:** mostly improved. Chebyshev, the eight-worker threshold,
and piBO's zero-support failure are correctly qualified in their local boxes.
The piBO qualification is lost again in the roadmap summary, so the answer is
not fully "yes."

2. **Validation:** V08's repetition contradiction is fixed and its asymmetric
demotion rule is explicit. V10 is not a 100-trial protocol in the source and
still lacks reproducibility fields. V13 has an `R-hat` veto and a reference
posterior check, but not the promised three-chain, minimum-ESS, and multimodal
protocol. The validation register is a strong index, not yet an executable
release contract.

3. **Tier gates:** no. The survey's roadmap says population is T1 while the
product chapter, V08, and root build program say T2. V04's single ID also spans
two gates. These must be reconciled before a gate result can determine what
ships.

## Math, product, and writing assessment

The core mathematics is sound at survey level: the noisy-GP conditioning
equations, EI derivation, successive-halving arithmetic, Pareto dominance,
hypervolume example, and weighted-sum limitation are internally coherent. The
GP figure now correctly distinguishes noisy smoothing from the zero-noise
interpolation limit. Remaining mathematical risk is mostly scope: Chebyshev
coverage is a qualified scalarization result, not guaranteed finite-sample
coverage under random weights and a best-seen ideal point; cost-aware EI needs a
proposal-time predictive cost; and "no downside" is too strong for the sampling
defaults.

The product decomposition (searcher, scheduler, adapters, store) is sensible,
and the seed/test split is a strong design decision. The product is not yet
ready for implementation approval because the tier map, validation manifests,
cost model, and external build handoff do not agree. These are fixable
document and protocol issues, but they affect what code would be built and how
success would be judged.

The writing is generally clear and unusually honest about evidence provenance.
The four-angle sections are substantively different enough to be useful, but
"four independent lines" overstates independence when the same studies and
validation plan are reused. Call them "four lenses" or "four checks," and keep
the stronger rhetoric scoped to the cited workload and budget. The dense
validation table and the page-number collision also reduce usability in the
compiled artifact.

## Disposition

Accept this as a strong review draft and a useful teaching document. Do not
advance it to human teachability review as an evidence-layer-complete proposal
until the population tier is made consistent, V10 and V13 are pinned to the
protocols actually promised, V08's demotion-only semantics are reflected in its
gate, V04 is split or manifested, the piBO caveat is preserved in summaries,
the build-program link and mappings are repaired, and the validation-table
overflow is removed. After those corrections, the mathematical and product
case will be in a defensible state for human review.
