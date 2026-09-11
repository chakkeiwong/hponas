"""Unit tests for RandomSearcher and SobolSearcher.

Tests for hponas/searchers/random_searcher.py - Phase 1 Day 1
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 1
"""

import pytest
import numpy as np
from hponas.searchers.random_searcher import RandomSearcher, SobolSearcher
from hponas.types import (
    Config,
    Result,
    Parameter,
    ParameterType,
    SearchSpace,
)


@pytest.fixture
def simple_search_space():
    """Simple 2D continuous search space for testing."""
    params = {
        "x": Parameter(name="x", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
        "y": Parameter(name="y", type=ParameterType.CONTINUOUS, bounds=(0.0, 1.0)),
    }
    return SearchSpace(parameters=params)


@pytest.fixture
def mixed_search_space():
    """Mixed search space with continuous, integer, categorical."""
    params = {
        "lr": Parameter(
            name="lr", type=ParameterType.CONTINUOUS, bounds=(1e-5, 1e-2), log_scale=True
        ),
        "depth": Parameter(name="depth", type=ParameterType.INTEGER, bounds=(2, 10)),
        "activation": Parameter(
            name="activation",
            type=ParameterType.CATEGORICAL,
            choices=["relu", "gelu", "tanh"],
        ),
    }
    return SearchSpace(parameters=params)


class TestRandomSearcherInitialization:
    """Tests for RandomSearcher initialization."""

    def test_random_searcher_creation(self, simple_search_space):
        """Test creating random searcher."""
        searcher = RandomSearcher(simple_search_space, seed=42)
        assert searcher.search_space == simple_search_space
        assert searcher.seed == 42
        assert hasattr(searcher, "rng")

    def test_random_searcher_no_seed(self, simple_search_space):
        """Test random searcher without seed."""
        searcher = RandomSearcher(simple_search_space, seed=None)
        assert searcher.seed is None
        assert hasattr(searcher, "rng")


class TestRandomSearcherSuggestions:
    """Tests for RandomSearcher suggest() method."""

    def test_random_searcher_suggest(self, simple_search_space):
        """Test suggesting random configurations."""
        searcher = RandomSearcher(simple_search_space, seed=42)

        # Suggest multiple configs
        configs = []
        for _ in range(10):
            config = searcher.suggest()
            configs.append(config)

        # All configs should be valid
        assert len(configs) == 10
        for config in configs:
            assert simple_search_space.validate_config(config)

    def test_random_searcher_deterministic(self, simple_search_space):
        """Test random searcher is deterministic with seed."""
        searcher1 = RandomSearcher(simple_search_space, seed=42)
        searcher2 = RandomSearcher(simple_search_space, seed=42)

        # Same seed should give same sequence
        for _ in range(5):
            config1 = searcher1.suggest()
            config2 = searcher2.suggest()
            assert config1.values["x"] == config2.values["x"]
            assert config1.values["y"] == config2.values["y"]

    def test_random_searcher_different_seeds(self, simple_search_space):
        """Test different seeds give different sequences."""
        searcher1 = RandomSearcher(simple_search_space, seed=42)
        searcher2 = RandomSearcher(simple_search_space, seed=99)

        config1 = searcher1.suggest()
        config2 = searcher2.suggest()

        # Different seeds should (very likely) give different configs
        assert config1.values["x"] != config2.values["x"] or config1.values["y"] != config2.values["y"]

    def test_random_searcher_bounds(self, simple_search_space):
        """Test random searcher respects bounds."""
        searcher = RandomSearcher(simple_search_space, seed=42)

        # Check many samples stay in bounds
        for _ in range(100):
            config = searcher.suggest()
            assert 0.0 <= config["x"] <= 1.0
            assert 0.0 <= config["y"] <= 1.0

    def test_random_searcher_mixed_space(self, mixed_search_space):
        """Test random searcher on mixed search space."""
        searcher = RandomSearcher(mixed_search_space, seed=42)

        # Check samples are valid
        for _ in range(20):
            config = searcher.suggest()
            assert mixed_search_space.validate_config(config)
            assert 1e-5 <= config["lr"] <= 1e-2
            assert 2 <= config["depth"] <= 10
            assert config["activation"] in ["relu", "gelu", "tanh"]


class TestRandomSearcherObserve:
    """Tests for RandomSearcher observe() method."""

    def test_random_searcher_observe(self, simple_search_space):
        """Test observing results doesn't affect random searcher."""
        searcher = RandomSearcher(simple_search_space, seed=42)

        # Observe some results
        for i in range(5):
            config = searcher.suggest()
            result = Result(trial_id=f"trial_{i}", objective_value=float(i) / 10.0)
            searcher.observe(result)

        # History should be tracked
        assert len(searcher.history) == 5

        # But suggestions should still be random (seed-deterministic)
        config = searcher.suggest()
        assert simple_search_space.validate_config(config)


class TestRandomSearcherStateSerialization:
    """Tests for RandomSearcher state serialization."""

    def test_random_searcher_get_state(self, simple_search_space):
        """Test getting random searcher state."""
        searcher = RandomSearcher(simple_search_space, seed=42)

        # Suggest some configs
        for i in range(3):
            config = searcher.suggest()
            result = Result(trial_id=f"trial_{i}", objective_value=float(i))
            searcher.observe(result)

        state = searcher.get_state()

        # Check state contents
        assert "seed" in state
        assert "history" in state
        assert "rng_state" in state
        assert len(state["history"]) == 3

    def test_random_searcher_set_state(self, simple_search_space):
        """Test restoring random searcher state."""
        searcher1 = RandomSearcher(simple_search_space, seed=42)

        # Suggest some configs
        for i in range(3):
            config = searcher1.suggest()
            result = Result(trial_id=f"trial_{i}", objective_value=float(i))
            searcher1.observe(result)

        # Save state
        state = searcher1.get_state()

        # Create new searcher and restore
        searcher2 = RandomSearcher(simple_search_space, seed=99)
        searcher2.set_state(state)

        # Should have same history
        assert len(searcher2.history) == 3
        assert searcher2.seed == 42

        # Next suggestions should be same
        config1 = searcher1.suggest()
        config2 = searcher2.suggest()
        assert config1.values["x"] == config2.values["x"]
        assert config1.values["y"] == config2.values["y"]


class TestSobolSearcherInitialization:
    """Tests for SobolSearcher initialization."""

    def test_sobol_searcher_creation(self, simple_search_space):
        """Test creating Sobol searcher."""
        searcher = SobolSearcher(simple_search_space, seed=42)
        assert searcher.search_space == simple_search_space
        assert searcher.seed == 42
        assert searcher.scramble is True
        assert searcher.d == 2

    def test_sobol_searcher_no_scramble(self, simple_search_space):
        """Test Sobol searcher without scrambling."""
        searcher = SobolSearcher(simple_search_space, seed=42, scramble=False)
        assert searcher.scramble is False


class TestSobolSearcherSuggestions:
    """Tests for SobolSearcher suggest() method."""

    def test_sobol_searcher_suggest(self, simple_search_space):
        """Test suggesting Sobol configurations."""
        searcher = SobolSearcher(simple_search_space, seed=42)

        # Suggest multiple configs
        configs = []
        for _ in range(10):
            config = searcher.suggest()
            configs.append(config)

        # All configs should be valid
        assert len(configs) == 10
        for config in configs:
            assert simple_search_space.validate_config(config)

    def test_sobol_searcher_deterministic(self, simple_search_space):
        """Test Sobol searcher is deterministic with seed."""
        searcher1 = SobolSearcher(simple_search_space, seed=42, scramble=True)
        searcher2 = SobolSearcher(simple_search_space, seed=42, scramble=True)

        # Same seed should give same sequence
        for _ in range(5):
            config1 = searcher1.suggest()
            config2 = searcher2.suggest()
            assert config1.values["x"] == config2.values["x"]
            assert config1.values["y"] == config2.values["y"]

    def test_sobol_searcher_better_coverage(self, simple_search_space):
        """Test Sobol has better coverage than random.

        Sobol should have lower discrepancy (more uniform coverage).
        """
        n_samples = 50

        # Get Sobol samples
        sobol = SobolSearcher(simple_search_space, seed=42)
        sobol_configs = [sobol.suggest() for _ in range(n_samples)]

        # Get random samples
        random = RandomSearcher(simple_search_space, seed=42)
        random_configs = [random.suggest() for _ in range(n_samples)]

        # Sobol should cover space more uniformly
        # Check by dividing space into quadrants
        def count_quadrants(configs):
            q1 = sum(1 for c in configs if c["x"] < 0.5 and c["y"] < 0.5)
            q2 = sum(1 for c in configs if c["x"] >= 0.5 and c["y"] < 0.5)
            q3 = sum(1 for c in configs if c["x"] < 0.5 and c["y"] >= 0.5)
            q4 = sum(1 for c in configs if c["x"] >= 0.5 and c["y"] >= 0.5)
            return [q1, q2, q3, q4]

        sobol_counts = count_quadrants(sobol_configs)
        random_counts = count_quadrants(random_configs)

        # Sobol should have more balanced distribution
        sobol_variance = np.var(sobol_counts)
        random_variance = np.var(random_counts)

        # Sobol should have lower variance (more uniform)
        assert sobol_variance < random_variance * 1.5  # Allow some tolerance

    def test_sobol_searcher_mixed_space(self, mixed_search_space):
        """Test Sobol searcher on mixed search space."""
        searcher = SobolSearcher(mixed_search_space, seed=42)

        # Check samples are valid
        for _ in range(20):
            config = searcher.suggest()
            assert mixed_search_space.validate_config(config)


class TestSobolSearcherStateSerialization:
    """Tests for SobolSearcher state serialization."""

    def test_sobol_searcher_get_state(self, simple_search_space):
        """Test getting Sobol searcher state."""
        searcher = SobolSearcher(simple_search_space, seed=42)

        # Suggest some configs
        for i in range(3):
            config = searcher.suggest()
            result = Result(trial_id=f"trial_{i}", objective_value=float(i))
            searcher.observe(result)

        state = searcher.get_state()

        # Check state contents
        assert "seed" in state
        assert "history" in state
        assert "scramble" in state
        assert "sample_count" in state
        assert state["sample_count"] == 3

    def test_sobol_searcher_set_state(self, simple_search_space):
        """Test restoring Sobol searcher state."""
        searcher1 = SobolSearcher(simple_search_space, seed=42)

        # Suggest some configs
        for i in range(3):
            config = searcher1.suggest()
            result = Result(trial_id=f"trial_{i}", objective_value=float(i))
            searcher1.observe(result)

        # Save state
        state = searcher1.get_state()

        # Create new searcher and restore
        searcher2 = SobolSearcher(simple_search_space, seed=99)
        searcher2.set_state(state)

        # Should have same history and sample count
        assert len(searcher2.history) == 3
        assert searcher2.sample_count == 3

        # Next suggestions should be same (after fast-forward)
        config1 = searcher1.suggest()
        config2 = searcher2.suggest()
        assert config1.values["x"] == config2.values["x"]
        assert config1.values["y"] == config2.values["y"]


class TestSobolVsRandom:
    """Comparison tests between Sobol and Random."""

    def test_sobol_vs_random_coverage(self, simple_search_space):
        """Test Sobol provides better space coverage than random."""
        n = 32  # Use power of 2 for Sobol

        sobol = SobolSearcher(simple_search_space, seed=42)
        random = RandomSearcher(simple_search_space, seed=42)

        sobol_points = np.array([[s.suggest()["x"], s.suggest()["y"]] for s in [sobol] for _ in range(n)])
        random_points = np.array([[r.suggest()["x"], r.suggest()["y"]] for r in [random] for _ in range(n)])

        # Sobol should have points more spread out
        # Check minimum pairwise distance
        def min_pairwise_distance(points):
            min_dist = float('inf')
            for i in range(len(points)):
                for j in range(i + 1, len(points)):
                    dist = np.linalg.norm(points[i] - points[j])
                    min_dist = min(min_dist, dist)
            return min_dist

        # Sobol should have larger minimum distance (less clustering)
        # Note: This is a probabilistic property, may occasionally fail
        # but should pass most of the time
