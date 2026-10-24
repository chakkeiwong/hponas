# Five-family application validation

This companion tests the public HPO-NAS API on five small, known-answer
models inspired by workspace projects. It has no sibling package, data,
service or environment dependency. The governing stage is APP-01 in
`CONSOLIDATED_MASTER_AUTHORITY.md`; `docs/program/program.json` owns status.
The detailed design is `design.json` and the reviewed program is
`docs/program/WORKSPACE_APPLICATION_VALIDATION_MASTER_2026_10_24.md`.

## Models and tuning tasks

| Family | Fitted model | Tuned coordinates | Independent reference |
|---|---|---|---|
| Forecast | Ridge covariates plus latent AR(1) filter, delayed and missing observations | Lag, ridge, observation variance | Joint Gaussian conditioning and augmented least squares |
| Wallet | Censored lognormal covariate model | Polynomial degree, ridge, noise scale | Scalar censored density, stationarity, quadrature and quantile inversion |
| Policy | Threshold policies evaluated by a train-only fitted doubly robust estimator | Threshold, time slope, transition smoothing | Finite trajectory enumeration and exact policy values |
| NAS | Trained neural value function and two derivatives | Width, depth, activation, learning rate | Analytic function, independent network/derivative evaluation, full finite grid |
| Transport | Trained triangular invertible neural shear | Width, depth, activation, learning rate | Exact target density/inverse/moments, independent HMC replay |

Each family uses three data replicates, four scalar searchers and sixteen
charged proposals per search. Training, tuning and final observations are
disjoint. The full finite grid supplies a reference after the design is
frozen; it is never supplied to the searcher. Final models refit on
training plus validation with fresh initialization seeds.

NAS also has three constrained vector studies and a separate momentum-SGD
streaming/recovery exercise. Transport tests nine sampler settings for
each of twelve selected maps. Finite numerical checks and posterior
assessment remain separate. No short-chain convergence claim is made.

## Operations

Run from `/home/ubuntu/workspace/hponas` using the exact commands in
`docs/PROGRAM_OPERATIONS.md`. The operational sequence is controls, forecast,
wallet, policy, nas, transport, verify, synthesis, audit; numerical
verification and master refresh occur at family boundaries.

To reconstruct existing artifacts without fitting:

```text
/home/ubuntu/workspace/hponas/program_operations/app_ops.py verify
```

The runner pins input hashes, uses one CPU and no GPU, enforces time, memory
and disk limits, and preserves immutable receipts and logs. Successful
family allocations cannot rerun automatically. New budgets, seeds, grids
or scientific tolerances require an explicitly reviewed successor design
and master amendment. Do not edit consumed evidence or remove a successful
receipt to force a repeat. The audit command is admitted at the active
APP-01 final-review stage; retained audit evidence is the completion record.

## Reading the evidence

`RESULTS.md` is the readable outcome report. The corresponding immutable
synthesis includes machine-readable `results.json`. Evidence lives under
`docs/program/evidence/2026-10-24/app-01/`. Each family result has:

- `design.json` and per-replicate `data.json` and `declaration.json`.
- `grid.json` plus raw fitted models for every finite configuration.
- Per-method summaries, reports, checkpoints, SQLite store and model payloads.
- An interrupted/resumed study with committed-work and selection checks.
- For NAS, vector finals and promoted optimizer checkpoints.
- For transport, fresh numerical checks and every HMC transition.

Failed attempts, repair reviews, numbered manifests and predecessor source
bytes are retained. NAS continuation copies earlier outputs with explicit
inheritance, avoiding refits of completed studies. Independent verification
checks copied payload identity and their original immutable references.

## Interpretation

Execution completion means the declared studies and objective checks are
complete. It does not imply every learned model meets its scientific goal.
Infeasible NAS finals, tuning/final ranking reversals and poor short-chain
moments remain results. Three data replicates do not establish universal
optimizer superiority. Deterministic repeated fits exercise the workflow
without increasing independent statistical information.

The existing LaTeX manual describes the accepted predecessor. This APP-01
extension is documented here, in its results and in the live master.
