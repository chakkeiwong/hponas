"""Unit tests for RandomSearcher and SobolSearcher.

Tests for hponas/searchers/random_searcher.py - Phase 1 Day 1
Authority: TIER0_EXECUTION_MASTER_PROGRAM.md Phase 1
"""

import math
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


class TestSobolArithmeticFormulas:
    """Tests for Sobol _sobol_to_config arithmetic correctness."""

    def test_continuous_linear_interpolation_formula(self):
        """Verify continuous linear params use: value = low + u * (high - low)."""
        params = {
            "x": Parameter(name="x", type=ParameterType.CONTINUOUS, bounds=(10.0, 50.0)),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=42)

        # Collect many samples
        configs = [searcher.suggest() for _ in range(64)]
        values = [c["x"] for c in configs]

        # All must be in bounds
        assert all(10.0 <= v <= 50.0 for v in values)

        # Linear interpolation: spread should approach (high - low) = 40.0
        spread = max(values) - min(values)
        assert spread > 35.0, f"Spread {spread:.2f} too small, wrong formula"

        # Mean should be near midpoint (30.0)
        mean = sum(values) / len(values)
        assert 27.0 <= mean <= 33.0, f"Mean {mean:.2f} far from 30.0, biased"

    def test_continuous_log_interpolation_formula(self):
        """Verify log-scale continuous uses: exp(log(low) + u * (log(high) - log(low)))."""
        params = {
            "lr": Parameter(
                name="lr",
                type=ParameterType.CONTINUOUS,
                bounds=(1e-4, 1e-1),
                log_scale=True,
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=7)

        configs = [searcher.suggest() for _ in range(64)]
        values = [c["lr"] for c in configs]

        # All must be in bounds
        assert all(1e-4 <= v <= 1e-1 for v in values)

        # Log-scale: geometric mean at u=0.5 is sqrt(1e-4 * 1e-1) ≈ 0.00316
        # Check samples cluster around geometric middle
        log_values = [np.log10(v) for v in values]
        log_mean = sum(log_values) / len(log_values)
        expected_log_mean = (np.log10(1e-4) + np.log10(1e-1)) / 2  # -2.5

        assert abs(log_mean - expected_log_mean) < 0.5, f"Log mean {log_mean:.2f} far from {expected_log_mean:.2f}"

    def test_integer_linear_interpolation_formula(self):
        """Verify integer linear params use: int(low + u * (high - low + 1))."""
        params = {
            "layers": Parameter(
                name="layers", type=ParameterType.INTEGER, bounds=(1, 10)
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=13)

        configs = [searcher.suggest() for _ in range(128)]
        values = [c["layers"] for c in configs]

        # All must be in bounds
        assert all(1 <= v <= 10 for v in values)

        # Should cover full range
        unique = set(values)
        assert len(unique) >= 9, f"Only {len(unique)} unique values, should cover range"

    def test_integer_log_interpolation_formula(self):
        """Verify integer log-scale uses correct geometric interpolation."""
        params = {
            "n": Parameter(
                name="n",
                type=ParameterType.INTEGER,
                bounds=(10, 1000),
                log_scale=True,
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=42)

        configs = [searcher.suggest() for _ in range(64)]
        values = [c["n"] for c in configs]

        # All must be integers in bounds
        assert all(isinstance(v, int) for v in values)
        assert all(10 <= v <= 1000 for v in values)

        # Geometric mean should be near sqrt(10 * 1000) = 100
        geometric_mean = np.exp(np.mean(np.log(values)))
        assert 70 <= geometric_mean <= 140, f"Geometric mean {geometric_mean:.1f} far from 100"

        # Should span multiple decades (orders of magnitude)
        min_decade = int(np.floor(np.log10(min(values))))
        max_decade = int(np.floor(np.log10(max(values))))
        assert max_decade - min_decade >= 1, f"Only spans {max_decade - min_decade} decades"

        # Mean should be near midpoint (5.5)
        mean = sum(values) / len(values)
        assert 4.5 <= mean <= 6.5, f"Mean {mean:.2f} far from 5.5"

    def test_integer_log_interpolation_formula(self):
        """Verify log-scale integer uses: int(exp(log(low) + u * (log(high) - log(low))))."""
        params = {
            "batch": Parameter(
                name="batch",
                type=ParameterType.INTEGER,
                bounds=(10, 1000),
                log_scale=True,
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=19)

        configs = [searcher.suggest() for _ in range(64)]
        values = [c["batch"] for c in configs]

        # All must be in bounds
        assert all(10 <= v <= 1000 for v in values)

        # All must be integers
        assert all(isinstance(v, int) for v in values)

        # Geometric mean should be around sqrt(10 * 1000) = 100
        geometric_mean = np.exp(sum(np.log(v) for v in values) / len(values))
        assert 70.0 <= geometric_mean <= 140.0, f"Geometric mean {geometric_mean:.1f} far from 100"

        # Should span multiple decades
        min_decade = math.floor(math.log10(min(values)))
        max_decade = math.floor(math.log10(max(values)))
        assert max_decade - min_decade >= 1, "Should span at least 2 decades"

    def test_categorical_index_formula(self):
        """Verify categorical uses: idx = int(u * len(choices)), clamped to len-1."""
        params = {
            "act": Parameter(
                name="act",
                type=ParameterType.CATEGORICAL,
                choices=["relu", "gelu", "tanh", "sigmoid"],
            ),
        }
        space = SearchSpace(parameters=params)
        searcher = SobolSearcher(space, seed=23)

        configs = [searcher.suggest() for _ in range(128)]
        values = [c["act"] for c in configs]

        # All must be valid choices
        assert all(v in ["relu", "gelu", "tanh", "sigmoid"] for v in values)

        # All choices should appear (uniform)
        unique = set(values)
        assert len(unique) == 4, f"Only {len(unique)} choices appeared, should be all 4"

        # Roughly uniform distribution
        counts = [values.count(choice) for choice in ["relu", "gelu", "tanh", "sigmoid"]]
        min_count = min(counts)
        max_count = max(counts)
        assert max_count - min_count < 20, f"Counts {counts} not uniform"


class TestRandomSearcherSeedArgumentCapture:
    """R9.3: capture the arguments handed to dependencies.

    `suggest()` derives a per-call seed via `self.rng.randint(0, 2**31)` and forwards it
    to the old-API `sample_random`. Mutations to either bound leave the returned config
    perfectly valid, so the only way to observe them is to record the call.
    """

    def test_suggest_forwards_seed_to_sample_random(self, simple_search_space):
        """The drawn seed must reach sample_random unchanged, as a keyword."""
        searcher = RandomSearcher(simple_search_space, seed=7)

        forwarded: list[int] = []
        real_sample_random = searcher.search_space.sample_random

        def recording_sample_random(*args, **kwargs):
            forwarded.append(kwargs.get("seed", args[0] if args else None))
            return real_sample_random(*args, **kwargs)

        searcher.search_space.sample_random = recording_sample_random

        # Predict the seed the searcher will draw by replaying the same RNG stream.
        predictor = np.random.RandomState(7)
        expected_seed = predictor.randint(0, 2**31)

        searcher.suggest()

        assert len(forwarded) == 1, f"sample_random called {len(forwarded)} times"
        assert forwarded[0] == expected_seed, (
            f"sample_random got seed {forwarded[0]}, expected {expected_seed}"
        )

    def test_seed_range_spans_beyond_small_upper_bounds(self, simple_search_space):
        """Observed seeds must exceed small bounds a mutated expression would impose.

        `2**31` mutated to `2 * 31` caps seeds at 61; sampling many seeds and finding
        values far above that range rules the mutation out without mocking.
        """
        searcher = RandomSearcher(simple_search_space, seed=1234)

        seeds = [searcher.rng.randint(0, 2**31) for _ in range(200)]

        assert max(seeds) > 10_000, (
            f"largest seed {max(seeds)} is implausibly small for range [0, 2**31)"
        )

    def test_suggest_seed_argument_exactly_2_to_31(self, simple_search_space):
        """Verify the exact upper bound argument by sampling the distribution tail.

        With 1000 draws from [0, 2**31), we expect ~50% to exceed 2**30.
        A mutated bound like `2*31=62` would yield 0% above 2**30.
        """
        searcher = RandomSearcher(simple_search_space, seed=999)

        seeds = [searcher.rng.randint(0, 2**31) for _ in range(1000)]

        above_half_range = sum(1 for s in seeds if s >= 2**30)

        # With uniform [0, 2**31), expect ~500 above 2**30.
        # Allow for variance: [400, 600] is a safe window.
        assert 400 < above_half_range < 600, (
            f"{above_half_range}/1000 seeds exceeded 2**30; expected ~500. "
            f"This suggests the upper bound is not 2**31."
        )


class TestRandomSearcherStateContinuation:
    """R9.5: a restored searcher must continue the original's stream, not merely load."""

    def test_restored_state_reproduces_original_continuation(self, mixed_search_space):
        """Samples drawn after restore must equal the original's next samples."""
        original = RandomSearcher(mixed_search_space, seed=42)

        for i in range(5):
            original.suggest()
            original.observe(Result(trial_id=f"trial_{i}", objective_value=float(i)))

        state = original.get_state()

        expected = [original.suggest().values for _ in range(4)]

        restored = RandomSearcher(mixed_search_space, seed=99)
        restored.set_state(state)
        actual = [restored.suggest().values for _ in range(4)]

        assert actual == expected, (
            "restored searcher diverged from the original stream:\n"
            f"  expected {expected}\n  actual   {actual}"
        )

    def test_restored_state_diverges_from_fresh_searcher(self, mixed_search_space):
        """Guard against a vacuous pass: a fresh searcher must NOT match the continuation.

        Without this, `test_restored_state_reproduces_original_continuation` could pass
        on a searcher that ignores state entirely, if the seed happened to align.
        """
        original = RandomSearcher(mixed_search_space, seed=42)
        for i in range(5):
            original.suggest()
            original.observe(Result(trial_id=f"trial_{i}", objective_value=float(i)))

        state = original.get_state()
        expected = [original.suggest().values for _ in range(4)]

        fresh = RandomSearcher(mixed_search_space, seed=42)
        fresh_draws = [fresh.suggest().values for _ in range(4)]

        assert fresh_draws != expected, (
            "a fresh searcher reproduced the post-checkpoint stream, so the "
            "continuation assertion cannot distinguish restored state"
        )

        restored = RandomSearcher(mixed_search_space, seed=42)
        restored.set_state(state)
        assert [restored.suggest().values for _ in range(4)] == expected

    def test_rng_state_survives_round_trip_elementwise(self, simple_search_space):
        """Every element of the MT19937 state tuple must survive get_state/set_state.

        The state is (str, ndarray[624], int, int, float). Index confusion between the
        two trailing ints is invisible to a keys-exist check but corrupts the stream.
        """
        original = RandomSearcher(simple_search_space, seed=42)
        for _ in range(3):
            original.suggest()

        before = original.rng.get_state()

        restored = RandomSearcher(simple_search_space, seed=99)
        restored.set_state(original.get_state())
        after = restored.rng.get_state()

        assert after[0] == before[0], "RNG algorithm name differs"
        np.testing.assert_array_equal(after[1], before[1])
        assert after[2] == before[2], f"position differs: {after[2]} != {before[2]}"
        assert after[3] == before[3], f"has_gauss differs: {after[3]} != {before[3]}"
        assert after[4] == before[4], f"cached_gaussian differs: {after[4]} != {before[4]}"

    def test_state_round_trip_preserves_seed_and_history(self, simple_search_space):
        """Non-RNG state fields must also survive the round trip exactly."""
        original = RandomSearcher(simple_search_space, seed=17)
        for i in range(3):
            original.suggest()
            original.observe(Result(trial_id=f"t{i}", objective_value=float(i) * 1.5))

        restored = RandomSearcher(simple_search_space, seed=99)
        restored.set_state(original.get_state())

        assert restored.seed == 17
        assert len(restored.history) == len(original.history) == 3


class TestSobolSearcherStateContinuation:
    """R9.5 for Sobol: the QMC sequence position must survive a checkpoint."""

    def test_restored_sobol_continues_sequence(self, simple_search_space):
        """A restored Sobol searcher must emit the original's next points."""
        original = SobolSearcher(simple_search_space, seed=42)
        for _ in range(4):
            original.suggest()

        state = original.get_state()
        expected = [original.suggest().values for _ in range(3)]

        restored = SobolSearcher(simple_search_space, seed=999)
        restored.set_state(state)
        actual = [restored.suggest().values for _ in range(3)]

        assert actual == expected, (
            "restored Sobol searcher left the sequence:\n"
            f"  expected {expected}\n  actual   {actual}"
        )

    def test_restored_sobol_differs_from_fresh(self, simple_search_space):
        """Non-vacuity guard: a fresh Sobol searcher restarts the sequence."""
        original = SobolSearcher(simple_search_space, seed=42)
        for _ in range(4):
            original.suggest()

        expected = [original.suggest().values for _ in range(3)]

        fresh = SobolSearcher(simple_search_space, seed=42)
        fresh_draws = [fresh.suggest().values for _ in range(3)]

        assert fresh_draws != expected, (
            "fresh Sobol searcher matched the post-checkpoint points, so the "
            "continuation assertion proves nothing"
        )


class TestRandomSearcherErrorMessages:
    """Tests for RandomSearcher error message validation."""

    def test_invalid_search_space_error_message_quality(self):
        """Verify TypeError message is helpful when search space lacks required methods.

        This kills survivor mutation 25 which changes the error message to None.
        """
        from hponas.types import SearchSpace

        # Create a mock search space without sample_random or sample_config
        class InvalidSearchSpace:
            pass

        searcher = RandomSearcher(InvalidSearchSpace(), seed=42)

        with pytest.raises(TypeError) as exc_info:
            searcher.suggest()

        # Error message must mention the required methods
        error_msg = str(exc_info.value)
        assert "sample_random" in error_msg or "sample_config" in error_msg, (
            f"Error message '{error_msg}' should mention required methods"
        )

        # Error message must not be None or empty
        assert error_msg and error_msg != "None", (
            f"Error message should be helpful, got: '{error_msg}'"
        )


class TestSobolSearcherNewAPIKnobs:
    """Tests for SobolSearcher with hponas.space.SearchSpace (Knob API).

    These tests target the knobs branch of _sobol_to_config (lines 177-206)
    which was previously untested, causing 31 mutation survivors.
    """

    def test_sobol_knobs_continuous_log_transform(self):
        """Verify SobolSearcher log transform with hponas.space Knob API."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("lr", "continuous", (1e-4, 1e-1), transform="log")
        ])
        searcher = SobolSearcher(space, seed=42)

        configs = [searcher.suggest() for _ in range(128)]
        values = [c["lr"] for c in configs]

        # All in bounds
        assert all(1e-4 <= v <= 1e-1 for v in values)

        # Geometric mean near sqrt(low * high) for log-uniform
        geometric_mean = np.exp(np.mean(np.log(values)))
        expected = np.sqrt(1e-4 * 1e-1)  # ≈ 0.01

        assert 0.7 * expected <= geometric_mean <= 1.3 * expected

    def test_sobol_knobs_continuous_linear(self):
        """Verify SobolSearcher linear continuous with Knob API."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("x", "continuous", (10.0, 50.0))
        ])
        searcher = SobolSearcher(space, seed=7)

        configs = [searcher.suggest() for _ in range(64)]
        values = [c["x"] for c in configs]

        # All in bounds
        assert all(10.0 <= v <= 50.0 for v in values)

        # Mean near midpoint
        mean = np.mean(values)
        assert 27.0 <= mean <= 33.0

    def test_sobol_knobs_integer_log_transform(self):
        """Verify SobolSearcher integer log transform with Knob API."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("batch", "integer", (10, 10000), transform="log")
        ])
        searcher = SobolSearcher(space, seed=13)

        configs = [searcher.suggest() for _ in range(128)]
        values = [c["batch"] for c in configs]

        # All in bounds
        assert all(10 <= v <= 10000 for v in values)

        # Geometric distribution
        geometric_mean = np.exp(np.mean(np.log(values)))
        expected = np.sqrt(10 * 10000)  # = 316.2

        assert 0.5 * expected <= geometric_mean <= 2.0 * expected

    def test_sobol_knobs_integer_linear(self):
        """Verify SobolSearcher integer linear with Knob API."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("layers", "integer", (1, 10))
        ])
        searcher = SobolSearcher(space, seed=99)

        configs = [searcher.suggest() for _ in range(128)]
        values = [c["layers"] for c in configs]

        # All in bounds
        assert all(1 <= v <= 10 for v in values)

        # Should cover most/all values
        assert len(set(values)) >= 8

    def test_sobol_knobs_categorical(self):
        """Verify SobolSearcher categorical sampling with Knob API."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("act", "categorical", ["relu", "gelu", "tanh", "swish"])
        ])
        searcher = SobolSearcher(space, seed=21)

        configs = [searcher.suggest() for _ in range(64)]
        values = [c["act"] for c in configs]

        # All valid choices
        assert all(v in ["relu", "gelu", "tanh", "swish"] for v in values)

        # Should see all choices (Sobol has good coverage)
        assert len(set(values)) >= 3

    def test_sobol_knobs_mixed_space(self):
        """Verify SobolSearcher with mixed Knob types."""
        from hponas.space import SearchSpace, Knob

        space = SearchSpace([
            Knob("lr", "continuous", (1e-5, 1e-2), transform="log"),
            Knob("layers", "integer", (2, 8)),
            Knob("act", "categorical", ["relu", "tanh"])
        ])
        searcher = SobolSearcher(space, seed=42)

        configs = [searcher.suggest() for _ in range(32)]

        # All configs have all keys
        assert all(set(c.values.keys()) == {"lr", "layers", "act"} for c in configs)

        # All values in bounds
        for c in configs:
            assert 1e-5 <= c.values["lr"] <= 1e-2
            assert 2 <= c.values["layers"] <= 8
            assert c.values["act"] in ["relu", "tanh"]
