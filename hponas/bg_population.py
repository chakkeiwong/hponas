"""Contextual temporal trust-region exploration for bounded local BG-PBT.

Architecture coordinates are fixed context during a generation. The numerical
learning-rate coordinate and categorical momentum alternate acquisition steps.
Local-region collapse selects a new center using an auxiliary global GP.
Generation orchestration and architecture proposals use separate state.
"""
from dataclasses import asdict
import math

import numpy as np
from scipy.optimize import minimize_scalar

from hponas.population_gp import TemporalOptions, TemporalPopulationGP


ACTIVATIONS = ['relu', 'tanh', 'elu', 'gelu', 'swish']
NORMALIZATIONS = ['none', 'layer_norm', 'spectral_norm']


class BGPopulationExplorer:
    def __init__(self, *, momenta=(0, 0.25, 0.5), learning_rate_bounds=(0.001, 1.0),
                 increment_bound, beta=1.0, fit_iterations=8, success_tolerance=3,
                 failure_tolerance=10, multiplier=1.5, initial_numeric=0.4,
                 initial_categorical=1.0, minimum_numeric=0.15, minimum_categorical=0.1):
        lo, hi = learning_rate_bounds
        if (not 0 < lo < hi <= 1 or not momenta or len(set(momenta)) != len(momenta)
                or any(isinstance(v, bool) or not math.isfinite(v) or not 0 <= v < 1 for v in momenta)
                or isinstance(increment_bound, bool) or not math.isfinite(increment_bound) or increment_bound <= 0):
            raise ValueError('Explicit valid population search bounds required')
        if (any(type(v) is not int or v < 1 for v in (fit_iterations, success_tolerance, failure_tolerance))
                or fit_iterations > 100 or not 1 < multiplier <= 4
                or not 0 < minimum_numeric <= initial_numeric <= 1
                or not 0 < minimum_categorical <= initial_categorical <= 1
                or not math.isfinite(beta) or beta < 0):
            raise ValueError('Invalid bounded mixed trust-region controls')
        self.contract = {'method': 'bgpbt_local_contextual_tr_v1', 'momenta': list(momenta),
                         'learning_rate_bounds': list(learning_rate_bounds), 'increment_bound': increment_bound,
                         'beta': beta, 'fit_iterations': fit_iterations,
                         'success_tolerance': success_tolerance, 'failure_tolerance': failure_tolerance,
                         'multiplier': multiplier, 'initial_numeric': initial_numeric,
                         'initial_categorical': initial_categorical, 'minimum_numeric': minimum_numeric,
                         'minimum_categorical': minimum_categorical,
                         'reference': 'BG-PBT Appendix B equation 7 and interleaved acquisition',
                         'acquisition': 'four alternating bounded scalar/categorical coordinate updates',
                         'restart': 'auxiliary temporal GP UCB over historical observations'}

    def point(self, time, optimizer, architecture):
        lo, hi = self.contract['learning_rate_bounds']
        lr = optimizer['learning_rate']
        if not lo <= lr <= hi or optimizer['momentum'] not in self.contract['momenta']:
            raise ValueError('Optimizer outside declared BG-PBT space')
        return [time, math.log(lr/lo)/math.log(hi/lo), architecture['width']/512,
                architecture['depth']/4, self.contract['momenta'].index(optimizer['momentum']),
                ACTIVATIONS.index(architecture['activation']), NORMALIZATIONS.index(architecture['normalization'])]

    def plan(self, rounds, scores, snapshot, top, bottom):
        c = self.contract
        x, y = [], []
        for index, row in enumerate(rounds):
            output = scores if index == len(rounds)-1 else row['scores']
            for member, old in row['training_inputs'].items():
                increment = (output[member]-old['score'])/c['increment_bound']
                if not math.isfinite(increment) or abs(increment) > 1+1e-12:
                    raise ValueError('Population gain exceeds declared objective bound')
                x.append(self.point(index, old['optimizer'], old['architecture']))
                y.append(float(increment))
        x, y = np.asarray(x), np.asarray(y)
        if len(x) > 512:
            raise ValueError('Population observation envelope exhausted')
        current = max(scores.values())
        if len(rounds) == 1:
            region = {'numeric': c['initial_numeric'], 'categorical': c['initial_categorical'],
                      'successes': 0, 'failures': 0, 'best': current, 'restarts': 0, 'start_round': 0}
        else:
            region = dict(rounds[-2]['exploration']['region'])
            if current > region['best']:
                region.update(successes=region['successes']+1, failures=0, best=current)
            else:
                region.update(failures=region['failures']+1, successes=0)
            if region['successes'] >= c['success_tolerance']:
                region.update(numeric=min(1, region['numeric']*c['multiplier']),
                              categorical=min(1, region['categorical']*c['multiplier']), successes=0)
            if region['failures'] >= c['failure_tolerance']:
                region.update(numeric=region['numeric']/c['multiplier'],
                              categorical=region['categorical']/c['multiplier'], failures=0)
        restart = None
        if region['numeric'] < c['minimum_numeric'] or region['categorical'] < c['minimum_categorical']:
            global_gp = TemporalPopulationGP([0, 1, 2], [3, 4, 5], TemporalOptions(family='bgpbt')).observe(x, y)
            fit = global_gp.fit(c['fit_iterations'])
            candidates = x.copy(); candidates[:, 0] = len(rounds)
            mean, variance = global_gp.predict(candidates)
            values = mean+np.sqrt(c['beta']*variance)
            chosen = int(np.argmax(values))
            restart = {'index': chosen, 'ucb': values.tolist(), 'center': candidates[chosen].tolist(),
                       'fit': fit, 'gp_options': asdict(global_gp.options)}
            region.update(numeric=c['initial_numeric'], categorical=c['initial_categorical'],
                          successes=0, failures=0, restarts=region['restarts']+1, start_round=len(rounds)-1)
        local = x[:, 0] >= region['start_round']
        gp = TemporalPopulationGP([0, 1, 2], [3, 4, 5], TemporalOptions(family='bgpbt')).observe(x[local], y[local])
        fit = gp.fit(c['fit_iterations'])
        pending, actions, traces = [], [], []
        for i, child in enumerate(bottom):
            parent = top[i % len(top)]
            teacher = snapshot['members'][parent]
            center = self.point(len(rounds), teacher['optimizer'], teacher['architecture'])
            if restart:
                center[1], center[4] = restart['center'][1], restart['center'][4]
            low, high = max(0, center[1]-region['numeric']/2), min(1, center[1]+region['numeric']/2)
            categories = list(range(len(c['momenta']))) if region['categorical'] >= 1 else [int(center[4])]
            point, evaluations = list(center), []
            def ucb(candidate):
                mean, variance = gp.predict([candidate], pending=pending)
                value = float(mean[0]+math.sqrt(c['beta']*variance[0]))
                evaluations.append({'point': list(candidate), 'ucb': value})
                return value
            ucb(point)
            for _ in range(4):
                fixed = list(point)
                def score(coordinate):
                    candidate = list(fixed); candidate[1] = float(coordinate)
                    return -ucb(candidate)
                minimize_scalar(score, bounds=(low, high), method='bounded', options={'maxiter': 24})
                score(low); score(high)
                point = list(max(evaluations, key=lambda row: row['ucb'])['point'])
                for category in categories:
                    candidate = list(point); candidate[4] = category; ucb(candidate)
                point = list(max(evaluations, key=lambda row: row['ucb'])['point'])
            pending.append(point)
            lo, hi = c['learning_rate_bounds']
            actions.append({'event_id': f'pbt:{len(rounds)-1}:exploit:{child}', 'parent': parent, 'child': child,
                            'architecture': teacher['architecture'], 'mode': 'COPY', 'optimizer_policy': 'COPY',
                            'optimizer': {'learning_rate': min(hi, max(lo, lo*(hi/lo)**point[1])),
                                          'momentum': c['momenta'][int(point[4])]}})
            traces.append({'center': center, 'numeric_bounds': [low, high], 'categories': categories,
                           'selected': point, 'evaluations': evaluations})
        return actions, {'region': region, 'restart': restart, 'x': x.tolist(), 'increments': y.tolist(),
                         'local_indices': np.flatnonzero(local).tolist(), 'gp_options': asdict(gp.options),
                         'fit': fit, 'acquisitions': traces}
