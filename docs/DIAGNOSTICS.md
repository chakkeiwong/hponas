# Rung diagnostics

`study.rung_diagnostics()` and `store.read_rung_diagnostics(study_id)` expose
paired Spearman rank correlations between each lower scheduled fidelity and
the scheduler's declared `r_max`. PASHA's temporary cap is not `r_max`.
Without a scheduler, the report is explicitly not applicable. Older snapshots
without a declared rung grid or root lineage return an unavailable result.

The statistic is the Pearson correlation of **midranks** in the observed
paired subset. Exact ties share their average rank. With fewer than two pairs
or a constant rank vector, `spearman` is null with an explicit reason. Each row
includes raw values, ranks and source trial IDs, the metric's direction,
counts of roots and observations on each side, and excluded roots and reasons.
Vector objectives have separate rows; the internal scalar carrier is ignored.
Finite vector measurements include their recorded feasibility so the report
does not silently equate an observed objective with an admissible model.

Pairs use root trial identity and an unchanged configuration. A completed
endpoint or acknowledged streaming report supplies a lower-rung value.
Repeated training prefixes of restarted promotions do not create another
observation. Consistent duplicate reports have one rank; conflicting values
are excluded. Full fidelity requires a successfully completed tuning endpoint,
including the declared seed/fold aggregate when applicable. A last progress
report followed by failure cannot supply that endpoint. Failed, cancelled,
pruned, vetoed, pending and unmeasured outcomes remain explicit. There is no
imputation. Exclusion counts are per side, so a root missing both measurements
can appear in two reason counts while counting only once in `n_excluded`.

The protected final-evaluation ledger never supplies these measurements.
These are **descriptive correlations for observed pairs**. Selective pruning
can bias which pairs exist; the result cannot prove safe pruning, unbiased
performance over all candidates, or a scheduler recommendation. No inferential
p-value, confidence bound or automatic scheduler switch is implied.

Study checkpoints persist the derived report alongside the tuning ledger.
Queries reconstruct it and refuse a conflicting stored projection; restoration
also checks it before replacing live Study state. Older checkpoints can omit
this optional derived field and reconstruct it where their raw fields suffice.
The check detects inconsistent records, not malicious edits to both raw data
and its projection. SQLite and PostgreSQL Store reporting share this
reconstruction; PostgreSQL reporting does not acquire coordinator ownership.
