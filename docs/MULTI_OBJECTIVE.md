# Multi-objective development API

`MultiObjectiveStudy` executes named objective vectors through the existing
executor and durable Study ledger. It returns a Pareto front and fixed
hypervolume, with no scalar "best". `ObjectiveSpec` binds two or three objective
names, each direction and finite domain bounds, named constraint upper bounds,
and the actual integer work unit before proposals. Normalization maps each
objective into minimization coordinates; the reference is always the declared
worst corner `(1, ..., 1)`. Out-of-domain or missing measurements fail explicitly.

The objective returns `objectives`, `constraints`, and incremental integer
`work`. Optional `cost` retains execution cost separately. Actual failed work
can be returned with `status="failed"` and both measurements set to `None`.
An unexpected exception has unknown operation work. Interrupted pending
evaluations also retain accounting uncertainty after retry. Their known work
is a lower bound; an exact work-budget curve is refused until all work is known.
Elapsed seconds remain separate from these counters.

Vectors, constraint measurements and outcomes, metric identity and pending
configurations live in the same JSON/SQLite snapshot as ordinary trial state.
Changed contracts, inconsistent vector history, mismatched vendor versions and
invalid scheduler replay are refused before replacing a live Study. Completed
work is not dispatched again. `Store.get_pareto_front` applies the bound
directions, constraint vetoes and full-fidelity endpoint to the authoritative
snapshot. Scalar Store queries cannot rank a vector study.

The maintained methods are:

| Method | Implementation and supported scope |
|---|---|
| `MultiObjectiveRandomSearcher` | Random baseline over the existing space schema; full vectors and failures retained. |
| `MultiObjectiveBayesSearcher(method="qlognehvi")` | Actual BoTorch qLogNEHVI, fitted objective/constraint GPs and a frozen reference. Unconditional continuous/ordinal coordinates. |
| `MultiObjectiveBayesSearcher(method="chebyshev")` | Fresh Dirichlet weights per proposal, augmented weighted Chebyshev scalarization against the ideal corner, all observations re-scalarized before fitting, actual constrained qLogEI. Same coordinate scope. |
| `WrappedNSGAIISearcher` | Actual Optuna NSGA-II, with constrained dominance and an exact ask/tell replay ledger; unconditional continuous, ordinal and categorical coordinates. Requires the Optuna extra. |

Bayesian acquisition uses a bounded sampled candidate set. Neither GP fitting,
posterior integration nor candidate maximization is claimed exact. Acquisition
errors propagate explicitly; there is no silent method substitution. Only
full-fidelity successful observations train the models/population. NSGA-II
keeps promoted roots pending until their endpoint; failed or finally unpromoted
roots close as failed vendor trials. Pending proposals and RNG position survive
recovery with the pinned vendors.

`MultiObjectiveScheduler` supports endpoint rung reports and resumable workload
checkpoints. It binds the same metric and constraint identities. Its default
`selection="advisory"` promotes all feasible configurations; absolute constraint
vetoes always stop a configuration. `selection="experimental_pareto"` explicitly
enables the existing Pareto/exclusive-hypervolume selection for development.
It is not V10 acceptance or an automatic default. A retained counterexample has
rank correlation above 0.94 while that selection discards the true optimum.
Streaming vector progress reports remain unsupported and are refused.

The reporting helpers `summarize_front` and `hypervolume_over_budget` now require
an explicit reference. `default_reference_point` is an exploratory utility and
does not establish a comparative metric. Three-objective hypervolume uses
disjoint coordinate slabs, eliminating the old exponential front-size limit;
duplicate points contribute volume once.

From the checkout, run a bounded fitted-network example:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m examples.multi_objective_tuning --method qlognehvi --output-dir /tmp/mo
```

The architecture identifier selects a subset of seven fixed ReLU knots. The
outputs are fitted by weighted least squares. Independent rational integration
gives the entire 128-architecture frontier. The declared error bound `1/128`
exceeds the analytic zero-hidden-unit error `5/768`, giving room for numerical
roundoff without deriving scales from observed results. Each unit of work is
one actual output-weight fit. Raw outcomes, constraints and checkpoints remain
in a unique run directory. This is implementation evidence; V09/V10, installed
wheel qualification and broader optimizer-performance claims remain open.
