"""
V05 Log-Warping Effectiveness: Log-scale improves search on scale-sensitive knobs.

Survey reference: Ch 16, Ch 3 (log-warping for learning rates).
Validation claim: Log-transform improves performance on scale-sensitive parameters.

Protocol:
1. Define two search spaces: one with log-transform, one without
2. Run identical searcher on both spaces
3. Compare convergence on objective with log-scale ground truth
4. Pass if log-warped space shows > 15% improvement

Success criteria:
- Improvement > 15% (log-warped finds optimum faster)
- p-value < 0.05 (statistically significant)
"""

from __future__ import annotations

import numpy as np
from scipy.stats import mannwhitneyu

from hponas import SearchSpace, RandomSearcher
from hponas.space import Knob


def log_sensitive_objective(config: dict) -> float:
    """
    Objective highly sensitive to log-scale parameter.

    Ground truth: optimal at lr=3e-4 (in middle of log-scale range)
    Performance degrades sharply as lr deviates in log-space.

    Returns value in [0, 1], maximize.
    """
    lr = config["learning_rate"]

    # Optimal in log-space at log10(lr) = log10(3e-4) ≈ -3.52
    optimal_log = np.log10(3e-4)
    actual_log = np.log10(lr)

    # Very narrow Gaussian in log-space
    # This heavily rewards log-uniform sampling
    score = np.exp(-((actual_log - optimal_log) ** 2) / 0.1)

    # Add minimal noise
    noise = np.random.randn() * 0.01
    return max(0.0, min(1.0, score + noise))


def run_search(
    space: SearchSpace,
    objective: callable,
    n_trials: int,
    seed: int
) -> list[float]:
    """Run search and return incumbent trajectory."""
    searcher = RandomSearcher(space, seed=seed)

    incumbents = []
    best_so_far = float('-inf')

    for trial in range(n_trials):
        configs = searcher.propose(1)
        config = configs[0]

        value = objective(config)

        if value > best_so_far:
            best_so_far = value
        incumbents.append(best_so_far)

        searcher.observe({
            "config": config,
            "value": value,
            "fidelity": 1.0,
            "cost": 1.0
        })

    return incumbents


def v05_log_warping_effectiveness(
    n_trials: int = 50,
    n_seeds: int = 10,
    improvement_threshold: float = 0.15
) -> dict[str, any]:
    """
    V05: Test log-warping effectiveness.

    Args:
        n_trials: Number of trials per seed
        n_seeds: Number of random seeds
        improvement_threshold: Required improvement (e.g., 0.15 = 15%)

    Returns:
        dict with keys: improvement, p_value, passed, details
    """
    print(f"\n=== V05: Log-Warping Effectiveness ===")
    print(f"Trials: {n_trials}, Seeds: {n_seeds}, Threshold: {improvement_threshold*100:.0f}%")

    # Space WITH log-transform
    space_log = SearchSpace()
    space_log.add_knob(Knob("learning_rate", kind="continuous", bounds=(1e-5, 1e-2), transform="log"))

    # Space WITHOUT log-transform (linear sampling)
    space_linear = SearchSpace()
    space_linear.add_knob(Knob("learning_rate", kind="continuous", bounds=(1e-5, 1e-2), transform=None))

    # Run experiments
    log_auc = []
    linear_auc = []

    print("\nRunning experiments:")
    for seed in range(n_seeds):
        print(f"  Seed {seed}...", end=" ", flush=True)

        # Log-warped space
        log_incumbents = run_search(space_log, log_sensitive_objective, n_trials, seed)
        log_auc.append(np.mean(log_incumbents))

        # Linear space
        linear_incumbents = run_search(space_linear, log_sensitive_objective, n_trials, seed + 1000)
        linear_auc.append(np.mean(linear_incumbents))

        print(f"log={log_auc[-1]:.3f}, linear={linear_auc[-1]:.3f}")

    # Statistical comparison
    log_mean = np.mean(log_auc)
    linear_mean = np.mean(linear_auc)
    improvement = (log_mean - linear_mean) / linear_mean

    # Mann-Whitney U test
    statistic, p_value = mannwhitneyu(log_auc, linear_auc, alternative='greater')

    # Success criteria
    passed = improvement >= improvement_threshold and p_value < 0.05

    print(f"\nResults:")
    print(f"  Log-warped AUC: {log_mean:.4f}")
    print(f"  Linear AUC: {linear_mean:.4f}")
    print(f"  Improvement: {improvement*100:.2f}%")
    print(f"  p-value: {p_value:.4f}")
    print(f"  Status: {'✓ PASSED' if passed else '✗ FAILED'}")

    return {
        "log_mean": log_mean,
        "linear_mean": linear_mean,
        "improvement": improvement,
        "p_value": p_value,
        "passed": passed,
        "n_trials": n_trials,
        "n_seeds": n_seeds,
        "log_auc": log_auc,
        "linear_auc": linear_auc,
    }


if __name__ == "__main__":
    print("="*70)
    print("V05 Log-Warping Validation")
    print("="*70)

    result = v05_log_warping_effectiveness(
        n_trials=50,
        n_seeds=10,
        improvement_threshold=0.15  # 15% improvement required
    )

    print("\n" + "="*70)
    if result["passed"]:
        print("V05 VALIDATION: ✓ PASSED")
        print(f"Log-warping improves search by {result['improvement']*100:.1f}% (p={result['p_value']:.4f})")
    else:
        print("V05 VALIDATION: ✗ FAILED")
        if result['improvement'] < 0.15:
            print(f"Improvement {result['improvement']*100:.1f}% below 15% threshold")
        if result['p_value'] >= 0.05:
            print(f"p-value {result['p_value']:.4f} not significant (>= 0.05)")
    print("="*70)
