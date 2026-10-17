# Local operations

The supported application is trusted, supervised local research. A coordinator
owns each Study and its Store writes. SQLite uses a local filesystem; the
optional PostgreSQL backend supplies cooperating coordinator/worker fencing and
shared work accounting described in [POSTGRES.md](POSTGRES.md). The retained
baseline completed local qualification; PRD-01 verifies subsequent source
changes. Remote failover, hostile multi-user isolation and unattended production
service remain unqualified. The master identifies current work and exact-source
evidence; component completion does not close the whole product.

## Durable work limits

`hponas.operations.LocalWorkLedger(path, capacity=100, unit='gradient_update')`
admits cooperative integer work across local processes and studies. Call
`charge(event_id, study_id, units)` before the work. **Only a `True` return
permits physical execution.** `False` means the event already consumed its
allocation; it must never be redispatched. A conflicting event identity or
changed capacity/unit is refused. `WorkBudgetExceeded` refuses before dispatch.
Call `complete(event_id)` after the work and its required result have been saved.
Completion never refunds work or grants a second execution.

Use stable identities derived from study, trial, attempt and update. A failed
attempt that genuinely needs more physical work needs a new identity and pays
again. Do not invent a new identity simply to replay a completed event. A crash
between debit and completion conservatively leaves uncertain charged work.
An acknowledgement only resolves uncertainty when independent durable evidence
shows completion; otherwise retain that uncertainty. Do not delete or refund
the debit. The ledger cannot enforce an arbitrary unmetered objective, bound
Python/OS overhead or atomically commit an external operation with SQLite.
Study's trial count and elapsed-time controls remain distinct from this ledger.

Each process/thread opens its own ledger connection. All participating studies
must share the same authoritative database and unit. Local SQLite locks are
required; network filesystems, writable clones and multiple hosts are outside
this contract. A ledger backup is historical evidence: restoring an older
ledger and continuing dispatch would forget subsequent spending. Fence old
writers and reconcile all subsequent charges before recovery; if they cannot
be reconstructed, refuse new dispatch under that allocation.

## Backup and recovery

`backup_database(database, new_directory)` uses SQLite's online backup API,
checks integrity and records schema/version, table counts and a SHA-256 digest.
The closed backup uses rollback journaling so no untracked WAL file supplies
part of its state. A failed or timed-out backup with no valid manifest is
incomplete; retain it for diagnosis and create a new directory for another
attempt. The default backup/inventory time limits are 30 seconds each.

`restore_database(backup_directory, fresh_database)` verifies bytes and inventory
before publishing exclusively. It refuses an existing destination, backup
symlinks and journal sidecars. Use a private restore directory with no other
writers. An existing live Store is never a restore target. Keep the manifest
and its checksum in the separately retained evidence inventory; a colocated
digest detects accidental corruption, not malicious replacement of both files.
All APIs assume trusted local paths and filesystem ownership.

Both Stores index every committed declared tuning/final repetition's artifact,
including a partial repetition group. Final entries use a `final:` type prefix;
the complete workflow report provides explicit role, fold, seed and candidate
fields. This reporting projection never enters the search history.

The backup contains **only database contents**. Artifact/checkpoint URIs refer
to separate files. Quiesce writers for a coordinated application backup, retain
all referenced files and their original hashes, then bind both database and
artifact manifests. Verify artifact content, source/runtime, search space,
algorithm options and checkpoint compatibility before resuming. Do not run
garbage collection while a retained checkpoint/history still references a file.
There is no automatic artifact deletion or schema migration in this module.
Store's legacy version `0` is identified by its schema hash; that does not
qualify migration to a changed schema. Unsupported identities require a separately
tested prospective migration, never an implicit reset.

Open a fresh `Store`, construct the compatible `Study` and explicitly call
`study.load_checkpoint()` before `study.run()`. Study construction alone does
not restore state. A committed completed trial must not run again; pending
trials need objective-specific idempotency and work-ledger reconciliation.

## Observe and verify

Run `python -m tools.operations_status --database study.db --ledger work.db`.
It starts no workers and makes no logical database writes; SQLite may maintain
WAL read-coordination sidecars on a live WAL database. It returns nonzero for
uncertain consumption or errors. The probe checks integrity, not all possible
semantic defects or operating-system health. Do not put secrets in trial
metadata or exceptions; retained logs are visible to the local owner. Arbitrary
pickle/cloudpickle and model checkpoints must come from trusted producers.

`python -m examples.operations_known_answer --output-dir runs` runs three
four-update diagonal quadratic trials with exact recurrences. It saves raw
updates, restores the Store and Study checkpoint, and checks that all twelve
physical updates are charged exactly once. The minimum of this finite-horizon
loss over the declared interval is at learning rate 0.25. This is a mathematical
orchestration fixture; random suggestions need not find that endpoint.

The tests also kill a process after debit, race independent local connections
for a shared budget, restore a pending Sobol proposal and committed artifact
references, and refuse corrupt/redirected snapshots. The optional backend has
separate finite local concurrency/role evidence. Remote load, independent-host
loss, application role policy and unattended operation remain outside the
qualified scope. Local reports measure recorded work and elapsed seconds;
they do not imply GPU-hour or currency quotas.
