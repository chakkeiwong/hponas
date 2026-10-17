"""Actual worker admission and bounded native Ray/PostgreSQL integration."""

from dataclasses import replace
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("psycopg")
from tests.integration.test_postgres_backend import database
from hponas.postgres import PostgresStore, PostgresWorkLedger, RecoveryRequired


def _leased_worker(dsn, schema, token, channel):
    with PostgresWorkLedger(
        dsn, schema=schema, allocation="workers", capacity=4
    ) as ledger:
        assert ledger.charge("first", "worker", coordinator=token)
        value = 1.0 - 0.25 * 2.0
        ledger.complete("first", coordinator=token)
        channel.send(value)
        channel.recv()
        try:
            ledger.charge("stale", "worker", coordinator=token)
        except RecoveryRequired:
            channel.send("fenced")
        else:
            channel.send("incorrectly admitted")


def test_live_worker_stops_after_coordinator_replacement(database):
    dsn, schema = database
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    owner = PostgresStore(dsn, schema=schema)
    token = owner.coordinator_token("worker")
    process = context.Process(target=_leased_worker, args=(dsn, schema, token, child))
    try:
        process.start()
        child.close()
        assert parent.poll(20) and parent.recv() == 0.5
        owner.close()
        with PostgresStore(dsn, schema=schema) as replacement:
            new_token = replacement.coordinator_token("worker")
            assert new_token != token
            parent.send("continue")
            assert parent.poll(20) and parent.recv() == "fenced"
            with PostgresWorkLedger(
                dsn, schema=schema, allocation="workers", capacity=4
            ) as ledger:
                assert ledger.charge("new", "worker", coordinator=new_token)
                with pytest.raises(RecoveryRequired):
                    ledger.complete("first", coordinator=token)
                assert ledger.metrics()["charged_units"] == 2
        process.join(5)
        assert process.exitcode == 0
    finally:
        owner.close()
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()
        child.close()


def test_worker_token_cannot_cross_study_session_or_schema(database):
    dsn, schema = database
    with (
        PostgresStore(dsn, schema=schema) as store,
        PostgresWorkLedger(
            dsn, schema=schema, allocation="tokens", capacity=2
        ) as ledger,
    ):
        token = store.coordinator_token("a")
        with pytest.raises(ValueError):
            ledger.charge("bad", "b", coordinator=token)
        with pytest.raises(RecoveryRequired):
            ledger.charge(
                "bad",
                "a",
                coordinator=replace(token, backend_start="2000-01-01T00:00:00+00:00"),
            )
        with pytest.raises(RecoveryRequired):
            ledger.charge(
                "bad", "a", coordinator=replace(token, backend_pid=2147483647)
            )
        assert ledger.metrics()["charged_units"] == 0


@pytest.mark.parametrize("use_ray", [False, True])
def test_native_known_answer_example_has_exact_work_and_restart(
    database, tmp_path, use_ray
):
    from examples.postgres_known_answer import run

    if use_ray:
        ray = pytest.importorskip("ray")
        ray.init(
            num_cpus=2, include_dashboard=False, object_store_memory=100 * 1024 * 1024
        )
    try:
        report = run(*database, tmp_path / "example", use_ray=use_ray)
        assert report["gradient_updates"] == 24 and report["passed"]
        if use_ray:
            assert ray.is_initialized()  # Caller owns and shuts down the cluster.
            assert ray.cluster_resources()["CPU"] == 2
    finally:
        if use_ray:
            ray.shutdown()


def test_status_cli_returns_nonzero_for_uncertainty_without_exposing_dsn(database):
    dsn, schema = database
    with PostgresWorkLedger(
        dsn, schema=schema, allocation="uncertain", capacity=2
    ) as ledger:
        ledger.charge("unacknowledged", "s")
    env = dict(os.environ, HPONAS_POSTGRES_DSN=dsn)
    result = subprocess.run(
        [sys.executable, "-m", "tools.postgres_status", "--schema", schema],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "uncertain_work_requires_reconciliation" in result.stdout
    assert dsn not in result.stdout + result.stderr


def test_storage_exhaustion_refusal_fences_connection_without_partial_snapshot(
    database,
):
    import psycopg
    from psycopg import sql
    from hponas.postgres import BackendUnavailable
    from tests.unit.test_store_snapshot_contract import snapshot

    dsn, schema = database
    with PostgresStore(dsn, schema=schema) as store:
        state = snapshot()
        store.save_study_snapshot(state)
        # PostgreSQL's real transaction/driver path receives disk_full. This
        # does not fill the shared host disk or establish physical-disk recovery.
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL(
                    "CREATE FUNCTION {}.refuse_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected storage refusal' USING ERRCODE='53100'; END $$"
                ).format(sql.Identifier(schema))
            )
            admin.execute(
                sql.SQL(
                    "CREATE TRIGGER refuse_write BEFORE UPDATE ON {}.trials FOR EACH ROW EXECUTE FUNCTION {}.refuse_write()"
                ).format(sql.Identifier(schema), sql.Identifier(schema))
            )
        changed = {**state, "budget": 77}
        with pytest.raises(BackendUnavailable):
            store.save_study_snapshot(changed)
        with pytest.raises(BackendUnavailable):
            store.save_study_snapshot(changed)
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP TRIGGER refuse_write ON {}.trials").format(
                    sql.Identifier(schema)
                )
            )
            admin.execute(
                sql.SQL("DROP FUNCTION {}.refuse_write()").format(
                    sql.Identifier(schema)
                )
            )
    with PostgresStore(dsn, schema=schema) as store:
        assert store.load_study_snapshot("snap") == state
        assert store.read_study("snap").budget == 9


def test_server_statement_deadline_fences_before_retry(database):
    from hponas.postgres import BackendUnavailable
    import time

    with PostgresStore(database[0], schema=database[1]) as store:
        start = time.monotonic()
        with pytest.raises(BackendUnavailable):
            store._execute("SELECT pg_sleep(30)")
        assert time.monotonic() - start < 15
        with pytest.raises(BackendUnavailable):
            store._execute("SELECT 1")
