"""Service recovery invariants on a real isolated PostgreSQL backend."""

import json

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql
from tests.integration.test_postgres_backend import database
from hponas.postgres import (
    CoordinatorBusy,
    PostgresStore,
    PostgresWorkLedger,
    RecoveryRequired,
)
from hponas.postgres_operations import (
    backup_postgres,
    restore_postgres,
    postgres_status,
)
from hponas.store import Study, Trial


def seed(database, root):
    dsn, schema = database
    (root / "model.bin").write_bytes(b"known-answer-checkpoint")
    with PostgresStore(dsn, schema=schema) as store:
        store.write_study(Study("s", "{}", "minimize", 1, 1, status="completed"))
        store.write_trial(
            Trial("t", {"x": 0.5}, 1, 1, 0.25, 1, status="completed"), "s"
        )
        store.write_artifact(
            "t", "model", "model.bin", {"sha256": "in-independent-manifest"}
        )
    with PostgresWorkLedger(dsn, schema=schema, allocation="a", capacity=2) as ledger:
        assert ledger.charge("spent", "s")


def test_backup_quiesces_writers_and_new_clients(database, tmp_path):
    dsn, schema = database
    with PostgresStore(dsn, schema=schema):
        with pytest.raises(CoordinatorBusy):
            backup_postgres(dsn, tmp_path / "refused", schema=schema)
    assert not (tmp_path / "refused/backup.json").exists()
    from hponas.postgres import _connect, _key

    owner = _connect(dsn, schema)
    try:
        owner.execute("SELECT pg_advisory_lock(%s)", (_key(schema, "maintenance"),))
        with pytest.raises(CoordinatorBusy):
            PostgresStore(dsn, schema=schema)
    finally:
        owner.close()


def test_historical_restore_preserves_rows_and_artifacts_but_cannot_reset_budget(
    database, tmp_path
):
    dsn, schema = database
    seed(database, tmp_path)
    assert (
        postgres_status(dsn, schema=schema)["status"]
        == "uncertain_work_requires_reconciliation"
    )
    receipt = backup_postgres(
        dsn, tmp_path / "backup", schema=schema, artifact_root=tmp_path
    )
    # Spending after backup proves why its remaining capacity cannot go live.
    with PostgresWorkLedger(dsn, schema=schema, allocation="a", capacity=2) as ledger:
        assert ledger.charge("later", "s")
    restored = schema + "_r"
    try:
        report = restore_postgres(
            dsn, tmp_path / "backup", schema=restored, expected_sha256=receipt["sha256"]
        )
        assert not report["dispatch_enabled"]
        with PostgresStore(dsn, schema=restored) as store:
            assert store.read_trials("s")[0].value == 0.25
            assert store.read_artifacts("t")[0]["path"] == "model.bin"
            with pytest.raises(RecoveryRequired):
                store.write_study(Study("extra", "{}", "minimize", 1, 1))
        with PostgresWorkLedger(
            dsn, schema=restored, allocation="a", capacity=2
        ) as ledger:
            assert ledger.metrics()["remaining_units"] == 1
            with pytest.raises(RecoveryRequired):
                ledger.charge("illegal", "s")
            with pytest.raises(RecoveryRequired):
                ledger.complete("spent")
        with pytest.raises(ValueError):
            PostgresWorkLedger(dsn, schema=restored, allocation="new", capacity=999)
        assert (
            postgres_status(dsn, schema=restored)["status"]
            == "historical_restore_fenced"
        )
        with pytest.raises(ValueError):
            restore_postgres(
                dsn,
                tmp_path / "backup",
                schema=restored,
                expected_sha256=receipt["sha256"],
            )
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(restored)
                )
            )


def test_backup_corrupt_artifact_or_replaced_manifest_is_refused(database, tmp_path):
    dsn, schema = database
    seed(database, tmp_path)
    receipt = backup_postgres(
        dsn, tmp_path / "backup", schema=schema, artifact_root=tmp_path
    )
    data = json.loads((tmp_path / "backup/backup.json").read_text())
    artifact = tmp_path / "backup" / data["artifacts"][0]["filename"]
    artifact.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        restore_postgres(
            dsn,
            tmp_path / "backup",
            schema=schema + "_r",
            expected_sha256=receipt["sha256"],
        )
    artifact.write_bytes(b"known-answer-checkpoint")
    (tmp_path / "backup/backup.json").write_text("{}")
    with pytest.raises(ValueError, match="digest"):
        restore_postgres(
            dsn,
            tmp_path / "backup",
            schema=schema + "_r",
            expected_sha256=receipt["sha256"],
        )
    with psycopg.connect(dsn, autocommit=True) as admin:
        assert (
            admin.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema + "_r",)
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("references", [0, 1, 2])
def test_backup_and_restore_share_exact_total_byte_boundary(database, tmp_path, references):
    dsn, schema = database
    if references:
        seed(database, tmp_path)
    if references == 2:
        (tmp_path / "alias.bin").write_bytes((tmp_path / "model.bin").read_bytes())
        with PostgresStore(dsn, schema=schema) as store:
            store.write_artifact("t", "alias", "alias.bin", {})
    measured = backup_postgres(
        dsn, tmp_path / "measure", schema=schema, artifact_root=tmp_path
    )
    # The independent measure is the actual published directory, including the
    # manifest and one content-addressed file for duplicate artifact references.
    total = sum(path.stat().st_size for path in (tmp_path / "measure").iterdir())
    assert measured["total_bytes"] == total
    assert measured["artifact_count"] == references
    assert measured["artifact_bytes"] == (
        len(b"known-answer-checkpoint") if references else 0
    )
    with pytest.raises(ValueError, match="envelope"):
        backup_postgres(
            dsn, tmp_path / "refused", schema=schema,
            artifact_root=tmp_path, max_bytes=total - 1,
        )
    assert not (tmp_path / "refused/backup.json").exists()
    exact = backup_postgres(
        dsn, tmp_path / "exact", schema=schema,
        artifact_root=tmp_path, max_bytes=total,
    )
    assert exact["sha256"] == measured["sha256"]
    restored = schema + "_boundary"
    try:
        with pytest.raises(ValueError):
            restore_postgres(
                dsn, tmp_path / "exact", schema=restored,
                expected_sha256=exact["sha256"], max_bytes=total - 1,
            )
        report = restore_postgres(
            dsn, tmp_path / "exact", schema=restored,
            expected_sha256=exact["sha256"], max_bytes=total,
        )
        assert report["artifact_count"] == references
        assert report["dispatch_enabled"] is False
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(restored))
            )


def test_backup_refuses_missing_root_symlink_and_excessive_resource(database, tmp_path):
    dsn, schema = database
    seed(database, tmp_path)
    with pytest.raises(ValueError, match="root"):
        backup_postgres(dsn, tmp_path / "no-root", schema=schema)
    with pytest.raises(ValueError, match="envelope"):
        backup_postgres(
            dsn, tmp_path / "small", schema=schema, artifact_root=tmp_path, max_bytes=1
        )
    original = tmp_path / "model.bin"
    original.rename(tmp_path / "original.bin")
    original.symlink_to(tmp_path / "original.bin")
    with pytest.raises(ValueError, match="path"):
        backup_postgres(dsn, tmp_path / "link", schema=schema, artifact_root=tmp_path)


def test_database_roles_separate_runtime_monitor_and_schema_owner(database):
    dsn, schema = database
    role = schema + "_role"
    reader = schema + "_read"
    with psycopg.connect(dsn, autocommit=True) as admin:
        try:
            for name in [role, reader]:
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(name))
                )
                admin.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(name)
                    )
                )
                admin.execute(
                    sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(name)
                    )
                )
            admin.execute(
                sql.SQL(
                    "GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO {}"
                ).format(sql.Identifier(schema), sql.Identifier(role))
            )
            admin.execute(
                sql.SQL("REVOKE INSERT,UPDATE,DELETE ON {}.identity FROM {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL(
                    "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}"
                ).format(sql.Identifier(schema), sql.Identifier(role))
            )
            with PostgresStore(dsn, schema=schema) as store:
                store._connection.execute(
                    sql.SQL("SET ROLE {}").format(sql.Identifier(role))
                )
                store.save_study_snapshot(
                    __import__(
                        "tests.unit.test_store_snapshot_contract", fromlist=["snapshot"]
                    ).snapshot()
                )
            admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(reader)))
            assert (
                admin.execute(
                    sql.SQL("SELECT count(*) FROM {}.trials").format(
                        sql.Identifier(schema)
                    )
                ).fetchone()[0]
                == 5
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(
                    sql.SQL("DELETE FROM {}.trials").format(sql.Identifier(schema))
                )
            admin.execute("RESET ROLE")
            admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(
                    sql.SQL("UPDATE {}.identity SET dispatch_enabled=TRUE").format(
                        sql.Identifier(schema)
                    )
                )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                admin.execute(
                    sql.SQL("ALTER TABLE {}.trials ADD COLUMN forbidden TEXT").format(
                        sql.Identifier(schema)
                    )
                )
        finally:
            admin.execute("RESET ROLE")
            for name in [role, reader]:
                admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(name)))
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
