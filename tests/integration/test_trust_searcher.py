"""Independent conditioning, real training work, restart isolation and recovery."""
from copy import deepcopy
import json
import math
import random

import numpy as np
import pytest
import torch

from hponas import Config, Knob, LocalExecutor, Result, SearchSpace, Study, Trial, TrustRegionSearcher
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.searchers.base import SearchSpaceExhaustedError
from hponas.trust_controller import Controller, Options, digest
from hponas.trust_searcher import LocalGP
from validation.multifidelity_reference import value
from workloads.tuning_models import quadratic


class FullQuadratic:
    """Study's unit fidelity is one complete eight-update training job."""
    def __init__(self):
        self.updates = []

    def __call__(self, config):
        state = None
        for step in range(1, 9):
            actual = quadratic(config['eta_index']/40, step, state)
            assert actual['incremental_steps'] == 1
            state = actual['checkpoint']
            self.updates.append({'eta_index': config['eta_index'], 'step': step, 'value': actual['value']})
        return {'value': actual['value'], 'cost': 8,
                'metadata': {'work_unit': 'gradient_updates', 'training_steps': 8}}


def searcher(seed=0, **options):
    return TrustRegionSearcher(SearchSpace([Knob('eta_index', 'integer', (1, 25))]),
                               seed=seed, initial_random=3, candidate_count=24, fit_steps=6, **options)


def bind(search, config):
    tid = 'trial-'+str(len(search.trials))
    search.trials[tid] = config
    search.register_trial(Trial(config, tid))
    return tid


def step(search, objective=1., status='completed'):
    config = search.suggest()
    tid = bind(search, config)
    result = objective(config) if callable(objective) else objective
    search.observe(Result(tid, result, 8, 1, {}, status))
    return config


def test_exact_gp_posterior_matches_independent_gaussian_conditioning():
    x = torch.tensor([[.1, 1.], [.6, 2.], [.9, 1.]], dtype=torch.double)
    y = torch.tensor([.8, -.4, .2], dtype=torch.double)
    points = torch.tensor([[.15, 1.], [.5, 2.], [.8, 1.]], dtype=torch.double)
    model = LocalGP(x, y, 1, 1)
    model.mean_module.constant = .2
    model.covar_module.outputscale = 1.7
    model.kernel.numeric.lengthscale = .4
    model.kernel.categorical.lengthscale = .8
    model.likelihood.noise = .003
    model.eval(); model.likelihood.eval()

    def covariance(a, b):
        radius = np.abs(a[:, None, 0]-b[None, :, 0])/.4
        mismatch = (a[:, None, 1] != b[None, :, 1])/.8
        return 1.7*(1+math.sqrt(5)*radius+5*radius**2/3)*np.exp(-math.sqrt(5)*radius-mismatch)

    train, target = x.numpy(), points.numpy()
    matrix = covariance(train, train)+.003*np.eye(3)
    cross = covariance(target, train)
    mean = .2+cross@np.linalg.solve(matrix, y.numpy()-.2)
    cov = covariance(target, target)-cross@np.linalg.solve(matrix, cross.T)+.003*np.eye(3)
    with torch.no_grad():
        posterior = model.likelihood(model(points))
    np.testing.assert_allclose(posterior.mean.numpy(), mean, rtol=1e-7, atol=1e-8)
    np.testing.assert_allclose(posterior.covariance_matrix.numpy(), cov, rtol=1e-6, atol=1e-8)
    assert np.linalg.norm(mean-.2) > .1
    assert np.max(np.abs(cov-np.diag(np.diag(cov)))) > .01


def test_trust_searcher_actual_training_updates_and_recovery(tmp_path):
    workload = FullQuadratic()
    source = Study(searcher(), LocalExecutor(), workload, budget=12, study_name='trust', maximize=False,
                   checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    result = source.run()
    assert result.n_trials == 12 and result.total_cost == len(workload.updates) == 96
    for row in result.history:
        index = source.trials[row.trial_id].config['eta_index']
        assert row.objective_value == pytest.approx(float(value(index, 8)), abs=1e-12)
        assert row.fidelity == 1 and row.metadata['training_steps'] == 8
    restored = Study(searcher(seed=9), LocalExecutor(), workload, budget=12, study_name='trust', maximize=False,
                     checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    restored.load_checkpoint(tmp_path/'trust_checkpoint.json')
    assert restored.searcher.get_state() == source.searcher.get_state()
    assert restored.run().total_cost == 96 and len(workload.updates) == 96
    assert source.searcher._fits
    for row in source.searcher._proposals:
        if row['selection']:
            selected = row['selection']
            assert selected['index'] == int(np.argmin(selected['sample']))
            assert row['config'] == selected['candidates'][selected['index']]


def test_restart_local_history_pending_failed_work_and_no_refit_recovery(monkeypatch):
    options = Options(1, .5, .25, 1., 3, 1, geometry='typed_product_v1')
    source = searcher(controller=Controller(options))
    generations = set()
    for index in range(13):
        before = source.get_state()
        replay = searcher(seed=42, controller=Controller(options))
        with monkeypatch.context() as patch:
            patch.setattr(torch.optim, 'Adam', lambda *a, **kw: pytest.fail('Recovery repeated an old fit'))
            replay.set_state(json.loads(json.dumps(before, allow_nan=False)))
        config = source.suggest()
        assert replay.suggest() == config
        with pytest.raises(ValueError): source.suggest()
        pending = source.get_state()
        replay.set_state(pending)
        assert replay.get_state() == pending
        tid = bind(source, config)
        bind(replay, config)
        bound = source.get_state()
        replay.set_state(bound)
        objective, status = (math.nan, 'timeout') if index == 4 else (1., 'completed')
        source.observe(Result(tid, objective, 8, 1, {}, status))
        replay.observe(Result(tid, objective, 8, 1, {}, status))
        assert replay.get_state() == source.get_state()
        generations.add(source._generation)
    assert len(generations) >= 3
    assert source.history[4].status == 'timeout' and source.history[4].cost == 8
    for proposal in source._proposals:
        if proposal['selection']:
            fit = source._fits[proposal['selection']['fit_index']]
            for tid in fit['train_ids']:
                origin = next(p for p in source._proposals if p['trial_id'] == tid)
                assert origin['generation'] == proposal['generation']
            assert 'trial-4' not in fit['train_ids']


def test_direction_changes_objective_sign_and_is_immutable_after_work():
    low, high = searcher(), searcher(maximize=True)
    for _ in range(8):
        a = step(low, lambda config: float((config['eta_index']-9)**2))
        b = step(high, lambda config: -float((config['eta_index']-9)**2))
        assert a == b
    with pytest.raises(ValueError): low.maximize = True
    restored = searcher(seed=987)
    restored.set_state(high.get_state())
    assert restored.maximize and restored.suggest() == high.suggest()


def test_global_rng_and_threads_survive_fit_and_sampling():
    source = searcher()
    for _ in range(3): step(source)
    previous_threads = torch.get_num_threads()
    numpy_before = deepcopy(np.random.get_state())
    python_before = random.getstate()
    torch_before = torch.random.get_rng_state().clone()
    source.suggest()
    assert torch.get_num_threads() == previous_threads
    torch.testing.assert_close(torch.random.get_rng_state(), torch_before, rtol=0, atol=0)
    after = np.random.get_state()
    assert after[0] == numpy_before[0] and after[2:] == numpy_before[2:]
    np.testing.assert_array_equal(after[1], numpy_before[1])
    assert random.getstate() == python_before


def test_finite_exhaustion_stops_study_with_actual_work_and_replays(tmp_path):
    factory = lambda: TrustRegionSearcher(SearchSpace([Knob('eta_index', 'integer', (1, 5))]),
                                         initial_random=2, candidate_count=4, fit_steps=3)
    event_log = EventLog(tmp_path/'events.jsonl')
    workload = FullQuadratic()
    study = Study(factory(), LocalExecutor(), workload, budget=20, maximize=False,
                  study_name='exhaust', checkpoint_dir=tmp_path, event_log=event_log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    result = study.run()
    assert result.n_trials == 5 and result.total_cost == len(workload.updates) == 40
    assert result.reason == result.status == 'search_space_exhausted'
    assert len({p['config']['eta_index'] for p in study.searcher._proposals}) == 5
    assert study._n_suggested < study.budget
    assert ReplayEngine(factory(), event_log, 0).verify_determinism(5)[0]
    resumed = Study(factory(), LocalExecutor(), workload, budget=20, maximize=False,
                    study_name='exhaust', checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    resumed.load_checkpoint(tmp_path/'exhaust_checkpoint.json')
    assert resumed.run().total_cost == 40 and len(workload.updates) == 40
    with pytest.raises(SearchSpaceExhaustedError): resumed.searcher.suggest()
    # A forged suggestion after true exhaustion is a failed replay, not an uncaught exception.
    event_log.record_suggest('foreign', {'eta_index': 1}, 0)
    passed, message, *_ = ReplayEngine(factory(), event_log, 0).verify_determinism(6)
    assert not passed and 'exhaust' in message


@pytest.mark.parametrize('damage', ['controller', 'pending', 'fit', 'local', 'trial', 'rng', 'candidate', 'value', 'direction'])
def test_checkpoint_cross_ledger_refusals_are_atomic_even_with_recomputed_checksum(damage):
    source = searcher()
    for _ in range(5): step(source, lambda c: float(c['eta_index']))
    before = source.get_state()
    bad = deepcopy(before)
    if damage == 'controller': bad['controller']['payload']['snapshot']['length'] *= 2
    elif damage == 'pending': bad['pending'] = 0
    elif damage == 'fit': bad['fits'][0]['parameters']['mean_module.raw_constant'] += .3
    elif damage == 'local': bad['local_ids'] = []
    elif damage == 'trial': bad['trials']['trial-0']['config_id'] = 'foreign'
    elif damage == 'rng': bad['rng']['state']['state'] += 1
    elif damage == 'candidate': bad['proposals'][3]['selection']['candidates'][0]['eta_index'] = 99
    elif damage == 'value': bad['events'][2]['result']['objective_value'] += 1
    elif damage == 'direction': bad['maximize'] = not bad['maximize']
    bad['sha256'] = digest({k: v for k, v in bad.items() if k != 'sha256'})
    with pytest.raises(ValueError): source.set_state(bad)
    assert source.get_state() == before


def test_modes_and_study_controls_refused_before_objective_work(tmp_path):
    space = SearchSpace([Knob('x', 'continuous', (0., 1.))])
    with pytest.raises(ValueError): TrustRegionSearcher(space, allow_batch=True)
    with pytest.raises(ValueError): TrustRegionSearcher(space, allow_noisy=True)
    with pytest.raises(ValueError): Study(searcher(), LocalExecutor(), FullQuadratic(), budget=5, max_concurrent=2, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    from hponas.schedulers import ASHAScheduler, ASHAConfig
    with pytest.raises(ValueError):
        Study(searcher(), LocalExecutor(), FullQuadratic(), budget=5,
              scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=4, eta=2)), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    source = Study(searcher(), LocalExecutor(), FullQuadratic(), budget=4, maximize=False,
                   study_name='atomic', checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    source.run()
    before = source._snapshot()
    for key, new_value in [('maximize', True), ('max_concurrent', 2)]:
        bad = deepcopy(before); bad[key] = new_value
        path = tmp_path/(key+'.json'); path.write_text(json.dumps(bad))
        with pytest.raises(ValueError): source.load_checkpoint(path)
        assert source._snapshot() == before


def test_bounded_candidate_failure_is_atomic_and_does_not_claim_exhaustion(monkeypatch):
    source = TrustRegionSearcher(SearchSpace([Knob('x', 'continuous', (0., 1.))]),
                                 initial_random=2, fit_steps=3)
    for _ in range(2): step(source)
    before = source.get_state()
    monkeypatch.setattr(source.space, 'candidates', lambda *a, **kw: ([], {}, False))
    with pytest.raises(RuntimeError, match='unproved'): source.suggest()
    assert source.get_state() == before


def test_all_failed_initial_design_restarts_without_fictitious_incumbent():
    source = searcher()
    for _ in range(3): step(source, math.nan, 'failed')
    assert source.controller.snapshot()['best'] is None
    step(source, 2.)
    assert source._generation == 1 and source._phase == 'initial'
    restored = searcher(seed=19)
    restored.set_state(source.get_state())
    assert restored.suggest() == source.suggest()


def test_mixed_conditional_search_fits_and_recovers_legal_branches():
    space = SearchSpace([Knob('family', 'categorical', ['a', 'b']), Knob('n', 'integer', (1, 4)),
                         Knob('rate_a', 'continuous', (.01, 1.), transform='log', condition=('family', 'a')),
                         Knob('rate_b', 'continuous', (.01, .99), transform='logit', condition=('family', 'b'))])
    source = TrustRegionSearcher(space, initial_random=3, candidate_count=24, fit_steps=4)
    for _ in range(8):
        config = step(source, lambda c: float((c['n']-2)**2+c.values.get('rate_a', c.values.get('rate_b'))))
        space.validate_config(config.values)
        assert ('rate_a' in config.values) == (config['family'] == 'a')
    restored = TrustRegionSearcher(space, seed=11, initial_random=3, candidate_count=24, fit_steps=4)
    restored.set_state(source.get_state())
    assert restored.suggest() == source.suggest()


def test_all_categorical_gp_and_partial_final_design_exhaust_without_duplicates():
    space = SearchSpace([Knob('family', 'categorical', ['linear', 'spline', 'network']),
                         Knob('penalty', 'categorical', ['none', 'ridge'])])
    source = TrustRegionSearcher(space, seed=4, initial_random=2, candidate_count=8, fit_steps=4)
    proposed = []
    for _ in range(6):
        config = step(source, lambda c: float((c['family'] != 'spline')+2*(c['penalty'] != 'ridge')))
        proposed.append(config.values)
    assert len({json.dumps(c, sort_keys=True) for c in proposed}) == 6 and source._fits
    with pytest.raises(SearchSpaceExhaustedError): source.suggest()
    clone = TrustRegionSearcher(space, seed=12, initial_random=2, candidate_count=8, fit_steps=4)
    clone.set_state(source.get_state())
    assert clone.get_state() == source.get_state()
    small = TrustRegionSearcher(SearchSpace([Knob('family', 'categorical', ['a', 'b'])]), initial_random=4)
    step(small)
    step(small)
    assert small._phase == 'active'
    with pytest.raises(SearchSpaceExhaustedError): small.suggest()


def test_all_failed_finite_study_has_no_fabricated_best_and_retains_work(tmp_path):
    from hponas import IncompleteStudyError
    factory = lambda: TrustRegionSearcher(SearchSpace([Knob('family', 'categorical', ['a', 'b'])]), initial_random=4)
    def fails(config):
        return {'value': math.nan, 'cost': 3}
    study = Study(factory(), LocalExecutor(), fails, budget=9, maximize=False,
                  study_name='failed', checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    with pytest.raises(IncompleteStudyError) as caught:
        study.run()
    result = caught.value.result
    assert result.best_config is None and result.best_value is None
    assert result.total_cost == 6 and result.n_trials == 2
    assert result.reason == 'search_space_exhausted' and result.status == 'incomplete'
    clone = Study(factory(), LocalExecutor(), fails, budget=9, maximize=False,
                  study_name='failed', checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    clone.load_checkpoint(tmp_path/'failed_checkpoint.json')
    assert clone.searcher.get_state() == study.searcher.get_state()
    assert all(not row.is_valid() for row in clone.searcher.history)


@pytest.mark.parametrize('invalid', [math.inf, -math.inf])
def test_infinite_executor_outcome_remains_failed_work_and_recovers(invalid):
    source = searcher()
    for _ in range(3): step(source)
    before = source.controller.snapshot()['best']
    step(source, invalid, 'inf')
    assert source.history[-1].status == 'inf' and source.history[-1].cost == 8
    assert source.controller.snapshot()['best'] == before
    restored = searcher(seed=42)
    restored.set_state(source.get_state())
    assert restored.get_state() == source.get_state()
