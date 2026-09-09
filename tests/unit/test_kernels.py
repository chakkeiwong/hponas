"""
Unit Tests: Gaussian Process Kernels

Tests RBF and Matern kernels.
Authority: TEST_PYRAMID_v1.md Layer 1
"""

import pytest
import numpy as np

pytest.skip("hponas.models.gp abstraction not yet implemented", allow_module_level=True)

from hponas.models.gp import Kernel


class TestRBFKernel:
    """Unit tests for RBF (squared exponential) kernel."""

    def test_rbf_diagonal_is_variance(self):
        """K(x, x) = variance."""
        kernel = Kernel("rbf", length_scale=1.0, variance=2.5)

        x = np.array([[0.5, 0.3]])
        K = kernel.compute(x, x)

        assert K.shape == (1, 1)
        assert abs(K[0, 0] - 2.5) < 1e-6

    def test_rbf_symmetry(self):
        """K(x1, x2) = K(x2, x1)."""
        kernel = Kernel("rbf", length_scale=1.0, variance=1.0)

        x1 = np.array([[0.2, 0.5]])
        x2 = np.array([[0.8, 0.3]])

        K12 = kernel.compute(x1, x2)
        K21 = kernel.compute(x2, x1)

        assert abs(K12[0, 0] - K21[0, 0]) < 1e-10

    def test_rbf_decreases_with_distance(self):
        """K(x1, x2) decreases as ||x1 - x2|| increases."""
        kernel = Kernel("rbf", length_scale=1.0, variance=1.0)

        x1 = np.array([[0.0]])
        x_near = np.array([[0.1]])
        x_far = np.array([[1.0]])

        K_near = kernel.compute(x1, x_near)[0, 0]
        K_far = kernel.compute(x1, x_far)[0, 0]

        assert K_near > K_far

    def test_rbf_length_scale_effect(self):
        """Larger length_scale increases correlation."""
        x1 = np.array([[0.0]])
        x2 = np.array([[0.5]])

        kernel_short = Kernel("rbf", length_scale=0.1, variance=1.0)
        kernel_long = Kernel("rbf", length_scale=2.0, variance=1.0)

        K_short = kernel_short.compute(x1, x2)[0, 0]
        K_long = kernel_long.compute(x1, x2)[0, 0]

        assert K_long > K_short

    def test_rbf_batch_computation(self):
        """Compute kernel matrix for multiple points."""
        kernel = Kernel("rbf", length_scale=1.0, variance=1.0)

        X = np.array([[0.0], [0.5], [1.0]])
        K = kernel.compute(X, X)

        assert K.shape == (3, 3)
        # Diagonal should be variance
        assert abs(K[0, 0] - 1.0) < 1e-6
        assert abs(K[1, 1] - 1.0) < 1e-6
        assert abs(K[2, 2] - 1.0) < 1e-6

        # Off-diagonal: symmetry
        assert abs(K[0, 1] - K[1, 0]) < 1e-10
        assert abs(K[0, 2] - K[2, 0]) < 1e-10

    def test_rbf_multidimensional(self):
        """RBF kernel works in multiple dimensions."""
        kernel = Kernel("rbf", length_scale=1.0, variance=1.0)

        X = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ])
        K = kernel.compute(X, X)

        assert K.shape == (3, 3)
        assert abs(K[0, 0] - 1.0) < 1e-6

        # Points [1,0] and [0,1] have same distance from [0,0]
        assert abs(K[0, 1] - K[0, 2]) < 1e-6


class TestMaternKernel:
    """Unit tests for Matern kernel."""

    def test_matern_diagonal_is_variance(self):
        """K(x, x) = variance."""
        kernel = Kernel("matern", length_scale=1.0, variance=2.0, nu=1.5)

        x = np.array([[0.3]])
        K = kernel.compute(x, x)

        assert abs(K[0, 0] - 2.0) < 1e-6

    def test_matern_symmetry(self):
        """K(x1, x2) = K(x2, x1)."""
        kernel = Kernel("matern", length_scale=1.0, variance=1.0, nu=2.5)

        x1 = np.array([[0.2]])
        x2 = np.array([[0.8]])

        K12 = kernel.compute(x1, x2)
        K21 = kernel.compute(x2, x1)

        assert abs(K12[0, 0] - K21[0, 0]) < 1e-10

    def test_matern_nu_effect(self):
        """Different nu values produce different smoothness."""
        x1 = np.array([[0.0]])
        x2 = np.array([[0.5]])

        kernel_nu1 = Kernel("matern", length_scale=1.0, variance=1.0, nu=0.5)
        kernel_nu2 = Kernel("matern", length_scale=1.0, variance=1.0, nu=2.5)

        K_nu1 = kernel_nu1.compute(x1, x2)[0, 0]
        K_nu2 = kernel_nu2.compute(x1, x2)[0, 0]

        # Different nu produces different covariance
        assert abs(K_nu1 - K_nu2) > 0.01

    def test_matern_batch_computation(self):
        """Compute Matern kernel matrix for batch."""
        kernel = Kernel("matern", length_scale=1.0, variance=1.0, nu=1.5)

        X = np.array([[0.0], [0.5], [1.0]])
        K = kernel.compute(X, X)

        assert K.shape == (3, 3)
        assert abs(K[0, 0] - 1.0) < 1e-6
        assert abs(K[1, 1] - 1.0) < 1e-6

    def test_matern_positive_definite(self):
        """Kernel matrix is positive definite."""
        kernel = Kernel("matern", length_scale=1.0, variance=1.0, nu=2.5)

        X = np.random.randn(10, 2)
        K = kernel.compute(X, X)

        # All eigenvalues should be positive
        eigvals = np.linalg.eigvalsh(K)
        assert np.all(eigvals > -1e-10)  # Allow numerical tolerance


class TestKernelProperties:
    """Tests for general kernel properties."""

    def test_invalid_kernel_type_raises(self):
        """Invalid kernel type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown kernel"):
            kernel = Kernel("invalid_kernel", length_scale=1.0, variance=1.0)

    def test_kernel_cross_covariance(self):
        """Compute K(X1, X2) for different sets."""
        kernel = Kernel("rbf", length_scale=1.0, variance=1.0)

        X1 = np.array([[0.0], [1.0]])
        X2 = np.array([[0.5], [1.5], [2.0]])

        K = kernel.compute(X1, X2)

        assert K.shape == (2, 3)
        # K[0, 0] is covariance between X1[0] and X2[0]
        assert K[0, 0] > 0

    def test_kernel_variance_scaling(self):
        """Variance parameter scales all covariances."""
        kernel1 = Kernel("rbf", length_scale=1.0, variance=1.0)
        kernel2 = Kernel("rbf", length_scale=1.0, variance=4.0)

        X = np.array([[0.0], [0.5]])
        K1 = kernel1.compute(X, X)
        K2 = kernel2.compute(X, X)

        # K2 should be 4x K1
        assert abs(K2[0, 1] - 4.0 * K1[0, 1]) < 1e-6
