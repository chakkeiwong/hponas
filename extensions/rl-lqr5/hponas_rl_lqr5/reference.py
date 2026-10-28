"""Coupled five-state finite LQR with full finite-law policy evaluation."""
from dataclasses import dataclass
from itertools import product
import math

import numpy as np


@dataclass(frozen=True)
class LQR5Spec:
    horizon: int = 8
    gamma: float = .99
    initial_scale: float = .5
    noise_scale: float = .025
    action_limit: float = 1.

    def __post_init__(self):
        if type(self.horizon) is not int or not 1 <= self.horizon <= 10:
            raise ValueError('Finite-law scoring supports integer horizons 1 through 10')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (self.gamma, self.initial_scale, self.noise_scale, self.action_limit)):
            raise ValueError('Finite numerical specification required')
        if not (0 < self.gamma <= 1 and self.initial_scale > 0
                and self.noise_scale >= 0 and self.action_limit > 0):
            raise ValueError('Invalid LQR5 specification')

    @property
    def A(self):
        return .8*np.eye(5)+.12*np.roll(np.eye(5), 1, axis=0)

    @property
    def B(self):
        return np.eye(5)[:, :1]

    @property
    def Q(self):
        return np.eye(5)

    @property
    def R(self):
        return np.array([[.1]])

    @property
    def noise_vector(self):
        return self.noise_scale*np.array([1., -1., 1., -1., 1.])

    @property
    def state_bound(self):
        value = bound = self.initial_scale
        for _ in range(self.horizon):
            value = np.linalg.norm(self.A, np.inf)*value+self.action_limit+self.noise_scale
            bound = max(bound, value)
        return float(bound)

    def contract(self):
        return {'states': 5, 'actions': 1, 'horizon': self.horizon, 'gamma': self.gamma,
                'A': self.A.tolist(), 'B': self.B.tolist(), 'Q': self.Q.tolist(),
                'terminal_Q': self.Q.tolist(), 'R': self.R.tolist(),
                'initial_scale': self.initial_scale, 'noise_vector': self.noise_vector.tolist(),
                'action_limit': self.action_limit, 'noise_covariance_rank': 1 if self.noise_scale else 0,
                'initial_covariance_rank': 5, 'path_count': 2**(5+self.horizon)}


def riccati(spec=LQR5Spec()):
    a, b, q, r, gamma = spec.A, spec.B, spec.Q, spec.R, spec.gamma
    p = np.empty((spec.horizon+1, 5, 5)); p[-1] = q
    gains = np.empty((spec.horizon, 1, 5))
    curvatures = np.empty((spec.horizon, 1, 1))
    constants = np.zeros(spec.horizon+1)
    w = spec.noise_vector
    for t in reversed(range(spec.horizon)):
        curvatures[t] = r+gamma*b.T@p[t+1]@b
        gains[t] = np.linalg.solve(curvatures[t], gamma*b.T@p[t+1]@a)
        p[t] = q+gamma*a.T@p[t+1]@a-gains[t].T@curvatures[t]@gains[t]
        constants[t] = gamma*(constants[t+1]+w@p[t+1]@w)
    cost = spec.initial_scale**2*np.trace(p[0])+constants[0]
    return {'P': p, 'K': gains, 'S': curvatures, 'constant': constants, 'optimal_cost': float(cost)}


def condensed_reference(spec=LQR5Spec()):
    """Independent block quadratic elimination, without Riccati recursion.

    For each remaining horizon, express all states as F*x+G*U and minimize
    the complete quadratic form in U. First action and Schur complement give
    K and P; known zero-mean noise contributes its value curvature afterward.
    """
    matrices, gains = [], []
    for t in range(spec.horizon):
        n = spec.horizon-t
        f = np.vstack([np.linalg.matrix_power(spec.A, k) for k in range(n+1)])
        g = np.zeros((5*(n+1), n))
        for k in range(1, n+1):
            for j in range(k):
                g[5*k:5*k+5, j:j+1] = np.linalg.matrix_power(spec.A, k-1-j)@spec.B
        discount = np.repeat(spec.gamma**np.arange(n+1), 5)
        weighted_g = discount[:, None]*g
        h = g.T@weighted_g+np.diag(.1*spec.gamma**np.arange(n))
        cross = g.T@(discount[:, None]*f)
        control = np.linalg.solve(h, cross)
        matrices.append(f.T@(discount[:, None]*f)-cross.T@control)
        gains.append(control[0])
    matrices.append(np.eye(5))
    p = np.array(matrices)
    cost = spec.initial_scale**2*np.trace(p[0])+math.fsum(
        spec.gamma**(t+1)*float(spec.noise_vector@p[t+1]@spec.noise_vector)
        for t in range(spec.horizon))
    return {'P': p, 'K': np.asarray(gains)[:, None, :], 'optimal_cost': cost}


def paths(spec=LQR5Spec()):
    signs = np.asarray(list(product((-1., 1.), repeat=5+spec.horizon)))
    return signs[:, :5]*spec.initial_scale, signs[:, 5:, None]*spec.noise_vector


def numerical_tolerance(spec, magnitude):
    return 4096*spec.horizon*np.finfo(np.float64).eps*max(1., abs(float(magnitude)))


def enumerate_policy(policy, spec=LQR5Spec()):
    initial, noise = paths(spec)
    n = len(initial); ref = riccati(spec)
    states = np.empty((n, spec.horizon+1, 5)); states[:, 0] = initial
    actions = np.empty((n, spec.horizon, 1))
    cost = np.zeros(n); gap_sum = np.zeros(n)
    for t in range(spec.horizon):
        x = states[:, t]
        u = np.asarray(policy(x.copy(), t), dtype=np.float64)
        if u.shape != (n, 1) or not np.isfinite(u).all() or np.any(np.abs(u) > spec.action_limit):
            raise ValueError('Policy must return one finite feasible action per five-state row')
        actions[:, t] = u
        cost += spec.gamma**t*(np.square(x).sum(axis=1)+.1*u[:, 0]**2)
        delta = u+x@ref['K'][t].T
        gap_sum += spec.gamma**t*float(ref['S'][t, 0, 0])*delta[:, 0]**2
        states[:, t+1] = x@spec.A.T+u@spec.B.T+noise[:, t]
    cost += spec.gamma**spec.horizon*np.square(states[:, -1]).sum(axis=1)
    mean = math.fsum(cost)/n; advantage = math.fsum(gap_sum)/n
    gap = mean-ref['optimal_cost']; tolerance = numerical_tolerance(spec, max(mean, advantage))
    if gap < -tolerance or abs(gap-advantage) > tolerance:
        raise ValueError('Complete-law cost/performance-difference identity failed')
    return {'cost': mean, 'optimal_cost': ref['optimal_cost'], 'gap': gap,
            'advantage_gap': advantage, 'identity_error': abs(gap-advantage), 'tolerance': tolerance,
            'paths': n, 'states': states, 'actions': actions, 'noise': noise, 'path_costs': cost}


def oracle_report(spec=LQR5Spec()):
    ref = riccati(spec); other = condensed_reference(spec)
    oracle = enumerate_policy(lambda x, t: -x@ref['K'][t].T, spec)
    zero = enumerate_policy(lambda x, t: np.zeros((len(x), 1)), spec)
    controllability = np.hstack([np.linalg.matrix_power(spec.A, i)@spec.B for i in range(5)])
    return {'spec': spec.contract(), 'optimal_cost': ref['optimal_cost'], 'zero_action_cost': zero['cost'],
            'max_oracle_action': float(np.abs(oracle['actions']).max()),
            'controllability_rank': int(np.linalg.matrix_rank(controllability)),
            'condensed_P_error': float(np.max(np.abs(other['P']-ref['P']))),
            'condensed_K_error': float(np.max(np.abs(other['K']-ref['K']))),
            'condensed_cost_error': abs(other['optimal_cost']-ref['optimal_cost']),
            'oracle_identity_error': oracle['identity_error'], 'path_count': oracle['paths'],
            'K': ref['K'].tolist(), 'P': ref['P'].tolist(), 'S': ref['S'].tolist()}
