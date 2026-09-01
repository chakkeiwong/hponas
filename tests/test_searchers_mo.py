"""
Test multi-objective searchers (qLogNEHVI).

Tier 1 validation: MO stack operational for 2-3 objectives.
"""

import pytest
import numpy as np

from hponas import SearchSpace
from hponas.space import Knob

try:
    from hponas.searchers_mo import qLogNEHVISearcher
    BOTORCH_AVAILABLE = True
except ImportError:
    BOTORCH_AVAILABLE = False


@pytest.mark.skipif(not BOTORCH_AVAILABLE, reason="BoTorch not installed")
def test_qlogNEHVI_basic():
    """qLogNEHVISearcher proposes configurations for 2-objective problem."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))
    space.add_knob(Knob("y", kind="continuous", bounds=(0, 1)))

    searcher = qLogNEHVISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Propose initial batch
    configs = searcher.propose(5)
    assert len(configs) == 5
    assert all("x" in c and "y" in c for c in configs)

    # Observe results
    for i, config in enumerate(configs):
        searcher.observe({
            "config": config,
            "objectives": {
                "obj1": config["x"] ** 2,
                "obj2": config["y"] ** 2
            },
            "fidelity": 1.0,
            "cost": 1.0
        })

    # Propose BO batch (should use GP now)
    bo_configs = searcher.propose(3)
    assert len(bo_configs) == 3


@pytest.mark.skipif(not BOTORCH_AVAILABLE, reason="BoTorch not installed")
def test_qlogNEHVI_pareto_front():
    """qLogNEHVISearcher computes Pareto front correctly."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = qLogNEHVISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=42
    )

    # Test Pareto mask computation
    Y = np.array([
        [1.0, 2.0],  # Dominated by [0.5, 1.0]
        [0.5, 1.0],  # Pareto optimal
        [2.0, 0.5],  # Pareto optimal
        [3.0, 3.0],  # Dominated
    ])

    pareto_mask = searcher._compute_pareto_mask(Y)

    # Expected: indices 1 and 2 are Pareto optimal
    assert pareto_mask[1] == True
    assert pareto_mask[2] == True
    assert pareto_mask[0] == False
    assert pareto_mask[3] == False


@pytest.mark.skipif(not BOTORCH_AVAILABLE, reason="BoTorch not installed")
def test_qlogNEHVI_state_serialization():
    """qLogNEHVISearcher state serializes and restores."""
    space = SearchSpace()
    space.add_knob(Knob("x", kind="continuous", bounds=(0, 1)))

    searcher = qLogNEHVISearcher(
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
    assert state["kind"] == "qLogNEHVI"
    assert len(state["X"]) == 3

    # Restore state
    searcher2 = qLogNEHVISearcher(
        space=space,
        objectives=["obj1", "obj2"],
        seed=999
    )
    searcher2.load_state_dict(state)

    assert len(searcher2._X) == 3
    assert searcher2.objectives == ["obj1", "obj2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
