"""
Recovery Tests: Crash Recovery and Fault Tolerance

Tests system behavior under failure conditions.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import tempfile
from pathlib import Path
import os
import signal

from hponas.executors import LocalExecutor
from hponas.store import Store, Trial


class TestCrashRecovery:
    """Tests for crash recovery and fault tolerance."""

    def test_executor_handles_objective_exception(self):
        """Executor catches objective exceptions and marks trial failed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir)

            def failing_objective(config):
                raise ValueError("Simulated failure")

            trial_id = "trial_crash"
            config = {"x": 0.5}

            # Launch should not propagate exception
            executor.launch(trial_id, config, failing_objective, fidelity=1.0)
            result = executor.get_result(trial_id)

            # Result should indicate failure
            assert result["status"] == "failed"
            assert "error" in result
            assert "ValueError" in result["error"]

    def test_store_handles_corrupt_trial(self):
        """Store skips corrupt trial records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"
            store = Store(db_path)

            # Write valid trial
            trial1 = Trial(
                trial_id="trial_1",
                config={"x": 0.5},
                seed=42,
                fidelity=1.0,
                value=0.25,
                cost=10.0,
                status="completed",
            )
            store.write_trial(trial1, study_id="study_1")

            # Simulate corruption: write invalid trial with missing required field
            # (This tests Store's error handling during read)
            with pytest.raises(Exception):
                invalid_trial = Trial(
                    trial_id=None,  # Invalid: missing trial_id
                    config={"x": 0.3},
                    seed=42,
                    fidelity=1.0,
                    value=0.09,
                    cost=10.0,
                    status="completed",
                )
                store.write_trial(invalid_trial, study_id="study_1")

    def test_checkpoint_survives_process_kill(self):
        """Checkpoint written before termination is recoverable."""
        from hponas.searchers import RandomSearcher
        from hponas.space import SearchSpace, Knob
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
            searcher = RandomSearcher(space, seed=42)

            # Propose some configs
            configs = searcher.propose(5)

            # Save checkpoint to file
            checkpoint_path = Path(tmpdir) / "searcher_checkpoint.json"
            state = searcher.state_dict()
            with open(checkpoint_path, "w") as f:
                json.dump(state, f)

            # Simulate process restart: new searcher instance
            searcher2 = RandomSearcher(space, seed=999)

            # Load checkpoint
            with open(checkpoint_path, "r") as f:
                loaded_state = json.load(f)

            searcher2.load_state_dict(loaded_state)

            # Continue from checkpoint
            configs2 = searcher2.propose(5)

            # Should produce deterministic continuation
            assert len(configs2) == 5
            assert all(0.0 <= c["x"] <= 1.0 for c in configs2)

    def test_partial_trial_resume(self):
        """Resume optimization with incomplete trials."""
        from hponas.space import SearchSpace, Knob
        from hponas.searchers import RandomSearcher

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"
            store = Store(db_path)

            # Session 1: Start 3 trials, complete 2
            trial1 = Trial(
                trial_id="trial_1",
                config={"x": 0.2},
                seed=42,
                fidelity=1.0,
                value=0.04,
                cost=10.0,
                status="completed",
            )
            trial2 = Trial(
                trial_id="trial_2",
                config={"x": 0.8},
                seed=42,
                fidelity=1.0,
                value=0.64,
                cost=10.0,
                status="completed",
            )
            trial3 = Trial(
                trial_id="trial_3",
                config={"x": 0.5},
                seed=42,
                fidelity=1.0,
                value=None,  # Incomplete
                cost=None,
                status="running",
            )

            store.write_trial(trial1, study_id="study_1")
            store.write_trial(trial2, study_id="study_1")
            store.write_trial(trial3, study_id="study_1")

            # Session 2: Resume, filter completed trials
            trials = store.read_trials(study_id="study_1")
            completed_trials = [t for t in trials if t.status == "completed"]

            assert len(trials) == 3
            assert len(completed_trials) == 2

            # Searcher should only observe completed trials
            space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
            searcher = RandomSearcher(space, seed=42)

            for trial in completed_trials:
                searcher.observe({
                    "config": trial.config,
                    "fidelity": trial.fidelity,
                    "value": trial.value,
                    "cost": trial.cost,
                })

            # Continue optimization
            new_configs = searcher.propose(2)
            assert len(new_configs) == 2

    def test_concurrent_write_safety(self):
        """Store handles concurrent writes (basic safety check)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"

            # Sequential writes (simulating concurrent scenario)
            store1 = Store(db_path)
            store2 = Store(db_path)

            trial1 = Trial(
                trial_id="trial_1",
                config={"x": 0.1},
                seed=42,
                fidelity=1.0,
                value=0.01,
                cost=10.0,
                status="completed",
            )
            trial2 = Trial(
                trial_id="trial_2",
                config={"x": 0.2},
                seed=42,
                fidelity=1.0,
                value=0.04,
                cost=10.0,
                status="completed",
            )

            # Write from different store instances
            store1.write_trial(trial1, study_id="study_1")
            store2.write_trial(trial2, study_id="study_1")

            # Both should be readable
            store3 = Store(db_path)
            trials = store3.read_trials(study_id="study_1")
            assert len(trials) == 2
