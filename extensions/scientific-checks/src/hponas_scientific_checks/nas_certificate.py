"""Optional interval checker, separately packaged and qualified under SCI-03.

Reuses the reviewed explicit Hessian chain-rule derivation with hardened input,
partition and resource validation. Public scope is deliberately finite.
"""
from fractions import Fraction
import math
import time
from mpmath.ctx_iv import MPIntervalContext
iv = MPIntervalContext()
iv.dps = 50
SCOPE = "2-4-4-1 real-valued SiLU network; exp(-x*a); rectangle [-1/2,1/2] x [1/5,3/5]; dx<=0.12148729268184028, da<=0.0843661754735002; not floating-point inference or unseen models."

def exact_interval(value):
    """Represent JSON binary64 values as exact dyadic interval constants."""
    if isinstance(value, Fraction):
        return iv.mpf(value.numerator) / value.denominator
    if isinstance(value, int):
        return iv.mpf(value)
    if isinstance(value, float):
        numerator, denominator = value.as_integer_ratio()
        return iv.mpf(numerator) / denominator
    raise TypeError(type(value).__name__)


def singleton(value):
    return exact_interval(value)


def coerce_interval(value):
    if isinstance(value, (Fraction, int, float)):
        return exact_interval(value)
    return value


def abs_iv(value):
    return abs(value)


def layers_from_model(model):
    if not isinstance(model, dict) or not isinstance(model.get("config"), dict):
        raise ValueError("Missing model/config")
    cfg = model["config"]
    if (cfg.get("activation") != "silu" or type(cfg.get("depth")) is not int
            or cfg["depth"] != 2 or type(cfg.get("width")) is not int or cfg["width"] != 4):
        raise ValueError("Only the explicit 2-4-4-1 SiLU architecture is supported")
    raw = model.get("layers")
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError("Exactly three affine layers required")
    layers = []
    for layer, nin, nout in zip(raw, (2, 4, 4), (4, 4, 1)):
        if not isinstance(layer, dict):
            raise ValueError("Malformed layer")
        weights, biases = layer.get("weight"), layer.get("bias")
        if (not isinstance(weights, list) or not isinstance(biases, list)
                or len(weights) != nout or len(biases) != nout
                or any(not isinstance(row, list) or len(row) != nin for row in weights)):
            raise ValueError("Layer dimensions do not match contract")
        values = [v for row in weights for v in row] + biases
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("Weights and biases must be finite real constants")
        layers.append(([[exact_interval(v) for v in row] for row in weights],
                       [exact_interval(v) for v in biases]))
    return layers


def add2(a, b):
    return [[a[i][j] + b[i][j] for j in range(2)] for i in range(2)]


def jet(layers, x0, x1):
    """Return output, gradient and 2x2 Hessian intervals.

    The state uses explicit 2x2 Hessian indices.  This is intentionally
    independent of the flattened (xx,xa,aa) representation in SCI-01/ANALYSIS.
    """
    x = [coerce_interval(x0), coerce_interval(x1)]
    grad = [[singleton(1), singleton(0)], [singleton(0), singleton(1)]]
    hess = [[[singleton(0), singleton(0)], [singleton(0), singleton(0)]]
            for _ in range(2)]
    for layer_index, (weights, biases) in enumerate(layers):
        values = []
        next_grad = []
        next_hess = []
        hidden = layer_index < len(layers) - 1
        for weights_row, bias in zip(weights, biases):
            z = bias
            for weight, value in zip(weights_row, x):
                z += weight * value
            dz = [sum((weight * grad[k][axis]
                       for k, weight in enumerate(weights_row)),
                      singleton(0)) for axis in range(2)]
            d2z = [[sum((weight * hess[k][axis][other]
                         for k, weight in enumerate(weights_row)),
                        singleton(0)) for other in range(2)]
                   for axis in range(2)]
            if hidden:
                sig = 1 / (1 + iv.exp(-z))
                first = sig + z * sig * (1 - sig)
                second = sig * (1 - sig) * (2 + z * (1 - 2 * sig))
                values.append(z * sig)
                next_grad.append([first * value for value in dz])
                next_hess.append(
                    [[first * d2z[i][j] + second * dz[i] * dz[j]
                      for j in range(2)] for i in range(2)])
            else:
                values.append(z)
                next_grad.append(dz)
                next_hess.append(d2z)
        x, grad, hess = values, next_grad, next_hess
    return x[0], grad[0], hess[0]


def target_hessian(x, a):
    value = iv.exp(-x * a)
    return [[a * a * value, (a * x - 1) * value],
            [(a * x - 1) * value, x * x * value]]


def rectangle(path):
    bounds = [Fraction(-1, 2), Fraction(1, 2), Fraction(1, 5), Fraction(3, 5)]
    for depth, bit in enumerate(path):
        axis = depth % 2
        midpoint = (bounds[2 * axis] + bounds[2 * axis + 1]) / 2
        if bit == "0":
            bounds[2 * axis + 1] = midpoint
        elif bit == "1":
            bounds[2 * axis] = midpoint
        else:
            raise AssertionError("non-binary partition path")
    return bounds


def derivative_bound(layers, path):
    xlo, xhi, alo, ahi = rectangle(path)
    x = exact_interval(xlo) + (exact_interval(xhi) - exact_interval(xlo)) / 2
    a = exact_interval(alo) + (exact_interval(ahi) - exact_interval(alo)) / 2
    _, centre_grad, _ = jet(layers, (xlo + xhi) / 2, (alo + ahi) / 2)
    centre_target = [-(a * iv.exp(-x * a)), -(x * iv.exp(-x * a))]
    centre_error = [centre_grad[i] - centre_target[i] for i in range(2)]

    x_interval = iv.mpf([exact_interval(xlo).a, exact_interval(xhi).b])
    a_interval = iv.mpf([exact_interval(alo).a, exact_interval(ahi).b])
    _, _, network_hessian = jet(layers, x_interval, a_interval)
    # The target Hessian must be bounded over the full rectangle.  Use a direct
    # interval evaluation at the rectangle, which is independent of the centre.
    target = target_hessian(x_interval, a_interval)
    error_hessian = [[network_hessian[i][j] - target[i][j]
                      for j in range(2)] for i in range(2)]
    rx = exact_interval((xhi - xlo) / 2)
    ra = exact_interval((ahi - alo) / 2)
    bounds = [abs_iv(centre_error[0]) + abs_iv(error_hessian[0][0]) * rx
              + abs_iv(error_hessian[0][1]) * ra,
              abs_iv(centre_error[1]) + abs_iv(error_hessian[1][0]) * rx
              + abs_iv(error_hessian[1][1]) * ra]
    limits = [exact_interval(0.12148729268184028),
              exact_interval(0.0843661754735002)]
    ratios = [bound / limit for bound, limit in zip(bounds, limits)]
    return ratios


def leaves_cover(paths):
    if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= 2048:
        raise ValueError("Partition must contain 1..2048 leaves")
    if any(not isinstance(p, str) or len(p) > 24 or set(p)-set("01") for p in paths):
        raise ValueError("Partition paths must be binary strings of depth <=24")
    leaves = set(paths)
    if len(leaves) != len(paths):
        raise ValueError("Duplicate partition leaves")
    prefixes = {p[:i] for p in paths for i in range(len(p))}
    if leaves & prefixes:
        raise ValueError("Overlapping partition leaves")
    if sum((Fraction(1, 2**len(p)) for p in paths), Fraction()) != 1:
        raise ValueError("Partition has holes")
    return True


def check_certificate(model, paths, *, seconds=120):
    """Recompute the mathematical derivative claim; never trust supplied bounds.

    No training, mesh scoring or inference roundoff guarantee. A NOT_VERIFIED
    result means the chosen partition/resource limit did not prove the bound.
    The function does not infer a counterexample from an interval overestimate.
    """
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 120:
        raise ValueError("Checker seconds must be finite in [0,120]")
    leaves_cover(paths)
    layers = layers_from_model(model)
    start = time.monotonic(); rows = []; unverified = 0
    for path in paths:
        if time.monotonic()-start >= seconds:
            return {"status":"NOT_VERIFIED", "reason":"resource_limit", "checked_leaves":len(rows),
                    "total_leaves":len(paths), "rows":rows, "scope":SCOPE}
        ratios = derivative_bound(layers, path)
        ok = all(r.b <= 1 for r in ratios)
        unverified += not ok
        # Preserve exact outward upper endpoints; floats are presentation only.
        rows.append({"path":path, "proved":ok,
                     "upper_endpoint_mpf":[list(r._mpi_[1]) for r in ratios]})
    return {"status":"CERTIFIED" if not unverified else "NOT_VERIFIED",
            "reason":"all_bounds_proved" if not unverified else "interval_bound_exceeds_limit",
            "checked_leaves":len(rows), "total_leaves":len(paths), "unverified_leaves":unverified,
            "rows":rows, "scope":SCOPE}
