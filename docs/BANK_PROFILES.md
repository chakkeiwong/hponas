# Standalone bank-model workflows

The prediction examples exercise the public Study, LocalExecutor and SQLite
Store interfaces without sibling repositories or private data:

```text
python -m examples.bank_tuning --profile ridge --output-dir /tmp/bank-ridge
python -m examples.bank_tuning --profile ridge --output-dir /tmp/bank-ridge --resume
```

Other current profiles are `bernoulli`, `censored` and `ar`. Choose a fresh
output directory for a new study. Existing studies require explicit resume;
changing the declared model/data/evaluation identity is refused by checkpoint
recovery. Each run writes a complete `report.json`, `study.sqlite`, checkpoint
and one digest-bound JSON model artifact per committed evaluation call.

`causal` tunes cross-fitted outcome and propensity models on a finite structural
example. Its final assessment names the estimand and assumptions. The
`causal_overlap` and `causal_unidentified` variants retain a null point effect
and conservative bounds. Smoothing propensity estimates cannot establish
missing raw treatment support. Predictive losses remain reported separately
from identification. `final_assessments` in the returned result and CLI output
exposes these outcomes; they are also retained in final Store records and model
artifacts. These examples do not establish identification for observational
bank data.

`inference` evaluates a scalar linear-Gaussian filter against independent
sequences, using predictive likelihood to select a statistical observation
variance. Its final output explicitly leaves posterior convergence unassessed.
The separate `python -m examples.bank_inference_handoff` example holds a standard
normal target fixed, verifies each leapfrog configuration on development and
fresh states, and saves every verified pair. It checks the Metropolis correction
and keeps posterior R-hat/ESS/MCSE out of candidate selection. Affine-density
examples also verify inverse/Jacobian terms. These are finite numerical
contracts, with no posterior sampling campaign or BayesFilter dependency.

`solver` constructs small neural networks for the known ODE u'=2x, u(0)=0.
It returns a feasible Pareto front of residual loss and model size. Width,
depth, activation and representation change real model arrays or computations;
output regularization changes the fit. Each value/derivative/boundary constraint
must pass independently. Model size, conditioning and a scoped operation meter
are reported with the saved coefficients and layers. A random search may miss
every feasible model; an empty front remains an explicit incomplete outcome.
The default 8 trials are an illustration, and `--budget 32` remains a small
finite search rather than an effectiveness guarantee.

`nas_prediction` applies the same coordinate constructor to prediction of x².
It returns a front of prediction error and parameter count, with separate final
nodes and saved, reloadable arrays. `--budget 32` covers at most 32 proposals;
random proposals need not enumerate the entire 32-configuration domain. Both
neural profiles measure hidden affine operations explicitly; activations,
linear solves and device latency are outside that meter. Weight transfer
requires identical architecture coordinates, including representation size.

`valuation` fits a censored hazard before exact signed discounted cashflow
calculation. `valuation_unidentified` retains a working predictive likelihood
and refuses a point-identified NPV. `wallet` uses total censored-tail probability
and reports latent-mean bounds. `allocation` tunes mean shrinkage while solving
the two-asset QP exactly; `allocation_uncertain` reports robust utility and the
range of possible optimal weights under declared mean intervals. These outputs
retain their synthetic units and provide no empirical return guarantee.

The ridge profile fits preprocessing within each declared entity fold. The
Bernoulli profile uses proper log loss. The censored profile fits a geometric
hazard and retains survival likelihood from right-censored observations. AR
forecasting uses chronological folds, a declared information gap and only
features available before the forecast target. These are small deterministic
generators with independent mathematical answers, not empirical bank results.

Tuning and final evaluation have disjoint row/fold and seed roles. The one seed
per role records deterministic fitting; it provides no statistical precision
claim. Candidate selection uses only tuning means. Final evaluation refits on
its declared training rows and cannot update the searcher. Work is measured in
fit-plus-score rows, with separate final capacity and one uncertain-call reserve
per role. Interrupted work is charged honestly; it is not a free retry.

`workloads.bank_prediction.prediction_profile(name)` returns the configured
caller adapter. `make_study(directory, store)` exposes the ordinary public
study, while `run(directory, resume=True)` supports the maintained workflow.
`workloads.bank_workflow.load_artifact(path, profile=..., config=...)` verifies
artifact schema, bytes and identities. `workloads.bank_prediction.predict`
reconstructs predictions from saved fitted parameters. Actual sampled losses,
failures, artifacts and measured work remain in the Store report.

Current evidence includes finite mathematical and configured-workflow
verification for all declared bank families, fresh offline Python 3.12/3.13
installation and the final exact-source scientific qualification package
linked from the master. These examples do not qualify production
bank deployment or establish which optimizer works best on real applications.
