# Validation aligned with the research workspace

Date: 2026-10-05. Master amendment: 1.89. Owner: `STAT-03P` with
`VAL-01`, `WL-00`, `WL-01`, `T1-MF` and `T1-MO` for implementation.

## Decision and purpose

The user rejected the robot-control testing problem and requested tests based
on FinMarketing, MacroFinance and related workspace projects. The program's
goal remains reliable HPO and moderate architecture-coordinate NAS. Its
validation problem must change: demonstrate correct, useful tuning of these
research pipelines, with claims limited to the evidence actually collected.

The Brax/PPO pilot is on hold while its replacement is implemented. Asking for
892.4 search hours is no longer the next action. That lower bound describes
the old successful-sizing design, not a requirement of HPO-NAS. The combination
of expensive nested training, several conjunctive superiority claims and an
especially conservative power-planning rule created the cost. Changing the
scientific question is necessary; shortening PPO episodes alone is insufficient.

This is a prospective scope/claim redesign, not a cheaper replication of the
old V04-T0/V05 claim. Historical results, their assumptions and engineering
receipts remain intact. The executable release gate still requires the old
protocols until the explicit migration stage reconciles the registry,
validators, requirement dispositions and release consequences together. Nothing
in this document creates a scientific PASS or a release authorization.

## What the projects actually do

The inspected sources are local research code, not evidence that every route
in those projects is scientifically accepted.

| Project and concrete source | Existing work | Appropriate HPO-NAS workload |
|---|---|---|
| [FinMarketing response fitting](/home/ubuntu/workspace/FinMarketing/src/finmarketing/estimators/response.py:177), [independent fitting checks](/home/ubuntu/workspace/FinMarketing/tests/toolkit/estimators/test_response.py:34) | Penalized logistic response, explicit training/validation/test boundaries, log loss, Brier score, calibration and simple baselines | Tune penalty strength and mixture, then a small supported model-family space; minimize development log loss and report separate final prediction loss |
| [FinMarketing causal checks](/home/ubuntu/workspace/FinMarketing/tests/toolkit/causal/test_learners.py:26) | Cross-fitted nuisance models, independent least-squares reconstruction, known synthetic heterogeneous effects, overlap and leakage refusals | Tune supported nuisance regularization on separate folds; check effect recovery and policy value under a known synthetic law, without optimizing on evaluation truth |
| [MacroFinance affine checks](/home/ubuntu/workspace/MacroFinance/tests/test_one_country_affine_macro_phase8_bayesfilter_adapter.py:18) | Prediction-first Kalman likelihood, analytic scores, independent NumPy/reverse-mode/finite-difference checks | Verify the HPO objective adapter on a small fixed state-space problem; tune numerical solver settings while holding the statistical target fixed |
| [MacroFinance current tuning](/home/ubuntu/workspace/MacroFinance/one_country_affine_macro_option1_tuning.py:66) | BayesFilter owns HMC adaptation, mass updates, candidate selection and sampling; a finite leapfrog grid already exists | An optional external HPO adapter for explicitly supported numerical settings; compare with the native tuner and simple grid, including total tuning cost |
| [dsge_hmc neural training](/home/ubuntu/workspace/dsge_hmc/main-baseline/tests/numerics/test_rotemberg_public_training.py:75), [analytic equilibrium fixture](/home/ubuntu/workspace/dsge_hmc/main-baseline/tests/fixtures/neural_solver_verification_linear.py:107) | Small neural architectures, residual/derivative tasks, structural constraints, analytic policy and derivative references | Tune width/depth, learning rate and batch size on a small manufactured equilibrium before a bounded native neural-solver case |

There is no reason to put another optimizer around a native tuner unless it
adds a useful capability. Estimating economic parameters is the inner model's
job. Economic equations, observations, likelihood, prior and posterior target
are not knobs to change to make a tuning score look better.

## The replacement suite

### 1. Fast mathematical and engineering checks

Retain current reference parity, recovery, cancellation, accounting and space
contracts. Add adapter checks against independent objectives: closed-form
response intercepts, ridge/least-squares solutions, Kalman likelihoods and
gradients, and analytic equilibrium policies. Derive numeric tolerances from
roundoff, conditioning, truncation error and reference accuracy; report those
bounds. Do not impose an arbitrary percentage improvement as correctness.

Use small enumerated domains where appropriate. If all K configurations have
been evaluated, the minimum is known on that finite domain. For minimization,
report development simple regret
`r(B) = min(loss of configurations visited by budget B) - min(all K losses)`.
This is exact for the retained deterministic table (up to its numerical error),
not a population guarantee or a global optimum over an unenumerated space.
A budget smaller than K does not entitle GP, TPE, Sobol or random to zero regret.
Grid enumeration supplies a useful baseline and an adapter oracle.

Known defects must be detected: reversed objective direction, wrong parameter
transform, data leakage, omitted derivative paths, invalid configurations,
lost costs and infeasible selections. Existing tests cover many of these;
reuse them and add only meaningful missing adapter behavior checks.

### 2. Small domain integration problems

Use three core representatives across the existing phases. Start with W-FM
and the W-MF oracle; schedule native sampler and neural integration with their
capability owners. Add causal/allocation cases only when their adapters exist.

| ID | Search problem and initial finite scale | Objective and independent check | Baseline and claim boundary |
|---|---|---|---|
| W-FM | Native synthetic response; five penalty strengths by three penalty mixtures = 15 settings | Development log loss; independent reconstruction of predictions/loss, native KKT diagnostics; final log loss/Brier after search selection | Exhaustive grid, fixed/default fit, intercept, Sobol/random; GP/TPE only as measured alternatives. Synthetic prediction evidence, no bank ROI or causal claim |
| W-MF | Small linear-Gaussian likelihood adapter, followed by a fixed known Gaussian posterior; an initial step-size by leapfrog grid, e.g. three stable step sizes by L in {3, 5, 9} | Likelihood/score agreement with exact Kalman reference first; for the sampler, independent moment error and Monte Carlo error, bulk/tail ESS and total cost | Exact Gaussian solution, native BayesFilter tuner and grid. Select stable step sizes from the target's curvature before measurement; the exact posterior supplies a check, not a reason to use sampling in production |
| W-NAS | Manufactured equilibrium; e.g. three widths by two depths by two learning rates = 12 settings, all trained at full fidelity for the initial comparison | Independent states/parameters for residual and derivative accuracy, structural feasibility, policy error against analytic solution, total cost and parameter count | Analytic/polynomial or perturbation solution, native default architecture, grid and Sobol. Small architecture search only; no topology/supernet claim |

For W-NAS, a low residual on training collocation points alone is insufficient.
Use separate validation and final state/parameter sets, tail/boundary cases,
the independent equilibrium operator and derivative checks. On a contraction
problem, a uniform residual bound epsilon and contraction modulus q give
policy error at most epsilon/(1-q); sampled maxima are not uniform bounds
without an additional argument. On a general DSGE problem, do not assume this
theorem applies. Transfer to a native model only after the manufactured case.

For later HMC work, use a known Gaussian posterior first, then a small native
BayesFilter case. Tune step size, leapfrog count or a supported mass/transport
policy without changing the target or correction. Freeze adaptation and
exclude warmup from final draws. Assess independent retained runs with known
moments, Monte Carlo error, bulk/tail ESS and appropriate chain diagnostics.
Do not maximize acceptance probability alone or interpret a short chain's ESS
as proof of correct inference. The native tuner is a baseline, not a component
to bypass. Total cost includes preparation, failed candidates and verification.

For later causal work, use known synthetic effects for evaluation only,
cross-fitting for nuisance selection and explicit overlap checks. For decision
allocation, verify feasibility/accounting and compare with the exact finite
LP/MILP/brute-force solution. Do not use HPO to solve a problem already handled
better by a direct optimizer.

### 3. Performance evidence proportional to the claim

Separate three questions:

1. Is the implementation correct? Independent oracles and behavioral checks.
2. Does the complete pipeline solve the stated finite task correctly? Retained
   search traces, separate final evaluation and domain accuracy/feasibility.
3. Is a particular search method better under a stated workload distribution
   and budget? This needs independent replication and uncertainty; the first
   two answers do not imply it.

Begin with development diagnostics and publish all losses, failures, regret
curves and costs. A method may lose to a simple baseline. Report that result;
retain the cheaper baseline as the recommendation for that workload. Universal
GP/TPE superiority is not a prerequisite for a reliable HPO library. Likewise,
log-coordinate correctness is an engineering requirement; an empirical claim
that log warping improves every workload is a separate question.

For any later comparative claim, prospectively specify the task population (or
explicitly a finite suite), evaluation unit, metric, budget, failure treatment
and statistical family. Separate training/search randomness from independent
datasets or tasks. Use paired comparisons on shared data and budgets, with
separate final evaluation. A fixed collection of seeds does not by itself
support generalization to all projects. Do not treat correlated folds, trials
or time points as independent replications.

Use established fixed-sample paired inference when a fixed design suffices;
use a justified confidence sequence only when optional stopping is required.
Size from precision and the intended claim, not a required favorable outcome.
For bounded independent paired outcomes of range width W, Hoeffding gives the
sufficient fixed-sample bound `n >= W^2 log(2/alpha)/(2 h^2)` for half-width h.
It may be conservative and requires the stated independence/boundedness; raw
log loss is unbounded without a justified bound. No arbitrary clipping or
IID assumption is permitted to obtain a smaller n. Cluster/time-series data
need an appropriate design. Multiple advertised claims need family control.

No calculation can guarantee useful power for every arbitrarily small real
effect. If no scientific use requires a precise superiority conclusion, report
uncertainty and leave that claim unresolved instead of forcing a huge campaign.
Application tolerances should come from the model's error propagation or a
stated decision loss. Where those facts are unavailable, report a cost/error
frontier; do not ask a person to decide whether the science passed.

## Cost and sequence

The first diagnostic is prospectively bounded to one synthetic response
dataset, one search seed, four methods with 16 proposals each, the 15-setting
grid and an intercept fit: 80 fits maximum. Sixteen proposals exercise TPE
beyond its ten startup trials and GP beyond its five startup trials. Repeated
proposals consume budget and are reported. This diagnostic is not a powered
comparison or a sample-size recommendation. Final data are generated only
after every method's search trace has closed. It has a 180-second process cap,
one CPU thread and no GPU use. The script records native imported sources and
the HPO-NAS source identity. If it fails or times out, retain the partial files.

Measure fit cost and search overhead separately. For a prospective suite,
budget `sum(reference work + methods * replications * trials * fit cost
+ search overhead + final evaluation)` including failures. Cached finite
tables can test search mechanics cheaply, but their lookup timings cannot
substitute for native end-to-end performance. Measure native timing separately.

The 12-setting neural example is a starting finite domain, not a promise that
every fit takes seconds. Measure one bounded fit before planning a larger run.
Use multifidelity only where increasing fidelity has real semantics; compare
pruned and full-fidelity outcomes at a matched total cost. A staged cheap test
must not quietly replace the final task's scientific accuracy requirement.

The master sequence is:

| Stage | Work | Exit |
|---|---|---|
| `STAT-03P/WORKSPACE-DESIGN` | Inspect actual projects; replace the testing question; specify the layered suite | This documented mapping, claims, mathematical limits and migration sequence |
| `STAT-03P/WORKSPACE-DIAGNOSTIC` | Run the bounded native FinMarketing feasibility diagnostic | All search traces and separate final evaluations retained, timings/errors disclosed; no acceptance promotion |
| `STAT-03P/WORKSPACE-PROTOCOL-MIGRATION` | Implement W-FM/W-MF/W-NAS adapters, independent checks and small measurement runs; reconcile V04-T0/V05 and later protocol claims, requirements and release behavior | Objective correctness gates and scoped performance reporting are executable; obsolete PPO dependencies are explicitly retired; no gate bypass |
| Existing workload/method owners | Execute the new bounded suite, repair defects and refresh subsequent phases | Reconstructed finite-task results; any empirical claim separately supported; release prerequisites recomputed |

The migration must explicitly disposition old alpha/power/rank/pilot clauses
as belonging to the retired comparative claim. They are not transferred
mechanically onto mathematical conformance tests. Preserve the archived
contracts and results. Reconcile broader V06/V09/V13 and cost-aware tests with
the same research scope rather than repeating a global win requirement later.

The plan and diagnostic are part of the master program. The reason for changing
direction is the user's correction of the target use case, supported by the
actual project code. The master is incomplete. Protocol migration is internal
implementation work; the old allocation blocker does not justify stopping it.

## First measured diagnostic

The [native diagnostic](evidence/2026-10-05/workspace-validation-01/finmarketing_diagnostic.py)
completed with [retained results](evidence/2026-10-05/workspace-validation-01/run01/summary.json).
It used real FinMarketing fitting/evaluation and the public HPO-NAS Study API.
All 64 HPO trials completed; all 15 grid configurations were fitted; separate
final evaluation followed persisted selections. Independent reconstruction of
development log loss differed by at most 1.12e-16.

| Route | Fits/proposals | Distinct configurations | Elapsed seconds |
|---|---:|---:|---:|
| Exhaustive grid | 15 | 15 | 0.126 |
| Random | 16 | 9 | 0.231 |
| Sobol | 16 | 9 | 0.224 |
| GP | 16 | 4 | 5.615 |
| TPE | 16 | 7 | 0.249 |

The complete diagnostic including imports and final evaluation took 9.172
seconds on this host. GP spent 5.485 seconds outside objective fitting. This
illustrates why search overhead and a direct grid baseline belong in the
design. Duplicate proposals count as spent trials. These are measured times
for one small fixture, not timings for full MacroFinance or neural training,
and not a statistically established ordering of search methods. Differences
near numerical fitting precision are not advertised as meaningful effects.
The diagnostic belongs to development evidence; final confirmation must use
fresh data after the replacement protocols and implementations are fixed.
