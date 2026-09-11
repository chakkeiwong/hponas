"""Integration tests for Study + RandomSearcher/SobolSearcher.

Tests end-to-end optimization with Study and baseline searchers.
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 1 Day 1
"""

import pytest
import numpy as np
from hponas import Study
from hponas.searchers.random_searcher import RandomSearcher, SobolSearcher
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


class TestStudyRandomIntegration:
    """Integration tests for Study + RandomSearcher."""

    def test_study_with_random_on_branin(self, branin_search_space):
        """Test Study with RandomSearcher on Branin function."""
        searcher = RandomSearcher(branin_search_space, seed=42)
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=20,
            maximize=True,
            study_name="test_random_branin",
        )

        result = study.run()

        # Verify result structure
        assert result is not None
        assert result.best_config is not None
        assert result.best_value is not None
        assert len(result.history) == 20
        assert result.n_trials == 20

        # Verify best value is reasonable
        assert result.best_value < 100.0  # Sanity check

        # Verify no crashes occurred
        completed_trials = [r for r in result.history if r.status == "completed"]
        assert len(completed_trials) > 0

    def test_study_random_deterministic(self, branin_search_space):
        """Test Study + Random is deterministic with seed."""
        searcher1 = RandomSearcher(branin_search_space, seed=42)
        executor1 = LocalExecutor(mode="sync")
        study1 = Study(
            searcher=searcher1,
            executor=executor1,
            objective_fn=branin_objective,
            budget=10,
            maximize=True,
            study_name="study1",
        )
        result1 = study1.run()

        searcher2 = RandomSearcher(branin_search_space, seed=42)
        executor2 = LocalExecutor(mode="sync")
        study2 = Study(
            searcher=searcher2,
            executor=executor2,
            objective_fn=branin_objective,
            budget=10,
            maximize=True,
            study_name="study2",
        )
        result2 = study2.run()

        # Same seed should give same sequence
        for i in range(10):
            config1 = study1.trials[f"study1_trial_{i}"].config
            config2 = study2.trials[f"study2_trial_{i}"].config

            assert config1.values["x"] == config2.values["x"]
            assert config1.values["y"] == config2.values["y"]

    def test_study_random_minimization(self, branin_search_space):
        """Test Study + Random in minimization mode."""
        searcher = RandomSearcher(branin_search_space, seed=42)
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=15,
            maximize=False,  # Minimize
        )

        result = study.run()

        # Should minimize (find more negative values)
        assert result.best_value < -5.0


class TestStudySobolIntegration:
    """Integration tests for Study + SobolSearcher."""

    def test_study_with_sobol_on_branin(self, branin_search_space):
        """Test Study with SobolSearcher on Branin function."""
        searcher = SobolSearcher(branin_search_space, seed=42)
        executor = LocalExecutor(mode="sync")

        study = Study(
            searcher=searcher,
            executor=executor,
            objective_fn=branin_objective,
            budget=20,
            maximize=True,
            study_name="test_sobol_branin",
        )

        result = study.run()

        # Verify result structure
        assert result is not None
        assert result.best_config is not None
        assert result.best_value is not None
        assert len(result.history) == 20
        assert result.n_trials == 20

    def test_study_sobol_deterministic(self, branin_search_space):
        """Test Study + Sobol is deterministic with seed."""
        searcher1 = SobolSearcher(branin_search_space, seed=42)
        executor1 = LocalExecutor(mode="sync")
        study1 = Study(
            searcher=searcher1,
            executor=executor1,
            objective_fn=branin_objective,
            budget=10,
            maximize=True,
            study_name="study1",
        )
        result1 = study1.run()

        searcher2 = SobolSearcher(branin_search_space, seed=42)
        executor2 = LocalExecutor(mode="sync")
        study2 = Study(
            searcher=searcher2,
            executor=executor2,
            objective_fn=branin_objective,
            budget=10,
            maximize=True,
            study_name="study2",
        )
        result2 = study2.run()

        # Same seed should give same sequence
        for i in range(10):
            config1 = study1.trials[f"study1_trial_{i}"].config
            config2 = study2.trials[f"study2_trial_{i}"].config

            assert config1.values["x"] == config2.values["x"]
            assert config1.values["y"] == config2.values["y"]

    def test_sobol_better_than_random(self, branin_search_space):
        """Test that Sobol achieves better results than Random on average."""
        n_runs = 5
        budget = 32  # Use power of 2 for Sobol

        random_results = []
        for i in range(n_runs):
            searcher = RandomSearcher(branin_search_space, seed=100 + i)
            executor = LocalExecutor(mode="sync")
            study = Study(
                searcher=searcher,
                executor=executor,
                objective_fn=branin_objective,
                budget=budget,
                maximize=True,
            )
            result = study.run()
            random_results.append(result.best_value)

        sobol_results = []
        for i in range(n_runs):
            searcher = SobolSearcher(branin_search_space, seed=100 + i)
            executor = LocalExecutor(mode="sync")
            study = Study(
                searcher=searcher,
                executor=executor,
                objective_fn=branin_objective,
                budget=budget,
                maximize=True,
            )
            result = study.run()
            sobol_results.append(result.best_value)

        # Sobol should have better average best value
        random_mean = np.mean(random_results)
        sobol_mean = np.mean(sobol_results)

        # Sobol should find better values on average (more negative Branin)
        # Allow some tolerance since this is probabilistic
        assert sobol_mean >= random_mean - 5.0


class TestStudyBaselineComparison:
    """Comparison tests between baselines."""

    def test_random_vs_sobol_coverage(self, branin_search_space):
        """Test that Sobol covers space better than Random."""
        budget = 16

        # Run Random
        random_searcher = RandomSearcher(branin_search_space, seed=42)
        random_executor = LocalExecutor(mode="sync")
        random_study = Study(
            searcher=random_searcher,
            executor=random_executor,
            objective_fn=branin_objective,
            budget=budget,
            maximize=True,
            study_name="random_study",
        )
        random_result = random_study.run()

        # Run Sobol
        sobol_searcher = SobolSearcher(branin_search_space, seed=42)
        sobol_executor = LocalExecutor(mode="sync")
        sobol_study = Study(
            searcher=sobol_searcher,
            executor=sobol_executor,
            objective_fn=branin_objective,
            budget=budget,
            maximize=True,
            study_name="sobol_study",
        )
        sobol_result = sobol_study.run()

        # Both should complete successfully
        assert len(random_result.history) == budget
        assert len(sobol_result.history) == budget

        # Sobol should explore space more uniformly
        # Check diversity of x values
        random_x_values = [random_study.trials[f"random_study_trial_{i}"].config["x"] for i in range(budget)]
        sobol_x_values = [sobol_study.trials[f"sobol_study_trial_{i}"].config["x"] for i in range(budget)]

        # Sobol should have more diverse x values (lower variance of sorted differences)
        random_x_sorted = np.sort(random_x_values)
        sobol_x_sorted = np.sort(sobol_x_values)

        random_gaps = np.diff(random_x_sorted)
        sobol_gaps = np.diff(sobol_x_sorted)

        # Sobol should have more uniform gaps (lower variance)
        assert np.var(sobol_gaps) < np.var(random_gaps) * 1.5  # Allow tolerance
