"""Test input validation for defensive programming."""

import pytest
from hponas.searchers.gp_searcher import GPSearcher
from hponas.space import Knob, SearchSpace


class TestGPSearcherValidation:
    """Test GPSearcher input validation."""

    def test_rejects_negative_seed(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="seed must be non-negative"):
            GPSearcher(space, seed=-1)

    def test_rejects_string_seed(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(TypeError, match="seed must be int or None"):
            GPSearcher(space, seed="42")

    def test_rejects_float_seed(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(TypeError, match="seed must be int or None"):
            GPSearcher(space, seed=42.0)

    def test_accepts_none_seed(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        searcher = GPSearcher(space, seed=None)
        assert searcher.seed is None

    def test_accepts_valid_seed(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        searcher = GPSearcher(space, seed=42)
        assert searcher.seed == 42

    def test_rejects_zero_initial_samples(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="initial_random_samples must be positive"):
            GPSearcher(space, initial_random_samples=0)

    def test_rejects_negative_initial_samples(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="initial_random_samples must be positive"):
            GPSearcher(space, initial_random_samples=-1)

    def test_rejects_float_initial_samples(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="initial_random_samples must be positive"):
            GPSearcher(space, initial_random_samples=5.5)

    def test_rejects_zero_num_restarts(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="num_restarts must be positive"):
            GPSearcher(space, num_restarts=0)

    def test_rejects_negative_num_restarts(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="num_restarts must be positive"):
            GPSearcher(space, num_restarts=-1)

    def test_rejects_invalid_kernel(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        with pytest.raises(ValueError, match="Only matern52 kernel supported"):
            GPSearcher(space, kernel="rbf")

    def test_accepts_valid_parameters(self):
        space = SearchSpace([Knob(name='x', kind='continuous', bounds=(0.0, 1.0))])
        searcher = GPSearcher(
            space,
            seed=42,
            initial_random_samples=10,
            num_restarts=20,
            kernel="matern52"
        )
        assert searcher.seed == 42
        assert searcher.initial_random_samples == 10
        assert searcher.num_restarts == 20
        assert searcher.kernel == "matern52"
