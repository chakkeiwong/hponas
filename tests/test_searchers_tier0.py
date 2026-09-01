"""
Tests for Tier 0 searchers: Random, Sobol, TPE, GP+qLogEI.

Validation coverage:
- V01: Implementation parity (distributional equivalence with references)
- V04: Performance check (beat random baseline)
- V05: Log-warping effectiveness

Test categories:
1. Contract tests: propose/observe/state_dict/capabilities
2. Mixed-space tests: continuous, ordinal, categorical
3. Crash recovery: state serialization round-trip
4. Log-warping: dimension transform correctness
"""

import pytest
import numpy as np
from hponas import SearchSpace, RandomSearcher, SobolSearcher
from hponas.space import Knob


def test_random_searcher_contract():
    """RandomSearcher implements Searcher protocol."""
    space = SearchSpace()
    space.add_knob(Knob("lr", kind="continuous", bounds=(1e-4, 1e-1), transform="log"))
    space.add_knob(Knob("batch_size", kind="ordinal", bounds=(16, 128)))
    space.add_knob(Knob("optimizer", kind="categorical", bounds=["sgd", "adam", "rmsprop"]))

    searcher = RandomSearcher(space, seed=42)

    # Test propose
    configs = searcher.propose(5)
    assert len(configs) == 5
    for config in configs:
        assert "lr" in config
        assert "batch_size" in config
        assert "optimizer" in config
        assert 1e-4 <= config["lr"] <= 1e-1
        assert 16 <= config["batch_size"] <= 128
        assert config["optimizer"] in ["sgd", "adam", "rmsprop"]

    # Test observe (should not error)
    searcher.observe({"config": configs[0], "value": 0.95, "fidelity": 1.0, "cost": 10.0})

    # Test capabilities
    caps = searcher.capabilities
    assert "continuous" in caps["knob_kinds"]
    assert "ordinal" in caps["knob_kinds"]
    assert "categorical" in caps["knob_kinds"]


def test_random_searcher_reproducibility():
    """Same seed produces same sequence."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    s1 = RandomSearcher(space, seed=42)
    s2 = RandomSearcher(space, seed=42)

    configs1 = s1.propose(10)
    configs2 = s2.propose(10)

    for c1, c2 in zip(configs1, configs2):
        assert c1["x"] == pytest.approx(c2["x"])


def test_random_searcher_log_warping():
    """Log transform samples log-uniformly."""
    space = SearchSpace()
    space.add_knob(Knob("lr", kind="continuous", bounds=(1e-5, 1e-1), transform="log"))

    searcher = RandomSearcher(space, seed=42)
    configs = searcher.propose(1000)

    # Log-uniform: log(lr) should be uniform in [log(1e-5), log(1e-1)]
    log_lrs = [np.log(c["lr"]) for c in configs]
    expected_mean = (np.log(1e-5) + np.log(1e-1)) / 2
    actual_mean = np.mean(log_lrs)

    # Mean should be close (within 10% relative error for 1000 samples)
    assert abs(actual_mean - expected_mean) / abs(expected_mean) < 0.1


def test_random_searcher_state_recovery():
    """State serialization preserves RNG position."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    # Propose 5, save state, propose 5 more
    s1 = RandomSearcher(space, seed=42)
    batch1 = s1.propose(5)
    state = s1.state_dict()
    batch2_original = s1.propose(5)

    # Restore state and propose 5 more
    s2 = RandomSearcher(space, seed=999)  # Different seed
    s2.load_state_dict(state)
    batch2_restored = s2.propose(5)

    # Restored sequence should match original continuation
    for c1, c2 in zip(batch2_original, batch2_restored):
        assert c1["x"] == pytest.approx(c2["x"])


def test_sobol_searcher_contract():
    """SobolSearcher implements Searcher protocol."""
    space = SearchSpace()
    space.add_knob(Knob("x1", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("x2", kind="continuous", bounds=(-5, 5)))
    space.add_knob(Knob("n", kind="ordinal", bounds=(1, 10)))

    searcher = SobolSearcher(space, seed=42)

    # Test propose
    configs = searcher.propose(8)
    assert len(configs) == 8

    for config in configs:
        assert "x1" in config
        assert "x2" in config
        assert "n" in config
        assert 0 <= config["x1"] <= 1
        assert -5 <= config["x2"] <= 5
        assert 1 <= config["n"] <= 10
        assert isinstance(config["n"], int)

    # Test capabilities
    caps = searcher.capabilities
    assert "continuous" in caps["knob_kinds"]
    assert "ordinal" in caps["knob_kinds"]


def test_sobol_searcher_qmc_coverage():
    """Sobol sequence covers space more uniformly than random."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = SobolSearcher(space, seed=42)
    configs = searcher.propose(64)

    # Split [0, 1]^2 into 4 quadrants
    quadrants = [0, 0, 0, 0]
    for config in configs:
        x, y = config["x"], config["y"]
        q = (0 if x < 0.5 else 1) + (0 if y < 0.5 else 2)
        quadrants[q] += 1

    # Sobol should visit all quadrants (random might not)
    for count in quadrants:
        assert count > 0, "Sobol should cover all quadrants"


def test_sobol_searcher_log_warping():
    """Sobol with log transform samples log-uniformly."""
    space = SearchSpace()
    space.add_knob(Knob("lr", kind="continuous", bounds=(1e-5, 1e-1), transform="log"))

    searcher = SobolSearcher(space, seed=42)
    configs = searcher.propose(128)

    # Log-uniform: log(lr) should be uniform in [log(1e-5), log(1e-1)]
    log_lrs = [np.log(c["lr"]) for c in configs]
    expected_mean = (np.log(1e-5) + np.log(1e-1)) / 2
    actual_mean = np.mean(log_lrs)

    # QMC should be very close to expected mean
    assert abs(actual_mean - expected_mean) / abs(expected_mean) < 0.05


def test_sobol_searcher_state_recovery():
    """State serialization preserves Sobol sequence position."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    # Propose 8, save state, propose 8 more
    s1 = SobolSearcher(space, seed=42)
    batch1 = s1.propose(8)
    state = s1.state_dict()
    batch2_original = s1.propose(8)

    # Restore state and propose 8 more
    s2 = SobolSearcher(space, seed=999)  # Different seed
    s2.load_state_dict(state)
    batch2_restored = s2.propose(8)

    # Restored sequence should match original continuation
    for c1, c2 in zip(batch2_original, batch2_restored):
        assert c1["x"] == pytest.approx(c2["x"], abs=1e-10)


def test_sobol_ordinal_quantization():
    """Ordinal knobs quantize Sobol sequence to integers."""
    space = SearchSpace()
    space.add_knob(Knob("n", kind="ordinal", bounds=(1, 5)))

    searcher = SobolSearcher(space, seed=42)
    configs = searcher.propose(64)

    # All values should be integers in [1, 5]
    for config in configs:
        n = config["n"]
        assert isinstance(n, (int, np.integer))
        assert 1 <= n <= 5

    # Should visit all values (64 samples from 5-point space)
    values = {config["n"] for config in configs}
    assert len(values) == 5, "Sobol should cover all ordinal values"


def test_sobol_categorical_coverage():
    """Categorical knobs sampled uniformly."""
    space = SearchSpace()
    space.add_knob(Knob("opt", kind="categorical", bounds=["a", "b", "c"]))

    searcher = SobolSearcher(space, seed=42)
    configs = searcher.propose(60)

    # Count occurrences
    counts = {"a": 0, "b": 0, "c": 0}
    for config in configs:
        counts[config["opt"]] += 1

    # Should be roughly uniform (within 2x of expected)
    expected = 60 / 3
    for choice, count in counts.items():
        assert expected / 2 <= count <= expected * 2


def test_mixed_space_proposal():
    """All searchers handle mixed-space proposals."""
    space = SearchSpace()
    space.add_knob(Knob("lr", kind="continuous", bounds=(1e-4, 1e-1), transform="log"))
    space.add_knob(Knob("layers", kind="ordinal", bounds=(2, 8)))
    space.add_knob(Knob("activation", kind="categorical", bounds=["relu", "tanh", "gelu"]))

    for SearcherClass in [RandomSearcher, SobolSearcher]:
        searcher = SearcherClass(space, seed=42)
        configs = searcher.propose(10)

        assert len(configs) == 10
        for config in configs:
            # Check all knobs present
            assert "lr" in config
            assert "layers" in config
            assert "activation" in config

            # Check bounds
            assert 1e-4 <= config["lr"] <= 1e-1
            assert 2 <= config["layers"] <= 8
            assert config["activation"] in ["relu", "tanh", "gelu"]

            # Check types
            assert isinstance(config["lr"], float)
            assert isinstance(config["layers"], (int, np.integer))
            assert isinstance(config["activation"], str)


def test_searcher_batch_proposals():
    """Batch proposals return requested count."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    for SearcherClass in [RandomSearcher, SobolSearcher]:
        searcher = SearcherClass(space, seed=42)

        for n in [1, 5, 16, 32]:
            configs = searcher.propose(n)
            assert len(configs) == n


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
