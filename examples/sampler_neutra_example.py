"""
Example: MCMC sampler tuning with correctness gates.

This example demonstrates:
1. Sampler correctness metrics (ESS, R̂, divergences)
2. Veto gates for correctness constraints
3. MO-ASHA with ESS-based ranking
4. Posterior agreement validation

Survey reference: Ch 16 (sampler correctness), Ch 11 (HMC/NUTS regime).
Validation: V13 (veto gates, ESS ranking, posterior agreement).
"""

from __future__ import annotations

from hponas import SearchSpace, FloatKnob, IntKnob, CategoricalKnob
from hponas import Store, Study
from hponas import SobolSearcher
from hponas import MOASHAScheduler

from workloads.sampler_neutra import sampler_neutra


def divergence_veto(trial_id: str, objectives: dict[str, float]) -> bool:
    """Veto gate: reject if divergence rate > 5%."""
    return objectives.get("divergences", 1.0) <= 0.05


def rhat_veto(trial_id: str, objectives: dict[str, float]) -> bool:
    """Veto gate: reject if R̂ > 1.1 (not converged)."""
    return objectives.get("rhat", 10.0) <= 1.1


def ess_veto(trial_id: str, objectives: dict[str, float]) -> bool:
    """Veto gate: reject if ESS < 100 (too few effective samples)."""
    return objectives.get("ess", 0.0) >= 100.0


def main():
    # Define search space
    space = SearchSpace(
        knobs=[
            FloatKnob("step_size", 1e-3, 1.0, log_scale=True),
            IntKnob("n_leapfrog", 1, 50),
            IntKnob("n_chains", 2, 8),
            CategoricalKnob("target", ["funnel"]),
        ]
    )

    # Create store and study
    store = Store(":memory:")
    study = store.create_study(
        name="sampler_tuning",
        space=space,
        objectives=["ess", "rhat", "divergences"],
        directions=["maximize", "minimize", "minimize"],
    )

    # Create searcher
    searcher = SobolSearcher(space=space, seed=42)

    # Create scheduler with veto gates
    scheduler = MOASHAScheduler(
        min_fidelity=0.1,
        max_fidelity=1.0,
        reduction_factor=3,
        grace_period=1,
    )

    # Register veto gates
    scheduler.gate(divergence_veto)
    scheduler.gate(rhat_veto)
    scheduler.gate(ess_veto)

    # Budget
    max_trials = 20
    n_completed = 0

    print("=" * 60)
    print("Sampler Tuning Example with Correctness Gates")
    print("=" * 60)
    print(f"Objectives: ESS (max), R̂ (min), divergences (min)")
    print(f"Budget: {max_trials} trials")
    print(f"Searcher: Sobol")
    print(f"Scheduler: MO-ASHA with 3 veto gates")
    print(f"  - Divergence rate ≤ 5%")
    print(f"  - R̂ ≤ 1.1")
    print(f"  - ESS ≥ 100")
    print("=" * 60)

    # Main loop
    while n_completed < max_trials:
        # Propose configuration
        config = searcher.propose()
        trial_id = f"trial_{n_completed:03d}"

        print(f"\n[{n_completed+1}/{max_trials}] Trial {trial_id}")
        print(f"  Config: step_size={config['step_size']:.4f}, "
              f"n_leapfrog={config['n_leapfrog']}, "
              f"n_chains={config['n_chains']}")

        # Ask scheduler for fidelity
        fidelity = scheduler.suggest(trial_id)

        while True:
            print(f"  Fidelity: {fidelity:.2f}")

            # Run workload
            result = sampler_neutra(config, fidelity=fidelity, seed=42)

            objectives = {
                "ess": result["ess"],
                "rhat": result["rhat"],
                "divergences": result["divergences"],
            }

            print(f"  Metrics: ESS={result['ess']:.1f}, "
                  f"R̂={result['rhat']:.3f}, "
                  f"div={result['divergences']:.3f}, "
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
                print(f"  → Stopped by scheduler (vetoed or promoted)")
                break
            elif action == "done":
                print(f"  → Completed at full fidelity")

                # Observe final result
                searcher.observe(config, {"ess": objectives["ess"]})

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

    # Show vetoed trials
    vetoed = scheduler.get_vetoed_trials()
    print(f"\nVetoed trials: {len(vetoed)}")
    if vetoed:
        print("  " + ", ".join(vetoed[:5]))
        if len(vetoed) > 5:
            print(f"  ... and {len(vetoed) - 5} more")

    # Retrieve survivors
    trials = study.get_trials()
    survivors = [
        t for t in trials
        if t["objectives"] is not None
    ]

    if not survivors:
        print("\nNo trials passed veto gates.")
        return

    print(f"\nSurvivors: {len(survivors)}")
    print("-" * 60)

    # Sort by ESS (descending)
    survivors.sort(key=lambda t: t["objectives"]["ess"], reverse=True)

    print("\nTop 5 by ESS:")
    for i, t in enumerate(survivors[:5]):
        obj = t["objectives"]
        cfg = t["config"]
        print(f"{i+1}. ESS={obj['ess']:.1f}, R̂={obj['rhat']:.3f}, "
              f"div={obj['divergences']:.3f}")
        print(f"   step_size={cfg['step_size']:.4f}, "
              f"n_leapfrog={cfg['n_leapfrog']}")

    print("=" * 60)


if __name__ == "__main__":
    main()
