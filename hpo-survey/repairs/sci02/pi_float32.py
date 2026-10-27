"""Retained ifBO BarDistribution PI: float32 geometry, double mass reference.

The incumbent is rounded before subtracting it from one. Bin subtraction,
division, clipping and complement are float32, as in pinned upstream code.
Softmax and weighted summation use double for an independent reconstruction;
agreement is numerical under the ORIGINAL 5e-6 absolute PI envelope, not bitwise.
This does not implement FullSupportBarDistribution or pretrained inference.
"""
import math
import numpy as np

PI_ATOL = 5e-6


def probability_of_improvement(logits, borders, incumbent_loss):
    logits, borders = np.asarray(logits), np.asarray(borders)
    if (logits.dtype != np.float32 or borders.dtype != np.float32
            or logits.ndim != 2 or borders.ndim != 1
            or not 1 <= len(logits) <= 10000
            or not 2 <= len(borders) <= 20000
            or logits.shape[1] != len(borders)-1
            or not np.isfinite(logits).all() or not np.isfinite(borders).all()
            or isinstance(incumbent_loss, (bool, np.bool_))
            or not np.isscalar(incumbent_loss)
            or not math.isfinite(float(incumbent_loss))):
        raise ValueError('Unsupported PI shape, dtype or nonfinite input')
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        try:
            widths = np.diff(borders)
            if not np.all(widths > 0):
                raise ValueError('PI borders must be strictly increasing')
            incumbent = np.float32(incumbent_loss)
            best = np.float32(1) - incumbent
            factors = np.float32(1) - np.clip(
                (best - borders[:-1]) / widths, np.float32(0), np.float32(1))
        except FloatingPointError as exc:
            raise ValueError('PI float32 arithmetic overflow') from exc
    z = logits.astype(np.float64)
    mass = np.exp(z - np.max(z, axis=1, keepdims=True))
    mass /= mass.sum(axis=1, keepdims=True)
    return mass @ factors.astype(np.float64)
