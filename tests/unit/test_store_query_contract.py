"""Store queries preserve measurements, ranking, scope and record fields."""

import math
import sqlite3

import pytest

from hponas.store import Store, Study, Trial
import hponas.store as module


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "queries.db")
    yield result
    result.close()


def test_study_upsert_listing_and_observation_queries_preserve_fields(store):
    assert store.list_studies() == []
    assert store.read_study("missing") is None
    first = Study("one", '{"x": 1}', "minimize", 8, 32.0, 7.0, "running")
    second = Study("two", '{"x": 2}', "maximize", 9, 64.0, 3.0, "completed")
    store.write_study(first)
    store.write_study(second)
    assert store.list_studies() == [second, first]
    first.status, first.incumbent_value = "completed", 2.0
    store.write_study(first)
    assert store.list_studies() == [first, second]
    assert store.read_study("one") == first
    store.write_observation("a", 4.0, 7.0, 12.0)
    store.write_observation("a", 1.0, 9.0, 8.0)
    store.write_observation("b", 2.0, 3.0, 5.0)
    assert store.read_observations("a") == [(1.0, 9.0, 8.0), (4.0, 7.0, 12.0)]
    assert store.read_observations("b") == [(2.0, 3.0, 5.0)]
    assert store.read_observations("missing") == []


def test_best_trials_filter_state_scope_and_rank_both_directions(store):
    for tid, value, status in [
        ("a", 5.0, "completed"),
        ("b", -2.0, "completed"),
        ("c", None, "completed"),
        ("d", -99.0, "failed"),
        ("e", 99.0, "running"),
        ("middle", 2.0, "completed"),
    ]:
        store.write_trial(
            Trial(tid, {"x": tid}, 7, 2.0, value, 3.0, status=status), "s"
        )
    store.write_trial(
        Trial("other", {}, 7, 2.0, -100.0, 3.0, status="completed"), "other"
    )
    assert [t.trial_id for t in store.get_best_trials("s", 2)] == ["b", "middle"]
    assert [t.trial_id for t in store.get_best_trials("s", 2, "maximize")] == [
        "a",
        "middle",
    ]
    assert [t.trial_id for t in store.get_best_trials("s", 10)] == [
        "b",
        "middle",
        "a",
        "c",
    ]
    assert [t.trial_id for t in store.get_best_trials("s", 10, "maximize")] == [
        "a",
        "middle",
        "b",
        "c",
    ]
    assert store.get_best_trials("s", 0) == []
    assert store.get_best_trials("missing") == []


def populate_pareto(store):
    for tid, loss, accuracy, status in [
        ("a", 1.0, 5.0, "completed"),
        ("tie", 1.0, 5.0, "completed"),
        ("b", 2.0, 8.0, "completed"),
        ("equal-loss-worse", 1.0, 4.0, "completed"),
        ("equal-accuracy-worse", 2.0, 5.0, "completed"),
        ("dominated", 3.0, 4.0, "completed"),
        ("failed", 0.0, 100.0, "failed"),
    ]:
        # Deliberately misleading configs and scalar value: query must use measurements.
        store.write_trial(
            Trial(tid, {"loss": -loss}, 2, 1.0, 99.0, 7.0, status=status), "s"
        )
        store.write_objectives(tid, {"loss": loss, "accuracy": accuracy})


def test_pareto_queries_use_named_measurements_directions_and_keep_ties(store):
    populate_pareto(store)
    front = store.get_pareto_front("s", ["loss", "accuracy"], ["minimize", "maximize"])
    assert {t.trial_id for t in front} == {"a", "tie", "b"}
    store.write_objectives("dominated", {"loss": 0.5, "accuracy": 10.0})
    assert [
        t.trial_id
        for t in store.get_pareto_front(
            "s", ["loss", "accuracy"], ["minimize", "maximize"]
        )
    ] == ["dominated"]
    assert store.get_pareto_front("missing", ["value", "cost"]) == []


def test_pareto_builtin_measurements_default_to_minimization(store):
    for tid, value, cost in [("a", 1.0, 5.0), ("b", 2.0, 3.0), ("c", 3.0, 8.0)]:
        store.write_trial(Trial(tid, {}, 2, 1.0, value, cost, status="completed"), "s")
    assert {t.trial_id for t in store.get_pareto_front("s", ["value", "cost"])} == {
        "a",
        "b",
    }


@pytest.mark.parametrize(
    "objectives,directions",
    [
        ([], None),
        (["value", "value"], None),
        (["value"], ["wrong"]),
        (["value", "cost"], ["minimize"]),
    ],
)
def test_invalid_pareto_query_is_rejected(store, objectives, directions):
    with pytest.raises(ValueError):
        store.get_pareto_front("s", objectives, directions)


@pytest.mark.parametrize(
    "measurements",
    [{}, {"loss": float("nan")}, {"loss": float("inf")}, {"loss": -float("inf")}],
)
def test_nonfinite_or_empty_objective_measurements_do_not_replace_good_values(
    store, measurements
):
    populate_pareto(store)
    before = store.get_pareto_front("s", ["loss", "accuracy"])
    with pytest.raises(ValueError, match="finite"):
        store.write_objectives("a", measurements)
    assert store.get_pareto_front("s", ["loss", "accuracy"]) == before


def test_missing_or_nonfinite_requested_measurement_is_not_a_front(store):
    store.write_trial(
        Trial("a", {"missing": 1.0}, 0, 1.0, math.inf, 2.0, status="completed"), "s"
    )
    with pytest.raises(ValueError, match="Missing objective"):
        store.get_pareto_front("s", ["missing"])
    with pytest.raises(ValueError, match="Nonfinite"):
        store.get_pareto_front("s", ["value"])
    store.write_trial(Trial("a", {}, 0, 1.0, None, 2.0, status="completed"), "s")
    with pytest.raises(ValueError, match="Nonfinite"):
        store.get_pareto_front("s", ["value"])


@pytest.mark.parametrize("trial_id", [None, ""])
def test_invalid_trial_identity_is_rejected_without_a_row(store, trial_id):
    with pytest.raises(ValueError, match="trial_id"):
        store.write_trial(Trial(trial_id, {}, 0, 1.0, 1.0, 1.0), "s")
    assert store.read_trials("s") == []


def test_unknown_lineage_and_empty_artifact_metadata(store):
    assert store.lineage("missing") == ["missing"]
    store.write_artifact("a", "model", "model.pt", {})
    assert store.read_artifacts("a")[0]["metadata"] is None


def test_new_store_creates_nested_directory_and_enables_wal(tmp_path):
    store = Store(tmp_path / "new" / "nested" / "store.db")
    try:
        assert store.db_path.exists()
        assert store._conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        store.close()


class JournalFailure:
    def __init__(self, connection, error, failures):
        self.connection, self.error, self.failures = connection, error, failures
        self.attempts = 0

    def execute(self, sql, *args):
        if "journal_mode" in sql.lower():
            self.attempts += 1
            if self.attempts <= self.failures:
                raise self.error
        return self.connection.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.connection, name)


@pytest.mark.parametrize(
    "code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY | (2 << 8)]
)
def test_transient_journal_lock_retries_and_finishes_schema(
    tmp_path, monkeypatch, code
):
    path = tmp_path / "transient.db"
    connection = sqlite3.connect(path)
    error = sqlite3.OperationalError("busy")
    error.sqlite_errorcode = code
    wrapped = JournalFailure(connection, error, failures=1)
    monkeypatch.setattr(module.sqlite3, "connect", lambda path: wrapped)
    monkeypatch.setattr(module.time, "monotonic", lambda: 10.0)
    waits = []
    monkeypatch.setattr(module.time, "sleep", waits.append)
    store = Store(path)
    try:
        assert wrapped.attempts == 2
        assert len(waits) == 1 and 0 < waits[0] < 0.1
        assert store._conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert store.list_studies() == []
    finally:
        store.close()


@pytest.mark.parametrize("code", [None, sqlite3.SQLITE_IOERR, sqlite3.SQLITE_BUSY])
def test_journal_errors_close_connection_and_busy_retry_has_five_second_cap(
    tmp_path, monkeypatch, code
):
    path = tmp_path / "failure.db"
    connection = sqlite3.connect(path)
    error = sqlite3.OperationalError("injected journal error")
    if code is not None:
        error.sqlite_errorcode = code
    wrapped = JournalFailure(connection, error, failures=2)
    monkeypatch.setattr(module.sqlite3, "connect", lambda path: wrapped)
    clock = iter([10.0, 15.0]) if code == sqlite3.SQLITE_BUSY else iter([10.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        module.time, "sleep", lambda _: pytest.fail("must fail without another retry")
    )
    with pytest.raises(sqlite3.OperationalError) as caught:
        Store(path)
    assert caught.value is error and wrapped.attempts == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_best_trials_default_limit_is_ten(store):
    for i in range(12):
        store.write_trial(
            Trial(str(i), {}, 0, 1.0, float(i), 1.0, status="completed"), "s"
        )
    assert [t.value for t in store.get_best_trials("s")] == list(range(10))


@pytest.mark.parametrize("direction,best", [("minimize", "a"), ("maximize", "b")])
def test_pareto_order_preserves_large_finite_values_without_rescaling(
    store, direction, best
):
    for tid, value in [("a", 1e308), ("b", 1.2e308)]:
        store.write_trial(Trial(tid, {}, 0, 1.0, value, 1.0, status="completed"), "s")
    assert [
        t.trial_id
        for t in store.get_pareto_front("s", ["value", "cost"], [direction, "minimize"])
    ] == [best]
