"""Independent review of the saved NAS interval-bound candidates.

This is a zero-fit review.  It uses a separate forward-mode value/gradient/
Hessian implementation, exact dyadic representations of the saved binary64
weights, and outward mpmath intervals.  The original analysis output is an
input to the review; it is never edited or trusted for the bound calculation.
"""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

import mpmath as mp

ROOT = Path("/home/ubuntu/workspace/hponas")
BASE = ROOT / "docs/program/evidence/2026-10-25/scientific-gap-trace-01"
ANALYSIS = BASE / "20261025T074605Z-analysis-833abd77"
iv = mp.iv
iv.dps = 50


def read(path):
    return json.loads(Path(path).read_text())


def bind(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


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
    cfg = model["config"]
    if cfg.get("activation") != "silu" or cfg.get("depth") != 2:
        raise AssertionError("review only accepts the pinned two-hidden-layer SiLU recipe")
    layers = []
    for layer in model["layers"]:
        weights = [[exact_interval(float(v)) for v in row]
                   for row in layer["weight"]]
        biases = [exact_interval(float(v)) for v in layer["bias"]]
        if len(weights) != len(biases) or not weights:
            raise AssertionError("malformed layer")
        layers.append((weights, biases))
    if [len(layer[0][0]) for layer in layers] != [2, 4, 4]:
        raise AssertionError("unexpected input widths")
    if [len(layer[0]) for layer in layers] != [4, 4, 1]:
        raise AssertionError("unexpected output widths")
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
    leaves = set(paths)
    if not leaves:
        raise AssertionError("empty partition")
    if any(any(other != path and other.startswith(path)
               for other in leaves) for path in leaves):
        raise AssertionError("overlapping partition leaves")

    def visit(prefix):
        if prefix in leaves:
            return
        descendants = [path for path in leaves if path.startswith(prefix)]
        if not descendants:
            raise AssertionError("partition hole at " + prefix)
        visit(prefix + "0")
        visit(prefix + "1")

    visit("")


def review(out):
    rows = []
    max_ratios = []
    for seed in range(7401, 7407):
        source = ANALYSIS / f"nas-domain-{seed}.json"
        proof = read(source)
        if not proof["complete_partition"] or proof["pending_paths"]:
            raise AssertionError("analysis partition was incomplete")
        confirmation = read(ROOT / proof["source"]["path"])
        layers = layers_from_model(confirmation["model"])
        paths = [leaf["path"] for leaf in proof["leaves"]]
        leaves_cover(paths)
        ratios = []
        for path in paths:
            independent = derivative_bound(layers, path)
            ratios.append(independent)
            if any(ratio.b > 1 for ratio in independent):
                raise AssertionError(f"independent bound fails for {seed}:{path}")
        maximum = max(max(float(ratio.b) for ratio in pair) for pair in ratios)
        max_ratios.append(maximum)
        rows.append({"seed": seed, "leaf_count": len(paths),
                     "independent_max_upper_ratio": maximum,
                     "analysis_max_upper_ratio": max(max(map(float, leaf["upper_limit_ratios"]))
                                                     for leaf in proof["leaves"]),
                     "partition_revalidated": True,
                     "all_leaf_bounds_revalidated": True})

    # Negative controls: a missing leaf is rejected, and a zero network does
    # not pass merely because the partition is syntactically complete.
    full = [leaf["path"] for leaf in read(ANALYSIS / "nas-domain-7401.json")["leaves"]]
    try:
        leaves_cover(full[:-1])
    except AssertionError:
        omitted_leaf_rejected = True
    else:
        omitted_leaf_rejected = False
    zero_layers = [([[exact_interval(0), exact_interval(0)]], [exact_interval(0)])]
    zero_ratios = derivative_bound(zero_layers, full[0])
    zero_network_rejected = any(ratio.b > 1 for ratio in zero_ratios)
    if not omitted_leaf_rejected or not zero_network_rejected:
        raise AssertionError("negative review controls did not reject")

    result = {
        "mechanics_passed": True,
        "scientific_status": "saved_NAS_domain_certificates_independently_reviewed",
        "models_reviewed": 6,
        "rows": rows,
        "maximum_upper_ratio": max(max_ratios),
        "controls": {"omitted_leaf_rejected": omitted_leaf_rejected,
                      "zero_network_rejected": zero_network_rejected},
        "method": "Independent explicit 2x2 Hessian chain rule with exact dyadic saved weights and 50-digit outward intervals; complete partition and negative controls rechecked.",
        "claim": "For each of the six saved binary64 networks, the mathematical SiLU network has both gradient-error suprema below the frozen limits over the rational rectangle [-1/2,1/2] x [1/5,3/5].",
        "limits": {"dx": 0.12148729268184028, "da": 0.0843661754735002},
        "limitations": ["The certificate applies only to the six saved networks and mathematical real-valued SiLU evaluation.",
                        "It does not certify floating-point inference error, unseen seeds, training convergence, or real-bank effectiveness."]
    }
    (out / "nas-review.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    review(Path(sys.argv[1]))
