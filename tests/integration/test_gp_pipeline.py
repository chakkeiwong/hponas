"""
Integration Tests: GP + Acquisition Pipeline

Tests Gaussian Process model integration with acquisition functions.
Authority: TEST_PYRAMID_v1.md Layer 2
"""

import pytest
import numpy as np

pytest.skip("hponas.models.gp abstraction not yet implemented", allow_module_level=True)

from hponas.models.gp import GaussianProcess, Kernel
from hponas.acquisitions import ExpectedImprovement, UpperConfidenceBound
from hponas.space import SearchSpace, Knob


class TestGPAcquisitionPipeline:
    """Integration tests for GP + acquisition function pipeline."""

    def test_gp_fit_and_predict(self):
        """GP fit on observations, predict at new points."""
        # Generate synthetic data
        X_train = np.array([[0.1], [0.4], [0.7], [0.9]])
        y_train = np.array([0.5, 0.2, 0.8, 0.3])

        kernel = Kernel("rbf", length_scale=0.5, variance=1.0)
        gp = GaussianProcess(kernel, noise=0.01)

        # Fit
        gp.fit(X_train, y_train)

        # Predict
        X_test = np.array([[0.3], [0.6]])
        mean, std = gp.predict(X_test)

        assert mean.shape == (2,)
        assert std.shape == (2,)
        assert np.all(std > 0)  # Uncertainty must be positive

    def test_ei_acquisition_maximization(self):
        """EI acquisition function finds promising regions."""
        # Synthetic observations with minimum at x=0.5
        X_train = np.array([[0.1], [0.3], [0.7], [0.9]])
        y_train = np.array([0.8, 0.4, 0.6, 0.9])

        kernel = Kernel("rbf", length_scale=0.2, variance=1.0)
        gp = GaussianProcess(kernel, noise=0.01)
        gp.fit(X_train, y_train)

        # EI should be high around x=0.5 (exploration region)
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        acq = ExpectedImprovement(gp, best_observed=0.4, xi=0.01)

        candidates = np.linspace(0.0, 1.0, 50).reshape(-1, 1)
        ei_values = np.array([acq.evaluate({"x": x[0]}) for x in candidates])

        # EI should be positive in unexplored regions
        assert np.max(ei_values) > 0.0

        # Best candidate should be in [0.4, 0.6] region
        best_idx = np.argmax(ei_values)
        best_x = candidates[best_idx][0]
        assert 0.3 <= best_x <= 0.7

    def test_ucb_acquisition_exploration_exploitation(self):
        """UCB balances exploration and exploitation via beta."""
        X_train = np.array([[0.2], [0.8]])
        y_train = np.array([0.5, 0.3])

        kernel = Kernel("rbf", length_scale=0.3, variance=1.0)
        gp = GaussianProcess(kernel, noise=0.01)
        gp.fit(X_train, y_train)

        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        # High beta (exploration)
        acq_explore = UpperConfidenceBound(gp, beta=2.0)
        candidates = np.linspace(0.0, 1.0, 30).reshape(-1, 1)
        ucb_explore = np.array([acq_explore.evaluate({"x": x[0]}) for x in candidates])

        # Low beta (exploitation)
        acq_exploit = UpperConfidenceBound(gp, beta=0.1)
        ucb_exploit = np.array([acq_exploit.evaluate({"x": x[0]}) for x in candidates])

        # Exploration should favor uncertain regions (x~0.5)
        best_explore_idx = np.argmax(ucb_explore)
        best_explore_x = candidates[best_explore_idx][0]

        # Exploitation should favor known good regions (x~0.8)
        best_exploit_idx = np.argmax(ucb_exploit)
        best_exploit_x = candidates[best_exploit_idx][0]

        # Exploration picks more uncertain region
        assert abs(best_explore_x - 0.5) < abs(best_exploit_x - 0.5)

    def test_gp_acq_optimization_loop(self):
        """Full BO loop: fit GP → optimize acquisition → observe → repeat."""
        # Target function: minimize (x-0.7)^2
        def target(x):
            return (x - 0.7)**2

        # Initial observations
        X_train = [np.array([0.1]), np.array([0.9])]
        y_train = [target(0.1), target(0.9)]

        kernel = Kernel("rbf", length_scale=0.3, variance=1.0)
        space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])

        # Run 5 BO iterations
        for iteration in range(5):
            # Fit GP
            gp = GaussianProcess(kernel, noise=0.01)
            gp.fit(np.array(X_train), np.array(y_train))

            # Optimize EI
            best_observed = min(y_train)
            acq = ExpectedImprovement(gp, best_observed=best_observed, xi=0.01)

            # Grid search for next point
            candidates = np.linspace(0.0, 1.0, 100)
            ei_values = [acq.evaluate({"x": x}) for x in candidates]
            best_idx = np.argmax(ei_values)
            next_x = candidates[best_idx]

            # Observe
            next_y = target(next_x)
            X_train.append(np.array([next_x]))
            y_train.append(next_y)

        # After 5 iterations, should find near-optimal x~0.7
        best_final = min(y_train)
        assert best_final < 0.05  # Close to minimum at 0.0

    def test_gp_2d_acquisition(self):
        """GP + acquisition in 2D space (Branin)."""
        # Branin function
        def branin(x1, x2):
            a = 1.0
            b = 5.1 / (4 * np.pi**2)
            c = 5.0 / np.pi
            r = 6.0
            s = 10.0
            t = 1.0 / (8 * np.pi)
            term1 = a * (x2 - b * x1**2 + c * x1 - r)**2
            term2 = s * (1 - t) * np.cos(x1)
            term3 = s
            return term1 + term2 + term3

        # Initial observations (4 random points)
        X_train = np.array([
            [-3.0, 5.0],
            [0.0, 10.0],
            [5.0, 2.0],
            [8.0, 12.0],
        ])
        y_train = np.array([branin(x[0], x[1]) for x in X_train])

        kernel = Kernel("rbf", length_scale=2.0, variance=10.0)
        gp = GaussianProcess(kernel, noise=0.1)
        gp.fit(X_train, y_train)

        # Predict at new points
        X_test = np.array([
            [0.0, 5.0],
            [3.0, 8.0],
        ])
        mean, std = gp.predict(X_test)

        assert mean.shape == (2,)
        assert std.shape == (2,)

        # Evaluate acquisition
        best_observed = np.min(y_train)
        acq = ExpectedImprovement(gp, best_observed=best_observed, xi=0.01)

        ei_val = acq.evaluate({"x1": 0.0, "x2": 5.0})
        assert ei_val >= 0.0  # EI is always non-negative
