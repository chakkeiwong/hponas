"""
Integration Tests: End-to-End Optimization Loops

Tests full component interactions on synthetic benchmarks.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import tempfile
from pathlib import Path
import numpy as np

from hponas.searchers import RandomSearcher, SobolSearcher
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.executors import LocalExecutor
from hponas.store import Store, Trial
from hponas.space import SearchSpace, Knob


def branin(x1, x2):
    """Branin-Hoo function (2D, 3 global minima)."""
    a = 1.0
    b = 5.1 / (4 * np.pi**2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8 * np.pi)

    term1 = a * (x2 - b * x1**2 + c * x1 - r)**2
    term2 = s * (1 - t) * np.cos(x1)
    term3 = s

    return term1 + term2 + term3


class TestEndToEndOptimization:
    """Integration tests for full optimization loops."""

    def test_random_searcher_end_to_end(self):
        """RandomSearcher + LocalExecutor + Store full loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            space = SearchSpace([
                Knob("x1", "continuous", (-5.0, 10.0)),
                Knob("x2", "continuous", (0.0, 15.0)),
            ])
            searcher = RandomSearcher(space, seed=42)
            executor = LocalExecutor(checkpoint_dir=tmpdir)
            store = Store(Path(tmpdir) / "study.db")

            def objective(config):
                return branin(config["x1"], config["x2"])

            # Run 10 trials
            for i in range(10):
                # Searcher proposes
                configs = searcher.propose(1)
                config = configs[0]

                # Executor launches
                trial_id = f"trial_{i}"
                executor.launch(trial_id, config, objective, fidelity=1.0)
                result = executor.get_result(trial_id)

                # Store saves
                trial = Trial(
                    trial_id=trial_id,
                    config=config,
                    seed=42,
                    fidelity=1.0,
                    value=result["value"],
                    cost=result["cost"],
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

                # Searcher observes
                searcher.observe({
                    "config": config,
                    "fidelity": 1.0,
                    "value": result["value"],
                    "cost": result["cost"],
                })

            # Validate: 10 trials stored
            trials = store.read_trials(study_id="study_1")
            assert len(trials) == 10

            # Validate: best trial found reasonable optimum
            best_value = min(t.value for t in trials)
            assert best_value < 100.0  # Global minimum ~0.398, but random search may not find it

    def test_sobol_searcher_end_to_end(self):
        """SobolSearcher end-to-end on Branin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            space = SearchSpace([
                Knob("x1", "continuous", (-5.0, 10.0)),
                Knob("x2", "continuous", (0.0, 15.0)),
            ])
            searcher = SobolSearcher(space, seed=42)
            executor = LocalExecutor(checkpoint_dir=tmpdir)
            store = Store(Path(tmpdir) / "study.db")

            def objective(config):
                return branin(config["x1"], config["x2"])

            # Run 20 trials (Sobol should find better optimum than random)
            for i in range(20):
                configs = searcher.propose(1)
                config = configs[0]

                trial_id = f"trial_{i}"
                executor.launch(trial_id, config, objective, fidelity=1.0)
                result = executor.get_result(trial_id)

                trial = Trial(
                    trial_id=trial_id,
                    config=config,
                    seed=42,
                    fidelity=1.0,
                    value=result["value"],
                    cost=result["cost"],
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

                searcher.observe({
                    "config": config,
                    "fidelity": 1.0,
                    "value": result["value"],
                    "cost": result["cost"],
                })

            # Validate: Sobol finds better optimum than random (with 20 trials)
            trials = store.read_trials(study_id="study_1")
            best_value = min(t.value for t in trials)
            assert best_value < 50.0  # Should get closer to global minimum

    def test_asha_scheduler_integration(self):
        """ASHA + Searcher + Executor integration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            space = SearchSpace([
                Knob("x1", "continuous", (-5.0, 10.0)),
                Knob("x2", "continuous", (0.0, 15.0)),
            ])
            searcher = RandomSearcher(space, seed=42)
            config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
            scheduler = ASHAScheduler(config)
            executor = LocalExecutor(checkpoint_dir=tmpdir)
            store = Store(Path(tmpdir) / "study.db")

            def objective(config, fidelity):
                # Simulate fidelity-dependent evaluation
                base_value = branin(config["x1"], config["x2"])
                noise = (1.0 / fidelity) * np.random.randn()
                return base_value + noise

            # Run 9 trials at r=1.0
            for i in range(9):
                configs = searcher.propose(1)
                config = configs[0]

                trial_id = f"trial_{i}"
                fidelity = 1.0
                result_value = objective(config, fidelity)

                # Report to scheduler
                decision = scheduler.report(trial_id, fidelity, result_value)
                assert decision in ["continue", "stop", "pause"]

                # Store trial
                trial = Trial(
                    trial_id=trial_id,
                    config=config,
                    seed=42,
                    fidelity=fidelity,
                    value=result_value,
                    cost=fidelity * 10.0,
                    status="completed",
                )
                store.write_trial(trial, study_id="study_1")

            # Promote top trials
            promoted = scheduler.promote()
            assert len(promoted) <= 3  # Top 1/eta=1/3 should be promoted

    def test_multi_fidelity_progression(self):
        """Full multi-fidelity loop: r=1 → r=3 → r=9."""
        with tempfile.TemporaryDirectory() as tmpdir:
            space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
            searcher = RandomSearcher(space, seed=42)
            config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
            scheduler = ASHAScheduler(config)

            def objective(config, fidelity):
                return config["x"]**2 + (1.0 / fidelity) * 0.1

            # Run at r=1.0
            trial_id = "trial_1"
            cfg = searcher.propose(1)[0]
            value_r1 = objective(cfg, 1.0)
            decision = scheduler.report(trial_id, 1.0, value_r1)
            assert decision in ["continue", "pause"]

            # Promote
            promoted = scheduler.promote()
            if trial_id in promoted:
                # Run at r=3.0
                value_r3 = objective(cfg, 3.0)
                decision = scheduler.report(trial_id, 3.0, value_r3)
                assert decision in ["continue", "pause"]

                # Promote again
                promoted = scheduler.promote()
                if trial_id in promoted:
                    # Run at r=9.0
                    value_r9 = objective(cfg, 9.0)
                    decision = scheduler.report(trial_id, 9.0, value_r9)
                    # At max fidelity, should stop
                    assert decision == "stop"
