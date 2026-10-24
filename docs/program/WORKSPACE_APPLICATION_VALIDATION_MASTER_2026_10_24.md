# APP-01: five-problem application validation master

## Authority and goal

The user authorizes creation, review and execution of this extension on
24 October 2026. Revision 2.526, commit e82060bb5, is the completed predecessor.
The governing authority remains CONSOLIDATED_MASTER_AUTHORITY.md and the
dependency/evidence register remains docs/program/program.json. This extension
tests usefulness and correct orchestration on five independent stylized models.
It does not claim authentic bank effectiveness, unrestricted topology search,
posterior convergence or production readiness. One inspector/editor works
serially. Sibling repositories provide read-only contracts, never dependencies.

## Scientific design

Each family has three prospectively fixed data replicates, disjoint training,
tuning and final observations, finite configuration enumeration and charged
search evaluations. Random, Sobol, GP and TPE are compared where scalar
selection is appropriate; constrained NAS additionally uses the public vector
workflow. Equal proposal budgets are accompanied by measured work and elapsed
time, including reference cost and search overhead. Duplicate proposals are
charged. Initializations are paired across configurations; final fits use new
seeds. Enumeration is a finite tuning reference, not knowledge supplied to the
searcher. Statistical performance is descriptive; three replicates cannot
establish universal superiority. Exact identities and finite enumerations can
establish their stated finite claims.

1. **Forecasting.** A stationary autoregression with delayed auxiliary and
   missing observations. Tune lag order, ridge regularization and observation
   variance. Fit only past data; score sequential prediction likelihoods.
   Verify with independently assembled joint Gaussian conditioning and an
   independent ridge solve. All-missing steps are prediction-only.
2. **Censored wallets.** External wallet W=max(exp(Z)-1,0), Gaussian Z with
   covariate-dependent mean. Tune feature degree, regularization and noise
   scale. Verify censored likelihood, zero mass, means, quantiles and gradients
   against scalar formulas/quadrature; retain support and fit failures.
3. **Sequential servicing.** A small finite-state, finite-horizon controlled
   process with known logging probabilities. Tune threshold policies and
   transition-estimator smoothing using validation off-policy value. Exact
   dynamic programming and separate trajectory enumeration supply policy
   values. Unknown optimal value, overlap failure and evaluation leakage are
   explicitly distinguished.
4. **Constrained NAS.** Train networks for an analytic value function and its
   state/parameter derivatives. Width, depth, activation and learning rate
   change actual trained models. Examine error/size fronts and separate
   derivative constraints; derive limits from a fixed-resolution interpolation
   reference and curvature bounds, never adjust them after seeing results.
   Exercise live learning curves, checkpoint promotion and interruption.
5. **Neural transport.** Learn triangular invertible neural maps for a
   transformed-Gaussian target with exact inverse/density/moments. Tune actual
   architecture/training coordinates on held-out likelihood, freeze selected
   maps and verify Jacobian-corrected HMC. Freshly verify a fixed small sampler
   candidate set, retain every numerically valid pair, and assess posterior
   discrepancies separately. R-hat/ESS/MCSE cannot rank tuning candidates.

Mathematical reconstruction tolerances come from float64 error scale,
conditioning and independent convergence checks. Learned-model adequacy and
optimizer superiority are not made prerequisites for declaring a study
executed. A negative or inconclusive outcome is retained; broken mechanics
must be repaired before progression.

## Ordered stages and completion evidence

| Stage | Deliverable and criterion | Dependency |
|---|---|---|
| APP-01/DESIGN | Frozen machine-readable design, resource manifest and skeptical review | DOC-01/FINAL-REVIEW |
| APP-01/REFERENCES | Five independent numerical references; negative and leakage controls pass | DESIGN |
| APP-01/FORECAST | Complete reference/search/final/recovery records and reconstruction | REFERENCES |
| APP-01/WALLET | Same, plus support and tail checks | FORECAST |
| APP-01/POLICY | Same, plus exact policy values and overlap refusals | WALLET |
| APP-01/NAS | Actual trained architecture searches, vector fronts and learning-curve recovery | POLICY |
| APP-01/TRANSPORT | Trained bijections, density checks and frozen sampler verification | NAS |
| APP-01/SYNTHESIS | Cross-family results, resource use, limitations and runnable guide | TRANSPORT |
| APP-01/FINAL-REVIEW | Independently reconstruct all results, adversarial controls and source bindings | SYNTHESIS |
| GAP-01/FINAL-AUDIT | Retained terminal master guard plus current extension closure | FINAL-REVIEW |

At every boundary retain results, repair demonstrated defects with successor
records, refresh the following bounded stage and continue. Do not overwrite
consumed allocations or silently rerun passing experiments. If core defects
appear, register source impact and requalification rather than inheriting
previous qualification. Companion changes stay separately identified.

## Resource and operation envelope

One CPU affinity, one numerical thread, no GPU/network/service/sibling imports.
Each family: at most 1,200 seconds; five-family fitting ceiling 6,000 seconds.
References, controls, reconstruction and reporting: 300 seconds per fixed
operation. These are ceilings, not expected runtime or permission to allocate
an unbounded campaign. Cap owned resident memory at 4 GiB and outputs at
256 MiB per family; require 2 GiB free disk. Exact operations and pinned input
manifests must exist before running. Actual managed approvals are grouped
only if required; no global rule changes. No deployment or separate-machine
test. Existing scientific qualification and historical evidence are immutable.

## Review requirements

Check identifiability and target definitions; causal ordering and leakage;
independent reference implementation; enumeration coverage; honest work
accounting; actual changes in neural architecture; complete recovery state;
calibrated numerical versus scientific criteria; negative outcomes; fresh
sampler verification; final audit dependency coverage. Freeze the executable
design and source hashes before the first allocation.
