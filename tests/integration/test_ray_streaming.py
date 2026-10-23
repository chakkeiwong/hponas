"""Live Ray workers must exchange decisions before executing later steps."""

import sys

import pytest

from hponas import IncompleteStudyError, RayExecutor, Study
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import RandomSearcher
from hponas.space import SearchSpace, Knob

ray = pytest.importorskip("ray")
ray.cloudpickle.register_pickle_by_value(sys.modules[__name__])


@pytest.fixture(scope="module")
def cluster():
    ray.init(num_cpus=1, include_dashboard=False)
    yield
    ray.shutdown()


def make_searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0, 1))]), seed=9)


def training(config, fidelity, resume_from, checkpoint, reporter):
    if resume_from:
        assert checkpoint == {"step": resume_from}
    for step in range(int(resume_from) + 1, int(fidelity) + 1):
        reporter(step, 5, cost=step - resume_from, checkpoint={"step": step})
    return {"value": 5, "cost": fidelity - resume_from}


@pytest.mark.parametrize("continuation,cost", [("restart", 6), ("resume", 4)])
def test_ray_study_continuation_and_replay(cluster, tmp_path, continuation, cost):
    # These functional cases have no per-trial latency claim. The enclosing
    # test-process deadline bounds execution; the dedicated timeout case below
    # exercises the executor's real per-trial deadline separately.
    scheduler = ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=2))
    events = EventLog(tmp_path / "events.jsonl")
    study = Study(
        make_searcher(),
        RayExecutor(num_workers=1, max_retries=0),
        training,
        budget=2,
        scheduler=scheduler,
        maximize=False,
        continuation=continuation,
        event_log=events, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    outcome = study.run()
    assert outcome.total_cost == cost and outcome.best_value == 5
    replay = ReplayEngine(make_searcher(), events, 9, ASHAScheduler(scheduler.config))
    passed, message, _, _ = replay.verify_determinism(2)
    assert passed, message
    assert replay.scheduler.state_dict() == scheduler.state_dict()
    assert ray.is_initialized()  # Study does not own this shared cluster.


def test_ray_median_stops_bad_trial_before_tail(cluster, tmp_path):
    marker = tmp_path / "work.txt"

    def objective(config, reporter):
        for step in range(1, 5):
            with marker.open("a") as handle:
                handle.write(str(step))
            reporter(step, 100, cost=step)
        return {"value": 100, "cost": 4}

    scheduler = ASHAScheduler(
        ASHAConfig(r_min=4, r_max=4, median_stopping=True, report_grid=(1, 2, 3, 4))
    )
    for i in range(5):
        for step in range(1, 5):
            scheduler.report(str(i), step, 5, is_progress=True)
        scheduler.finish(str(i), "completed")
    study = Study(
        make_searcher(),
        RayExecutor(num_workers=1, max_retries=0),
        objective,
        budget=1,
        scheduler=scheduler,
        maximize=False, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    assert marker.read_text() == "1"
    assert raised.value.result.history[0].status == "pruned"
    assert raised.value.result.history[0].metadata["attempts"] == 1


def test_ray_streaming_timeout_cancels_worker_and_retains_progress(cluster, tmp_path):
    import time

    marker = tmp_path / "late.txt"

    def objective(config, reporter):
        reporter(1, 1, cost=1)
        time.sleep(5)
        marker.write_text("late work")
        return 1

    # Warm-up above leaves the worker and control actors installed; the deadline
    # still includes actor startup. A timeout cannot produce a successful trial.
    study = Study(
        make_searcher(),
        RayExecutor(num_workers=1, max_retries=0, timeout=3),
        objective,
        budget=1,
        scheduler=ASHAScheduler(ASHAConfig(r_min=4, r_max=4)), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    with pytest.raises(IncompleteStudyError) as raised:
        study.run()
    assert raised.value.result.history[0].status == "timeout"
    assert raised.value.result.total_elapsed_seconds >= 3
    assert not marker.exists()


def test_ray_worker_crash_retries_without_double_counting_reports(cluster, tmp_path):
    import os

    marker = tmp_path / "attempt.txt"

    def objective(config, reporter):
        reporter(1, 5, cost=1)
        if not marker.exists():
            marker.write_text("first attempt reported then died")
            os._exit(31)
        for step in (2, 3, 4):
            reporter(step, 5, cost=step)
        return {"value": 5, "cost": 4}

    scheduler = ASHAScheduler(ASHAConfig(r_min=4, r_max=4))
    study = Study(
        make_searcher(),
        RayExecutor(num_workers=1, max_retries=1),
        objective,
        budget=1,
        scheduler=scheduler, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately',
    )
    result = study.run()
    assert result.history[0].metadata["attempts"] == 2
    assert result.total_cost >= 5
    assert len(next(iter(scheduler._running_histories.values()))) == 4
    events = [e for e in study._events if e["kind"] == "progress"]
    assert len(events) == 5 and events[1]["data"]["scheduler_applied"] is False
