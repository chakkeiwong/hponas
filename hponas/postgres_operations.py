"""Quiesced PostgreSQL evidence backups and fenced historical restores.

This finite logical backup preserves database rows and referenced files. It is
not physical replication, point-in-time recovery or a writable failover service.
"""

import hashlib
import json
from pathlib import Path
import time

from hponas.postgres import (
    TABLES,
    VERSION,
    BackendUnavailable,
    CoordinatorBusy,
    _Backend,
    _connect,
    _contract,
    _create_schema,
    _driver,
    _key,
    _schema,
)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, data):
    import os

    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def backup_postgres(
    dsn,
    directory,
    *,
    schema="hponas",
    artifact_root=None,
    max_bytes=64 * 1024 * 1024,
    max_seconds=30,
):
    """Back up a quiescent private schema and its declared artifact references.

    All cooperating Store/ledger clients must be closed. The maintenance lock
    blocks new clients while rows and files are captured. Checkpoint files must
    already be closed and immutable. Owner-controlled paths are required.
    """
    from hponas.operations import _integer

    _integer(max_bytes, "backup byte cap")
    _integer(max_seconds, "backup time cap")
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = time.monotonic()
    used = 0
    artifact_bytes = 0

    def check(size):
        nonlocal used
        used += size
        if used > max_bytes or time.monotonic() - started > max_seconds:
            raise ValueError("Backup resource envelope exceeded")

    with _Backend(dsn, schema=schema) as backend:
        backend._execute(
            "SELECT pg_advisory_unlock_shared(%s)", (_key(schema, "maintenance"),)
        )
        if not backend._execute(
            "SELECT pg_try_advisory_lock(%s)", (_key(schema, "maintenance"),)
        ).fetchone()[0]:
            raise CoordinatorBusy(
                "Close all Store and ledger clients before coordinated backup"
            )
        from psycopg import sql

        tables = {}
        with backend._transaction():
            backend._execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            for table in TABLES:
                cursor = backend._execute(
                    sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
                )
                columns = [column.name for column in cursor.description]
                rows = []
                for row in cursor:
                    check(len(json.dumps(row).encode()))
                    rows.append(list(row))
                tables[table] = dict(columns=columns, rows=rows)
            inventory = []
            artifacts = tables["artifacts"]
            path_index = artifacts["columns"].index("path")
            paths = sorted({row[path_index] for row in artifacts["rows"]})
            if len(paths) > 4096:
                raise ValueError("Artifact count exceeds backup envelope")
            for path in paths:
                if artifact_root is None:
                    raise ValueError("An explicit artifact root is required")
                root = Path(artifact_root).resolve()
                source = Path(path)
                if not source.is_absolute():
                    source = root / source
                if source.is_symlink() or not source.resolve().is_relative_to(root):
                    raise ValueError("Artifact path escapes the declared root")
                if source.stat().st_size > max_bytes:
                    raise ValueError("Artifact exceeds backup byte cap")
                with source.open("rb") as handle:
                    content = handle.read(max_bytes + 1)
                if len(content) > max_bytes:
                    raise ValueError("Artifact exceeds backup byte cap")
                digest = _digest(content)
                target = directory / digest
                if not target.exists():
                    check(len(content))
                    _write(target, content)
                    artifact_bytes += len(content)
                else:
                    check(0)
                inventory.append(
                    dict(
                        original_path=path,
                        filename=digest,
                        sha256=digest,
                        bytes=len(content),
                    )
                )
            payload = dict(
                kind="postgres_quiesced_backup_v1",
                version=VERSION,
                contract=_contract(),
                tables=tables,
                artifacts=inventory,
                source_schema=schema,
                continuation="historical_inspection_only_until_external_reconciliation",
            )
            encoded = (
                json.dumps(payload, sort_keys=True, allow_nan=False) + "\n"
            ).encode()
            if len(encoded) + artifact_bytes > max_bytes:
                raise ValueError("Backup resource envelope exceeded")
            if time.monotonic() - started > max_seconds:
                raise ValueError("Backup time cap exceeded")
            _write(directory / "backup.json", encoded)
    return dict(
        sha256=_digest(encoded),
        bytes=len(encoded),
        artifact_bytes=artifact_bytes,
        total_bytes=len(encoded) + artifact_bytes,
        artifact_count=len(inventory),
        table_counts={name: len(value["rows"]) for name, value in tables.items()},
        dispatch_after_restore=False,
    )


def restore_postgres(
    dsn, directory, *, schema, expected_sha256, max_bytes=64 * 1024 * 1024
):
    """Restore into a new schema atomically, with all dispatch permanently fenced.

    The digest must come from a separately retained inventory. A colocated hash
    does not authenticate an owner-controlled backup. This API deliberately has
    no switch that can make a historical budget live again.
    """
    from hponas.operations import _integer

    _integer(max_bytes, "restore byte cap")
    _schema(schema)
    directory = Path(directory)
    source = directory / "backup.json"
    if (
        directory.is_symlink()
        or source.is_symlink()
        or source.stat().st_size > max_bytes
    ):
        raise ValueError("Unsafe or excessive backup")
    content = source.read_bytes()
    if len(content) > max_bytes or _digest(content) != expected_sha256:
        raise ValueError("Backup bytes differ from the retained digest")
    payload = json.loads(content)
    if (
        payload.get("kind") != "postgres_quiesced_backup_v1"
        or payload.get("version") != VERSION
        or payload.get("contract") != _contract()
        or set(payload["tables"]) != set(TABLES)
    ):
        raise ValueError("Backup schema contract differs")
    used = len(content)
    verified = set()
    for item in payload["artifacts"]:
        if (
            item["filename"] != item["sha256"]
            or len(item["filename"]) != 64
            or any(c not in "0123456789abcdef" for c in item["filename"])
        ):
            raise ValueError("Unsafe artifact identity")
        file = directory / item["filename"]
        if (
            file.is_symlink()
            or file.stat().st_size != item["bytes"]
        ):
            raise ValueError("Unsafe or excessive artifact")
        if item["filename"] in verified:
            continue
        with file.open("rb") as handle:
            blob = handle.read(max_bytes - used + 1)
        used += len(blob)
        if used > max_bytes:
            raise ValueError("Unsafe or excessive artifact")
        if len(blob) != item["bytes"] or _digest(blob) != item["sha256"]:
            raise ValueError("Artifact bytes differ")
        verified.add(item["filename"])
    connection = _connect(dsn, schema)
    try:
        from psycopg import sql

        with connection.transaction():
            _create_schema(connection, schema)
            connection.execute("UPDATE identity SET dispatch_enabled=FALSE")
            for table in TABLES:
                if table == "identity":
                    continue
                data = payload["tables"][table]
                expected = [
                    c.name
                    for c in connection.execute(
                        sql.SQL("SELECT * FROM {} LIMIT 0").format(
                            sql.Identifier(table)
                        )
                    ).description
                ]
                if data["columns"] != expected:
                    raise ValueError("Backup table columns differ")
                query = sql.SQL(
                    "INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE VALUES ({})"
                ).format(
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, expected)),
                    sql.SQL(",").join(sql.Placeholder() for _ in expected),
                )
                for row in data["rows"]:
                    connection.execute(query, row)
            # Queries and inspection are safe. All writers and new work are
            # blocked by identity.dispatch_enabled, including empty allocations.
            inconsistencies = connection.execute(
                "SELECT b.allocation FROM budgets b LEFT JOIN charges c USING(allocation) GROUP BY b.allocation HAVING b.spent<>COALESCE(SUM(c.units),0)"
            ).fetchall()
            if inconsistencies:
                raise ValueError("Restored budget conservation is violated")
    except _driver().Error:
        raise BackendUnavailable("Historical restore failed atomically") from None
    finally:
        connection.close()
    return dict(
        schema=schema,
        dispatch_enabled=False,
        table_counts={n: len(v["rows"]) for n, v in payload["tables"].items()},
        artifact_count=len(payload["artifacts"]),
    )


def postgres_status(dsn, *, schema="hponas"):
    """Observe integrity/accounting without opening a study or creating rows."""
    with _Backend(dsn, schema=schema) as backend:
        with backend._transaction():
            backend._execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            enabled = backend._execute(
                "SELECT dispatch_enabled FROM identity"
            ).fetchone()[0]
            rows = backend._execute(
                "SELECT b.allocation,b.capacity,b.spent,COALESCE(SUM(c.units),0),COALESCE(SUM(CASE WHEN c.completed THEN c.units ELSE 0 END),0) FROM budgets b LEFT JOIN charges c USING(allocation) GROUP BY b.allocation ORDER BY b.allocation"
            ).fetchall()
            allocations = []
            for name, capacity, spent, charged, completed in rows:
                if spent != charged or not 0 <= completed <= charged <= capacity:
                    raise ValueError("Ledger conservation is violated")
                allocations.append(
                    dict(
                        allocation=name,
                        capacity=capacity,
                        charged_units=int(charged),
                        uncertain_units=int(charged - completed),
                    )
                )
            return dict(
                dispatch_enabled=enabled,
                allocations=allocations,
                status="historical_restore_fenced"
                if not enabled
                else "uncertain_work_requires_reconciliation"
                if any(a["uncertain_units"] for a in allocations)
                else "ok",
                studies=backend._execute("SELECT COUNT(*) FROM studies").fetchone()[0],
                trials=backend._execute("SELECT COUNT(*) FROM trials").fetchone()[0],
            )
