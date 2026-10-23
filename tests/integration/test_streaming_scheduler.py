"""Observable interruption, continuation, accounting and recovery across workers."""

import json
import time

import pytest

from hponas import IncompleteStudyError, LocalExecutor, Study
from hponas.events import EventLog
from hponas.executors.reporting import ReportDecision
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import RandomSearcher
from hponas.space import Knob, SearchSpace
from hponas.store import Store
from hponas.types import Config, Trial


def searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0, 1))]), seed=17)


def scheduler(**kwargs):
    return ASHAScheduler(ASHAConfig(**{"r_min": 4, "r_max": 4, **kwargs}))


def stream(config, fidelity, reporter, resume_from, checkpoint):
    if resume_from:
        assert checkpoint["step"] == resume_from
    for step in range(int(resume_from) + 1, int(fidelity) + 1):
        reporter(step, 5, cost=step - resume_from, checkpoint={"step": step})
    return {
        "value": 5,
        "cost": fidelity - resume_from,
        "checkpoint": {"step": fidelity},
    }


@pytest.mark.parametrize(
    "mode,timeout", [("sync", None), ("async", None), ("sync", 20)]
)
def test_local_report_decision_interrupts_before_expensive_work(
    tmp_path, mode, timeout
):
    path = tmp_path / "work.txt"

    def objective(config, reporter):
        for step in range(1, 5):
            with path.open("a") as handle:
                handle.write(str(step))
            reporter(step, 10, cost=step)
        raise AssertionError("Expensive tail ran after pruning")

    seen = []

    def report(progress):
        seen.append(progress.step)
        return ReportDecision("stop" if progress.step == 2 else "continue")

    trial = Trial(Config({}), "root", fidelity=4)
    executor = LocalExecutor(mode=mode, timeout=timeout)
    try:
        if mode == "async":
            result = executor.execute_async(trial, objective, on_report=report).result()
        else:
            result = executor.execute(trial, objective, on_report=report)
    finally:
        executor.shutdown()
    assert result.status == "pruned" and not result.is_valid()
    assert result.cost == 2
    assert seen == [1, 2] and path.read_text() == "12"


@pytest.mark.parametrize("continuation,expected_cost", [("resume", 8), ("restart", 14)])
def test_promotions_carry_state_and_charge_repeated_work(
    tmp_path, continuation, expected_cost
):
    log = EventLog(tmp_path / "events.jsonl")
    study = Study(
        searcher(),
        LocalExecutor(),
        stream,
        budget=2,
        maximize=False,
        scheduler=scheduler(eta=2, r_min=1),
        continuation=continuation,
        event_log=log,
        checkpoint_dir=tmp_path,
        study_name="continuation", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    result = study.run()
    assert result.total_cost == expected_cost and result.n_trials == 6
    assert result.best_value == 5 and result.status == "completed"
    for trial in study.trials.values():
        assert trial.root_trial_id == study._roots[trial.trial_id]
        if trial.parent_trial_id and continuation == "resume":
            assert trial.resume_from == study.trials[trial.parent_trial_id].fidelity
            assert trial.checkpoint == {"step": trial.resume_from}
    assert len(study.scheduler._terminal) == 2
    assert all(status == "completed" for status in study.scheduler._terminal.values())
    replay = ReplayEngine(searcher(), log, 17, scheduler=scheduler(eta=2, r_min=1))
    passed, message, _, _ = replay.verify_determinism(2)
    assert passed, message
    assert replay.scheduler.state_dict() == study.scheduler.state_dict()


def test_no_full_fidelity_incumbent_is_durable_incomplete(tmp_path):
    store = Store(tmp_path / "ledger.db")
    try:
        study = Study(
            searcher(),
            LocalExecutor(),
            lambda c: {"value": 1, "cost": 2},
            budget=1,
            maximize=False,
            scheduler=scheduler(r_min=1),
            checkpoint_dir=tmp_path,
            store=store,
            study_name="underfilled", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        with pytest.raises(IncompleteStudyError) as raised:
            study.run()
        outcome = raised.value.result
        assert outcome.best_config is None and outcome.best_value is None
        assert outcome.reason == "no_full_fidelity_result" and outcome.total_cost == 2
        assert study.get_best_so_far() is None
        assert store.read_study("underfilled").status == "incomplete"
        checkpoint = tmp_path / "underfilled_checkpoint.json"
        assert json.loads(checkpoint.read_text())["outcome"] == "incomplete"
        restored = Study(
            searcher(),
            LocalExecutor(),
            lambda c: pytest.fail("repeated committed work"),
            scheduler=scheduler(r_min=1), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        restored.load_checkpoint(checkpoint)
        with pytest.raises(IncompleteStudyError):
            restored.run()
    finally:
        store.close()


def test_completed_references_prune_a_live_trial_and_endpoint_only_is_explicit(
    tmp_path,
):
    calls = []

    def objective(config, fidelity, trial_id, reporter):
        value = 100 if trial_id.endswith("_5") else 5
        for step in range(1, int(fidelity) + 1):
            calls.append((trial_id, step))
            reporter(step, value, cost=step)
        return {"value": value, "cost": fidelity}

    log = EventLog(tmp_path / "median.jsonl")
    target = scheduler(median_stopping=True, report_grid=(1, 2, 3, 4))
    study = Study(
        searcher(),
        LocalExecutor(),
        objective,
        budget=6,
        maximize=False,
        scheduler=target,
        study_name="median",
        event_log=log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    outcome = study.run()
    assert [r.status for r in outcome.history] == ["completed"] * 5 + ["pruned"]
    assert [s for tid, s in calls if tid.endswith("_5")] == [1]
    replay = ReplayEngine(
        searcher(),
        log,
        17,
        scheduler=scheduler(median_stopping=True, report_grid=(1, 2, 3, 4)),
    )
    passed, message, _, _ = replay.verify_determinism(6)
    assert passed, message
    assert replay.scheduler.state_dict() == target.state_dict()
    endpoint = Study(
        searcher(),
        LocalExecutor(),
        lambda c: 100,
        budget=6,
        scheduler=scheduler(median_stopping=True, report_grid=(1, 2, 3, 4)), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    result = endpoint.run()
    assert all(
        r.status == "completed" and r.metadata["execution"]["mode"] == "endpoint"
        for r in result.history
    )
    assert endpoint.scheduler._running_histories == {}


def test_async_reports_commit_on_study_thread_with_sqlite(tmp_path):
    store = Store(tmp_path / "async.db")
    try:
        study = Study(
            searcher(),
            LocalExecutor(mode="async", max_workers=2),
            stream,
            budget=4,
            scheduler=scheduler(),
            store=store,
            study_name="async", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
        )
        result = study.run()
        assert result.n_trials == 4
        assert len([e for e in study._events if e["kind"] == "progress"]) == 16
        assert store.load_study_snapshot("async")["outcome"] == "completed"
    finally:
        store.close()


def test_crash_recovery_deduplicates_evidence_and_charges_restarted_prefix(tmp_path):
    def interrupted(config, reporter):
        reporter(1, 5, cost=1)
        raise KeyboardInterrupt("crash after durable progress")

    log = EventLog(tmp_path / "crash.jsonl")
    study = Study(
        searcher(),
        LocalExecutor(),
        interrupted,
        budget=1,
        scheduler=scheduler(),
        checkpoint_dir=tmp_path,
        study_name="crash",
        event_log=log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    with pytest.raises(KeyboardInterrupt):
        study.run()
    restored = Study(
        searcher(), LocalExecutor(), stream, scheduler=scheduler(), event_log=log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately'
    )
    restored.load_checkpoint(tmp_path / "crash_checkpoint.json")
    outcome = restored.run()
    assert outcome.total_cost == 5  # One abandoned step plus the restarted four.
    assert len(restored.scheduler._running_histories["crash_trial_0"]) == 4
    reports = [e for e in restored._events if e["kind"] == "progress"]
    assert len(reports) == 5 and reports[1]["data"]["scheduler_applied"] is False
    replay = ReplayEngine(searcher(), log, 17, scheduler=scheduler())
    assert replay.verify_determinism(1)[0]


def test_compute_cap_is_separate_from_configuration_budget():
    calls = []

    def objective(config, fidelity, reporter):
        for step in range(1, int(fidelity) + 1):
            time.sleep(0.005)
            calls.append(step)
            reporter(step, 1, cost=step)
        return {"value": 1, "cost": fidelity}

    study = Study(
        searcher(),
        LocalExecutor(),
        objective,
        budget=10,
        scheduler=scheduler(r_min=100, r_max=100),
        compute_budget_seconds=0.03, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    assert raised.value.result.reason == "compute_budget_exhausted"
    assert raised.value.result.total_elapsed_seconds >= 0.03
    assert study._n_suggested == 1 and 1 <= len(calls) < 100
    assert raised.value.result.history[0].status == "cancelled"


def test_user_cancellation_is_terminal_and_distinct_from_failure():
    calls = []

    def objective(config, trial_id, reporter):
        reporter(1, 5, cost=1)
        study.cancel_trial(trial_id)
        reporter(2, 5, cost=2)
        calls.append("should not execute")

    study = Study(
        searcher(), LocalExecutor(), objective, budget=1, scheduler=scheduler(), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately'
    )
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    assert calls == [] and raised.value.result.history[0].status == "cancelled"
    assert list(study.scheduler._terminal.values()) == ["cancelled"]


def test_scheduler_policy_rejection_does_not_mutate_live_study(tmp_path):
    source = Study(
        searcher(),
        LocalExecutor(),
        stream,
        scheduler=scheduler(promotion_policy="legacy_bootstrap"),
        checkpoint_dir=tmp_path,
        study_name="legacy", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    source._new_trial()
    source.save_checkpoint()
    target = Study(searcher(), LocalExecutor(), stream, scheduler=scheduler(), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    before = json.loads(json.dumps(target._snapshot()))
    with pytest.raises(ValueError, match="policy differs"):
        target.load_checkpoint(tmp_path / "legacy_checkpoint.json")
    assert json.loads(json.dumps(target._snapshot())) == before
