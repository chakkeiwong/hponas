"""Small, self-contained numerical models with independently known tuning optima.

Only NumPy is needed to evaluate these fixtures. Mathematical references and
acceptance reconstruction live separately in validation.stylized_reference.
"""
from __future__ import annotations

from copy import deepcopy
from numbers import Real
import numpy as np


def case_specs():
    """Return independent copies of the prospectively fixed finite corpus."""
    cases = []
    for suffix, prior, noise in [("a", [.5, 2., 8.], 2.), ("b", [1., 4., 16.], 1.5)]:
        cases.append({"id": f"ridge-{suffix}", "family": "ridge", "n": 8,
                      "prior_variances": prior, "noise_variance": noise,
                      "space": [{"name": f"lambda_{j}", "kind": "continuous",
                                 "bounds": [.001, 100.], "transform": "log"} for j in range(3)]})
    for suffix, spectrum in [("a", [1., 3., 9.]), ("b", [.5, 2., 5.])]:
        cases.append({"id": f"quadratic-{suffix}", "family": "quadratic",
                      "spectrum": spectrum, "iterations": 4,
                      "space": [{"name": "eta", "kind": "continuous",
                                 "bounds": [.001, 3/spectrum[-1]], "transform": "none"}]})
    for suffix, process, observation in [("a", 1., 6.), ("b", .25, 1.)]:
        cases.append({"id": f"filter-{suffix}", "family": "filter",
                      "process_variance": process, "observation_variance": observation,
                      "space": [{"name": "gain", "kind": "continuous",
                                 "bounds": [.01, .99], "transform": "none"}]})
    for suffix, spectrum, penalty in [("a", [4., 2., 1., .5], 1/16),
                                       ("b", [3., 1.5, .75, .25], 1/8)]:
        cases.append({"id": f"bottleneck-{suffix}", "family": "bottleneck",
                      "spectrum": spectrum, "size_penalty": penalty,
                      "space": [{"name": "width", "kind": "ordinal",
                                 "bounds": [1, 4], "transform": "none"}]})
    return cases


def get_case(case_id):
    for case in case_specs():
        if case["id"] == case_id:
            return deepcopy(case)
    raise ValueError(f"Unknown stylized case: {case_id}")


def validate_config(case, config):
    if not isinstance(config, dict) or set(config) != {k["name"] for k in case["space"]}:
        raise ValueError("Configuration fields differ from the fixture")
    for knob in case["space"]:
        value = config[knob["name"]]
        if (isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value)
                or not knob["bounds"][0] <= value <= knob["bounds"][1]):
            raise ValueError("Fixture coordinate is nonfinite or outside its bounds")
        if knob["kind"] == "ordinal" and not isinstance(value, (int, np.integer)):
            raise ValueError("Fixture ordinal must be an integer")


def _hadamard(n):
    result = np.ones((1, 1))
    while len(result) < n:
        result = np.block([[result, result], [result, -result]])
    return result


def evaluate(case_id, config):
    """Compute the actual model and preserve intermediate numerical outputs."""
    case = get_case(case_id)
    validate_config(case, config)
    family = case["family"]
    if family == "ridge":
        n, d = case["n"], len(case["prior_variances"])
        dimension = n+d
        points = np.concatenate([np.eye(dimension), -np.eye(dimension)]) * np.sqrt(dimension)
        beta = points[:, :d] * np.sqrt(case["prior_variances"])
        design = _hadamard(n)[:, :d]
        responses = design @ beta.T + np.sqrt(case["noise_variance"])*points[:, d:].T
        penalties = np.diag([config[f"lambda_{j}"] for j in range(d)])
        coefficients = np.linalg.solve(design.T @ design + penalties, design.T @ responses).T
        value = float(np.square(coefficients-beta).sum(axis=1).mean())
        payload = {"coefficients": coefficients.tolist()}
        work_units = 2*dimension
    elif family == "quadratic":
        rotation = np.array([[1., -2., -2.], [2., 2., -1.], [2., -1., 2.]])/3
        hessian = rotation @ np.diag(case["spectrum"]) @ rotation.T
        errors = np.eye(3)
        for _ in range(case["iterations"]):
            errors -= config["eta"] * hessian @ errors
        value = float(np.linalg.norm(errors, ord=2)**2)
        payload = {"propagator": errors.tolist()}
        work_units = case["iterations"]
    elif family == "filter":
        gain = config["gain"]
        transition = np.array([[1-gain]])
        loading = np.array([[1-gain, -gain]])
        innovation = loading @ np.diag([case["process_variance"],
                                        case["observation_variance"]]) @ loading.T
        covariance = np.linalg.solve(np.eye(1)-np.kron(transition, transition),
                                     innovation.reshape(-1))
        value = float(covariance[0])
        payload = {"covariance": covariance.tolist()}
        work_units = 1
    else:
        width = int(config["width"])
        rotation = _hadamard(4)/2
        teacher = rotation @ np.diag(case["spectrum"]) @ rotation.T
        left, singular, right = np.linalg.svd(teacher, full_matrices=False)
        first = np.sqrt(singular[:width])[:, None] * right[:width]
        second = left[:, :width] * np.sqrt(singular[:width])
        mse = float(np.square(second @ first-teacher).sum())
        count = first.size + second.size
        value = mse + case["size_penalty"]*count
        payload = {"weights_in": first.tolist(), "weights_out": second.tolist(),
                   "prediction_error": mse, "parameter_count": count}
        work_units = count
    return {"value": value, "payload": payload, "work_units": work_units}
