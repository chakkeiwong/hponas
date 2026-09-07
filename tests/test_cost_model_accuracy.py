"""Cost model accuracy tests.

Tests that CostModelGP accurately predicts trial costs and generalizes to unseen configs.
"""

import numpy as np
import pytest
from hponas import SearchSpace
from hponas.space import Knob
from hponas.searchers_cost import CostModelGP


def test_linear_cost_trend_prediction():
    """Cost model learns linear trend: cost(x) = 1 + 9x."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # True cost function: 1s to 10s linearly
    def true_cost(x):
        return 1.0 + 9.0 * x

    # Train on 10 uniform samples
    rng = np.random.RandomState(42)
    train_x = rng.uniform(0, 1, 10)
    for x_val in train_x:
        model.observe({"x": x_val}, cost=true_cost(x_val))

    # Test on 20 held-out samples
    test_x = rng.uniform(0, 1, 20)
    test_configs = [{"x": x_val} for x_val in test_x]
    predictions = model.predict(test_configs)
    true_costs = np.array([true_cost(x_val) for x_val in test_x])

    # Measure MAPE (mean absolute percentage error)
    mape = np.mean(np.abs((predictions - true_costs) / true_costs))

    # Measure Spearman correlation
    from scipy.stats import spearmanr
    rho, _ = spearmanr(predictions, true_costs)

    assert mape < 0.20, f"MAPE should be <20%, got {mape:.3f}"
    assert rho > 0.9, f"Spearman rho should be >0.9, got {rho:.3f}"


def test_quadratic_cost_trend_prediction():
    """Cost model learns quadratic trend: cost(x) = 1 + 99x²."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # True cost function: 1s to 100s quadratically
    def true_cost(x):
        return 1.0 + 99.0 * x**2

    # Train on 15 samples including corners
    rng = np.random.RandomState(42)
    train_x = np.concatenate([[0.0, 0.5, 1.0], rng.uniform(0, 1, 12)])
    for x_val in train_x:
        model.observe({"x": x_val}, cost=true_cost(x_val))

    # Test on 25 held-out samples
    test_x = rng.uniform(0, 1, 25)
    test_configs = [{"x": x_val} for x_val in test_x]
    predictions = model.predict(test_configs)
    true_costs = np.array([true_cost(x_val) for x_val in test_x])

    # Measure MAPE
    mape = np.mean(np.abs((predictions - true_costs) / true_costs))

    # Check monotonicity: predictions should increase with x (roughly)
    sorted_indices = np.argsort(test_x)
    sorted_preds = predictions[sorted_indices]

    # Allow some noise, but trend should be upward
    monotonic_violations = np.sum(np.diff(sorted_preds) < -1.0)  # Allow small violations

    assert mape < 0.25, f"MAPE should be <25%, got {mape:.3f}"
    assert monotonic_violations < len(sorted_preds) // 4, \
        f"Too many monotonicity violations: {monotonic_violations}/{len(sorted_preds)}"


def test_multidimensional_cost():
    """Cost model learns additive 2D cost: cost(x1, x2) = 1 + 4x1 + 4x2."""
    space = SearchSpace(knobs=[
        Knob(name="x1", kind="continuous", bounds=(0.0, 1.0)),
        Knob(name="x2", kind="continuous", bounds=(0.0, 1.0)),
    ])
    model = CostModelGP(space)

    # True cost function: additive
    def true_cost(x1, x2):
        return 1.0 + 4.0 * x1 + 4.0 * x2

    # Train on 20 samples
    rng = np.random.RandomState(42)
    for _ in range(20):
        x1, x2 = rng.uniform(0, 1, 2)
        model.observe({"x1": x1, "x2": x2}, cost=true_cost(x1, x2))

    # Test on 30 held-out samples
    test_configs = []
    true_costs = []
    for _ in range(30):
        x1, x2 = rng.uniform(0, 1, 2)
        test_configs.append({"x1": x1, "x2": x2})
        true_costs.append(true_cost(x1, x2))

    predictions = model.predict(test_configs)
    true_costs = np.array(true_costs)

    # Measure MAPE
    mape = np.mean(np.abs((predictions - true_costs) / true_costs))

    # Check corner rankings: (0, 0) < (0.5, 0.5) < (1, 1)
    corners = [{"x1": 0.0, "x2": 0.0}, {"x1": 0.5, "x2": 0.5}, {"x1": 1.0, "x2": 1.0}]
    corner_preds = model.predict(corners)

    assert corner_preds[0] < corner_preds[1] < corner_preds[2], \
        f"Corner predictions should increase: {corner_preds}"
    assert mape < 0.30, f"MAPE should be <30%, got {mape:.3f}"


def test_log_warped_cost():
    """Cost model handles log-transformed dimension: cost(x) = x / 10."""
    space = SearchSpace(knobs=[
        Knob(name="x", kind="continuous", bounds=(1.0, 100.0), transform="log")
    ])
    model = CostModelGP(space)

    # True cost function: linear in original space, log-linear in warped space
    def true_cost(x):
        return x / 10.0

    # Train on 10 log-uniform samples
    rng = np.random.RandomState(42)
    train_x = np.exp(rng.uniform(np.log(1), np.log(100), 10))
    for x_val in train_x:
        model.observe({"x": x_val}, cost=true_cost(x_val))

    # Test on 20 held-out samples
    test_x = np.exp(rng.uniform(np.log(1), np.log(100), 20))
    test_configs = [{"x": x_val} for x_val in test_x]
    predictions = model.predict(test_configs)
    true_costs = np.array([true_cost(x_val) for x_val in test_x])

    # Measure MAPE
    mape = np.mean(np.abs((predictions - true_costs) / true_costs))

    # Check monotonicity: predictions should increase with x
    sorted_indices = np.argsort(test_x)
    sorted_preds = predictions[sorted_indices]
    monotonic_violations = np.sum(np.diff(sorted_preds) < 0)

    assert mape < 0.25, f"MAPE should be <25%, got {mape:.3f}"
    assert monotonic_violations < len(sorted_preds) // 4, \
        f"Predictions should be roughly monotonic, got {monotonic_violations} violations"


def test_extrapolation_robustness():
    """Cost model predictions are reasonable when extrapolating."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # True cost function
    def true_cost(x):
        return 1.0 + 9.0 * x

    # Train only on x ∈ [0.2, 0.8]
    rng = np.random.RandomState(42)
    train_x = rng.uniform(0.2, 0.8, 10)
    for x_val in train_x:
        model.observe({"x": x_val}, cost=true_cost(x_val))

    # Test extrapolation at boundaries
    boundary_configs = [{"x": 0.0}, {"x": 1.0}]
    predictions = model.predict(boundary_configs)

    # Predictions should be:
    # 1. Positive and finite
    # 2. Not the default (1.0 exactly)
    # 3. Reasonable (within 2x of true value)
    assert np.all(predictions > 0), f"Predictions must be positive: {predictions}"
    assert np.all(np.isfinite(predictions)), f"Predictions must be finite: {predictions}"
    assert not np.allclose(predictions, 1.0), "Should not return default for extrapolation"

    true_boundary = np.array([true_cost(0.0), true_cost(1.0)])
    ratios = predictions / true_boundary
    # Extrapolation can be less accurate, allow up to 3x
    assert np.all(ratios < 3.0) and np.all(ratios > 0.3), \
        f"Extrapolation should be within 3x of true: {predictions} vs {true_boundary}"


def test_small_sample_behavior():
    """Cost model handles small training sets gracefully."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # Single observation: should return default or that observation
    model.observe({"x": 0.5}, cost=5.0)
    pred = model.predict([{"x": 0.3}])
    assert pred[0] > 0 and np.isfinite(pred[0]), "Single sample should not crash"

    # Two observations: minimum for GP
    model.observe({"x": 0.7}, cost=7.0)
    preds = model.predict([{"x": 0.4}, {"x": 0.6}])

    # Predictions should interpolate reasonably
    assert np.all(preds > 0) and np.all(np.isfinite(preds)), "Two samples should enable GP"
    assert preds[0] < preds[1], "Predictions should reflect training trend"


def test_identical_cost_observations():
    """Cost model handles zero-variance training data."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # All observations have same cost
    for x_val in [0.1, 0.3, 0.5, 0.7, 0.9]:
        model.observe({"x": x_val}, cost=5.0)

    # Predictions should return constant (not crash, not NaN)
    preds = model.predict([{"x": 0.2}, {"x": 0.6}])

    assert np.all(np.isfinite(preds)), f"Should handle zero variance: {preds}"
    assert np.allclose(preds, 5.0, atol=1.0), \
        f"Predictions should be near constant 5.0, got {preds}"


def test_near_zero_costs():
    """Cost model handles very small costs gracefully."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # Observe near-zero costs (valid, but extreme)
    model.observe({"x": 0.1}, cost=0.01)
    model.observe({"x": 0.5}, cost=0.02)
    model.observe({"x": 0.9}, cost=0.05)

    # Predict: should handle log(0.01) gracefully
    preds = model.predict([{"x": 0.3}, {"x": 0.7}])

    assert np.all(preds > 0), f"Predictions must be positive: {preds}"
    assert np.all(np.isfinite(preds)), f"Should handle log(small) gracefully: {preds}"


def test_cost_outliers():
    """Cost model is not dominated by single outlier."""
    space = SearchSpace(knobs=[Knob(name="x", kind="continuous", bounds=(0.0, 1.0))])
    model = CostModelGP(space)

    # Train with one outlier
    model.observe({"x": 0.1}, cost=1.0)
    model.observe({"x": 0.3}, cost=1.1)
    model.observe({"x": 0.5}, cost=50.0)  # Outlier
    model.observe({"x": 0.7}, cost=1.2)
    model.observe({"x": 0.9}, cost=1.3)

    # Predict at outlier location and neighbors
    preds = model.predict([{"x": 0.4}, {"x": 0.5}, {"x": 0.6}])

    # Prediction at x=0.5 may be high, but neighbors should not be dominated
    assert preds[0] < 20.0, f"Neighbor should not be dominated by outlier: {preds[0]}"
    assert preds[2] < 20.0, f"Neighbor should not be dominated by outlier: {preds[2]}"
    assert np.all(np.isfinite(preds)), f"Should handle outliers gracefully: {preds}"
