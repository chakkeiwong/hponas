"""Completed lognormal densities and noninformative timeout survival likelihoods."""
import math

import numpy as np
from scipy.special import erfcx, log_ndtr


def array(value, label):
    raw = np.asarray(value)
    if raw.dtype.kind not in "fiu":
        raise ValueError(label + " must contain real numbers, not booleans or strings")
    result = raw.astype(float, copy=True)
    if not np.isfinite(result).all():
        raise ValueError(label + " must be finite")
    return result


def scalar(value, label, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(label + " must be real")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(label + " must be finite" + (" and positive" if positive else ""))
    return result


def normal_tail(z):
    """Log survival, hazard and negative second derivative in standard units."""
    z = array(z, "standardized threshold")
    survival = log_ndtr(-z)
    hazard = np.empty_like(z)
    positive = z >= 0
    hazard[positive] = math.sqrt(2 / math.pi) / erfcx(z[positive] / math.sqrt(2))
    hazard[~positive] = np.exp(-z[~positive] ** 2 / 2 - math.log(2 * math.pi) / 2 - survival[~positive])
    curvature = hazard * (hazard - z)
    # Avoid subtracting indistinguishable large floating point numbers.
    far = z > 1e4
    t = 1 / z[far]
    hazard[far] = z[far] + t - 2 * t**3 + 10 * t**5 - 74 * t**7
    curvature[far] = 1 - t**2 + 6 * t**4 - 50 * t**6
    if (not np.isfinite(survival).all() or not np.isfinite(hazard).all()
            or not np.isfinite(curvature).all() or (curvature < -1e-12).any()
            or (curvature > 1 + 1e-10).any()):
        raise ArithmeticError("Unrepresentable Gaussian tail")
    return survival, hazard, np.clip(curvature, 0, 1)


def event_arrays(events):
    logs, noises, censored = [], [], []
    for event in events:
        if not isinstance(event, dict) or set(event) != {"kind", "elapsed", "noise_variance"}:
            raise ValueError("An observation needs kind, elapsed and noise_variance")
        if event["kind"] not in ("complete", "timeout"):
            raise ValueError("Unsupported event; censor mechanism needs separate treatment")
        logs.append(math.log(scalar(event["elapsed"], "elapsed", positive=True)))
        noises.append(scalar(event["noise_variance"], "noise variance", positive=True))
        censored.append(event["kind"] == "timeout")
    return np.array(logs), np.array(noises), np.array(censored, dtype=bool)


def likelihood(eta, events):
    """Log likelihood, its eta gradient and negative eta Hessian diagonal."""
    eta = array(eta, "observation mean")
    logs, noise, censored = event_arrays(events)
    if eta.shape != logs.shape:
        raise ValueError("Observation means and records differ")
    residual = logs - eta
    terms = -(residual**2 / noise + np.log(2 * math.pi * noise)) / 2 - logs
    score = residual / noise
    precision = 1 / noise
    if censored.any():
        log_sf, hazard, curvature = normal_tail(residual[censored] / np.sqrt(noise[censored]))
        terms[censored] = log_sf
        score[censored] = hazard / np.sqrt(noise[censored])
        precision[censored] = curvature / noise[censored]
    if not all(np.isfinite(v).all() for v in [terms, score, precision]):
        raise ArithmeticError("Unrepresentable observation likelihood")
    return float(terms.sum()), score, precision

