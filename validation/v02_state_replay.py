"""Execute V02 replay, process-crash recovery, concurrency and adversarial cases."""

from __future__ import annotations
import json
from pathlib import Path
import time

from hponas import Knob, SearchSpace, GPSearcher, RandomSearcher, Study, LocalExecutor
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.schedulers import ASHAConfig, ASHAScheduler


def _space():
    return SearchSpace([Knob("x", "continuous", (0.0, 1.0))])


def _objective(config, seed=0, fidelity=1.0):
    return -((config["x"] - 0.4) ** 2)


def _case(name, expected, actual):
    return {"name": name, "expected": expected, "actual": actual}


def _replay_run(
    directory,
    name,
    seed,
    count,
    searcher_factory,
    scheduler=None,
    executor=None,
    width=1,
):
    event_log = EventLog(directory / f"{name}.jsonl")
    searcher = searcher_factory(_space(), seed=seed)
    study = Study(
        searcher,
        executor or LocalExecutor(),
        _objective,
        budget=count,
        study_name=name,
        event_log=event_log,
        scheduler=scheduler,
        max_concurrent=width,
    )
    study.run()
    restored_scheduler = ASHAScheduler(ASHAConfig()) if scheduler else None
    if restored_scheduler:
        restored_scheduler = ASHAScheduler(scheduler.config)
    engine = ReplayEngine(
        searcher_factory(_space(), seed=seed),
        event_log,
        seed,
        scheduler=restored_scheduler,
    )
    passed, message, original, replayed = engine.verify_determinism(count)
    cases = [
        _case("configs", original, replayed),
        _case(message, True, passed),
        _case("searcher_state", searcher.get_state(), engine.searcher.get_state()),
    ]
    if scheduler:
        cases.append(
            _case(
                "scheduler_state",
                scheduler.state_dict(),
                restored_scheduler.state_dict(),
            )
        )
    from validation.evidence import digest

    return {
        "id": name,
        "n_trials": count,
        "seed": seed,
        "workers": width,
        "cases": cases,
        "event_log": {
            "path": str(event_log.log_path.resolve()),
            "sha256": digest(event_log.log_path),
        },
        "scheduler_config": scheduler.state_dict()["config"] if scheduler else None,
    }


def campaign(run_dir):
    from validation.v02_contract import prepare_contract, freeze_contract, execute_population

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    contract = prepare_contract()
    contract_ref = freeze_contract(run_dir, contract)
    scenarios = [
        _replay_run(run_dir, "gp_replay", 42, 20, GPSearcher),
        _replay_run(
            run_dir,
            "asha_replay",
            43,
            30,
            RandomSearcher,
            ASHAScheduler(ASHAConfig(eta=3, r_min=1, r_max=9)),
        ),
    ]
    from validation.v02_fault_execution import execute_crash, execute_concurrency

    scenarios.append(execute_crash(run_dir))
    scenarios.append(execute_concurrency(run_dir))
    # Arrival order differs; Study commits observations in dispatch order.
    runs = []
    for reverse in (False, True):

        def delayed(config, trial_id):
            index = int(trial_id.rsplit("_", 1)[1]) % 4
            time.sleep((3 - index if reverse else index) * 0.002)
            return _objective(config)

        study = Study(
            RandomSearcher(_space(), seed=45),
            LocalExecutor(mode="async", max_workers=4),
            delayed,
            budget=20,
            study_name="order",
        )
        study.run()
        runs.append(
            [
                [t.config.values for t in study.trials.values()],
                [r.objective_value for r in study.results.values()],
            ]
        )
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=9))
    scheduler.report("a", 1, 0.2)
    scheduler.report("a", 1, 0.2)
    scheduler.report("b", 1, 0.3)
    promotions = scheduler.promote()
    scheduler.report("a", 1, 0.2)
    scenarios.append(
        {
            "id": "adversarial_events",
            "cases": [
                _case("arrival_order", runs[0], runs[1]),
                _case("unique_rung_population", 2, len(scheduler._rung_populations[0])),
                _case("single_promotion", [("a", 3)], promotions),
                _case("stale_report_no_repromotion", [], scheduler.promote()),
            ],
        }
    )
    empty = ReplayEngine(
        RandomSearcher(_space(), seed=46), EventLog(run_dir / "empty.jsonl"), 46
    ).verify_determinism(1)[0]
    scenarios.append(
        {"id": "non_vacuity", "cases": [_case("empty_log_rejected", False, empty)]}
    )
    scenarios.append(streamed_replay(run_dir))
    scenarios.append(cancelled_replay(run_dir))
    # Normalize tuple/list representations before persisting expected/actual fields.
    return json.loads(
        json.dumps(
            {"validation_id": "V02", "schema_version": 1, "scenarios": scenarios,
             "evidence_kind": "bound_candidate_event_grammar", "certifies_acceptance": False,
             "run_dir": str(run_dir.resolve()), "input_contract": contract_ref,
             "event_population": execute_population(contract)}
        )
    )


def streamed_replay(directory):
    """Real Study log spanning streamed reports, resume, promotion and completion."""
    from validation.evidence import digest

    directory = Path(directory)
    log = EventLog(directory / "streamed_replay.jsonl")
    config = ASHAConfig(eta=2, r_min=1, r_max=4)

    def stream(config, fidelity, reporter, resume_from, checkpoint):
        for step in range(int(resume_from) + 1, int(fidelity) + 1):
            reporter(step, 5, cost=step - resume_from, checkpoint={"step": step})
        return {"value": 5, "cost": fidelity - resume_from, "checkpoint": {"step": fidelity}}

    study = Study(RandomSearcher(_space(), seed=47), LocalExecutor(), stream,
                  budget=2, maximize=False, scheduler=ASHAScheduler(config),
                  continuation="resume", event_log=log, study_name="streamed")
    result = study.run()
    replay = ReplayEngine(RandomSearcher(_space(), seed=47), log, 47, ASHAScheduler(config))
    passed, message, _, _ = replay.verify_determinism(2)
    return {"id": "streamed_replay", "n_trials": 2, "seed": 47,
            "scheduler_config": study.scheduler.state_dict()["config"],
            "event_log": {"path": str(log.log_path.resolve()), "sha256": digest(log.log_path)},
            "cases": [_case(message, True, passed), _case("resumed_compute", 8.0, result.total_cost),
                      _case("scheduler_state", study.scheduler.state_dict(), replay.scheduler.state_dict()),
                      _case("terminal_roots", 2, len(study.scheduler._terminal))]}


def cancelled_replay(directory):
    from hponas import IncompleteStudyError
    from validation.evidence import digest

    log = EventLog(Path(directory) / "cancelled_replay.jsonl")
    config = ASHAConfig(r_min=4, r_max=4)
    tail = []

    def objective(config, trial_id, reporter):
        reporter(1, 5, cost=1)
        study.cancel_trial(trial_id)
        reporter(2, 5, cost=2)
        tail.append("tail executed after cancellation")

    study = Study(RandomSearcher(_space(), seed=48), LocalExecutor(), objective, budget=1,
                  scheduler=ASHAScheduler(config), event_log=log, study_name="cancelled")
    try:
        study.run()
        outcome = "unexpected_success"
    except IncompleteStudyError as exc:
        outcome = exc.result.history[0].status
    replay = ReplayEngine(RandomSearcher(_space(), seed=48), log, 48, ASHAScheduler(config))
    passed, message, _, _ = replay.verify_determinism(1)
    return {"id": "cancelled_replay", "n_trials": 1, "seed": 48,
            "scheduler_config": study.scheduler.state_dict()["config"],
            "event_log": {"path": str(log.log_path.resolve()), "sha256": digest(log.log_path)},
            "cases": [_case("cancelled outcome", "cancelled", outcome), _case("interrupted tail", [], tail),
                      _case(message, True, passed),
                      _case("scheduler_state", study.scheduler.state_dict(), replay.scheduler.state_dict())]}


if __name__ == "__main__":
    from validation.run_validation_with_audit import ValidationRunner

    runner = ValidationRunner("V02")
    raise SystemExit(0 if runner.run(lambda: campaign(runner.run_dir)) else 1)
