"""Branin Study, Store and ASHA orchestration on local and optional Ray executors.

Run from the checkout with ``python -m examples.spike_branin --executor local``.
Fidelity does not change this analytic objective; this demonstrates orchestration,
not ASHA efficiency or scientific acceptance. Each invocation retains a new run.
"""

import argparse
import math
from pathlib import Path
import tempfile

from hponas import LocalExecutor, RayExecutor, SobolSearcher, Study
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.space import Knob, SearchSpace
from hponas.store import Store


def branin(x, y):
    return ((y - 5.1 / (4 * math.pi**2) * x**2 + 5 / math.pi * x - 6)**2
            + 10 * (1 - 1 / (8 * math.pi)) * math.cos(x) + 10)


def objective_fn(config):
    return branin(config["x"], config["y"])


def search_space():
    return SearchSpace([Knob("x", "continuous", (-5., 10.)),
                        Knob("y", "continuous", (0., 15.))])


def _run_study(executor_name, seed, n_trials, output_dir):
    if executor_name not in {"local", "ray"}:
        raise ValueError("executor_name must be local or ray")
    if output_dir is not None:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"branin-{executor_name}-", dir=output_dir))
    store = Store(run_dir / "study.db")
    try:
        executor = LocalExecutor() if executor_name == "local" else RayExecutor(num_workers=2)
        study = Study(
            SobolSearcher(search_space(), seed=seed), executor, objective_fn,
            budget=n_trials, maximize=False, study_name="branin", store=store,
            checkpoint_dir=run_dir / "checkpoints", max_concurrent=2,
            scheduler=ASHAScheduler(ASHAConfig(eta=2, r_min=1., r_max=4.)),
        )
        result = study.run()
        trace = [(study.trials[r.trial_id].config.values, r.fidelity, r.objective_value)
                 for r in result.history]
        if not all(r.is_valid() for r in result.history):
            raise RuntimeError("Branin example contains failed evaluations")
    finally:
        store.close()
    print(f"{executor_name}: best={result.best_value:.6f}; "
          f"evaluations={result.n_trials}; artifacts={run_dir}")
    return result, trace


def run_study(executor_name, seed=42, n_trials=16, output_dir=None):
    result, _ = _run_study(executor_name, seed, n_trials, output_dir)
    return result.best_value, result.total_cost


def test_determinism(seed=42, n_trials=8, output_dir=None):
    _, local = _run_study("local", seed, n_trials, output_dir)
    _, ray = _run_study("ray", seed, n_trials, output_dir)
    if local != ray:
        raise AssertionError("Local and Ray proposal/fidelity/value traces differ")
    print("DETERMINISM TEST PASSED: full proposal, fidelity and objective traces agree")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", choices=["local", "ray", "both"], default="both")
    parser.add_argument("--trials", type=int, default=16)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.executor == "both":
        test_determinism(n_trials=args.trials, output_dir=args.output_dir)
    else:
        run_study(args.executor, n_trials=args.trials, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
