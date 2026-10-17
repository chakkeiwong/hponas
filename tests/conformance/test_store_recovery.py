"""Local SQLite recovery contracts (master TST-01).

Backup/restore and arbitrary corruption repair are tracked under OPS-01; they
are not Store APIs. These tests exercise committed-state durability, transaction
visibility, serialized local writers, and detection of malformed stored data.
"""

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import sqlite3
import threading

import pytest

from hponas.store import Store, Trial
from tests.unit.test_store_snapshot_contract import snapshot


def _pause_during_snapshot(path, connection):
    store = Store(path)
    state = store.load_study_snapshot("snap")
    state["budget"] = 77

    def pause(sql):
        if sql.startswith("INSERT OR REPLACE INTO trials"):
            connection.send("uncommitted")
            connection.recv()

    store._conn.set_trace_callback(pause)
    store.save_study_snapshot(state)
    store.close()


def test_failed_snapshot_write_is_atomic_across_all_projections(tmp_path):
    store = Store(tmp_path / "atomic.db")
    try:
        original = snapshot()
        store.save_study_snapshot(original)
        previous_trials = store.read_trials("snap")
        broken = copy.deepcopy(original)
        broken["budget"] = 77
        broken["trials"]["pending"]["status"] = None
        with pytest.raises(sqlite3.IntegrityError):
            store.save_study_snapshot(broken)
        assert store.load_study_snapshot("snap") == original
        assert store.read_study("snap").budget == original["budget"]
        assert store.read_trials("snap") == previous_trials
    finally:
        store.close()


def test_killed_writer_preserves_the_previous_committed_snapshot(tmp_path):
    path = tmp_path / "killed.db"
    store = Store(path)
    original = snapshot()
    store.save_study_snapshot(original)
    before_trials = store.read_trials("snap")
    before_artifacts = store.read_artifacts("base")
    store.close()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_pause_during_snapshot, args=(str(path), child))
    try:
        process.start()
        child.close()
        assert parent.poll(15), "writer did not reach the uncommitted transaction"
        assert parent.recv() == "uncommitted"
        process.kill()
        process.join(timeout=5)
        assert not process.is_alive() and process.exitcode == -9
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        parent.close()
        child.close()
    reopened = Store(path)
    try:
        assert reopened.load_study_snapshot("snap") == original
        assert reopened.read_study("snap").budget == original["budget"]
        assert reopened.read_trials("snap") == before_trials
        assert reopened.read_artifacts("base") == before_artifacts
        assert reopened._conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        reopened.close()


def test_readers_never_observe_part_of_an_uncommitted_snapshot(tmp_path):
    path = tmp_path / "visibility.db"
    reader = Store(path)
    original = snapshot()
    reader.save_study_snapshot(original)
    updated = copy.deepcopy(original)
    updated["budget"] = 77
    updated["trials"]["base"]["config"]["values"] = {"updated": True}
    reached, release = threading.Event(), threading.Event()

    def write():
        writer = Store(path)
        paused = False

        def pause(sql):
            nonlocal paused
            if not paused and sql.startswith("INSERT OR REPLACE INTO trials"):
                paused = True
                reached.set()
                if not release.wait(5):
                    raise RuntimeError("reader did not release writer")

        try:
            writer._conn.set_trace_callback(pause)
            writer.save_study_snapshot(updated)
        finally:
            writer.close()

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(write)
    try:
        assert reached.wait(5)
        assert reader.load_study_snapshot("snap") == original
        assert reader.read_study("snap").budget == original["budget"]
        assert next(
            t for t in reader.read_trials("snap") if t.trial_id == "base"
        ).config == {"x": 0.25}
        release.set()
        future.result(timeout=5)
        assert reader.load_study_snapshot("snap") == updated
        assert reader.read_study("snap").budget == 77
        assert next(
            t for t in reader.read_trials("snap") if t.trial_id == "base"
        ).config == {"updated": True}
    finally:
        release.set()
        pool.shutdown()
        reader.close()


def test_independent_local_connections_serialize_concurrent_writes(tmp_path):
    path = tmp_path / "concurrent.db"
    barrier = threading.Barrier(4)

    def write(worker):
        barrier.wait(timeout=5)
        store = Store(path)
        try:
            for index in range(5):
                tid = f"{worker}-{index}"
                store.write_trial(
                    Trial(tid, {"worker": worker}, worker, 1.0, index, 0.5), "s"
                )
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(write, worker) for worker in range(4)]
        for future in futures:
            future.result(timeout=15)
    store = Store(path)
    try:
        trials = store.read_trials("s")
        assert {t.trial_id for t in trials} == {
            f"{w}-{i}" for w in range(4) for i in range(5)
        }
        assert all(t.config == {"worker": t.seed} for t in trials)
        assert store._conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        store.close()


def test_last_committed_writer_replaces_same_trial_without_duplication(tmp_path):
    path = tmp_path / "last-writer.db"
    first, second = Store(path), Store(path)
    try:
        a = Trial("same", {"x": 1.0}, 1, 1.0, 3.0, 0.5)
        b = Trial("same", {"x": 2.0}, 2, 4.0, 1.0, 1.5, "parent", "completed")
        first.write_trial(a, "s")
        assert second.read_trials("s") == [a]
        second.write_trial(b, "s")
        assert first.read_trials("s") == [b]
    finally:
        first.close()
        second.close()


def test_invalid_database_and_snapshot_payload_raise_without_silent_reset(tmp_path):
    path = tmp_path / "corrupt.db"
    corrupt = b"invalid SQLite database" * 128
    path.write_bytes(corrupt)
    with pytest.raises(sqlite3.DatabaseError):
        Store(path)
    assert path.read_bytes() == corrupt
    store = Store(tmp_path / "payload.db")
    try:
        store.save_study_snapshot(snapshot())
        with store._conn:
            store._conn.execute(
                "UPDATE study_snapshots SET payload=? WHERE study_id=?",
                ("{broken", "snap"),
            )
        with pytest.raises(json.JSONDecodeError):
            store.load_study_snapshot("snap")
        assert store._conn.execute(
            "SELECT payload FROM study_snapshots WHERE study_id='snap'"
        ).fetchone() == ("{broken",)
    finally:
        store.close()
