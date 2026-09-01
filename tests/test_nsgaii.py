"""
Test NSGA-II evolutionary multi-objective searcher.

Tier 1: MO evolutionary algorithm.
"""

import pytest
import numpy as np

from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_mo import NSGAIISearcher


def test_nsgaii_initialization():
    """NSGA-II initializes with random population."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        population_size=10,
        seed=42
    )

    # Propose initial population
    configs = searcher.propose(10)
    assert len(configs) == 10
    assert all("x" in c and "y" in c for c in configs)


def test_nsgaii_pareto_dominance():
    """NSGA-II correctly identifies Pareto dominance."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Test dominance
    obj_a = np.array([1.0, 2.0])
    obj_b = np.array([2.0, 3.0])  # Dominated by a
    obj_c = np.array([0.5, 3.0])  # Not dominated by a or b

    assert searcher._pareto_dominates(obj_a, obj_b)
    assert not searcher._pareto_dominates(obj_b, obj_a)
    assert not searcher._pareto_dominates(obj_a, obj_c)


def test_nsgaii_fast_non_dominated_sort():
    """NSGA-II fast non-dominated sorting works correctly."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Test sorting with known fronts
    objectives = [
        np.array([1.0, 3.0]),  # Front 0
        np.array([2.0, 2.0]),  # Front 0
        np.array([3.0, 1.0]),  # Front 0
        np.array([2.5, 2.5]),  # Front 1 (dominated by 1)
        np.array([4.0, 4.0]),  # Front 2 (dominated by all)
    ]

    fronts = searcher._fast_non_dominated_sort(objectives)

    assert len(fronts) >= 2
    # Front 0 should have 3 non-dominated solutions
    assert len(fronts[0]) == 3
    assert set(fronts[0]) == {0, 1, 2}


def test_nsgaii_crowding_distance():
    """NSGA-II crowding distance computation."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Front with 3 solutions
    objectives = [
        np.array([1.0, 3.0]),
        np.array([2.0, 2.0]),
        np.array([3.0, 1.0]),
    ]

    distances = searcher._crowding_distance([0, 1, 2], objectives)

    # Boundary points should have infinite distance
    assert distances[0] == np.inf or distances[2] == np.inf
    # Interior point should have finite distance
    assert np.isfinite(distances[1])


def test_nsgaii_evolution():
    """NSGA-II evolves population over generations."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        population_size=20,
        seed=42
    )

    # Initialize population
    gen0 = searcher.propose(20)
    assert len(gen0) == 20

    # Evaluate initial population
    for config in gen0:
        searcher.observe({
            "config": config,
            "objectives": {
                "obj1": config["x"] ** 2 + config["y"] ** 2,
                "obj2": (config["x"] - 1) ** 2 + (config["y"] - 1) ** 2
            },
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Generate offspring
    gen1 = searcher.propose(10)
    assert len(gen1) == 10

    # Evaluate offspring
    for config in gen1:
        searcher.observe({
            "config": config,
            "objectives": {
                "obj1": config["x"] ** 2 + config["y"] ** 2,
                "obj2": (config["x"] - 1) ** 2 + (config["y"] - 1) ** 2
            },
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Population should be truncated to population_size
    assert len(searcher._population) == 20


def test_nsgaii_sbx_crossover():
    """NSGA-II SBX crossover produces valid offspring."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    parent1 = np.array([0.2, 0.8])
    parent2 = np.array([0.7, 0.3])

    child1, child2 = searcher._sbx_crossover(parent1, parent2)

    # Children should be in [0, 1]
    assert np.all((child1 >= 0) & (child1 <= 1))
    assert np.all((child2 >= 0) & (child2 <= 1))


def test_nsgaii_polynomial_mutation():
    """NSGA-II polynomial mutation produces valid offspring."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        mutation_prob=1.0,  # Always mutate for testing
        seed=42
    )

    individual = np.array([0.5, 0.5])
    mutated = searcher._polynomial_mutation(individual)

    # Mutated should be in [0, 1]
    assert np.all((mutated >= 0) & (mutated <= 1))
    # Should be different from original (high mutation prob)
    assert not np.allclose(mutated, individual)


def test_nsgaii_state_serialization():
    """NSGA-II state serializes and restores."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        population_size=10,
        seed=42
    )

    # Initialize and evaluate
    configs = searcher.propose(10)
    for config in configs:
        searcher.observe({
            "config": config,
            "objectives": {"obj1": config["x"], "obj2": 1 - config["x"]},
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Save state
    state = searcher.state_dict()
    assert state["kind"] == "NSGA-II"
    assert len(state["population"]) == 10

    # Restore state
    searcher2 = NSGAIISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=999
    )
    searcher2.load_state_dict(state)

    assert len(searcher2._population) == 10
    assert searcher2.population_size == 10
    assert searcher2.objectives == ["obj1", "obj2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
