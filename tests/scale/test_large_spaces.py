"""
Scale Tests: Large Search Spaces and Configuration Complexity

Tests handling of complex search spaces.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import numpy as np

from hponas.space import SearchSpace, Knob
from hponas.searchers import RandomSearcher, SobolSearcher


class TestLargeSearchSpaces:
    """Tests for large and complex search spaces."""

    def test_mixed_type_large_space(self):
        """Search space with 100+ knobs of mixed types."""
        knobs = []
        # 50 continuous
        for i in range(50):
            knobs.append(Knob(f"cont_{i}", "continuous", (0.0, 100.0)))
        # 30 ordinal
        for i in range(30):
            knobs.append(Knob(f"ord_{i}", "ordinal", list(range(10))))
        # 20 categorical
        for i in range(20):
            knobs.append(Knob(f"cat_{i}", "categorical", ["a", "b", "c", "d"]))

        space = SearchSpace(knobs)
        assert space.dimension() == 100

        # Sample and validate
        config = space.sample_random_config(seed=42)
        space.validate_config(config)

        # Searcher should handle it
        searcher = RandomSearcher(space, seed=42)
        configs = searcher.propose(10)
        assert len(configs) == 10

    def test_nested_categorical_explosion(self):
        """Large categorical spaces (combinatorial explosion)."""
        knobs = [
            Knob("arch", "categorical", [f"arch_{i}" for i in range(100)]),
            Knob("optimizer", "categorical", ["sgd", "adam", "rmsprop", "adagrad"]),
            Knob("activation", "categorical", ["relu", "tanh", "sigmoid", "elu"]),
        ]
        space = SearchSpace(knobs)

        # Total combinations: 100 * 4 * 4 = 1600
        searcher = RandomSearcher(space, seed=42)

        # Sample 500 configs (should cover diverse combinations)
        configs = searcher.propose(500)
        assert len(configs) == 500

        # Check diversity: should have many unique architectures
        unique_archs = len(set(c["arch"] for c in configs))
        assert unique_archs > 50  # Expect good coverage

    def test_extreme_ordinal_range(self):
        """Ordinal knob with 10000 levels."""
        space = SearchSpace([
            Knob("n_layers", "ordinal", list(range(10000))),
        ])

        searcher = SobolSearcher(space, seed=42)
        configs = searcher.propose(100)

        # Verify all within bounds
        for config in configs:
            assert 0 <= config["n_layers"] < 10000

        # Check spread across range
        values = [c["n_layers"] for c in configs]
        assert min(values) < 1000
        assert max(values) > 8000

    def test_validate_config_performance_large_space(self):
        """validate_config scales with space size."""
        import time

        # Create large space
        knobs = [Knob(f"x{i}", "continuous", (0.0, 1.0)) for i in range(200)]
        space = SearchSpace(knobs)

        # Valid config
        config = {f"x{i}": 0.5 for i in range(200)}

        # Validate should be fast
        start_time = time.time()
        for _ in range(1000):
            space.validate_config(config)
        elapsed = time.time() - start_time

        assert elapsed < 1.0  # 1000 validations in <1 second

    def test_sample_random_config_large_space(self):
        """sample_random_config handles 500D space."""
        knobs = [Knob(f"x{i}", "continuous", (-10.0, 10.0)) for i in range(500)]
        space = SearchSpace(knobs)

        config = space.sample_random_config(seed=42)

        assert len(config) == 500
        for key, value in config.items():
            assert -10.0 <= value <= 10.0

    def test_conditional_space_simulation(self):
        """Simulate conditional space (architecture-dependent parameters)."""
        # Base architecture choice
        space = SearchSpace([
            Knob("arch_type", "categorical", ["mlp", "cnn", "rnn"]),
            Knob("n_layers", "ordinal", list(range(1, 21))),
            Knob("hidden_dim", "continuous", (64.0, 512.0)),
            # CNN-specific (ignored if not CNN)
            Knob("kernel_size", "ordinal", [3, 5, 7]),
            Knob("pool_size", "ordinal", [2, 3, 4]),
            # RNN-specific (ignored if not RNN)
            Knob("cell_type", "categorical", ["lstm", "gru"]),
        ])

        searcher = RandomSearcher(space, seed=42)
        configs = searcher.propose(100)

        # All configs should be valid
        for config in configs:
            space.validate_config(config)

        # Check diversity of arch_type
        arch_types = [c["arch_type"] for c in configs]
        assert "mlp" in arch_types
        assert "cnn" in arch_types
        assert "rnn" in arch_types

    def test_precision_handling_continuous(self):
        """Continuous knobs maintain precision across range."""
        space = SearchSpace([
            Knob("learning_rate", "continuous", (1e-6, 1e-1)),
        ])

        searcher = RandomSearcher(space, seed=42)
        configs = searcher.propose(1000)

        values = [c["learning_rate"] for c in configs]

        # Should span log scale effectively
        assert min(values) < 1e-4
        assert max(values) > 1e-2

        # All values in bounds
        for v in values:
            assert 1e-6 <= v <= 1e-1
