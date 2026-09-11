"""
V04-T0 Baseline Floor Check: Random search beats pathological configurations.

Survey reference: Ch 16, validation category "performance check" (baseline floor).
Validation claim: Random search beats explicitly bad hyperparameter configurations on rl_routine workload.

Protocol:
1. Run random search for N trials on rl_routine workload
2. Run pathological fixed configuration for N trials on same workload
3. Compare area under incumbent curves (AUC)
4. Pass if random > pathological by threshold (e.g., 5%)
5. Statistical significance: Mann-Whitney U test, p < 0.05

Pathological configuration (from v04_t0_protocol.md):
- learning_rate = 1e-5 (too low, learning stalls)
- batch_size = 64 (too small, high variance)
- entropy_cost = 0.1 (too high, exploration dominates)

This establishes a floor: random search must beat obviously broken configurations.
"""

import json
import numpy as np
from pathlib import Path
from scipy.stats import mannwhitneyu
from typing import Dict, Any, List

# Pre-recorded threshold (prevents post-hoc tuning per V16 audit)
IMPROVEMENT_THRESHOLD = 0.05  # 5% improvement required

# Pathological configuration (per v04_t0_protocol.md lines 39-42)
PATHOLOGICAL_CONFIG = {
    "learning_rate": 1e-5,
    "batch_size": 64,
    "entropy_cost": 0.1
}

# Experimental parameters (per v04_t0_protocol.md lines 66-69)
N_TRIALS = 50
N_SEEDS = 5
RANDOM_SEEDS = [0, 1, 2, 3, 4]
WORKLOAD_NAME = "rl_routine"


def load_baseline_data() -> Dict[str, Any]:
    """Load pre-recorded baseline curves."""
    baseline_path = Path(__file__).parent / "baselines" / f"{WORKLOAD_NAME}_baseline.json"

    if not baseline_path.exists():
        raise FileNotFoundError(
            f"Baseline data not found at {baseline_path}. "
            f"Run the baseline generation script first."
        )

    with open(baseline_path, 'r') as f:
        return json.load(f)


def compute_auc(incumbent_curve: List[float]) -> float:
    """Compute area under incumbent curve (normalized by number of trials)."""
    return float(np.trapz(incumbent_curve) / len(incumbent_curve))


def extract_random_auc(data: Dict[str, Any]) -> List[float]:
    """Extract AUC values for random search across seeds."""
    random_aucs = []

    for seed in RANDOM_SEEDS:
        seed_key = f"random_seed_{seed}"
        if seed_key not in data:
            raise KeyError(f"Missing random baseline data for seed {seed}")

        incumbent_curve = data[seed_key]["incumbent_curve"]
        auc = compute_auc(incumbent_curve)
        random_aucs.append(auc)

    return random_aucs


def extract_pathological_auc(data: Dict[str, Any]) -> List[float]:
    """Extract AUC values for pathological configuration across seeds."""
    pathological_aucs = []

    for seed in RANDOM_SEEDS:
        seed_key = f"pathological_seed_{seed}"
        if seed_key not in data:
            raise KeyError(f"Missing pathological baseline data for seed {seed}")

        incumbent_curve = data[seed_key]["incumbent_curve"]
        auc = compute_auc(incumbent_curve)
        pathological_aucs.append(auc)

    return pathological_aucs


def run_check() -> Dict[str, Any]:
    """
    Run V04-T0 baseline floor check: Random vs Pathological.

    Returns:
        Dictionary with check results including:
        - passed: bool
        - random_auc_mean: float
        - pathological_auc_mean: float
        - improvement: float
        - p_value: float
        - threshold: float
        - message: str
    """
    # Load pre-recorded baseline data
    data = load_baseline_data()

    # Extract AUC values
    random_aucs = extract_random_auc(data)
    pathological_aucs = extract_pathological_auc(data)

    # Compute statistics
    random_mean = float(np.mean(random_aucs))
    pathological_mean = float(np.mean(pathological_aucs))
    improvement = random_mean - pathological_mean

    # Statistical test: Mann-Whitney U (one-sided, random > pathological)
    statistic, p_value = mannwhitneyu(
        random_aucs,
        pathological_aucs,
        alternative='greater'
    )

    # Check passing criteria
    improvement_met = improvement >= IMPROVEMENT_THRESHOLD
    significance_met = p_value < 0.05
    passed = improvement_met and significance_met

    # Construct result message
    if passed:
        message = (
            f"Random search beats pathological configuration: "
            f"improvement={improvement:.4f} (threshold={IMPROVEMENT_THRESHOLD}), "
            f"p={p_value:.4f}"
        )
    else:
        reasons = []
        if not improvement_met:
            reasons.append(
                f"improvement {improvement:.4f} < threshold {IMPROVEMENT_THRESHOLD}"
            )
        if not significance_met:
            reasons.append(f"p-value {p_value:.4f} >= 0.05")
        message = f"Check failed: {'; '.join(reasons)}"

    return {
        "passed": passed,
        "random_auc_mean": random_mean,
        "pathological_auc_mean": pathological_mean,
        "improvement": improvement,
        "p_value": float(p_value),
        "threshold": IMPROVEMENT_THRESHOLD,
        "message": message,
        "n_trials": N_TRIALS,
        "n_seeds": N_SEEDS,
        "pathological_config": PATHOLOGICAL_CONFIG
    }


if __name__ == "__main__":
    result = run_check()

    # Print human-readable summary
    print("=" * 60)
    print("V04-T0: Random Baseline Floor Check")
    print("=" * 60)
    print(f"Workload: {WORKLOAD_NAME}")
    print(f"Trials per seed: {N_TRIALS}")
    print(f"Seeds: {N_SEEDS}")
    print()
    print(f"Random AUC (mean):       {result['random_auc_mean']:.4f}")
    print(f"Pathological AUC (mean): {result['pathological_auc_mean']:.4f}")
    print(f"Improvement:             {result['improvement']:.4f}")
    print(f"Threshold:               {result['threshold']:.4f}")
    print(f"P-value:                 {result['p_value']:.4f}")
    print()
    print(f"Status: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"Message: {result['message']}")
    print("=" * 60)

    # Save results to JSON
    output_path = Path(__file__).parent / "results" / "v04_t0_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nResults saved to: {output_path}")
