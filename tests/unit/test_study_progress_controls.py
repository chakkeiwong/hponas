"""Public streaming controls, promotion provenance and recovery diagnostics."""

import json
from types import SimpleNamespace

import pytest

from hponas import IncompleteStudyError, LocalExecutor, RandomSearcher, Study
from hponas.events import EventLog
from hponas.executors import reporting
from hponas.schedulers import ASHAConfig, ASHAScheduler, BudgetedASHAConfig, BudgetedASHAScheduler
from hponas.space import Knob, SearchSpace


def make_study(objective, tmp_path, **kwargs):
    options = dict(searcher=RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=17),
                   executor=LocalExecutor(), objective_fn=objective, budget=1,
                   maximize=False, study_name="progress", checkpoint_dir=tmp_path,
                   event_log=EventLog(tmp_path / "events.jsonl"),
                   scheduler=ASHAScheduler(ASHAConfig(r_min=2, r_max=2)))
    options.update(kwargs)
    return Study(**options)


def events(tmp_path, kind):
    return [row for row in (json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines())
            if row["event_type"] == kind]


def test_conflicting_progress_has_durable_diagnostic_and_preserves_acknowledged_prefix(tmp_path):
    def objective(config, reporter):
        reporter(1, 5, cost=1)
        reporter(1, 7, cost=2)
        pytest.fail("Conflicting progress returned control to the objective")

    study = make_study(objective, tmp_path)
    with pytest.raises(ValueError, match="^Conflicting duplicate progress value$"):
        study.run()
    state = json.loads((tmp_path / "progress_checkpoint.json").read_text())
    assert state["pending"] == ["progress_trial_0"]
    assert state["results"] == {}
    assert state["report_cache"]["progress_trial_0"]["1.0"]["value"] == 5
    assert [row["data"]["value"] for row in events(tmp_path, "progress")] == [5]


def test_compute_cap_retains_exact_control_and_measured_progress_accounting(tmp_path, monkeypatch):
    tick = [0.]
    clock = SimpleNamespace(monotonic=lambda: tick[0])
    monkeypatch.setattr(reporting, "time", clock)

    def objective(config, reporter):
        tick[0] = reporter.started + 2.
        reporter(1, 5, cost=3)
        pytest.fail("Work continued after the compute cap")

    study = make_study(objective, tmp_path, compute_budget_seconds=1., budget=8)
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    result = raised.value.result
    assert result.reason == "compute_budget_exhausted"
    assert result.n_trials == 1 and result.total_cost == 3.
    assert result.total_elapsed_seconds == 2.
    assert result.history[0].status == "cancelled"
    assert result.history[0].metadata["stop_reason"] == "compute_budget_exhausted"
    report, = events(tmp_path, "progress")
    assert report["data"]["control"] == {"action": "cancel", "reason": "compute_budget_exhausted"}
    assert report["data"]["compute_budget_seconds"] == 1.
    assert report["data"]["total_elapsed_seconds"] == 2.
    assert report["data"]["scheduler_applied"] is False


@pytest.mark.parametrize("continuation,expected_cost", [("restart", 14.), ("resume", 8.)])
def test_promoted_reports_distinguish_paid_prefix_from_new_evidence(tmp_path, continuation, expected_cost):
    dispatch = []

    def objective(config, trial_id, root_trial_id, seed, fidelity, resume_from, checkpoint, reporter):
        dispatch.append((trial_id, root_trial_id, seed, fidelity, resume_from, checkpoint))
        if resume_from:
            assert checkpoint == {"step": resume_from}
        for step in range(int(resume_from) + 1, int(fidelity) + 1):
            reporter(step, 5., cost=step - resume_from, checkpoint={"step": step})
        return {"value": 5., "cost": fidelity - resume_from, "checkpoint": {"step": fidelity}}

    study = make_study(objective, tmp_path, budget=2, continuation=continuation,
                       scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=4)))
    outcome = study.run()
    assert outcome.n_trials == 6 and outcome.total_cost == expected_cost
    assert outcome.best_value == 5.
    promotions = events(tmp_path, "promote")
    assert len(promotions) == 4
    assert all(row["trial_id"] == "progress" for row in events(tmp_path, "promotion_round"))
    for row in promotions:
        tid = row["trial_id"]
        root, level = tid.split("_fidelity_")
        level = float(level)
        previous = level / 2
        parent = root if previous == 1 else root + "_fidelity_2"
        assert row["data"] == {
            "root": root, "parent": parent, "config": study.trials[root].config.values,
            "from_fidelity": previous, "to_fidelity": level, "continuation": continuation,
            "resume_from": previous if continuation == "resume" else 0.,
            "checkpoint": {"step": previous} if continuation == "resume" else None,
        }
        trial = study.trials[tid]
        assert trial.parent_trial_id == parent and trial.root_trial_id == root
        assert trial.seed == 17 + int(root.rsplit("_", 1)[-1])
        delivered, = [entry for entry in dispatch if entry[0] == tid]
        assert delivered == (tid, root, trial.seed, level,
                             previous if continuation == "resume" else 0.,
                             {"step": previous} if continuation == "resume" else None)
    repeated = []
    for row in events(tmp_path, "progress"):
        data = row["data"]
        if "_fidelity_" in row["trial_id"]:
            assigned = float(row["trial_id"].rsplit("_", 1)[-1])
            if data["step"] <= assigned / 2:
                repeated.append((row["trial_id"], data["step"]))
                assert continuation == "restart"
                assert data["scheduler_applied"] is False
                assert data["scheduler_decision"] is None
                assert data["control"] == {"action": "continue", "reason": "repeated_work"}
            else:
                assert data["scheduler_applied"] is True
    assert len(repeated) == (6 if continuation == "restart" else 0)


def test_median_pruning_at_assigned_endpoint_prevents_successful_completion(tmp_path):
    tails = []

    def objective(config, trial_id, reporter):
        reporter(1, 5., cost=1)
        reporter(2, 100. if trial_id.endswith("_1") else 5., cost=2)
        tails.append(trial_id)
        return {"value": 100. if trial_id.endswith("_1") else 5., "cost": 2}

    study = make_study(objective, tmp_path, budget=2,
                       scheduler=ASHAScheduler(ASHAConfig(r_min=2, r_max=2,
                           median_stopping=True, median_min_completed=1, report_grid=(1, 2))))
    outcome = study.run()
    assert [row.status for row in outcome.history] == ["completed", "pruned"]
    assert tails == ["progress_trial_0"]
    assert outcome.best_value == 5. and outcome.total_cost == 4.
    final = events(tmp_path, "progress")[-1]["data"]
    assert final["step"] == 2. and final["scheduler_decision"] == "stop"
    assert final["control"] == {"action": "stop", "reason": "scheduler"}
    assert events(tmp_path, "finish")[-1]["data"]["status"] == "pruned"


def test_streaming_legacy_scheduler_uses_its_declared_report_signature(tmp_path):
    def objective(config, reporter):
        reporter(1, 5., cost=1)
        reporter(2, 5., cost=2)
        return {"value": 5., "cost": 2}

    study = make_study(objective, tmp_path,
                       scheduler=BudgetedASHAScheduler(BudgetedASHAConfig(r_min=2, r_max=2)))
    result = study.run()
    assert result.n_trials == 1 and result.best_value == 5. and result.total_cost == 2.
    assert result.history[0].status == "completed"
    assert [row["data"]["scheduler_decision"] for row in events(tmp_path, "progress")] == ["continue", "stop"]


def test_cancelled_paused_root_is_finished_once_before_promotion(tmp_path):
    calls = []

    def objective(config, trial_id):
        calls.append(trial_id)
        if trial_id == "progress_trial_1":
            study.cancel_trial("progress_trial_0")
        return 5.

    study = make_study(objective, tmp_path, budget=2,
                       scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2)))
    try:
        study.run()
    except IncompleteStudyError:
        pass
    assert "progress_trial_0_fidelity_2" not in calls
    request, = events(tmp_path, "cancel_request")
    assert request["trial_id"] == "progress_trial_0"
    assert request["data"] == {"schema_version": 1, "root": "progress_trial_0"}
    finished, = [row for row in events(tmp_path, "finish") if row["trial_id"] == "progress_trial_0"]
    assert finished["data"] == {"schema_version": 1, "root": "progress_trial_0", "status": "cancelled"}
    state = json.loads((tmp_path / "progress_checkpoint.json").read_text())
    assert state["scheduler_state"]["terminal"]["progress_trial_0"] == "cancelled"


def test_duplicate_promotion_does_not_discard_the_remaining_batch(tmp_path):
    class RepeatingScheduler(ASHAScheduler):
        def promote(self):
            chosen = super().promote()
            return [chosen[0], *chosen] if chosen else []

    calls = []

    def objective(config, trial_id):
        calls.append(trial_id)
        return {"value": 5., "cost": 1.}

    study = make_study(objective, tmp_path, budget=2,
                       scheduler=RepeatingScheduler(ASHAConfig(eta=2, r_min=1, r_max=2)))
    result = study.run()
    assert result.n_trials == 4 and result.total_cost == 4.
    assert calls == ["progress_trial_0", "progress_trial_1",
                     "progress_trial_0_fidelity_2", "progress_trial_1_fidelity_2"]
    assert len(events(tmp_path, "promote")) == 2


def test_cancellation_cleanup_visits_every_requested_root(tmp_path):
    study = make_study(lambda config: 5., tmp_path, budget=2)
    study._new_trial()
    study._new_trial()
    study._pending.clear()
    study._cancel_requested.update({"progress_trial_0", "progress_trial_1"})
    study._promotions()
    assert study.scheduler._terminal == {
        "progress_trial_0": "cancelled", "progress_trial_1": "cancelled"
    }
    cancelled = [row["trial_id"] for row in study._events if row["kind"] == "cancel_request"]
    assert cancelled == ["progress_trial_0", "progress_trial_1"]


def test_duplicate_promotion_identity_does_not_drop_later_promotion(tmp_path):
    class DuplicateThenDistinct(ASHAScheduler):
        def __init__(self, config):
            super().__init__(config)
            self.round = 0

        def promote(self):
            self.round += 1
            return ([("progress_trial_0", 2.)] if self.round == 1 else
                    [("progress_trial_0", 2.), ("progress_trial_1", 2.)])

    study = make_study(lambda config: 5., tmp_path, budget=2,
                       scheduler=DuplicateThenDistinct(ASHAConfig(r_min=1, r_max=2)))
    study._new_trial()
    study._new_trial()
    study._pending.clear()
    study._promotions()
    study._promotions()
    assert "progress_trial_0_fidelity_2" in study.trials
    assert "progress_trial_1_fidelity_2" in study.trials
    assert [row["trial_id"] for row in study._events if row["kind"] == "promote"] == [
        "progress_trial_0_fidelity_2", "progress_trial_1_fidelity_2"
    ]
