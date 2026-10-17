"""PriorBand with numerical, integer and categorical product distributions."""
from copy import deepcopy
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import json
import random
import sys

import numpy as np
import scipy

from hponas.prior_band import PriorBand, identity
from hponas.product_prior import ProductPrior
from hponas.searchers.base import BaseSearcher
from hponas.searchers.prior import FinitePriorSearcher
from hponas.searchers.priorband import CategoricalPriorBandSearcher
from hponas.types import Config, Result, Trial
from hponas.capabilities import SearcherCapabilities, MIXED


class ProductPriorBandSearcher(BaseSearcher):
    """Pinned geometric/dynamic PriorBand on unconditional mixed products.

    Linear/log numerical laws use bounded float64 inverse CDF. Integer draws
    follow the reference's expanded interval and rounding. All completed draws,
    their policy contexts and the RNG are independently replayed on restoration.
    Conditional/logit spaces require an explicit different law and are refused.
    """

    support = SearcherCapabilities(MIXED, partial_fidelity=True, prior='external_law')
    validate_study_controls = CategoricalPriorBandSearcher.validate_study_controls
    _validate_scheduler = CategoricalPriorBandSearcher._validate_scheduler

    def __init__(self, search_space, default, *, rungs, eta=3, seed=0,
                 confidence='medium', mutation_rate=Fraction(1,2), mutation_std=.25,
                 mutation_attempts=50):
        if type(seed) is not int or not 0<=seed<2**64:
            raise ValueError('A nonnegative 64-bit seed is required')
        super().__init__(search_space,seed)
        self.law=ProductPrior(search_space,default,confidence=confidence,mutation_rate=mutation_rate,
                              mutation_std=mutation_std,mutation_attempts=mutation_attempts)
        self.policy=PriorBand(rungs=rungs,eta=eta)
        self.maximize=False
        self._rng=random.Random(seed)
        self._rung_index=None
        self._draws,self._contexts,self._events=[],[],[]

    @property
    def contract(self):
        return {'distribution':self.law.contract(),'rungs':self.policy.rungs,'eta':self.policy.eta,
                'policy':self.policy.identity,'default_at_target':True,'portfolio':'geometric-dynamic',
                'dynamic_score_arithmetic':'float64-logpdf; common rescaling with 64-digit decimal exp',
                'versions':{'python':list(sys.version_info[:2]),'numpy':np.__version__,'scipy':scipy.__version__}}

    @property
    def prior_identity(self):
        return identity(self.contract)

    set_scheduler_context=CategoricalPriorBandSearcher.set_scheduler_context

    def _mixture(self):
        root=self.policy.incumbent()
        center=self.trials[root].values if root is not None else self.law.default
        logs={root:(self.law.log_score(self.trials[root].values),
                    self.law.log_score(self.trials[root].values,center)) for root in self.policy._latest}
        offset=max((x for pair in logs.values() for x in pair),default=0)
        with localcontext(Context(prec=64)):
            scores={root:tuple(Fraction(Decimal(str(x-offset)).exp()) for x in pair)
                    for root,pair in logs.items()}
        weights=self.policy.sampling_weights(self._rung_index,inc_style='dynamic',scores=scores)
        return {'rung_index':self._rung_index,'policy_events':len(self.policy._events),'incumbent':root,
                'mixture':{k:str(v) for k,v in weights.items()}}

    def suggest(self):
        if self._rung_index is None:
            raise ValueError('PriorBand proposals require scheduler context from Study')
        if not self._draws:
            values=deepcopy(self.law.default)
            context={'default_at_target':True}
        else:
            context=self._mixture()
            weights={k:Fraction(v) for k,v in context['mixture'].items()}
            if self.law.bernoulli(self._rng,weights['random']):
                branch='base'
            elif self.law.bernoulli(self._rng,weights['prior']/(1-weights['random'])):
                branch='prior'
            else:
                branch='mutation'
            root=context['incumbent']
            center=self.trials[root].values if root is not None else self.law.default
            values=self.law.sample(self._rng,mode=branch,center=center if branch=='mutation' else None)
            context['branch']=branch
        config=Config(values,f'product-prior-draw-{len(self._draws)}')
        self._draws.append(deepcopy(values))
        self._contexts.append(context)
        self._events.append({'action':'suggest','rung_index':self._rung_index})
        return config

    def _validate_config_binding(self, config):
        if not isinstance(config,Config) or type(config.config_id) is not str:
            raise ValueError('A retained product-prior configuration is required')
        suffix=config.config_id.removeprefix('product-prior-draw-')
        if (not config.config_id.startswith('product-prior-draw-') or not suffix.isdecimal()
                or str(int(suffix))!=suffix or int(suffix)>=len(self._draws)
                or config.values!=self._draws[int(suffix)]):
            raise ValueError('Configuration differs from its retained product-prior draw')

    def register_trial(self, trial):
        self._validate_config_binding(trial.config)
        root=trial.root_trial_id or trial.trial_id
        if root not in self.trials or self.trials[root]!=trial.config:
            raise ValueError('PriorBand root and evaluation configurations differ')
        self.policy.begin(trial.trial_id,root=root,rung=trial.fidelity)
        self._events.append({'action':'register','trial':{
            'config':deepcopy(trial.config.to_dict()),'trial_id':trial.trial_id,
            'root_trial_id':root,'fidelity':trial.fidelity}})

    def observe(self, result):
        if (not isinstance(result,Result) or result.trial_id not in self.trials
                or any(r.trial_id==result.trial_id for r in self.history)):
            raise ValueError('PriorBand requires a new bound result')
        self._validate_config_binding(self.trials[result.trial_id])
        value=(-result.objective_value if self.maximize else result.objective_value) if result.is_valid() else None
        self.policy.observe(result.trial_id,rung=result.fidelity,value=value,work=result.cost,
                            status='completed' if result.is_valid() else 'failed')
        super().observe(result)
        self._events.append({'action':'observe','result':deepcopy(result.to_dict())})

    def validate_study_snapshot(self, state):
        FinitePriorSearcher.validate_study_snapshot(self,state)
        if state['searcher_state']['maximize']!=state['maximize']:
            raise ValueError('PriorBand direction differs from Study')
        roots=[tid for tid in state['trials'] if state['roots'][tid]==tid]
        if sorted(self.trials[tid].config_id for tid in roots)!=sorted(f'product-prior-draw-{i}' for i in range(len(self._draws))):
            raise ValueError('PriorBand draws and Study roots differ')
        for tid,trial in state['trials'].items():
            row=self.policy._rows[tid]
            if row['root']!=state['roots'][tid] or row['rung']!=trial['fidelity']:
                raise ValueError('PriorBand policy lineage differs from Study')

    def get_state(self):
        # JSON roundtrip converts the Python RNG tuples into an immutable JSON recipe.
        return json.loads(json.dumps({**super().get_state(),'kind':'product_priorband_v1',
            'contract':self.contract,'maximize':self.maximize,'policy':self.policy.state_dict(),
            'draws':self._draws,'contexts':self._contexts,'events':self._events,
            'rung_index':self._rung_index,'rng':self._rng.getstate()}))

    def set_state(self, state):
        if (type(state) is not dict or set(state)!=set(self.get_state())
                or state.get('kind')!='product_priorband_v1' or state.get('contract')!=self.contract
                or type(state.get('maximize')) is not bool or type(state.get('events')) is not list):
            raise ValueError('Product PriorBand identity or state shape differs')
        target=type(self)(self.search_space,self.law.default,rungs=self.policy.rungs,eta=self.policy.eta,
            seed=state['seed'],confidence=self.law.confidence,mutation_rate=self.law.mutation_rate,
            mutation_std=self.law.mutation_std,mutation_attempts=self.law.mutation_attempts)
        target.maximize=state['maximize']
        try:
            for event in state['events']:
                if event['action']=='suggest':
                    rung=event['rung_index']
                    if type(rung) is not int or not 0<=rung<len(self.policy.rungs):
                        raise ValueError('Invalid proposal rung')
                    target._rung_index=rung
                    target.suggest()
                elif event['action']=='register':
                    row=deepcopy(event['trial'])
                    row['config']=Config(**row['config'])
                    trial=Trial(**row)
                    target.trials[trial.trial_id]=trial.config
                    target.register_trial(trial)
                elif event['action']=='observe':
                    target.observe(Result(**deepcopy(event['result'])))
                else:
                    raise ValueError('Unknown PriorBand event')
            # Context can be refreshed before suggest, without consuming randomness.
            rung=state['rung_index']
            if rung is not None and (type(rung) is not int or not 0<=rung<len(self.policy.rungs)):
                raise ValueError('Invalid scheduler context')
            target._rung_index=rung
            if json.dumps(target.get_state(),sort_keys=True)!=json.dumps(state,sort_keys=True):
                raise ValueError('PriorBand state differs from complete draw and observation replay')
        except (KeyError,TypeError,AttributeError) as exc:
            raise ValueError('Malformed product PriorBand event') from exc
        self.__dict__.update(target.__dict__)

    @property
    def capabilities(self):
        return {**super().capabilities,'supports_fidelity':True,'prior':True,
                'priorband_envelope':'unconditional-linear/log-product-neps-3f7475b',
                'sampling_arithmetic':'float64-inverse-cdf'}
