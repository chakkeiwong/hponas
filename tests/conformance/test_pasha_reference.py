"""Full promotion/reference sequences beyond the isolated soft-ranking rule."""

import json

import numpy as np
import pytest

from hponas.schedulers import PASHAConfig, PASHAScheduler
from validation.reference_checks import pasha_reference


@pytest.fixture(scope="module")
def vendor():
    return pasha_reference()


def reference(vendor):
    return vendor["PASHARungSystem"]([1, 3, 9], [1/3] * 3, "loss", "min", "step", 27)


def drain(scheduler):
    result = []
    while promoted := scheduler.promote():
        assert len(promoted) == 1
        assert promoted[0] not in result, 'Scheduler repeated an already emitted promotion'
        result.extend(promoted)
    return result


def ref_drain(ref):
    result = []
    while promoted := ref.on_task_schedule("unused"):
        result.append((promoted["trial_id"], promoted["milestone"]))
    return result


def report_first(ref, ours, tid, value):
    ref.on_task_add(tid, 0)
    ref.on_task_report(tid, {"loss": value, "step": 1}, 0)
    ref.on_task_remove(tid)
    ours.report(tid, 1, value)


@pytest.mark.parametrize("values", [[], [0], [0, 1], [0, 1, 2], [0, 1, 2, 3],
                                    list(range(7)), [1] * 7, [1, 0, 1, 0, 1],
                                    [-1e308, 1e308], [-1e308, -1e308, 1e308, 1e308]])
def test_full_published_pasha_small_populations_and_ties(vendor, values):
    ref, ours = reference(vendor), PASHAScheduler(PASHAConfig())
    for index, value in enumerate(values):
        report_first(ref, ours, str(index), value)
    assert drain(ours) == ref_drain(ref)
    assert drain(ours) == []


def test_late_eligibility_and_checkpoint_preserve_promoted_population(vendor):
    ref, ours = reference(vendor), PASHAScheduler(PASHAConfig())
    for index in range(4):
        report_first(ref, ours, str(index), index)
    assert drain(ours) == ref_drain(ref) == [("0", 3), ("1", 3)]
    assert ours._trial_state["2"][-1] == "paused"
    restored = PASHAScheduler(PASHAConfig())
    restored.load_state_dict(json.loads(json.dumps(ours.state_dict())))
    for index in range(4, 7):
        report_first(ref, ours, str(index), 100 + index)
        restored.report(str(index), 1, 100 + index)
    assert drain(ours) == drain(restored) == ref_drain(ref) == [("2", 3)]
    assert ours.state_dict() == restored.state_dict()
    assert len(ours._rung_populations[0]) == 7


def test_highest_rung_and_separate_incremental_cap(vendor):
    ref = reference(vendor)
    ref.current_max_t = 9
    ours = PASHAScheduler(PASHAConfig(promotion_budget=8))
    ours._current_top = 2
    # Isolate dispatch order at a fixed legal cap/population. The independent
    # lifecycle tests below reach such states using actual promotions.
    for rung_index, step in enumerate((1, 3)):
        for index in range(4):
            tid = f"{step}-{index}"
            ours.report(tid, step, index)
            ref._rungs[-1-rung_index].add(vendor["PromotionRungEntry"](tid, index))
    assert ours.promote() == [("3-0", 9)] == ref_drain(ref)[:1]
    # Only two budget units remain: an additional six-unit promotion cannot
    # fit, but a two-unit lower-rung promotion can. No ineligible trial dies.
    assert ours.promote() == [("1-0", 3)]
    assert ours._budget_spent == 8
    assert ours._trial_state["3-1"][-1] == "paused"
    assert ours._trial_state["3-0"][3] == 6
    before = ours.state_dict()
    assert ours.promote() == []
    assert ours.state_dict() == before


def test_duplicate_reports_cannot_rewrite_ranking_or_spend_twice():
    ours = PASHAScheduler(PASHAConfig())
    for tid in ("a", "b"):
        ours.report(tid, 1, 0)
    before = ours.state_dict()
    assert ours.report("a", 1, 0) == "pause"
    assert ours.report("a", 2, 0) == "pause"
    with pytest.raises(ValueError, match="Conflicting"):
        ours.report("a", 1, 1)
    assert ours.state_dict() == before
    assert ours.promote() == [("a", 3)]
    assert ours.report("a", 1, 0) == "continue"
    assert ours.report("a", 2, 0) == "continue"
    assert ours.report("a", 3, 0) == "pause"
    assert ours.promote() == [("b", 3)]
    assert ours.promote() == []
    assert ours._budget_spent == 4


def full_trace(actor, table, *, is_reference, recover=False):
    rows, next_trial, last_steps = [], 0, {}
    dispatched = set()
    while True:
        if is_reference:
            promotion = actor.on_task_schedule("unused")
            dispatch = (promotion["trial_id"], promotion["milestone"]) if promotion else None
        else:
            promoted = actor.promote()
            dispatch = promoted[0] if promoted else None
        if dispatch:
            tid, target = dispatch
            assert (tid, target) not in dispatched, 'Scheduler repeated a trial at the same rung'
            dispatched.add((tid, target))
            start = promotion["resume_from"] if is_reference else last_steps[tid]
            rows.append(("promotion", tid, target))
            if is_reference:
                actor.on_task_add(tid, 0, new_config=False, milestone=target, resume_from=start)
        elif next_trial < len(table):
            tid, start, target = str(next_trial), 0, 1
            next_trial += 1
            if is_reference:
                actor.on_task_add(tid, 0)
        else:
            return rows
        for step in range(int(start) + 1, int(target) + 1):
            value = float(table[int(tid), step-1])
            if is_reference:
                decision = actor.on_task_report(tid, {"step": step, "loss": value}, 0)
                decision = ("continue" if decision["task_continues"] else
                            "stop" if step == 27 else "pause")
                cap, epsilon = actor.current_max_t, actor.epsilon
            else:
                decision = actor.report(tid, step, value)
                cap, epsilon = actor.current_max_fidelity, actor._epsilon
                if recover:
                    restored = PASHAScheduler(PASHAConfig())
                    restored.load_state_dict(json.loads(json.dumps(actor.state_dict())))
                    actor = restored
            rows.append(("report", tid, step, value, decision, cap, epsilon))
        last_steps[tid] = target
        if is_reference:
            actor.on_task_remove(tid)


@pytest.mark.parametrize("seed", range(6))
def test_independent_dense_lifecycles_and_recovery_match_pinned_pasha(vendor, seed):
    table = np.random.RandomState(seed).normal(size=(40, 27))
    expected = full_trace(reference(vendor), table, is_reference=True)
    canonical = full_trace(reference(pasha_reference(canonical_pairs=True)), table, is_reference=True)
    actual = full_trace(PASHAScheduler(PASHAConfig()), table, is_reference=False)
    restored = full_trace(PASHAScheduler(PASHAConfig()), table, is_reference=False, recover=True)
    # The upstream ordered-pair/set-iteration bug can change epsilon. Do not
    # mislabel the canonical interpretation as verbatim vendor equivalence.
    decisions = lambda rows: [row[:-1] if row[0] == "report" else row for row in rows]
    assert decisions(actual) == decisions(expected)
    assert actual == canonical
    assert restored == canonical


def test_pinned_tolerance_depends_on_pair_iteration_order(vendor):
    outcomes = {"a": {1: 0, 2: 0, 3: 2, 4: 0, 5: 0},
                "b": {1: 1, 2: 1, 3: 0, 4: 2, 5: 10},
                "c": {1: 100, 2: 100, 3: 100, 4: 100}}
    epsilons = []
    for order in (["a", "b", "c"], ["b", "a", "c"]):
        ref = reference(vendor)
        ref.current_rung_idx, ref.current_max_t, ref.current_max_epoch = 3, 9, 5
        ref.per_epoch_results = outcomes
        # Only iteration is used by this exact upstream method. These two
        # iterable orders represent the same observed trial set at epoch 4.
        ref.epoch_to_trials = {4: order, 5: ["a", "b"]}
        ref._update_epsilon()
        epsilons.append(ref.epsilon)
    assert epsilons == [10, 9.2]
    ours = PASHAScheduler(PASHAConfig())
    ours._current_top, ours._resource_reports = 2, outcomes
    ours._update_epsilon()
    assert ours._epsilon == 10


@pytest.mark.parametrize("top_order,expected_cap", [(["z", "y"], 3), (["y", "z"], 9)])
def test_tied_survivor_scores_preserve_actual_arrival_order(vendor, top_order, expected_cap):
    ref = reference(vendor)
    ours = PASHAScheduler(PASHAConfig(ranking_epsilon=0))
    for tid, value in (("z", 0), ("y", 1), ("x", 2), ("w", 3)):
        report_first(ref, ours, tid, value)
    assert drain(ours) == ref_drain(ref) == [("z", 3), ("y", 3)]
    for tid in top_order:
        ref.on_task_add(tid, 0, new_config=False, resume_from=1, milestone=3)
        for step in (2, 3):
            ref.on_task_report(tid, {"step": step, "loss": 0}, 0)
            ours.report(tid, step, 0)
        ref.on_task_remove(tid)
    assert ours.current_max_fidelity == ref.current_max_t == expected_cap
