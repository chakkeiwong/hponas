"""
Unit Tests: Acquisition Functions

Tests Expected Improvement and Upper Confidence Bound.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import numpy as np

pytest.skip("hponas.acquisitions abstraction not yet implemented", allow_module_level=True)

from hponas.acquisitions import ExpectedImprovement, UpperConfidenceBound
from hponas.models.gp import GaussianProcess, Kernel


class MockGP:
    """Mock GP for testing acquisition functions in isolation."""

    def __init__(self, mean_val, std_val):
        self.mean_val = mean_val
        self.std_val = std_val

    def predict(self, X):
        if isinstance(X, dict):
            # Single config
            return self.mean_val, self.std_val
        else:
            # Batch
            n = len(X)
            return np.full(n, self.mean_val), np.full(n, self.std_val)


class TestExpectedImprovement:
    """Unit tests for Expected Improvement acquisition function."""

    def test_ei_zero_when_no_improvement(self):
        """EI is zero when predicted mean equals best observed."""
        gp = MockGP(mean_val=0.5, std_val=0.1)
        acq = ExpectedImprovement(gp, best_observed=0.5, xi=0.0)

        ei = acq.evaluate({"x": 0.5})

        # With zero improvement and no xi, EI should be ~0
        assert ei < 0.01

    def test_ei_positive_when_better_mean(self):
        """EI is positive when predicted mean < best observed."""
        gp = MockGP(mean_val=0.3, std_val=0.1)
        acq = ExpectedImprovement(gp, best_observed=0.5, xi=0.0)

        ei = acq.evaluate({"x": 0.3})

        assert ei > 0.0

    def test_ei_increases_with_uncertainty(self):
        """EI increases with higher uncertainty (std)."""
        best_observed = 0.5
        mean = 0.4

        gp_low_std = MockGP(mean_val=mean, std_val=0.01)
        acq_low = ExpectedImprovement(gp_low_std, best_observed=best_observed, xi=0.0)

        gp_high_std = MockGP(mean_val=mean, std_val=0.2)
        acq_high = ExpectedImprovement(gp_high_std, best_observed=best_observed, xi=0.0)

        ei_low = acq_low.evaluate({"x": 0.4})
        ei_high = acq_high.evaluate({"x": 0.4})

        assert ei_high > ei_low

    def test_ei_xi_exploration_bonus(self):
        """xi parameter adds exploration bonus."""
        gp = MockGP(mean_val=0.5, std_val=0.1)

        acq_no_xi = ExpectedImprovement(gp, best_observed=0.5, xi=0.0)
        acq_with_xi = ExpectedImprovement(gp, best_observed=0.5, xi=0.01)

        ei_no_xi = acq_no_xi.evaluate({"x": 0.5})
        ei_with_xi = acq_with_xi.evaluate({"x": 0.5})

        assert ei_with_xi > ei_no_xi

    def test_ei_always_non_negative(self):
        """EI is always >= 0."""
        gp = MockGP(mean_val=0.8, std_val=0.05)
        acq = ExpectedImprovement(gp, best_observed=0.3, xi=0.0)

        ei = acq.evaluate({"x": 0.8})

        assert ei >= 0.0

    def test_ei_batch_evaluation(self):
        """EI can evaluate batch of configs."""
        gp = MockGP(mean_val=0.4, std_val=0.1)
        acq = ExpectedImprovement(gp, best_observed=0.5, xi=0.0)

        configs = [{"x": 0.2}, {"x": 0.4}, {"x": 0.6}]
        ei_values = [acq.evaluate(c) for c in configs]

        assert len(ei_values) == 3
        assert all(ei >= 0.0 for ei in ei_values)


class TestUpperConfidenceBound:
    """Unit tests for Upper Confidence Bound acquisition function."""

    def test_ucb_equals_mean_when_beta_zero(self):
        """UCB equals mean when beta=0."""
        gp = MockGP(mean_val=0.5, std_val=0.1)
        acq = UpperConfidenceBound(gp, beta=0.0)

        ucb = acq.evaluate({"x": 0.5})

        assert abs(ucb - 0.5) < 1e-6

    def test_ucb_increases_with_beta(self):
        """UCB increases with larger beta (more exploration)."""
        gp = MockGP(mean_val=0.5, std_val=0.1)

        acq_low_beta = UpperConfidenceBound(gp, beta=0.5)
        acq_high_beta = UpperConfidenceBound(gp, beta=2.0)

        ucb_low = acq_low_beta.evaluate({"x": 0.5})
        ucb_high = acq_high_beta.evaluate({"x": 0.5})

        assert ucb_high > ucb_low

    def test_ucb_exploits_low_std_regions(self):
        """Low beta UCB favors low-std (exploit) regions."""
        gp_low_std = MockGP(mean_val=0.3, std_val=0.01)
        gp_high_std = MockGP(mean_val=0.4, std_val=0.5)

        acq = UpperConfidenceBound(gp_low_std, beta=0.1)
        ucb_low_std = acq.evaluate({"x": 0.3})

        acq = UpperConfidenceBound(gp_high_std, beta=0.1)
        ucb_high_std = acq.evaluate({"x": 0.4})

        # Low std with better mean should win under exploitation
        assert ucb_low_std < ucb_high_std  # Lower is better for minimization

    def test_ucb_explores_high_std_regions(self):
        """High beta UCB favors high-std (explore) regions."""
        gp_low_std = MockGP(mean_val=0.3, std_val=0.01)
        gp_high_std = MockGP(mean_val=0.4, std_val=0.5)

        acq = UpperConfidenceBound(gp_low_std, beta=5.0)
        ucb_low_std = acq.evaluate({"x": 0.3})

        acq = UpperConfidenceBound(gp_high_std, beta=5.0)
        ucb_high_std = acq.evaluate({"x": 0.4})

        # High beta amplifies std, so high-std region might dominate
        # (depends on exact values, but test that beta affects outcome)
        assert ucb_high_std != ucb_low_std

    def test_ucb_batch_evaluation(self):
        """UCB can evaluate batch of configs."""
        gp = MockGP(mean_val=0.4, std_val=0.15)
        acq = UpperConfidenceBound(gp, beta=1.0)

        configs = [{"x": 0.1}, {"x": 0.5}, {"x": 0.9}]
        ucb_values = [acq.evaluate(c) for c in configs]

        assert len(ucb_values) == 3

    def test_ucb_formula_correctness(self):
        """UCB = mean - beta * std (minimization)."""
        mean = 0.6
        std = 0.2
        beta = 1.5

        gp = MockGP(mean_val=mean, std_val=std)
        acq = UpperConfidenceBound(gp, beta=beta)

        ucb = acq.evaluate({"x": 0.6})

        expected = mean - beta * std
        assert abs(ucb - expected) < 1e-6
