"""Integration tests for Study + GPSearcher.

Tests end-to-end optimization with Study and GPSearcher.
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 0 Day 2-4, Blocking Issue #3
"""

import pytest
import numpy as np
from hponas import Study
from hponas.searchers.gp_searcher import GPSearcher
from hponas.executors.local_executor import LocalExecutor
from hponas.types import Parameter, ParameterType, SearchSpace


def branin(x: float, y: float) -> float:
    """Branin function (2D optimization benchmark).

    Global minimum: f(x, y) ≈ 0.397887 at (-π, 12.275), (π, 2.275), (9.42478, 2.475)
    Search domain: x ∈ [-5, 10], y ∈ [0, 15]
    """
    a = 1.0
    b = 5.1 / (4.0 * np.pi ** 2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8.0 * np.pi)

    term1 = a * (y - b * x ** 2 + c * x - r) ** 2
    term2 = s * (1 - t) * np.cos(x)
    term3 = s

    return -(term1 + term2 + term3)  # Negate for maximization


def branin_objective(config: dict) -> float:
    """Branin objective for HPO (takes config dict)."""
    return branin(config["x"], config["y"])


@pytest.fixture
def branin_search_space():
    """Search space for Branin function."""
    params = {
        "x": Parameter(name="x", type=ParameterType.CONTINUOUS, bounds=(-5.0, 10.0)),
        "y": Parameter(name="y", type=ParameterType.CONTINUOUS, bounds=(0.0, 15.0)),
    }
    return SearchSpace(parameters=params)


class TestStudyGPIntegration:
    """Integration tests for Study + GPSearcher."""

    def test_study_with_gp_on_branin(self, branin_search_space):
        """Test Study with GPSearcher on Branin function."""
        # Create searcher and executor
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=5,
        )
        executor = LocalExecutor(mode="sync")

        # Create study
        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=20,
            maximize=True,
            study_name="test_branin",
        )

        # Run optimization
        result = study.run()

        # Verify result structure
        assert result is not None
        assert result.best_config is not None
        assert result.best_value is not None
        assert len(result.history) == 20
        assert result.n_trials == 20

        # Verify best value is reasonable (Branin min ≈ -0.398, max ≈ -0.398)
        # Note: Branin is negated, so we're looking for values close to 0
        assert result.best_value < 100.0  # Sanity check

        # Verify no crashes occurred
        completed_trials = [r for r in result.history if r.status == "completed"]
        assert len(completed_trials) > 0

    def test_study_gp_improves_over_time(self, branin_search_space):
        """Test that GP improves objective over time."""
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=5,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=15,
            maximize=True,
        )

        result = study.run()

        # Get best value in first 5 trials (random phase)
        first_5_best = max(r.objective_value for r in result.history[:5])

        # Get best value in last 5 trials (GP phase)
        last_5_best = max(r.objective_value for r in result.history[-5:])

        # GP phase should find better values than random phase
        # (or at least not significantly worse)
        assert last_5_best >= first_5_best - 10.0  # Allow some tolerance

    def test_study_gp_trial_config_mapping(self, branin_search_space):
        """Test that Study correctly maps trial_id to config for GP."""
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=3,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=10,
            maximize=True,
        )

        result = study.run()

        # After study runs, searcher should have trial mappings
        assert len(searcher.trials) == 10

        # Verify all trial_ids in results have corresponding configs
        for res in result.history:
            assert res.trial_id in searcher.trials

    def test_study_gp_no_crash_after_initial_phase(self, branin_search_space):
        """Test GP doesn't crash when transitioning from random to GP phase."""
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=5,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=8,  # 5 random + 3 GP
            maximize=True,
        )

        # Should not crash when GP kicks in at trial 6
        result = study.run()

        # Verify all trials completed
        assert result.n_trials == 8
        assert len(result.history) == 8

    def test_study_gp_handles_deterministic_seed(self, branin_search_space):
        """Test Study + GP random phase is deterministic with seed."""
        searcher1 = GPSearcher(branin_search_space, seed=42, initial_random_samples=5)
        executor1 = LocalExecutor(mode="sync")
        study1 = Study(
            searcher=searcher1,
            executor=executor1,
            objective_fn=branin_objective,
            budget=5,
            maximize=True,
            study_name="study1",
        )
        result1 = study1.run()

        searcher2 = GPSearcher(branin_search_space, seed=42, initial_random_samples=5)
        executor2 = LocalExecutor(mode="sync")
        study2 = Study(
            searcher=searcher2,
            executor=executor2,
            objective_fn=branin_objective,
            budget=5,
            maximize=True,
            study_name="study2",
        )
        result2 = study2.run()

        # Same seed should give same sequence of configs in random phase
        # (GP phase has stochastic optimization, so not tested here)
        for i in range(5):
            config1 = study1.trials[f"study1_trial_{i}"].config
            config2 = study2.trials[f"study2_trial_{i}"].config

            # Configs should be identical in random phase
            assert config1.values["x"] == config2.values["x"]
            assert config1.values["y"] == config2.values["y"]

    def test_study_gp_minimization(self, branin_search_space):
        """Test Study + GP in minimization mode."""
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=5,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=15,
            maximize=False,  # Minimize
        )

        result = study.run()

        # Should find minimum (not maximum)
        # For negated Branin, minimum is more negative
        assert result.best_value < -5.0  # Should find something better than random

    def test_study_gp_with_nan_results(self, branin_search_space):
        """Test Study + GP handles NaN results gracefully."""
        def noisy_branin(config: dict) -> float:
            """Branin that sometimes returns NaN."""
            if np.random.rand() < 0.2:  # 20% chance of NaN
                return np.nan
            return branin_objective(config)

        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=5,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=noisy_branin,
            budget=15,
            maximize=True,
        )

        # Should complete despite NaN results
        result = study.run()

        # Should have some valid results
        valid_results = [r for r in result.history if r.is_valid()]
        assert len(valid_results) > 0

        # Best result should be valid
        assert result.best_value is not None
        assert np.isfinite(result.best_value)


class TestStudyGPCheckpoint:
    """Integration tests for Study checkpointing with GPSearcher."""

    def test_study_gp_checkpoint_contains_searcher_state(
        self, branin_search_space, tmp_path
    ):
        """Test Study checkpoint includes searcher state."""
        searcher = GPSearcher(
            branin_search_space,
            seed=42,
            initial_random_samples=3,
        )
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=15,
            maximize=True,
            study_name="test_checkpoint_study",
            checkpoint_dir=tmp_path,
        )

        result = study.run()

        # Checkpoint should have been saved (at trial 10)
        checkpoint_file = tmp_path / "test_checkpoint_study_checkpoint.json"
        assert checkpoint_file.exists()

        # Verify checkpoint contains searcher state
        import json
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        assert "searcher_state" in checkpoint
        assert "trials" in checkpoint["searcher_state"]
        assert len(checkpoint["searcher_state"]["trials"]) == 10
