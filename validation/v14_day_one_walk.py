"""Real, bounded day-one walk using the public Study API and protected evaluation."""

from __future__ import annotations
from functools import partial
from pathlib import Path
import sqlite3
import time

from hponas import Knob, SearchSpace, RandomSearcher, LocalExecutor, Study
from hponas.store import Store
from hponas.events import EventLog
from validation.evidence import digest


def campaign(run_dir, smoke=True):
    from workloads.rl_routine import rl_routine, RLSettings, evaluate_checkpoint

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    space = SearchSpace(
        [
            Knob("learning_rate", "continuous", (1e-5, 1e-2), transform="log"),
            Knob("width", "ordinal", (8, 16)),
            Knob("depth", "ordinal", (1, 2)),
            Knob("activation", "categorical", ["relu", "tanh", "swish"]),
        ]
    )
    # V14 is a 60-second integration demonstration, not a performance campaign.
    settings = RLSettings.smoke()

    def objective(config, seed, trial_id):
        return rl_routine(
            {**config, "num_envs": 32, "batch_size": 64},
            seed=seed,
            settings=settings,
            artifact_dir=run_dir / "policies",
            trial_id=trial_id,
        )

    store = Store(run_dir / "v14_walk.db")
    study = Study(
        RandomSearcher(space, seed=42),
        LocalExecutor(),
        objective,
        budget=1,
        study_name="v14",
        store=store,
        checkpoint_dir=run_dir / "checkpoints",
        event_log=EventLog(run_dir / "events.jsonl"),
    )
    try:
        result = study.run()
        observed = {r.trial_id: r.objective_value for r in study.searcher.history}
        trials = []
        for value in result.history:
            artifacts = value.metadata["artifacts"]
            acceptance = evaluate_checkpoint(artifacts["checkpoint"], 999)
            trials.append(
                {
                    "trial_id": value.trial_id,
                    "training_seed": value.metadata["training_seed"],
                    "search_seed": value.metadata["search_seed"],
                    "search_value": value.objective_value,
                    "observed_value": observed[value.trial_id],
                    "acceptance_value": acceptance["value"],
                    **{
                        k: {"path": artifacts[k], "sha256": digest(artifacts[k])}
                        for k in ("checkpoint", "learning_curve")
                    },
                }
            )
    finally:
        store.close()
    database = run_dir / "v14_walk.db"
    with sqlite3.connect(database) as db:
        seeds = [row[0] for row in db.execute("SELECT seed FROM trials")]
    snapshot = run_dir / "checkpoints/v14_checkpoint.json"
    return {
        "validation_id": "V14",
        "schema_version": 1,
        "workload": "brax_ppo",
        "real_workload": True,
        "duration_seconds": time.monotonic() - started,
        "protected_seed": 999,
        "database_seeds": seeds,
        "database": {"path": str(database), "sha256": digest(database)},
        "study_checkpoint": {"path": str(snapshot), "sha256": digest(snapshot)},
        "trials": trials,
    }


if __name__ == "__main__":
    from validation.run_validation_with_audit import ValidationRunner

    runner = ValidationRunner("V14")
    raise SystemExit(0 if runner.run(lambda: campaign(runner.run_dir)) else 1)
