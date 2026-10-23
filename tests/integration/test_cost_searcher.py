"""Independent cost conditioning, actual Study work and joint recovery."""
from copy import deepcopy
import hashlib
import json
import math

import numpy as np
import pytest
import torch
from scipy.special import log_ndtr

from hponas import CensoredCostGP, CostAwareProposalSearcher, Knob, LocalExecutor, SearchSpace, Study
from hponas.cost_policy import CostRecord
from hponas.legacy_searchers import RandomSearcher
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers.adapter import LegacySearcherAdapter
from hponas.searchers_gp import GPqLogEISearcher
from hponas.types import Config, Result, Trial
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from workloads.tuning_models import quadratic


def space():
    return SearchSpace([Knob('eta', 'continuous', (.025, .625))])


class AnalyticScore(RandomSearcher):
    def log_expected_improvement(self, configs):
        return np.log([1+c['eta'] for c in configs])


def search(seed=4, **options):
    return CostAwareProposalSearcher(space(), AnalyticScore(space(), seed),
                                    seed=seed, total_budget=options.pop('total_budget', 128.),
                                    candidate_count=4, **options)


def step(s, *, status='completed', cost=8., metadata=None, value=2., timeout_assumption=None):
    config = s.propose()[0]
    row = {'config': config, 'cost': cost, 'status': status, 'value': value,
           'metadata': metadata or {}}
    if timeout_assumption:
        row['timeout_assumption'] = timeout_assumption
    s.observe(row)
    return config


def resign(state):
    payload = {k: v for k, v in state.items() if k != 'sha256'}
    state['sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@pytest.mark.parametrize('kind', ['complete', 'right_censored'])
def test_cost_moments_match_independent_single_observation_conditioning(kind):
    model = CensoredCostGP(space(), default_cost=4., lengthscale=.3)
    assert float(model._kernel.numeric.lengthscale.item()) == pytest.approx(.3, abs=1e-15)
    first = model.predict([{'eta': .2}])
    assert first['log_expected_cost'][0] == pytest.approx(math.log(4))
    assert first['cost_cv_squared'][0] == pytest.approx(math.expm1(1+.05**2))
    cause = 'completed' if kind == 'complete' else 'external_deadline'
    assumption = None if kind == 'complete' else 'deadline_independent_given_config'
    model.observe({'eta': .2}, CostRecord('a', 5., 5., kind, cause, 'declared_work_units', 'measured', assumption))
    points = [{'eta': .1}, {'eta': .45}]
    prediction = model.predict(points)
    r = np.abs(np.array([.1, .45])-.2)/(.625-.025)/.3
    cross = (1+np.sqrt(5)*r+5*r*r/3)*np.exp(-np.sqrt(5)*r)
    variance = 1.+1e-6+.05**2
    prior = math.log(4)-(1+.05**2)/2
    expected = []
    for power in [1, 2]:
        if kind == 'complete':
            mean = prior + cross/variance*(math.log(5)-prior)
            var = 1+.05**2-cross**2/variance
            expected.append(power*mean+power**2*var/2)
        else:
            expected.append(power*prior+power**2*(1+.05**2)/2
                +log_ndtr((prior+power*cross-math.log(5))/np.sqrt(variance))
                -log_ndtr((prior-math.log(5))/np.sqrt(variance)))
    np.testing.assert_allclose(prediction['log_expected_cost'], expected[0], atol=2e-12)
    np.testing.assert_allclose(prediction['log_second_moment'], expected[1], atol=2e-12)
    restored = CensoredCostGP.from_state(json.loads(json.dumps(model.state_dict())), space())
    np.testing.assert_array_equal(restored.predict(points)['log_expected_cost'], prediction['log_expected_cost'])


def test_cooling_cheap_first_and_candidate_reranking_are_actually_applied():
    s = search(initial_budget=16)
    alphas = []
    for _ in range(7):
        s.propose()
        p = s._pending
        pool = p['pool']
        if p['base_source'] == 'cheap_first_warmup':
            remaining = list(range(len(pool)))
            costs = p['predicted']['log_expected_cost']
            while len(remaining) > 1:
                remaining.remove(sorted(remaining, key=lambda j: (-costs[j], j))[0])
                if len(remaining) > 1:
                    remaining.remove(sorted(remaining, key=lambda j: (math.inf if p['distances'][j] is None else p['distances'][j], j))[0])
            assert p['index'] == remaining[0]
        else:
            alpha = (128-s._spent)/(128-16)
            scores = [(1+c['eta'])/math.exp(logcost)**alpha
                      for c, logcost in zip(pool, p['predicted']['log_expected_cost'])]
            assert p['alpha'] == alpha and p['index'] == np.argmax(scores)
            alphas.append(alpha)
        s.observe({'config': p['config'], 'value': 1., 'cost': 8.})
    assert alphas[0] == 1 and alphas == sorted(alphas, reverse=True)


def test_mixed_negative_infinity_is_valid_log_ei_and_bad_scores_are_refused(monkeypatch):
    s = search(initial_budget=0)
    monkeypatch.setattr(s.base_searcher, 'log_expected_improvement', lambda c: [-math.inf, -2., -1., -math.inf])
    assert s.propose()[0] == s._pending['pool'][2]
    assert s.state_dict()['pending']['base_scores'][0] is None
    s.observe({'config': s._pending['config'], 'value': 1., 'cost': 1.})
    for invalid in [math.nan, math.inf]:
        monkeypatch.setattr(s.base_searcher, 'log_expected_improvement', lambda c: [invalid]*len(c))
        before = s.state_dict()
        with pytest.raises(ValueError, match='acquisition'): s.propose()
        assert s.state_dict() == before


@pytest.mark.parametrize('status', ['failed', 'nan', 'inf', 'pruned', 'cancelled', 'timeout'])
def test_unmodeled_failures_consume_budget_without_duration_likelihood(status):
    s = search(initial_budget=0)
    step(s, status=status, value=math.nan, cost=3)
    assert s.records[0].kind == 'unmodeled' and s._spent == 3
    assert s.cost_model.predict([{'eta': .3}])['modelable_count'] == 0
    s.propose()  # Invalid outcomes must clear the pending slot.


def test_external_timeout_requires_provenance_and_declared_assumption():
    for assumption in [None, 'deadline_independent_given_config']:
        s = search(initial_budget=0, timeout_assumption=assumption)
        step(s, status='timeout', value=math.nan, cost=3,
             metadata={'execution': {'censor_cause': 'external_deadline'}})
        assert s.records[0].kind == ('right_censored' if assumption else 'unmodeled')
    s = search(initial_budget=0, timeout_assumption='deadline_independent_given_config')
    step(s, status='pruned', cost=3, metadata={'execution': {'censor_cause': 'external_deadline'}})
    assert s.records[0].kind == 'unmodeled'


def test_pending_and_next_proposal_recovery_with_different_constructor_seed():
    s = search()
    for index in range(6):
        resumed = search(seed=92)
        resumed.load_state_dict(json.loads(json.dumps(s.state_dict(), allow_nan=False)))
        assert resumed.propose() == s.propose()
        state = s.state_dict()
        resumed.load_state_dict(state)
        assert resumed.state_dict() == state
        obs = {'config': s._pending['config'], 'value': float(index), 'cost': 8.}
        s.observe(obs); resumed.observe(obs)
        assert resumed.state_dict() == s.state_dict()


@pytest.mark.parametrize('damage', ['checksum', 'rng', 'records', 'spent', 'pending', 'trace', 'configs', 'units', 'direction', 'model'])
def test_corrupt_recovery_refuses_atomically_even_with_recomputed_checksum(damage):
    source = search(); step(source); source.propose()
    bad = source.state_dict()
    if damage == 'checksum': bad['sha256'] = 'wrong'
    elif damage == 'rng': bad['rng']['bit_generator'] = 'unsupported'
    elif damage == 'records': bad['records'][0]['trial_id'] = 'other'
    elif damage == 'spent': bad['spent'] += 1
    elif damage == 'pending': bad['pending']['index'] = 999
    elif damage == 'trace': bad['trace'][0]['spent'] += 1
    elif damage == 'configs': bad['cost_model']['configs'][0]['eta'] = .025
    elif damage == 'units': bad['records'][0]['unit'] = 'wall_seconds'
    elif damage == 'direction': bad['maximize'] = 'false'
    elif damage == 'model': bad['cost_model']['contract']['lengthscale'] = .2
    if damage != 'checksum': resign(bad)
    target = search(seed=19); step(target)
    before = target.state_dict()
    with pytest.raises(ValueError): target.load_state_dict(bad)
    assert target.state_dict() == before


def test_duplicate_observation_refusal_keeps_pending_cost_and_base_state():
    s = search(); step(s)
    config = s.propose()[0]
    before = s.state_dict()
    with pytest.raises(ValueError, match='revised'):
        s.observe({'config': config, 'trial_id': s.records[0].trial_id, 'value': 1., 'cost': 5.})
    assert s.state_dict() == before


def test_study_controls_direction_failed_work_budget_and_pending_checkpoint(tmp_path):
    for options in [{'max_concurrent': 2}, {'scheduler': ASHAScheduler(ASHAConfig())}]:
        with pytest.raises(ValueError, match='sequential'):
            Study(search(), LocalExecutor(), lambda c: 1., **options, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    calls = []
    def objective(config):
        calls.append(config)
        return {'value': math.nan if len(calls) == 2 else quadratic(config['eta'], 8)['value'], 'cost': 8.}
    source = Study(search(total_budget=24), LocalExecutor(), objective,
                   budget=20, maximize=False, study_name='cost', checkpoint_dir=tmp_path,
                   event_log=EventLog(tmp_path/'events.jsonl'), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    source._new_trial(); source.save_checkpoint()
    resumed = Study(search(seed=33, total_budget=24), LocalExecutor(), objective,
                    budget=20, maximize=False, study_name='cost', checkpoint_dir=tmp_path,
                    event_log=EventLog(tmp_path/'events.jsonl'), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    resumed.load_checkpoint(tmp_path/'cost_checkpoint.json')
    assert resumed.searcher.get_state() == source.searcher.get_state()
    outcome = resumed.run()
    s = resumed.searcher.searcher
    assert outcome.n_trials == 3 and outcome.total_cost == 24 and s._spent == 24
    assert outcome.reason == 'search_budget_exhausted' and len(calls) == 3
    assert s.records[1].kind == 'unmodeled'
    assert s._trace[0]['objective_observation']['value'] == -outcome.history[0].objective_value
    final = Study(search(total_budget=24), LocalExecutor(), objective,
                  budget=20, maximize=False, study_name='cost', checkpoint_dir=tmp_path, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    final.load_checkpoint(tmp_path/'cost_checkpoint.json')
    assert final.run().total_cost == 24 and len(calls) == 3
    replay = LegacySearcherAdapter(search(total_budget=24), maximize=False)
    replay.validate_study_context('cost')
    assert ReplayEngine(replay, EventLog(tmp_path/'events.jsonl'), seed=4).verify_determinism(3)[0]


def test_real_gp_scoring_and_recovery_preserve_global_rng():
    def make(seed):
        return CostAwareProposalSearcher(space(), GPqLogEISearcher(space(), seed=seed, n_fantasies=16,
            raw_samples=16, n_restarts=2), seed=seed, total_budget=128, initial_budget=8, candidate_count=4)
    source = make(7); step(source)
    restored = make(88); restored.load_state_dict(source.state_dict())
    rng = torch.get_rng_state().clone()
    proposal = source.propose()
    assert torch.equal(rng, torch.get_rng_state())
    assert proposal == restored.propose()
    assert source.state_dict() == restored.state_dict()
    assert source._pending['base_source'] == 'log_expected_improvement'
    bad = source.state_dict(); bad['base_state']['Y'][0] += 1.; resign(bad)
    before = restored.state_dict()
    with pytest.raises(ValueError, match='objective ledger'): restored.load_state_dict(bad)
    assert restored.state_dict() == before


def test_executor_wall_duration_and_objective_timeout_are_not_external_censoring():
    executor = LocalExecutor()
    result = executor.execute(Trial(Config({'eta': .2}), 'ok'), lambda c: {'value': 2., 'cost': 8.})
    assert result.metadata['execution']['elapsed_seconds'] > 0
    def fail(config): raise TimeoutError('objective declared timeout')
    failed = executor.execute(Trial(Config({'eta': .3}), 'bad'), fail)
    assert failed.status == 'timeout' and 'censor_cause' not in failed.metadata['execution']
    s = search(initial_budget=0, cost_unit='wall_seconds', timeout_assumption='deadline_independent_given_config')
    adapter = LegacySearcherAdapter(s)
    adapter.trials['bad'] = adapter.suggest()
    adapter.observe(failed)
    assert s.records[0].kind == 'unmodeled' and s._spent == failed.metadata['execution']['elapsed_seconds']


def test_explicit_cost_only_mode_and_finite_mixed_space_exhaustion():
    mixed = SearchSpace([Knob('kind', 'categorical', ['a', 'b']), Knob('n', 'integer', (1, 2), condition=('kind', 'b'))])
    with pytest.raises(TypeError, match='log_expected_improvement'):
        CostAwareProposalSearcher(mixed, RandomSearcher(mixed), total_budget=100)
    s = CostAwareProposalSearcher(mixed, RandomSearcher(mixed), total_budget=100, cost_only=True, candidate_count=4)
    study = Study(s, LocalExecutor(), lambda c: {'value': 1., 'cost': 1.}, budget=10, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    result = study.run()
    assert result.n_trials == 3 and result.reason == 'search_space_exhausted'


def test_real_external_deadline_has_measured_censor_provenance():
    import time
    executor = LocalExecutor(timeout=.1)
    result = executor.execute(Trial(Config({'eta': .2}), 'deadline'), lambda c: time.sleep(10))
    executor.shutdown()
    assert result.status == 'timeout'
    assert result.metadata['execution']['censor_cause'] == 'external_deadline'
    assert result.metadata['execution']['elapsed_seconds'] >= .1
    s = search(initial_budget=0, cost_unit='wall_seconds', timeout_assumption='deadline_independent_given_config')
    adapter = LegacySearcherAdapter(s)
    adapter.trials['deadline'] = adapter.suggest()
    adapter.observe(result)
    assert s.records[0].kind == 'right_censored'
    assert s.records[0].spent == result.metadata['execution']['elapsed_seconds']
