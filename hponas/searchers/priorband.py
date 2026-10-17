"""Categorical PriorBand with exact finite sampling and retained policy state."""
from copy import deepcopy
from fractions import Fraction

from hponas.categorical_prior import CategoricalPrior
from hponas.prior_band import PriorBand, identity
from hponas.prior_sampling import FiniteGuardedPrior
from hponas.searchers.base import BaseSearcher
from hponas.searchers.prior import FinitePriorSearcher, PriorPendingError
from hponas.types import Config
from hponas.capabilities import SearcherCapabilities


class CategoricalPriorBandSearcher(BaseSearcher):
    """NePS geometric/dynamic policy on unconditional finite categoricals.

    Use with PriorBandScheduler(default_at_target=True) and Study. The first
    default is a separate full-fidelity evaluation. Subsequent mixtures freeze
    their policy history and bracket index until an exact draw completes.
    Recovery preserves those frozen laws even if other results arrive meanwhile.
    """

    support = SearcherCapabilities(('categorical',), partial_fidelity=True, prior='external_law')

    def validate_study_controls(self, max_concurrent, scheduler):
        self._validate_scheduler(scheduler)

    def __init__(self, search_space, default, *, rungs, eta=3, seed=0,
                 confidence='medium', max_proposals=16, max_cells=4096,
                 mutation_rate=Fraction(1, 2), mutation_attempts=50):
        super().__init__(search_space, seed)
        if type(max_proposals) is not int or max_proposals < 1:
            raise ValueError('A positive proposal cap is required')
        self.law = CategoricalPrior(search_space, default, confidence=confidence,
                                    mutation_rate=mutation_rate, mutation_attempts=mutation_attempts,
                                    max_cells=max_cells)
        self.cells = self.law.cells
        self.policy = PriorBand(rungs=rungs, eta=eta)
        self.max_proposals = max_proposals
        self.maximize = False
        self._draws, self._contexts = [], []
        self._context, self._rung_index = None, None
        self._sampler = self._make_sampler(None, seed=seed)

    @property
    def contract(self):
        return {'distribution': self.law.contract(), 'rungs': self.policy.rungs, 'eta': self.policy.eta,
                'policy': self.policy.identity, 'max_proposals': self.max_proposals,
                'default_at_target': True, 'portfolio': 'geometric-dynamic'}

    @property
    def prior_identity(self):
        return identity(self.contract)

    def _validate_scheduler(self, scheduler):
        from hponas.schedulers_prior import PriorBandScheduler
        if (not isinstance(scheduler, PriorBandScheduler) or not scheduler.default_at_target
                or scheduler.rungs != self.policy.rungs or scheduler.config.eta != self.policy.eta):
            raise ValueError('Categorical PriorBand requires its matching default-at-target scheduler')

    def set_scheduler_context(self, scheduler):
        self._validate_scheduler(scheduler)
        self._rung_index = scheduler.next_start_rung

    def _policy_at(self, count):
        if type(count) is not int or not 0 <= count <= len(self.policy._events):
            raise ValueError('Invalid frozen policy prefix')
        target = PriorBand(rungs=self.policy.rungs, eta=self.policy.eta)
        for event in self.policy._events[:count]:
            args = {k: deepcopy(v) for k, v in event.items() if k != 'action'}
            if event['action'] == 'begin':
                target.begin(**args)
            else:
                target.observe(**args)
        return target

    def _mixture(self, rung, policy):
        prior = self.law.prior_masses()
        root = policy.incumbent()
        incumbent = self.trials[root].values if root is not None else self.law.default
        inc_scores = self.law.prior_masses(incumbent)
        indices = {root: self.cells.index(self.trials[root].values) for root in policy._latest}
        scores = {root: (prior[index], inc_scores[index]) for root, index in indices.items()}
        mix = policy.sampling_weights(rung, inc_style='dynamic', scores=scores)
        mutation = self.law.mutation_masses(incumbent)
        weights = [mix['prior']*p + mix['inc']*q for p, q in zip(prior, mutation)]
        return {'weights': list(map(str, weights)), 'alpha': str(1-mix['random']),
                'mixture': {k: str(v) for k, v in mix.items()}, 'incumbent': root}

    def _make_sampler(self, context, seed=0):
        count = len(self.cells)
        return FiniteGuardedPrior(
            [1]*count, [1]*count if context is None else [Fraction(x) for x in context['weights']],
            0 if context is None else Fraction(context['alpha']), seed,
            cell_identity=identity({'contract': self.contract, 'context': context}),
        )

    def suggest(self):
        if self._rung_index is None:
            raise ValueError('PriorBand proposals require scheduler context from Study')
        if not self._draws:
            index = self.law.default_index
            self._contexts.append({'default_at_target': True})
        else:
            if not self._sampler.pending_prior:
                self._context = {'rung_index': self._rung_index,
                                 'policy_events': len(self.policy._events),
                                 **self._mixture(self._rung_index, self.policy)}
                rng = self._sampler._rng
                self._sampler = self._make_sampler(self._context)
                self._sampler._rng = rng
            index = self._sampler.advance(self.max_proposals)
            if index is None:
                raise PriorPendingError('PriorBand mixture is pending with its frozen policy and RNG')
            self._contexts.append(deepcopy(self._context))
        config = Config(deepcopy(self.cells[index]), f'finite-prior-draw-{len(self._draws)}')
        self._draws.append(index)
        return config

    _validate_config_binding = FinitePriorSearcher._validate_config_binding

    def validate_study_snapshot(self, state):
        FinitePriorSearcher.validate_study_snapshot(self, state)
        if state['searcher_state']['maximize'] != state['maximize']:
            raise ValueError('PriorBand objective direction differs from Study')
        roots = [tid for tid in state['trials'] if state['roots'][tid] == tid]
        draws = [self.trials[tid].config_id for tid in roots]
        expected = [f'finite-prior-draw-{i}' for i in range(len(self._draws))]
        if sorted(draws) != sorted(expected):
            raise ValueError('PriorBand draws and Study roots differ')
        for tid, trial in state['trials'].items():
            row = self.policy._rows[tid]
            root = state['roots'][tid]
            if (row['root'] != root or row['rung'] != trial['fidelity']
                    or self.trials[tid] != self.trials[root]):
                raise ValueError('PriorBand evaluation lineage differs from Study')
        for position, event in enumerate(self.policy._events):
            if event['action'] == 'begin' and event['trial_id'] == event['root']:
                index = int(self.trials[event['root']].config_id.removeprefix('finite-prior-draw-'))
                if index and self._contexts[index]['policy_events'] > position:
                    raise ValueError('PriorBand proposal uses future observations')

    def register_trial(self, trial):
        self._validate_config_binding(trial.config)
        root = trial.root_trial_id or trial.trial_id
        if root not in self.trials or self.trials[root].values != trial.config.values:
            raise ValueError('PriorBand root and evaluation configurations differ')
        self.policy.begin(trial.trial_id, root=root, rung=trial.fidelity)

    def observe(self, result):
        if result.trial_id not in self.trials or any(r.trial_id == result.trial_id for r in self.history):
            raise ValueError('PriorBand requires a new bound trial result')
        self._validate_config_binding(self.trials[result.trial_id])
        value = (-result.objective_value if self.maximize else result.objective_value) if result.is_valid() else None
        self.policy.observe(result.trial_id, rung=result.fidelity, value=value, work=result.cost,
                            status='completed' if result.is_valid() else 'failed')
        super().observe(result)

    @property
    def capabilities(self):
        return {**super().capabilities, 'supports_fidelity': True, 'prior': True,
                'finite_support': True, 'pending_suggestions': True,
                'priorband_envelope': 'categorical-product-neps-3f7475b'}

    def get_state(self):
        return deepcopy({**super().get_state(), 'kind': 'categorical_priorband_v1',
                         'contract': self.contract, 'maximize': self.maximize, 'policy': self.policy.state_dict(),
                         'draws': self._draws, 'contexts': self._contexts, 'context': self._context,
                         'rung_index': self._rung_index, 'sampler': self._sampler.state_dict()})

    def set_state(self, state):
        if (type(state) is not dict or set(state) != set(self.get_state())
                or state.get('kind') != 'categorical_priorband_v1' or state.get('contract') != self.contract
                or type(state.get('maximize')) is not bool):
            raise ValueError('Categorical PriorBand identity or state shape differs')
        target = type(self)(self.search_space, self.law.default, rungs=self.policy.rungs,
                            eta=self.policy.eta, seed=state['seed'], confidence=self.law.confidence,
                            max_proposals=self.max_proposals, max_cells=self.law.max_cells,
                            mutation_rate=self.law.mutation_rate, mutation_attempts=self.law.mutation_attempts)
        target.maximize = state['maximize']
        BaseSearcher.set_state(target, deepcopy(state))
        target.policy.load_state_dict(state['policy'])
        draws, contexts = state['draws'], state['contexts']
        if (type(draws) is not list or type(contexts) is not list or len(draws) != len(contexts)
                or any(type(i) is not int or not 0 <= i < len(self.cells) for i in draws)
                or (draws and (draws[0] != self.law.default_index or contexts[0] != {'default_at_target': True}))):
            raise ValueError('PriorBand draw ledger differs')
        target._draws, target._contexts = list(draws), deepcopy(contexts)
        for tid, config in target.trials.items():
            if type(tid) is not str or not tid:
                raise ValueError('Invalid trial ID')
            target._validate_config_binding(config)
        if set(target.trials) != set(target.policy._rows):
            raise ValueError('PriorBand policy and trial ledger differ')
        observed = set()
        for result in target.history:
            row = target.policy._rows.get(result.trial_id)
            value = (-result.objective_value if target.maximize else result.objective_value) if result.is_valid() else None
            if (row is None or result.trial_id in observed or row['value'] != value or row['work'] != result.cost
                    or row['rung'] != result.fidelity or row['status'] != ('completed' if result.is_valid() else 'failed')):
                raise ValueError('PriorBand observations differ from policy')
            observed.add(result.trial_id)
        if observed != {tid for tid, row in target.policy._rows.items() if row['status'] != 'pending'}:
            raise ValueError('Missing policy result')
        for context in contexts[1:] + ([state['context']] if state['context'] is not None else []):
            if type(context) is not dict or set(context) != {'rung_index','policy_events','weights','alpha','mixture','incumbent'}:
                raise ValueError('Malformed frozen mixture')
            expected = target._mixture(context['rung_index'], target._policy_at(context['policy_events']))
            if any(context[k] != v for k, v in expected.items()):
                raise ValueError('Frozen mixture differs from retained policy prefix')
        target._context = deepcopy(state['context'])
        target._sampler = target._make_sampler(target._context)
        target._sampler.load_state_dict(state['sampler'])
        if (target._context is None and (len(draws) > 1 or target._sampler.started_draws)
                or target._context is not None and target._sampler.started_draws != 1):
            raise ValueError('Sampler counters differ from proposal lifecycle')
        if (not target._sampler.pending_prior and target._context is not None
                and (len(contexts) < 2 or target._context != contexts[-1])):
            raise ValueError('Completed sampler differs from its last retained mixture')
        rung = state['rung_index']
        if rung is not None and (type(rung) is not int or not 0 <= rung < len(self.policy.rungs)):
            raise ValueError('Invalid scheduler context')
        target._rung_index = rung
        self.__dict__.update(target.__dict__)
