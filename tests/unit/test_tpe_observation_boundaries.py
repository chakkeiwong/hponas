"""TPE endpoint, identity and recovery contracts against vendor trial state."""

from copy import deepcopy
import math

import optuna
import pytest

from hponas import Config, Knob, Result, SearchSpace, Trial
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers_tpe import TPESearcher


def searcher(endpoint=2.):
    return TPESearcher(SearchSpace([Knob('x', 'continuous', (0., 1.))]),
                       seed=17, model_fidelity=endpoint)


def register(s, tid='root', fidelity=2.):
    config, = s.propose(1)
    trial = Trial(Config(config), tid, fidelity=fidelity, root_trial_id=tid)
    s.register_trial(trial)
    return trial


def assert_refusal(s, message, call):
    state = deepcopy(s.state_dict())
    vendor = [(t.number, t.state, t.value, t.params) for t in s._study.trials]
    with pytest.raises(ValueError) as caught:
        call()
    assert str(caught.value) == message
    assert s.state_dict() == state
    assert [(t.number, t.state, t.value, t.params) for t in s._study.trials] == vendor


@pytest.mark.parametrize('endpoint', [True, False, '2', None, 0., -1., math.inf, -math.inf, math.nan])
def test_model_endpoint_requires_a_positive_finite_number(endpoint):
    with pytest.raises(ValueError) as caught:
        searcher(endpoint)
    assert str(caught.value) == 'Positive finite TPE model_fidelity required'


@pytest.mark.parametrize('scheduled', [False, True])
def test_study_endpoint_must_match_model_endpoint(scheduled):
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=2)) if scheduled else None
    s = searcher(2. if scheduled else 1.)
    s.validate_study_controls(1, scheduler)
    other = searcher(1. if scheduled else 2.)
    assert_refusal(other, 'TPE model_fidelity must match the full study endpoint',
                   lambda: other.validate_study_controls(1, scheduler))


@pytest.mark.parametrize('fidelity', [0., -1., 1., 3., math.nan, math.inf])
def test_direct_partial_or_invalid_fidelity_is_refused_before_telling_optuna(fidelity):
    s = searcher()
    config, = s.propose(1)
    assert_refusal(s, 'Direct TPE observe requires model fidelity; use Study for scheduler composition',
                   lambda: s.observe(dict(config=config, value=7., fidelity=fidelity)))
    s.observe(dict(config=config, value=7., fidelity=2.))
    assert s._study.trials[0].value == -7.


@pytest.mark.parametrize('extra', [{}, {'fidelity': None}, {'fidelity': 2.}])
def test_direct_legacy_missing_or_null_fidelity_means_the_complete_endpoint(extra):
    s = searcher()
    config, = s.propose(1)
    s.observe(dict(config=config, value=7., **extra))
    saved = deepcopy(s.state_dict())
    restored = searcher()
    restored.load_state_dict(saved)
    assert restored.state_dict() == saved
    assert restored._study.trials[0].value == -7.
    assert restored.propose(2) == s.propose(2)


def test_duplicate_direct_asks_require_identity_and_preserve_the_other_ask():
    s = TPESearcher(SearchSpace([Knob('x', 'categorical', ['a', 'b'])]))
    configs = s.propose(3)
    first, second = next((i, j) for i in range(3) for j in range(i+1, 3)
                         if configs[i] == configs[j])
    a, b = configs[first], configs[second]
    assert_refusal(s, 'TPE observation requires one pending ask; supply trial_number for duplicate configurations',
                   lambda: s.observe(dict(config=a, value=7.)))
    s.observe(dict(config=b, value=9., trial_number=second))
    assert s._study.trials[first].state == optuna.trial.TrialState.RUNNING
    assert s._study.trials[second].value == -9.
    s.observe(dict(config=a, value=7., trial_number=first))
    assert s._study.trials[first].value == -7.
    remaining = ({0, 1, 2} - {first, second}).pop()
    assert s._study.trials[remaining].state == optuna.trial.TrialState.RUNNING


@pytest.mark.parametrize('case,message', [
    ('duplicate', 'TPE evaluation identity already registered'),
    ('orphan', 'TPE promotion lacks a root ask'),
    ('unasked', 'TPE root lacks an unbound ask'),
    ('config', 'TPE root/ask configuration differs'),
    ('terminal', 'TPE root/ask configuration differs'),
    ('zero', 'TPE observation exceeds model fidelity'),
    ('excess', 'TPE observation exceeds model fidelity'),
])
def test_invalid_registration_preserves_the_ask_and_lineage(case, message):
    s = searcher()
    trial = register(s, fidelity=1.)
    invalid = Trial(Config(dict(trial.config.values)), 'promoted', fidelity=2., root_trial_id='root')
    if case == 'duplicate': invalid = trial
    elif case == 'orphan': invalid.root_trial_id = 'absent'
    elif case == 'unasked': invalid.root_trial_id = invalid.trial_id
    elif case == 'config': invalid.config.values['x'] = -1.
    elif case == 'terminal': s.finalize_pending()
    elif case == 'zero': invalid.fidelity = 0.
    elif case == 'excess': invalid.fidelity = 3.
    assert_refusal(s, message, lambda: s.register_trial(invalid))


@pytest.mark.parametrize('case', ['trial', 'config', 'fidelity', 'terminal'])
def test_result_requires_the_registered_evaluation_identity(case):
    s = searcher()
    trial = register(s)
    result = Result(trial.trial_id, 7., fidelity=2.)
    config = dict(trial.config.values)
    if case == 'trial': result.trial_id = 'absent'
    elif case == 'config': config['x'] = -1.
    elif case == 'fidelity': result.fidelity = 1.
    else: s.observe_result(result, config=config, maximize=False)
    message = 'TPE root ask is already terminal' if case == 'terminal' else 'TPE result lacks matching registered identity'
    assert_refusal(s, message, lambda: s.observe_result(result, config=config, maximize=False))


@pytest.mark.parametrize('registered', [False, True])
@pytest.mark.parametrize('maximize', [False, True])
@pytest.mark.parametrize('status,value', [('completed', 7.), ('failed', 7.), ('paused', 7.), ('completed', math.nan)])
def test_only_finite_completed_endpoints_train_in_the_declared_direction(registered, maximize, status, value):
    s = searcher()
    if registered:
        config = register(s).config.values
    else:
        config, = s.propose(1)
    result = Result('root', value, fidelity=2., status=status)
    s.observe_result(result, config=config, maximize=maximize)
    vendor = s._study.trials[0]
    valid = status == 'completed' and math.isfinite(value)
    assert vendor.state == (optuna.trial.TrialState.COMPLETE if valid else optuna.trial.TrialState.FAIL)
    assert vendor.value == ((-value if maximize else value) if valid else None)
    saved = s.state_dict()
    if not registered:
        assert saved['events'][-1]['result']['fidelity'] == 2.
    restored = searcher()
    restored.load_state_dict(saved)
    assert restored.state_dict() == saved


def test_partial_standalone_result_requires_root_registration():
    s = searcher()
    config, = s.propose(1)
    assert_refusal(s, 'Partial TPE observations require registered root identity',
        lambda: s.observe_result(Result('root', 999., fidelity=1.), config=config, maximize=True))


def test_registered_trial_checkpoint_is_detached_from_caller_mutation():
    s = searcher()
    trial = register(s)
    before = deepcopy(s.state_dict())
    trial.config.values['x'] = -1.
    trial.checkpoint = {'unexpected': True}
    assert s.state_dict() == before


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_nonfinite_direct_value_does_not_consume_the_pending_trial(value):
    s = searcher()
    config, = s.propose(1)
    assert_refusal(s, 'TPE requires a finite complete value',
                   lambda: s.observe(dict(config=config, value=value)))


def test_checkpoint_endpoint_mismatch_preserves_live_state_and_future_proposals():
    s = searcher()
    register(s)
    incompatible = searcher(3.).state_dict()
    assert_refusal(s, 'TPE checkpoint model fidelity differs', lambda: s.load_state_dict(incompatible))
    restored = searcher()
    restored.load_state_dict(s.state_dict())
    assert restored.propose(2) == s.propose(2)


def snapshot(s, trial, maximize, results):
    return dict(trials={trial.trial_id: trial.to_dict()}, roots={trial.trial_id: trial.trial_id},
                results={r.trial_id: r.to_dict() for r in results}, maximize=maximize)


@pytest.mark.parametrize('maximize', [False, True])
def test_snapshot_agrees_with_vendor_value_and_rejects_each_independent_mismatch(maximize):
    s = searcher()
    trial = register(s)
    result = Result('root', 7., fidelity=2.)
    s.observe_result(result, config=trial.config.values, maximize=maximize)
    state = snapshot(s, trial, maximize, [result])
    s.validate_study_snapshot(state)
    cases = [('missing', 'TPE registered evaluations differ from Study'),
             ('root', 'TPE evaluation lineage differs from Study'),
             ('config', 'TPE evaluation lineage differs from Study'),
             ('fidelity', 'TPE evaluation lineage differs from Study'),
             ('value', 'TPE fitted value differs from full-fidelity Study result'),
             ('duplicate', 'TPE fitted value differs from full-fidelity Study result'),
             ('partial', 'TPE trained on a partial or final-role observation')]
    for case, message in cases:
        altered = deepcopy(state)
        if case == 'missing': altered['trials'] = {}
        elif case == 'root': altered['roots']['root'] = 'other'
        elif case == 'config': altered['trials']['root']['config']['values']['x'] = -1.
        elif case == 'fidelity': altered['trials']['root']['fidelity'] = 1.
        elif case == 'value': altered['results']['root']['objective_value'] = 8.
        elif case == 'duplicate':
            altered['results']['extra'] = deepcopy(altered['results']['root'])
            altered['roots']['extra'] = 'root'
        else: altered['results']['root']['fidelity'] = 1.
        assert_refusal(s, message, lambda: s.validate_study_snapshot(altered))


def test_snapshot_cannot_claim_a_complete_result_for_a_pending_vendor_ask():
    s = searcher()
    trial = register(s)
    state = snapshot(s, trial, False, [Result('root', 7., fidelity=2.)])
    assert_refusal(s, 'TPE fitted value differs from full-fidelity Study result',
                   lambda: s.validate_study_snapshot(state))
