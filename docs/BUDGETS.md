# Admission and resource contracts

Pass `resource_budget=StudyBudget(...)` alongside a `StudyDeclaration` to budget
the declared endpoint workflow. For example, eight candidate configurations,
two seeds each, one final selection and two final seeds can use:

```python
from hponas import StudyBudget

resources = StudyBudget(
    configurations=8, work_unit='training_steps',
    tuning_work=160, final_work=20, max_work_per_call=10,
    worker_capacity=1, tuning_seconds=60, final_seconds=20,
    full_run_work=10,
)
```

Omit the old `budget`/`compute_budget_seconds` controls or give exactly matching
values. A configuration count is distinct from evaluations: folds, seeds and
promotions add calls. `work_unit` names actual incremental objective work;
`cost` retains the existing objective cost contract and is not silently
reinterpreted as training steps or GPU-hours. Scalar objectives return
`metadata={'resource': {'work': measured_work, 'unit': 'training_steps'}}`.
Vector studies use the existing named `work` meter with exactly the same
`work_unit`. The evaluation context supplies `work_limit` and `work_unit` so
the caller can enforce the declared maximum in its own training loop.

Each call reserves `max_work_per_call` before dispatch. On return, its measured
incremental work replaces the reservation, including unsuccessful calls. A
missing/wrong-unit/nonfinite meter or an amount above the bound fails the
measurement and stops further dispatch in that role. Lost attempts consume
the full reservation; their actual work remains unknown. Retrying consumes
another reservation. This bounds admission under the declared per-call work
contract; arbitrary objective code can violate that contract, which is detected
and reported, not physically prevented by this Python accounting layer.

Tuning and final work have independent pools. Admission checks that final work
can cover every declared final fold/seed for one scalar winner or the maximum
possible vector front (at most the configuration count). Tuning cannot spend
this reserve. Crashes/retries may exhaust it; final refusal remains a recorded
failure with no mean and no replacement selection. Additional retry headroom
is a caller resource choice. An explicit evaluation opt-out may reserve zero
final work; it cannot claim an evaluated result.

Elapsed seconds are summed measured call durations, not calendar time from
Study construction. Endpoint limits stop further dispatch after the cap; the
last call can overshoot and the report records this amount. Use an executor
deadline where a hard per-call time bound is needed. After a crash leaves
elapsed work unknown, a role with a time cap refuses further dispatch rather
than inventing a remaining allowance. The final time limit is independent.
Current declared repetitions execute serially; worker capacity constrains
admission and does not claim concurrent utilization.

`result.resources`/`study.resource_report()` retain both pools, attempt IDs,
measured and charged work, timing, lost work, breaches and admission evidence.
Full-run equivalents are reported only when `full_run_work` is explicitly
declared in the same units; with lost work the measured value is a lower
bound. It is a cost normalization, not a statistical guarantee or an assertion
that fidelity scales linearly. Resource checkpoints use schema 5 and reject
changed contracts, meters or capability declarations atomically.

Searchers expose an explicit `SearcherCapabilities` contract through `support`
and `capabilities`. Supported kinds and conditionals do not come from the
input space. Study checks kinds, conditions, vector constraints, partial
fidelity, concurrency, architecture-coordinate names and dimension limits
before dispatch. A prior requires its method's explicit law; `Knob.prior`
documentation is refused instead of silently interpreted or ignored. A claim
of prior-law support describes an available method, not evidence that a prior
is configured or useful. Coordinate NAS still requires the objective to build
and validate the corresponding models.

Random/Sobol and finite-prior search can consume partial observations.
PriorBand requires its matching scheduler. Bayesian vector methods filter
model fitting to their declared endpoint. Scalar GP/TPE/CMA-ES do not bind a
partial-fidelity model in this interface and refuse scheduled Study use.
Trust/cost/robust GP retain their sequential restrictions. Robust GP currently
refuses failed observations, so it cannot enter declared evaluation until
that behavior is implemented. No minimum of eight workers is imposed on
finite local population controllers; their separate contracts still apply.

Without a resource declaration, `resources.mode='legacy_controls'` reports the
old configuration/time limits and no final reserve or full-run normalization.
An undeclared custom searcher is allowed only on that legacy evaluation path,
with `legacy_unverified_capabilities`; declared studies require explicit support.
No method selection or scientific default is automatically changed.
