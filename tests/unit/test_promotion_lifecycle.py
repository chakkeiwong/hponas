# Historical bootstrap/quota regression contract, explicitly retained for compatibility.
# Default reference ASHA is verified in test_asha_reference.py.
"""Promotion decisions must remain valid across reports, vetoes and recovery."""

import json

import pytest

from hponas.schedulers import (
    ASHAConfig,
    ASHAScheduler,
    MOASHAConfig,
    MOASHAScheduler,
    BudgetedASHAConfig,
    BudgetedASHAScheduler,
)


def scheduler(kind, r_max=9):
    if kind == "scalar":
        return ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", eta=3, r_min=1, r_max=r_max))
    if kind == "budgeted":
        return BudgetedASHAScheduler(
            BudgetedASHAConfig(eta=3, r_min=1, r_max=r_max, promotion_budget=1000.0)
        )
    return MOASHAScheduler(
        MOASHAConfig(
            eta=3,
            r_min=1,
            r_max=r_max,
            objectives=["loss", "cost"],
            reference_point=[20.0, 20.0],
        )
    )


def report(target, tid, fidelity, value):
    if isinstance(target, MOASHAScheduler):
        value = {"loss": value, "cost": value}
    return target.report(tid, fidelity, value)


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
@pytest.mark.parametrize("population,winners", [(1, 1), (3, 3), (4, 2), (7, 3)])
def test_promotion_quota_terminal_states_and_resume(kind, population, winners):
    target = scheduler(kind)
    ids = [f"candidate-{population - i}" for i in range(population)]
    for i in reversed(range(population)):
        assert report(target, ids[i], 1, i) == "pause"
    expected = {(ids[i], 3) for i in range(winners)}
    assert set(target.promote()) == expected
    checkpoint = json.loads(json.dumps(target.state_dict()))
    for i in range(population):
        state = checkpoint["trial_state"][ids[i]]
        assert state[0:2] == ([1, 3] if i < winners else [0, 1])
        assert state[4 if kind == "budgeted" else 3] == (
            "active" if i < winners else "stopped"
        )
        if kind == "multiobjective":
            assert state[4] is False
    restored = scheduler(kind)
    restored.load_state_dict(checkpoint)
    assert restored.promote() == []  # active trials must not redispatch
    for i in range(winners, population):
        assert report(restored, ids[i], 3, -10) == "stop"
    for i in range(winners):
        assert report(restored, ids[i], 3, i) == "pause"
    assert set(restored.promote()) == {(ids[i], 9) for i in range(winners)}
    assert restored.promote() == []
    for i in range(winners):
        assert report(restored, ids[i], 9, i) == "stop"
    assert restored.promote() == []


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
def test_empty_lower_rung_does_not_hide_later_rung(kind):
    target = scheduler(kind)
    assert report(target, "already-trained", 3, 1.0) == "pause"
    assert target.promote() == [("already-trained", 9)]
    assert target.promote() == []


def test_veto_after_initial_report_removes_candidate_and_never_revives_it():
    target = scheduler("multiobjective")
    assert report(target, "vetoed", 1, 0.0) == "pause"
    assert report(target, "vetoed", 1, float("nan")) == "stop"
    assert report(target, "eligible", 1, 1.0) == "pause"
    assert target.promote() == [("eligible", 3)]
    assert report(target, "vetoed", 3, -100.0) == "stop"
    assert report(target, "eligible", 3, 0.5) == "pause"
    assert target.promote() == [("eligible", 9)]


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
def test_final_rung_is_not_a_source_of_promotions(kind):
    target = scheduler(kind, r_max=1)
    assert report(target, "done", 1, 0.5) == "stop"
    assert target.promote() == []
