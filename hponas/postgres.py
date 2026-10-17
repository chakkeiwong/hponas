"""Optional PostgreSQL persistence for trusted, cooperating study coordinators.

Create a private schema explicitly with ``initialize_postgres``. Each thread or
process owns its connection. Session advisory locks serialize a study; separate
studies can commit concurrently. Connections never reconnect implicitly.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time

from hponas.operations import WorkBudgetExceeded, _identity, _integer
from hponas.store import Store, Study, Trial


class BackendUnavailable(RuntimeError):
    """Database state may be ambiguous; reconnect and reconcile before work."""


class CoordinatorBusy(RuntimeError):
    """A different live connection owns this study."""


class RecoveryRequired(RuntimeError):
    """A restored historical database cannot grant live dispatch authority."""


@dataclass(frozen=True)
class CoordinatorToken:
    """A server session identity for cooperative workers; contains no credentials."""

    study_id: str
    backend_pid: int
    backend_start: str


VERSION = 1
TABLES = {
    "identity": "singleton BOOLEAN PRIMARY KEY CHECK(singleton), version INTEGER NOT NULL, layout TEXT NOT NULL, contract TEXT NOT NULL, dispatch_enabled BOOLEAN NOT NULL",
    "studies": "study_id TEXT PRIMARY KEY, payload TEXT NOT NULL, ordinal BIGINT GENERATED ALWAYS AS IDENTITY",
    "snapshots": "study_id TEXT PRIMARY KEY REFERENCES studies(study_id), payload TEXT NOT NULL, revision BIGINT NOT NULL",
    "trials": "trial_id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(study_id), payload TEXT NOT NULL",
    "observations": "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES trials(trial_id), fidelity DOUBLE PRECISION NOT NULL, value DOUBLE PRECISION NOT NULL, observed_at DOUBLE PRECISION NOT NULL",
    "artifacts": "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, trial_id TEXT NOT NULL REFERENCES trials(trial_id), kind TEXT NOT NULL, path TEXT NOT NULL, metadata TEXT",
    "objectives": "trial_id TEXT PRIMARY KEY REFERENCES trials(trial_id), payload TEXT NOT NULL",
    "warm_history": "study_id TEXT PRIMARY KEY REFERENCES studies(study_id), payload TEXT NOT NULL",
    "budgets": "allocation TEXT PRIMARY KEY, capacity BIGINT NOT NULL CHECK(capacity>0), unit TEXT NOT NULL, spent BIGINT NOT NULL DEFAULT 0 CHECK(spent>=0 AND spent<=capacity)",
    "charges": "allocation TEXT NOT NULL REFERENCES budgets(allocation), event_id TEXT NOT NULL, study_id TEXT NOT NULL, units BIGINT NOT NULL CHECK(units>0), completed BOOLEAN NOT NULL DEFAULT FALSE, PRIMARY KEY(allocation,event_id)",
}


def _driver():
    try:
        import psycopg
    except ImportError:
        raise ImportError(
            "Install hponas[postgres] for the PostgreSQL backend"
        ) from None
    return psycopg


def _schema(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", value)
        or value in {"public", "information_schema"}
        or value.startswith("pg_")
    ):
        raise ValueError("Use a private lowercase PostgreSQL schema name")
    return value


def _key(schema, identity):
    return int.from_bytes(
        hashlib.sha256(("hponas:" + schema + ":" + identity).encode()).digest()[:8],
        "big",
        signed=True,
    )


def _json(value, *, sort_keys=True):
    # Native Study checkpoints retain NaN/Infinity for failed evaluations. The
    # text column stores the same Python JSON dialect as the local Store; it is
    # never executed or deserialized through pickle.
    return json.dumps(value, allow_nan=True, sort_keys=sort_keys, separators=(",", ":"))


def _layout(connection, schema):
    columns = connection.execute(
        "SELECT table_name,column_name,data_type,is_nullable,column_default,is_identity FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name,ordinal_position",
        (schema,),
    ).fetchall()
    constraints = connection.execute(
        "SELECT c.relname,p.contype,pg_get_constraintdef(p.oid) FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s ORDER BY c.relname,p.contype,pg_get_constraintdef(p.oid)",
        (schema,),
    ).fetchall()
    return hashlib.sha256(_json([columns, constraints]).encode()).hexdigest()


def _contract():
    return hashlib.sha256(_json(TABLES).encode()).hexdigest()


def _connect(dsn, schema):
    psycopg = _driver()
    _driver()
    from psycopg import sql

    _schema(schema)
    try:
        connection = psycopg.connect(
            dsn,
            autocommit=True,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=10000",
            application_name="hponas",
        )
        connection.execute(
            sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema))
        )
        return connection
    except psycopg.Error:
        if "connection" in locals():
            connection.close()
        raise BackendUnavailable("PostgreSQL connection/setup failed") from None


def initialize_postgres(dsn, *, schema="hponas"):
    """Create a new service schema atomically; refuse existing namespaces.

    Initialization is explicit and uses an owner role. Runtime roles need only
    schema usage, table reads/writes and sequence usage. Never uses public tables.
    """
    _schema(schema)
    connection = _connect(dsn, schema)
    try:
        with connection.transaction():
            _create_schema(connection, schema)
    except _driver().Error:
        raise BackendUnavailable(
            "PostgreSQL initialization failed; inspect the private database"
        ) from None
    finally:
        connection.close()


def _create_schema(connection, schema):
    from psycopg import sql

    connection.execute("SELECT pg_advisory_xact_lock(%s)", (_key(schema, "schema"),))
    if connection.execute(
        "SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)
    ).fetchone():
        raise ValueError(
            "PostgreSQL schema already exists; explicit migration is required"
        )
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    for table, columns in TABLES.items():
        connection.execute(
            sql.SQL("CREATE TABLE {} ({})").format(
                sql.Identifier(table), sql.SQL(columns)
            )
        )
    connection.execute(
        "INSERT INTO identity VALUES (TRUE,%s,%s,%s,TRUE)",
        (VERSION, _layout(connection, schema), _contract()),
    )


class _Backend:
    def __init__(self, dsn, *, schema="hponas"):
        self.schema = _schema(schema)
        self._connection = _connect(dsn, schema)
        self._failed = False
        try:
            if not self._execute(
                "SELECT pg_try_advisory_lock_shared(%s)", (_key(schema, "maintenance"),)
            ).fetchone()[0]:
                raise CoordinatorBusy("Database maintenance is in progress")
            rows = self._execute(
                "SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema,)
            ).fetchall()
            if {row[0] for row in rows} != set(TABLES):
                raise ValueError(
                    "PostgreSQL table inventory differs; explicit migration is required"
                )
            if self._execute(
                "SELECT singleton,version,layout,contract FROM identity"
            ).fetchall() != [
                (True, VERSION, _layout(self._connection, schema), _contract())
            ]:
                raise ValueError("Unsupported PostgreSQL schema version/layout")
        except BaseException:
            self.close()
            raise

    def _execute(self, query, parameters=()):
        if self._failed or self._connection.closed:
            raise BackendUnavailable(
                "Connection is fenced; open a fresh instance and reconcile"
            )
        try:
            return self._connection.execute(query, parameters)
        except _driver().Error:
            self._failed = True
            self._connection.close()
            raise BackendUnavailable(
                "PostgreSQL operation failed; committed state requires reconciliation"
            ) from None

    @contextmanager
    def _transaction(self):
        if self._failed or self._connection.closed:
            raise BackendUnavailable(
                "Connection is fenced; open a fresh instance and reconcile"
            )
        try:
            with self._connection.transaction():
                yield
        except _driver().Error:
            self._failed = True
            self._connection.close()
            raise BackendUnavailable(
                "PostgreSQL transaction failed; reconcile durable state before retry"
            ) from None

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PostgresStore(_Backend):
    """Study-compatible store with one connection holding each study's lock.

    Call load_checkpoint after reopening an existing Study. A new coordinator
    cannot overwrite an existing snapshot without first loading it. A terminated
    session remains fenced even if the database becomes available again.
    """

    def __init__(self, dsn, *, schema="hponas"):
        super().__init__(dsn, schema=schema)
        self._owned = set()
        self._loaded = set()

    def _claim(self, study_id):
        _identity(study_id)
        if not self._execute("SELECT dispatch_enabled FROM identity").fetchone()[0]:
            raise RecoveryRequired(
                "Historical restore is for inspection; reconcile and fence old writers before dispatch"
            )
        if study_id not in self._owned:
            if not self._execute(
                "SELECT pg_try_advisory_lock(%s)",
                (_key(self.schema, "study:" + study_id),),
            ).fetchone()[0]:
                raise CoordinatorBusy("Study already has a live coordinator")
            self._owned.add(study_id)
        else:
            self._execute(
                "SELECT 1"
            )  # Never trust cached ownership after connection loss.

    def _upsert_study(self, study):
        self._execute(
            "INSERT INTO studies(study_id,payload) VALUES (%s,%s) ON CONFLICT(study_id) DO UPDATE SET payload=EXCLUDED.payload",
            (study.study_id, _json(asdict(study))),
        )

    def coordinator_token(self, study_id):
        """Bind worker admission to the currently owning database session."""
        self._claim(study_id)
        pid, started = self._execute(
            "SELECT pid,backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()"
        ).fetchone()
        return CoordinatorToken(study_id, pid, started.isoformat())

    def _upsert_trial(self, trial, study_id):
        _identity(trial.trial_id)
        if not isinstance(trial.status, str) or not trial.status:
            raise ValueError("Trial status is required")
        row = self._execute(
            "INSERT INTO trials VALUES (%s,%s,%s) ON CONFLICT(trial_id) DO UPDATE SET payload=EXCLUDED.payload WHERE trials.study_id=EXCLUDED.study_id RETURNING trial_id",
            (trial.trial_id, study_id, _json(asdict(trial))),
        ).fetchone()
        if row is None:
            raise ValueError("Trial identity already belongs to another study")

    def save_study_snapshot(self, state):
        sid = state["study_name"]
        self._claim(sid)
        # All serializable values are checked before the transaction.
        # Trial/result mapping order is the durable proposal/observation order.
        # Lexical sorting places trial_10 before trial_2 and changes replay and
        # tie resolution. Keep canonical ordering for unrelated row payloads.
        payload = _json(state, sort_keys=False)
        eligible = [r for r in state["results"].values() if r["status"] == "completed"]
        if state.get("scheduler_state"):
            eligible = [
                r
                for r in eligible
                if r["fidelity"] == state["scheduler_state"]["config"]["r_max"]
            ]
        vector = state.get("multi_objective")
        if vector is not None:
            from hponas.multi_objective import ObjectiveSpec
            from hponas.types import Result

            spec = ObjectiveSpec(**vector["contract"])
            if spec.identity != vector["identity"]:
                raise ValueError("Store objective contract identity differs")
            for result in state["results"].values():
                spec.validate_result(Result(**result))
        best = (
            None
            if vector
            else (max if state["maximize"] else min)(
                (r["objective_value"] for r in eligible), default=None
            )
        )
        study = Study(
            sid,
            _json(state["space"]),
            "multi_objective"
            if vector
            else "maximize"
            if state["maximize"]
            else "minimize",
            state["searcher_state"].get("seed") or 0,
            state["budget"],
            best,
            state.get("outcome")
            or ("completed" if state.get("finished") else "running"),
        )
        if state.get('evaluation') is not None:
            from hponas.evaluation import evaluation_outcome
            final_outcome = evaluation_outcome(state['evaluation'])
            if final_outcome != 'completed':
                study.status = 'evaluation_' + final_outcome
        with self._transaction():
            prior = self._execute(
                "SELECT revision FROM snapshots WHERE study_id=%s", (sid,)
            ).fetchone()
            if prior and sid not in self._loaded:
                raise ValueError(
                    "Load the existing checkpoint before overwriting study state"
                )
            self._upsert_study(study)
            self._execute(
                "INSERT INTO snapshots VALUES (%s,%s,1) ON CONFLICT(study_id) DO UPDATE SET payload=EXCLUDED.payload,revision=snapshots.revision+1",
                (sid, payload),
            )
            for tid, trial in state["trials"].items():
                if tid != trial["trial_id"]:
                    raise ValueError("Trial key differs from identity")
                self._upsert_trial(
                    Trial(
                        tid,
                        trial["config"]["values"],
                        trial["seed"] or 0,
                        trial["fidelity"],
                        None if vector else trial["value"],
                        trial["cost"],
                        trial["parent_trial_id"],
                        trial["status"],
                    ),
                    sid,
                )
                from hponas.persistence import snapshot_artifacts
                self._execute("DELETE FROM artifacts WHERE trial_id=%s", (tid,))
                for kind, path in snapshot_artifacts(state, tid):
                    if isinstance(path, str):
                        self._execute(
                            "INSERT INTO artifacts(trial_id,kind,path) VALUES (%s,%s,%s)",
                            (tid, kind, path),
                        )
        self._loaded.add(sid)

    def peek_study_snapshot(self, study_id):
        """Read committed state for monitoring without acquiring ownership."""
        row = self._execute(
            "SELECT payload FROM snapshots WHERE study_id=%s", (study_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def load_study_snapshot(self, study_id):
        self._claim(study_id)
        state = self.peek_study_snapshot(study_id)
        self._loaded.add(study_id)
        return state

    def read_evaluation(self, study_id):
        state = self.peek_study_snapshot(study_id)
        if state is None:
            return None
        if state.get('evaluation') is None:
            from hponas.evaluation import legacy_evaluation_report
            return legacy_evaluation_report()
        return state['evaluation']

    def read_rung_diagnostics(self, study_id):
        from hponas.diagnostics import read_rung_diagnostics
        return read_rung_diagnostics(self.peek_study_snapshot(study_id))

    def read_report(self, study_id):
        from hponas.reporting import study_report
        return study_report(self.peek_study_snapshot(study_id))

    def export_report(self, study_id, destination):
        from hponas.reporting import export_study_report
        return export_study_report(self.peek_study_snapshot(study_id), destination)

    def write_study(self, study):
        self._claim(study.study_id)
        with self._transaction():
            self._upsert_study(study)

    def write_trial(self, trial, study_id):
        self._claim(study_id)
        with self._transaction():
            self._upsert_trial(trial, study_id)

    def read_study(self, study_id):
        row = self._execute(
            "SELECT payload FROM studies WHERE study_id=%s", (study_id,)
        ).fetchone()
        return Study(**json.loads(row[0])) if row else None

    def list_studies(self):
        return [
            Study(**json.loads(r[0]))
            for r in self._execute(
                "SELECT payload FROM studies ORDER BY ordinal DESC"
            ).fetchall()
        ]

    def read_trials(self, study_id):
        return [
            Trial(**json.loads(r[0]))
            for r in self._execute(
                "SELECT payload FROM trials WHERE study_id=%s ORDER BY trial_id",
                (study_id,),
            ).fetchall()
        ]

    def _trial_owner(self, trial_id):
        row = self._execute(
            "SELECT study_id FROM trials WHERE trial_id=%s", (trial_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Trial is not registered")
        self._claim(row[0])
        return row[0]

    def lineage(self, trial_id):
        result = []
        while trial_id:
            if trial_id in result:
                raise ValueError("Cyclic trial lineage")
            result.append(trial_id)
            row = self._execute(
                "SELECT payload FROM trials WHERE trial_id=%s", (trial_id,)
            ).fetchone()
            trial_id = json.loads(row[0])["parent_trial_id"] if row else None
        return result

    def write_observation(self, trial_id, fidelity, value, timestamp):
        self._trial_owner(trial_id)
        if not all(math.isfinite(v) for v in (fidelity, value, timestamp)):
            raise ValueError("Observations must be finite")
        self._execute(
            "INSERT INTO observations(trial_id,fidelity,value,observed_at) VALUES (%s,%s,%s,%s)",
            (trial_id, fidelity, value, timestamp),
        )

    def read_observations(self, trial_id):
        return self._execute(
            "SELECT fidelity,value,observed_at FROM observations WHERE trial_id=%s ORDER BY fidelity,id",
            (trial_id,),
        ).fetchall()

    def write_artifact(self, trial_id, artifact_type, path, metadata=None):
        self._trial_owner(trial_id)
        self._execute(
            "INSERT INTO artifacts(trial_id,kind,path,metadata) VALUES (%s,%s,%s,%s)",
            (
                trial_id,
                artifact_type,
                path,
                _json(metadata) if metadata is not None else None,
            ),
        )

    def read_artifacts(self, trial_id, artifact_type=None):
        query = "SELECT id,kind,path,metadata FROM artifacts WHERE trial_id=%s"
        args = (trial_id,)
        if artifact_type:
            query += " AND kind=%s"
            args += (artifact_type,)
        return [
            dict(
                artifact_id=i,
                artifact_type=k,
                path=p,
                metadata=json.loads(m) if m is not None else None,
            )
            for i, k, p, m in self._execute(query + " ORDER BY id", args).fetchall()
        ]

    def write_objectives(self, trial_id, values):
        self._trial_owner(trial_id)
        if not values or not all(math.isfinite(v) for v in values.values()):
            raise ValueError("Objective measurements must be nonempty and finite")
        self._execute(
            "INSERT INTO objectives VALUES (%s,%s) ON CONFLICT(trial_id) DO UPDATE SET payload=EXCLUDED.payload",
            (trial_id, _json(values)),
        )

    get_best_trials = Store.get_best_trials

    def get_pareto_front(self, study_id, objectives, directions=None):
        state = self.peek_study_snapshot(study_id)
        if state is None or state.get("multi_objective") is None:
            raise ValueError(
                "PostgreSQL Pareto queries require a saved MultiObjectiveStudy"
            )
        from hponas.multi_objective import ObjectiveSpec
        from hponas.types import Result

        spec = ObjectiveSpec(**state["multi_objective"]["contract"])
        expected = [
            "minimize" if o["direction"] == "min" else "maximize"
            for o in spec.contract["objectives"]
        ]
        if (
            spec.identity != state["multi_objective"]["identity"]
            or objectives != spec.names
            or directions is not None
            and directions != expected
        ):
            raise ValueError("Pareto query differs from stored objective contract")
        endpoint = (
            state["scheduler_state"]["config"]["r_max"]
            if state.get("scheduler_state")
            else 1.0
        )
        ids = spec.summarize(
            [Result(**r) for r in state["results"].values()], endpoint_fidelity=endpoint
        )["front_trial_ids"]
        trials = {t.trial_id: t for t in self.read_trials(study_id)}
        return [trials[tid] for tid in ids]

    def freeze_warm_history(
        self,
        study_id,
        *,
        task_id,
        model_family,
        task_domain,
        objective_key,
        endpoint_fidelity=1.0,
    ):
        from hponas.space import SearchSpace
        from hponas.warm_history import (
            _finite,
            _identity as check_identity,
            digest,
            space_signature,
        )

        identity = dict(
            study_id=study_id,
            task_id=task_id,
            model_family=model_family,
            task_domain=task_domain,
            objective_key=objective_key,
            endpoint_fidelity=endpoint_fidelity,
        )
        check_identity({**identity, "direction": "minimize"})
        if not _finite(endpoint_fidelity) or endpoint_fidelity <= 0:
            raise ValueError("A positive finite endpoint fidelity is required")
        self._claim(study_id)
        with self._transaction():
            row = self._execute(
                "SELECT payload FROM warm_history WHERE study_id=%s", (study_id,)
            ).fetchone()
            if row:
                value = self._history(row[0], study_id)
                if any(value.get(k) != v for k, v in identity.items()):
                    raise ValueError("Completed history identity is immutable")
                return value
            study = self.read_study(study_id)
            trials = [asdict(t) for t in self.read_trials(study_id)]
            if (
                study is None
                or study.status != "completed"
                or any(t["status"] in {"pending", "running", "paused"} for t in trials)
            ):
                raise ValueError("Only completed studies can become history")
            for trial in trials:
                if trial["status"] == "completed" and not _finite(trial["value"]):
                    trial.update(status="nonfinite", value=None)
                for key in ["value", "cost"]:
                    if trial[key] is not None and not _finite(trial[key]):
                        trial[key] = None
            body = {
                **identity,
                "direction": study.objective,
                "space_signature": space_signature(
                    SearchSpace.from_json(study.space_json)
                ),
                "status": "completed",
                "completed_at": time.time(),
                "trials": trials,
                "schema": "warm_history_snapshot_v1",
            }
            check_identity(body)
            value = {**body, "binding": digest(body)}
            self._execute(
                "INSERT INTO warm_history VALUES (%s,%s)", (study_id, _json(value))
            )
            return value

    @staticmethod
    def _history(payload, study_id):
        from hponas.warm_history import digest

        value = json.loads(payload)
        if (
            value.get("binding")
            != digest({k: v for k, v in value.items() if k != "binding"})
            or value.get("study_id") != study_id
            or value.get("schema") != "warm_history_snapshot_v1"
        ):
            raise ValueError("Retained warm history binding differs")
        return value

    def read_warm_histories(self):
        return [
            self._history(payload, sid)
            for sid, payload in self._execute(
                "SELECT study_id,payload FROM warm_history ORDER BY study_id"
            ).fetchall()
        ]


class PostgresWorkLedger(_Backend):
    """Shared prepaid capacity. Only a new charge permits physical work.

    All events under an allocation serialize through its budget row. A lost
    acknowledgement is uncertain consumption and never authorizes a replay.
    Use a new connection per process/thread; cloning/restoring stale budgets is
    not safe for continued dispatch without external reconciliation.
    """

    def __init__(
        self, dsn, *, allocation, capacity, unit="gradient_update", schema="hponas"
    ):
        _identity(allocation)
        _integer(capacity, "capacity")
        _identity(unit)
        super().__init__(dsn, schema=schema)
        self.allocation = allocation
        try:
            with self._transaction():
                enabled = self._execute(
                    "SELECT dispatch_enabled FROM identity"
                ).fetchone()[0]
                if enabled:
                    self._execute(
                        "INSERT INTO budgets(allocation,capacity,unit) VALUES (%s,%s,%s) ON CONFLICT(allocation) DO NOTHING",
                        (allocation, capacity, unit),
                    )
                if self._execute(
                    "SELECT capacity,unit FROM budgets WHERE allocation=%s",
                    (allocation,),
                ).fetchone() != (capacity, unit):
                    raise ValueError("Ledger capacity/unit contract differs")
        except BaseException:
            self.close()
            raise

    def _check_coordinator(self, token, study_id):
        if (
            not isinstance(token, CoordinatorToken)
            or token.study_id != study_id
            or type(token.backend_pid) is not int
            or token.backend_pid <= 0
            or not isinstance(token.backend_start, str)
        ):
            raise ValueError("Worker coordinator token differs")
        key = _key(self.schema, "study:" + study_id) & ((1 << 64) - 1)
        alive = self._execute(
            "SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid AND a.datid=l.database "
            "WHERE l.locktype='advisory' AND l.granted AND l.mode='ExclusiveLock' "
            "AND l.objsubid=1 AND l.classid::bigint=%s AND l.objid::bigint=%s "
            "AND a.pid=%s AND a.backend_start=%s::timestamptz AND a.datname=current_database()",
            (key >> 32, key & ((1 << 32) - 1), token.backend_pid, token.backend_start),
        ).fetchone()
        if alive is None:
            raise RecoveryRequired(
                "Coordinator no longer owns this study; stop metered work"
            )

    def charge(self, event_id, study_id, units=1, *, coordinator=None):
        _identity(event_id)
        _identity(study_id)
        _integer(units, "units")
        with self._transaction():
            if not self._execute("SELECT dispatch_enabled FROM identity").fetchone()[0]:
                raise RecoveryRequired(
                    "Historical work allocation is fenced after restore"
                )
            capacity, spent = self._execute(
                "SELECT capacity,spent FROM budgets WHERE allocation=%s FOR UPDATE",
                (self.allocation,),
            ).fetchone()
            if coordinator is not None:
                self._check_coordinator(coordinator, study_id)
            prior = self._execute(
                "SELECT study_id,units FROM charges WHERE allocation=%s AND event_id=%s",
                (self.allocation, event_id),
            ).fetchone()
            if prior:
                if prior != (study_id, units):
                    raise ValueError("Conflicting work event identity")
                return False
            if units > capacity - spent:
                raise WorkBudgetExceeded(
                    "Durable work capacity exhausted before dispatch"
                )
            self._execute(
                "INSERT INTO charges(allocation,event_id,study_id,units) VALUES (%s,%s,%s,%s)",
                (self.allocation, event_id, study_id, units),
            )
            self._execute(
                "UPDATE budgets SET spent=spent+%s WHERE allocation=%s",
                (units, self.allocation),
            )
        return True

    def complete(self, event_id, *, coordinator=None):
        _identity(event_id)
        if coordinator is not None:
            row = self._execute(
                "SELECT study_id FROM charges WHERE allocation=%s AND event_id=%s",
                (self.allocation, event_id),
            ).fetchone()
            if row is None:
                raise ValueError("Cannot acknowledge an uncharged event")
            self._check_coordinator(coordinator, row[0])
        if not self._execute("SELECT dispatch_enabled FROM identity").fetchone()[0]:
            raise RecoveryRequired("Historical work allocation is fenced after restore")
        if (
            self._execute(
                "UPDATE charges SET completed=TRUE WHERE allocation=%s AND event_id=%s RETURNING event_id",
                (self.allocation, event_id),
            ).fetchone()
            is None
        ):
            raise ValueError("Cannot acknowledge an uncharged event")

    def metrics(self):
        row = self._execute(
            "SELECT b.capacity,b.unit,b.spent,COALESCE(SUM(c.units),0),COALESCE(SUM(CASE WHEN c.completed THEN c.units ELSE 0 END),0),COUNT(c.event_id) FROM budgets b LEFT JOIN charges c USING(allocation) WHERE b.allocation=%s GROUP BY b.allocation",
            (self.allocation,),
        ).fetchone()
        capacity, unit, spent, charged, completed, count = row
        if not spent == charged or not 0 <= completed <= charged <= capacity:
            raise ValueError("Ledger conservation is violated")
        return dict(
            capacity=capacity,
            unit=unit,
            charged_units=int(charged),
            completed_units=int(completed),
            uncertain_units=int(charged - completed),
            remaining_units=capacity - int(charged),
            events=count,
        )
