"""Sequential cost-aware proposal adapter with censored-duration evidence.

This adapter is intentionally separate from the retained legacy
``hponas.searchers_cost`` module. It wraps a proposal source exposing
``propose(n=1)``/``observe(record)`` (for example the maintained legacy GP
proposal interface) and applies the CArBO one-to-zero cost exponent to a
candidate pool. Only one evaluation may be pending. Cost-aware performance
acceptance remains a separate protocol decision.
"""
from copy import deepcopy
import hashlib
import json
import math
import platform
from types import SimpleNamespace

import numpy as np
import scipy
import torch
import gpytorch

from hponas.cost_inference import GaussianCensoredCost
from hponas.cost_policy import CostRecord, cheap_first, cooling, cost_aware_acquisition, observation_record
from hponas.encoding import SpaceEncoder, as_knob_space
from hponas.space import SearchSpace
from hponas.searchers.base import SearchBudgetExhaustedError, SearchSpaceExhaustedError
from hponas.trust_space import config_key


class CensoredCostGP:
    """Fixed-kernel GP over log duration with exact small-censor moments.

    Kernel hyperparameters are deliberately fixed and recorded. Completed and
    externally deadline-censored observations use the exact Gaussian likelihood
    and exponential-tilt predictive moments. Other failures remain accounting
    records but are excluded from the duration likelihood.
    """

    def __init__(self, space, *, default_cost=1., observation_noise=.05, jitter=1e-6,
                 lengthscale=.5, max_censored=32):
        if not isinstance(space, SearchSpace):
            space = as_knob_space(space)
        self.space = deepcopy(space)
        self.encoder = SpaceEncoder(self.space)
        from hponas.trust_space import MixedKernel, TrustSpace
        self.geometry = TrustSpace(self.space)
        self._kernel_class = MixedKernel
        self.default_cost = self._positive(default_cost, 'default cost')
        self.observation_noise = self._positive(observation_noise, 'observation noise')
        self.jitter = self._positive(jitter, 'jitter')
        self.lengthscale = self._positive(lengthscale, 'lengthscale')
        if type(max_censored) is not int or not 1 <= max_censored <= 32:
            raise ValueError('max_censored must be an integer in [1,32]')
        self.max_censored = max_censored
        self.records, self._configs = [], []
        self._kernel = self._new_kernel()

    @staticmethod
    def _positive(value, label):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(label+' must be a finite positive number')
        return float(value)

    def _new_kernel(self):
        kernel = self._kernel_class(self.geometry.n_numeric, len(self.geometry.categorical)).double()
        with torch.no_grad():
            if self.geometry.numeric:
                kernel.numeric.lengthscale = torch.tensor(self.lengthscale, dtype=torch.double)
            if self.geometry.categorical:
                kernel.categorical.lengthscale = torch.tensor(self.lengthscale, dtype=torch.double)
        return kernel

    @property
    def contract(self):
        return {'schema': 'censored_cost_gp_v1', 'space': self.space.to_dict(),
                'duration': 'log(cost)', 'likelihood': 'complete-density-or-independent-deadline-survival',
                'prediction': 'Gaussian-exponential-tilt-first-and-second-moments',
                'kernel': 'mixed-matern52-times-hamming-fixed-lengthscale',
                'default_cost': self.default_cost, 'observation_noise': self.observation_noise,
                'jitter': self.jitter, 'lengthscale': self.lengthscale,
                'prior_log_mean': self.prior_mean, 'signal_variance': 1.,
                'max_observations': 128, 'max_censored': self.max_censored,
                'predictive_noise_included': True, 'error_estimates_are_bounds': False,
                'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                             'scipy': scipy.__version__, 'torch': torch.__version__, 'gpytorch': gpytorch.__version__}}

    @property
    def prior_mean(self):
        return math.log(self.default_cost) - (1. + self.observation_noise**2)/2

    def _features(self, configs):
        return torch.tensor([self.geometry.features(c) for c in configs], dtype=torch.double)

    def _matrix(self, left, right):
        value = self._kernel(self._features(left), self._features(right))
        return value.to_dense().detach().numpy()

    def observe(self, config, record):
        if not isinstance(record, CostRecord):
            raise ValueError('CensoredCostGP requires a CostRecord')
        self.geometry.validate(config)
        if any(existing.trial_id == record.trial_id for existing in self.records):
            raise ValueError('A cost observation cannot be revised')
        if self.records and record.unit != self.records[0].unit:
            raise ValueError('Cost observations must use one declared unit')
        if record.kind != 'unmodeled' and len(self._modelable()) >= 128:
            raise ValueError('Cost observation count exceeds the bounded inference envelope')
        if record.kind == 'right_censored' and sum(r.kind == 'right_censored' for r in self.records) >= self.max_censored:
            raise ValueError('Censor count exceeds the bounded exact-inference envelope')
        self._configs.append(deepcopy(config))
        self.records.append(record)

    def _modelable(self):
        rows = [(c, r) for c, r in zip(self._configs, self.records)
                if r.kind in {'complete', 'right_censored'} and r.duration is not None and r.duration > 0]
        return rows

    def predict(self, configs):
        if not isinstance(configs, list) or not configs:
            raise ValueError('At least one cost candidate is required')
        for config in configs:
            self.geometry.validate(config)
        rows = self._modelable()
        if not rows:
            value = math.log(self.default_cost)
            return {'log_expected_cost': np.full(len(configs), value),
                    'log_second_moment': np.full(len(configs), 2*value + 1. + self.observation_noise**2),
                    'cost_cv_squared': np.full(len(configs), math.expm1(1. + self.observation_noise**2)),
                    'censor_count': 0, 'modelable_count': 0, 'quadrature_relative_error_estimates': [0.]*len(configs),
                    'cold_start': True}
        observed_configs = [c for c, _ in rows]
        observed_records = [r for _, r in rows]
        k = self._matrix(observed_configs, observed_configs)
        k = (k+k.T)/2 + self.jitter*np.eye(len(rows))
        events = [{'kind': 'complete' if r.kind == 'complete' else 'timeout',
                   'elapsed': r.duration, 'noise_variance': self.observation_noise**2}
                  for r in observed_records]
        mean = np.full(len(rows), self.prior_mean, dtype=float)
        design = np.eye(len(rows), dtype=float)
        reference = GaussianCensoredCost(mean, k, design, events)
        target = self._matrix(configs, configs)
        cross = self._matrix(observed_configs, configs)
        result = reference.predict(np.full(len(configs), self.prior_mean), target, cross,
                                   noise_variance=self.observation_noise**2)
        result['modelable_count'] = len(rows)
        result['cold_start'] = False
        result['records_total'] = len(self.records)
        return result

    def state_dict(self):
        return {'schema': 'censored_cost_gp_state_v1', 'contract': self.contract,
                'records': [r.to_dict() for r in self.records], 'configs': deepcopy(self._configs)}

    @classmethod
    def from_state(cls, state, space):
        if (type(state) is not dict or set(state) != {'schema', 'contract', 'records', 'configs'}
                or state['schema'] != 'censored_cost_gp_state_v1'):
            raise ValueError('Malformed cost-model checkpoint')
        if not isinstance(state['contract'], dict) or not all(k in state['contract'] for k in
                ('default_cost', 'observation_noise', 'jitter', 'lengthscale', 'max_censored')):
            raise ValueError('Malformed cost-model contract')
        target = cls(space, default_cost=state['contract']['default_cost'],
                     observation_noise=state['contract']['observation_noise'],
                     jitter=state['contract']['jitter'], lengthscale=state['contract']['lengthscale'],
                     max_censored=state['contract']['max_censored'])
        if state['contract'] != target.contract:
            raise ValueError('Cost-model contract differs')
        if (not isinstance(state['records'], list) or not isinstance(state['configs'], list)
                or len(state['records']) != len(state['configs'])):
            raise ValueError('Cost-model ledger dimensions differ')
        for config, row in zip(state['configs'], state['records']):
            try:
                target.observe(config, CostRecord(**row))
            except TypeError as exc:
                raise ValueError('Malformed cost-model record') from exc
        return target


class CostAwareProposalSearcher:
    """One-pending CArBO adapter around a proposal source.

    ``base_searcher`` supplies log expected improvement over a bounded global
    candidate pool and accepts maximizing objective observations. The maintained
    GPqLogEI interface supplies this scoring contract. A source without it is
    permitted only with ``cost_only=True``, an explicit diagnostic mode.
    """

    def __init__(self, space, base_searcher, *, total_budget, initial_budget=None,
                 candidate_count=16, default_cost=1., cost_unit='declared_work_units', seed=0,
                 timeout_assumption=None, cost_only=False):
        if not hasattr(base_searcher, 'propose') or not hasattr(base_searcher, 'observe'):
            raise TypeError('Cost-aware base must expose propose and observe')
        self.space = deepcopy(as_knob_space(space))
        if as_knob_space(base_searcher.space).to_dict() != self.space.to_dict():
            raise ValueError('Cost-aware base search space differs')
        if type(cost_only) is not bool:
            raise ValueError('cost_only must be boolean')
        if not cost_only and not callable(getattr(base_searcher, 'log_expected_improvement', None)):
            raise TypeError('Base must expose log_expected_improvement or explicitly use cost_only=True')
        if timeout_assumption not in {None, 'deadline_independent_given_config'}:
            raise ValueError('Unknown censoring assumption')
        if not all(callable(getattr(base_searcher, name, None)) for name in ('state_dict', 'load_state_dict')):
            raise TypeError('Cost-aware base must support JSON checkpoint recovery')
        self.timeout_assumption, self.cost_only = timeout_assumption, cost_only
        self.base_searcher = base_searcher
        if type(total_budget) not in (int, float) or not math.isfinite(total_budget) or total_budget <= 0:
            raise ValueError('total_budget must be finite and positive')
        self.total_budget = float(total_budget)
        if initial_budget is not None and (type(initial_budget) not in (int, float) or not math.isfinite(initial_budget)):
            raise ValueError('initial_budget must be finite')
        self.initial_budget = float(total_budget/8 if initial_budget is None else initial_budget)
        if not 0 <= self.initial_budget < self.total_budget:
            raise ValueError('initial_budget must lie in [0,total_budget)')
        if type(candidate_count) is not int or not 2 <= candidate_count <= 256:
            raise ValueError('candidate_count must be in [2,256]')
        if cost_unit not in {'declared_work_units', 'wall_seconds'}:
            raise ValueError('Unknown cost unit')
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        self.seed = seed
        self.candidate_count = candidate_count
        self.cost_unit = cost_unit
        self.cost_model = CensoredCostGP(self.space, default_cost=default_cost)
        self.records, self._proposals, self._trace = [], [], []
        self._pending = None
        self._spent = 0.
        self._rng = np.random.default_rng(seed)
        self._base_kind = type(base_searcher).__module__+'.'+type(base_searcher).__name__
        self._study_name, self._maximize = None, None

    @property
    def space_contract(self):
        return self.space.to_dict()

    @property
    def support(self):
        from dataclasses import replace
        base = getattr(self.base_searcher, 'support', None)
        return replace(base, partial_fidelity=False, concurrent_proposals=False, joint_batch=False) if base else None

    @property
    def capabilities(self):
        base = getattr(self.base_searcher, 'capabilities', {})
        return {**base, **(self.support.report() if self.support else {}), 'cost_aware': True, 'supports_censoring': True,
                'supports_batch': False, 'supports_noise': False, 'supports_fidelity': False}

    def validate_study_context(self, study_name, maximize=True):
        if not isinstance(study_name, str) or not study_name:
            raise ValueError('A nonempty Study name is required')
        if not isinstance(maximize, bool):
            raise ValueError('Study direction must be boolean')
        if self._proposals and self._study_name is not None and (study_name, maximize) != (self._study_name, self._maximize):
            raise ValueError('Cost-aware Study identity or direction changed after work')
        self._study_name, self._maximize = study_name, maximize

    def validate_study_controls(self, max_concurrent, scheduler):
        if max_concurrent != 1 or scheduler is not None:
            raise ValueError('Cost-aware adapter requires sequential fixed-fidelity Study controls')

    def _proposal_distances(self, configs):
        """Distance to the nearest already proposed configuration.

        The CArBO initial-design elimination uses a fill-distance tie breaker.
        Distances combine normalized numeric features and categorical Hamming;
        an empty design has infinite distance for every candidate.
        """
        if not self._proposals:
            return np.full(len(configs), np.inf, dtype=float)
        geometry = self.cost_model.geometry
        previous = np.asarray([geometry.features(c) for c in self._proposals], dtype=float)
        current = np.asarray([geometry.features(c) for c in configs], dtype=float)
        d = geometry.n_numeric
        numeric = np.sum((current[:, None, :d] - previous[None, :, :d])**2, axis=2)
        categorical = np.sum(current[:, None, d:] != previous[None, :, d:], axis=2)
        return np.sqrt(np.min(numeric + categorical, axis=1))

    def _base_score(self, configs):
        if self.cost_only:
            return np.zeros(len(configs)), 'explicit_cost_only'
        values = np.asarray(self.base_searcher.log_expected_improvement(configs), dtype=float)
        if values.shape != (len(configs),) or np.isnan(values).any() or np.isposinf(values).any():
            raise ValueError('Base acquisition contains unsupported nonfinite values or shape')
        return values, 'log_expected_improvement'

    def propose(self, n=1):
        if type(n) is not int or n != 1:
            raise ValueError('Cost-aware adapter supports exactly one sequential proposal')
        if self._pending is not None:
            raise RuntimeError('A cost-aware proposal is already pending')
        if self._spent >= self.total_budget:
            raise SearchBudgetExhaustedError('Cost budget exhausted')
        if (len(self.cost_model._modelable()) >= 128
                or sum(r.kind == 'right_censored' for r in self.records) >= self.cost_model.max_censored):
            raise RuntimeError('Cost inference envelope exhausted before further work')
        # Candidate generation is bounded independently of objective fitting;
        # building a q=candidate_count batch would solve a different, costly BO
        # problem before reranking only one of its candidates.
        candidate_rng = deepcopy(self._rng)
        pool, exhausted = self.cost_model.geometry.initial_design(
            candidate_rng, count=self.candidate_count, exclude=self._proposals)
        if exhausted:
            raise SearchSpaceExhaustedError('Finite cost-aware search space exhausted')
        if not isinstance(pool, list) or not pool:
            raise ValueError('Base proposal source returned no candidates')
        pool = [dict(c) for c in pool]
        unique = []
        seen = set(json.dumps(c, sort_keys=True, separators=(',', ':')) for c in self._proposals)
        for config in pool:
            self.space.validate_config(config)
            key = json.dumps(config, sort_keys=True, separators=(',', ':'))
            if key not in seen:
                unique.append(config); seen.add(key)
        if not unique:
            raise RuntimeError('Base proposal source returned only previously proposed configurations')
        if self._spent < self.initial_budget:
            predicted = self.cost_model.predict(unique)
            distances = self._proposal_distances(unique)
            index, eliminated = cheap_first(predicted['log_expected_cost'], distances)
            selected, alpha, source = unique[index], 1., 'cheap_first_warmup'
            base_scores = None
        else:
            predicted = self.cost_model.predict(unique)
            base_scores, source = self._base_score(unique)
            distances, eliminated = None, []
            alpha = cooling(self._spent, self.total_budget, self.initial_budget)
            # Legacy qLogEI is already in log-EI units; base source alternatives
            # that expose ordinary EI must declare a different adapter in future.
            scores = cost_aware_acquisition(torch.tensor(base_scores, dtype=torch.double),
                                            torch.tensor(predicted['log_expected_cost'], dtype=torch.double),
                                            alpha, log_domain=True).numpy()
            index = int(np.argmax(scores))
            selected = unique[index]
        self._pending = {'config': deepcopy(selected), 'pool': deepcopy(unique),
                         'alpha': float(alpha), 'base_source': source,
                         'index': index, 'spent_before': self._spent,
                         'base_scores': None if base_scores is None else [None if np.isneginf(v) else float(v) for v in base_scores],
                         'distances': None if distances is None else [None if np.isinf(v) else float(v) for v in distances],
                         'eliminated': eliminated,
                         'predicted': {k: np.asarray(v).tolist() if isinstance(v, np.ndarray) else v
                                       for k, v in predicted.items()}}
        self._proposals.append(deepcopy(selected))
        self._rng = candidate_rng
        return [deepcopy(selected)]

    def observe(self, observation):
        if self._pending is None or not isinstance(observation, dict):
            raise ValueError('An observation requires one owned pending proposal')
        config = observation.get('config')
        if config != self._pending['config']:
            raise ValueError('Observation configuration differs from pending proposal')
        status = observation.get('status', 'completed')
        value = observation.get('value', observation.get('objective_value', math.nan))
        if isinstance(value, bool) or value is None:
            value = math.nan
        value = float(value)
        if status == 'completed' and not math.isfinite(value):
            status = 'nan' if math.isnan(float(value)) else 'inf'
        row = {'config': deepcopy(config), 'value': float(value), 'cost': float(observation.get('cost', 0.)),
               'status': status, 'metadata': deepcopy(observation.get('metadata', {}))}
        result = SimpleNamespace(**{'trial_id': observation.get('trial_id', 'cost-trial-'+str(len(self.records))),
            'objective_value': row['value'], 'cost': row['cost'], 'metadata': row['metadata'], 'status': row['status'],
            'is_valid': lambda: status == 'completed' and math.isfinite(value)})
        record = observation_record(result, unit=self.cost_unit,
                                    timeout_assumption=observation.get('timeout_assumption', self.timeout_assumption))
        model = deepcopy(self.cost_model)
        model.observe(config, record)
        base = deepcopy(self.base_searcher)
        objective_row = None
        if status == 'completed':
            objective_row = {'config': deepcopy(config), 'value': float(value), 'cost': record.spent}
            base.observe(objective_row)
        self.cost_model, self.base_searcher = model, base
        self.records.append(record)
        self._spent = math.fsum(r.spent for r in self.records)
        self._trace.append({'proposal': deepcopy(self._pending), 'observation': record.to_dict(), 'spent': self._spent,
                            'objective_observation': objective_row,
                            'alpha_after': cooling(self._spent, self.total_budget, self.initial_budget)
                            if self._spent < self.total_budget else 0.})
        self._pending = None

    def observe_result(self, result, *, config, maximize=True):
        """Accept a Study ``Result`` while retaining invalid-work accounting.

        Legacy adapters historically dropped failed results before forwarding
        them. Cost evidence needs the executor metadata from every attempt, so
        this explicit bridge forwards valid objective values with the Study
        direction and forwards failures/timeouts with their original status.
        """
        if not isinstance(maximize, bool):
            raise ValueError('Study direction must be boolean')
        value = result.objective_value
        if value is not None and not isinstance(value, bool) and not maximize:
            value = -value
        self.observe({'trial_id': result.trial_id, 'config': deepcopy(config),
                      'value': value, 'cost': result.cost, 'status': result.status,
                      'metadata': deepcopy(result.metadata)})

    def state_dict(self):
        base = self.base_searcher.state_dict() if hasattr(self.base_searcher, 'state_dict') else self.base_searcher.get_state()
        payload = {'schema': 'cost_aware_proposal_searcher_v1', 'space': self.space_contract,
                   'base_kind': self._base_kind, 'base_state': base, 'seed': self.seed,
                   'total_budget': self.total_budget, 'initial_budget': self.initial_budget,
                   'candidate_count': self.candidate_count, 'cost_unit': self.cost_unit,
                   'timeout_assumption': self.timeout_assumption, 'cost_only': self.cost_only,
                   'study_name': self._study_name, 'maximize': self._maximize,
                   'cost_model': self.cost_model.state_dict(), 'records': [r.to_dict() for r in self.records],
                   'proposals': self._proposals, 'pending': self._pending, 'spent': self._spent,
                   'trace': self._trace, 'rng': self._rng.bit_generator.state}
        payload['sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return json.loads(json.dumps(payload, allow_nan=False))

    def load_state_dict(self, state):
        expected = self.state_dict()
        if (type(state) is not dict or set(state) != set(expected)
                or state.get('schema') != 'cost_aware_proposal_searcher_v1' or state.get('space') != self.space_contract):
            raise ValueError('Cost-aware checkpoint identity differs')
        checksum = state.get('sha256')
        payload = {k: v for k, v in state.items() if k != 'sha256'}
        if checksum != hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest():
            raise ValueError('Cost-aware checkpoint checksum differs')
        for key in ('base_kind', 'total_budget', 'initial_budget', 'candidate_count', 'cost_unit', 'cost_only', 'timeout_assumption'):
            if state.get(key) != expected.get(key):
                raise ValueError('Cost-aware checkpoint contract differs')
        if (type(state.get('seed')) is not int or state['seed'] < 0
                or not isinstance(state.get('records'), list)
                or not isinstance(state.get('proposals'), list)
                or not isinstance(state.get('trace'), list)
                or not isinstance(state.get('spent'), (int, float))
                or not math.isfinite(state['spent']) or state['spent'] < 0):
            raise ValueError('Malformed cost-aware checkpoint ledger')
        pending = state.get('pending')
        if pending is not None and not isinstance(pending, dict):
            raise ValueError('Malformed pending cost-aware proposal')
        expected_proposals = len(state['records']) + (1 if pending is not None else 0)
        if len(state['proposals']) != expected_proposals:
            raise ValueError('Cost-aware ledger lengths differ')
        if pending is not None:
            if pending.get('config') != state['proposals'][-1]:
                raise ValueError('Pending proposal is not the final proposal')
            if not isinstance(pending.get('pool'), list) or not pending['pool']:
                raise ValueError('Pending candidate pool is malformed')
        seen = set()
        for config in state['proposals']:
            self.space.validate_config(config)
            key = json.dumps(config, sort_keys=True, separators=(',', ':'))
            if key in seen:
                raise ValueError('Cost-aware proposals are not unique')
            seen.add(key)
        if pending is not None:
            for config in pending['pool']:
                self.space.validate_config(config)
        # Validate the model and record normalization before touching live state.
        model = CensoredCostGP.from_state(state['cost_model'], self.space)
        records = [CostRecord(**row) for row in state['records']]
        if [r.to_dict() for r in records] != state['records']:
            raise ValueError('Cost record normalization differs')
        if math.fsum(r.spent for r in records) != state['spent']:
            raise ValueError('Cost accounting differs')
        if [r.to_dict() for r in model.records] != [r.to_dict() for r in records]:
            raise ValueError('Cost-model and accounting ledgers differ')
        if model._configs != state['proposals'][:len(records)]:
            raise ValueError('Cost-model configurations differ from observed proposals')
        if model.contract != self.cost_model.contract or any(r.unit != self.cost_unit for r in records):
            raise ValueError('Cost model recipe or units differ')
        if len(state['trace']) != len(records):
            raise ValueError('Cost-aware observation trace length differs')
        for index, (trace, record) in enumerate(zip(state['trace'], records)):
            spent = math.fsum(r.spent for r in records[:index])
            after = math.fsum(r.spent for r in records[:index+1])
            if (type(trace) is not dict or set(trace) != {'proposal', 'observation', 'spent', 'alpha_after', 'objective_observation'}
                    or trace['observation'] != record.to_dict() or trace['spent'] != after
                    or trace['alpha_after'] != cooling(after, self.total_budget, self.initial_budget)):
                raise ValueError('Cost-aware observation trace differs')
            self._validate_proposal(trace['proposal'], state['proposals'][index], spent)
            row = trace['objective_observation']
            if row is not None and (type(row) is not dict or set(row) != {'config', 'value', 'cost'}
                    or row['config'] != state['proposals'][index] or row['cost'] != record.spent
                    or type(row['value']) not in (int, float) or not math.isfinite(row['value'])):
                raise ValueError('Cost-aware objective trace differs')
            if record.kind == 'complete' and row is None:
                raise ValueError('Completed cost lacks its objective observation')
        if pending is not None:
            self._validate_proposal(pending, state['proposals'][-1], state['spent'])
        if ((state['study_name'] is None) != (state['maximize'] is None)
                or (state['study_name'] is not None and (type(state['study_name']) is not str
                    or not state['study_name'] or type(state['maximize']) is not bool))):
            raise ValueError('Cost-aware Study identity is malformed')
        candidate_base = deepcopy(self.base_searcher)
        if hasattr(candidate_base, 'load_state_dict'):
            candidate_base.load_state_dict(deepcopy(state['base_state']))
        else:
            candidate_base.set_state(deepcopy(state['base_state']))
        if hasattr(candidate_base, 'validate_observations'):
            candidate_base.validate_observations([t['objective_observation'] for t in state['trace']
                                                  if t['objective_observation'] is not None])
        candidate_rng = np.random.default_rng()
        try:
            candidate_rng.bit_generator.state = deepcopy(state['rng'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Malformed cost-aware RNG state')
        # Commit only after every component has been validated on detached copies.
        self.base_searcher = candidate_base
        self.seed = state['seed']
        self._study_name, self._maximize = state['study_name'], state['maximize']
        self.cost_model = model; self.records = records; self._proposals = deepcopy(state['proposals'])
        self._pending = deepcopy(pending); self._spent = float(state['spent']); self._trace = deepcopy(state['trace'])
        self._rng = candidate_rng

    def _validate_proposal(self, proposal, config, spent):
        required = {'config', 'pool', 'alpha', 'base_source', 'index', 'spent_before',
                    'base_scores', 'distances', 'eliminated', 'predicted'}
        if type(proposal) is not dict or set(proposal) != required or proposal['config'] != config:
            raise ValueError('Malformed cost-aware proposal trace')
        pool = proposal['pool']
        if (not isinstance(pool, list) or not 1 <= len(pool) <= self.candidate_count
                or type(proposal['index']) is not int or not 0 <= proposal['index'] < len(pool)
                or pool[proposal['index']] != config or proposal['spent_before'] != spent
                or spent >= self.total_budget):
            raise ValueError('Cost-aware selection trace differs')
        for candidate in pool:
            self.cost_model.geometry.validate(candidate)
        if len({config_key(c) for c in pool}) != len(pool):
            raise ValueError('Duplicate cost-aware candidate')
        predicted = proposal['predicted']
        if type(predicted) is not dict:
            raise ValueError('Malformed predicted costs')
        for name in ('log_expected_cost', 'log_second_moment', 'cost_cv_squared'):
            values = np.asarray(predicted.get(name), dtype=float)
            if values.shape != (len(pool),) or not np.isfinite(values).all():
                raise ValueError('Malformed predicted cost moments')
        first, second, cv = (np.asarray(predicted[k]) for k in ('log_expected_cost', 'log_second_moment', 'cost_cv_squared'))
        if (np.any(cv < 0) or not np.allclose(second-2*first, np.log1p(cv), rtol=1e-9, atol=1e-9)):
            raise ValueError('Predicted cost moments disagree')
        if spent < self.initial_budget:
            if proposal['base_source'] != 'cheap_first_warmup' or proposal['alpha'] != 1. or proposal['base_scores'] is not None:
                raise ValueError('Initial cost selection trace differs')
            if not isinstance(proposal['distances'], list) or len(proposal['distances']) != len(pool):
                raise ValueError('Initial design distances differ')
            distances = [math.inf if d is None else d for d in proposal['distances']]
            index, eliminated = cheap_first(first, distances)
            if eliminated != proposal['eliminated']:
                raise ValueError('Initial design elimination trace differs')
        else:
            alpha = cooling(spent, self.total_budget, self.initial_budget)
            if (proposal['base_source'] != ('explicit_cost_only' if self.cost_only else 'log_expected_improvement')
                    or proposal['alpha'] != alpha or proposal['distances'] is not None or proposal['eliminated'] != []
                    or not isinstance(proposal['base_scores'], list) or len(proposal['base_scores']) != len(pool)):
                raise ValueError('Cost-aware acquisition trace differs')
            scores = np.asarray([-math.inf if v is None else v for v in proposal['base_scores']], dtype=float)
            if np.isnan(scores).any() or np.isposinf(scores).any():
                raise ValueError('Invalid checkpoint acquisition score')
            index = int(np.argmax(scores-alpha*first))
        if index != proposal['index']:
            raise ValueError('Cost-aware selected candidate differs')

    def validate_study_snapshot(self, state):
        """Bind the wrapper ledger to the owning Study before atomic recovery."""
        if state['study_name'] != self._study_name or state['maximize'] != self._maximize:
            raise ValueError('Cost-aware Study identity differs')
        trials, results = state['trials'], state['results']
        if len(trials) != len(self._proposals) or len(results) != len(self.records):
            raise ValueError('Cost-aware Study ledger lengths differ')
        history = state['searcher_state']['history']
        if json.dumps({r['trial_id']: r for r in history}, sort_keys=True) != json.dumps(results, sort_keys=True):
            raise ValueError('Cost-aware adapter history differs from Study results')
        if state['searcher_state']['trials'] != {tid: trial['config'] for tid, trial in trials.items()}:
            raise ValueError('Cost-aware adapter configurations differ from Study')
        for index, (record, trace) in enumerate(zip(self.records, self._trace)):
            if record.trial_id not in results:
                raise ValueError('Cost record missing from Study')
            result = results[record.trial_id]
            trial = trials[record.trial_id]
            if trial['config']['values'] != self._proposals[index] or result['fidelity'] != 1.:
                raise ValueError('Cost-aware Study configuration or fidelity differs')
            obj = result['objective_value']
            result_like = SimpleNamespace(**result, is_valid=lambda: result['status'] == 'completed' and math.isfinite(obj))
            rebuilt = observation_record(result_like, unit=self.cost_unit, timeout_assumption=self.timeout_assumption)
            if rebuilt != record:
                raise ValueError('Cost-aware Study measured work differs')
            row = trace['objective_observation']
            if row is not None and row['value'] != (obj if self._maximize else -obj):
                raise ValueError('Cost-aware Study objective direction differs')
        pending = state['pending']
        if len(pending) != int(self._pending is not None):
            raise ValueError('Cost-aware Study pending count differs')
        if pending and trials[pending[0]]['config']['values'] != self._pending['config']:
            raise ValueError('Cost-aware Study pending configuration differs')
