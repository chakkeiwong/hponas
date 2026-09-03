"""
Test MO-ASHA: Multi-objective Asynchronous Successive Halving.

BUILD_PROGRAM_v2.md: Tier 1 MO stack (~4d).
"""

import pytest
import numpy as np

from hponas.schedulers import MOASHAScheduler, MOASHAConfig


def test_mo_asha_basic():
    """MO-ASHA schedules multi-objective trials through rungs."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=9.0,
        eta=3.0,
        objectives=["loss", "latency"]
    )

    scheduler = MOASHAScheduler(config)

    # Rungs should be [1, 3, 9]
    assert len(scheduler.rungs) == 3
    assert scheduler.rungs == [1.0, 3.0, 9.0]

    # Launch 9 trials at first rung
    for i in range(9):
        decision = scheduler.report(
            f"trial_{i}",
            fidelity=1.0,
            objectives={
                "loss": 1.0 + i * 0.1,  # trial_0 best on loss
                "latency": 2.0 - i * 0.05  # trial_8 best on latency
            }
        )
        assert decision == "pause"

    # Promote: should select ~3 trials (top 1/eta)
    promotions = scheduler.promote()
    assert 2 <= len(promotions) <= 4  # Allow some flexibility

    # Promoted trials should get next fidelity
    for trial_id, next_fid in promotions:
        assert next_fid == 3.0


def test_mo_asha_pareto_ranking():
    """MO-ASHA promotes based on Pareto dominance."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=3.0,
        eta=2.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # Report 4 trials with different trade-offs
    # trial_0: (1.0, 3.0) - dominated
    # trial_1: (2.0, 1.0) - Pareto optimal
    # trial_2: (1.5, 2.0) - Pareto optimal
    # trial_3: (3.0, 3.0) - dominated

    scheduler.report("trial_0", 1.0, {"f1": 1.0, "f2": 3.0})
    scheduler.report("trial_1", 1.0, {"f1": 2.0, "f2": 1.0})
    scheduler.report("trial_2", 1.0, {"f1": 1.5, "f2": 2.0})
    scheduler.report("trial_3", 1.0, {"f1": 3.0, "f2": 3.0})

    # Promote top 1/2 = 2 trials
    promotions = scheduler.promote()
    promoted_ids = [tid for tid, _ in promotions]

    # Should promote Pareto-optimal trials
    assert len(promoted_ids) == 2
    assert "trial_1" in promoted_ids
    assert "trial_2" in promoted_ids


def test_mo_asha_hypervolume_contribution():
    """MO-ASHA correctly computes hypervolume contributions."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=3.0,
        eta=2.0,
        objectives=["f1", "f2"],
        reference_point=[2.0, 2.0]
    )

    scheduler = MOASHAScheduler(config)

    # Population with known hypervolume contributions
    population = [
        ("trial_0", np.array([0.5, 0.5])),  # High contribution (far from reference)
        ("trial_1", np.array([1.5, 1.5])),  # Low contribution (close to reference)
    ]

    contributions = scheduler._compute_hypervolume_contributions(population)

    # trial_0 should have higher contribution
    assert contributions[0] > contributions[1]


def test_mo_asha_final_rung_stops():
    """MO-ASHA stops trials at final rung."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=3.0,
        eta=3.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # At final rung (3.0), should stop
    decision = scheduler.report("trial_0", 3.0, {"f1": 1.0, "f2": 2.0})
    assert decision == "stop"


def test_mo_asha_non_rung_fidelity():
    """MO-ASHA continues at non-rung fidelities."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=9.0,
        eta=3.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # At non-rung fidelity, should continue
    decision = scheduler.report("trial_0", 2.0, {"f1": 1.0, "f2": 2.0})
    assert decision == "continue"


def test_mo_asha_small_population():
    """MO-ASHA promotes all trials when population <= eta."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=9.0,
        eta=5.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # Report only 3 trials (< eta=5)
    for i in range(3):
        scheduler.report(f"trial_{i}", 1.0, {"f1": float(i), "f2": float(i)})

    # Should promote all 3
    promotions = scheduler.promote()
    assert len(promotions) == 3


def test_mo_asha_requires_two_objectives():
    """MO-ASHA requires at least 2 objectives."""
    with pytest.raises(ValueError, match="at least 2 objectives"):
        config = MOASHAConfig(
            r_min=1.0,
            r_max=9.0,
            eta=3.0,
            objectives=["f1"]  # Only 1 objective
        )
        MOASHAScheduler(config)


def test_mo_asha_pareto_mask():
    """MO-ASHA correctly identifies Pareto front."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=3.0,
        eta=2.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # Test objectives
    objectives = np.array([
        [1.0, 3.0],  # Dominated by [0.5, 0.5]
        [0.5, 0.5],  # Pareto optimal (dominates all others here)
        [2.0, 1.0],  # Dominated by [0.5, 0.5]
        [3.0, 3.0],  # Dominated
    ])

    pareto_mask = scheduler._compute_pareto_mask(objectives)

    assert pareto_mask[0] == False  # Dominated
    assert pareto_mask[1] == True   # Pareto optimal
    assert pareto_mask[2] == False  # [0.5, 0.5] is better on both objectives
    assert pareto_mask[3] == False  # Dominated


def test_mo_asha_pareto_mask_genuine_tradeoff():
    """MO-ASHA keeps both points when neither dominates the other."""
    config = MOASHAConfig(
        r_min=1.0,
        r_max=3.0,
        eta=2.0,
        objectives=["f1", "f2"]
    )

    scheduler = MOASHAScheduler(config)

    # Genuine trade-off: neither point dominates the other
    objectives = np.array([
        [0.5, 2.0],  # Better on f1
        [2.0, 0.5],  # Better on f2
        [3.0, 3.0],  # Dominated by both
    ])

    pareto_mask = scheduler._compute_pareto_mask(objectives)

    assert pareto_mask[0] == True
    assert pareto_mask[1] == True
    assert pareto_mask[2] == False
