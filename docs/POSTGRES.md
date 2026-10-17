# PostgreSQL operations backend

The optional PostgreSQL backend has retained finite local qualification under
`OPS-01`; `PRD-01` verifies subsequent source changes. This is trusted supervised
local research, with no unattended-production or remote-host-loss claim. Install
`hponas[postgres]`. The reference environment uses PostgreSQL 14.24 and psycopg
3.2.10. Numerical dependencies and the default local Store are unchanged.

Use a private PostgreSQL database/schema controlled by its owner. An owner calls
`initialize_postgres(dsn, schema='hponas')` exactly once. Existing schemas,
changed tables/constraints and unknown versions are refused; there is no implicit
migration. Each process or thread creates its own `PostgresStore` connection.
Pass that instance as `store=` to a normal `Study` or `MultiObjectiveStudy`.
No SQLite file is shared with remote workers.

Every writer acquires a session advisory lock for its study. Another connection
can use `peek_study_snapshot` for monitoring, but cannot load or overwrite that
study until its coordinator closes or loses its database session. Reopening an
existing study requires `study.load_checkpoint()` before `run()`. Snapshots and
their study/trial/artifact projections commit atomically. Trial identities cannot
move between studies. A database error fences the connection; it never silently
reconnects or retries an ambiguous operation. These locks protect cooperating
clients; an administrator or a role with direct table-write privileges can bypass
the API. They do not kill work already running on a disconnected Ray worker.

`PostgresWorkLedger(dsn, allocation='...', capacity=..., unit='gradient_update')`
precharges physical work across processes and studies. Only `charge(...) is True`
permits an operation. False means that identity has already consumed capacity.
A crash after debit leaves uncertain consumption. `complete` is an acknowledgement
backed by durable execution evidence, not a refund. Fixed capacity/unit cannot be
changed by reopening the same allocation. Every retry that really executes new
work must pay again under a distinct attempt identity. All cooperating workers
must use the same authoritative allocation. The ledger does not meter arbitrary
Python work or enforce operating-system CPU/GPU/memory limits.

`postgres_status` reads consistent counts and work conservation. An uncertain
charge is reported as `uncertain_work_requires_reconciliation`; a restored
historical database reports `historical_restore_fenced`. The probe neither
creates an allocation nor acquires a study's coordinator lock. Connection errors
are reported without the connection string. Do not put credentials in metadata
or logs. Use PostgreSQL service files, a private password file or the deployment
secret manager rather than embedding secrets in scripts.

Close all Store and ledger clients before `backup_postgres`. A maintenance lock
refuses a live backup and blocks new cooperating connections during capture.
The backup includes all tables and copies every registered artifact under an
explicit `artifact_root`; missing files, escaping paths and symlinks are refused.
Declared Study snapshots register every committed tuning and final repetition's
artifact, including an unfinished repetition group. Snapshot serialization
preserves proposal/observation order; lexically sorted trial identifiers cannot
replace that order. Public report/evaluation/diagnostic queries do not acquire
the coordinator lock. An exported report is not a restart checkpoint.
Files must be immutable and writers quiescent. Keep the returned digest in an
independent evidence inventory. A failed backup has no valid terminal receipt
and must be retained for diagnosis. Defaults cap data at 64 MiB and 30 seconds;
larger deployments require a separately planned PostgreSQL physical/PITR policy.

`restore_postgres` verifies that retained digest, schema and artifact bytes before
creating a new schema atomically. Existing targets are refused. Restored records
can be inspected, but all study mutation, new allocations and budget admissions
are fenced. Artifact paths remain their original provenance, with copied files
listed in the backup manifest. Restoring an older budget cannot authorize more
work. This API intentionally has no resume switch: live disaster recovery requires
fencing the original deployment, reconciling every later debit/result, resolving
artifact locations and a separately verified recovery procedure. Same-database
restart recovers committed WAL normally; a lost historical suffix is different.

For a private trusted-research deployment, separate the schema owner, coordinator
and monitor roles. Grant the coordinator schema `USAGE`, table
`SELECT/INSERT/UPDATE/DELETE`, and sequence `USAGE/SELECT`; revoke all identity-table
writes and schema `CREATE`. The monitor receives only `USAGE` and `SELECT`.
Use SCRAM authentication and TLS with hostname/certificate verification for remote
connections, restrict network reachability and give Ray no public listener.
Untrusted train functions, hostile tenants, automatic failover, replicated storage,
multi-host load and availability guarantees remain unqualified. The local tests
exercise real PostgreSQL processes and role permissions; they cannot prove those
deployment properties.

The master retains completed local operations and REL-02 baseline evidence,
then continues through PRD-01 product repair and BANK-01 model-family workflows.
Changed-source verification is recorded separately from that exact-source
baseline. Arbitrary PITR, scheduled incremental backup, large-scale capacity,
application owner/collaborator/viewer policy, managed secrets, encryption at rest
and currency/GPU quotas remain unqualified deployment integrations.
