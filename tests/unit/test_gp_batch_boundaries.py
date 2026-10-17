"""Public GP boundary cases and independently enumerable batch objectives."""
from copy import deepcopy
from dataclasses import replace
from itertools import combinations
import json
import re

import pytest
import torch

from hponas import GPSearcher, Knob, SearchSpace, Config, Result
from hponas.searchers.base import PendingSuggestionError
import hponas.searchers.gp_searcher as implementation


def finite(size=12, **kwargs):
    return GPSearcher(SearchSpace([Knob('x', 'ordinal', (0, size - 1))]), seed=17, **kwargs)


@pytest.mark.parametrize('count', [1, 8])
def test_inclusive_batch_limits_return_distinct_locations_and_durable_request(count):
    source = finite()
    configs = source.suggest_batch(count)
    assert len(configs) == count
    assert len({c['x'] for c in configs}) == count
    state = json.loads(json.dumps(source.get_state()))
    assert state['proposal_batches'] == [{'mode': 'initial_random',
        'configs': [c.to_dict() for c in configs], 'requested': count,
        'pending_trial_ids': [], 'log_acquisition': None}]
    target = finite(); target.set_state(state)
    assert target.suggest_batch(count) == source.suggest_batch(count)


@pytest.mark.parametrize('count', [0, 9, True, 1.5])
def test_batch_refusal_explains_inclusive_limits_without_advancing_state(count):
    source = finite(); before = deepcopy(source.get_state())
    with pytest.raises(ValueError, match='^GP batch size must be an integer from 1 to 8$'):
        source.suggest_batch(count)
    assert source.get_state() == before


def test_gp_variant_without_joint_capability_refuses_before_state_changes():
    class ScalarGP(GPSearcher):
        support = replace(GPSearcher.support, joint_batch=False)
    source = ScalarGP(SearchSpace([Knob('x','ordinal',(0, 2))]))
    before = deepcopy(source.get_state())
    with pytest.raises(ValueError, match='^This GP variant does not implement joint batch proposals$'):
        source.suggest_batch(2)
    assert source.get_state() == before


@pytest.mark.parametrize('raises', [False, True])
def test_batch_preserves_caller_rng_threads_and_uses_cpu_only_rng_context(monkeypatch, raises):
    source = finite(); before = deepcopy(source.get_state())
    previous = torch.get_num_threads()
    rng = torch.random.get_rng_state().clone()
    original = torch.random.fork_rng
    def cpu_context(*args, **kwargs):
        # This is the external torch boundary: a CPU search must not initialize
        # accelerator RNG contexts even on a host with available accelerators.
        assert kwargs.get('devices') == []
        return original(*args, **kwargs)
    def sample():
        assert torch.get_num_threads() == 1
        torch.rand(7)
        if raises:
            raise RuntimeError('objective-independent sampler fault')
        return Config({'x': 3})
    monkeypatch.setattr(torch.random, 'fork_rng', cpu_context)
    monkeypatch.setattr(source, '_sample_random', sample)
    try:
        torch.set_num_threads(3)
        if raises:
            with pytest.raises(RuntimeError, match='sampler fault'):
                source.suggest_batch(1)
            assert source.get_state() == before
        else:
            assert source.suggest_batch(1) == [Config({'x': 3})]
        assert torch.get_num_threads() == 3
        assert torch.equal(torch.random.get_rng_state(), rng)
    finally:
        torch.set_num_threads(previous)
        torch.random.set_rng_state(rng)


def test_pending_initial_design_has_bounded_sampling_and_does_not_duplicate(monkeypatch):
    source = finite(2)
    source.trials['pending'] = Config({'x': 0})
    calls = []
    def sample():
        calls.append(1)
        return Config({'x': 0})
    monkeypatch.setattr(source, '_sample_random', sample)
    before = deepcopy(source.get_state())
    with pytest.raises(PendingSuggestionError,
            match='^No distinct GP location available within the sampling bound$'):
        source.suggest_batch(1)
    assert len(calls) == 1024  # The documented finite dispatch bound.
    assert source.get_state() == before
    monkeypatch.setattr(source, '_sample_random', lambda: Config({'x': 1}))
    assert source.suggest_batch(2) == [Config({'x': 1})]
    assert source.get_state()['proposal_batches'][-1]['pending_trial_ids'] == ['pending']


@pytest.mark.parametrize('winner', [(4, 11), (10, 11)])
def test_joint_finite_enumeration_checks_every_set_across_chunks(winner):
    choices = torch.arange(12, dtype=torch.double)[:, None]
    visited = []
    def score(points):
        pairs = [tuple(map(int, row[:, 0])) for row in points]
        visited.extend(pairs)
        return torch.tensor([7. if pair == winner else -3. for pair in pairs])
    selected, score_value = GPSearcher._joint_finite(score, choices, 2)
    assert visited == list(combinations(range(12), 2))
    assert selected[:, 0].tolist() == list(winner)
    assert float(score_value) == 7.


def test_finite_enumeration_accepts_exact_limit_and_refuses_excess():
    choices = torch.arange(4096, dtype=torch.double)[:, None]
    selected, score = GPSearcher._joint_finite(lambda x: x[..., 0].sum(dim=-1), choices, 1)
    assert selected.tolist() == [[4095.]] and float(score) == 4095.
    with pytest.raises(ValueError, match='^Joint finite GP enumeration exceeds 4096 candidate sets$'):
        GPSearcher._joint_finite(lambda x: pytest.fail('unbounded evaluation'),
            torch.arange(4097)[:, None], 1)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf')])
def test_joint_enumeration_rejects_nonfinite_values_in_any_chunk(bad):
    choices = torch.arange(12, dtype=torch.double)[:, None]
    def score(points):
        scores = points[..., 0].sum(dim=-1)
        scores[(points[:, 0, 0] == 10) & (points[:, 1, 0] == 11)] = bad
        return scores
    with pytest.raises(ValueError, match='^Nonfinite joint GP acquisition values$'):
        GPSearcher._joint_finite(score, choices, 2)


def fitted(continuous=False):
    source = GPSearcher(SearchSpace([Knob('x','continuous',(0., 1.))]) if continuous
        else SearchSpace([Knob('x','ordinal',(0, 2))]), seed=4, initial_random_samples=1)
    for i, x in enumerate((.1, .9) if continuous else (0, 2)):
        source.trials[str(i)] = Config({'x': x})
        source.observe(Result(str(i), float(x)))
    return source


def test_fitted_all_pending_refusal_is_explicit_and_atomic():
    source = fitted()
    for x in range(3): source.trials['pending'+str(x)] = Config({'x': x})
    before = deepcopy(source.get_state())
    with pytest.raises(PendingSuggestionError, match='^All finite GP locations are pending$'):
        source.suggest_batch(2)
    assert source.get_state() == before


@pytest.mark.parametrize('case', ['duplicate', 'pending', 'nan', 'vector'])
def test_invalid_optimizer_outputs_fail_atomically_with_actionable_reason(monkeypatch, case):
    source = fitted(continuous=True)
    source.trials['pending'] = Config({'x': .4})
    candidate = torch.tensor([[.2], [.2 if case == 'duplicate' else .4 if case == 'pending' else .7]], dtype=torch.double)
    score = torch.tensor(float('nan') if case == 'nan' else [1., 2.] if case == 'vector' else 1.)
    monkeypatch.setattr(implementation, 'optimize_acqf', lambda *a, **k: (candidate, score))
    before = deepcopy(source.get_state())
    message = ('GP acquisition returned duplicate or pending coordinates' if case in {'duplicate','pending'}
               else 'Nonfinite or nonscalar GP acquisition value')
    with pytest.raises(ValueError, match='^'+re.escape(message)+'$'):
        source.suggest_batch(2)
    assert source.get_state() == before


@pytest.mark.parametrize('domain_factory,message', [
    (lambda: SearchSpace([Knob('x','ordinal',(0,99))]), 'Joint finite GP enumeration exceeds 4096 candidate sets'),
    (lambda: SearchSpace([Knob('x','continuous',(0.,1.)), Knob('family','categorical',['a','b'])]),
        'Joint mixed GP batches require a bounded finite domain'),
])
def test_unqualified_joint_domain_has_precise_refusal(domain_factory, message):
    source = GPSearcher(domain_factory())
    with pytest.raises(ValueError, match='^'+re.escape(message)+'$'):
        source.suggest_batch(2)


def test_pending_state_is_explicit_and_legacy_batch_fields_are_optional():
    source = finite(3)
    source.trials['pending'] = Config({'x': 1})
    state = source.get_state()
    assert state['pending_trial_ids'] == ['pending']
    legacy = deepcopy(state)
    legacy.pop('pending_trial_ids'); legacy.pop('proposal_batches')
    target = finite(3); target.set_state(legacy)
    assert target.pending_locations() == [('pending', Config({'x': 1}))]
    assert target.proposal_batches == []


@pytest.mark.parametrize('case,message', [
    ('pending','GP pending locations differ from trial/observation ledgers'),
    ('not_list','GP batch proposal ledger must be a list'),
    ('extra_key','Invalid GP batch proposal record'),
    ('requested_bool','Invalid GP batch proposal record'),
    ('requested_large','Invalid GP batch proposal record'),
    ('pending_duplicate','Invalid GP batch proposal record'),
    ('pending_nonstring','Invalid GP batch proposal record'),
    ('nan_score','Invalid GP acquisition score'),
    ('bool_score','Invalid GP acquisition score'),
])
def test_corrupt_proposal_checkpoint_has_precise_atomic_refusal(case,message):
    source=finite(); source.suggest_batch(1)
    state=deepcopy(source.get_state())
    batch=state['proposal_batches'][0]
    if case=='pending':state['pending_trial_ids']=['unknown']
    if case=='not_list':state['proposal_batches']={}
    if case=='extra_key':batch['unexpected']=1
    if case=='requested_bool':batch['requested']=True
    if case=='requested_large':batch['requested']=9
    if case=='pending_duplicate':batch['pending_trial_ids']=['x','x']
    if case=='pending_nonstring':batch['pending_trial_ids']=[5]
    if case in {'nan_score','bool_score'}:
        batch['mode']='joint_qlogei'
        batch['log_acquisition']=float('nan') if case=='nan_score' else True
    target=finite(); before=deepcopy(target.get_state())
    with pytest.raises(ValueError,match='^'+re.escape(message)+'$'):
        target.set_state(state)
    assert target.get_state()==before


def test_pending_proposal_ledger_round_trip_with_nonempty_pending_ids():
    source=finite(); source.trials['pending']=Config({'x':0})
    source.suggest_batch(2)
    state=json.loads(json.dumps(source.get_state()))
    assert state['proposal_batches'][0]['pending_trial_ids']==['pending']
    target=finite(); target.set_state(state)
    assert json.loads(json.dumps(target.get_state()))==state


def test_constructor_diagnostics_identify_invalid_type_and_empty_domain():
    with pytest.raises(TypeError,match='^seed must be int or None, got float$'):
        GPSearcher(SearchSpace([Knob('x','ordinal',(0,2))]),seed=1.5)
    with pytest.raises(ValueError,match='^GP requires a nonempty search space$'):
        GPSearcher(SearchSpace([]))


@pytest.mark.parametrize('entrypoint',['suggest','suggest_batch'])
def test_scalar_mixed_domain_retains_qualified_relaxed_optimizer(entrypoint,monkeypatch):
    domain=SearchSpace([Knob('x','continuous',(0.,1.)),
                        Knob('family','categorical',['a','b'])])
    source=GPSearcher(domain,seed=7,initial_random_samples=1,num_restarts=1)
    for i,(x,family) in enumerate(((.1,'a'),(.9,'b'))):
        source.trials[str(i)]=Config({'x':x,'family':family})
        source.observe(Result(str(i),float(i)))
    expected=Config({'x':.625,'family':'a'})
    seen=[]
    def optimize(acquisition,*,bounds,q,num_restarts,raw_samples):
        assert q==1
        seen.append(q)
        return source._config_to_tensor(expected)[None,:],torch.tensor(.4)
    monkeypatch.setattr(implementation,'optimize_acqf',optimize)
    result=source.suggest() if entrypoint=='suggest' else source.suggest_batch(1)[0]
    assert result==expected and seen==[1]
