# Installed caller model examples

`hponas.quickstart` ships in the wheel and needs only base package dependencies.
Its two objective classes are ordinary callers of public Study/Store APIs;
they do not inherit bank fixtures or import sibling projects, validation models,
private data or services. The source is [quickstart.py](../hponas/quickstart.py).

```bash
python -m hponas.quickstart --model hinge --output /tmp/hinge-study
python -m hponas.quickstart --model allocation --output /tmp/allocation-study
python -m hponas.quickstart --model hinge --output /tmp/hinge-study --resume
```

A new run requires an empty directory. Resuming requires an existing study and
the matching model. The output directory contains `study.sqlite`, its JSON
checkpoint projection, `report.json` and integrity-checked JSON model artifacts
under `models/`. Model publication is atomic; identical retries preserve bytes
and conflicting artifacts are refused. The directory and its parent are
caller-trusted. Move/copy recovery to other directory layouts is not promised.

| Model | Actual fit and search | Exact reference |
|---|---|---|
| `hinge` | Fit the output coefficients of a fixed-hidden-feature ReLU network by ridge regression; search hidden width 1 or 2 and ridge penalty 0 or 1. Width changes fitted parameter count and feature computation. | The generating function is `1 + 2 relu(x) - relu(x-1)`. Width 2 and ridge 0 recover coefficients `[1, 2, -1]`, with zero held-out squared loss up to floating-point error. Hidden weights are fixed. |
| `allocation` | Fit two nonnegative weights summing to one using projected-gradient steps; search step 1/8 or 1/4 and one or two updates. | Scenarios `[1,5,1,5]` have mean 3 and population variance 4. For first-asset weight `w`, loss is `2w²-3w`, so `w=3/4`, weights `[.75,.25]`, loss `-9/8`. Step 1/4 reaches it in one update. |

Each search uses four unscrambled Sobol proposals that cover its four legal
configurations exactly; integration tests verify that coverage. Tuning scores
use validation rows. Only after selection is frozen, final fitting uses
training plus validation rows and scores distinct final rows. Seeds `(0,1)`
and `(1000,1001)` are recorded as separate role identities. Fitting is
deterministic: repeated seeds do not supply independent stochastic information
or a statistical precision claim. Allocation roles have distinct row identities
but deliberately identical synthetic scenario values.

Work is measured in `row_visits_plus_fit_updates`: training rows plus scoring
rows plus one readout solve, or the allocation update count. The budget allows
four configurations, 160 tuning work units, 64 protected final units and a
16-unit maximum per call. Unacknowledged calls after interruption charge their
lost reservation in addition to newly measured work. Reports retain raw
repetitions, seed/fold roles, frozen selection, artifacts and resource totals.
Final measurements never train the searcher.

To adapt these examples, supply a plain callable accepting `config`, `seed`,
`evaluation` and `trial_id`. Fit only on `evaluation.fold.train_ids` and score
only `score_ids`; return `value`, model-path `artifacts` and measured work in
`metadata.resource`. Create a `StudyDeclaration` with stable model/data/protocol
identities and role-separated folds/seeds, then attach it and a `StudyBudget`
to `Study`. Make artifact writes idempotent under the provided `trial_id`.
[Evaluation](EVALUATION.md), [budgets](BUDGETS.md) and
[reports/adapters](REPORTS_AND_ADAPTERS.md) define the full contracts.

Independent tests enumerate every configuration and role using rational
Gaussian elimination or an exact scalar recurrence. They verify model reload,
work, final-role isolation and interruptions after artifact publication during
both tuning and final evaluation. Offline wheel checks run both CLI models
and completed resume outside the checkout on Python 3.12/3.13. This is finite
mathematical and workflow evidence. Empirical banking usefulness, general
optimizer superiority, posterior convergence and production readiness remain
unestablished. Changed-source scientific qualification and the final complete
audit belong to the remaining GAP-01 master phases.
