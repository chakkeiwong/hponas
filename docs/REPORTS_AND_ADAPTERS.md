# Reports and executor contracts

`study.report()` returns a detached, complete workflow report.
`study.export_report(path)` writes strict JSON to a new file and refuses to
overwrite an existing report. SQLite and PostgreSQL provide the same
`read_report(study_id)` and `export_report(study_id, path)` queries.
PostgreSQL reporting reads committed snapshots without taking coordinator
ownership. Missing studies return None; exports require a stored snapshot.

Reports contain the declaration, frozen or provisional selection, every tuning
trial and result, raw tuning/final fold and seed records, vector measurements
and feasibility, progress curves, parent/root lineage, artifacts, scheduler
events, rung diagnostics, metric front and resource accounting. No constraint
or veto is reduced to an unexplained scalar. Declared final records are a
reporting surface; application access control must protect who can inspect
them. They do not feed the searcher or alter the frozen selection.

The tuning trajectory reports the incumbent or feasible front/hypervolume at
each observation commit with cumulative recorded cost, elapsed time and
measured work when available. Its time axis is the sum of evaluation elapsed
measurements, not parallel wall time. Failed work is included and incomplete
work is marked; a partial-fidelity score cannot become a full-fidelity
incumbent. Final evaluation never enters this tuning curve.

Artifacts remain caller-owned paths with role, candidate, repetition and
fold/seed identities. The report does not read remote URIs, relocate files,
load arbitrary model code, or prove an artifact's scientific validity. A model
adapter owns serialization, reload and compatibility checks. The declared
quadratic example writes tiny inspectable model JSON artifacts; bank model
profiles add their own artifact contracts.

Nonfinite measurements become JSON null with an explicit `nonfinite_values`
list of JSON pointers and original nan/+inf/-inf classifications. Failures
retain their status and raw error metadata. This report format is not a resume
checkpoint. Retain the authoritative checkpoint or Store snapshot and restore
it with matching code, searcher, objective and declaration. Event traces permit
supported schedule replay. Legacy reports explicitly lack qualified evaluation
roles and may lack work units. Cost is caller-reported cost or executor seconds;
it is not inferred to mean GPU-hours or currency. Resource meters use their
declared units; uncertain/lost work and missing elapsed values remain visible.

| Behavior | Public supported route and boundary |
|---|---|
| Submit and collect | `hponas.executors.LocalExecutor` and `RayExecutor` use the common Trial/Result evaluator; Study commits in dispatch order. Ray is a Core task/actor adapter. |
| Seed, fidelity and evaluation identity | Endpoint objectives receive explicit context. Declared fold/seed repetitions commit serially even with a concurrent executor; proposal batches do not imply parallel repetitions. |
| Stop and pause | Ordinary scalar streaming objectives use acknowledged `reporter` decisions. Cooperative pause/stop prevents later objective steps; endpoint objectives can only stop between calls. |
| Resume and checkpoints | Promotions carry explicit parent/root identities. Ordinary streams and declared endpoints support restart or per-evaluation/per-repetition checkpoints. Final declared refits restart. |
| Declared streaming | Explicitly unsupported: a declared objective accepting `reporter` refuses before dispatch. A legacy single stream cannot claim repeated protected evaluation. |
| Metered Ray retries | `StudyBudget` requires `max_retries=0` before dispatch. Each retry must reenter the durable reservation workflow through recovery. Hidden internal retries cannot consume unreserved work. |
| Ray infrastructure failure | A returned controller failure remains a failed repetition, with measured dispatch elapsed time and explicit work uncertainty. Missing work meters stop further metered dispatch; cancelled remainder records stay visible. |
| Unmetered Ray retry | Existing executor retries remain available. Declared repeated reports mark interrupted work uncertain; raw attempt counts survive. |
| Ownership | Executors shut down only owned local Ray services. Local controller regression and retained live-worker qualification are distinct evidence. |

The original Ray Tune wording is reconciled to these behavior contracts under
PRD-ADAPTER. `legacy_executors.py` retains a compatibility Tune path, while the
public package exports the Core adapter. Core evidence is not a claim that
Tune internals, searcher APIs, or checkpoint formats are interchangeable.
Remote host loss/partition and unattended production service remain unqualified;
the user's separate-machine test waiver remains in force.

The maintained `declared_tuning.py` uses protected final roles and model
artifacts. `finance_tuning.py` uses a declared vector workflow, 64 actual
gradient updates and an explicit deterministic-known-answer final opt-out.
Existing numerical/streaming examples retain their finite contract and report
legacy evaluation where they do not supply a declaration; they are not bank
application evidence. BANK-01 owns the complete configured bank profiles.
