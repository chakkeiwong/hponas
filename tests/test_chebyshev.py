"""
Test Chebyshev scalarization multi-objective searcher.

Tier 1: MO fallback method, no BoTorch dependency.
"""

import pytest
import numpy as np

from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_mo import ChebyshevSearcher


def test_chebyshev_basic():
    """ChebyshevSearcher proposes and optimizes 2-objective problem."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        base_searcher="random",
        seed=42
    )

    # Propose configurations
    configs = searcher.propose(5)
    assert len(configs) == 5
    assert all("x" in c and "y" in c for c in configs)

    # Observe results
    for config in configs:
        searcher.observe({
            "config": config,
            "objectives": {
                "obj1": config["x"] ** 2,
                "obj2": config["y"] ** 2
            },
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Check scalarized values computed
    assert len(searcher._scalarized) == 5


def test_chebyshev_scalarization():
    """Chebyshev scalarization computes weighted Chebyshev correctly."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        weights=np.array([0.5, 0.5]),
        reference_point=np.array([0.0, 0.0]),
        seed=42
    )

    # Test scalarization
    objectives = np.array([1.0, 2.0])
    scalarized = searcher._scalarize(objectives)

    # Chebyshev: max(0.5 * |1.0 - 0.0|, 0.5 * |2.0 - 0.0|) = max(0.5, 1.0) = 1.0
    assert abs(scalarized - 1.0) < 1e-6


def test_chebyshev_reference_point_adaptation():
    """ChebyshevSearcher adapts reference point from observed data."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    initial_ref = searcher.reference_point.copy()

    # Observe some results
    configs = searcher.propose(3)
    for i, config in enumerate(configs):
        searcher.observe({
            "config": config,
            "objectives": {"obj1": float(i), "obj2": float(i + 1)},
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Reference point should have updated (anti-ideal = worst on each objective)
    assert not np.allclose(searcher.reference_point, initial_ref)
    # Should be slightly worse than worst observed (1.1x)
    assert searcher.reference_point[0] >= 2.0  # Worst obj1 = 2.0
    assert searcher.reference_point[1] >= 3.0  # Worst obj2 = 3.0


def test_chebyshev_state_serialization():
    """ChebyshevSearcher state serializes and restores."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Observe some results
    configs = searcher.propose(3)
    for config in configs:
        searcher.observe({
            "config": config,
            "objectives": {"obj1": config["x"], "obj2": 1 - config["x"]},
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Save state
    state = searcher.state_dict()
    assert state["kind"] == "Chebyshev"
    assert len(state["configs"]) == 3

    # Restore state
    searcher2 = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=999
    )
    searcher2.load_state_dict(state)

    assert len(searcher2._configs) == 3
    assert searcher2.objectives == ["obj1", "obj2"]
    assert np.allclose(searcher2.weights, searcher.weights)


def test_chebyshev_with_gp():
    """ChebyshevSearcher works with GP base searcher."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = ChebyshevSearcher(
        space=space,
        objectives=["obj1", "obj2"],
        base_searcher="gp",
        seed=42
    )

    # Observe enough data for GP
    configs = searcher.propose(10)
    for config in configs:
        searcher.observe({
            "config": config,
            "objectives": {
                "obj1": config["x"] ** 2,
                "obj2": (1 - config["x"]) ** 2
            },
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Propose with GP acquisition
    bo_configs = searcher.propose(3)
    assert len(bo_configs) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
