# Declared study evaluation

`StudyDeclaration` binds objective, model, data and protocol identities to a
scalar `Study` or `MultiObjectiveStudy`. Declare objective names, units and
directions, training/scoring folds, and tuning/final seeds before running.
Run `python -m examples.declared_tuning` for [a quadratic example](../examples/declared_tuning.py)
with a known minimum and no external data. It retains SQLite, checkpoint and
report files in a unique temporary directory. This development example does
not qualify the changed package scientifically.

Objectives explicitly accept `seed` and `evaluation`. The latter provides
`role` (`tuning` or `final`), the declared `fold`, and the declaration identity.
Use the fold to load data and fit all preprocessing and model parameters on
its training role only. Stable dataset versions/content digests are suitable
identifiers; private data need not enter the Store. The package checks declared
identities and transitions; it cannot inspect undeclared data access or prove
that arbitrary fitting code obeys the declaration.

Each candidate/fidelity runs every tuning fold/seed. The searcher receives one
arithmetic mean after all repetitions are recorded, with equal weight per fold
and seed even when folds differ in size. Any failed or cancelled repetition
invalidates the candidate; measurements are retained and charged, never dropped
from a mean. Vector objectives are averaged; each upper-bounded constraint
takes its maximum over repetitions, so every repetition must be feasible.

The durable phases are `tuning → selection_frozen → final_evaluation → reported`.
Selection uses the best eligible scalar tuning aggregate or the feasible
tuning Pareto front. Final measurements use fresh fits for each final fold,
disjoint scoring identities and seeds, and cannot change selection or enter
searcher history. Final repetitions use the selected fidelity, retained in
their records. A progressive scheduler can select below its configured maximum;
that does not establish full-fidelity performance.

`result.evaluation` and `study.evaluation_report()` expose the declaration,
selection, raw final records, means, sample standard deviations and counts.
Incomplete groups have no final mean. `status='reported'` means the workflow
ended; `outcome` separately says `completed`, `failed`, `infeasible` or
`no_selection`. Final failure/infeasibility also appears in Study and Store
status and never triggers another selection. Standard deviation describes the
fold/seed measurements; overlapping training folds are not independent
statistical replicates. The default two seeds establish no precision guarantee.

Study history and Store trial projections contain tuning aggregates whose
metadata retains raw tuning records. `store.read_evaluation(study_id)` returns
the separate persisted declaration/final state, rather than a formatted summary.
Application access control owns who may inspect final data. Cost and elapsed
totals include recorded final work. Unknown work lost before a record committed
remains explicitly a lower bound.

`rows` rejects train/score overlap. `grouped` additionally requires disjoint
entities, including final versus all tuning exposures. `temporal` requires
finite `train_until`, `score_from`, `score_until` and a nonnegative `gap`.
These denote information availability, including labels: scoring starts after
all training information plus the gap, and final scoring starts after all
tuning scoring information plus the gap. Final scoring rows/entities cannot
train another final fold. Nested evaluation of the entire selection procedure
requires separate studies and an appropriate outer design; this workflow
evaluates a selected model.

Declared checkpoints use schema 4 and refuse declaration/direction changes.
Each repetition commits before its aggregate. Restart skips committed work,
retries uncommitted work and records uncertainty without inventing lost cost.
File and Store recovery share validation; Store is authoritative when both
are configured. Resume with fresh searcher/executor objects, the same
declaration and `load_checkpoint(...)` before `run()`. Frozen selection cannot
reopen by changing the configuration budget. Changed protocols require a new
study that records prior exposure.

Endpoint Local execution (sync or async) and Ray Core commit repetitions serially.
Ray transport failures retain explicit uncertain-work records. With StudyBudget,
configure Ray with `max_retries=0` so recovery reserves each retry. See the
[report and adapter contract](REPORTS_AND_ADAPTERS.md).
For streaming, declare `streaming_steps=(...)` containing every scheduler
endpoint and any intermediate pruning barriers. The objective must accept
`reporter`, `checkpoint` and `resume_from`. Each call advances one repetition
to a barrier, returns its measurement and a JSON checkpoint, and reports the
assigned endpoint. The controller advances all fold/seed repetitions serially
before reporting their mean at that fidelity. Missing or failed repetitions
invalidate the candidate; the scheduler never receives a partial mean. A stop
at a complete barrier prevents all later training. Pause/promotion preserves
each repetition's checkpoint. Internal barrier calls always resume; promotions
respect the Study's restart/resume policy. Reports within a segment enforce
cancellation and time controls; scheduler decisions occur only at declared
barriers. Choosing coarse barriers limits pruning opportunities.

Scalar reports use `reporter(step, value, cost=..., checkpoint=..., metadata=...)`.
For a work budget, include `metadata={'resource': {'work': ..., 'unit': ...}}`
on reports and returns; work is cumulative within the current segment.
Vector reports use `reporter(step, objectives={...}, constraints={...}, work=...,
cost=..., checkpoint=...)`. Vector endpoint output uses the same named fields.
Each segment and acknowledged lost prefix remains in the durable ledger.
Unknown work consumes its full reservation, and final fitting starts fresh with
final folds/seeds. No final barrier is sent to search or scheduling.

Endpoint promotions support restart or per-repetition checkpoints; resumed
objectives explicitly accept `checkpoint` and `resume_from`. For separate final work reserves,
units and worker limits, use [StudyBudget](BUDGETS.md); its checkpoints use
schema 5 and bind both the evaluation and resource contracts.

Without `declaration`, construction requires a nonempty `legacy_reason` and
reports `legacy_unqualified`. The exact reason is persisted and must match on
recovery. Omitting both arguments or supplying both is refused before dispatch.
An exposed deterministic fixture can specify a nonempty `opt_out_reason`
and empty `final_folds`/`final_seeds`; its report says `opted_out`. Neither
path upgrades old evidence. Historical legacy snapshots without a reason need
an explicit migration with a retained predecessor, or execution on their
retained source; the loader cannot invent a reason. Crossing the declared/legacy
boundary requires a new study and is refused by the loader. Endpoint declaration
identities remain version 1; streaming declarations and their raw segment
ledgers use version 2 inside the ordinary Study checkpoint.
