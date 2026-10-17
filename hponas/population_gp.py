"""Reference temporal GPs for population increments, with pending variance.

PB2-Mix equation (5) and BG-PBT equation (7) are distinct kernels. Inputs must
already use the declared numerical scale; categorical coordinates are codes.
The finite candidate maximizer is a diagnostic control, not continuous global
acquisition optimization or a complete population method.
"""
from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize


@dataclass(frozen=True)
class TemporalOptions:
    family: str = 'pb2_mix'
    length: float = 0.5
    categorical_length: float = 1.0
    decay: float = 0.1
    mixture: float = 0.5
    amplitude: float = 1.0
    noise: float = 0.001

    def __post_init__(self):
        if self.family not in {'pb2_mix', 'bgpbt'}:
            raise ValueError('Unknown population kernel reference')
        values = asdict(self)
        for name, value in values.items():
            if name == 'family':
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Finite kernel parameters required')
        if (min(self.length, self.categorical_length, self.amplitude, self.noise) <= 0
                or not 0 <= self.decay <= 1 or not 0 <= self.mixture <= 1):
            raise ValueError('Invalid temporal kernel parameters')


def _points(points, dimensions):
    x = np.asarray(points, dtype=float)
    if (x.ndim != 2 or x.shape[1] != dimensions + 1 or not np.isfinite(x).all()
            or len(x) > 512 or np.any(x[:, 0] < 0)):
        raise ValueError('Points must be bounded finite rows: time then coordinates')
    return x


class TemporalPopulationGP:
    def __init__(self, numeric, categorical, options=None):
        if (not isinstance(numeric, (list, tuple)) or not isinstance(categorical, (list, tuple))
                or any(type(i) is not int for i in [*numeric, *categorical])):
            raise ValueError('Explicit typed coordinate indices required')
        self.numeric, self.categorical = tuple(numeric), tuple(categorical)
        self.dimensions = len(numeric) + len(categorical)
        if not 1 <= self.dimensions <= 32 or sorted([*numeric, *categorical]) != list(range(self.dimensions)):
            raise ValueError('Typed indices must partition the coordinates')
        self.options = options or TemporalOptions()
        if not isinstance(self.options, TemporalOptions):
            raise ValueError('TemporalOptions required')
        self.x = np.empty((0, self.dimensions+1))
        self.y = np.empty(0)
        self.fit_receipt = None

    def kernel(self, left, right, options=None):
        a, b = _points(left, self.dimensions), _points(right, self.dimensions)
        o = self.options if options is None else options
        for data in (a, b):
            if self.categorical and np.any(data[:, [i+1 for i in self.categorical]] % 1 != 0):
                raise ValueError('Categorical coordinates must be integer codes')
        delta_t = np.abs(a[:, None, 0] - b[None, :, 0])
        temporal = ((delta_t == 0).astype(float) if o.decay == 1
                    else np.exp(0.5 * delta_t * np.log1p(-o.decay)))
        if self.numeric:
            indices = [i+1 for i in self.numeric]
            distance2 = np.square((a[:, None, indices] - b[None, :, indices])/o.length).sum(-1)
            if o.family == 'pb2_mix':
                numeric = np.exp(-distance2/2)
            else:
                distance = np.sqrt(5*distance2)
                numeric = (1+distance+5*distance2/3)*np.exp(-distance)
        if self.categorical:
            indices = [i+1 for i in self.categorical]
            matches = (a[:, None, indices] == b[None, :, indices]).mean(-1)
            category = matches if o.family == 'pb2_mix' else np.exp(matches/o.categorical_length)
        if not self.categorical:
            result = numeric * temporal
        elif not self.numeric:
            result = category * temporal
        elif o.family == 'pb2_mix':
            # Eq. (5) defines BOTH component kernels with temporal decay.
            nx, hc = numeric*temporal, category*temporal
            result = (1-o.mixture)*(nx+hc)+o.mixture*nx*hc
        else:
            result = (numeric+category+numeric*category)*temporal/2
        return o.amplitude * result

    def observe(self, points, increments):
        x = _points(points, self.dimensions)
        y = np.asarray(increments, dtype=float)
        if y.shape != (len(x),) or not np.isfinite(y).all() or not len(x):
            raise ValueError('Each observation needs a finite performance increment')
        self.kernel(x, x)
        self.x, self.y = x.copy(), y.copy()
        return self

    def _factor(self, x, options=None):
        o = self.options if options is None else options
        covariance = self.kernel(x, x, o) + o.noise * np.eye(len(x))
        return cho_factor(covariance, lower=True, check_finite=True)

    def predict(self, query, *, pending=()):
        query = _points(query, self.dimensions)
        mean = np.zeros(len(query))
        if len(self.x):
            cross = self.kernel(query, self.x)
            mean = cross @ cho_solve(self._factor(self.x), self.y)
        pending = np.asarray(pending, dtype=float)
        if not pending.size:
            pending = np.empty((0, self.dimensions+1))
        pending = _points(pending, self.dimensions)
        conditioned = np.vstack([self.x, pending])
        if len(conditioned) > 512:
            raise ValueError('Observed plus pending points exceed the finite envelope')
        variance = np.diag(self.kernel(query, query)).copy()
        if len(conditioned):
            cross = self.kernel(query, conditioned)
            variance -= np.einsum('ij,ji->i', cross, cho_solve(self._factor(conditioned), cross.T))
        if np.any(variance < -1e-8) or not np.isfinite(variance).all():
            raise ValueError('Invalid posterior variance')
        return mean, np.maximum(variance, 0)

    def suggest_finite(self, candidates, count=1, *, beta=1.0, pending=()):
        candidates = _points(candidates, self.dimensions)
        if type(count) is not int or not 1 <= count <= len(candidates):
            raise ValueError('Invalid finite batch size')
        if isinstance(beta, bool) or not math.isfinite(beta) or beta < 0:
            raise ValueError('UCB beta must be finite and nonnegative')
        rows = [tuple(row) for row in candidates]
        if len(set(rows)) != len(rows):
            raise ValueError('Duplicate finite candidates')
        pending = [list(row) for row in pending]
        selected = []
        for _ in range(count):
            mean, variance = self.predict(candidates, pending=pending)
            score = mean + math.sqrt(beta)*np.sqrt(variance)
            score[selected] = -np.inf
            index = int(np.argmax(score))
            selected.append(index)
            pending.append(candidates[index].tolist())
        return selected

    def fit(self, max_iterations=30):
        """Bounded marginal-likelihood fit; retain optimizer status honestly."""
        if not len(self.x) or type(max_iterations) is not int or not 1 <= max_iterations <= 100:
            raise ValueError('Observed data and a bounded iteration limit are required')
        previous = self.options
        def options(values):
            return TemporalOptions(previous.family, np.exp(values[0]), previous.categorical_length,
                                   values[1], values[2], np.exp(values[3]), np.exp(values[4]))
        def nll(values):
            o = options(values)
            factor = self._factor(self.x, o)
            return float(0.5*self.y@cho_solve(factor, self.y)
                         + np.log(np.diag(factor[0])).sum() + len(self.y)*np.log(2*np.pi)/2)
        start = [math.log(previous.length), previous.decay, previous.mixture,
                 math.log(previous.amplitude), math.log(previous.noise)]
        initial = nll(start)
        result = minimize(nll, start, method='L-BFGS-B',
                          bounds=[(-4, 3), (0, 1-1e-9), (0, 1), (-8, 5), (-14, 0)],
                          options={'maxiter': max_iterations, 'maxfun': 1200})
        if np.isfinite(result.fun) and result.fun <= initial:
            self.options = options(result.x)
        self.fit_receipt = {'success': bool(result.success), 'message': str(result.message),
                            'evaluations': int(result.nfev), 'initial_nll': initial,
                            'final_nll': float(result.fun), 'adopted': self.options != previous}
        return self.fit_receipt.copy()
