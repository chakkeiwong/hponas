# Cooperative worker admission

The PostgreSQL worker extension adds `store.coordinator_token(study_id)`. The
token identifies the owning server session and its start time; it contains no
credentials. A worker passes that token as `coordinator=` to every ledger charge
and completion. Workers and the coordinator use the same trusted runtime role
so the server exposes that role's session information. The database verifies
that the original session still holds the study's exclusive lock. PID reuse,
another study and a replacement coordinator cannot validate the old token.

A replacement owner invalidates later work admissions from the old worker.
An update admitted just before ownership loss can still finish: the durable
budget has already paid for it. With one outstanding update per worker, the
in-flight exposure is one prepaid update per worker. A lost acknowledgement
remains uncertain consumption. This is cooperative work fencing, not an
operating-system kill switch or a guarantee for unmetered objective code.

`python -m examples.postgres_known_answer --schema hponas --output-dir runs`
uses the connection profile in `HPONAS_POSTGRES_DSN`. The initialized schema must
be private. Add `--ray` for two Ray workers. Six four-update quadratic trials
produce 24 physical updates, check the exact power formula and resume completed
Study state without repeating training. Ray workers need the installed package,
the same private database profile and a shared output directory for this example.
The example's local files do not establish remote artifact storage readiness.

The native Study limits outstanding trials to its declared concurrency. The
example's two-worker cluster declares two CPU resources and a 100 MiB object
store in the integration harness. The tests retain saturation at 17 admitted
updates across four competing processes, stale worker refusal, a database
statement deadline, a database-session loss and an injected SQLSTATE `disk_full`
rollback. Injection verifies the transaction/error path without filling a shared
disk; physical storage exhaustion and network partition require the declared
deployment environment.

`python -m tools.postgres_status --schema hponas` returns zero for an intact
fully acknowledged state, one for uncertain work or a fenced historical restore,
and two for errors. It outputs no DSN. Configure the operator's monitoring system
to alert on nonzero status. Monitoring and a runbook are implemented; no unattended
production alert service or operator on-call ownership is inferred.

The [database runbook](POSTGRES.md) describes schema, roles, backup and restoration.
Its initial component evidence remains immutable. This supplement documents the
subsequent worker repair. The retained local lab includes explicit
TLS/authentication and role evidence. It does not establish remote independent-
host recovery or unattended production. Separate-machine testing remains
waived; it is not an outstanding local gate. Results remain finite evidence
on the named source and runtime, with changed-source verification owned by
the current master stage.
