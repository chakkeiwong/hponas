"""Finite, inspectable output transforms and noisy acquisition arithmetic."""
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import yeojohnson, yeojohnson_llf


def fit_output_power(values):
    """Fit a monotone Yeo-Johnson power in [-2,2] to observed values only.

    Center and scale are robust preprocessing, not a noise calibration model.
    Constant observations use the identity power. Extreme unrepresentable
    transforms are refused rather than replaced with favorable observations.
    """
    y = np.asarray(values, dtype=float)
    if y.ndim != 1 or not len(y) or not np.isfinite(y).all() or np.max(np.abs(y)) > 1e100:
        raise ValueError('Output power requires a finite bounded observation vector')
    center = float(np.median(y))
    scale = float(np.median(np.abs(y-center)))
    if scale == 0:
        scale = float(np.max(np.abs(y-center))) or 1.
    normalized = (y-center)/scale
    if not np.isfinite(normalized).all() or np.max(np.abs(normalized)) > 1e100:
        raise ValueError('Output dynamic range exceeds the numerical envelope')
    power = 1.
    if np.ptp(normalized) > 0:
        result = minimize_scalar(lambda p: -yeojohnson_llf(p, normalized),
                                 bounds=(-2., 2.), method='bounded',
                                 options={'maxiter': 100, 'xatol': 1e-8})
        if not result.success or not np.isfinite(result.fun):
            raise RuntimeError('Output power fit failed')
        power = float(result.x)
    transformed = yeojohnson(normalized, lmbda=power)
    if not np.isfinite(transformed).all():
        raise ValueError('Output power is not numerically representable')
    return transformed, {'center': center, 'scale': scale, 'power': power}


def noisy_ensemble(draws, mean, covariance, baseline_count, exploration=2.):
    """Maximization scores: joint noisy EI, joint noisy PI and latent UCB.

    Every draw compares candidates with that draw's best latent baseline.
    Observation noise enters GP conditioning. These finite posterior averages
    are approximations, not estimates with a claimed error or coverage bound.
    """
    samples = np.asarray(draws, dtype=float)
    mu, cov = np.asarray(mean, dtype=float), np.asarray(covariance, dtype=float)
    if (samples.ndim != 2 or not len(samples) or mu.shape != (samples.shape[1],)
            or cov.shape != (len(mu), len(mu)) or type(baseline_count) is not int
            or not 0 < baseline_count < len(mu) or not np.isfinite(samples).all()
            or not np.isfinite(mu).all() or not np.isfinite(cov).all()
            or not np.isfinite(exploration) or exploration < 0
            or np.any(np.diag(cov) < 0)):
        raise ValueError('Invalid joint posterior ensemble inputs')
    improvement = samples[:, baseline_count:] - samples[:, :baseline_count].max(axis=1)[:, None]
    return np.column_stack((np.maximum(improvement, 0).mean(axis=0),
        (improvement > 0).mean(axis=0),
        mu[baseline_count:] + exploration*np.sqrt(np.diag(cov)[baseline_count:])))


def nondominated_indices(scores):
    values = np.asarray(scores, dtype=float)
    if values.ndim != 2 or not values.shape[0] or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError('Ensemble requires three finite acquisition scores')
    return np.array([i for i, row in enumerate(values)
        if not np.any(np.all(values >= row, axis=1) & np.any(values > row, axis=1))], dtype=int)
