"""
Property-Based Tests: Invariants

Tests that hold for all valid inputs using Hypothesis.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import numpy as np
from hypothesis import given, strategies as st, assume, settings
from hponas.legacy_searchers import RandomSearcher, SobolSearcher
from hponas.space import SearchSpace, Knob


# Strategy: generate random search spaces
@st.composite
def search_space_strategy(draw):
    """Generate random SearchSpace with 1-5 knobs."""
    n_knobs = draw(st.integers(min_value=1, max_value=5))
    knobs = []

    for i in range(n_knobs):
        name = f"x{i}"
        kind = draw(st.sampled_from(["continuous", "ordinal", "categorical"]))

        if kind == "continuous":
            low = draw(st.floats(min_value=-100.0, max_value=100.0))
            high = draw(st.floats(min_value=low + 0.1, max_value=low + 200.0))
            knobs.append(Knob(name, kind, (low, high)))
        elif kind == "ordinal":
            low = draw(st.integers(min_value=1, max_value=50))
            high = draw(st.integers(min_value=low + 1, max_value=low + 100))
            knobs.append(Knob(name, kind, (low, high)))
        else:  # categorical
            n_choices = draw(st.integers(min_value=2, max_value=5))
            choices = [f"choice_{j}" for j in range(n_choices)]
            knobs.append(Knob(name, kind, choices))

    return SearchSpace(knobs)


class TestSearcherInvariants:
    """Property-based tests for searcher invariants."""

    @given(space=search_space_strategy(), n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50, deadline=1000)
    def test_propose_returns_exact_count(self, space, n):
        """propose(n) must return exactly n configs for any valid space."""
        searcher = RandomSearcher(space, seed=42)
        configs = searcher.propose(n)
        assert len(configs) == n

    @given(space=search_space_strategy(), n=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50, deadline=1000)
    def test_propose_respects_bounds(self, space, n):
        """All proposed configs must satisfy bounds for any valid space."""
        searcher = RandomSearcher(space, seed=42)
        configs = searcher.propose(n)

        for cfg in configs:
            # Should not raise
            space.validate_config(cfg)

    @given(space=search_space_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_state_dict_roundtrip(self, space):
        """state_dict → load_state_dict must preserve behavior."""
        searcher1 = RandomSearcher(space, seed=42)
        searcher1.propose(5)
        state = searcher1.state_dict()

        # Load into new searcher
        searcher2 = RandomSearcher(space, seed=999)
        searcher2.load_state_dict(state)

        # Next proposals should match
        next1 = searcher1.propose(3)
        next2 = searcher2.propose(3)

        assert len(next1) == len(next2)
        for cfg1, cfg2 in zip(next1, next2):
            assert cfg1.keys() == cfg2.keys()
            for key in cfg1.keys():
                assert cfg1[key] == cfg2[key]

    @given(space=search_space_strategy(), seed=st.integers(min_value=0, max_value=10000))
    @settings(max_examples=50, deadline=1000)
    def test_same_seed_same_output(self, space, seed):
        """Same seed must produce identical proposals."""
        searcher1 = RandomSearcher(space, seed=seed)
        searcher2 = RandomSearcher(space, seed=seed)

        configs1 = searcher1.propose(5)
        configs2 = searcher2.propose(5)

        assert len(configs1) == len(configs2)
        for cfg1, cfg2 in zip(configs1, configs2):
            for key in cfg1.keys():
                assert cfg1[key] == cfg2[key]


class TestSobolInvariants:
    """Property-based tests for Sobol quasi-random invariants."""

    @given(space=search_space_strategy(), n=st.integers(min_value=1, max_value=50))
    @settings(max_examples=30, deadline=1000)
    def test_sobol_deterministic_given_seed(self, space, n):
        """Sobol sequence must be deterministic given seed."""
        assume(all(k.kind == "continuous" for k in space.knobs))  # Sobol only for continuous

        if not all(k.kind == "continuous" for k in space.knobs):
            return  # Skip if not all continuous

        searcher1 = SobolSearcher(space, seed=42)
        searcher2 = SobolSearcher(space, seed=42)

        configs1 = searcher1.propose(n)
        configs2 = searcher2.propose(n)

        for cfg1, cfg2 in zip(configs1, configs2):
            for key in cfg1.keys():
                assert cfg1[key] == cfg2[key]

    @given(space=search_space_strategy(), n=st.integers(min_value=1, max_value=50))
    @settings(max_examples=30, deadline=1000)
    def test_sobol_respects_bounds(self, space, n):
        """All Sobol configs must satisfy bounds."""
        assume(all(k.kind == "continuous" for k in space.knobs))

        if not all(k.kind == "continuous" for k in space.knobs):
            return

        searcher = SobolSearcher(space, seed=42)
        configs = searcher.propose(n)

        for cfg in configs:
            space.validate_config(cfg)


class TestSearchSpaceInvariants:
    """Property-based tests for SearchSpace invariants."""

    @given(space=search_space_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_sample_always_valid(self, space):
        """space.sample() must always produce valid config."""
        for _ in range(10):
            config = space.sample(seed=None)
            # Should not raise
            space.validate_config(config)

    @given(space=search_space_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_dimension_matches_knob_count(self, space):
        """space.dim must equal number of knobs."""
        assert space.dim == len(space.knobs)

    @given(space=search_space_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_get_knob_retrieves_all(self, space):
        """get_knob must retrieve every knob by name."""
        for knob in space.knobs:
            retrieved = space.get_knob(knob.name)
            assert retrieved.name == knob.name
            assert retrieved.kind == knob.kind
