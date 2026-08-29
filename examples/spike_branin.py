"""
Spike example: 2D Branin optimization with Sobol + ASHA on both executors.

Survey reference: Ch 15 (interfaces), R1 spike charter (deliverable 1).

Exit criterion: runs end-to-end on both Ray and local executors, determinism verified.
"""

import time
from pathlib import Path

import numpy as np

from hponas.executors import LocalExecutor, RayExecutor
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import SobolSearcher
from hponas.space import Knob, SearchSpace
from hponas.store import Store, Study, Trial


def branin(x: float, y: float) -> float:
    """
    2D Branin function (standard optimization benchmark).

    Global minimum at (−π, 12.275), (π, 2.275), (9.42478, 2.475) with f = 0.397887.
    Search domain: x ∈ [-5, 10], y ∈ [0, 15].
    """
    a = 1.0
    b = 5.1 / (4 * np.pi**2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8 * np.pi)
    return a * (y - b * x**2 + c * x - r)**2 + s * (1 - t) * np.cos(x) + s


def objective_fn(config: dict) -> float:
    """Objective function: evaluate Branin at (x, y) from config."""
    x = config["x"]
    y = config["y"]
    return branin(x, y)


def run_study(
    executor_name: str,
    seed: int = 42,
    n_trials: int = 16,
    output_dir: str = "/tmp/hponas_spike",
) -> tuple[float, float]:
    """
    Run one Branin study with Sobol searcher + ASHA scheduler.

    Args:
        executor_name: "local" or "ray"
        seed: random seed for reproducibility
        n_trials: number of trials to run
        output_dir: directory for store and checkpoints

    Returns:
        (best_value, total_cost_seconds)
    """
    print(f"\n=== Running study with {executor_name} executor, seed={seed} ===")

    # Setup
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # SearchSpace: 2D Branin
    space = SearchSpace()
    space.add_knob(Knob(name="x", kind="continuous", bounds=(-5.0, 10.0)))
    space.add_knob(Knob(name="y", kind="continuous", bounds=(0.0, 15.0)))

    # Store
    store = Store(output_path / f"study_{executor_name}_{seed}.db")
    study_id = f"branin_{executor_name}_{seed}"
    store.write_study(Study(
        study_id=study_id,
        space_json=str(space.knobs),
        objective="minimize",
        seed=seed,
        budget=100.0,  # dummy budget
    ))

    # Searcher: Sobol
    searcher = SobolSearcher(space, seed=seed)

    # Scheduler: ASHA (simplified for spike: η=2, r_min=1, r_max=4)
    scheduler = ASHAScheduler(ASHAConfig(eta=2, r_min=1.0, r_max=4.0))

    # Executor
    if executor_name == "local":
        executor = LocalExecutor(checkpoint_dir=output_path / "checkpoints_local")
    elif executor_name == "ray":
        executor = RayExecutor(checkpoint_dir=output_path / "checkpoints_ray")
    else:
        raise ValueError(f"Unknown executor: {executor_name}")

    # Run trials
    best_value = float('inf')
    total_cost = 0.0

    for i in range(n_trials):
        trial_id = f"trial_{i}"

        # Propose configuration
        configs = searcher.propose(1)
        config = configs[0]

        # Launch trial at initial fidelity
        fidelity = 1.0
        start = time.time()
        executor.launch(trial_id, config, objective_fn, fidelity)

        # Get result (spike: synchronous for local, poll for ray)
        if executor_name == "local":
            result = executor.get_result(trial_id)
        else:
            result = executor.poll(trial_id)

        value = result.get("value", float('inf'))
        cost = time.time() - start
        total_cost += cost

        # Update best
        if value < best_value:
            best_value = value
            print(f"  Trial {i}: config={config}, value={value:.4f} *** NEW BEST")
        else:
            print(f"  Trial {i}: config={config}, value={value:.4f}")

        # Record in store
        store.write_trial(
            Trial(
                trial_id=trial_id,
                config=config,
                seed=seed,
                fidelity=fidelity,
                value=value,
                cost=cost,
                status="completed",
            ),
            study_id=study_id,
        )

        # Observe (for future GP searcher in Tier 0)
        searcher.observe({"config": config, "value": value})

        # Report to scheduler. The spike runs every trial at a single fidelity, so the
        # decision is recorded but not acted on; Tier 0 wires it to pause and resume.
        scheduler.report(trial_id, fidelity, value)

    store.close()

    print(f"  Best value: {best_value:.6f}")
    print(f"  Total cost: {total_cost:.2f}s")
    print(f"  Trials stored in: {output_path / f'study_{executor_name}_{seed}.db'}")

    return best_value, total_cost


def test_determinism():
    """
    Test that same seed produces same results on both executors (R1 exit criterion).
    """
    print("\n" + "="*80)
    print("DETERMINISM TEST")
    print("="*80)

    seed = 42
    best_local, cost_local = run_study("local", seed=seed, n_trials=8)
    best_ray, cost_ray = run_study("ray", seed=seed, n_trials=8)

    print(f"\nLocal executor: best={best_local:.6f}, cost={cost_local:.2f}s")
    print(f"Ray executor:   best={best_ray:.6f}, cost={cost_ray:.2f}s")

    # Check determinism (values should match exactly for Sobol with same seed)
    if abs(best_local - best_ray) < 1e-6:
        print("\n✅ DETERMINISM TEST PASSED: same seed → same results")
        return True
    else:
        print(f"\n❌ DETERMINISM TEST FAILED: best values differ by {abs(best_local - best_ray)}")
        return False


if __name__ == "__main__":
    # Run on both executors
    run_study("local", seed=42, n_trials=16)
    run_study("ray", seed=42, n_trials=16)

    # Test determinism
    test_determinism()

    print("\n" + "="*80)
    print("Spike example complete. Next: crash recovery demo.")
    print("="*80)
