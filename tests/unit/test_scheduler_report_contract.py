# Historical bootstrap/quota regression contract, explicitly retained for compatibility.
# Default reference ASHA is verified in test_asha_reference.py.
"""Report validation, stale updates, median state and budgeted recovery."""

import json

import numpy as np
import pytest

from hponas.schedulers import (
    ASHAConfig,
    ASHAScheduler,
    MOASHAConfig,
    MOASHAScheduler,
    BudgetedASHAConfig,
    BudgetedASHAScheduler,
)
from tests.unit.test_promotion_lifecycle import scheduler, report


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
@pytest.mark.parametrize("fidelity", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_fidelity_fails_before_recording_state(kind, fidelity):
    target = scheduler(kind)
    with pytest.raises(ValueError, match="(?i)fidelity"):
        report(target, "bad", fidelity, 1.0)
    assert target.state_dict()["trial_state"] == {}


@pytest.mark.parametrize("kind", ["scalar", "budgeted"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_scalar_reports_reject_nonfinite_objective(kind, value):
    with pytest.raises(ValueError, match="finite"):
        report(scheduler(kind), "bad", 1.0, value)


@pytest.mark.parametrize("config_type", [ASHAConfig, BudgetedASHAConfig, MOASHAConfig])
@pytest.mark.parametrize(
    "options",
    [
        {"eta": 1},
        {"eta": float("nan")},
        {"r_min": 0},
        {"r_min": float("inf")},
        {"r_max": float("nan")},
        {"r_max": 0.5},
    ],
)
def test_invalid_rung_controls_are_rejected_without_constructing_a_loop(
    config_type, options
):
    kwargs = {"eta": 3, "r_min": 1.0, "r_max": 9.0, **options}
    with pytest.raises(ValueError, match="^Require finite eta>1 and 0<r_min<=r_max$"):
        config_type(**kwargs)


@pytest.mark.parametrize('step', [0., -1., 10., float('nan'), float('inf')])
def test_report_grid_refuses_every_invalid_endpoint(step):
    with pytest.raises(ValueError) as raised:
        ASHAConfig(r_max=9., report_grid=(step,))
    assert str(raised.value) == 'report_grid must contain finite steps in (0, r_max]'
    assert ASHAConfig(r_max=9., report_grid=(1., 9.)).report_grid == (1., 9.)


@pytest.mark.parametrize('options,message', [
    ({'promotion_policy': 'unknown'}, 'Unknown ASHA promotion_policy'),
    ({'median_stopping': True}, 'Streamed median stopping requires an explicit report_grid'),
])
def test_scheduler_policy_refusal_explains_the_required_control(options, message):
    with pytest.raises(ValueError) as raised:
        ASHAConfig(**options)
    assert str(raised.value) == message


def test_streaming_history_snapshot_cannot_change_live_median_decisions():
    target = ASHAScheduler(ASHAConfig(r_min=2., r_max=2., median_stopping=True,
                                     median_min_completed=1, report_grid=(1., 2.)))
    target.report('reference', 1., 1., is_progress=True)
    target.report('reference', 2., 1., is_progress=True)
    target.finish('reference', 'completed')
    snapshot = target.state_dict()
    snapshot['running_histories']['reference'][1.] = 1000.
    assert target.state_dict()['running_histories']['reference'][1.] == 1.
    assert target.report('candidate', 1., 2., is_progress=True) == 'stop'


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
def test_stale_reports_do_not_rewind_active_trial_or_revive_terminal_trial(kind):
    target = scheduler(kind, r_max=8.0)
    assert target.rungs == [1.0, 3.0, 8.0]
    assert report(target, "trial", 1.0, 4.0) == "pause"
    assert target.promote() == [("trial", 3.0)]
    before = json.dumps(target.state_dict())
    assert report(target, "trial", 1.0, -10.0) == "continue"
    assert json.dumps(target.state_dict()) == before
    assert report(target, "trial", 3.0, 2.0) == "pause"
    assert target.promote() == [("trial", 8.0)]
    assert report(target, "trial", 8.0, 1.0) == "stop"
    before = json.dumps(target.state_dict())
    assert report(target, "trial", 8.0, -20.0) == "stop"
    assert report(target, "trial", 1.0, -20.0) == "stop"
    assert json.dumps(target.state_dict()) == before


def test_median_history_is_scoped_by_fidelity_deduplicated_and_restored():
    target = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", median_stopping=True))
    for i, value in enumerate([1.0, 2.0, 3.0, 4.0]):
        assert target.report(str(i), 2.0, value) == "continue"
    for _ in range(3):
        assert target.report("3", 2.0, 4.0) == "continue"
    # A different fidelity must not inherit the four measurements at fidelity 2.
    assert target.report("different", 4.0, 100.0) == "continue"
    state = json.loads(json.dumps(target.state_dict()))
    restored = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", ))
    restored.load_state_dict(state)
    assert restored.report("bad", 2.0, 5.0) == "stop"
    assert restored.report("bad", 2.0, -100.0) == "stop"
    assert restored.promote() == []
    assert len(restored.state_dict()["fidelity_history"][2.0]) == 5
    # Checkpoint writes must not mutate a live scheduler's nested median ledger.
    independent = target.state_dict()
    independent["median_reports"][2.0]["3"] = -100.0
    assert target.report("equal", 2.0, 3.0) == "continue"
    assert target.state_dict()["median_reports"][2.0]["3"] == 4.0


def test_budgeted_scheduler_exact_limit_survives_checkpoint_without_extra_promotion():
    target = BudgetedASHAScheduler(BudgetedASHAConfig(r_max=9.0, promotion_budget=2.0))
    assert target.report("first", 1.0, 1.0) == "pause"
    assert target.promote() == [("first", 3.0)]
    state = json.loads(json.dumps(target.state_dict()))
    restored = BudgetedASHAScheduler(BudgetedASHAConfig(promotion_budget=100.0))
    restored.load_state_dict(state)
    assert restored.state_dict() == target.state_dict()
    assert restored.report("first", 3.0, 0.5) == "pause"
    assert restored.promote() == []
    assert restored.report("first", 3.0, 0.25) == "stop"
    assert restored.state_dict()["budget_spent"] == 2.0
    independent = target.state_dict()
    independent["rung_populations"][0].append(("fake", -10.0))
    assert len(target.state_dict()["rung_populations"][0]) == 1


def test_multiobjective_recovery_preserves_ordered_values_and_dimensions():
    target = MOASHAScheduler(
        MOASHAConfig(r_min=1.0, r_max=9.0, objectives=["cost", "loss"])
    )
    assert target.reference_point.tolist() == [1.1, 1.1]
    assert target.report("a", 1.0, {"loss": 0.75, "cost": 0.25}) == "pause"
    state = json.loads(json.dumps(target.state_dict()))
    restored = scheduler("multiobjective")
    restored.load_state_dict(state)
    assert restored.state_dict() == target.state_dict()
    assert restored.n_objectives == 2
    assert restored.promote() == [("a", 3.0)]
    assert restored.report("bad", 1.0, {"cost": float("nan"), "loss": 0.0}) == "stop"
    state = restored.state_dict()["trial_state"]["bad"]
    assert state[3:] == ["vetoed", True]
    assert state[2] == [0.0, 0.0]


def test_multiobjective_fronts_and_rectangles_include_shared_coordinates_and_ties():
    target = MOASHAScheduler(
        MOASHAConfig(
            r_min=1.0, r_max=9.0, objectives=["x", "y"], reference_point=[1.0, 1.0]
        )
    )
    points = np.array([[0.2, 0.2], [0.2, 0.2], [0.2, 0.4], [0.4, 0.2], [0.5, 0.5]])
    fronts = target._fast_non_dominated_sort(points)
    assert [set(front) for front in fronts] == [{0, 1}, {2, 3}, {4}]
    mask = target._compute_pareto_mask(points)
    assert mask.dtype == bool and mask.tolist() == [True, True, False, False, False]
    assert target._dominated_hypervolume(np.array([0.2, 0.5])) == pytest.approx(0.4)
    assert target._dominated_hypervolume(np.array([1.2, 0.5])) == 0.0
    contributions = target._compute_hypervolume_contributions(
        [("a", np.array([0.2, 0.2])), ("b", np.array([0.2, 0.4]))]
    )
    assert contributions == pytest.approx([0.16, 0.0])
    assert target._fast_non_dominated_sort(np.array([[0.2, 0.2], [0.4, 0.4]])) == [
        [0],
        [1],
    ]


@pytest.mark.parametrize("kind", ["scalar", "multiobjective", "budgeted"])
def test_rung_matching_strict_tolerance_has_an_executable_boundary(kind):
    options = {"r_min": 1e-6, "r_max": 1e-6}
    if kind == "scalar":
        target = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap", **options))
    elif kind == "budgeted":
        target = BudgetedASHAScheduler(BudgetedASHAConfig(**options))
    else:
        target = MOASHAScheduler(MOASHAConfig(**options, objectives=["loss", "cost"]))
    # These binary floats subtract to exactly the encoded tolerance. Equality
    # at the boundary is not an equivalent mutation merely because it is rare.
    assert 2e-6 - 1e-6 == 1e-6
    assert report(target, "outside", 2e-6, 1.0) == "continue"
    assert report(target, "inside", 1.5e-6, 1.0) == "stop"
