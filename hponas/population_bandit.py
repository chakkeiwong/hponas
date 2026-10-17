"""TV.EXP3.M category selection from PB2-Mix Appendix D, Algorithm 5.

The truncation threshold is solved algebraically. Dependent rounding preserves
inclusion marginals and the exact batch cardinality. Rewards are externally
defined in [0,1]; no outcome-dependent normalization is invented here.
"""
from copy import deepcopy
import math
import random

import numpy as np

from hponas.population import _digest


def inclusion_probabilities(weights, batch, gamma):
    w = np.asarray(weights, dtype=float).copy()
    if (w.ndim != 1 or not 1 <= len(w) <= 64 or not np.isfinite(w).all() or np.any(w <= 0)
            or type(batch) is not int or not 1 <= batch <= len(w)
            or isinstance(gamma, bool) or not math.isfinite(gamma) or not 0 <= gamma <= 1):
        raise ValueError('Invalid finite TV.EXP3.M distribution')
    w /= w.max()
    count = len(w)
    if batch == count:
        # All arms are certain. Clipping to the minimum preserves that law.
        return np.ones(count), np.full(count, w.min()), list(range(count))
    clipped = []
    if gamma < 1:
        eta = (1/batch - gamma/count)/(1-gamma)
        if w.max() >= eta*w.sum():
            ordered = np.sort(w)[::-1]
            for k in range(1, count):
                if 1-eta*k <= 0:
                    continue
                threshold = eta*ordered[k:].sum()/(1-eta*k)
                if ordered[k] <= threshold <= ordered[k-1]:
                    clipped = np.flatnonzero(w >= threshold).tolist()
                    w = np.minimum(w, threshold)
                    break
            else:
                raise ValueError('Cannot resolve probability truncation')
    p = batch*((1-gamma)*w/w.sum() + gamma/count)
    if p.max() > 1+1e-12 or abs(p.sum()-batch) > 1e-12:
        raise ValueError('Truncation did not produce valid inclusion marginals')
    return np.clip(p, 0, 1), w, clipped


def dependent_round(probabilities, generator):
    p = np.asarray(probabilities, dtype=float).copy()
    if (p.ndim != 1 or not 1 <= len(p) <= 64 or not np.isfinite(p).all()
            or np.any(p < 0) or np.any(p > 1)
            or abs(p.sum()-round(float(p.sum()))) > 1e-10):
        raise ValueError('Dependent rounding requires valid integer-sum marginals')
    target = round(float(p.sum()))
    for _ in range(2*len(p)):
        fractional = np.flatnonzero((p > 1e-14) & (p < 1-1e-14))
        if len(fractional) < 2:
            break
        i, j = fractional[:2]
        alpha, beta = min(1-p[i], p[j]), min(p[i], 1-p[j])
        if generator.random() < beta/(alpha+beta):
            p[i] += alpha; p[j] -= alpha
        else:
            p[i] -= beta; p[j] += beta
    selected = np.flatnonzero(p > 0.5).tolist()
    if len(selected) != target:
        raise ValueError('Dependent rounding lost batch cardinality')
    return selected


class TimeVaryingExp3:
    def __init__(self, categories, batch, horizon, *, seed=0, gamma=None, sharing=None):
        if any(type(v) is not int for v in (categories, batch, horizon, seed)):
            raise ValueError('Integer bandit dimensions and seed required')
        if not 1 <= batch <= categories <= 64 or not 1 <= horizon <= 1024 or not 0 <= seed < 2**32:
            raise ValueError('Bandit dimensions exceed the declared finite envelope')
        gamma = min(1.0, math.sqrt(categories*math.log(categories/batch)/((math.e-1)*batch*horizon))) if gamma is None else gamma
        sharing = 1/horizon if sharing is None else sharing
        if isinstance(sharing, bool) or not math.isfinite(sharing) or not 0 <= sharing <= 1:
            raise ValueError('Sharing rate must be in [0,1]')
        inclusion_probabilities([1]*categories, batch, gamma)
        self.options = dict(categories=categories, batch=batch, horizon=horizon, seed=seed,
                            gamma=gamma, sharing=sharing)
        self.weights = np.ones(categories)/categories
        self.history = []
        self.pending = None

    def ask(self):
        if self.pending is not None:
            return deepcopy(self.pending)
        if len(self.history) >= self.options['horizon']:
            raise ValueError('Bandit horizon exhausted')
        p, weights, clipped = inclusion_probabilities(self.weights, self.options['batch'], self.options['gamma'])
        generator = random.Random(f"{self.options['seed']}:{len(self.history)}")
        selected = dependent_round(p, generator)
        self.pending = {'round': len(self.history), 'selected': selected,
                        'probabilities': p.tolist(), 'clipped_weights': weights.tolist(),
                        'clipped': clipped}
        return deepcopy(self.pending)

    def tell(self, rewards):
        if self.pending is None:
            raise ValueError('A pending selection is required')
        if (not isinstance(rewards, dict) or set(rewards) != set(self.pending['selected'])
                or any(type(k) is not int for k in rewards)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       or not 0 <= v <= 1 for v in rewards.values())):
            raise ValueError('Exactly the selected arms need rewards in [0,1]')
        p = np.asarray(self.pending['probabilities'])
        w = np.asarray(self.pending['clipped_weights'])
        shared = math.e*self.options['sharing']*w.sum()/len(w)
        next_weights = w.copy()
        for arm, reward in rewards.items():
            if arm not in self.pending['clipped']:
                next_weights[arm] *= math.exp(self.options['batch']*self.options['gamma']*reward/(len(w)*p[arm]))
        next_weights += shared  # Every arm receives sharing, including unobserved arms.
        self.weights = next_weights/next_weights.sum()
        self.history.append({'selection': deepcopy(self.pending),
                             'rewards': {str(k): float(v) for k, v in rewards.items()}})
        self.pending = None

    def state_dict(self):
        value = {'schema': 'tv_exp3_m_v1', 'options': deepcopy(self.options),
                 'weights': self.weights.tolist(), 'history': deepcopy(self.history),
                 'pending': deepcopy(self.pending)}
        return {'payload': value, 'sha256': _digest(value)}

    def load_state_dict(self, state):
        if not isinstance(state, dict) or set(state) != {'payload', 'sha256'} or _digest(state['payload']) != state['sha256']:
            raise ValueError('Bandit checksum differs')
        value = state['payload']
        if value.get('schema') != 'tv_exp3_m_v1' or value.get('options') != self.options:
            raise ValueError('Bandit identity differs')
        replay = TimeVaryingExp3(**self.options)
        for row in value['history']:
            if replay.ask() != row['selection']:
                raise ValueError('Bandit selection differs from replay')
            replay.tell({int(k): v for k, v in row['rewards'].items()})
        if value['pending'] is not None and replay.ask() != value['pending']:
            raise ValueError('Pending categorical selection differs')
        if replay.state_dict() != state:
            raise ValueError('Bandit weights or journal differs from replay')
        self.weights, self.history, self.pending = replay.weights, replay.history, replay.pending
