"""Gaussian exponential-tilt cost moments with bounded numerical integration.

This backend supports at most 32 noninformative timeouts. It does
not replace a censored posterior by a Gaussian. Quadrature/QMC errors are
numerical estimates, not proven probability bounds. Hyperparameters are fixed.
"""
from copy import deepcopy
import math

import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import log_ndtr

from hponas.cost_likelihood import array, event_arrays, scalar
from scipy.stats import _qmvnt
import torch


def log_survival(mean, covariance, lower, tolerance=2e-6):
    mean = array(mean, "censor means")
    covariance = array(covariance, "censor covariance")
    lower = array(lower, "censor bounds")
    tolerance = scalar(tolerance, "quadrature tolerance", positive=True)
    n = mean.size
    if mean.shape != (n,) or lower.shape != (n,) or covariance.shape != (n, n) or n > 32:
        raise ValueError("The numerical envelope supports zero through 32 censor events")
    if n == 0:
        return {"log_probability": 0., "quadrature_relative_error_estimate": 0.}
    if not np.allclose(covariance, covariance.T, rtol=0, atol=1e-12):
        raise ValueError("Asymmetric censor covariance")
    if np.linalg.eigvalsh(covariance).min() <= 0:
        raise ValueError("Censor covariance must be positive definite")
    z = (lower - mean) / np.sqrt(np.diag(covariance))
    if n == 1:
        value = float(log_ndtr(-z[0]))
        if not math.isfinite(value):
            raise ArithmeticError("Unrepresentable univariate censor probability")
        return {"log_probability": value, "quadrature_relative_error_estimate": 0.}
    if n >= 3:
        # Independent randomized lattice batches supply an error ESTIMATE. The
        # local fixed seeds make recovery deterministic and isolate global RNG.
        # The exact moment identity is distinct from numerical integration error.
        used = 0
        for count in (4096, 16384, 65536, 262144, 1048576):
            probability, error, actual = _qmvnt._qmvn(count, covariance, lower-mean,
                np.full(n, np.inf), np.random.default_rng(1729), n_batches=16)
            used += actual
            if (math.isfinite(probability) and 0 < probability <= 1
                    and math.isfinite(error) and 0 <= error <= tolerance*probability):
                return {"log_probability": math.log(probability),
                        "quadrature_relative_error_estimate": float(error/probability),
                        "integration": "Genz randomized lattice; 16 batches; fixed local seed 1729",
                        "samples": int(used), "error_is_rigorous_bound": False}
        raise ArithmeticError("Censor probability unresolved within bounded QMC precision budget")
    rho = covariance[0, 1] / math.sqrt(covariance[0, 0] * covariance[1, 1])
    if abs(rho) > .98 or np.max(np.abs(z)) > 12:
        raise ValueError("Bivariate reference outside declared numerical domain")
    if rho == 0:
        return {"log_probability": float(log_ndtr(-z).sum()), "quadrature_relative_error_estimate": 0.}
    # The rarer marginal supplies the outer integration variable. The
    # integrand is log-concave; scale at its constrained mode to avoid tiny
    # unscaled tail integrals being mistaken for accurate zero probabilities.
    za, zb = sorted(z, reverse=True)
    residual_sd = math.sqrt(1 - rho**2)

    def log_integrand(t):
        return -t*t/2 - math.log(2*math.pi)/2 + float(log_ndtr(-(zb - rho*t) / residual_sd))

    optimum = minimize_scalar(lambda t: -log_integrand(t), bounds=(za, max(za + 1, 20.)), method="bounded")
    if not optimum.success:
        raise RuntimeError("Censor integral scale search failed")
    shift = max(log_integrand(za), log_integrand(optimum.x))
    value, error = quad(lambda t: math.exp(log_integrand(t) - shift), za, math.inf,
                        epsabs=tolerance, epsrel=tolerance, limit=200)
    if not math.isfinite(value) or value <= 0 or error / value > 10 * tolerance:
        raise ArithmeticError("Censor probability quadrature did not resolve its tolerance")
    logp = math.log(value) + shift
    if logp > 1e-12:
        raise ArithmeticError("Censor probability exceeds one")
    return {"log_probability": min(0., logp), "quadrature_relative_error_estimate": error/value}


class GaussianCensoredCost:
    """Gaussian conditioning plus censor survival; no Laplace posterior."""

    def __init__(self, mean, covariance, design, events):
        self.mean = array(mean, "mean")
        self.covariance = array(covariance, "covariance")
        self.design = array(design, "design")
        self.events = deepcopy(events)
        self.logs, self.noise, self.censored = event_arrays(events)
        n = self.mean.size
        if not 1 <= n <= 128 or self.mean.shape != (n,) or len(events) > 512:
            raise ValueError("Invalid finite model dimensions")
        if len(events) == 0 and self.design.size == 0:
            self.design = self.design.reshape(0, n)
        if self.covariance.shape != (n, n) or self.design.shape != (len(events), n):
            raise ValueError("Model dimensions differ")
        if (not np.allclose(self.covariance, self.covariance.T, rtol=0, atol=1e-12)
                or np.linalg.eigvalsh(self.covariance).min() <= 0):
            raise ValueError("Prior covariance must be symmetric and positive definite")
        if self.censored.sum() > 32:
            raise ValueError("More than 32 timeout events exceed the bounded inference envelope")
        self.completed = ~self.censored
        obs_means = self.design @ self.mean
        obs_covariance = self.design @ self.covariance @ self.design.T + np.diag(self.noise)
        self._complete_mean = obs_means[self.completed]
        self._complete_covariance = obs_covariance[np.ix_(self.completed, self.completed)]
        self._censor_mean = obs_means[self.censored]
        self._censor_covariance = obs_covariance[np.ix_(self.censored, self.censored)]
        self._censor_complete = obs_covariance[np.ix_(self.censored, self.completed)]
        if self.completed.any():
            solve = np.linalg.solve(self._complete_covariance, self._censor_complete.T)
            self._censor_mean = self._censor_mean + solve.T @ (self.logs[self.completed] - self._complete_mean)
            self._censor_covariance = self._censor_covariance - self._censor_complete @ solve
        self._denominator = log_survival(self._censor_mean, self._censor_covariance, self.logs[self.censored])

    def predict(self, mean, covariance, cross_covariance, noise_variance=0., tolerance=2e-6):
        mean = array(mean, "prediction mean")
        covariance = array(covariance, "prediction covariance")
        cross = array(cross_covariance, "cross covariance")
        noise = scalar(noise_variance, "prediction noise")
        q = mean.size
        if (q < 1 or mean.shape != (q,) or covariance.shape != (q, q)
                or cross.shape != (self.mean.size, q) or noise < 0):
            raise ValueError("Prediction dimensions or noise differ")
        if not np.allclose(covariance, covariance.T, rtol=0, atol=1e-12):
            raise ValueError("Prediction covariance is asymmetric")
        residual = covariance - cross.T @ np.linalg.solve(self.covariance, cross)
        if np.linalg.eigvalsh(residual).min() < -1e-10:
            raise ValueError("Invalid joint prediction covariance")
        obs_cross = self.design @ cross
        censor_cross = obs_cross[self.censored]
        if self.completed.any():
            solve = np.linalg.solve(self._complete_covariance, obs_cross[self.completed])
            mean = mean + solve.T @ (self.logs[self.completed] - self._complete_mean)
            covariance = covariance - obs_cross[self.completed].T @ solve
            censor_cross = censor_cross - self._censor_complete @ solve
        variance = np.maximum(np.diag(covariance), 0) + noise
        denom = log_survival(self._censor_mean, self._censor_covariance, self.logs[self.censored], tolerance)
        moments, errors = [], []
        for power in (1, 2):
            numerator = [log_survival(self._censor_mean + power * censor_cross[:, j], self._censor_covariance,
                                      self.logs[self.censored], tolerance) for j in range(q)]
            moments.append(power * mean + .5 * power**2 * variance
                           + np.array([p["log_probability"] for p in numerator]) - denom["log_probability"])
            errors.append([p["quadrature_relative_error_estimate"] + denom["quadrature_relative_error_estimate"] for p in numerator])
        log_first, log_second = moments
        ratio_log = log_second - 2 * log_first
        if np.min(ratio_log) < -1e-9:
            raise ArithmeticError("Second cost moment is smaller than squared mean")
        # Variance/mean^2 is well-defined and avoids unnecessarily exponentiating
        # a large duration mean. Zero variance remains exactly representable.
        cv_squared = np.expm1(np.maximum(ratio_log, 0))
        if not np.isfinite(cv_squared).all():
            raise ArithmeticError("Unrepresentable cost variance")
        return {"log_expected_cost": log_first, "log_second_moment": log_second,
                "cost_cv_squared": cv_squared, "quadrature_relative_error_estimates": errors,
                "inference": "Gaussian exponential tilt with numerical orthant integration",
                "numerical_error_estimates_are_rigorous_bounds": False,
                "censor_count": int(self.censored.sum()), "posterior_gaussian_approximation": False}

    def state_dict(self):
        return {'schema': 'gaussian_censored_cost_v1', 'mean': self.mean.tolist(),
                'covariance': self.covariance.tolist(), 'design': self.design.tolist(),
                'events': deepcopy(self.events)}

    @classmethod
    def from_state(cls, state):
        if (type(state) is not dict or set(state) != {'schema', 'mean', 'covariance', 'design', 'events'}
                or state['schema'] != 'gaussian_censored_cost_v1'):
            raise ValueError('Invalid censored cost model state')
        return cls(state['mean'], state['covariance'], state['design'], state['events'])

    def predict_torch(self, mean, covariance, cross_covariance, *, noise_variance=0., tolerance=2e-6):
        """Differentiable exponential moments for candidate mean/covariance/cross.

        Training parameters stay fixed during acquisition. Censor-mean
        derivatives use Gaussian boundary densities and conditional orthants;
        they do not differentiate random quadrature iterations or use finite
        differences. The same bounded numerical precision rules apply.
        """
        if not all(isinstance(x, torch.Tensor) and x.dtype == torch.double and x.device.type == 'cpu'
                   for x in [mean, covariance, cross_covariance]):
            raise ValueError('CPU float64 prediction tensors required')
        noise_variance = scalar(noise_variance, 'prediction noise')
        q = mean.numel()
        if (noise_variance < 0 or mean.shape != (q,) or q < 1 or covariance.shape != (q, q)
                or cross_covariance.shape != (self.mean.size, q)
                or not all(torch.isfinite(x).all() for x in [mean, covariance, cross_covariance])):
            raise ValueError('Prediction dimensions, noise or numerical values differ')
        tensor = lambda v: torch.as_tensor(v, dtype=torch.double)
        prior = tensor(self.covariance)
        if not torch.allclose(covariance, covariance.T, rtol=0, atol=1e-12):
            raise ValueError('Prediction covariance is asymmetric')
        residual = covariance-cross_covariance.T@torch.linalg.solve(prior, cross_covariance)
        if float(torch.linalg.eigvalsh(residual.detach()).min()) < -1e-10:
            raise ValueError('Invalid joint prediction covariance')
        obs_cross = tensor(self.design)@cross_covariance
        censor_cross = obs_cross[self.censored]
        if self.completed.any():
            solved = torch.linalg.solve(tensor(self._complete_covariance), obs_cross[self.completed])
            mean = mean+solved.T@tensor(self.logs[self.completed]-self._complete_mean)
            covariance = covariance-obs_cross[self.completed].T@solved
            censor_cross = censor_cross-tensor(self._censor_complete)@solved
        variance = torch.diag(covariance).clamp_min(0)+noise_variance
        denominator = log_survival(self._censor_mean, self._censor_covariance, self.logs[self.censored], tolerance)
        moments = []
        for power in (1, 2):
            numerators = torch.stack([_LogSurvival.apply(tensor(self._censor_mean)+power*censor_cross[:, j],
                tensor(self._censor_covariance), tensor(self.logs[self.censored]), tolerance) for j in range(q)])
            moments.append(power*mean+.5*power**2*variance+numerators-denominator['log_probability'])
        return {'log_expected_cost': moments[0], 'log_second_moment': moments[1]}


def log_survival_mean_gradient(mean, covariance, lower, tolerance=2e-6):
    """d log P(Y>=lower)/d mean from each Gaussian boundary conditional."""
    mean, covariance, lower = array(mean, 'mean'), array(covariance, 'covariance'), array(lower, 'lower')
    probability = log_survival(mean, covariance, lower, tolerance)['log_probability']
    gradient = []
    for j in range(len(mean)):
        remaining = [i for i in range(len(mean)) if i != j]
        sd = math.sqrt(covariance[j, j])
        z = (lower[j]-mean[j])/sd
        cross = covariance[remaining, j]
        conditional_mean = mean[remaining]+cross*(lower[j]-mean[j])/covariance[j, j]
        conditional_covariance = covariance[np.ix_(remaining, remaining)]-np.outer(cross, cross)/covariance[j, j]
        conditional = log_survival(conditional_mean, conditional_covariance, lower[remaining], tolerance)
        log_gradient = -z*z/2-math.log(sd)-math.log(2*math.pi)/2+conditional['log_probability']-probability
        gradient.append(math.exp(log_gradient))
    return np.array(gradient)


class _LogSurvival(torch.autograd.Function):
    @staticmethod
    def forward(ctx, mean, covariance, lower, tolerance):
        if covariance.requires_grad or lower.requires_grad:
            raise ValueError('Acquisition gradients require fixed training covariance and censor bounds')
        arrays = [value.detach().numpy() for value in [mean, covariance, lower]]
        result = log_survival(*arrays, tolerance)
        if ctx.needs_input_grad[0]:
            gradient = log_survival_mean_gradient(*arrays, tolerance)
            ctx.save_for_backward(torch.tensor(gradient, dtype=mean.dtype))
        return mean.new_tensor(result['log_probability'])

    @staticmethod
    def backward(ctx, upstream):
        gradient, = ctx.saved_tensors
        return upstream*gradient, None, None, None
