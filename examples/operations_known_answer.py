"""Metered known-answer training with Store backup and checkpoint recovery.

The objective is a two-coordinate diagonal quadratic. Every update has an
exact recurrence, and the global ledger admits each stable trial/step identity
before the update. This demonstrates local operational controls; it does not
claim distributed service readiness or optimizer performance.
"""

import argparse
import json
from pathlib import Path
import tempfile

import numpy as np

from hponas import Knob, LocalExecutor, RandomSearcher, SearchSpace, Study
from hponas.operations import (LocalWorkLedger, backup_database, database_inventory,
                               ledger_status, restore_database)
from hponas.store import Store


def run(output_dir=None):
    parent = Path(output_dir) if output_dir is not None else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="operations-known-answer-", dir=parent))
    database = run_dir / "study.db"
    ledger_path = run_dir / "work-ledger.db"
    space = SearchSpace([Knob("eta", "continuous", (0.05, 0.25))])
    searcher = RandomSearcher(space, seed=17)
    traces = []
    with LocalWorkLedger(ledger_path, capacity=12) as ledger:
        def objective(config, trial_id):
            eta = config["eta"]
            state = np.array([1.0, 1.0])
            for step in range(1, 5):
                event = f"{trial_id}/step-{step}"
                if not ledger.charge(event, trial_id):
                    raise RuntimeError("A charged event was redispatched")
                state -= eta * np.array([1.0, 2.0]) * state
                expected = np.array([(1.0 - eta) ** step, (1.0 - 2.0 * eta) ** step])
                np.testing.assert_allclose(state, expected, rtol=2e-13, atol=2e-14)
                ledger.complete(event)
                traces.append({"trial_id": trial_id, "step": step,
                               "eta": eta, "state": state.tolist()})
            return {"value": float(state @ state / 2.0), "cost": 4.0}

        store = Store(database)
        try:
            study = Study(searcher, LocalExecutor(), objective, budget=3, maximize=False,
                          study_name="metered-quadratic", checkpoint_dir=run_dir,
                          store=store, legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
            result = study.run()
            snapshot = store.load_study_snapshot("metered-quadratic")
            before_inventory = database_inventory(database)
            backup = backup_database(database, run_dir / "backup")
        finally:
            store.close()

        restored_database = run_dir / "restored.db"
        restore_database(run_dir / "backup", restored_database)
        restored_store = Store(restored_database)
        try:
            restored_snapshot = restored_store.load_study_snapshot("metered-quadratic")
            resumed = Study(RandomSearcher(space, seed=17), LocalExecutor(), objective,
                            budget=3, maximize=False, study_name="metered-quadratic",
                            store=restored_store, checkpoint_dir=run_dir / "restored-checkpoints", legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
            resumed.load_checkpoint()
            resumed_result = resumed.run()
            if restored_snapshot != snapshot or resumed_result.to_dict() != result.to_dict():
                raise AssertionError("Study checkpoint changed during database restore")
        finally:
            restored_store.close()

        metrics = ledger.metrics()
    summary = {
        "run_dir": str(run_dir),
        "trials": result.n_trials,
        "physical_updates": len(traces),
        "accounted_updates": metrics["completed_units"],
        "ledger": ledger_status(ledger_path),
        "database_inventory": before_inventory,
        "restored_inventory": database_inventory(restored_database),
        "backup_scope": backup["scope"],
        "known_endpoint_optimum_eta": 0.25,
        "best_value": result.best_value,
        "scientific_acceptance": False,
        "distributed_service_acceptance": False,
    }
    if summary["physical_updates"] != summary["accounted_updates"]:
        raise AssertionError("Physical and durable work accounting differ")
    (run_dir / "updates.json").write_text(json.dumps(traces, indent=2) + "\n")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
