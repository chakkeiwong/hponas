"""Self-contained numerical tuning models with separately derived references.

Quadratic training, fixed-feature ReLU fitting and exact Gaussian flow expose
actual iterates and outputs. They establish finite-model conformance, not
generic optimizer superiority or acceptance of later statistical campaigns.
"""
from __future__ import annotations

from numbers import Real
import numpy as np


def _real(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError("Finite real coordinate required")
    return float(value)


def quadratic(eta, iterations, checkpoint=None):
    """Actually update a rotated quadratic, charging only newly executed steps."""
    eta = _real(eta)
    if not 0 < eta < 2 / 3:
        raise ValueError("Learning rate must lie in the stable open interval")
    if type(iterations) is not int or not 0 <= iterations <= 8:
        raise ValueError("Fidelity must be an integer in [0, 8]")
    rotation = np.array([[.6, -.8], [.8, .6]])
    hessian = rotation @ np.diag([1., 3.]) @ rotation.T
    state = rotation @ np.array([.1, 1.])
    completed = 0
    if checkpoint is not None:
        fields = {"schema", "case", "eta", "iterations", "state", "gradient_steps"}
        if (not isinstance(checkpoint, dict) or set(checkpoint) != fields
                or checkpoint["schema"] != "quadratic_checkpoint_v1"
                or checkpoint["case"] != "rotated_diag_1_3_initial_0.1_1"
                or _real(checkpoint["eta"]) != eta):
            raise ValueError("Checkpoint identity differs")
        completed = checkpoint["iterations"]
        if (type(completed) is not int or not 0 <= completed <= iterations
                or type(checkpoint["gradient_steps"]) is not int
                or checkpoint["gradient_steps"] != completed
                or not isinstance(checkpoint["state"], list) or len(checkpoint["state"]) != 2):
            raise ValueError("Checkpoint fidelity or work accounting differs")
        state = np.array([_real(x) for x in checkpoint["state"]])
    trace = []
    for index in range(completed, iterations):
        state = state - eta * hessian @ state
        trace.append({"iteration": index + 1, "state": state.tolist(),
                      "value": float(state @ state)})
    return {"value": float(state @ state), "incremental_steps": iterations - completed,
            "trace": trace,
            "checkpoint": {"schema": "quadratic_checkpoint_v1",
                           "case": "rotated_diag_1_3_initial_0.1_1", "eta": eta,
                           "iterations": iterations, "state": state.tolist(),
                           "gradient_steps": iterations}}


def _features(x, knots):
    return np.column_stack([np.ones_like(x), x, *(np.maximum(x - k, 0) for k in knots)])


def _quadrature(order):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    starts = np.arange(8) / 8
    x = (starts[:, None] + (nodes[None, :] + 1) / 16).reshape(-1)
    return x, np.tile(weights / 16, 8)


def _target(x):
    return np.maximum(x - .25, 0) - 2 * np.maximum(x - .5, 0) + np.maximum(x - .75, 0)


def spline(knot_indices):
    """Fit output weights of a real ReLU network with fixed input knots."""
    if (not isinstance(knot_indices, (list, tuple))
            or any(type(i) is not int or not 1 <= i <= 7 for i in knot_indices)
            or list(knot_indices) != sorted(set(knot_indices))):
        raise ValueError("Knots must be a sorted subset of integer indices 1..7")
    knots = np.array(knot_indices) / 8
    x, weights = _quadrature(2)
    design = _features(x, knots)
    coefficients, _, rank, _ = np.linalg.lstsq(
        np.sqrt(weights)[:, None] * design, np.sqrt(weights) * _target(x), rcond=None)
    if rank != len(coefficients):
        raise ValueError("Rank-deficient output fit")
    probes, probe_weights = _quadrature(3)
    predictions = _features(probes, knots) @ coefficients
    error = float(probe_weights @ np.square(predictions - _target(probes)))
    return {"knot_indices": list(knot_indices), "hidden_units": len(knots),
            "fitted_output_count": len(coefficients), "coefficients": coefficients.tolist(),
            "integrated_error": error, "probe_x": probes.tolist(),
            "probe_weights": probe_weights.tolist(), "predictions": predictions.tolist()}


def gaussian_flow(correlation):
    """Exact-flow Gaussian moment dynamics, integrated by degree-five cubature.

The feature transfer matrix is computed from actual transitions of quadrature
points, then its correlation series is summed by a small linear solve.
This is not leapfrog HMC or Monte Carlo sampling-efficiency acceptance.
"""
    c = _real(correlation)
    if not -1 < c < 1:
        raise ValueError("Exact-flow correlation must lie in (-1, 1)")
    nodes = np.array([-np.sqrt(3.), 0., np.sqrt(3.)])
    weights = np.array([1 / 6, 2 / 3, 1 / 6])
    z, momentum = np.meshgrid(nodes, nodes, indexing="ij")
    z, momentum = z.reshape(-1), momentum.reshape(-1)
    joint_weights = np.outer(weights, weights).reshape(-1)
    next_z = c * z + np.sqrt(1 - c * c) * momentum
    before = np.column_stack([z, (z * z - 1) / np.sqrt(2.)])
    after = np.column_stack([next_z, (next_z * next_z - 1) / np.sqrt(2.)])
    covariance = (before.T * joint_weights) @ before
    cross = (before.T * joint_weights) @ after
    transfer = np.linalg.solve(covariance, cross)
    correlation_sum = np.eye(2) + 2 * transfer @ np.linalg.solve(np.eye(2) - transfer, np.eye(2))
    iact = np.diag(correlation_sum)
    return {"correlation": c, "position": z.tolist(), "momentum": momentum.tolist(),
            "joint_weights": joint_weights.tolist(), "next_position": next_z.tolist(),
            "next_moments": [float(joint_weights @ next_z ** k) for k in range(1, 5)],
            "feature_transfer": transfer.tolist(), "iact": iact.tolist(),
            "worst_iact": float(np.max(iact)), "work_units": 9}
