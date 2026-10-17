"""Prospective public PASHA refusal, continuation and checkpoint contracts."""

import copy
import json
import math

import pytest

from hponas.schedulers import PASHAConfig, PASHAScheduler


def scheduler(**options):
    return PASHAScheduler(PASHAConfig(**options))


def first_pair(target):
    for tid, value in (("a", 0.), ("b", 1.), ("c", 2.), ("d", 3.)):
        assert target.report(tid, 1., value) == "pause"
    assert target.promote() == [("a", 3.)]
    assert target.promote() == [("b", 3.)]


@pytest.mark.parametrize("fidelity,value", [
    (0., 1.), (-1., 1.), (math.nan, 1.), (math.inf, 1.), (-math.inf, 1.),
    (1., math.nan), (1., math.inf), (1., -math.inf),
])
def test_invalid_report_refusal_preserves_scheduler_state(fidelity, value):
    target = scheduler()
    target.report("existing", 1., 0.)
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.report("new", fidelity, value)
    assert str(error.value) == "Reports require positive fidelity and a finite value"
    assert target.state_dict() == before


@pytest.mark.parametrize("fidelity", [1., 2., 3., 4., 9.])
def test_terminal_trial_never_reopens_or_rewrites_state(fidelity):
    target = scheduler(r_max=3.)
    first_pair(target)
    assert target.report("a", 3., .5) == "stop"
    before = copy.deepcopy(target.state_dict())
    assert target.report("a", fidelity, -100.) == "stop"
    assert target.state_dict() == before


def test_conflicting_duplicate_reports_are_precise_and_atomic():
    target = scheduler()
    target.report("a", 1., .5)
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.report("a", 1., .7)
    assert str(error.value) == "Conflicting duplicate scheduler report"
    assert target.state_dict() == before


@pytest.mark.parametrize("fidelity", [3.000002, 3.1, 4., 9.])
def test_cap_overshoot_is_refused_before_state_changes(fidelity):
    target = scheduler()
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.report("a", fidelity, .5)
    assert str(error.value) == "Report exceeds PASHA's current maximum fidelity"
    assert target.state_dict() == before


def test_cap_tolerance_includes_its_representable_endpoint_only():
    target = scheduler()
    boundary = target.current_max_fidelity + 1e-6
    assert target.report("a", boundary, .5) == "continue"
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError, match="maximum fidelity"):
        target.report("b", math.nextafter(boundary, math.inf), .5)
    assert target.state_dict() == before


def test_promoted_checkpoint_records_correct_rung_and_resumable_status():
    target = scheduler()
    target.report("a", 1., 0.)
    target.report("b", 1., 1.)
    assert target.promote() == [("a", 3.)]
    state = json.loads(json.dumps(target.state_dict()))
    assert state["trial_state"]["a"] == [1, 3., 0., 2., "active"]
    restored = scheduler()
    restored.load_state_dict(state)
    assert restored.report("a", 2., .25) == "continue"
    assert restored.report("a", 3., .5) == "pause"
    assert restored.state_dict()["resource_reports"]["a"] == {1.: 0., 2.: .25, 3.: .5}


def test_budget_skip_can_find_a_later_affordable_tied_trial():
    target = scheduler(promotion_budget=2.)
    assert target.report("earlier", 1. - 5e-7, 0.) == "pause"
    assert target.report("affordable", 1., 0.) == "pause"
    assert target.promote() == [("affordable", 3.)]
    assert target.state_dict()["budget_spent"] == 2.
    assert target.promote() == []


def test_rank_reversal_at_final_fidelity_cannot_grow_past_last_rung():
    target = scheduler(r_max=3., ranking_epsilon=0.)
    first_pair(target)
    assert target.report("a", 3., 10.) == "stop"
    assert target.report("b", 3., -1.) == "stop"
    assert target.current_max_fidelity == 3.
    assert target.state_dict()["current_top"] == 1
    assert target.promote() == []


def test_zero_fidelity_is_invalid_even_for_a_terminal_trial():
    target = scheduler(r_max=1.)
    assert target.report("a", 1., 0.) == "stop"
    before = copy.deepcopy(target.state_dict())
    with pytest.raises(ValueError) as error:
        target.report("a", 0., 1.)
    assert str(error.value) == "Reports require positive fidelity and a finite value"
    assert target.state_dict() == before


def test_saved_nested_report_mapping_is_owned_by_the_caller():
    target = scheduler()
    target.report("a", .5, 1.)
    target.report("a", 1., 0.)
    saved = target.state_dict()
    expected = copy.deepcopy(saved)
    saved["resource_reports"]["a"][1.] = 100.
    saved["resource_reports"]["a"][2.] = -1.
    assert target.state_dict() == expected
    assert target.report("a", 1., 0.) == "pause"


@pytest.mark.parametrize("values,epsilon", [
    ((-1., -1., -1., 0., 0., -1.), 0.),
    ((-1., -1., -1., 0., -1., -1., -1., -1., 0.), .9),
])
def test_ties_use_strict_ordering_in_temporary_reversal_tolerance(values, epsilon):
    count = len(values) // 3
    target = scheduler()
    for index, value in enumerate(values[:count]):
        target.report(chr(ord("a") + index), 1., value)
    for index in range(2 * count - 2):
        target.report(f"decoy-{index}", 1., 100.)
    promoted = [target.promote() for _ in range(count)]
    assert {tid for row in promoted for tid, _ in row} == {
        chr(ord("a") + i) for i in range(count)}
    for step in (2, 3):
        for index in range(count):
            target.report(chr(ord("a") + index), float(step), values[count * (step - 1) + index])
    assert target.state_dict()["epsilon"] == epsilon
    assert target.current_max_fidelity == 3.


def test_accepted_sparse_checkpoint_considers_lower_populated_rung():
    target = scheduler()
    target.report("a", 1., 0.)
    target.report("b", 1., 1.)
    state = json.loads(json.dumps(target.state_dict()))
    # The public recovery schema accepts every in-range resource cap, including
    # sparse imported populations. It does not require a cap-growth history.
    # Once accepted, the lower eligible rung must remain dispatchable.
    state["current_top"] = 2
    restored = scheduler()
    restored.load_state_dict(state)
    assert restored.current_max_fidelity == 9.
    assert restored.promote() == [("a", 3.)]
    assert restored.report("a", 2., .5) == "continue"
