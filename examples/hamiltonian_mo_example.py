"""
Example: Multi-objective Hamiltonian network tuning with HPO-NAS.

This example demonstrates:
1. Multi-objective optimization (prediction error vs drift)
2. qLogNEHVI acquisition for MO
3. MO-ASHA scheduler with early stopping
4. Hypervolume-based front reporting

Survey reference: Ch 7 (MO methods), Ch 10 (Hamiltonian regime).
Validation: V09 (qLogNEHVI vs scalarization).
"""

from __future__ import annotations

from hponas import SearchSpace, FloatKnob, IntKnob, CategoricalKnob
from hponas import Store, Study
from hponas import qLogNEHVISearcher
from hponas import MOASHAScheduler
from hponas.reporting_mo import compute_hypervolume

from workloads.hamiltonian_mo import hamiltonian_mo


def main():
    # Define search space
    space = SearchSpace(
        knobs=[
            FloatKnob("learning_rate", 1e-5, 1e-2, log_scale=True),
            IntKnob("batch_size", 16, 256),
            CategoricalKnob("hidden_sizes", [[32, 32], [64, 64], [64, 64, 64]]),
            CategoricalKnob("activation", ["tanh", "relu", "elu"]),
            FloatKnob("weight_decay", 1e-6, 1e-2, log_scale=True),
            CategoricalKnob("optimizer", ["adam", "sgd", "rmsprop"]),
        ]
    )

    # Create store and study
    store = Store(":memory:")
    study = store.create_study(
        name="hamiltonian_tuning",
        space=space,
        objectives=["prediction_error", "drift"],
        directions=["minimize", "minimize"],
    )

    # Create searcher and scheduler
    searcher = qLogNEHVISearcher(
        space=space,
        objectives=["prediction_error", "drift"],
        seed=42,
    )

    scheduler = MOASHAScheduler(
        min_fidelity=0.1,
        max_fidelity=1.0,
        reduction_factor=3,
        grace_period=1,
    )

    # Budget
    max_trials = 30
    n_completed = 0

    print("=" * 60)
    print("Hamiltonian MO Tuning Example")
    print("=" * 60)
    print(f"Objectives: prediction_error (min), drift (min)")
    print(f"Budget: {max_trials} trials")
    print(f"Searcher: qLogNEHVI")
    print(f"Scheduler: MO-ASHA (reduction_factor=3)")
    print("=" * 60)

    # Main loop
    while n_completed < max_trials:
        # Propose configuration
        config = searcher.propose()
        trial_id = f"trial_{n_completed:03d}"

        print(f"\n[{n_completed+1}/{max_trials}] Trial {trial_id}")
        print(f"  Config: lr={config['learning_rate']:.2e}, "
              f"batch={config['batch_size']}, "
              f"hidden={config['hidden_sizes']}, "
              f"act={config['activation']}")

        # Ask scheduler for fidelity
        fidelity = scheduler.suggest(trial_id)

        while True:
            print(f"  Fidelity: {fidelity:.2f}")

            # Run workload
            result = hamiltonian_mo(config, fidelity=fidelity, seed=42)

            objectives = {
                "prediction_error": result["prediction_error"],
                "drift": result["drift"],
            }

            print(f"  Objectives: pred_err={result['prediction_error']:.4f}, "
                  f"drift={result['drift']:.4f}, "
                  f"cost={result['cost']:.2f}s")

            # Report to scheduler
            action = scheduler.report(
                trial_id=trial_id,
                fidelity=fidelity,
                objectives=objectives,
            )

            if action == "continue":
                fidelity = scheduler.suggest(trial_id)
            elif action == "stop":
                print(f"  → Stopped by scheduler")
                break
            elif action == "done":
                print(f"  → Completed at full fidelity")

                # Observe final result
                searcher.observe(config, objectives)

                # Store in study
                study.add_trial(
                    config=config,
                    objectives=objectives,
                    metadata={"cost": result["cost"]},
                )

                n_completed += 1
                break

    print("\n" + "=" * 60)
    print("Optimization Complete")
    print("=" * 60)

    # Retrieve final front
    trials = study.get_trials()
    front_trials = [
        t for t in trials
        if t["objectives"] is not None
    ]

    if not front_trials:
        print("No completed trials.")
        return

    # Extract objectives
    objectives_array = [
        [t["objectives"]["prediction_error"], t["objectives"]["drift"]]
        for t in front_trials
    ]

    # Compute hypervolume
    ref_point = [1.0, 1.0]  # Worst-case reference
    hv = compute_hypervolume(
        objectives_array,
        ref_point=ref_point,
        directions=["minimize", "minimize"],
    )

    print(f"\nHypervolume: {hv:.4f}")
    print(f"Reference point: {ref_point}")
    print(f"\nPareto front ({len(front_trials)} solutions):")
    print("-" * 60)

    # Sort by prediction error for display
    front_trials.sort(key=lambda t: t["objectives"]["prediction_error"])

    for i, t in enumerate(front_trials[:10]):  # Show top 10
        obj = t["objectives"]
        print(f"{i+1:2d}. pred_err={obj['prediction_error']:.4f}, "
              f"drift={obj['drift']:.4f}")

    if len(front_trials) > 10:
        print(f"... and {len(front_trials) - 10} more solutions")

    print("=" * 60)


if __name__ == "__main__":
    main()
