"""
Unit Tests: Legacy Searchers

High-value tests targeting survived mutations in legacy_searchers.py.
Created 2026-09-18 for V03 mutation testing round 4.
"""

import pytest
import numpy as np
from hponas.legacy_searchers import RandomSearcher, SobolSearcher
from hponas.space import SearchSpace, Knob


class TestRandomSearcherLogTransform:
    """Tests for RandomSearcher log-scale sampling."""

    def test_log_transform_produces_log_uniform_distribution(self):
        """Log-scale continuous knobs must produce log-uniform distribution."""
        space = SearchSpace([Knob("lr", "continuous", (1e-5, 1e-1), transform="log")])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(200)
        values = [cfg["lr"] for cfg in configs]

        # All values in bounds
        assert all(1e-5 <= v <= 1e-1 for v in values)

        # Log-uniform: geometric mean should be near sqrt(low * high)
        geometric_mean = np.exp(np.mean(np.log(values)))
        expected_mean = np.sqrt(1e-5 * 1e-1)  # = 1e-3

        # Within 30% tolerance
        assert 0.7 * expected_mean <= geometric_mean <= 1.3 * expected_mean

    def test_log_transform_crashes_on_invalid_bounds(self):
        """Log-scale with zero or negative bounds must fail cleanly."""
        with pytest.raises(ValueError, match="Log bounds must be positive"):
            SearchSpace([Knob("x", "continuous", (0.0, 1.0), transform="log")])

    def test_log_vs_linear_produces_different_distributions(self):
        """Log-scale and linear-scale must produce different distributions."""
        space_log = SearchSpace(
            [Knob("x", "continuous", (1.0, 100.0), transform="log")]
        )
        space_linear = SearchSpace(
            [Knob("x", "continuous", (1.0, 100.0), transform="none")]
        )

        searcher_log = RandomSearcher(space_log, seed=42)
        searcher_linear = RandomSearcher(space_linear, seed=42)

        configs_log = searcher_log.propose(100)
        configs_linear = searcher_linear.propose(100)

        values_log = [cfg["x"] for cfg in configs_log]
        values_linear = [cfg["x"] for cfg in configs_linear]

        # Linear: arithmetic mean near midpoint
        mean_linear = np.mean(values_linear)
        assert 40 <= mean_linear <= 60, "Linear should cluster around midpoint"

        # Log: geometric mean near sqrt(low * high) = 10
        geometric_mean_log = np.exp(np.mean(np.log(values_log)))
        assert 7 <= geometric_mean_log <= 13, "Log should have geometric mean near 10"

        # Linear mean should be much higher than log geometric mean
        assert mean_linear > 4 * geometric_mean_log


class TestRandomSearcherOrdinal:
    """Tests for RandomSearcher ordinal (integer) knobs."""

    def test_ordinal_covers_full_range(self):
        """Ordinal knobs must sample from entire range [low, high]."""
        space = SearchSpace([Knob("n", "ordinal", (1, 5))])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(100)
        values = set(cfg["n"] for cfg in configs)

        # Should see all values in range
        assert values == {1, 2, 3, 4, 5}, "Must cover full ordinal range"

    def test_ordinal_bounds_inclusive(self):
        """Ordinal high bound must be inclusive."""
        space = SearchSpace([Knob("n", "ordinal", (9, 10))])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(20)
        values = set(cfg["n"] for cfg in configs)

        # Should see both 9 and 10 (both bounds inclusive)
        assert values == {9, 10}, "Small ordinal range must include both bounds"


class TestRandomSearcherCategorical:
    """Tests for RandomSearcher categorical knobs."""

    def test_categorical_covers_all_choices(self):
        """Categorical knobs must sample all choices given enough samples."""
        choices = ["adam", "sgd", "rmsprop", "adagrad"]
        space = SearchSpace([Knob("opt", "categorical", choices)])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(200)
        values = set(cfg["opt"] for cfg in configs)

        # Should see all choices
        assert values == set(choices), "Must cover all categorical choices"

    def test_categorical_rejects_invalid_choice(self):
        """Categorical knobs must never return values outside choices."""
        choices = ["a", "b", "c"]
        space = SearchSpace([Knob("x", "categorical", choices)])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(100)
        for cfg in configs:
            assert cfg["x"] in choices, f"Invalid choice: {cfg['x']}"


class TestRandomSearcherStateRecovery:
    """Tests for RandomSearcher state_dict/load_state_dict."""

    def test_state_dict_rejects_wrong_kind(self):
        """load_state_dict must reject state from different searcher kind."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        wrong_state = {"kind": "sobol", "seed": 42, "n_proposed": 0}

        with pytest.raises(ValueError, match="cannot load state of kind"):
            searcher.load_state_dict(wrong_state)

    def test_load_state_dict_advances_rng_for_all_knob_kinds(self):
        """RNG fast-forward must handle continuous, ordinal, and categorical."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("n", "ordinal", (1, 10)),
                Knob("opt", "categorical", ["a", "b", "c"]),
            ]
        )

        # Generate 5 proposals
        searcher1 = RandomSearcher(space, seed=42)
        searcher1.propose(5)
        state = searcher1.state_dict()
        next1 = searcher1.propose(1)[0]

        # Restore and generate 6th proposal
        searcher2 = RandomSearcher(space, seed=999)
        searcher2.load_state_dict(state)
        next2 = searcher2.propose(1)[0]

        # All fields should match
        assert next1["x"] == next2["x"]
        assert next1["n"] == next2["n"]
        assert next1["opt"] == next2["opt"]


class TestSobolSearcherOrdinal:
    """Tests for SobolSearcher ordinal knobs."""

    def test_sobol_ordinal_covers_range(self):
        """Sobol ordinal knobs must cover the full integer range."""
        space = SearchSpace([Knob("n", "ordinal", (1, 10))])
        searcher = SobolSearcher(space, seed=42)

        configs = searcher.propose(64)
        values = set(cfg["n"] for cfg in configs)

        # Should see most/all values (Sobol has good coverage)
        assert len(values) >= 8, "Sobol should cover most ordinal values"
        assert all(1 <= v <= 10 for v in values), "All values must be in bounds"

    def test_sobol_ordinal_clamps_at_boundary(self):
        """Sobol ordinal must clamp u=1.0 to high bound."""
        space = SearchSpace([Knob("n", "ordinal", (4, 6))])
        searcher = SobolSearcher(space, seed=42)

        configs = searcher.propose(20)
        values = set(cfg["n"] for cfg in configs)

        # Should see 4, 5, and 6 (small range)
        assert values.issubset({4, 5, 6}), "All values must be in bounds"
        assert all(4 <= v <= 6 for v in [c["n"] for c in configs]), (
            "Must clamp to bounds"
        )


class TestSobolSearcherLogTransform:
    """Tests for SobolSearcher log-scale continuous knobs."""

    def test_sobol_log_produces_geometric_distribution(self):
        """Sobol log-scale must produce log-uniform distribution."""
        space = SearchSpace([Knob("lr", "continuous", (1e-4, 1e-1), transform="log")])
        searcher = SobolSearcher(space, seed=42)

        configs = searcher.propose(128)
        values = [cfg["lr"] for cfg in configs]

        # All in bounds
        assert all(1e-4 <= v <= 1e-1 for v in values)

        # Geometric mean near sqrt(low * high)
        geometric_mean = np.exp(np.mean(np.log(values)))
        expected = np.sqrt(1e-4 * 1e-1)  # = 0.01

        assert 0.7 * expected <= geometric_mean <= 1.3 * expected


class TestSobolSearcherStateRecovery:
    """Tests for SobolSearcher state_dict/load_state_dict."""

    def test_sobol_state_dict_rejects_wrong_kind(self):
        """load_state_dict must reject state from different searcher kind."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = SobolSearcher(space, seed=42)

        wrong_state = {"kind": "random", "seed": 42, "n_proposed": 0}

        with pytest.raises(ValueError, match="cannot load state of kind"):
            searcher.load_state_dict(wrong_state)

    def test_sobol_state_dict_rejects_space_mismatch(self):
        """load_state_dict must reject state from different space structure."""
        space1 = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        space2 = SearchSpace([Knob("y", "continuous", (0.0, 1.0))])

        searcher1 = SobolSearcher(space1, seed=42)
        searcher1.propose(5)
        state = searcher1.state_dict()

        searcher2 = SobolSearcher(space2, seed=42)

        with pytest.raises(ValueError, match="does not match space"):
            searcher2.load_state_dict(state)

    def test_sobol_load_state_dict_handles_categorical_rng(self):
        """Sobol categorical RNG must be fast-forwarded on restore."""
        space = SearchSpace(
            [
                Knob("x", "continuous", (0.0, 1.0)),
                Knob("opt", "categorical", ["a", "b", "c"]),
            ]
        )

        # Generate 10 proposals
        searcher1 = SobolSearcher(space, seed=42)
        searcher1.propose(10)
        state = searcher1.state_dict()
        next1 = searcher1.propose(1)[0]

        # Restore and generate 11th proposal
        searcher2 = SobolSearcher(space, seed=999)
        searcher2.load_state_dict(state)
        next2 = searcher2.propose(1)[0]

        # Both continuous and categorical should match
        assert next1["x"] == next2["x"]
        assert next1["opt"] == next2["opt"]
