"""
Scale Tests: Distributed Execution and Large Workloads

Tests scalability under load.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import tempfile
from pathlib import Path
import time
import concurrent.futures

from hponas.executors import LocalExecutor
from hponas.store import Store, Trial
from hponas.searchers import RandomSearcher, SobolSearcher
from hponas.space import SearchSpace, Knob


class TestDistributedExecution:
    """Tests for distributed/parallel execution."""

    def test_local_executor_parallel_trials(self):
        """LocalExecutor runs multiple trials in parallel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = LocalExecutor(checkpoint_dir=tmpdir, max_workers=4)

            def slow_objective(config):
                time.sleep(0.1)  # Simulate work
                return config["x"]**2

            # Launch 8 trials
            trial_ids = [f"trial_{i}" for i in range(8)]
            configs = [{"x": float(i) / 10.0} for i in range(8)]

            start_time = time.time()
            for trial_id, config in zip(trial_ids, configs):
                executor.launch(trial_id, config, slow_objective, fidelity=1.0)

            # Wait for all results
            results = [executor.get_result(tid) for tid in trial_ids]
            elapsed = time.time() - start_time

            # With 4 workers, 8 trials should take ~0.2s (not 0.8s sequential)
            assert elapsed < 0.5  # Allow margin
            assert all(r["status"] == "completed" for r in results)

    def test_store_handles_concurrent_writes(self):
        """Store safely handles concurrent writes from multiple workers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"

            def write_trial(trial_id):
                store = Store(db_path)
                trial = Trial(
                    trial_id=trial_id,
                    config={"x": float(trial_id.split("_")[1])},
                    seed=42,
                    fidelity=1.0,
                    value=float(trial_id.split("_")[1])**2,
                    cost=10.0,
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

            # Launch 20 concurrent writes
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                trial_ids = [f"trial_{i}" for i in range(20)]
                futures = [pool.submit(write_trial, tid) for tid in trial_ids]
                concurrent.futures.wait(futures)

            # All trials should be written
            store = Store(db_path)
            trials = store.read_trials(study_id="study_1")
            assert len(trials) == 20

    def test_large_batch_proposal(self):
        """Searcher handles large batch sizes efficiently."""
        space = SearchSpace([
            Knob("x1", "continuous", (0.0, 1.0)),
            Knob("x2", "continuous", (0.0, 1.0)),
            Knob("x3", "continuous", (0.0, 1.0)),
            Knob("x4", "continuous", (0.0, 1.0)),
            Knob("x5", "continuous", (0.0, 1.0)),
        ])

        searcher = SobolSearcher(space, seed=42)

        # Propose 1000 configs
        start_time = time.time()
        configs = searcher.propose(1000)
        elapsed = time.time() - start_time

        assert len(configs) == 1000
        assert elapsed < 1.0  # Should be fast (<1 second)

        # Verify bounds
        for config in configs:
            for key in ["x1", "x2", "x3", "x4", "x5"]:
                assert 0.0 <= config[key] <= 1.0

    def test_high_dimensional_search_space(self):
        """Searcher handles high-dimensional spaces (50D)."""
        knobs = [Knob(f"x{i}", "continuous", (0.0, 1.0)) for i in range(50)]
        space = SearchSpace(knobs)

        searcher = RandomSearcher(space, seed=42)

        # Propose 100 configs
        configs = searcher.propose(100)

        assert len(configs) == 100
        assert all(len(c) == 50 for c in configs)

        # Verify all dimensions respect bounds
        for config in configs:
            for i in range(50):
                assert 0.0 <= config[f"x{i}"] <= 1.0

    def test_store_large_trial_count(self):
        """Store handles thousands of trials."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"
            store = Store(db_path)

            # Write 5000 trials
            for i in range(5000):
                trial = Trial(
                    trial_id=f"trial_{i}",
                    config={"x": float(i) / 5000.0},
                    seed=42,
                    fidelity=1.0,
                    value=float(i)**2,
                    cost=10.0,
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

            # Read all trials
            start_time = time.time()
            trials = store.read_trials(study_id="study_1")
            elapsed = time.time() - start_time

            assert len(trials) == 5000
            assert elapsed < 5.0  # Read should be reasonably fast

    def test_memory_efficient_observation_history(self):
        """Searcher handles large observation histories efficiently."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        # Observe 10000 trials
        for i in range(10000):
            config = {"x": float(i) / 10000.0}
            searcher.observe({
                "config": config,
                "fidelity": 1.0,
                "value": config["x"]**2,
                "cost": 10.0,
            })

        # State dict should still be manageable
        state = searcher.state_dict()
        assert "history" in state or "n_proposed" in state

        # Propose more configs (should not be prohibitively slow)
        start_time = time.time()
        new_configs = searcher.propose(100)
        elapsed = time.time() - start_time

        assert len(new_configs) == 100
        assert elapsed < 1.0
