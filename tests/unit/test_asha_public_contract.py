"""Public reference-ASHA lifecycle, diagnostics and streamed median boundaries."""

import json

import pytest

from hponas.schedulers import ASHAConfig, ASHAScheduler


def snapshot(target):
    return json.loads(json.dumps(target.state_dict()))


@pytest.mark.parametrize("fidelity,value", [(0., 1.), (-1., 1.), (float("nan"), 1.),
    (float("inf"), 1.), (1., float("nan")), (1., float("inf"))])
def test_invalid_reference_report_refuses_precisely_before_changing_state(fidelity, value):
    target = ASHAScheduler(ASHAConfig(r_max=9))
    target.report("existing", 1., 3.)
    before = snapshot(target)
    with pytest.raises(ValueError) as caught:
        target.report("existing", fidelity, value)
    assert str(caught.value) == "Reports require positive fidelity and a finite value"
    assert snapshot(target) == before


def test_reference_promotion_orders_loss_independently_of_ids_and_updates_owned_state():
    target = ASHAScheduler(ASHAConfig(eta=2, r_max=4))
    for name, value in [("a", 10.), ("b", 9.), ("y", 2.), ("z", 1.)]:
        assert target.report(name, 1., value) == "pause"
    assert target.promote() == [("z", 2.)]
    assert target.promote() == [("y", 2.)]
    assert target.promote() == []
    state = snapshot(target)
    assert state["trial_state"] == {
        "a": [0, 1., 10., "paused"], "b": [0, 1., 9., "paused"],
        "y": [1, 2., 2., "active"], "z": [1, 2., 1., "active"],
    }
    restored = ASHAScheduler(ASHAConfig(eta=2, r_max=4))
    restored.load_state_dict(state)
    assert snapshot(restored) == state and restored.promote() == []


def test_legacy_dispatch_keeps_its_distinct_duplicate_report_contract():
    target = ASHAScheduler(ASHAConfig(r_max=3, promotion_policy="legacy_bootstrap"))
    assert target.report("one", 1., 2.) == "pause"
    assert target.report("one", 1., 1.) == "pause"
    assert snapshot(target)["last_reports"] == {}
    assert target.promote() == [("one", 3.)]


def test_paused_trials_require_promotion_and_stale_reports_never_rewrite_the_ledger():
    target = ASHAScheduler(ASHAConfig(r_min=3, r_max=9))
    assert target.report("one", 3., 2.) == "pause"
    before = snapshot(target)
    assert target.report("one", 4., -100., is_progress=True) == "pause"
    assert target.report("one", 2., -200., is_progress=True) == "continue"
    assert snapshot(target) == before
    with pytest.raises(ValueError) as caught:
        target.report("one", 3., 0.)
    assert str(caught.value) == "Conflicting duplicate scheduler report"
    assert snapshot(target) == before


def test_final_rung_report_is_stopped_before_finish_and_cannot_be_reopened():
    target = ASHAScheduler(ASHAConfig(r_max=9))
    assert target.report("final", 9., 2.) == "stop"
    before = snapshot(target)
    assert before["trial_state"]["final"] == [2, 9., 2., "stopped"]
    assert before["last_reports"]["final"] == [9., 2., "stop"]
    assert before["terminal"] == {}  # Endpoint reporting is not completion.
    assert target.report("final", 1., -100.) == "stop"
    assert snapshot(target) == before


@pytest.mark.parametrize("status", ["failed", "cancelled", "pruned"])
def test_terminal_outcome_preserves_reported_values_and_stops_trials_without_a_rung(status):
    target = ASHAScheduler(ASHAConfig(r_max=9))
    target.report("one", 1., 2.)
    target.finish("one", status)
    state = snapshot(target)
    assert state["trial_state"]["one"] == [0, 1., 2., "stopped"]
    assert state["terminal"] == {"one": status}
    target.finish("one", status)
    assert snapshot(target) == state
    with pytest.raises(ValueError) as caught:
        target.finish("one", "completed")
    assert str(caught.value) == "Conflicting terminal trial status"
    assert snapshot(target) == state
    target.finish("unreported", status)
    before = snapshot(target)
    assert target.report("unreported", 1., 2.) == "stop"
    assert snapshot(target) == before


@pytest.mark.parametrize("status", [None, "", "running", "PRUNED", "XXprunedXX"])
def test_unknown_terminal_outcome_is_precise_and_atomic(status):
    target = ASHAScheduler(ASHAConfig(r_max=9))
    before = snapshot(target)
    with pytest.raises(ValueError) as caught:
        target.finish("one", status)
    assert str(caught.value) == "Unknown terminal trial status"
    assert snapshot(target) == before


@pytest.mark.parametrize("reported", [False, True])
def test_completion_requires_a_full_fidelity_report_without_overwriting_live_state(reported):
    target = ASHAScheduler(ASHAConfig(r_max=9))
    if reported:
        target.report("one", 1., 2.)
    before = snapshot(target)
    with pytest.raises(ValueError) as caught:
        target.finish("one", "completed")
    assert str(caught.value) == "Completion requires a full-fidelity report"
    assert snapshot(target) == before


def median_target(**options):
    return ASHAScheduler(ASHAConfig(r_min=4, r_max=4, median_stopping=True,
                                   report_grid=(1., 2., 3., 4.), **options))


def completed_reference(target, name, values):
    for step, value in enumerate(values, 1):
        target.report(name, float(step), float(value), is_progress=True)
    target.finish(name, "completed")


def test_median_includes_the_current_step_and_serializes_the_exact_pruned_outcome():
    target = median_target()
    for i in range(5):
        completed_reference(target, str(i), [0., 10., 0., 0.])
    # The first value is better than the reference; only including step two
    # makes the candidate running mean 10 worse than the reference mean 5.
    assert target.report("candidate", 1., -10., is_progress=True) == "continue"
    assert target.report("candidate", 2., 30., is_progress=True) == "stop"
    state = snapshot(target)
    assert state["trial_state"]["candidate"] == [-1, 2., 30., "stopped"]
    assert state["last_reports"]["candidate"] == [2., 30., "stop"]
    assert state["running_histories"]["candidate"] == {"1.0": -10., "2.0": 30.}
    assert state["terminal"]["candidate"] == "pruned"
    restored = median_target()
    restored.load_state_dict(state)
    restored.finish("candidate", "pruned")
    assert restored.report("candidate", 3., -100., is_progress=True) == "stop"
    assert snapshot(restored) == state


def test_completed_endpoint_only_trials_have_no_imputed_streamed_reference_history():
    target = median_target()
    for i in range(5):
        target.report(str(i), 4., 0.)
        target.finish(str(i), "completed")
    assert snapshot(target)["running_histories"] == {}
    assert target.report("candidate", 1., 100., is_progress=True) == "continue"
    assert snapshot(target)["running_histories"] == {"candidate": {"1.0": 100.}}


@pytest.mark.parametrize("enabled", [False, True])
def test_median_needs_both_enabled_policy_and_an_explicit_grid_point(enabled):
    target = ASHAScheduler(ASHAConfig(r_min=4, r_max=4, median_stopping=enabled,
                                   report_grid=(1., 3., 4.)))
    # The candidate precedes the completed references, so its first point
    # cannot be pruned. Step two is outside the declared decision grid.
    assert target.report("candidate", 1., 10., is_progress=True) == "continue"
    for i in range(5):
        completed_reference(target, str(i), [5., 5., 5., 5.])
    assert target.report("candidate", 2., 100., is_progress=True) == "continue"
    assert target.report("candidate", 3., 100., is_progress=True) == ("stop" if enabled else "continue")
