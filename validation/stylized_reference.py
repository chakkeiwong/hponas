"""Independent analytic and intermediate-output oracles for the finite fixtures.

This module never calls the workload evaluator. Ridge risks use exact rational
arithmetic on the declared binary64 inputs; filter roots use Decimal precision.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
import math
import numpy as np


def _fraction(value):
    return Fraction(float(value))


def reference_value(case, config):
    family = case["family"]
    if family == "ridge":
        n, s = case["n"], _fraction(case["noise_variance"])
        value = Fraction(0)
        for j, variance in enumerate(case["prior_variances"]):
            penalty = _fraction(config[f"lambda_{j}"])
            value += (_fraction(variance)*penalty**2 + n*s)/(n+penalty)**2
        return float(value)
    if family == "quadratic":
        eta = _fraction(config["eta"])
        rho = max(abs(1-eta*_fraction(eigenvalue)) for eigenvalue in case["spectrum"])
        return float(rho**(2*case["iterations"]))
    if family == "filter":
        k = _fraction(config["gain"])
        q, r = _fraction(case["process_variance"]), _fraction(case["observation_variance"])
        return float(((1-k)**2*q + k**2*r)/(k*(2-k)))
    if family == "bottleneck":
        width = config["width"]
        return float(sum(_fraction(s)**2 for s in case["spectrum"][width:])
                     + 8*width*_fraction(case["size_penalty"]))
    raise ValueError("Unknown reference family")


def optimum(case):
    family = case["family"]
    if family == "ridge":
        s = _fraction(case["noise_variance"])
        config = {f"lambda_{j}": float(s/_fraction(t))
                  for j, t in enumerate(case["prior_variances"])}
        minimum = float(sum(s/(case["n"]+s/_fraction(t)) for t in case["prior_variances"]))
    elif family == "quadratic":
        low, high = min(case["spectrum"]), max(case["spectrum"])
        config = {"eta": float(2/(_fraction(low)+_fraction(high)))}
        minimum = float(((_fraction(high)-_fraction(low))/(_fraction(high)+_fraction(low)))
                        **(2*case["iterations"]))
    elif family == "filter":
        with localcontext() as context:
            context.prec = 80
            q = Decimal(str(case["process_variance"]))
            r = Decimal(str(case["observation_variance"]))
            variance = 2*q*r/((q*q+4*q*r).sqrt()+q)
            config = {"gain": float((variance+q)/(variance+q+r))}
            minimum = float(variance)
    elif family == "bottleneck":
        width = min(range(1, 5), key=lambda h: reference_value(case, {"width": h}))
        config = {"width": width}
        minimum = reference_value(case, config)
    else:
        raise ValueError("Unknown reference family")
    return {"config": config, "value": minimum}


def numerical_allowance(case, config, expected):
    """Declared binary64 finite-conformance envelope, not a regret threshold.

    4096 elementary rounding allowances cover these tiny dense operations;
    scale by the ridge normal-equation condition or iteration/spectral factors.
    This is a conservative engineering bound, not an interval-arithmetic proof.
    """
    eps = np.finfo(np.float64).eps
    gamma = 4096*eps/(1-4096*eps)
    if case["family"] == "ridge":
        diagonal = [case["n"]+config[f"lambda_{j}"] for j in range(3)]
        condition = max(diagonal)/min(diagonal)
    elif case["family"] == "quadratic":
        condition = case["iterations"] * max(case["spectrum"])/min(case["spectrum"])
    else:
        condition = 1.0
    return gamma * condition * max(1.0, abs(expected))


def _array(value, shape):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("Malformed or nonfinite numerical payload")
    return result


def _finite_numbers(value):
    if isinstance(value, dict):
        return all(_finite_numbers(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite_numbers(v) for v in value)
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def verify_observation(case, config, observation):
    """Reconstruct model outputs, objective, and work units independently."""
    expected = reference_value(case, config)
    allowed = numerical_allowance(case, config, expected)
    actual = observation["value"]
    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual):
        raise ValueError("Nonfinite or invalid observed objective")
    payload = observation["payload"]
    if not isinstance(payload, dict) or not _finite_numbers(payload):
        raise ValueError("Invalid or nonfinite numerical payload")
    family = case["family"]
    if family == "ridge":
        n, d = case["n"], len(case["prior_variances"])
        dimension = n+d
        # Sylvester signs directly from binary parity, not the workload builder.
        design = np.array([[(-1)**((i & j).bit_count()) for j in range(d)] for i in range(n)])
        points = np.vstack((np.diag(np.full(dimension, math.sqrt(dimension))),
                            -np.diag(np.full(dimension, math.sqrt(dimension)))))
        truth = points[:, :d]*np.sqrt(case["prior_variances"])
        responses = truth @ design.T + points[:, d:]*math.sqrt(case["noise_variance"])
        exact = (responses @ design)/np.array([n+config[f"lambda_{j}"] for j in range(d)])
        coefficients = _array(payload["coefficients"], (2*dimension, d))
        if not np.allclose(coefficients, exact, rtol=allowed, atol=allowed):
            raise ValueError("Ridge coefficients fail independent normal-equation solution")
        reconstructed = float(np.square(coefficients-truth).sum(axis=1).mean())
        work_units = 2*dimension
    elif family == "quadratic":
        rotation = np.array([[1., -2., -2.], [2., 2., -1.], [2., -1., 2.]])/3
        spectrum = (1-config["eta"]*np.array(case["spectrum"]))**case["iterations"]
        exact = rotation @ np.diag(spectrum) @ rotation.T
        propagator = _array(payload["propagator"], (3, 3))
        if not np.allclose(propagator, exact, rtol=allowed, atol=allowed):
            raise ValueError("Quadratic propagator differs from spectral solution")
        reconstructed = float(np.linalg.norm(propagator, 2)**2)
        work_units = case["iterations"]
    elif family == "filter":
        covariance = _array(payload["covariance"], (1,))
        reconstructed = float(covariance[0])
        work_units = 1
    else:
        width = config["width"]
        first = _array(payload["weights_in"], (width, 4))
        second = _array(payload["weights_out"], (4, width))
        signs = np.array([[(-1)**((i & j).bit_count())/2 for j in range(4)] for i in range(4)])
        teacher = sum(s*np.outer(signs[:, j], signs[:, j]) for j, s in enumerate(case["spectrum"]))
        error = float(np.square(second @ first-teacher).sum())
        work_units = first.size+second.size
        if payload["parameter_count"] != work_units or abs(payload["prediction_error"]-error) > allowed:
            raise ValueError("Bottleneck prediction/size receipt is inconsistent")
        reconstructed = error + work_units*case["size_penalty"]
    if type(observation["work_units"]) is not int or observation["work_units"] != work_units:
        raise ValueError("Numerical work accounting differs from fixture")
    if abs(actual-expected) > allowed or abs(actual-reconstructed) > allowed:
        raise ValueError("Observed objective differs from analytic or raw-output reconstruction")
    best = optimum(case)["value"]
    return {"reference_value": expected, "known_minimum": best,
            "regret": expected-best, "absolute_error": abs(actual-expected),
            "numerical_allowance": allowed, "work_units": work_units}
