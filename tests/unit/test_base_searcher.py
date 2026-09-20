"""Tests for BaseSearcher.get_best() method."""

import pytest
from hponas.searchers.base import BaseSearcher
from hponas.types import SearchSpace, Result, Config


class DummySearcher(BaseSearcher):
    """Minimal searcher for testing BaseSearcher methods."""

    def suggest(self) -> Config:
        return Config(values={"x": 0.5})


@pytest.fixture
def search_space():
    """Simple search space for testing."""
    return SearchSpace(parameters={})


@pytest.fixture
def searcher(search_space):
    """Dummy searcher instance."""
    return DummySearcher(search_space, seed=42)


def test_get_best_maximize_returns_highest(searcher):
    """get_best(maximize=True) returns result with highest objective value."""
    # Add results with different objective values
    searcher.history = [
        Result(trial_id="t1", objective_value=0.5, status="completed"),
        Result(trial_id="t2", objective_value=0.9, status="completed"),
        Result(trial_id="t3", objective_value=0.3, status="completed"),
    ]

    best = searcher.get_best(maximize=True)
    assert best is not None
    assert best.trial_id == "t2"
    assert best.objective_value == 0.9


def test_get_best_minimize_returns_lowest(searcher):
    """get_best(maximize=False) returns result with lowest objective value."""
    searcher.history = [
        Result(trial_id="t1", objective_value=0.5, status="completed"),
        Result(trial_id="t2", objective_value=0.1, status="completed"),
        Result(trial_id="t3", objective_value=0.8, status="completed"),
    ]

    best = searcher.get_best(maximize=False)
    assert best is not None
    assert best.trial_id == "t2"
    assert best.objective_value == 0.1


def test_get_best_filters_invalid_results(searcher):
    """get_best() ignores results with is_valid()=False."""
    searcher.history = [
        Result(trial_id="t1", objective_value=0.5, status="completed"),
        Result(trial_id="t2", objective_value=float('nan'), status="failed"),
        Result(trial_id="t3", objective_value=float('inf'), status="completed"),
        Result(trial_id="t4", objective_value=0.9, status="completed"),
    ]

    best = searcher.get_best(maximize=True)
    assert best is not None
    assert best.trial_id == "t4"
    assert best.objective_value == 0.9


def test_get_best_returns_none_when_empty(searcher):
    """get_best() returns None when history is empty."""
    assert searcher.history == []
    assert searcher.get_best(maximize=True) is None
    assert searcher.get_best(maximize=False) is None


def test_get_best_returns_none_when_all_invalid(searcher):
    """get_best() returns None when all results are invalid."""
    searcher.history = [
        Result(trial_id="t1", objective_value=float('nan'), status="failed"),
        Result(trial_id="t2", objective_value=float('inf'), status="completed"),
    ]

    assert searcher.get_best(maximize=True) is None
    assert searcher.get_best(maximize=False) is None


def test_get_best_with_single_valid_result(searcher):
    """get_best() returns the only valid result."""
    searcher.history = [
        Result(trial_id="t1", objective_value=0.7, status="completed"),
    ]

    best_max = searcher.get_best(maximize=True)
    best_min = searcher.get_best(maximize=False)

    assert best_max is not None
    assert best_min is not None
    assert best_max.trial_id == "t1"
    assert best_min.trial_id == "t1"


def test_get_best_with_negative_values(searcher):
    """get_best() handles negative objective values correctly."""
    searcher.history = [
        Result(trial_id="t1", objective_value=-0.5, status="completed"),
        Result(trial_id="t2", objective_value=-0.9, status="completed"),
        Result(trial_id="t3", objective_value=-0.1, status="completed"),
    ]

    best_max = searcher.get_best(maximize=True)
    best_min = searcher.get_best(maximize=False)

    assert best_max.objective_value == -0.1
    assert best_min.objective_value == -0.9
