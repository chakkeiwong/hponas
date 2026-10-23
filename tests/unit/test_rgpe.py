"""Independent finite rank arithmetic, Gaussian conditioning and recovery."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest

from hponas.evaluation import EvaluationController, EvaluationFold, EvaluationObjective, StudyDeclaration
from hponas.rgpe import (FixedKernelGP, RGPESearcher, combine_posteriors, ranking_loss, rank_weights)
from hponas.searchers.base import PendingSuggestionError, SearchSpaceExhaustedError
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Result, Trial
from hponas.warm_history import digest, select, space_signature, target_context
from hponas.warm_start import checkpoint_digest


def declaration(data='target-data', direction='min'):
    return StudyDeclaration('loss:v1', 'line:v1', data, 'repeat:v1',
        (EvaluationObjective('loss', direction, 'units'),),
        (EvaluationFold('tune', ('train',), ('score',)),),
        (EvaluationFold('final', ('train', 'score'), ('sealed',)),))


def measured(declared, config, tid, value, status='completed'):
    trial = Trial(Config(config), tid)
    controller = EvaluationController(declared, maximize=declared.objectives[0].direction == 'max')
    rows = [{'fold': fold.name, 'seed': seed, 'result': Result(rid, value, 1., 1.,
        {'execution': {'elapsed_seconds': 0., 'accounting': 'measured'}}, status).to_dict()}
        for fold, seed, rid in controller.tasks(trial, 'tuning')]
    return controller.aggregate(trial, rows)


def bundle(space, sources=(), *, a=1., b=0., direction='min'):
    target = declaration(direction=direction)
    context = target_context(space, study_id='target', task_id='target-task', model_family='line',
        task_domain='finite', objective_key=target.objective_id,
        direction='maximize' if direction == 'max' else 'minimize', history_cutoff=100.)
    retained = []
    for name, values in sources:
        declared = declaration(name+'-data', direction=direction)
        trials, proof = [], []
        for i, v in enumerate(values):
            value = a*v+b
            row = dict(trial_id=f'{name}-{i}', config={'x': i}, value=value, fidelity=1., status='completed')
            aggregate = measured(declared, row['config'], row['trial_id'], value)
            trials.append(row)
            proof.append({k: deepcopy(row[k]) for k in ('trial_id', 'config', 'value')} | {
                'role': 'tuning', 'evaluation_identity': declared.identity,
                'repetitions': aggregate.metadata['evaluation']['records']})
        history = dict(context, study_id=name, task_id=name+'-task', status='completed',
                       completed_at=10., trials=trials, schema='warm_history_snapshot_v1')
        history.pop('excluded_task_ids'); history.pop('history_cutoff')
        history['binding'] = digest(history)
        retained.append({'history': history, 'declaration': declared.contract, 'tuning_proof': proof})
    body = dict(schema='declared_rgpe_history_v1', context=context, target_declaration=target.contract,
                target_identity=target.identity, sources=retained, excluded=[],
                selection=select([s['history'] for s in retained], context, space, 2))
    return body | {'binding': digest(body)}


def feed(searcher, value=None, status='completed'):
    config = searcher.suggest()
    tid = f'target-{len(searcher.history)}'
    searcher.trials[tid] = config
    result = measured(declaration(direction='max' if searcher.maximize else 'min'),
                      config.values, tid, config['x'] if value is None else value, status)
    searcher.observe(result)
    return config, result


def test_ordered_pair_and_loo_losses_match_literal_enumeration():
    target = [0., 3., 3., -1.]
    samples = np.array([[0., 1., 2., -1.], [3., 2., 1., 0.], [1., 1., 1., 1.]])
    expected = [sum((sample[i] < sample[j]) != (target[i] < target[j])
                    for i in range(4) for j in range(4)) for sample in samples]
    assert ranking_loss(samples, target).tolist() == expected
    loo = np.arange(3*4*4).reshape(3, 4, 4) % 7
    expected = [sum((sample[i, i] < sample[i, j]) != (target[i] < target[j])
                    for i in range(4) for j in range(4)) for sample in loo]
    assert ranking_loss(loo, target).tolist() == expected


def test_finite_minimum_loss_probabilities_split_ties_equally():
    losses = [[0, 1, 1, 0], [2, 1, 0, 0], [3, 2, 0, 0]]
    np.testing.assert_allclose(rank_weights(losses), [11/24, 1/3, 5/24], rtol=0., atol=1e-15)
    np.testing.assert_allclose(rank_weights([[2, 2], [2, 2]]), [.5, .5])


def test_gp_matches_two_point_inverse_and_independent_ensemble_covariance():
    model = FixedKernelGP([[0.], [1.]], [2., 6.], lengthscale=1., noise=.25)
    query = np.array([[.5], [.75]])
    c = math.exp(-.5); determinant = 1.25**2-c*c
    inverse = np.array([[1.25, -c], [-c, 1.25]])/determinant
    cross = np.array([[math.exp(-q*q/2) for q in [.5, .75]],
                      [math.exp(-(1-q)**2/2) for q in [.5, .75]]])
    prior = np.array([[1., math.exp(-.25**2/2)], [math.exp(-.25**2/2), 1.]])
    mean, covariance = model.posterior(query)
    np.testing.assert_allclose(mean, cross.T @ inverse @ [-1., 1.], atol=1e-14)
    np.testing.assert_allclose(covariance, prior-cross.T @ inverse @ cross, atol=1e-14)
    combined_mean, combined_cov = combine_posteriors([[1., 2.], [3., 4.]],
        [[[2., .5], [.5, 1.]], [[4., -.2], [-.2, 3.]]], [.25, .75])
    np.testing.assert_allclose(combined_mean, [2.5, 3.5])
    np.testing.assert_allclose(combined_cov, [[2.375, -.08125], [-.08125, 1.75]])
    with pytest.raises(ValueError, match='semidefinite'):
        combine_posteriors([[0., 0.]], [[[1., 2.], [2., 1.]]], [1.])


@pytest.mark.parametrize('kind', ['weights', 'loss', 'gp', 'scale', 'query'])
def test_nonfinite_or_mismatched_arithmetic_is_refused(kind):
    with pytest.raises(ValueError):
        if kind == 'weights': rank_weights([[math.nan]])
        elif kind == 'loss': ranking_loss([[0., 1.]], [0.])
        elif kind == 'gp': FixedKernelGP([[0.]], [math.inf])
        elif kind == 'scale': FixedKernelGP([[0.]], [1.], lengthscale=0.)
        elif kind == 'query': FixedKernelGP([[0.]], [1.]).posterior([[math.inf]])


def test_ranked_initialization_then_actual_rank_weighted_ensemble():
    space = SearchSpace([Knob('x', 'ordinal', (0, 5))])
    saved = bundle(space, [('good', [0., 10., 20., 30.]), ('reversed', [30., 20., 10., 0.])])
    searcher = RGPESearcher(space, saved, n_initial=2, rank_samples=512)
    assert [feed(searcher, value=0.)[0]['x'], feed(searcher, value=30.)[0]['x']] == [0, 3]
    before = deepcopy(searcher.get_state())
    posterior = searcher.posterior([{'x': i} for i in range(6)])
    assert posterior['weights']['reversed'] == 0.
    assert posterior['weights']['good'] > posterior['weights']['target']
    assert posterior['mean'][0] < posterior['mean'][3]
    assert searcher.get_state() == before  # inspection does not consume proposal randomness
    next_config = searcher.suggest()
    assert next_config['x'] not in (0, 3)
    with pytest.raises(PendingSuggestionError): searcher.suggest()


@pytest.mark.parametrize('direction,a,b', [('min', 7., 100.), ('max', -1., 0.)])
def test_affine_units_and_maximization_preserve_rank_weights(direction, a, b):
    space = SearchSpace([Knob('x', 'ordinal', (0, 5))])
    sources = [('good', [0., 1., 2., 3.]), ('bad', [3., 2., 1., 0.])]
    first = RGPESearcher(space, bundle(space, sources), n_initial=2, rank_samples=128)
    second = RGPESearcher(space, bundle(space, sources, a=a, b=b, direction=direction),
                          n_initial=2, rank_samples=128)
    for value in (0., 3.):
        assert feed(first, value)[0] == feed(second, a*value+b)[0]
    p, q = first.posterior([{'x': 1}, {'x': 4}]), second.posterior([{'x': 1}, {'x': 4}])
    assert p['weights'] == q['weights']
    np.testing.assert_allclose(q['mean'], a*p['mean']+b, atol=1e-12)
    np.testing.assert_allclose(q['covariance'], a*a*p['covariance'], atol=1e-12)
    assert first.suggest() == second.suggest()


def test_cold_fallback_failure_exclusion_and_finite_exhaustion():
    space = SearchSpace([Knob('x', 'ordinal', (0, 3))])
    searcher = RGPESearcher(space, bundle(space), n_initial=2)
    assert searcher.fallback_reason == 'no_eligible_declared_history'
    feed(searcher, math.nan, 'failed')
    for _ in range(3): feed(searcher)
    assert len({c.values['x'] for c in searcher.trials.values()}) == 4
    assert len(searcher.history) == 4 and searcher.history[0].status == 'failed'
    assert searcher.posterior([{'x': 0}])['weights'] == {'target': 1.}
    with pytest.raises(SearchSpaceExhaustedError): searcher.suggest()


@pytest.mark.parametrize('bad', ['duplicate', 'pending', 'missing_trial', 'role', 'raw', 'rng', 'over_limit'])
def test_semantic_checkpoint_corruption_is_refused_atomically_even_if_rehashed(bad):
    space = SearchSpace([Knob('x', 'ordinal', (0, 5))])
    searcher = RGPESearcher(space, bundle(space), n_initial=2)
    feed(searcher); feed(searcher)
    state = json.loads(json.dumps(searcher.get_state()))
    if bad == 'duplicate': state['proposed'][1] = state['proposed'][0]
    elif bad == 'pending': state['proposed'].extend([{'x': 4}, {'x': 5}])
    elif bad == 'missing_trial': state['trials'].pop(next(iter(state['trials'])))
    elif bad == 'role': state['history'][0]['metadata']['evaluation']['role'] = 'final'
    elif bad == 'raw': state['history'][0]['metadata']['evaluation']['records'][0]['seed'] = 99
    elif bad == 'rng': state['rng']['bit_generator'] = 'not-a-generator'
    elif bad == 'over_limit': state['settings']['rank_samples'] = 513
    state['binding'] = checkpoint_digest({k: v for k, v in state.items() if k != 'binding'})
    before = deepcopy(searcher.get_state())
    with pytest.raises(ValueError): searcher.set_state(state)
    assert searcher.get_state() == before


def test_json_checkpoint_retains_bundle_failed_results_pending_and_rng():
    space = SearchSpace([Knob('x', 'ordinal', (0, 5))])
    original = RGPESearcher(space, bundle(space, [('past', [0., 2., 4., 6.])]), n_initial=2)
    feed(original, math.nan, 'failed'); feed(original)
    pending = original.suggest(); original.trials['target-2'] = pending
    state = json.loads(json.dumps(original.get_state()))
    restored = RGPESearcher.from_state(space, state)
    assert restored.bundle == original.bundle
    result = measured(declaration(), pending.values, 'target-2', 3.)
    original.observe(result); restored.observe(result)
    assert restored.suggest() == original.suggest()
    before = restored.get_state()
    restored.observe(result)  # idempotent acknowledgement
    assert checkpoint_digest(before) == checkpoint_digest(restored.get_state())
    changed = deepcopy(result); changed.objective_value = -999.
    with pytest.raises(ValueError, match='acknowledged'): restored.observe(changed)


@pytest.mark.parametrize('kind', ['categorical', 'conditional', 'samples', 'initial', 'candidates'])
def test_unsupported_space_or_allocation_is_refused(kind):
    space = SearchSpace([Knob('x', 'ordinal', (0, 5))]); saved = bundle(space)
    options = {'n_initial': 2}
    if kind == 'categorical': space = SearchSpace([Knob('x', 'categorical', [0, 1])])
    elif kind == 'conditional':
        space = SearchSpace([Knob('x', 'ordinal', (0, 5)), Knob('z', 'continuous', (0., 1.), condition=('x', 1))])
    elif kind == 'samples': options['rank_samples'] = 513
    elif kind == 'initial': options['n_initial'] = 1
    elif kind == 'candidates': options['candidates'] = [{'x': 0}, {'x': 0}]
    with pytest.raises(ValueError): RGPESearcher(space, saved, **options)
