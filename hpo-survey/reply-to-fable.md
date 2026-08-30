# Review for Fable

## Executive verdict

This is a strong, unusually traceable survey and a sensible product direction. The decomposition into searcher, scheduler, executor adapter, and run store is practical, and Ray Tune is a reasonable execution substrate. The core HPO presentation is generally correct and the document does a good job connecting literature claims to proposed interfaces and validation tests.

I would not approve implementation of the full proposal yet. Several issues affect scientific validity or make the promised product behavior impossible to reproduce. The most urgent are the seed protocol, predictive cost accounting, the under-specified validation gates, and contradictions about the PPO search space and mixed-space GP scope. These are document/protocol fixes, but they need to land before code and benchmarks are treated as evidence.

## Blocking findings

### 1. The objective declaration leaks the test set

`sections/14-product.tex:82-90` declares the optimization objective to be mean return on the test seeds, then says that candidates are evaluated on tuning seeds and only the winner is reported on disjoint test seeds. Those statements cannot both be true. If the searcher observes test-seed values, the test set is no longer held out; if it does not, it cannot optimize the declared objective directly.

The declaration should optimize a pre-declared tuning-seed estimator (for example, mean or a robust aggregate over fixed tuning seeds). After selection is frozen, the winner or Pareto front should be evaluated once on disjoint test seeds. The final report can call that quantity the test objective, but it must not be part of search feedback. The same rule must be explicit in the store schema, API, and validation harness.

### 2. EI-per-cost cannot use only realized executor cost

The acquisition in `sections/08-priors-transfer.tex:145-159` is selected before a trial runs, but the product decision in `sections/08-priors-transfer.tex:392-394` and `sections/12-roadmap.tex:107-111` says cost is measured by the executor rather than predicted. Realized cost is useful for fitting the next prediction; it cannot price the current candidate. This is an operational impossibility, not just an omitted implementation detail.

Specify either a deterministic cost estimator or a predictive cost model (including uncertainty, cold-start behavior, feature inputs, and update/calibration policy). Define what happens when no cost history exists, when a trial fails early, and when cost is censored by ASHA. The acquisition should use the predicted cost available at proposal time, while realized cost updates the model and the audit record.

### 3. The validation protocol is not reproducible enough to gate releases

`sections/16-validation.tex:72-113` gives useful test names, but most pass rules omit numerical tolerances, effect/non-inferiority margins, statistical tests, confidence levels, aggregation rules, and exact budgets. Examples include "within tolerance" (V01), "within noise" (V06 and V11), "must not lose" (V05), "with uncertainty" (V09), "passes the rank-correlation pilot" (V10), "enough studies" (V12), and "agreement with the reference posterior" (V13). These phrases cannot determine a demotion consistently.

`sections/16-validation.tex:121-127` also requires at least ten repetitions for every layer-two comparison, while `sections/16-validation.tex:159-165` says V08 runs once. V08 compares multiple methods on both sides of a worker boundary, so a single run is especially vulnerable to seed and scheduling noise. Define repetitions, fixed seeds, paired comparisons, stopping rules, uncertainty estimates, and a pre-registered pass threshold for every V01-V15. Resolve whether V08 is exempt, and justify that exemption if it remains.

### 4. The running PPO space is internally inconsistent

`sections/02-problem.tex:87-95` defines the BG-PBT PPO example as a 15-dimensional space: nine training knobs and six architecture knobs. The walkthrough at `sections/02-problem.tex:234-243` uses "soft updates off," and `sections/14-product.tex:69-75` adds a conditional soft-update temperature while still calling the schema fifteen-knob. PPO does not ordinarily have a target-network soft-update temperature, so this looks like a parameter imported from another algorithm.

Either remove the soft-update example, or name the actual supported conditional parameter and add it to the dimensionality, constraints, and cited source. The schema, figures, examples, and benchmark manifest must describe one identical space.

### 5. Mixed-space GP support is promised at incompatible milestones

`sections/04-bayesian.tex:683-705` correctly explains that categorical and ordinal variables require specialized kernels and trust-region/discrete optimization. However, `sections/11-architecture.tex:76-80` presents a day-one BoTorch GP/qLogEI proposal over the mixed PPO space, while `sections/12-roadmap.tex:53-60,178-184` schedules the mixed-space trust-region searcher later. Standard qLogEI alone does not make arbitrary conditional/categorical optimization work.

Choose and document a capability boundary. A coherent day-one plan would use TPE (or another mixed-space method) for the full conditional space and restrict the initial GP to supported continuous/encoded spaces. The later trust-region searcher can then unlock native mixed-space GP and BG-PBT. Add a negative capability test so unsupported spaces fail at declaration time rather than silently degrading.

### 6. The eight-worker boundary is presented as a hard law without matched evidence

`sections/06-population.tex:327-372` derives an "below roughly eight / above it" rule from studies with different budgets, populations, tasks, and evaluation protocols, then `sections/06-population.tex:467-472` turns eight workers into a universal product gate. The cited evidence supports a hypothesis about a regime, not a universal threshold. The document itself acknowledges the boundary is empirical at `sections/06-population.tex:504-511`.

Treat eight as a configurable dispatch heuristic or prior until V08 is fully repeated with matched total compute, worker counts on both sides, and schedule-shaped versus pointwise objectives. Report uncertainty around the crossover and allow an explicit override with an audit entry.

## Mathematical and technical assessment

The basic black-box objective, Gaussian-process conditioning equations, expected improvement intuition, ASHA mechanics, Pareto dominance, hypervolume, and weighted-sum limitation are sound at the level presented. The following claims need correction or qualification.

1. **Noisy GP figure contradicts the equations.** `sections/04-bayesian.tex:64-69,111-126` models nonzero observation noise and correctly says this produces smoothing. The figure caption at `sections/04-bayesian.tex:170-176` nevertheless says the mean interpolates observations and the variance collapses at observed points. For a latent GP with `sigma^2 > 0`, posterior variance at a training location is generally nonzero and the mean need not equal the noisy observation. The caption should say "near" or show the zero-noise special case. Also, after fitting hyperparameters by marginal likelihood, the variance depends indirectly on observed values through the fitted hyperparameters, contrary to the unconditional wording that it depends only on locations.

2. **Log-uniform decade count is wrong.** `sections/03-model-free.tex:110-120` says `[10^-5, 10^-2]` has four decades and allocates one quarter per decade. It spans three decades: `[10^-5,10^-4]`, `[10^-4,10^-3]`, and `[10^-3,10^-2]`; a log-uniform draw allocates one third to each. The separate claim that a linear-uniform draw puts about 90 percent above `10^-3` is correct.

3. **Chebyshev completeness is overstated.** `sections/07-multiobjective.tex:135-148` says sweeping positive weights reaches every Pareto point while using the "best seen" point as the ideal. The standard completeness statement needs an appropriate true/utopian ideal point, positive weights, and assumptions on the attainable set; a best-seen point can change the scalarized problem and does not guarantee recovery of every Pareto point. State this as a coverage advantage under assumptions, not a guarantee of the proposed implementation.

4. **The piBO safety claim ignores zero-support priors.** `sections/08-priors-transfer.tex:16-40` relies on `pi(config)^(beta/n)` tending to one, but that argument applies only where the prior is positive. A prior that is exactly zero permanently zeros the acquisition there, so a wrong prior may never be overruled. Require a lower-bounded prior or a uniform-mixture floor, and test recovery from a strongly wrong but nonzero prior.

5. **Constrained acquisition multiplication needs a modeling caveat.** `sections/07-multiobjective.tex:361-371` presents `EI * P(feasible)` as the usable value. It is exact only under an appropriate independence/factorization assumption (or as a chosen approximation); correlated objective and constraint posteriors require a joint treatment. State the assumption and expose the approximation in diagnostics.

6. **TPE's interaction limitation needs scoping.** `sections/04-bayesian.tex:529-583` describes TPE as factorized and blind to interactions, while `sections/10-libraries.tex:80-96` points to Optuna's multivariate TPE direction. Qualify the criticism as applying to classic/univariate TPE and specify which Optuna sampler/mode the product wraps.

7. **Sampler correctness vetoes need minimum statistical conditions.** `sections/09-workloads.tex:161-185` and `sections/16-validation.tex:34-41,105-107` use divergences, split R-hat, and reference-posterior agreement, but do not require minimum chains/draws or define the reference comparison. R-hat is unreliable with too few chains/draws and does not by itself detect multimodal mode omission. Specify chain count, draw count, warmup, thresholds, and a multimodal/reference diagnostic where applicable.

8. **Dynamic schedules are outside the formal objective.** `sections/02-problem.tex:246-337` formalizes a fixed configuration, while `sections/02-problem.tex:307-323` and `sections/06-population.tex:16-32` say PBT returns a schedule. Define the value of a schedule, its seed aggregation and test protocol, checkpoint lineage, and how it is compared fairly with a fixed configuration under equal compute.

## Product proposal and accounting

The architecture is the strongest part of the proposal: small searcher/scheduler interfaces, capability flags, a run store with curves and lineage, and Ray/local adapters are good boundaries. The contracts still need to be made implementable.

- `sections/15-contracts.tex:90-190` describes `report(trial, fidelity, value)` as scalar even though the product supports objective vectors, diagnostics, constraints, and vetoes. Define metric IDs, objective direction, vector shape, missing/failure semantics, timestamps, fidelity units and monotonicity, seed aggregation, idempotency, concurrency ordering, retries, and schema versioning.
- Define the hypervolume normalization and reference-point policy. A reference point that moves with the incumbent makes progress curves incomparable; a fixed, declared point can make a study infeasible if it is not dominated.
- Checkpoint surgery in `sections/15-contracts.tex:192-205` is not generally valid across architecture changes or optimizer-state shapes. Specify compatible-copy rules, reset behavior for incompatible state, distillation requirements, artifact/checkpoint versions, and the failure path.
- The run store says it records fitted cost models (`sections/11-architecture.tex:68-74`) but no model contract, feature schema, or calibration metrics are defined. This is the missing piece behind finding 2.
- The proposal's product scope and schedule disagree. `RELEASE_NOTES.md:17-19` asks for a tier-1 gate in about 12 weeks, while `sections/12-roadmap.tex:69-112,178-190` calls the population line tier 1 but schedules its prerequisite and flagship through week 30. Clarify whether "tier 1" means the first multi-objective/priors campaign or the complete population flagship.
- The compute bill is likely understated. V07 alone is estimated at 640 accelerator-hours in `sections/16-validation.tex:147-157`. V08 has several methods, two sides of the boundary, and should inherit the ten-repetition rule; the "runs once" description cannot support the "few GPU-weeks" total in `sections/16-validation.tex:181-191` and `sections/12-roadmap.tex:208-214`. Recalculate from an explicit manifest of methods, tasks, seeds, repetitions, fidelity, and failure/retry allowance.

## Writing and PDF quality

The linear teaching structure works. Equations are readable, figures are honestly labeled as schematic, and the decision boxes, glossary, audit ledger, and source anchors make the document unusually easy to audit. The PDF builds cleanly at 106 pages with no unresolved references or material LaTeX errors; the only log issue observed was a negligible 0.87 pt overfull vbox.

The main editorial risks are density and tone:

- The repeated "evidence / four angles / overturn clause" template makes a 106-page proposal feel longer than necessary. Consolidate repeated methodology prose and reserve the full template for decisions that actually differ.
- A decision box visibly splits across printed pages 53-54. Keep each box together where possible.
- The validation register on printed page 84 is dense and small. Move detailed protocols below the table or give the table more room.
- Scope rhetorical claims such as "strongest available," "best-maintained," "no downside," and "hard boundary" to the cited workload, budget, and evidence. Repeated phrases such as "charity," "smile," "regress has to stop," "embarrassingly strong," and "honest" give some passages an advocacy tone that is at odds with the otherwise careful review posture.

## Required revisions before approval

1. Correct the seed protocol and ensure test-seed values are unavailable to search and scheduler decisions.
2. Add a proposal-time predictive cost model or deterministic estimator, with cold-start, censoring, failure, and calibration rules.
3. Rewrite V01-V15 with exact repetitions, budgets, metrics, statistical thresholds, uncertainty reporting, and demotion actions; resolve V08's one-run exception.
4. Make the PPO search-space declaration, running example, citations, and dimensionality identical.
5. Separate day-one mixed-space capabilities from the later trust-region GP implementation and enforce capability checks.
6. Recast the eight-worker crossover as an empirically calibrated heuristic until V08 supports it.
7. Complete the objective, multi-objective reference-point, schedule, seed, and checkpoint contracts, including versioning and failure semantics.
8. Reconcile the tier labels, week-12 approval request, week-30 population campaign, and total compute estimates.
9. Apply the mathematical corrections and qualifications above, then perform one final PDF pass for split boxes, table legibility, and claim scope.

With those changes, the proposal would be a credible basis for a staged tier-0 build and a defensible tier-1 funding decision. In its current form, approve the survey as a review draft, but hold implementation approval for the protocol and contract revisions.
