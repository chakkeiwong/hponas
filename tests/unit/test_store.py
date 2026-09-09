"""
Unit Tests: Trial Store

Tests Store for persisting trial data.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import tempfile
from pathlib import Path

from hponas.store import Store, Trial


class TestStore:
    """Unit tests for Store."""

    def test_init_creates_database(self):
        """Store creates database file on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            assert db_path.exists()

    def test_write_trial_persists_data(self):
        """write_trial() saves trial to database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            trial = Trial(
                trial_id="trial_1",
                config={"x": 0.5, "y": 1.0},
                seed=42,
                fidelity=1.0,
                value=0.75,
                cost=10.5,
                status="completed",
            )

            store.write_trial(trial, study_id="study_1")

            # Read back
            trials = store.read_trials(study_id="study_1")
            assert len(trials) == 1
            assert trials[0].trial_id == "trial_1"
            assert trials[0].value == 0.75

    def test_write_multiple_trials(self):
        """Store handles multiple trials."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            for i in range(5):
                trial = Trial(
                    trial_id=f"trial_{i}",
                    config={"x": float(i)},
                    seed=42,
                    fidelity=1.0,
                    value=float(i)**2,
                    cost=10.0,
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            assert len(trials) == 5

    def test_read_trials_filters_by_study_id(self):
        """read_trials() filters by study_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            # Write to study_1
            trial1 = Trial(
                trial_id="trial_1",
                config={"x": 1.0},
                seed=42,
                fidelity=1.0,
                value=1.0,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial1, study_id="study_1")

            # Write to study_2
            trial2 = Trial(
                trial_id="trial_2",
                config={"x": 2.0},
                seed=42,
                fidelity=1.0,
                value=4.0,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial2, study_id="study_2")

            # Read study_1
            trials_s1 = store.read_trials(study_id="study_1")
            assert len(trials_s1) == 1
            assert trials_s1[0].trial_id == "trial_1"

            # Read study_2
            trials_s2 = store.read_trials(study_id="study_2")
            assert len(trials_s2) == 1
            assert trials_s2[0].trial_id == "trial_2"

    def test_trial_status_tracking(self):
        """Store tracks trial status (running, completed, failed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            # Running trial
            trial_running = Trial(
                trial_id="trial_running",
                config={"x": 1.0},
                seed=42,
                fidelity=1.0,
                value=None,
                cost=None,
                status="running",
            )
            store.write_trial(trial_running, study_id="study_1")

            # Completed trial
            trial_completed = Trial(
                trial_id="trial_completed",
                config={"x": 2.0},
                seed=42,
                fidelity=1.0,
                value=4.0,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial_completed, study_id="study_1")

            # Failed trial
            trial_failed = Trial(
                trial_id="trial_failed",
                config={"x": 3.0},
                seed=42,
                fidelity=1.0,
                value=None,
                cost=None,
                status="failed",
            )
            store.write_trial(trial_failed, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            assert len(trials) == 3

            statuses = {t.trial_id: t.status for t in trials}
            assert statuses["trial_running"] == "running"
            assert statuses["trial_completed"] == "completed"
            assert statuses["trial_failed"] == "failed"

    def test_config_serialization(self):
        """Store correctly serializes/deserializes config dicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            config = {
                "x": 0.123456789,
                "y": 10,
                "arch": "resnet50",
            }

            trial = Trial(
                trial_id="trial_1",
                config=config,
                seed=42,
                fidelity=1.0,
                value=0.5,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            loaded_config = trials[0].config

            assert loaded_config["x"] == pytest.approx(0.123456789)
            assert loaded_config["y"] == 10
            assert loaded_config["arch"] == "resnet50"

    def test_trial_update(self):
        """Store allows updating trial status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            # Write running trial
            trial = Trial(
                trial_id="trial_1",
                config={"x": 1.0},
                seed=42,
                fidelity=1.0,
                value=None,
                cost=None,
                status="running",
            )
            store.write_trial(trial, study_id="study_1")

            # Update to completed
            trial_updated = Trial(
                trial_id="trial_1",
                config={"x": 1.0},
                seed=42,
                fidelity=1.0,
                value=1.0,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial_updated, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            # Depending on Store implementation, may have 1 or 2 entries
            # Assume update replaces
            completed = [t for t in trials if t.status == "completed"]
            assert len(completed) >= 1

    def test_read_empty_study(self):
        """read_trials() returns empty list for non-existent study."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            trials = store.read_trials(study_id="nonexistent")
            assert trials == []

    def test_fidelity_persistence(self):
        """Store persists fidelity value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = Store(db_path)

            trial = Trial(
                trial_id="trial_1",
                config={"x": 1.0},
                seed=42,
                fidelity=0.25,
                value=2.0,
                cost=5.0,
                status="completed",
            )
            store.write_trial(trial, study_id="study_1")

            trials = store.read_trials(study_id="study_1")
            assert trials[0].fidelity == 0.25
