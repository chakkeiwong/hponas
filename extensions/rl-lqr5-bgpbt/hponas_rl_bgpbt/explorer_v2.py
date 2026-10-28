"""Objective-based architecture proposals and round-based trust-region state.

This bounded SAC adaptation preserves the original pilot explorer for replay.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import math

import numpy as np
from scipy.optimize import minimize

from hponas.population_gp import TemporalOptions, TemporalPopulationGP
from .explorer import point, sample_config


class JointExplorer:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.rows, self.values, self.configs, self.costs = [], [], [], []
        self.radius, self.successes, self.failures = .5, 0, 0
        self.best, self.round, self.local_start = None, -1, 0

    def observe(self, config, time, before, after):
        if not all(math.isfinite(v) and v >= 0 for v in (before, after)):
            raise ValueError('Finite costs required')
        self.rows.append(point(config, time, before))
        self.values.append((before-after)/max(1., before))
        self.configs.append(deepcopy(config)); self.costs.append(after)
        if len(self.rows) > 480: raise ValueError('Observation envelope exhausted')

    def finish_round(self, time, costs):
        if time != self.round+1 or not costs or not all(math.isfinite(v) and v >= 0 for v in costs):
            raise ValueError('One consecutive population round required')
        current = min(costs)
        if self.best is not None:
            if current < self.best:
                self.successes += 1; self.failures = 0
            else:
                self.failures += 1; self.successes = 0
            if self.successes >= 2:
                self.radius = min(1., 2*self.radius); self.successes = 0
            if self.failures >= 2:
                self.radius /= 2; self.failures = 0
        self.best = current if self.best is None else min(self.best, current)
        self.round = time

    @staticmethod
    def fit(rows, values):
        gp = TemporalPopulationGP(list(range(2,13)), [0,1], TemporalOptions(family='bgpbt'))
        receipt = None
        if rows:
            gp.observe(rows, values); receipt = gp.fit(max_iterations=20)
        return gp, receipt

    def propose(self, donor, time, cost, *, architecture=False, count=1):
        if not 1 <= count <= 4: raise ValueError('Bounded proposal count required')
        center = deepcopy(donor); restart_record = None
        restart = not architecture and self.radius < .03125
        if restart:
            global_gp, fitted = self.fit(self.rows, self.values)
            centers = [dict(donor, actor_lr=c['actor_lr'], critic_lr=c['critic_lr']) for c in self.configs]
            queries = [point(c,time,cost) for c in centers]
            mean,var = global_gp.predict(queries)
            index = int(np.argmax(mean+2*np.sqrt(var)))
            center = centers[index]
            restart_record = {'index':index,'center':center,'fit':fitted,
                              'kernel':asdict(global_gp.options),'points':queries,
                              'observed_points':deepcopy(self.rows),'observed_values':list(self.values)}
            self.local_start = len(self.rows); self.radius = .5
            self.successes = self.failures = 0
        if architecture:
            # The objective model is distinct from the incremental rate model.
            best = {}
            for c,v in zip(self.configs,self.costs):
                key=json.dumps(c,sort_keys=True)
                if key not in best or v < best[key][1]: best[key]=(c,v)
            observations=[best[k] for k in sorted(best)]
            rows=[point(c,0,0) for c,v in observations]
            values=[-math.log1p(v) for c,v in observations]
            query_time, context = 0., 0.
        else:
            # Canonical ordering also makes equal round observations order-invariant.
            ordered=sorted(zip(self.rows[self.local_start:],self.values[self.local_start:]))
            rows=[r for r,v in ordered]; values=[v for r,v in ordered]
            query_time, context = time, cost
        gp, fitted = self.fit(rows,values)
        candidates=[]; bounds=[]
        for side in ('actor','critic'):
            x=(math.log10(center[side+'_lr'])+5)/3
            bounds.append((max(0.,x-self.radius/2),min(1.,x+self.radius/2)))
        for _ in range(64):
            c=sample_config(self.rng) if architecture else deepcopy(center)
            if not architecture:
                for side,(low,high) in zip(('actor','critic'),bounds):
                    c[side+'_lr']=float(10**(-5+3*self.rng.uniform(low,high)))
            candidates.append(c)
        refinement=None
        if not architecture:
            def convert(x):
                return dict(center,actor_lr=float(10**(-5+3*x[0])),critic_lr=float(10**(-5+3*x[1])))
            def objective(x):
                m,v=gp.predict([point(convert(x),time,cost)])
                return -float(m[0]+2*np.sqrt(v[0]))
            query=[point(c,time,cost) for c in candidates]; m,v=gp.predict(query)
            start=query[int(np.argmax(m+2*np.sqrt(v)))][11:13]
            fit=minimize(objective,start,method='L-BFGS-B',bounds=bounds,options={'maxiter':20,'maxfun':120})
            refinement={'success':bool(fit.success),'message':str(fit.message),'evaluations':int(fit.nfev)}
            if np.isfinite(fit.fun): candidates.append(convert(fit.x))
        unique={}
        for c in candidates: unique.setdefault(tuple(point(c,query_time,context)),c)
        candidates=list(unique.values()); points=list(map(list,unique))
        bo_count=max(1,count//2) if architecture else count
        bo=gp.suggest_finite(points,bo_count,beta=4.)
        remaining=[i for i in range(len(points)) if i not in bo]
        random_indices=self.rng.choice(remaining,count-bo_count,replace=False).tolist()
        indices=bo+random_indices; mean,var=gp.predict(points)
        record={'schema':2,'architecture':architecture,'time':query_time,'cost_context':context,
            'donor':deepcopy(donor),'radius':self.radius,'restart':restart_record,'fit':fitted,
            'kernel':asdict(gp.options),'observed_points':deepcopy(rows),
            'observed_improvements':list(values),'candidates':candidates,'points':points,
            'mean':mean.tolist(),'variance':var.tolist(),'selected_indices':indices,
            'bo_indices':bo,'random_indices':random_indices,'refinement':refinement,
            'response':'negative_log1p_best_objective' if architecture else 'relative_cost_improvement',
            'global_optimum':False}
        return [deepcopy(candidates[i]) for i in indices],record
