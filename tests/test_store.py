"""
Test store: crash recovery and lineage queries.

Survey reference: Ch 15 sec:run-store, Ch 6 (lineage).
R1 spike exit criterion: crash recovery without duplicates, lineage queries work.
"""

import tempfile
from pathlib import Path

from hponas.store import Store, Study, Trial


def test_store_write_and_read_study():
    """Write and read a study record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        study = Study(
            study_id="study_1",
            space_json='{"knobs": []}',
            objective="minimize",
            seed=42,
            budget=100.0,
        )
        store.write_study(study)

        loaded = store.read_study("study_1")
        assert loaded is not None
        assert loaded.study_id == "study_1"
        assert loaded.seed == 42

        store.close()


def test_store_write_and_read_trials():
    """Write and read trial records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "test.db")

        # Write study first
        study = Study(
            study_id="study_1",
            space_json='{"knobs": []}',
            objective="minimize",
            seed=42,
            budget=100.0,
        )
        store.write_study(study)

        # Write trials
        trial1 = Trial(
            trial_id="trial_1",
            config={"x": 1.0},
            seed=42,
            fidelity=1.0,
            value=0.5,
            cost=10.0,
        )
        store.write_trial(trial1, "study_1")

        trial2 = Trial(
            trial_id="trial_2",
            config={"x": 2.0},
            seed=42,
            fidelity=1.0,
            value=0.3,
            cost=12.0,
        )
        store.write_trial(trial2, "study_1")

        # Read trials
        trials = store.read_trials("study_1")
        assert len(trials) == 2
        assert trials[0].trial_id == "trial_1"
        assert trials[1].trial_id == "trial_2"

        store.close()


def test_store_crash_recovery():
    """
    Crash recovery test: store survives restart without duplicates.

    R1 spike exit criterion: coordinator dies, restarts, continues without re-running.
    """
    db_path = None
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "crash_test.db"

        # First session: write study and 2 trials
        store1 = Store(db_path)
        study = Study(
            study_id="study_crash",
            space_json='{"knobs": []}',
            objective="minimize",
            seed=42,
            budget=100.0,
        )
        store1.write_study(study)

        store1.write_trial(
            Trial("trial_1", {"x": 1.0}, 42, 1.0, 0.5, 10.0),
            "study_crash",
        )
        store1.write_trial(
            Trial("trial_2", {"x": 2.0}, 42, 1.0, 0.3, 12.0),
            "study_crash",
        )
        store1.close()

        # Simulate crash: open new store instance on same DB
        store2 = Store(db_path)

        # Read existing trials (should have 2)
        trials_before = store2.read_trials("study_crash")
        assert len(trials_before) == 2

        # Add a new trial (continuing after "crash")
        store2.write_trial(
            Trial("trial_3", {"x": 3.0}, 42, 1.0, 0.7, 11.0),
            "study_crash",
        )

        # Read all trials (should have 3, no duplicates)
        trials_after = store2.read_trials("study_crash")
        assert len(trials_after) == 3
        assert trials_after[0].trial_id == "trial_1"
        assert trials_after[1].trial_id == "trial_2"
        assert trials_after[2].trial_id == "trial_3"

        store2.close()


def test_store_lineage():
    """
    Lineage queries for population methods (Ch 15, Ch 6).

    Survey: with the parent pointer, a hyperparameter schedule is a walk up the tree.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "lineage.db")

        study = Study("study_1", '{}', "minimize", 42, 100.0)
        store.write_study(study)

        # Create lineage: trial_3 → trial_2 → trial_1 → None
        store.write_trial(
            Trial("trial_1", {"lr": 0.01}, 42, 1.0, 0.5, 10.0, parent_trial_id=None),
            "study_1",
        )
        store.write_trial(
            Trial("trial_2", {"lr": 0.005}, 42, 2.0, 0.3, 12.0, parent_trial_id="trial_1"),
            "study_1",
        )
        store.write_trial(
            Trial("trial_3", {"lr": 0.002}, 42, 3.0, 0.2, 15.0, parent_trial_id="trial_2"),
            "study_1",
        )

        # Query lineage from trial_3
        lineage = store.lineage("trial_3")
        assert lineage == ["trial_3", "trial_2", "trial_1"]

        # Query lineage from trial_1 (root)
        lineage_root = store.lineage("trial_1")
        assert lineage_root == ["trial_1"]

        store.close()


def test_store_upsert():
    """Store upserts (INSERT OR REPLACE) allow updating trials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(Path(tmpdir) / "upsert.db")

        study = Study("study_1", '{}', "minimize", 42, 100.0)
        store.write_study(study)

        # Write trial
        trial = Trial("trial_1", {"x": 1.0}, 42, 1.0, 0.5, 10.0, status="running")
        store.write_trial(trial, "study_1")

        # Update trial (same trial_id, new value)
        trial_updated = Trial("trial_1", {"x": 1.0}, 42, 1.0, 0.4, 12.0, status="completed")
        store.write_trial(trial_updated, "study_1")

        # Should have only 1 trial (not 2)
        trials = store.read_trials("study_1")
        assert len(trials) == 1
        assert trials[0].value == 0.4
        assert trials[0].status == "completed"

        store.close()
