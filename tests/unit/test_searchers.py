"""
Unit Tests: Searchers

Tests individual searcher methods in isolation.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import numpy as np
from hponas.legacy_searchers import RandomSearcher, SobolSearcher
from hponas.space import SearchSpace, Knob


class TestRandomSearcher:
    """Unit tests for RandomSearcher."""

    def test_init_sets_seed(self):
        """RandomSearcher must respect seed for reproducibility."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)
        assert searcher.seed == 42

    def test_propose_respects_bounds(self):
        """Proposed configs must be within declared bounds."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "continuous", (-5.0, 5.0)),
        ])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(100)
        for cfg in configs:
            assert 0.0 <= cfg["x"] <= 1.0
            assert -5.0 <= cfg["y"] <= 5.0

    def test_propose_handles_ordinal(self):
        """Ordinal knobs must be integers in [low, high]."""
        space = SearchSpace([Knob("n", "ordinal", (1, 10))])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(50)
        for cfg in configs:
            assert isinstance(cfg["n"], int)
            assert 1 <= cfg["n"] <= 10

    def test_propose_handles_categorical(self):
        """Categorical knobs must be one of the declared choices."""
        space = SearchSpace([Knob("opt", "categorical", ["adam", "sgd", "rmsprop"])])
        searcher = RandomSearcher(space, seed=42)

        configs = searcher.propose(30)
        for cfg in configs:
            assert cfg["opt"] in ["adam", "sgd", "rmsprop"]

    def test_observe_updates_history(self):
        """observe() must add trial to history."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        trial = {"config": {"x": 0.5}, "fidelity": 1.0, "value": 0.25, "cost": 10.0}
        searcher.observe(trial)

        # History should contain the trial
        assert len(searcher.history) == 1
        assert searcher.history[0]["value"] == 0.25

    def test_state_dict_includes_seed(self):
        """state_dict must include seed for reproducibility."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        state = searcher.state_dict()
        assert "seed" in state
        assert state["seed"] == 42

    def test_load_state_dict_restores_rng(self):
        """load_state_dict must restore RNG state for exact replay."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        # Searcher 1: generate some proposals
        searcher1 = RandomSearcher(space, seed=42)
        searcher1.propose(5)
        state = searcher1.state_dict()
        next1 = searcher1.propose(1)[0]

        # Searcher 2: restore and generate
        searcher2 = RandomSearcher(space, seed=999)
        searcher2.load_state_dict(state)
        next2 = searcher2.propose(1)[0]

        # Next proposals should be identical
        assert next1["x"] == next2["x"]

    def test_capabilities_declares_max_dim(self):
        """capabilities must declare max_dim."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = RandomSearcher(space, seed=42)

        caps = searcher.capabilities
        assert "max_dim" in caps
        assert isinstance(caps["max_dim"], int)
        assert caps["max_dim"] > 0


class TestSobolSearcher:
    """Unit tests for SobolSearcher (quasi-random low-discrepancy sequence)."""

    def test_sobol_first_point_deterministic(self):
        """First Sobol point must be deterministic given seed."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        searcher1 = SobolSearcher(space, seed=42)
        searcher2 = SobolSearcher(space, seed=42)

        cfg1 = searcher1.propose(1)[0]
        cfg2 = searcher2.propose(1)[0]

        assert cfg1["x"] == cfg2["x"]

    def test_sobol_respects_bounds(self):
        """Sobol configs must be within declared bounds."""
        space = SearchSpace([
            Knob("x", "continuous", (0.0, 1.0)),
            Knob("y", "continuous", (-10.0, 10.0)),
        ])
        searcher = SobolSearcher(space, seed=42)

        configs = searcher.propose(200)
        for cfg in configs:
            assert 0.0 <= cfg["x"] <= 1.0
            assert -10.0 <= cfg["y"] <= 10.0

    def test_sobol_fills_space(self):
        """Sobol sequence must have better coverage than random (low discrepancy)."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        sobol = SobolSearcher(space, seed=42)
        random = RandomSearcher(space, seed=42)

        sobol_configs = sobol.propose(64)
        random_configs = random.propose(64)

        # Sobol should have lower max distance to nearest neighbor (better coverage)
        sobol_points = np.array([cfg["x"] for cfg in sobol_configs])
        random_points = np.array([cfg["x"] for cfg in random_configs])

        # Simple coverage metric: standard deviation of inter-point distances
        # (Lower is better for low-discrepancy)
        sobol_spacing_std = np.std(np.diff(np.sort(sobol_points)))
        random_spacing_std = np.std(np.diff(np.sort(random_points)))

        # Sobol should have more uniform spacing
        assert sobol_spacing_std < random_spacing_std

    def test_sobol_state_dict_includes_counter(self):
        """state_dict must include counter to resume from correct position."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        searcher = SobolSearcher(space, seed=42)

        searcher.propose(10)
        state = searcher.state_dict()

        assert "counter" in state
        assert state["counter"] == 10

    def test_sobol_load_state_dict_resumes(self):
        """load_state_dict must resume from saved counter."""
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        # Searcher 1: generate 10 points
        searcher1 = SobolSearcher(space, seed=42)
        searcher1.propose(10)
        state = searcher1.state_dict()
        next1 = searcher1.propose(1)[0]

        # Searcher 2: restore and generate 11th point
        searcher2 = SobolSearcher(space, seed=42)
        searcher2.load_state_dict(state)
        next2 = searcher2.propose(1)[0]

        # 11th points should match
        assert next1["x"] == next2["x"]
