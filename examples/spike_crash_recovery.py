"""
Crash recovery demonstration: coordinator dies after trial 8, restarts, continues without duplicates.

Survey reference: Ch 15 (store contract), R1 spike charter (deliverable 2).

Exit criterion: no duplicate observations, trials 9-16 continue from checkpoint.
"""

import sys
import time
from pathlib import Path

import numpy as np

from hponas.executors import LocalExecutor
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import SobolSearcher
from hponas.space import Knob, SearchSpace
from hponas.store import Store, Study, Trial


def branin(x: float, y: float) -> float:
    """2D Branin function."""
    a = 1.0
    b = 5.1 / (4 * np.pi**2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8 * np.pi)
    return a * (y - b * x**2 + c * x - r)**2 + s * (1 - t) * np.cos(x) + s


def objective_fn(config: dict) -> float:
    """Evaluate Branin at (x, y) from config."""
    return branin(config["x"], config["y"])


def run_study_with_crash(
    crash_after: int = 8,
    n_trials: int = 16,
    seed: int = 99,
    output_dir: str = "/tmp/hponas_crash",
):
    """
    Run a study that crashes after N trials, then recovers.

    Args:
        crash_after: simulate crash after this many trials
        n_trials: total trials to run
        seed: random seed
        output_dir: directory for store and checkpoints
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    db_path = output_path / "study_crash.db"
    study_id = "branin_crash_recovery"

    print(f"\n{'='*80}")
    print("CRASH RECOVERY TEST")
    print(f"{'='*80}")
    print(f"Plan: run {crash_after} trials, simulate crash, restart, complete {n_trials} total")
    print(f"Store: {db_path}")

    # Check if store exists (restart scenario)
    store_exists = db_path.exists()
    searcher_state_path = output_path / "searcher_state.json"

    if store_exists:
        print("\n🔄 RESTARTING from existing store (crash recovery)")
        store = Store(db_path)
        existing_trials = store.read_trials(study_id)
        n_completed = len(existing_trials)
        print(f"   Found {n_completed} existing trials")

        # Resume from last trial
        start_trial = n_completed
    else:
        print("\n🚀 STARTING fresh study")
        store = Store(db_path)

        # Setup space
        space = SearchSpace()
        space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
        space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))

        # Write study
        store.write_study(Study(
            study_id=study_id,
            space_json=str(space.knobs),
            objective="minimize",
            seed=seed,
            budget=100.0,
        ))

        start_trial = 0
        existing_trials = []

    # Setup components
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))

    searcher = SobolSearcher(space, seed=seed)
    scheduler = ASHAScheduler(ASHAConfig(eta=2, r_min=1.0, r_max=4.0))
    executor = LocalExecutor(checkpoint_dir=output_path / "checkpoints")

    # If restarting, restore searcher state
    if existing_trials:
        if searcher_state_path.exists():
            import json
            with open(searcher_state_path) as f:
                state = json.load(f)
            searcher.load_state_dict(state)
            print(f"   Restored searcher state: {state['n_proposed']} points already proposed")
        else:
            print("   WARNING: no searcher state found, will replay observations (weaker recovery)")

        print(f"   Replaying {len(existing_trials)} trials to scheduler")
        for trial in existing_trials:
            # Note: observe() is no longer used for recovery (state_dict handles it)
            scheduler.report(trial.trial_id, trial.fidelity, trial.value)

    # Run remaining trials
    best_value = float('inf')
    for i in range(start_trial, n_trials):
        trial_id = f"trial_{i}"

        # Propose configuration
        configs = searcher.propose(1)
        config = configs[0]

        # Launch trial
        start = time.time()
        executor.launch(trial_id, config, objective_fn, fidelity=1.0)
        result = executor.get_result(trial_id)
        value = result.get("value", float('inf'))
        cost = time.time() - start

        # Update best
        if value < best_value:
            best_value = value
            print(f"  Trial {i}: value={value:.4f} *** NEW BEST")
        else:
            print(f"  Trial {i}: value={value:.4f}")

        # Record in store
        store.write_trial(
            Trial(
                trial_id=trial_id,
                config=config,
                seed=seed,
                fidelity=1.0,
                value=value,
                cost=cost,
                status="completed",
            ),
            study_id=study_id,
        )

        # Observe (values don't advance Sobol state, but maintained for compatibility)
        searcher.observe({"config": config, "value": value})
        scheduler.report(trial_id, 1.0, value)

        # Persist searcher state after each trial (crash recovery contract)
        import json
        with open(searcher_state_path, "w") as f:
            json.dump(searcher.state_dict(), f, indent=2)

        # Simulate crash after N trials
        if not store_exists and i == crash_after - 1:
            print(f"\n💥 SIMULATING CRASH after trial {i}")
            print(f"   Store has {i+1} trials committed")
            print(f"   Searcher state saved: {searcher_state_path}")
            store.close()
            print("   Restart this script to continue")
            sys.exit(0)

    store.close()

    # Verification
    print(f"\n{'='*80}")
    print("VERIFICATION")
    print(f"{'='*80}")

    store_verify = Store(db_path)
    final_trials = store_verify.read_trials(study_id)
    store_verify.close()

    print(f"Total trials in store: {len(final_trials)}")
    print(f"Expected: {n_trials}")

    # Check for duplicate trial IDs (weak check: IDs are assigned by the loop counter)
    trial_ids = [t.trial_id for t in final_trials]
    id_duplicates = len(trial_ids) - len(set(trial_ids))

    # Check for duplicate CONFIGS (strong check: catches searcher state loss).
    # A searcher rebuilt from its seed restarts the QMC sequence and silently
    # re-proposes pre-crash points; trial IDs stay unique, so only this catches it.
    configs = [tuple(sorted(t.config.items())) for t in final_trials]
    config_duplicates = len(configs) - len(set(configs))

    if id_duplicates > 0:
        print(f"❌ FAILED: {id_duplicates} duplicate trial IDs found")
        return False
    elif len(final_trials) != n_trials:
        print(f"❌ FAILED: expected {n_trials} trials, got {len(final_trials)}")
        return False
    elif config_duplicates > 0:
        print(f"❌ FAILED: {config_duplicates} duplicate configs "
              f"({len(set(configs))} unique in {len(configs)} trials)")
        print("   Cause: searcher state not restored — QMC sequence restarted after crash")
        return False
    else:
        print(f"✅ PASSED: {n_trials} unique trials, {len(set(configs))} unique configs")
        print(f"Best value found: {best_value:.6f}")
        return True


if __name__ == "__main__":
    # Clean start
    import shutil
    crash_dir = Path("/tmp/hponas_crash")
    if crash_dir.exists():
        shutil.rmtree(crash_dir)

    # First run: will crash after trial 8
    try:
        run_study_with_crash(crash_after=8, n_trials=16, seed=99)
    except SystemExit:
        pass

    # Second run: will recover and complete
    success = run_study_with_crash(crash_after=8, n_trials=16, seed=99)

    if success:
        print(f"\n{'='*80}")
        print("CRASH RECOVERY DEMONSTRATION COMPLETE")
        print(f"{'='*80}")
