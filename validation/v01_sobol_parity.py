"""
V01 Implementation Parity: Sobol sequence distributional equivalence.

Survey reference: Ch 16, validation category "implementation parity."
Validation claim: Our Sobol implementation matches scipy reference distribution.

Protocol:
1. Generate N samples from our SobolSearcher
2. Generate N samples from scipy Sobol reference
3. Apply Kolmogorov-Smirnov test on each dimension
4. Pass if KS statistic < 0.05 and p-value > 0.05 for all dimensions

Success criteria:
- KS statistic < 0.05 (distributions are close)
- p-value > 0.05 (cannot reject null hypothesis of same distribution)
"""

from __future__ import annotations

import numpy as np
from scipy.stats import ks_2samp, qmc

from hponas import SearchSpace, SobolSearcher
from hponas.space import Knob


def v01_sobol_parity(n_samples: int = 1000, n_dims: int = 5, seed: int = 42) -> dict[str, any]:
    """
    V01: Test Sobol implementation parity with scipy reference.

    Args:
        n_samples: Number of samples to generate
        n_dims: Number of dimensions
        seed: Random seed

    Returns:
        dict with keys: ks_statistic, p_value, passed, details
    """
    print(f"\n=== V01: Sobol Implementation Parity ===")
    print(f"Samples: {n_samples}, Dimensions: {n_dims}, Seed: {seed}")

    # Create search space with n_dims continuous knobs
    space = SearchSpace()
    for i in range(n_dims):
        space.add_knob(Knob(f"x{i}", kind="continuous", bounds=(0, 1)))

    # Our implementation
    our_searcher = SobolSearcher(space, seed=seed)
    our_samples = our_searcher.propose(n_samples)

    # Extract samples as numpy array
    our_array = np.array([[config[f"x{i}"] for i in range(n_dims)] for config in our_samples])

    # Reference implementation (scipy)
    ref_sobol = qmc.Sobol(d=n_dims, scramble=True, seed=seed)
    ref_array = ref_sobol.random(n_samples)

    # KS test per dimension
    ks_statistics = []
    p_values = []

    print("\nPer-dimension KS test results:")
    for dim in range(n_dims):
        our_dim = our_array[:, dim]
        ref_dim = ref_array[:, dim]

        ks_stat, p_val = ks_2samp(our_dim, ref_dim)
        ks_statistics.append(ks_stat)
        p_values.append(p_val)

        print(f"  Dimension {dim}: KS={ks_stat:.4f}, p={p_val:.4f}")

    # Overall results
    max_ks = max(ks_statistics)
    min_p = min(p_values)

    # Success: KS < 0.05 (close) and p > 0.05 (same distribution)
    passed = max_ks < 0.05 and min_p > 0.05

    print(f"\nOverall: max_KS={max_ks:.4f}, min_p={min_p:.4f}")
    print(f"Status: {'✓ PASSED' if passed else '✗ FAILED'}")

    return {
        "ks_statistic": max_ks,
        "p_value": min_p,
        "passed": passed,
        "n_samples": n_samples,
        "n_dims": n_dims,
        "per_dimension": [
            {"dim": i, "ks": ks_statistics[i], "p": p_values[i]}
            for i in range(n_dims)
        ]
    }


if __name__ == "__main__":
    # Run validation
    result = v01_sobol_parity(n_samples=1000, n_dims=5)

    print("\n" + "="*60)
    if result["passed"]:
        print("V01 VALIDATION: ✓ PASSED")
        print("Our Sobol implementation matches scipy reference distribution")
    else:
        print("V01 VALIDATION: ✗ FAILED")
        print(f"KS statistic too high or p-value too low")
    print("="*60)
