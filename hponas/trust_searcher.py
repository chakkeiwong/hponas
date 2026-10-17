"""Sequential, noiseless TuRBO-style search with typed local GP geometry.

The continuous controller follows the pinned TuRBO reference. Typed geometry,
unique proposals, bounded fits, and explicit finite exhaustion are declared
extensions. GP posterior draws are correlated Gaussian Thompson samples.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import math
import sys

import gpytorch
import numpy as np
import scipy
import torch
from gpytorch.constraints import Interval
from gpytorch.distributions import MultivariateNormal
from gpytorch.kernels import ScaleKernel
from gpytorch.likelihoods import GaussianLikelihood
from gpytorch.means import ConstantMean
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.models import ExactGP

from hponas.searchers.base import BaseSearcher, SearchSpaceExhaustedError
from hponas.searchers.gp_searcher import _GP_RUNTIME_LOCK
from hponas.trust_controller import Controller, Options, digest
from hponas.trust_space import MixedKernel, TrustSpace
from hponas.types import Config, Result, Trial


def _result_state(result):
    row = deepcopy(result.to_dict())
    value = row['objective_value']
    if not math.isfinite(value):
        row['objective_value'] = {'nonfinite': 'nan' if math.isnan(value) else 'inf' if value > 0 else '-inf'}
    return row


def _result_from_state(row):
    row = deepcopy(row)
    if isinstance(row.get('objective_value'), dict):
        value = row['objective_value']
        if set(value) != {'nonfinite'} or value['nonfinite'] not in {'nan', 'inf', '-inf'}:
            raise ValueError('Malformed nonfinite objective')
        row['objective_value'] = float(value['nonfinite'])
    return Result(**row)


class LocalGP(ExactGP):
    """Exact conditioned GP; a small fitted nugget regularizes noiseless data."""

    def __init__(self, x, y, numeric, categorical):
        likelihood = GaussianLikelihood(noise_constraint=Interval(1e-6, .1)).double()
        super().__init__(x, y, likelihood)
        self.mean_module = ConstantMean().double()
        self.covar_module = ScaleKernel(MixedKernel(numeric, categorical)).double()
        self.likelihood.noise = .001
        self.covar_module.outputscale = 1.
        if numeric:
            self.kernel.numeric.lengthscale = .5
        if categorical:
            self.kernel.categorical.lengthscale = .5

    @property
    def kernel(self):
        return self.covar_module.base_kernel

    def forward(self, x):
        return MultivariateNormal(self.mean_module(x), self.covar_module(x))


class TrustRegionSearcher(BaseSearcher):
    """One pending evaluation, one local region, fixed-fidelity observations.

    Noisy objectives, asynchronous batches and multifidelity schedulers require
    different incumbent/update contracts and are refused. The supported bounded
    envelope is <=512 observations per region and <=512 posterior candidates.
    Checkpoint restoration replays geometry, controller, binding and acquisition
    using retained fitted parameters, without repeating old optimizer fits.
    """

    from hponas.capabilities import SearcherCapabilities, MIXED
    support = SearcherCapabilities(MIXED, conditionals=True, concurrent_proposals=False, max_dimensions=64)

    def __init__(self, search_space, *, seed=0, initial_random=4, candidate_count=256,
                 fit_steps=20, controller=None, maximize=False, allow_noisy=False,
                 allow_batch=False):
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError('A nonnegative 64-bit seed is required')
        for name, value, cap in [('initial_random', initial_random, 512),
                                 ('candidate_count', candidate_count, 512), ('fit_steps', fit_steps, 200)]:
            if type(value) is not int or not 1 <= value <= cap:
                raise ValueError(f'{name} must be an integer in [1,{cap}]')
        if type(allow_noisy) is not bool or type(allow_batch) is not bool or allow_noisy or allow_batch:
            raise ValueError('Noisy and batch trust-region semantics are unsupported')
        super().__init__(search_space, seed)
        self.space = TrustSpace(search_space)
        self.initial_random, self.candidate_count, self.fit_steps = initial_random, candidate_count, fit_steps
        dimension = len(self.space.space.knobs)
        if controller is None:
            controller = Controller(Options(dimension, .8, 2**-7, 1.6, 3, max(4, dimension),
                                            relative_improvement=.001, geometry='typed_product_v1'))
        if (not isinstance(controller, Controller) or controller.options.dimension != dimension
                or controller.snapshot()['status'] != 'needs_initialization'
                or controller.state_dict()['payload']['journal']):
            raise ValueError('A fresh dimension-compatible controller is required')
        if controller.options.geometry == 'continuous' and any(
                k.kind != 'continuous' or k.condition for k in self.space.space.knobs):
            raise ValueError('Mixed spaces require typed controller geometry')
        self.controller = deepcopy(controller)
        self._proposals, self._generations, self._fits, self._events = [], [], [], []
        self._local_ids, self._initial_queue = [], []
        self._phase, self._generation = 'restart', -1
        self._pending, self._center_id = None, None
        self._exhausted = False
        self._rng = np.random.default_rng(seed)
        self.maximize = maximize

    @property
    def maximize(self):
        return self._maximize

    @maximize.setter
    def maximize(self, value):
        if type(value) is not bool:
            raise ValueError('Objective direction must be boolean')
        if self._proposals and value != self._maximize:
            raise ValueError('Cannot change objective direction after proposing work')
        self._maximize = value

    @property
    def contract(self):
        return {'schema': 'trust_searcher_v2', 'space': self.space.space.to_dict(),
                'initial_random': self.initial_random, 'candidate_count': self.candidate_count,
                'fit_steps': self.fit_steps, 'controller_options': asdict(self.controller.options),
                'method': 'typed-turbo-q1-matern52-hamming-predictive-thompson-v1',
                'fit': 'exact-gp; median/population-std; Adam(lr=.05); fresh fit each proposal',
                'arithmetic': 'cpu-float64; one-thread; exact-cholesky',
                'initialization': 'global-Latin-hypercube; finite-domain-without-replacement',
                'sampling': 'correlated Gaussian predictive draw including fitted nugget',
                'noise': 'noiseless-objective; nugget-in-[1e-6,.1]', 'batch': 'q=1',
                'restart': 'fresh-local-history; shrinkage-or-proven-empty-typed-region',
                'duplicates': 'exclude-all-proposed-configurations', 'max_local_observations': 512,
                'versions': {'python': list(sys.version_info[:2]), 'numpy': np.__version__,
                             'scipy': scipy.__version__, 'torch': str(torch.__version__),
                             'gpytorch': gpytorch.__version__}}

    @property
    def capabilities(self):
        return {**super().capabilities, 'trust_region': True, 'mixed_space': True, 'conditional': True,
                'supports_noise': False, 'supports_batch': False, 'supports_fidelity': False, 'max_dim': 64}

    def validate_study_controls(self, max_concurrent, scheduler):
        if max_concurrent != 1 or scheduler is not None:
            raise ValueError('Trust search requires sequential fixed-fidelity Study controls')

    def _signed(self, result):
        return -result.objective_value if self.maximize else result.objective_value

    def _valid_local(self):
        return [r for r in self.history if r.trial_id in self._local_ids and r.is_valid()]

    def _excluded(self):
        return [p['config'] for p in self._proposals]

    def _start_generation(self):
        design, exhausted = self.space.initial_design(self._rng, count=self.initial_random, exclude=self._excluded())
        if exhausted:
            self._mark_exhausted()
        if not design or (len(design) < self.initial_random and self.space.finite_configs() is None):
            raise RuntimeError('Bounded global design did not find enough distinct points; exhaustion is unproved')
        self._generation += 1
        self._generations.append({'generation': self._generation, 'design': deepcopy(design),
                                  'controller_before': self.controller.snapshot()})
        self._local_ids, self._center_id = [], None
        self._initial_queue, self._phase = design, 'initial'

    def _mark_exhausted(self):
        self._exhausted = True
        self._events.append({'action': 'exhausted'})
        raise SearchSpaceExhaustedError('All configurations in the declared finite space were proposed')

    def _fit(self):
        results = self._valid_local()
        if not results or len(results) > 512:
            raise RuntimeError('Local GP requires between 1 and 512 valid observations')
        rows = [self.space.features(self.trials[r.trial_id].values) for r in results]
        values = [self._signed(r) for r in results]
        median, scale = float(np.median(values)), float(np.std(values))
        if scale < 1e-6:
            scale = 1.
        x = torch.tensor(rows, dtype=torch.double)
        y = (torch.tensor(values, dtype=torch.double) - median) / scale
        model = LocalGP(x, y, self.space.n_numeric, len(self.space.categorical))
        fit = {'train_ids': [r.trial_id for r in results], 'median': median, 'scale': scale,
               'data_sha256': digest({'features': rows, 'values': values})}
        if hasattr(self, '_replay_fits'):
            retained = self._replay_fits[self._replay_fit_index]
            self._replay_fit_index += 1
            if any(retained.get(key) != value for key, value in fit.items()):
                raise ValueError('Fitted model uses a different local observation history')
            parameters = dict(model.named_parameters())
            if set(retained['parameters']) != set(parameters):
                raise ValueError('Fitted parameter identity differs')
            with torch.no_grad():
                for name, parameter in parameters.items():
                    value = torch.tensor(retained['parameters'][name], dtype=parameter.dtype)
                    if value.shape != parameter.shape or not torch.isfinite(value).all():
                        raise ValueError('Invalid fitted parameter shape or value')
                    parameter.copy_(value)
        else:
            model.train()
            model.likelihood.train()
            objective = ExactMarginalLogLikelihood(model.likelihood, model)
            optimizer = torch.optim.Adam(model.parameters(), lr=.05)
            for _ in range(self.fit_steps):
                optimizer.zero_grad()
                loss = -objective(model(x), y)
                if not torch.isfinite(loss):
                    raise RuntimeError('Local GP fit produced nonfinite marginal likelihood')
                loss.backward()
                optimizer.step()
        fit['parameters'] = {name: p.detach().tolist() for name, p in model.named_parameters()}
        digest(fit)  # Refuse nonfinite state before adopting it.
        self._fits.append(fit)
        model.eval()
        model.likelihood.eval()
        return model

    def suggest(self):
        if self._pending is not None:
            raise ValueError('One trust-region proposal is already pending')
        if self._exhausted:
            raise SearchSpaceExhaustedError('The declared finite space is exhausted')
        previous = deepcopy(self.__dict__)
        with _GP_RUNTIME_LOCK:
            previous_threads = torch.get_num_threads()
            try:
                torch.set_num_threads(1)
                with torch.random.fork_rng(devices=[]), gpytorch.settings.max_cholesky_size(1000000), \
                        gpytorch.settings.fast_computations(covar_root_decomposition=False, log_prob=False, solves=False):
                    return self._suggest_impl()
            except SearchSpaceExhaustedError:
                raise
            except BaseException:
                self.__dict__.clear()
                self.__dict__.update(previous)
                raise
            finally:
                torch.set_num_threads(previous_threads)

    def _suggest_impl(self):
        if self._phase == 'restart':
            self._start_generation()
        selection = None
        if self._phase == 'active':
            # Prove global exhaustion before spending a GP fit.
            finite = self.space.finite_configs()
            if finite is not None and len(self._proposals) == len(finite):
                self._mark_exhausted()
            model = self._fit()
            center = self.trials[self._center_id].values
            scales = self.space.logical_lengthscales(model.kernel)
            choices, region, complete_domain = self.space.candidates(
                center, self.controller.snapshot()['length'], scales, self._rng,
                count=self.candidate_count, exclude=self._excluded())
            if not choices:
                if not complete_domain:
                    raise RuntimeError('Bounded candidate generation failed; finite exhaustion is unproved')
                self.controller.retire('empty_typed_region')
                self._phase = 'restart'
                self._start_generation()
            else:
                sampling_seed = int(self._rng.integers(2**63))
                torch.random.default_generator.manual_seed(sampling_seed)
                x = torch.tensor([self.space.features(c) for c in choices], dtype=torch.double)
                with torch.no_grad():
                    posterior = model.likelihood(model(x))
                    sample = posterior.rsample()
                if not torch.isfinite(sample).all():
                    raise RuntimeError('Nonfinite posterior Thompson sample')
                index = int(torch.argmin(sample))
                values = choices[index]
                selection = {'fit_index': len(self._fits)-1, 'center': deepcopy(center), 'scales': scales,
                             'region': region, 'candidates': choices, 'sampling_seed': sampling_seed,
                             'posterior_mean': posterior.mean.tolist(), 'sample': sample.tolist(), 'index': index}
        kind = 'initial' if self._phase == 'initial' else 'thompson'
        if kind == 'initial':
            values = self._initial_queue.pop(0)
        self.space.validate(values)
        draw_id = f'trust-draw-{len(self._proposals)}'
        if kind == 'thompson':
            self.controller.propose(draw_id, [float(v) for v in self.space.encoder.encode(values)], selection['scales'])
        proposal = {'draw_id': draw_id, 'config': deepcopy(values), 'generation': self._generation,
                    'kind': kind, 'selection': selection, 'trial_id': None}
        self._proposals.append(proposal)
        self._pending = len(self._proposals)-1
        self._events.append({'action': 'suggest'})
        return Config(deepcopy(values), draw_id)

    def register_trial(self, trial):
        if self._pending is None or not isinstance(trial, Trial):
            raise ValueError('A retained pending trust proposal is required')
        row = self._proposals[self._pending]
        if (row['trial_id'] is not None or type(trial.trial_id) is not str or not trial.trial_id
                or any(p['trial_id'] == trial.trial_id for p in self._proposals)
                or trial.config != Config(row['config'], row['draw_id'])
                or self.trials.get(trial.trial_id) != trial.config
                or trial.fidelity != 1 or type(trial.fidelity) is bool
                or trial.parent_trial_id is not None or trial.resume_from != 0
                or trial.root_trial_id not in {None, trial.trial_id}):
            raise ValueError('Trust trial binding, lineage or fixed fidelity differs')
        row['trial_id'] = trial.trial_id
        self._local_ids.append(trial.trial_id)
        self._events.append({'action': 'register', 'trial_id': trial.trial_id})

    def observe(self, result):
        if (not isinstance(result, Result) or self._pending is None
                or result.trial_id not in self.trials or result.fidelity != 1
                or type(result.fidelity) is bool or type(result.cost) not in (int, float)
                or not math.isfinite(result.cost) or result.cost < 0
                or type(result.objective_value) not in (int, float)
                or result.status not in {'completed', 'failed', 'nan', 'inf', 'timeout', 'cancelled', 'pruned'}):
            raise ValueError('A new bound fixed-fidelity result with finite work is required')
        row = self._proposals[self._pending]
        if (row['trial_id'] != result.trial_id
                or self.trials[result.trial_id] != Config(row['config'], row['draw_id'])):
            raise ValueError('Observation differs from the pending trust proposal')
        packed = _result_state(result)
        digest(packed)
        if row['kind'] == 'thompson':
            if result.is_valid():
                self.controller.observe(row['draw_id'], self._signed(result))
            else:
                self.controller.fail(row['draw_id'])
        super().observe(deepcopy(result))
        self._pending = None
        if self._phase == 'initial' and not self._initial_queue:
            valid = self._valid_local()
            if valid:
                best = min(valid, key=self._signed)
                self._center_id = best.trial_id
                self.controller.initialize(f'trust-initial-{self._generation}',
                    [float(v) for v in self.space.encoder.encode(self.trials[best.trial_id])], self._signed(best))
                self._phase = 'active'
            else:
                self._phase = 'restart'
        elif self._phase == 'active':
            self._center_id = min(self._valid_local(), key=self._signed).trial_id
            if self.controller.snapshot()['status'] == 'needs_restart':
                self._phase = 'restart'
        self._events.append({'action': 'observe', 'result': packed})

    def get_state(self):
        payload = {'kind': 'trust_region_searcher_v2', 'contract': self.contract,
                   'seed': self.seed, 'maximize': self.maximize,
                   'history': [_result_state(r) for r in self.history],
                   'trials': {tid: config.to_dict() for tid, config in self.trials.items()},
                   'controller': self.controller.state_dict(), 'pending': self._pending,
                   'proposals': self._proposals, 'generations': self._generations, 'fits': self._fits,
                   'local_ids': self._local_ids, 'initial_queue': self._initial_queue, 'phase': self._phase,
                   'generation': self._generation, 'center_id': self._center_id, 'exhausted': self._exhausted,
                   'events': self._events, 'rng': self._rng.bit_generator.state}
        return json.loads(json.dumps({**payload, 'sha256': digest(payload)}, allow_nan=False))

    def set_state(self, state):
        if (type(state) is not dict or set(state) != set(self.get_state())
                or state.get('kind') != 'trust_region_searcher_v2' or state.get('contract') != self.contract
                or type(state.get('events')) is not list or len(state['events']) > 100000):
            raise ValueError('Trust searcher identity or checkpoint schema differs')
        if digest({k: v for k, v in state.items() if k != 'sha256'}) != state['sha256']:
            raise ValueError('Trust checkpoint content checksum differs')
        target = type(self)(self.search_space, seed=state['seed'], initial_random=self.initial_random,
            candidate_count=self.candidate_count, fit_steps=self.fit_steps,
            controller=Controller(self.controller.options), maximize=state['maximize'])
        target._replay_fits, target._replay_fit_index = deepcopy(state['fits']), 0
        try:
            for event in state['events']:
                if event == {'action': 'suggest'}:
                    target.suggest()
                elif event == {'action': 'exhausted'}:
                    try:
                        target.suggest()
                    except SearchSpaceExhaustedError:
                        pass
                    else:
                        raise ValueError('Checkpoint claims unproved exhaustion')
                elif type(event) is dict and set(event) == {'action', 'trial_id'} and event['action'] == 'register':
                    proposal = target._proposals[target._pending]
                    config = Config(deepcopy(proposal['config']), proposal['draw_id'])
                    target.trials[event['trial_id']] = config
                    target.register_trial(Trial(config, event['trial_id']))
                elif type(event) is dict and set(event) == {'action', 'result'} and event['action'] == 'observe':
                    target.observe(_result_from_state(event['result']))
                else:
                    raise ValueError('Unknown checkpoint event')
            if target._replay_fit_index != len(target._replay_fits):
                raise ValueError('Unused fitted model state')
            del target._replay_fits, target._replay_fit_index
            if target.get_state() != state:
                raise ValueError('Trust checkpoint disagrees with replayed local/controller/acquisition state')
        except (KeyError, TypeError, IndexError, RuntimeError, OverflowError) as exc:
            raise ValueError('Invalid trust checkpoint replay: '+str(exc)) from exc
        self.__dict__.clear()
        self.__dict__.update(target.__dict__)

    def validate_study_snapshot(self, state):
        if (state['maximize'] != self.maximize or state['n_suggested'] != len(self._proposals)
                or state['pending'] != ([] if self._pending is None else [self._proposals[self._pending]['trial_id']])
                or {tid: row['config'] for tid, row in state['trials'].items()}
                != {tid: cfg.to_dict() for tid, cfg in self.trials.items()}):
            raise ValueError('Trust proposal/direction ledger differs from Study')
        if [_result_state(Result(**row)) for row in state['results'].values()] != [_result_state(r) for r in self.history]:
            raise ValueError('Trust observation ledger differs from Study')
        for tid, trial in state['trials'].items():
            if state['roots'][tid] != tid or trial['fidelity'] != 1 or trial['parent_trial_id'] is not None:
                raise ValueError('Trust fixed-fidelity lineage differs from Study')
        if (state['stop_reason'] == 'search_space_exhausted') != self._exhausted:
            raise ValueError('Trust exhaustion differs from Study')
