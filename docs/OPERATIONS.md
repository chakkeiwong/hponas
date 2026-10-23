# Local operations

The supported application is trusted, supervised local research. A coordinator
owns each Study and its Store writes. SQLite uses a local filesystem; the
optional PostgreSQL backend supplies cooperating coordinator/worker fencing and
shared work accounting described in [POSTGRES.md](POSTGRES.md). The retained
baseline completed local qualification; GAP-01 verifies subsequent source
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
There is no automatic artifact deletion or schema migration in this snapshot module.
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
separate finite local concurrency/role evidence. The service below adds local
application policy and declared device/currency accounting. Remote load,
independent-host loss and unattended operation remain unqualified.

## Managed local Study service

`ManagedStudyService` adds transactional application policy, committed event
history and resource accounting over the actual SQLite Study tables. GAP-01
development verification passes; final current-source scientific qualification
is still pending. Open one connection per thread/process. The caller
authenticates principal names; the host, local files and caller adapters remain
trusted. Direct `Store` or filesystem access bypasses this application facade
and must be restricted by the host owner.

```python
from hponas import ManagedStudyService, restore_events

with ManagedStudyService.create("service.db", admin="operator") as service:
    service.project("operator", "forecast", owner="alice", event_id="project-1")
    service.grant("alice", "forecast", "reviewer", "viewer", event_id="viewer-1")
    study_store = service.store("alice", "forecast")
    # Pass study_store and study_name="forecast" to a declared public Study.
    # The viewer can inspect this study but cannot commit checkpoints.
    head = service.export_events("operator", "backup/events-1.json")

restore_events(["backup/events-1.json"], "recovered.db", expected_head=head["head"])
```

Creation and recovery refuse existing destinations. Owners can grant
collaborator/viewer roles; collaborators can write, viewers can read. Scoped
reads cannot switch projects, even for the service administrator. Access
denials commit a sanitized audit entry without a business mutation. Closing a
project refuses new writes/reservations while allowing completion accounting
for admitted work. Administrative exports/history can contain protected final
records and must never be supplied to a searcher.

`import_legacy_store(source, fresh_destination, backup_directory, admin=...)`
supports the exact legacy Store schema 0 to service schema 1.
`migrate_service(source, fresh_destination, backup_directory, actor=...)`
supports service schema 1 to 2. Quiesce the source before either offline
migration. Both preserve a verified predecessor backup and durable prepared
migration manifest before publishing the fresh destination. Unknown versions
are refused. `rollback_migration(manifest, fresh_destination, ...)` restores
the verified predecessor; retain the manifest digest independently when
replacement detection is required. Rollback must not resume a historical work
allocation without fencing/reconciliation.

`export_events(..., after_seq=N)` exports an ordered hash-linked incremental
segment. Start with `after_seq=0`, then use the previous segment's `end_seq`.
`restore_events` requires a complete ordered history from genesis, verifies all
supplied segments, and optionally selects an inclusive `through_sequence` or
`through_time_us` boundary. Supply `expected_head` from independent retained
evidence to detect truncation. This restores committed database state; external
artifact bytes and physical work require their own retained evidence.

Every event recovery copy starts with physical dispatch fenced, including
copies whose history contains a previous reconciliation. Before continuing,
fence old writers and reconcile all later reservations, then call
`acknowledge_recovery(..., evidence_id=..., writers_fenced=True,
later_reservations_reconciled=True)`. These booleans record an obligation; they
cannot prove that external work stopped. Uncertain work remains charged.

## Quotas, scheduling and encryption

`configure_quota` binds a subject, half-open microsecond accounting period,
device, active-study limit, currency code and immutable price version. Device
limits use integer microseconds; costs use integer micro-currency units and a
declared price per device hour, rounded up per reservation. `reserve` must
return **True** before execution; a repeated ID returns False and grants no
new work. `finish` records an actual measurement and unique measurement ID.
Failed/lost work retains the unused reservation as uncertainty. Actual overruns
are recorded and block later admission. `quota_report` separates measured,
uncertain and charged amounts. The caller supplies genuine device
measurements: CPU time is not GPU time, and framework overhead is separate.

`configure_schedule` and `tick` use an explicit clock, immutable intervals and
durable occurrence IDs. A tick handles at most 100 occurrences. Backups advance
their incremental cursor only after successful publication. Monitoring accepts
unit-labelled measured error rate, latency, queue depth and disk fraction;
`DirectoryAlertSink` publishes local alert files. No background daemon or
external notification is implied. Claimed/interrupted/uncertain effects block
automatic retry, preventing silent duplicate work or delivery; retain them for
explicit reconciliation. Key-provider and sink exception text is not retained.

With `hponas[security]`, supply `key_id` and a `BackupKeyProvider.get_key(key_id)`
that returns a 32-byte key to `export_events` or `tick`. AES-256-GCM authenticates
the artifact and its metadata. Recovery uses the same provider and fails on a
wrong key or altered artifact. Keep keys outside artifacts, metadata and logs.
This feature encrypts exported event backups; the live SQLite database and full
snapshot backups remain plaintext. Authentication, TLS and an external vault
are separate integrations.

The bounded capacity fixture measured 256 trials, eight studies and four local
workers on one CPU. It retains raw worker timing, objective-to-durable-checkpoint
latency, memory, accounting and a verified backup. It does not establish the
original 100 concurrent studies, 1,000 trials per study, 50 distributed workers
or production throughput/latency targets. See the operations stage's retained
review and measurement for exact source and run bindings.
