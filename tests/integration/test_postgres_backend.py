"""Real server invariants for the optional concurrent backend (OPS-01)."""

import copy
import multiprocessing
import os
import time
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql

from hponas.postgres import (
    BackendUnavailable,
    CoordinatorBusy,
    PostgresStore,
    PostgresWorkLedger,
    initialize_postgres,
)
from hponas.operations import WorkBudgetExceeded
from hponas.store import Study as StoredStudy, Trial
from tests.unit.test_store_snapshot_contract import snapshot


@pytest.fixture
def database():
    dsn = os.environ.get("HPONAS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Requires an isolated PostgreSQL test server")
    schema = "test_" + uuid.uuid4().hex
    initialize_postgres(dsn, schema=schema)
    yield dsn, schema
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
        )


def _write_independent(dsn, schema, worker, output):
    try:
        sid = "study-" + str(worker)
        with PostgresStore(dsn, schema=schema) as store:
            store.write_study(StoredStudy(sid, "{}", "minimize", worker, 8))
            for i in range(8):
                store.write_trial(
                    Trial(
                        sid + "-" + str(i),
                        {"x": i},
                        i,
                        1.0,
                        i * i,
                        1.0,
                        status="completed",
                    ),
                    sid,
                )
        output.put(("ok", worker))
    except BaseException as exc:
        output.put(("error", type(exc).__name__))


def _spend(dsn, schema, worker, output):
    try:
        admitted = []
        with PostgresWorkLedger(
            dsn, schema=schema, allocation="shared", capacity=17
        ) as ledger:
            for i in range(12):
                event = str(worker) + "-" + str(i)
                try:
                    if ledger.charge(event, "study-" + str(worker)):
                        # Every admitted operation is an actual scalar update.
                        value = 1.0
                        value -= 0.25 * 2.0 * value
                        admitted.append((event, value))
                        ledger.complete(event)
                except WorkBudgetExceeded:
                    break
        output.put(("ok", admitted))
    except BaseException as exc:
        output.put(("error", type(exc).__name__))


def _uncommitted_writer(dsn, schema, channel):
    store = PostgresStore(dsn, schema=schema)
    state = store.load_study_snapshot("snap")
    state["budget"] = 77
    original = store._upsert_trial

    def pause(trial, study_id):
        original(trial, study_id)
        channel.send("uncommitted")
        channel.recv()

    store._upsert_trial = pause
    store.save_study_snapshot(state)


def _charge_then_wait(dsn, schema, channel):
    with PostgresWorkLedger(
        dsn, schema=schema, allocation="crash", capacity=2
    ) as ledger:
        assert ledger.charge("uncertain", "s")
        channel.send("charged")
        channel.recv()


def _processes(target, database):
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    jobs = [
        context.Process(target=target, args=(*database, i, output)) for i in range(4)
    ]
    try:
        for job in jobs:
            job.start()
        reports = [output.get(timeout=25) for job in jobs]
        for job in jobs:
            job.join(5)
            assert job.exitcode == 0
        assert all(r[0] == "ok" for r in reports), reports
        return [r[1] for r in reports]
    finally:
        for job in jobs:
            if job.is_alive():
                job.kill()
                job.join(5)
        output.close()


def _kill_after(target, database, expected):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=target, args=(*database, child))
    try:
        process.start()
        child.close()
        assert parent.poll(25)
        assert parent.recv() == expected
        process.kill()
        process.join(5)
        assert process.exitcode == -9
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()
        child.close()


def test_real_independent_processes_commit_distinct_studies(database):
    assert sorted(_processes(_write_independent, database)) == [0, 1, 2, 3]
    with PostgresStore(database[0], schema=database[1]) as store:
        assert len(store.list_studies()) == 4
        for i in range(4):
            trials = store.read_trials("study-" + str(i))
            assert len(trials) == 8
            assert [t.value for t in trials] == [j * j for j in range(8)]


@pytest.mark.parametrize(
    "maximize,scheduled,incumbent",
    [(False, False, -4), (True, False, 7), (False, True, 2), (True, True, 7)],
)
def test_snapshot_and_queries_recover_together(
    database, maximize, scheduled, incumbent
):
    dsn, schema = database
    state = snapshot(maximize, scheduled, finished=True)
    with PostgresStore(dsn, schema=schema) as store:
        store.save_study_snapshot(state)
        assert store.read_study("snap").incumbent_value == incumbent
    with PostgresStore(dsn, schema=schema) as store:
        assert store.load_study_snapshot("snap") == state
        assert len(store.read_trials("snap")) == 5
        assert store.lineage("full-a") == ["full-a", "base"]
        assert store.read_artifacts("base")[0]["path"] == "base.bin"
        store.save_study_snapshot(state)
        assert len(store.read_artifacts("base")) == 1


def test_second_coordinator_is_fenced_and_monitor_stays_read_only(database):
    dsn, schema = database
    with (
        PostgresStore(dsn, schema=schema) as owner,
        PostgresStore(dsn, schema=schema) as peer,
    ):
        owner.save_study_snapshot(snapshot())
        assert peer.peek_study_snapshot("snap") == snapshot()
        with pytest.raises(CoordinatorBusy):
            peer.load_study_snapshot("snap")
        with pytest.raises(CoordinatorBusy):
            peer.save_study_snapshot(snapshot())
        token = owner.coordinator_token("snap")
        owner.close()
        # Client close sends Terminate; PostgreSQL releases session locks when
        # its backend exits. Observe that boundary before testing a new owner.
        deadline = time.monotonic() + 5
        while peer._connection.execute(
            "SELECT 1 FROM pg_stat_activity WHERE pid=%s "
            "AND backend_start=%s::timestamptz",
            (token.backend_pid, token.backend_start),
        ).fetchone() is not None:
            assert time.monotonic() < deadline, "Closed owner session did not exit"
            time.sleep(0.01)
        with pytest.raises(ValueError, match="Load"):
            peer.save_study_snapshot(snapshot())
        peer.load_study_snapshot("snap")
        peer.save_study_snapshot(snapshot())


def test_invalid_later_trial_rolls_back_every_projection(database):
    dsn, schema = database
    with PostgresStore(dsn, schema=schema) as store:
        state = snapshot()
        store.save_study_snapshot(state)
        invalid = copy.deepcopy(state)
        invalid["budget"] = 77
        invalid["trials"]["pending"]["status"] = None
        with pytest.raises(ValueError):
            store.save_study_snapshot(invalid)
        assert store.load_study_snapshot("snap") == state
        assert store.read_study("snap").budget == 9


def test_killed_snapshot_transaction_restores_previous_commit(database):
    dsn, schema = database
    with PostgresStore(dsn, schema=schema) as store:
        store.save_study_snapshot(snapshot())
    _kill_after(_uncommitted_writer, database, "uncommitted")
    with PostgresStore(dsn, schema=schema) as store:
        assert store.load_study_snapshot("snap") == snapshot()
        assert store.read_study("snap").budget == 9


def test_global_budget_bounds_actual_work_under_four_process_contention(database):
    reports = _processes(_spend, database)
    events = [item for report in reports for item in report]
    assert len(events) == len({e[0] for e in events}) == 17
    assert all(value == 0.5 for _, value in events)
    with PostgresWorkLedger(
        database[0], schema=database[1], allocation="shared", capacity=17
    ) as ledger:
        assert ledger.metrics() == dict(
            capacity=17,
            unit="gradient_update",
            charged_units=17,
            completed_units=17,
            uncertain_units=0,
            remaining_units=0,
            events=17,
        )
        event = events[0][0]
        assert not ledger.charge(event, "study-" + event.split("-")[0])
        with pytest.raises(WorkBudgetExceeded):
            ledger.charge("extra", "s")
        with pytest.raises(ValueError):
            ledger.charge(event, "wrong-study")


def test_kill_after_debit_preserves_uncertain_spend_and_refuses_replay(database):
    _kill_after(_charge_then_wait, database, "charged")
    with PostgresWorkLedger(
        database[0], schema=database[1], allocation="crash", capacity=2
    ) as ledger:
        assert ledger.metrics()["uncertain_units"] == 1
        assert not ledger.charge("uncertain", "s")
        assert ledger.charge("new", "s")
        with pytest.raises(WorkBudgetExceeded):
            ledger.charge("over", "s")
        with pytest.raises(ValueError):
            ledger.complete("absent")
    with pytest.raises(ValueError):
        PostgresWorkLedger(
            database[0], schema=database[1], allocation="crash", capacity=3
        )


def test_terminated_server_session_cannot_reuse_cached_ownership(database):
    dsn, schema = database
    with PostgresStore(dsn, schema=schema) as store:
        store.save_study_snapshot(snapshot())
        pid = store._connection.info.backend_pid
        with psycopg.connect(dsn, autocommit=True) as admin:
            assert admin.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[
                0
            ]
        for _ in range(2):
            with pytest.raises(BackendUnavailable):
                store.save_study_snapshot(snapshot())
    with PostgresStore(dsn, schema=schema) as fresh:
        assert fresh.load_study_snapshot("snap") == snapshot()


def test_schema_reinitialization_and_future_version_are_refused(database):
    dsn, schema = database
    with pytest.raises(ValueError):
        initialize_postgres(dsn, schema=schema)
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("UPDATE {}.identity SET version=999").format(sql.Identifier(schema))
        )
    with pytest.raises(ValueError, match="version"):
        PostgresStore(dsn, schema=schema)
    with pytest.raises(ValueError):
        PostgresStore(dsn, schema="public")


def test_schema_drift_without_version_change_is_refused(database):
    dsn, schema = database
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL(
                "ALTER TABLE {}.charges DROP CONSTRAINT charges_units_check"
            ).format(sql.Identifier(schema))
        )
    with pytest.raises(ValueError, match="layout"):
        PostgresStore(dsn, schema=schema)


def test_native_failed_evaluation_is_durable_and_resumable(database):
    import math
    from hponas import Study, LocalExecutor, IncompleteStudyError
    from hponas.space import SearchSpace, Knob
    from hponas.searchers import RandomSearcher

    dsn, schema = database
    space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
    calls = []

    def objective(config):
        calls.append(config)
        return math.nan

    with PostgresStore(dsn, schema=schema) as store:
        study = Study(
            RandomSearcher(space, seed=1),
            LocalExecutor(),
            objective,
            budget=1,
            study_name="failed",
            store=store, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        with pytest.raises(IncompleteStudyError):
            study.run()
        state = store.peek_study_snapshot("failed")
        assert math.isnan(next(iter(state["results"].values()))["objective_value"])
    with PostgresStore(dsn, schema=schema) as store:
        study = Study(
            RandomSearcher(space, seed=1),
            LocalExecutor(),
            objective,
            budget=1,
            study_name="failed",
            store=store, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        study.load_checkpoint()
        with pytest.raises(IncompleteStudyError):
            study.run()
        assert len(calls) == 1


def test_cross_study_trial_identity_cannot_overwrite_owner(database):
    with PostgresStore(database[0], schema=database[1]) as store:
        for sid in ["first", "second"]:
            store.write_study(StoredStudy(sid, "{}", "minimize", 1, 1))
        store.write_trial(Trial("shared", {}, 1, 1, 2, 3), "first")
        with pytest.raises(ValueError):
            store.write_trial(Trial("shared", {}, 1, 1, 9, 9), "second")
        assert store.read_trials("first")[0].value == 2
        assert store.read_trials("second") == []


def test_native_study_restart_does_not_rerun_committed_training(database):
    from hponas import Study, LocalExecutor
    from hponas.space import SearchSpace, Knob
    from hponas.searchers import RandomSearcher

    dsn, schema = database
    space = SearchSpace([Knob("eta", "continuous", (0.125, 0.875))])
    updates = []

    def objective(config):
        value = 1.0
        for _ in range(4):
            value -= config["eta"] * 2.0 * value
            updates.append(value)
        return value * value

    with PostgresStore(dsn, schema=schema) as store:
        study = Study(
            RandomSearcher(space, seed=13),
            LocalExecutor(),
            objective,
            budget=4,
            maximize=False,
            study_name="native",
            store=store, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        outcome = study.run()
        assert len(updates) == 16
        first = store.peek_study_snapshot("native")
    with PostgresStore(dsn, schema=schema) as store:
        resumed = Study(
            RandomSearcher(space, seed=13),
            LocalExecutor(),
            objective,
            budget=4,
            maximize=False,
            study_name="native",
            store=store, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        resumed.load_checkpoint()
        assert resumed.run().best_value == outcome.best_value
        assert len(updates) == 16
        assert store.peek_study_snapshot("native") == first
        for result in outcome.history:
            eta = first["trials"][result.trial_id]["config"]["values"]["eta"]
            assert result.objective_value == pytest.approx(
                (1 - 2 * eta) ** 8, abs=1e-14
            )
        history = store.freeze_warm_history(
            "native",
            task_id="quadratic",
            model_family="quadratic",
            task_domain="synthetic",
            objective_key="loss",
        )
        assert store.read_warm_histories() == [history]
