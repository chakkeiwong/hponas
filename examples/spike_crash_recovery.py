"""Interrupt a Study and restore its committed ledger and pending Sobol proposal.

This is a deterministic driver-interruption demonstration, not a kill-9 test.
The Store conformance suite separately tests process termination. No existing
folder is deleted; each demonstration retains its own artifacts.
"""

import argparse
import json
from pathlib import Path
import tempfile

from hponas import Knob, LocalExecutor, SearchSpace, SobolSearcher, Study
from hponas.store import Store


class SimulatedCrash(KeyboardInterrupt):
    """Interrupt the driver after earlier results have been committed."""


def objective_fn(config):
    return (config["x"] - .25)**2 + (config["y"] - .75)**2


def _space():
    return SearchSpace([Knob("x", "continuous", (0., 1.)),
                        Knob("y", "continuous", (0., 1.))])


def run_study_with_crash(crash_after=8, n_trials=16, seed=99, output_dir=None):
    if not 0 < crash_after < n_trials:
        raise ValueError("crash_after must be between zero and n_trials")
    if output_dir is None:
        raise ValueError("Provide the same output_dir to interrupt and resume")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    store = Store(directory / "study.db")
    try:
        snapshot = store.load_study_snapshot("recovery")
        calls = 0

        def interruptible(config):
            nonlocal calls
            calls += 1
            if snapshot is None and calls == crash_after + 1:
                raise SimulatedCrash("committed checkpoint retained")
            return objective_fn(config)

        study = Study(SobolSearcher(_space(), seed=seed), LocalExecutor(), interruptible,
                      budget=n_trials, maximize=False, study_name="recovery",
                      store=store, checkpoint_dir=directory / "checkpoints")
        if snapshot is not None:
            study.load_checkpoint()
            if study.budget != n_trials or study.searcher.seed != seed:
                raise ValueError("Resume budget/seed differs from the saved study")
        result = study.run()
        trace = [(study.trials[r.trial_id].config.values, r.objective_value)
                 for r in result.history]
        if len(store.read_trials("recovery")) != n_trials:
            raise AssertionError("Stored evaluation count differs from the budget")
        return result, trace
    finally:
        store.close()


def run_demo(output_dir=None, crash_after=8, n_trials=16, seed=99):
    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="hponas-recovery-", dir=output_dir))
    resumed_dir = directory / "resumed"
    try:
        run_study_with_crash(crash_after, n_trials, seed, resumed_dir)
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("Interruption was not exercised")
    store = Store(resumed_dir / "study.db")
    try:
        committed = store.load_study_snapshot("recovery")["results"]
    finally:
        store.close()
    if len(committed) != crash_after:
        raise AssertionError("Unexpected committed prefix at interruption")
    result, resumed = run_study_with_crash(crash_after, n_trials, seed, resumed_dir)
    reference = Study(SobolSearcher(_space(), seed=seed), LocalExecutor(), objective_fn,
                      budget=n_trials, maximize=False, study_name="reference")
    baseline = reference.run()
    expected = [(reference.trials[r.trial_id].config.values, r.objective_value)
                for r in baseline.history]
    if resumed != expected:
        raise AssertionError("Resumed proposals/results differ from uninterrupted run")
    actual = {r.trial_id: r.to_dict() for r in result.history}
    if any(actual[key] != value for key, value in committed.items()):
        raise AssertionError("Previously committed results changed during recovery")
    if len({tuple(sorted(config.items())) for config, _ in resumed}) != n_trials:
        raise AssertionError("Recovered Sobol stream contains duplicate configurations")
    receipt = {"kind": "interruption_demo", "scientific_acceptance": False,
               "trials": n_trials, "committed_preserved": len(committed),
               "exact_reference_trace": True, "artifact_dir": str(directory)}
    (directory / "recovery-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PASSED: {n_trials} unique trials; committed prefix preserved; artifacts={directory}")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    run_demo(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
