"""Prospective mathematical cost/quality rules and adverse finite controls."""
from copy import deepcopy
from fractions import Fraction as Q

import pytest

from validation.cost_acceptance import POLICY, exact_loss, optimum, slots, summarize, verify_observation, verify_slots
from workloads.cost_quadratic import evaluate


def test_unique_mathematical_optimum_and_physical_profile_boundaries():
    answer = optimum(); eta = answer['eta']
    assert .425 < eta < .625
    derivative = -(16/100)*(1-eta)**15-48*(1-3*eta)**15
    assert abs(derivative) < 1e-16
    for profile in POLICY['profiles']:
        for x in [.025, .225, .425, .625, eta]:
            row = evaluate(profile, {'eta': x})
            verify_observation(profile, row)
            assert exact_loss(x) >= Q(answer['value'])-Q(1, 10**18)
    assert evaluate('cost_decreases', {'eta': .425})['cost'] == 8
    assert evaluate('cost_increases', {'eta': .425})['cost'] == 24


def test_common_budget_excludes_overrun_incumbents_and_integrates_exactly():
    rows = [evaluate('constant', {'eta': .1}), evaluate('constant', {'eta': optimum()['eta']})]
    report = summarize('constant', rows, work_budget=20)
    assert report['physical_updates'] == 32 and report['overrun'] == 12
    assert report['completed_within_budget'] == 1
    assert report['final_loss'] == float(exact_loss(.1))
    assert report['integrated_loss'] == float(16*Q(101, 100)+4*exact_loss(.1))
    assert not report['automatic_default'] and not report['performance_superiority']
    with pytest.raises(ValueError, match='admitted'): summarize('constant', rows+[rows[0]], work_budget=20)


@pytest.mark.parametrize('damage', ['cost', 'replicas', 'iteration', 'state', 'endpoint', 'rate'])
def test_physical_evidence_damage_cannot_be_accepted(damage):
    row = evaluate('constant', {'eta': .4})
    if damage == 'cost': row['cost'] -= 1
    elif damage == 'replicas': row['replicas'].pop()
    elif damage == 'iteration': row['replicas'][0][0]['iteration'] = 2
    elif damage == 'state': row['replicas'][0][0]['state'][0] += .01
    elif damage == 'endpoint': row['value'] += .01
    elif damage == 'rate': row['config']['eta'] = .3
    with pytest.raises(ValueError): verify_observation('constant', row)


def test_roster_missingness_and_reported_regret_cannot_hide_an_unfavorable_slot():
    runs = []
    for profile, seed, method in slots():
        rows = []
        while sum(r['cost'] for r in rows) < POLICY['work_budget']:
            rows.append(evaluate(profile, {'eta': .1}))
        runs.append({'profile': profile, 'seed': seed, 'method': method, 'observations': rows,
                     'summary': summarize(profile, rows)})
    result = verify_slots(runs)
    # A deliberately poor optimizer can satisfy finite conformance, but never
    # obtains a superiority or default label from this verifier.
    assert result['status'] == 'PASS' and not result['superiority_claim'] and not result['default_activation']
    with pytest.raises(ValueError, match='roster'): verify_slots(runs[:-1])
    bad = deepcopy(runs); bad[0]['summary']['normalized_final_regret'] = 0.
    with pytest.raises(ValueError, match='summary'): verify_slots(bad)
    partial = deepcopy(runs); partial[0]['observations'] = []
    partial[0]['summary'] = summarize(partial[0]['profile'], [])
    assert verify_slots(partial)['status'] == 'INCONCLUSIVE'


def test_finite_physical_resource_bound_follows_from_integer_job_costs():
    bounds = []
    for profile, seed, method in slots():
        reachable = {0}; terminals = set()
        while reachable:
            spent = reachable.pop()
            for size in POLICY['profiles'][profile]:
                nxt = spent+8*size
                if nxt >= POLICY['work_budget']: terminals.add(nxt)
                else: reachable.add(nxt)
        bounds.append(max(terminals))
    assert sum(bounds) == POLICY['max_physical_updates'] == 2048
    assert POLICY['work_budget']//8 == POLICY['max_trials_per_study'] == 9


@pytest.mark.parametrize('method', POLICY['methods'])
def test_actual_method_replay_and_relabeling_refusal(method):
    from validation.cost_replay import replay_run, run_slot
    run = run_slot('cost_decreases', POLICY['seeds'][0], method)
    assert run['error'] is None
    replay = replay_run(run)
    assert replay['method_identity_verified']
    relabeled = deepcopy(run); relabeled['method'] = 'random' if method != 'random' else 'sobol'
    with pytest.raises(ValueError, match='identity'): replay_run(relabeled)
    seed = deepcopy(run); seed['seed'] = POLICY['seeds'][1]
    with pytest.raises(ValueError, match='proposal'): replay_run(seed)
    state = deepcopy(run); state['final_state_sha256'] = '0'*64
    with pytest.raises(ValueError, match='state'): replay_run(state)
    assert not replay['scientific_acceptance']


def test_failed_work_is_retained_and_cannot_pass(monkeypatch):
    import validation.cost_replay as replay
    def broken_observe(*args):
        raise RuntimeError('delivery failed after physical evaluation')
    monkeypatch.setattr(replay, 'observe', broken_observe)
    run = replay.run_slot('constant', POLICY['seeds'][0], 'random')
    assert len(run['observations']) == 1
    assert run['summary']['physical_updates'] == 16
    assert run['summary']['status'] == 'incomplete'
    assert replay.replay_run(run)['status'] == 'INCONCLUSIVE'
    assert not run['failed_attempt']['physical_work_unknown']
