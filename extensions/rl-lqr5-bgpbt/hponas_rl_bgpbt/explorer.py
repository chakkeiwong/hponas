"""Bounded conditional BG-PBT proposals, not exhaustive/global optimization."""
from copy import deepcopy
from dataclasses import asdict
import math

import numpy as np
from scipy.optimize import minimize

from hponas.population_gp import TemporalOptions, TemporalPopulationGP
from hponas_rl_lqr5.search import validate


def point(config, time, cost):
    c = validate(config)
    row = [float(time), len(c['actor_hiddens']), len(c['critic_hiddens'])]
    for side in ('actor', 'critic'):
        widths = c[side+'_hiddens']
        row.extend([(w-7)/57 for w in widths]+[0.]*(4-len(widths)))
    row += [(math.log10(c[s+'_lr'])+5)/3 for s in ('actor', 'critic')]
    row += [math.log1p(cost)]
    return row


def sample_config(rng):
    return {**{s+'_hiddens': rng.integers(8,65,size=int(rng.integers(2,5))).tolist()
               for s in ('actor','critic')},
            **{s+'_lr': float(10**rng.uniform(-5,-2)) for s in ('actor','critic')}}


class Explorer:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.rows, self.values, self.records = [], [], []
        self.radius, self.successes, self.failures = .5, 0, 0

    def observe(self, config, time, before, after):
        if not all(math.isfinite(c) and c >= 0 for c in (before, after)):
            raise ValueError('Finite nonnegative objective costs required')
        self.rows.append(point(config,time,before)); self.values.append(before-after)
        if len(self.rows) > 480:
            self.rows, self.values = self.rows[-480:], self.values[-480:]
        if after < before:
            self.successes += 1; self.failures = 0
            if self.successes >= 2: self.radius = min(1.,2*self.radius); self.successes = 0
        else:
            self.failures += 1; self.successes = 0
            if self.failures >= 2: self.radius /= 2; self.failures = 0

    def _gp(self):
        gp = TemporalPopulationGP(list(range(2,13)), [0,1], TemporalOptions(family='bgpbt'))
        fit = None
        if self.rows:
            gp.observe(self.rows,self.values); fit = gp.fit(max_iterations=20)
        return gp, fit

    def propose(self, donor, time, cost, *, architecture=False, count=1):
        if not 1 <= count <= 4: raise ValueError('Bounded proposal count required')
        gp, fit = self._gp()
        restart = self.radius < .03125
        radius = 1. if restart else self.radius
        candidates = []
        bounds = []
        for side in ('actor','critic'):
            center = (math.log10(donor[side+'_lr'])+5)/3
            bounds.append((0.,1.) if restart else (max(0.,center-radius/2),min(1.,center+radius/2)))
        for _ in range(64):
            c = sample_config(self.rng) if architecture else deepcopy(donor)
            if not architecture:
                for side, (low,high) in zip(('actor','critic'),bounds):
                    c[side+'_lr'] = float(10**(-5+3*self.rng.uniform(low,high)))
            candidates.append(validate(c))
        rows = np.asarray([point(c,time,cost) for c in candidates])
        mean,var = gp.predict(rows); acquisition = mean+2*np.sqrt(var)
        refinement = None
        if not architecture:
            def convert(x):
                c = deepcopy(donor)
                c['actor_lr'],c['critic_lr'] = [float(10**(-5+3*v)) for v in x]
                return c
            def objective(x):
                m,v=gp.predict([point(convert(x),time,cost)])
                return -float(m[0]+2*np.sqrt(v[0]))
            start = rows[int(np.argmax(acquisition)),11:13]
            fit_acq = minimize(objective,start,method='L-BFGS-B',bounds=bounds,
                               options={'maxiter':20,'maxfun':120})
            refinement = {'success': bool(fit_acq.success), 'message': str(fit_acq.message),
                          'evaluations': int(fit_acq.nfev)}
            if np.isfinite(fit_acq.fun): candidates.append(validate(convert(fit_acq.x)))
            rows=np.asarray([point(c,time,cost) for c in candidates])
        unique = {}
        for c in candidates: unique.setdefault(tuple(point(c,time,cost)),c)
        candidates = list(unique.values())
        rows = np.asarray(list(unique))
        indices = gp.suggest_finite(rows,count,beta=4.)
        m,v=gp.predict(rows)
        record = {'architecture':architecture, 'time':time, 'cost_context':cost,
            'donor':deepcopy(donor), 'radius':radius, 'restart':restart, 'fit':fit,
            'kernel':asdict(gp.options), 'observed_points':deepcopy(self.rows),
            'observed_improvements':list(self.values), 'candidates':candidates,
            'points':rows.tolist(), 'mean':m.tolist(), 'variance':v.tolist(),
            'selected_indices':indices, 'refinement':refinement,
            'acquisition':'mean_plus_2_std_with_pending_variance', 'global_optimum':False}
        self.records.append(record)
        if restart: self.radius=.5
        return [deepcopy(candidates[i]) for i in indices], record

    def state(self):
        return {'rng':deepcopy(self.rng.bit_generator.state), 'rows':deepcopy(self.rows),
                'values':list(self.values), 'records':deepcopy(self.records),
                'radius':self.radius,'successes':self.successes,'failures':self.failures}

    @classmethod
    def restore(cls,state):
        result=cls(0)
        for k,v in state.items():
            if k=='rng': result.rng.bit_generator.state=v
            else: setattr(result,k,deepcopy(v))
        return result
