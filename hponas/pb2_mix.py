"""PB2-Mix exploration for the local finite-MDP population contract.

Categories select momentum, continuous search selects learning rate. Past
performance increments train the time-varying mixed GP. Each proposed category
receives feedback only after its actual training interval. Continuous UCB is
optimized with a bounded scalar solver plus both boundaries. Model fit status
and acquisition evaluations are retained; no global optimum is promised.
"""
from dataclasses import asdict
import math

import numpy as np
from scipy.optimize import minimize_scalar

from hponas.population_bandit import TimeVaryingExp3
from hponas.population_gp import TemporalOptions, TemporalPopulationGP


class PB2MixExplorer:
    def __init__(self, *, momenta=(0.0, 0.25, 0.5), learning_rate_bounds=(0.001, 1.0),
                 increment_bound, horizon=32, seed=0, beta=1.0, fit_iterations=8):
        if (not momenta or len(set(momenta)) != len(momenta)
                or any(isinstance(v, bool) or not math.isfinite(v) or not 0 <= v < 1 for v in momenta)):
            raise ValueError('Distinct categorical momentum choices in [0,1) required')
        lo, hi = learning_rate_bounds
        if not 0 < lo < hi <= 1 or not math.isfinite(increment_bound) or increment_bound <= 0:
            raise ValueError('Declared learning-rate and gain bounds required')
        if type(fit_iterations) is not int or not 1 <= fit_iterations <= 100:
            raise ValueError('Bounded fit iterations required')
        if not math.isfinite(beta) or beta < 0:
            raise ValueError('Nonnegative UCB beta required')
        TimeVaryingExp3(len(momenta), 1, horizon, seed=seed)
        self.contract = {'method': 'pb2_mix_local_temporal_v1', 'momenta': list(momenta),
                         'learning_rate_bounds': [lo, hi], 'increment_bound': increment_bound,
                         'horizon': horizon, 'seed': seed, 'beta': beta, 'fit_iterations': fit_iterations,
                         'continuous_solver': 'bounded_scalar_with_endpoints_32_iterations',
                         'reward': '(performance_increment / declared_bound + 1) / 2',
                         'kernel_reference': 'PB2-Mix equation 5; TV.EXP3.M Algorithm 5'}

    def _coordinate(self, lr):
        lo, hi = self.contract['learning_rate_bounds']
        if not lo <= lr <= hi:
            raise ValueError('Population learning rate outside declared search space')
        return math.log(lr/lo)/math.log(hi/lo)

    def _increment(self, value):
        if not math.isfinite(value) or abs(value) > self.contract['increment_bound']*(1+1e-12):
            raise ValueError('Observed gain violates the declared objective bound')
        return min(1.0, max(-1.0, value/self.contract['increment_bound']))

    def plan(self, rounds, scores, snapshot, top, bottom):
        if len(bottom) > len(self.contract['momenta']):
            raise ValueError('TV.EXP3.M batch exceeds categorical choices')
        bandit = TimeVaryingExp3(len(self.contract['momenta']), len(bottom), self.contract['horizon'], seed=self.contract['seed'])
        x, y = [], []
        for index, row in enumerate(rounds):
            outputs = scores if index == len(rounds)-1 else row['scores']
            for name, before in row['training_inputs'].items():
                optimizer = before['optimizer']
                if optimizer['momentum'] not in self.contract['momenta']:
                    raise ValueError('Observed momentum is not a declared category')
                category = self.contract['momenta'].index(optimizer['momentum'])
                x.append([index, self._coordinate(optimizer['learning_rate']), category])
                y.append(self._increment(outputs[name]-before['score']))
            if index:
                previous = rounds[index-1]['exploration']
                if bandit.ask() != previous['selection']:
                    raise ValueError('Category choice differs from retained bandit replay')
                rewards = {arm: (self._increment(outputs[action['child']]-row['training_inputs'][action['child']]['score'])+1)/2
                           for arm, action in zip(previous['selection']['selected'], rounds[index-1]['plan'])}
                bandit.tell(rewards)
        if len(x) > 512:
            raise ValueError('Population GP observation envelope exhausted')
        selection = bandit.ask()
        gp = TemporalPopulationGP([0], [1]).observe(x, y)
        fit = gp.fit(self.contract['fit_iterations'])
        pending, actions, acquisitions = [], [], []
        lo, hi = self.contract['learning_rate_bounds']
        index = len(rounds)-1
        for child, category in zip(bottom, selection['selected']):
            evaluations = []
            def objective(coordinate):
                point = [index+1, float(coordinate), category]
                mean, variance = gp.predict([point], pending=pending)
                ucb = float(mean[0]+math.sqrt(self.contract['beta']*variance[0]))
                evaluations.append({'coordinate': float(coordinate), 'ucb': ucb})
                return -ucb
            result = minimize_scalar(objective, bounds=(0, 1), method='bounded', options={'maxiter': 32})
            objective(0); objective(1)
            best = max(evaluations, key=lambda value: (value['ucb'], -value['coordinate']))
            # The posterior mean is always conditioned on observed data only;
            # selected points augment only the variance for later batch slots.
            pending.append([index+1, best['coordinate'], category])
            parent = top[len(actions) % len(top)]
            teacher = snapshot['members'][parent]
            actions.append({'event_id': f'pbt:{index}:exploit:{child}', 'parent': parent, 'child': child,
                            'mode': 'COPY', 'optimizer_policy': 'COPY',
                            'architecture': teacher['architecture'],
                            'optimizer': {'learning_rate': min(hi, max(lo, lo*(hi/lo)**best['coordinate'])),
                                          'momentum': self.contract['momenta'][category]}})
            acquisitions.append({'category': category, 'selected': best, 'evaluations': evaluations,
                                 'solver_success': bool(result.success)})
        return actions, {'selection': selection, 'bandit': bandit.state_dict(),
                         'gp_options': asdict(gp.options), 'fit': fit, 'x': x, 'increments': y,
                         'acquisitions': acquisitions}
