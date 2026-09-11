"""
V09 validation: qLogNEHVI vs random-weight Chebyshev and NSGA-II.

BUILD_PROGRAM_v2.md validation criterion:
  Claim: the premium MO searcher earns its tier
  Pass rule: qLogNEHVI vs random-weight Chebyshev and wrapped NSGA-II on the
             Hamiltonian task; hypervolume with uncertainty; demote to option
             on a tie
  Gate criteria: V09 (qLogNEHVI beats scalarization or ties and gets demoted)

This validation runs all three multi-objective searchers (qLogNEHVI, Chebyshev
scalarization with random weights, and NSGA-II) on the Hamiltonian task across
multiple seeds and compares hypervolume-over-budget curves with statistical
uncertainty.

Pass conditions:
1. qLogNEHVI achieves strictly higher final hypervolume than both baselines (with
   statistical significance at α=0.05)
2. If qLogNEHVI ties with either baseline, demote it to tier-2 option status

Output:
- Hypervolume curves per searcher with mean and std across seeds
- Statistical test results (paired t-test)
- Pass/fail verdict
- Demotion recommendation if needed
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to Python path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import time
import json
from pathlib import Path

import numpy as np
from scipy import stats

from hponas.space import SearchSpace, Knob
from hponas.searchers_mo import qLogNEHVISearcher, ChebyshevSearcher, NSGAIISearcher
from hponas.reporting_mo import hypervolume, default_reference_point

from workloads.hamiltonian_mo import hamiltonian_mo


def run_searcher_trial(
    searcher,
    space: SearchSpace,
    max_trials: int,
    seed: int,
) -> tuple[list[dict], list[float], list[dict]]:
    """
    Run one searcher for max_trials evaluations.

    Returns:
        configs: List of configurations evaluated
        costs: List of costs (wall-clock seconds) per trial
        objectives_list: List of dicts with objective values per trial
    """
    configs = []
    costs = []
    objectives_list = []

    for trial_idx in range(max_trials):
        # Propose configuration
        proposed = searcher.propose(n=1)
        config = proposed[0]

        # Convert ordinal hidden_dim/n_layers to hidden_sizes list
        # hamiltonian_mo expects hidden_sizes, activation, optimizer
        full_config = {
            "learning_rate": config["learning_rate"],
            "batch_size": config["batch_size"],
            "hidden_sizes": [config["hidden_dim"]] * config["n_layers"],
            "activation": "tanh",
            "weight_decay": config["weight_decay"],
            "optimizer": "adam",
        }

        # Evaluate workload (use lower fidelity for faster validation)
        result = hamiltonian_mo(full_config, fidelity=0.3, seed=seed)

        # Extract objectives
        objectives = {
            "prediction_error": result["prediction_error"],
            "drift": result["drift"],
        }

        # Observe result
        searcher.observe({
            "config": config,
            "objectives": objectives,
            "fidelity": 0.3,
            "cost": result["cost"],
        })

        configs.append(config)
        costs.append(result["cost"])
        objectives_list.append(objectives)

    return configs, costs, objectives_list


def compute_hv_curve(
    objectives_list: list[dict],
    costs: list[float],
    reference_point: np.ndarray,
    n_points: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute hypervolume-over-budget curve.

    Args:
        objectives_list: List of objective dicts with keys ["prediction_error", "drift"]
        costs: List of costs per trial
        reference_point: Reference point for hypervolume computation
        n_points: Number of budget points to sample

    Returns:
        budgets: Array of cumulative budgets
        hvs: Array of hypervolumes at each budget
    """
    # Convert objectives to array (n_trials, 2)
    objectives_array = np.array([
        [obj["prediction_error"], obj["drift"]]
        for obj in objectives_list
    ])

    costs_array = np.array(costs)
    cumulative_costs = np.cumsum(costs_array)
    total_budget = cumulative_costs[-1]

    # Sample budget grid
    budget_grid = np.linspace(0, total_budget, n_points)
    hvs = []

    for budget in budget_grid:
        # Find trials completed within budget
        mask = cumulative_costs <= budget
        if not np.any(mask):
            hvs.append(0.0)
            continue

        # Compute hypervolume of incumbent front
        incumbent_objectives = objectives_array[mask]
        hv = hypervolume(incumbent_objectives, reference_point)
        hvs.append(hv)

    return budget_grid, np.array(hvs)


def run_validation(
    max_trials: int = 30,
    n_seeds: int = 5,
    alpha: float = 0.05,
) -> dict:
    """
    Run V09 validation: qLogNEHVI vs Chebyshev vs NSGA-II.

    Args:
        max_trials: Number of trials per searcher per seed
        n_seeds: Number of random seeds for statistical robustness
        alpha: Significance level for statistical tests

    Returns:
        dict with results, curves, statistics, and verdict
    """
    # Define search space (qLogNEHVI supports continuous/ordinal only)
    space = SearchSpace(
        knobs=[
            Knob("learning_rate", "continuous", (1e-5, 1e-2), transform="log"),
            Knob("batch_size", "ordinal", (16, 256)),
            Knob("hidden_dim", "ordinal", (32, 128)),
            Knob("n_layers", "ordinal", (2, 4)),
            Knob("weight_decay", "continuous", (1e-6, 1e-2), transform="log"),
        ]
    )

    objectives = ["prediction_error", "drift"]

    # Reference point: anti-ideal (worse than worst expected)
    # Both objectives are minimized, so ref point must dominate all points
    reference_point = np.array([10.0, 10.0])

    # Storage for curves per searcher per seed
    results = {
        "qLogNEHVI": {"budgets": [], "hvs": [], "final_hvs": []},
        "Chebyshev": {"budgets": [], "hvs": [], "final_hvs": []},
        "NSGA-II": {"budgets": [], "hvs": [], "final_hvs": []},
    }

    print("=" * 70)
    print("V09 qLogNEHVI vs Scalarization Validation")
    print("=" * 70)
    print()
    print(f"=== V09: Premium MO Searcher Validation ===")
    print(f"Claim: qLogNEHVI earns its tier")
    print(f"Max trials per searcher: {max_trials}")
    print(f"Seeds: {n_seeds}")
    print(f"Significance level α: {alpha}")
    print()

    for seed in range(n_seeds):
        print(f"Running seed {seed}...")

        # qLogNEHVI
        print(f"  qLogNEHVI...", end=" ", flush=True)
        start = time.time()
        searcher_qnehvi = qLogNEHVISearcher(
            space=space,
            objectives=objectives,
            reference_point=reference_point,
            seed=seed,
        )
        configs_qn, costs_qn, objs_qn = run_searcher_trial(
            searcher_qnehvi, space, max_trials, seed
        )
        budgets_qn, hvs_qn = compute_hv_curve(objs_qn, costs_qn, reference_point)
        results["qLogNEHVI"]["budgets"].append(budgets_qn)
        results["qLogNEHVI"]["hvs"].append(hvs_qn)
        results["qLogNEHVI"]["final_hvs"].append(hvs_qn[-1])
        elapsed = time.time() - start
        print(f"done ({elapsed:.1f}s)")

        # Chebyshev with random weights
        print(f"  Chebyshev...", end=" ", flush=True)
        start = time.time()
        rng = np.random.RandomState(seed)
        random_weights = rng.dirichlet(np.ones(2))  # Random simplex weights
        searcher_cheb = ChebyshevSearcher(
            space=space,
            objectives=objectives,
            weights=random_weights,
            reference_point=reference_point,
            base_searcher="random",
            seed=seed,
        )
        configs_ch, costs_ch, objs_ch = run_searcher_trial(
            searcher_cheb, space, max_trials, seed
        )
        budgets_ch, hvs_ch = compute_hv_curve(objs_ch, costs_ch, reference_point)
        results["Chebyshev"]["budgets"].append(budgets_ch)
        results["Chebyshev"]["hvs"].append(hvs_ch)
        results["Chebyshev"]["final_hvs"].append(hvs_ch[-1])
        elapsed = time.time() - start
        print(f"done ({elapsed:.1f}s)")

        # NSGA-II
        print(f"  NSGA-II...", end=" ", flush=True)
        start = time.time()
        searcher_nsga = NSGAIISearcher(
            space=space,
            objectives=objectives,
            population_size=20,
            seed=seed,
        )
        configs_ns, costs_ns, objs_ns = run_searcher_trial(
            searcher_nsga, space, max_trials, seed
        )
        budgets_ns, hvs_ns = compute_hv_curve(objs_ns, costs_ns, reference_point)
        results["NSGA-II"]["budgets"].append(budgets_ns)
        results["NSGA-II"]["hvs"].append(hvs_ns)
        results["NSGA-II"]["final_hvs"].append(hvs_ns[-1])
        elapsed = time.time() - start
        print(f"done ({elapsed:.1f}s)")
        print()

    # Compute statistics
    print("=" * 70)
    print("Results")
    print("=" * 70)
    print()

    for name in ["qLogNEHVI", "Chebyshev", "NSGA-II"]:
        final_hvs = results[name]["final_hvs"]
        mean_hv = np.mean(final_hvs)
        std_hv = np.std(final_hvs, ddof=1)
        print(f"{name:12s}: final HV = {mean_hv:.4f} ± {std_hv:.4f}")

    print()

    # Statistical tests (paired t-test on final hypervolumes)
    qnehvi_hvs = np.array(results["qLogNEHVI"]["final_hvs"])
    cheb_hvs = np.array(results["Chebyshev"]["final_hvs"])
    nsga_hvs = np.array(results["NSGA-II"]["final_hvs"])

    # qLogNEHVI vs Chebyshev
    t_stat_cheb, p_value_cheb = stats.ttest_rel(qnehvi_hvs, cheb_hvs)
    mean_diff_cheb = np.mean(qnehvi_hvs - cheb_hvs)

    # qLogNEHVI vs NSGA-II
    t_stat_nsga, p_value_nsga = stats.ttest_rel(qnehvi_hvs, nsga_hvs)
    mean_diff_nsga = np.mean(qnehvi_hvs - nsga_hvs)

    print("Statistical Tests (paired t-test):")
    print(f"  qLogNEHVI vs Chebyshev: t={t_stat_cheb:.3f}, p={p_value_cheb:.4f}, Δ={mean_diff_cheb:.4f}")
    print(f"  qLogNEHVI vs NSGA-II:   t={t_stat_nsga:.3f}, p={p_value_nsga:.4f}, Δ={mean_diff_nsga:.4f}")
    print()

    # Verdict
    beats_cheb = (mean_diff_cheb > 0) and (p_value_cheb < alpha)
    beats_nsga = (mean_diff_nsga > 0) and (p_value_nsga < alpha)
    ties_cheb = not beats_cheb and abs(mean_diff_cheb) < 0.01  # Tie threshold
    ties_nsga = not beats_nsga and abs(mean_diff_nsga) < 0.01

    passed = beats_cheb and beats_nsga
    demote = (ties_cheb or ties_nsga) or not passed

    print("=" * 70)
    print("Verdict")
    print("=" * 70)
    print()

    if passed:
        print("✓ PASS: qLogNEHVI beats both baselines")
        print("  Gate criterion: qLogNEHVI retains tier-1 status")
    elif demote and (ties_cheb or ties_nsga):
        print("○ TIE: qLogNEHVI ties with baseline(s)")
        print("  Gate criterion: demote qLogNEHVI to tier-2 option")
    else:
        print("✗ FAIL: qLogNEHVI does not beat baselines")
        print("  Gate criterion: demote qLogNEHVI to tier-2 option")

    print()

    return {
        "results": results,
        "statistics": {
            "qLogNEHVI_vs_Chebyshev": {
                "t_stat": t_stat_cheb,
                "p_value": p_value_cheb,
                "mean_diff": mean_diff_cheb,
                "beats": beats_cheb,
            },
            "qLogNEHVI_vs_NSGA-II": {
                "t_stat": t_stat_nsga,
                "p_value": p_value_nsga,
                "mean_diff": mean_diff_nsga,
                "beats": beats_nsga,
            },
        },
        "verdict": {
            "passed": passed,
            "demote": demote,
        },
    }


if __name__ == "__main__":
    # Load cached results if available
    output_dir = Path(__file__).parent.parent / "results"
    output_file = output_dir / "v09_qlogNEHVI_vs_scalarization.json"

    if output_file.exists():
        print("Loading cached validation results...")
        with open(output_file, "r") as f:
            results = json.load(f)

        print("\n" + "=" * 70)
        print("V09 qLogNEHVI vs Scalarization Validation (CACHED)")
        print("=" * 70)
        print()

        print("qLogNEHVI   : final HV = {:.4f} ± {:.4f}".format(
            results["statistics"]["qLogNEHVI"]["mean"],
            results["statistics"]["qLogNEHVI"]["std"]
        ))
        print("Chebyshev   : final HV = {:.4f} ± {:.4f}".format(
            results["statistics"]["Chebyshev"]["mean"],
            results["statistics"]["Chebyshev"]["std"]
        ))
        print("NSGA-II     : final HV = {:.4f} ± {:.4f}".format(
            results["statistics"]["NSGA-II"]["mean"],
            results["statistics"]["NSGA-II"]["std"]
        ))
        print()
        print("Statistical Tests (paired t-test):")
        for comparison in results["statistics"].get("comparisons", []):
            print("  {}: t={:.3f}, p={:.4f}, Δ={:.4f}".format(
                comparison["pair"],
                comparison["t_stat"],
                comparison["p_value"],
                comparison["mean_diff"]
            ))
        print()
        print("=" * 70)
        print("Verdict")
        print("=" * 70)
        print()
        print(results["verdict"])
        print()
    else:
        # Run validation
        results = run_validation(max_trials=30, n_seeds=5, alpha=0.05)

        # Convert numpy arrays to lists for JSON serialization
        def make_serializable(obj):
            if isinstance(obj, (np.floating, float)):
                return float(obj)
            elif isinstance(obj, (np.integer, int)):
                return int(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(x) for x in obj]
            elif isinstance(obj, (np.bool_, bool)):
                return bool(obj)
            else:
                return obj

        serializable_results = {
            "verdict": make_serializable(results["verdict"]),
            "statistics": make_serializable(results["statistics"]),
            "final_hvs": {
                searcher: [float(x) for x in results["results"][searcher]["final_hvs"]]
                for searcher in ["qLogNEHVI", "Chebyshev", "NSGA-II"]
            },
        }

        # Save results
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "v09_qlogNEHVI_vs_scalarization.json"

        with open(output_file, "w") as f:
            json.dump(serializable_results, f, indent=2)

        print(f"\nResults saved to {output_file}")
