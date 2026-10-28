"""Finite stochastic LQR, exact rational oracle, and full-path scoring.

No learning library, sibling repository, simulation estimate, or fitted
reference is used in this module. Positive costs are minimized.
"""
from dataclasses import asdict, dataclass
from fractions import Fraction
from itertools import product
import math

import numpy as np


@dataclass(frozen=True)
class LQRSpec:
    a: float = .8
    b: float = 1.
    q: float = 1.
    r: float = .1
    terminal_q: float = 1.
    gamma: float = .99
    noise: float = .05
    initial: float = 1.
    action_limit: float = 1.
    horizon: int = 8

    def __post_init__(self):
        if type(self.horizon) is not int or not 1 <= self.horizon <= 12:
            raise ValueError('Enumeration supports integer horizons 1 through 12')
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in asdict(self).values()):
            raise ValueError('Finite real coefficients required')
        if not (0 < self.gamma <= 1 and self.q > 0 and self.r > 0 and self.terminal_q >= 0
                and self.noise >= 0 and self.initial > 0 and self.action_limit > 0 and self.b != 0):
            raise ValueError('Invalid quadratic control contract')

    @property
    def state_bound(self):
        bound = self.initial
        maximum = bound
        for _ in range(self.horizon):
            bound = abs(self.a)*bound + abs(self.b)*self.action_limit + self.noise
            maximum = max(maximum, bound)
        return maximum

    def to_dict(self):
        return asdict(self)


def riccati(spec=LQRSpec()):
    """Floating-point backward dynamic programming for the stated finite horizon."""
    p = np.empty(spec.horizon+1)
    constant = np.zeros(spec.horizon+1)
    k, curvature = np.empty(spec.horizon), np.empty(spec.horizon)
    p[-1] = spec.terminal_q
    for t in reversed(range(spec.horizon)):
        curvature[t] = spec.r + spec.gamma*spec.b**2*p[t+1]
        k[t] = spec.gamma*spec.b*spec.a*p[t+1]/curvature[t]
        p[t] = spec.q + spec.gamma*spec.a**2*p[t+1] - curvature[t]*k[t]**2
        constant[t] = spec.gamma*(constant[t+1] + p[t+1]*spec.noise**2)
    return {'P': p, 'K': k, 'S': curvature, 'constant': constant,
            'optimal_cost': float(p[0]*spec.initial**2+constant[0])}


def rational_reference(spec=LQRSpec()):
    """Independent scalar elimination in exact arithmetic.

    Uses P_t = Q + gamma*A^2*P_next*R/(R+gamma*B^2*P_next),
    avoiding the subtractive floating-point recursion used above.
    The returned rational optimum is exact for the decimal input coefficients.
    """
    f = lambda name: Fraction(str(getattr(spec, name)))
    a, b, q, r, discount = (f(n) for n in ('a', 'b', 'q', 'r', 'gamma'))
    p, c = f('terminal_q'), Fraction(0)
    ps, ks, ss = [p], [], []
    for _ in range(spec.horizon):
        s = r + discount*b*b*p
        gain = discount*b*a*p/s
        c = discount*(c+p*f('noise')**2)
        p = q + discount*a*a*p*r/s
        ps.append(p)
        ks.append(gain)
        ss.append(s)
    optimum = p*f('initial')**2+c
    return {'P': tuple(reversed(ps)), 'K': tuple(reversed(ks)),
            'S': tuple(reversed(ss)), 'constant': c, 'optimal_cost': optimum}


def paths(spec=LQRSpec()):
    """Every equally weighted initial-state/noise realization, in fixed order."""
    signs = np.asarray(list(product((-1., 1.), repeat=spec.horizon+1)))
    return signs[:, 0]*spec.initial, signs[:, 1:]*spec.noise


def numerical_tolerance(spec, magnitude=1.):
    # 256 elementary operations per time step is a conservative allowance for
    # the FP64 polynomial recurrences, averaging and the telescoping identity.
    # Neural inference is treated as a fixed action map; its accuracy is not
    # excused by this tolerance.
    return 256*spec.horizon*np.finfo(np.float64).eps*max(1., abs(float(magnitude)))


def validate_actions(actions, count, spec):
    actions = np.asarray(actions, dtype=np.float64)
    if actions.shape != (count,) or not np.isfinite(actions).all():
        raise ValueError('Policy must return one finite action per state')
    if np.any(np.abs(actions) > spec.action_limit):
        raise ValueError('Policy action outside contract; no silent clipping')
    return actions


def enumerate_policy(policy, spec=LQRSpec()):
    """Evaluate a deterministic, non-anticipating policy on the entire law.

    policy(states, step) sees current states and time only. Noise paths are
    never supplied to it. The finite expectation is exact up to FP64 arithmetic.
    """
    initial, noise = paths(spec)
    ref = riccati(spec)
    count = len(initial)
    states = np.empty((count, spec.horizon+1))
    actions = np.empty((count, spec.horizon))
    states[:, 0] = initial
    costs = np.zeros(count)
    advantages = np.zeros(count)
    for t in range(spec.horizon):
        x = states[:, t]
        u = validate_actions(policy(x.copy(), t), count, spec)
        actions[:, t] = u
        costs += spec.gamma**t*(spec.q*x*x+spec.r*u*u)
        advantages += spec.gamma**t*ref['S'][t]*(u+ref['K'][t]*x)**2
        states[:, t+1] = spec.a*x+spec.b*u+noise[:, t]
    costs += spec.gamma**spec.horizon*spec.terminal_q*states[:, -1]**2
    cost = math.fsum(costs)/count
    excess = math.fsum(advantages)/count
    optimum = float(rational_reference(spec)['optimal_cost'])
    gap = cost-optimum
    tolerance = numerical_tolerance(spec, max(cost, optimum, excess))
    if gap < -tolerance or abs(gap-excess) > tolerance:
        raise ValueError('Cost lower bound or independent performance identity failed')
    return {'cost': cost, 'optimal_cost': optimum, 'gap': gap, 'advantage_gap': excess,
            'identity_error': abs(gap-excess), 'tolerance': tolerance,
            'paths': count, 'states': states, 'actions': actions, 'noise': noise,
            'path_costs': costs, 'path_advantages': advantages}


def oracle_report(spec=LQRSpec()):
    reference = riccati(spec)
    oracle = enumerate_policy(lambda x, t: -reference['K'][t]*x, spec)
    zero = enumerate_policy(lambda x, t: np.zeros_like(x), spec)
    exact = rational_reference(spec)
    return {'spec': spec.to_dict(), 'optimal_cost': oracle['optimal_cost'],
            'zero_action_cost': zero['cost'], 'max_oracle_action': float(np.abs(oracle['actions']).max()),
            'oracle_identity_error': oracle['identity_error'], 'path_count': oracle['paths'],
            'rational_optimum': str(exact['optimal_cost']), 'K': reference['K'].tolist(),
            'P': reference['P'].tolist(), 'S': reference['S'].tolist(),
            'numeric_rational_error': abs(reference['optimal_cost']-float(exact['optimal_cost']))}
