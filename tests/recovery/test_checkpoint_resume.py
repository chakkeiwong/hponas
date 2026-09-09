"""
Recovery Tests: Checkpoint and Resume

Tests deterministic recovery from saved state.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import tempfile
from pathlib import Path
import numpy as np

from hponas.searchers import RandomSearcher, SobolSearcher
from hponas.schedulers import ASHAScheduler, ASHAConfig
from hponas.store import Store, Trial


class TestCheckpointResume:
    """Tests for deterministic checkpoint and resume."""

    def test_random_searcher_resume_deterministic(self):
        """RandomSearcher resume from checkpoint produces same sequence."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "continuous", (0.0, 1.0)),
        ])

        # Original run: propose 5, save, propose 5 more
        searcher1 = RandomSearcher(space, seed=42)
        batch1_orig = searcher1.propose(5)
        state = searcher1.state_dict()
        batch2_orig = searcher1.propose(5)

        # Resume run: load state, propose 5
        searcher2 = RandomSearcher(space, seed=999)  # Different seed
        searcher2.load_state_dict(state)
        batch2_resumed = searcher2.propose(5)

        # Resumed batch must match original batch
        for i in range(5):
            assert batch2_orig[i] == batch2_resumed[i]

    def test_sobol_searcher_resume_deterministic(self):
        """SobolSearcher resume from checkpoint produces same sequence."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "continuous", (0.0, 1.0)),
        ])

        # Original run
        searcher1 = SobolSearcher(space, seed=42)
        batch1 = searcher1.propose(10)
        state = searcher1.state_dict()
        batch2_orig = searcher1.propose(10)

        # Resume run
        searcher2 = SobolSearcher(space, seed=999)
        searcher2.load_state_dict(state)
        batch2_resumed = searcher2.propose(10)

        # Must match exactly
        for i in range(10):
            assert batch2_orig[i] == batch2_resumed[i]

    def test_asha_scheduler_resume_preserves_rungs(self):
        """ASHAScheduler resume restores rung state."""
        config = ASHAConfig(eta=3, r_min=1.0, r_max=9.0)
        scheduler1 = ASHAScheduler(config)

        # Report some trials
        scheduler1.report("trial_1", 1.0, 0.5)
        scheduler1.report("trial_2", 1.0, 0.8)
        scheduler1.report("trial_3", 1.0, 0.3)

        # Save state
        state = scheduler1.state_dict()

        # Resume in new scheduler
        scheduler2 = ASHAScheduler(config)
        scheduler2.load_state_dict(state)

        # Promote: should see same trials
        promoted1 = scheduler1.promote()
        promoted2 = scheduler2.promote()

        assert set(promoted1) == set(promoted2)

    def test_store_resume_after_crash(self):
        """Store persists trials across process restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study.db"

            # Session 1: Write 3 trials
            store1 = Store(db_path)
            for i in range(3):
                trial = Trial(
                    trial_id=f"trial_{i}",
                    config={"x": float(i)},
                    seed=42,
                    fidelity=1.0,
                    value=float(i)**2,
                    cost=10.0,
                    status="completed",
                )
                store1.write_trial(trial, study_id="study_1")

            # Session 2: New Store instance, read trials
            store2 = Store(db_path)
            trials = store2.read_trials(study_id="study_1")

            assert len(trials) == 3
            assert trials[0].trial_id == "trial_0"
            assert trials[2].value == 4.0

    def test_full_optimization_resume(self):
        """Full optimization loop resumes mid-run."""
        from hponas.space import SearchSpace, Knob

        with tempfile.TemporaryDirectory() as tmpdir:
            space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
            db_path = Path(tmpdir) / "study.db"

            # Session 1: Run 5 trials
            searcher1 = RandomSearcher(space, seed=42)
            store1 = Store(db_path)

            for i in range(5):
                configs = searcher1.propose(1)
                config = configs[0]
                value = config["x"]**2

                trial = Trial(
                    trial_id=f"trial_{i}",
                    config=config,
                    seed=42,
                    fidelity=1.0,
                    value=value,
                    cost=10.0,
                    status="completed",
                )
                store1.write_trial(trial, study_id="study_1")

                searcher1.observe({
                    "config": config,
                    "fidelity": 1.0,
                    "value": value,
                    "cost": 10.0,
                })

            # Save checkpoint
            searcher_state = searcher1.state_dict()

            # Session 2: Resume and run 5 more trials
            searcher2 = RandomSearcher(space, seed=999)
            searcher2.load_state_dict(searcher_state)
            store2 = Store(db_path)

            # Reload history
            trials = store2.read_trials(study_id="study_1")
            for trial in trials:
                searcher2.observe({
                    "config": trial.config,
                    "fidelity": trial.fidelity,
                    "value": trial.value,
                    "cost": trial.cost,
                })

            # Continue optimization
            for i in range(5, 10):
                configs = searcher2.propose(1)
                config = configs[0]
                value = config["x"]**2

                trial = Trial(
                    trial_id=f"trial_{i}",
                    config=config,
                    seed=42,
                    fidelity=1.0,
                    value=value,
                    cost=10.0,
                    status="completed",
                )
                store2.write_trial(trial, study_id="study_1")

            # Validate: 10 trials total
            all_trials = store2.read_trials(study_id="study_1")
            assert len(all_trials) == 10

    def test_checkpoint_roundtrip_preserves_history(self):
        """Checkpoint → resume → checkpoint produces identical state."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher1 = RandomSearcher(space, seed=42)

        # Propose and observe
        configs = searcher1.propose(10)
        for config in configs:
            searcher1.observe({
                "config": config,
                "fidelity": 1.0,
                "value": config["x"]**2,
                "cost": 10.0,
            })

        # Save state
        state1 = searcher1.state_dict()

        # Resume
        searcher2 = RandomSearcher(space, seed=999)
        searcher2.load_state_dict(state1)

        # Save again
        state2 = searcher2.state_dict()

        # States must match
        assert state1 == state2
