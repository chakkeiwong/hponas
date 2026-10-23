"""Opt-in fixed-kernel rank-weighted GP transfer from declared tuning history.

This bounded RGPE variant uses independent task standardization, posterior
rank probabilities with equal tie shares, target leave-one-out ranking and
scalar EI over a bounded candidate pool. It makes no transfer-speedup claim.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import math

import numpy as np
from scipy.special import ndtr

from hponas.capabilities import SearcherCapabilities
from hponas.encoding import SpaceEncoder, as_knob_space
from hponas.evaluation import EvaluationController, StudyDeclaration
from hponas.searchers.base import (BaseSearcher, PendingSuggestionError,
                                   SearchBudgetExhaustedError, SearchSpaceExhaustedError)
from hponas.types import Config, Result, Trial
from hponas.warm_history import digest, physical_key, select, space_signature
from hponas.warm_start import BaseState, checkpoint_digest


def ranking_loss(samples, target):
    """Ordered-pair disagreements; 3D samples index LOO model, then point."""
    samples, target = np.asarray(samples, dtype=float), np.asarray(target, dtype=float)
    if (target.ndim != 1 or not len(target) or samples.ndim not in (2, 3)
            or samples.shape[-1] != len(target) or not len(samples)
            or samples.ndim == 3 and samples.shape[1] != len(target)
            or not np.isfinite(samples).all() or not np.isfinite(target).all()):
        raise ValueError('Finite posterior samples and matching target points required')
    actual = target[:, None] < target[None, :]
    if samples.ndim == 2:
        predicted = samples[:, :, None] < samples[:, None, :]
    else:
        held_out = np.diagonal(samples, axis1=1, axis2=2)
        predicted = held_out[:, :, None] < samples
    return np.count_nonzero(predicted != actual, axis=(1, 2))


def rank_weights(losses):
    """Monte Carlo probability of lowest loss, splitting each sample's ties."""
    losses = np.asarray(losses)
    if (losses.ndim != 2 or not all(losses.shape) or not np.isfinite(losses).all()
            or (losses < 0).any()):
        raise ValueError('Finite nonnegative model-by-sample ranking losses required')
    winners = losses == losses.min(axis=0)
    return (winners / winners.sum(axis=0)).mean(axis=1)


def combine_posteriors(means, covariances, weights):
    """Posterior of the weighted sum of independent GPs, in common units."""
    means, covariances, weights = (np.asarray(v, dtype=float) for v in (means, covariances, weights))
    if (means.ndim != 2 or covariances.shape != (len(means), means.shape[1], means.shape[1])
            or weights.shape != (len(means),) or not np.isfinite(means).all()
            or not np.isfinite(covariances).all() or not np.isfinite(weights).all()
            or (weights < 0).any() or not np.isclose(weights.sum(), 1.)):
        raise ValueError('Matching finite GP posteriors and normalized weights required')
    for covariance in covariances:
        if (not np.allclose(covariance, covariance.T, rtol=0., atol=1e-10)
                or np.linalg.eigvalsh(covariance).min(initial=0.) < -1e-8):
            raise ValueError('GP covariance must be symmetric positive semidefinite')
    return weights @ means, np.einsum('m,mij->ij', weights**2, covariances)


class FixedKernelGP:
    """Exact RBF conditioning with fixed normalized-coordinate hyperparameters."""
    def __init__(self, x, y, *, lengthscale=.25, noise=1e-6):
        self.x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if (self.x.ndim != 2 or not self.x.shape[1] or y.shape != (len(self.x),) or not len(y)
                or not np.isfinite(self.x).all() or not np.isfinite(y).all()
                or type(lengthscale) not in (int, float) or not math.isfinite(lengthscale) or lengthscale <= 0
                or type(noise) not in (int, float) or not math.isfinite(noise) or noise <= 0):
            raise ValueError('Finite GP training data, lengthscale and positive noise required')
        self.lengthscale, self.noise = lengthscale, noise
        self.center = float(y.mean())
        self.scale = float(y.std()) or 1.
        if not math.isfinite(self.center) or not math.isfinite(self.scale):
            raise ValueError('GP objective normalization overflowed')
        self.y = (y-self.center)/self.scale
        self.chol = np.linalg.cholesky(self.kernel(self.x, self.x) + noise*np.eye(len(y)))
        self.alpha = np.linalg.solve(self.chol.T, np.linalg.solve(self.chol, self.y))
        if not np.isfinite(self.alpha).all():
            raise ValueError('GP conditioning overflowed')

    def kernel(self, a, b):
        with np.errstate(over='raise', invalid='raise'):
            try:
                return np.exp(-.5 * np.sum(((a[:, None, :]-b[None, :, :])/self.lengthscale)**2, axis=-1))
            except FloatingPointError as exc:
                raise ValueError('GP kernel coordinates overflowed') from exc

    def posterior(self, x):
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[1] != self.x.shape[1] or not np.isfinite(x).all():
            raise ValueError('Finite matching GP prediction coordinates required')
        cross = self.kernel(self.x, x)
        solved = np.linalg.solve(self.chol, cross)
        covariance = self.kernel(x, x) - solved.T @ solved
        covariance = (covariance+covariance.T)/2
        return cross.T @ self.alpha, covariance


def _draw(model, x, count, rng):
    mean, covariance = model.posterior(x)
    values, vectors = np.linalg.eigh(covariance)
    if values.min(initial=0.) < -1e-8:
        raise ValueError('GP posterior covariance is not positive semidefinite')
    return mean + rng.standard_normal((count, len(x))) @ (vectors*np.sqrt(np.maximum(values, 0.))).T


def _declaration(declaration, context):
    if (not isinstance(declaration, StudyDeclaration) or len(declaration.objectives) != 1
            or declaration.streaming_steps or not declaration.final_folds
            or context['objective_key'] != declaration.objective_id
            or context['direction'] != {'min': 'minimize', 'max': 'maximize'}[declaration.objectives[0].direction]
            or context['endpoint_fidelity'] != 1.):
        raise ValueError('RGPE requires a matching scalar endpoint declaration with protected final roles')


def _source_reason(source, target):
    for key in ('objective_id', 'model_id', 'protocol_id'):
        if getattr(source, key) != getattr(target, key):
            return 'incompatible_declaration_'+key
    if source.objectives != target.objectives or source.streaming_steps:
        return 'incompatible_declaration_objectives'
    if source.data_id == target.data_id:
        exposed = {v for f in source.tuning_folds for v in f.train_ids+f.score_ids}
        protected = {v for f in target.final_folds for v in f.score_ids}
        groups = {v for f in source.tuning_folds for v in f.train_groups+f.score_groups}
        final_groups = {v for f in target.final_folds for v in f.score_groups}
        if exposed & protected or groups & final_groups:
            return 'protected_target_final_exposure'
    return None


def _tuning_aggregate(declaration, trial, repetitions, *, cancelled=False):
    controller = EvaluationController(declaration, maximize=declaration.objectives[0].direction == 'max')
    expected = controller.tasks(trial, 'tuning')
    if not isinstance(repetitions, list) or len(repetitions) != len(expected):
        raise ValueError('Incomplete declared tuning repetitions')
    for repetition, (fold, seed, rid) in zip(repetitions, expected):
        if (set(repetition) != {'fold', 'seed', 'result'}
                or repetition['fold'] != fold.name or type(repetition['seed']) is not int or repetition['seed'] != seed):
            raise ValueError('Tuning repetition identity differs')
        controller.validate_record(Result(**repetition['result']), rid, trial.fidelity)
    return controller.aggregate(trial, repetitions, cancelled=cancelled)


def _valid_source_rows(history):
    return [row for row in history['trials'] if row['status'] == 'completed' and row['fidelity'] == 1.
            and type(row['value']) in (float, int) and math.isfinite(row['value'])]


def _verify_source(source, target, space):
    history = source['history']
    if (history.get('schema') != 'warm_history_snapshot_v1'
            or history.get('binding') != digest({k: v for k, v in history.items() if k != 'binding'})):
        raise ValueError('RGPE source history binding differs')
    declared = StudyDeclaration.from_contract(source['declaration'])
    if (_source_reason(declared, target) or history['objective_key'] != declared.objective_id
            or history['direction'] != {'min': 'minimize', 'max': 'maximize'}[declared.objectives[0].direction]):
        raise ValueError('RGPE source declaration or protected final roles differ')
    rows = _valid_source_rows(history)
    proof = source['tuning_proof']
    if len(rows) > 128 or not isinstance(proof, list) or len(proof) != len(rows):
        raise ValueError('RGPE source tuning proof or 128-point bound differs')
    for row, record in zip(rows, proof):
        physical_key(space, row['config'])
        if (set(record) != {'trial_id', 'config', 'value', 'role', 'evaluation_identity', 'repetitions'}
                or any(record[k] != row[k] for k in ('trial_id', 'config', 'value'))
                or record['role'] != 'tuning' or record['evaluation_identity'] != declared.identity):
            raise ValueError('RGPE source tuning proof differs')
        trial = Trial(Config(row['config']), row['trial_id'])
        aggregate = _tuning_aggregate(declared, trial, record['repetitions'])
        if aggregate.status != 'completed' or aggregate.objective_value != row['value']:
            raise ValueError('RGPE source value differs from its declared tuning proof')


def _source_from_store(store, history, target):
    snapshot = store.load_study_snapshot(history['study_id'])
    if not snapshot or not snapshot.get('evaluation') or not snapshot.get('finished'):
        return None, 'missing_declared_tuning_proof'
    state = snapshot['evaluation']
    source = StudyDeclaration.from_contract(state['contract'])
    reason = _source_reason(source, target)
    if reason:
        return None, reason
    if state['identity'] != source.identity or snapshot['study_name'] != history['study_id']:
        raise ValueError('Source declaration or study identity differs')
    proof = []
    for row in _valid_source_rows(history):
        tid = row['trial_id']
        saved = snapshot['trials'].get(tid)
        measured = snapshot['results'].get(tid)
        if saved is None or measured is None:
            raise ValueError('Frozen history differs from its declared tuning snapshot')
        trial = Trial(**{**saved, 'config': Config(**saved['config'])})
        result = Result(**measured)
        repetitions = state['tuning'].get(tid, [])
        aggregate = _tuning_aggregate(source, trial, repetitions)
        if (trial.trial_id != tid or result.trial_id != tid
                or trial.status != 'completed' or result.status != 'completed' or aggregate.status != 'completed'
                or result.metadata.get('evaluation') != aggregate.metadata['evaluation']
                or result.objective_value != aggregate.objective_value or result.objective_value != row['value']
                or trial.config.values != row['config'] or trial.fidelity != 1. or result.fidelity != 1.
                or result.cost != aggregate.cost or trial.cost != result.cost or trial.value != result.objective_value):
            raise ValueError('Source measurement is not its declared tuning aggregate')
        proof.append({'trial_id': tid, 'config': deepcopy(row['config']), 'value': row['value'],
                      'role': 'tuning', 'evaluation_identity': source.identity,
                      'repetitions': deepcopy(repetitions)})
    return {'history': deepcopy(history), 'declaration': source.contract, 'tuning_proof': proof}, None


def prepare_rgpe_history(space, store, *, context, declaration, n_initial=4):
    """Freeze an eligible, role-checked bundle without any final measurements."""
    _declaration(declaration, context)
    if type(n_initial) is not int or not 2 <= n_initial <= 64:
        raise ValueError('RGPE initial count must be between 2 and 64')
    histories = store.read_warm_histories()
    screened = select(histories, context, space, 0)
    excluded = deepcopy(screened['excluded'])
    excluded_ids = {r['study_id'] for r in excluded}
    sources = []
    for history in histories:
        if history['study_id'] in excluded_ids:
            continue
        source, reason = _source_from_store(store, history, declaration)
        if reason:
            excluded.append({'study_id': history['study_id'], 'reason': reason})
        else:
            sources.append(source)
    selection = select([s['history'] for s in sources], context, space, n_initial)
    body = {'schema': 'declared_rgpe_history_v1', 'context': deepcopy(context),
            'target_declaration': declaration.contract, 'target_identity': declaration.identity,
            'selection': selection, 'sources': sources,
            'excluded': sorted(excluded, key=lambda r: r['study_id'])}
    return {**body, 'binding': digest(body)}


class RGPESearcher(BaseSearcher):
    """Ranked initialization, then bounded sequential scalar RGPE-EI proposals."""
    support = SearcherCapabilities(('continuous', 'ordinal'), concurrent_proposals=False, max_dimensions=20)

    def __init__(self, search_space, bundle, *, seed=0, n_initial=4, rank_samples=128,
                 n_candidates=128, candidates=None, lengthscale=.25, noise=1e-6):
        space = as_knob_space(search_space)
        if (not space.knobs or len(space.knobs) > 20
                or any(k.kind not in self.support.kinds or k.condition is not None for k in space.knobs)):
            raise ValueError('RGPE supports at most 20 unconditional continuous/ordinal coordinates')
        for value, low, high in ((n_initial, 2, 64), (rank_samples, 1, 512), (n_candidates, 1, 512)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('RGPE count exceeds its declared finite bound')
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('RGPE requires an explicit nonnegative 32-bit seed')
        # Validate numerical settings even before any GP can be fitted.
        FixedKernelGP([[0.]], [0.], lengthscale=lengthscale, noise=noise)
        body = {k: v for k, v in bundle.items() if k != 'binding'}
        if bundle.get('schema') != 'declared_rgpe_history_v1' or bundle.get('binding') != digest(body):
            raise ValueError('RGPE history bundle binding/schema differs')
        declaration = StudyDeclaration.from_contract(bundle['target_declaration'])
        _declaration(declaration, bundle['context'])
        if bundle['target_identity'] != declaration.identity or bundle['selection']['limit'] != n_initial:
            raise ValueError('RGPE target declaration or initial count differs')
        if len(bundle['sources']) > 16:
            raise ValueError('RGPE supports at most 16 source studies')
        expected = select([s['history'] for s in bundle['sources']], bundle['context'], space, n_initial)
        if expected != bundle['selection'] or expected['excluded']:
            raise ValueError('RGPE source eligibility or ranked selection differs')
        for source in bundle['sources']:
            _verify_source(source, declaration, search_space)
        super().__init__(search_space, seed)
        self._bundle, self._declaration = deepcopy(bundle), declaration
        self._encoder = SpaceEncoder(search_space)
        self._rng = np.random.default_rng(seed)
        self._settings = dict(n_initial=n_initial, rank_samples=rank_samples, n_candidates=n_candidates,
                              lengthscale=lengthscale, noise=noise)
        if candidates is None and all(k.kind == 'ordinal' and k.transform == 'none' for k in space.knobs):
            count = math.prod(k.bounds[1]-k.bounds[0]+1 for k in space.knobs)
            if count <= 512:
                candidates = [dict(zip([k.name for k in space.knobs], values))
                              for values in itertools.product(*(range(k.bounds[0], k.bounds[1]+1) for k in space.knobs))]
        self._candidates = None if candidates is None else deepcopy(list(candidates))
        if self._candidates is not None:
            if not 1 <= len(self._candidates) <= 512:
                raise ValueError('RGPE requires 1 to 512 distinct finite candidates')
            keys = [physical_key(search_space, c) for c in self._candidates]
            if len(set(keys)) != len(keys):
                raise ValueError('Duplicate RGPE candidates')
        self._ranked = [deepcopy(r['config']) for r in bundle['selection']['seeds']
                        if self._candidates is None or r['config'] in self._candidates]
        self._proposed = []

    @classmethod
    def from_store(cls, search_space, store, *, context, declaration, n_initial=4, **kwargs):
        bundle = prepare_rgpe_history(search_space, store, context=context, declaration=declaration, n_initial=n_initial)
        return cls(search_space, bundle, n_initial=n_initial, **kwargs)

    @classmethod
    def from_state(cls, search_space, state):
        """Restore the retained bundle without querying newly arrived histories."""
        searcher = cls(search_space, state['bundle'], seed=state['seed'],
                       candidates=state['candidates'], **state['settings'])
        searcher.set_state(state)
        return searcher

    @property
    def bundle(self):
        return deepcopy(self._bundle)

    @property
    def maximize(self):
        return self._bundle['context']['direction'] == 'maximize'

    @maximize.setter
    def maximize(self, value):
        if type(value) is not bool or value != self.maximize:
            raise ValueError('Study objective direction differs from RGPE target')

    @property
    def fallback_reason(self):
        return None if any(s['tuning_proof'] for s in self._bundle['sources']) else 'no_eligible_declared_history'

    def validate_study_context(self, study_name):
        if study_name != self._bundle['context']['study_id']:
            raise ValueError('Study identity differs from RGPE target')

    def validate_study_declaration(self, declaration):
        if declaration is None or declaration.contract != self._declaration.contract:
            raise ValueError('Study declaration differs from RGPE target protocol')

    def _points(self):
        return [(self.trials[r.trial_id].values, (-1 if self.maximize else 1)*r.objective_value)
                for r in self.history if r.status == 'completed' and r.is_valid()]

    def _ensemble(self):
        points = self._points()
        if len(points) < 2:
            raise ValueError('RGPE requires at least two completed target points')
        x = np.stack([self._encoder.encode(c) for c, _ in points])
        y = np.array([v for _, v in points])
        numerical = {k: self._settings[k] for k in ('lengthscale', 'noise')}
        models, names = [], []
        for source in self._bundle['sources']:
            rows = source['tuning_proof']
            if not rows:
                continue
            models.append(FixedKernelGP(np.stack([self._encoder.encode(r['config']) for r in rows]),
                          [(-1 if self.maximize else 1)*r['value'] for r in rows], **numerical))
            names.append(source['history']['study_id'])
        target = FixedKernelGP(x, y, **numerical)
        # Derived from immutable data, so posterior inspection does not advance
        # the proposal RNG or change a later recovered trajectory.
        derived = digest({'seed': self.seed, 'configs': [c for c, _ in points],
                          'sources': names, 'settings': self._settings})
        rng = np.random.default_rng(int(derived[:16], 16))
        count = self._settings['rank_samples']
        losses = [ranking_loss(_draw(model, x, count, rng), y) for model in models]
        loo = np.empty((count, len(y), len(y)))
        for i in range(len(y)):
            mask = np.arange(len(y)) != i
            loo[:, i, :] = _draw(FixedKernelGP(x[mask], y[mask], **numerical), x, count, rng)
        losses.append(ranking_loss(loo, y))
        return models+[target], rank_weights(losses), names+['target'], np.asarray(losses)

    def posterior(self, configs):
        """Mean/covariance in target physical objective units plus rank weights."""
        configs = list(configs)
        if not 1 <= len(configs) <= 512:
            raise ValueError('RGPE posterior query requires 1 to 512 candidates')
        x = np.stack([self._encoder.encode(c) for c in configs])
        models, weights, names, losses = self._ensemble()
        predictions = [model.posterior(x) for model in models]
        mean, covariance = combine_posteriors([m for m, _ in predictions], [c for _, c in predictions], weights)
        target = models[-1]
        sign = -1 if self.maximize else 1
        with np.errstate(over='ignore', invalid='ignore'):
            physical_mean = sign*(target.center+target.scale*mean)
            physical_covariance = target.scale*target.scale*covariance
        if not np.isfinite(physical_mean).all() or not np.isfinite(physical_covariance).all():
            raise ValueError('RGPE physical posterior scale overflowed')
        return {'mean': physical_mean, 'covariance': physical_covariance,
                'weights': dict(zip(names, map(float, weights))), 'ranking_losses': losses}

    def suggest(self):
        if len(self._proposed) != len(self.history):
            raise PendingSuggestionError('RGPE requires completion of its preceding sequential proposal')
        if len(self._points()) >= 64:
            raise SearchBudgetExhaustedError('RGPE 64-target-point fitting bound reached')
        seen = {physical_key(self.search_space, c) for c in self._proposed}
        if len(self._proposed) < len(self._ranked):
            config = deepcopy(self._ranked[len(self._proposed)])
        else:
            pool = self._candidates
            if pool is None:
                pool = [self._encoder.decode(self._rng.random(len(self._encoder.space.knobs)), sampling=True)
                        for _ in range(self._settings['n_candidates'])]
            unique = {}
            for c in pool:
                key = physical_key(self.search_space, c)
                if key not in seen:
                    unique.setdefault(key, c)
            pool = list(unique.values())
            if not pool:
                if self._candidates is None:
                    raise PendingSuggestionError('Bounded RGPE candidate draw found no new configuration')
                raise SearchSpaceExhaustedError('RGPE finite candidate set exhausted')
            if len(self._proposed) < self._settings['n_initial'] or len(self._points()) < 2:
                config = deepcopy(pool[int(self._rng.integers(len(pool)))])
            else:
                posterior = self.posterior(pool)
                sign = -1 if self.maximize else 1
                mean = sign*posterior['mean']
                std = np.sqrt(np.maximum(np.diag(posterior['covariance']), 0.))
                improvement = min(v for _, v in self._points()) - mean
                z = np.divide(improvement, std, out=np.zeros_like(improvement), where=std > 0)
                ei = np.where(std > 0, improvement*ndtr(z)+std*np.exp(-z*z/2)/math.sqrt(2*math.pi),
                              np.maximum(improvement, 0.))
                config = deepcopy(pool[int(np.argmax(ei))])
        self._proposed.append(deepcopy(config))
        return Config(config)

    def observe(self, result):
        if any(r.trial_id == result.trial_id for r in self.history):
            old = next(r for r in self.history if r.trial_id == result.trial_id)
            if checkpoint_digest(old.to_dict()) != checkpoint_digest(result.to_dict()):
                raise ValueError('RGPE cannot replace an acknowledged target measurement')
            return
        if (len(self.history) >= len(self._proposed) or result.trial_id not in self.trials
                or self.trials[result.trial_id].values != self._proposed[len(self.history)]
                or result.fidelity != 1. or result.metadata.get('evaluation', {}).get('role') != 'tuning'
                or result.metadata['evaluation'].get('identity') != self._declaration.identity
                or result.status not in {'completed', 'failed', 'timeout', 'nan', 'inf', 'cancelled'}
                or result.status == 'completed' and not result.is_valid()):
            raise ValueError('RGPE accepts only its actual declared target tuning measurements')
        aggregate = _tuning_aggregate(self._declaration, Trial(self.trials[result.trial_id], result.trial_id),
            result.metadata['evaluation'].get('records'), cancelled=result.status == 'cancelled')
        if (result.status != aggregate.status or result.cost != aggregate.cost
                or checkpoint_digest(result.metadata['evaluation']) != checkpoint_digest(aggregate.metadata['evaluation'])
                or result.status == 'completed' and result.objective_value != aggregate.objective_value):
            raise ValueError('RGPE target measurement differs from its raw declared tuning records')
        if result.status == 'completed' and len(self._points()) >= 64:
            raise ValueError('RGPE 64-target-point fitting bound exceeded')
        super().observe(deepcopy(result))

    def get_state(self):
        body = {**deepcopy(super().get_state()), 'kind': 'declared_rgpe_v1',
                'bundle': self.bundle, 'settings': deepcopy(self._settings),
                'candidates': deepcopy(self._candidates), 'proposed': deepcopy(self._proposed),
                'rng': deepcopy(self._rng.bit_generator.state), 'space_signature': space_signature(self.search_space)}
        return {**body, 'binding': checkpoint_digest(body)}

    def set_state(self, state):
        if not isinstance(state, dict):
            raise ValueError('Malformed RGPE checkpoint')
        body = {k: v for k, v in state.items() if k != 'binding'}
        if (state.get('binding') != checkpoint_digest(body) or state.get('kind') != 'declared_rgpe_v1'
                or state.get('bundle') != self._bundle or state.get('settings') != self._settings
                or state.get('candidates') != self._candidates
                or state.get('space_signature') != space_signature(self.search_space)):
            raise ValueError('RGPE checkpoint binding, history or settings differ')
        candidate = RGPESearcher(self.search_space, self._bundle, seed=state['seed'],
                                  candidates=self._candidates, **self._settings)
        detached = BaseState(self.search_space)
        detached.set_state(deepcopy(state))
        proposed = deepcopy(state['proposed'])
        keys = [physical_key(self.search_space, c) for c in proposed]
        if (len(set(keys)) != len(keys) or not len(detached.history) <= len(proposed) <= len(detached.history)+1
                or len(detached.trials) > len(proposed)
                or proposed[:min(len(proposed), len(self._ranked))] != self._ranked[:len(proposed)]
                or self._candidates is not None and any(c not in self._candidates for c in proposed)):
            raise ValueError('Malformed RGPE proposal/cursor checkpoint')
        candidate._proposed, candidate.trials = proposed, detached.trials
        if len({r.trial_id for r in detached.history}) != len(detached.history):
            raise ValueError('Duplicate RGPE target result identity')
        for result in detached.history:
            candidate.observe(result)
        observed = {r.trial_id for r in detached.history}
        pending = [c.values for tid, c in detached.trials.items() if tid not in observed]
        if len(pending) > 1 or pending and pending != proposed[len(detached.history):]:
            raise ValueError('RGPE pending target identity differs')
        candidate._rng.bit_generator.state = deepcopy(state['rng'])
        if len(candidate._points()) == 64 and len(proposed) != len(candidate.history):
            raise ValueError('RGPE checkpoint proposes beyond the target fitting bound')
        self.__dict__.update(candidate.__dict__)
