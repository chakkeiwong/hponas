"""Independent finite-MDP identities and process-interruption transfer controls."""
from copy import deepcopy
from fractions import Fraction
import json
import math

import pytest
import torch

from hponas import population
from hponas.population import PopulationCheckpoint, make_member, restore_member
from hponas import population_search
from hponas.population_search import LocalPBT
from workloads.finite_mdp import FiniteMDP


def mdp():
    return FiniteMDP([1.0], [[[0.0], [0.0]]], [[1.0, 0.0]], horizon=1)


def config(width=2, depth=1):
    return dict(width=width, depth=depth, input_dim=1, output_dim=3,
                activation='tanh', normalization='none')


OPTIONS = {'learning_rate': 0.05, 'momentum': 0.2}


def members():
    parent = make_member(config(), OPTIONS, seed=11)
    model, _ = restore_member(parent)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model[-1].bias[:] = torch.tensor([math.log(3), 0, 0.75])
    parent['tensors'] = population._arrays(model.state_dict())
    parent['velocity'] = population._arrays({k: torch.full_like(v, 0.125) for k, v in model.named_parameters()})
    parent['updates'] = 7
    return {'parent': parent, 'child': make_member(config(), OPTIONS, seed=31)}


def request(mode='DISTILL', policy='RESET', weights=(1, 0)):
    return dict(event_id='event-1', parent='parent', child='child',
                architecture=config(3, 2) if mode == 'DISTILL' else config(),
                optimizer=OPTIONS, mode=mode, optimizer_policy=policy,
                weights=weights if mode == 'DISTILL' else (), seed=19)


def table_model(probabilities, values):
    model = torch.nn.Linear(len(values), 3, bias=False).double()
    with torch.no_grad():
        model.weight[:] = torch.tensor([[math.log(float(p)) for p in probabilities],
                                        [math.log(float(1-p)) for p in probabilities],
                                        values], dtype=torch.float64)
    return model


@pytest.mark.parametrize('wrapper', ['callable', 'buffer_only', 'parameterless'])
def test_finite_mdp_callable_and_parameterless_known_answer(wrapper):
    outputs = torch.tensor([[0.0, 0.0, 0.25]], dtype=torch.float64, requires_grad=True)
    targets = torch.tensor([[math.log(3), 0.0, 0.75]], dtype=torch.float64, requires_grad=True)

    class Table(torch.nn.Module):
        def __init__(self, value):
            super().__init__()
            if wrapper == 'buffer_only':
                self.register_buffer('value', value)
            else:
                self.value = value

        def forward(self, observations):
            assert observations.device == self.value.device
            return self.value

    student = (lambda observations: outputs) if wrapper == 'callable' else Table(outputs)
    teacher = (lambda observations: targets) if wrapper == 'callable' else Table(targets)
    result = mdp().components(student, teacher, 0.0)
    assert result['return'].item() == pytest.approx(0.5, abs=1e-14)
    assert result['loss'].item() == pytest.approx(-0.5, abs=1e-14)
    assert result['occupancy'].tolist() == [1.0]
    result['loss'].backward()
    assert outputs.grad.tolist()[0] == pytest.approx([-0.25, 0.25, 0.0], abs=1e-14)
    assert targets.grad is None
    outputs.grad = None
    result = mdp().components(student, teacher, 1.0)
    result['loss'].backward()
    assert outputs.grad.tolist()[0] == pytest.approx([-0.25, 0.25, -0.5], abs=1e-14)
    assert targets.grad is None


def test_exact_path_expectation_occupancy_and_independent_gradients():
    # The root action selects one of two terminal contexts. Enumerate its
    # path probabilities with Fractions independently of the implementation.
    env = FiniteMDP([1, 0, 0], [[[0, 1, 0], [0, 0, 1]],
                              [[0, 0, 0], [0, 0, 0]],
                              [[0, 0, 0], [0, 0, 0]]],
                    [[0, 0], [0, 4], [2, 0]], horizon=2)
    p = [Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)]
    q = [Fraction(3, 4), Fraction(1, 4), Fraction(1, 2)]
    student = table_model(p, [0.5, 1.5, -1])
    teacher = table_model(q, [0, 1, 2])
    result = env.components(student, teacher, 0)
    expected = p[0] * (1-p[1]) * 4 + (1-p[0]) * p[2] * 2
    assert expected == Fraction(13, 8)
    assert result['return'].item() == pytest.approx(float(expected), abs=1e-14)
    assert result['occupancy'].tolist() == pytest.approx([1, 0.25, 0.75], abs=1e-14)
    result['loss'].backward()
    assert student.weight.grad[0].tolist() == pytest.approx([-3/32, 1/4, -9/32], abs=1e-14)
    assert teacher.weight.grad is None
    student.zero_grad()
    result = env.components(student, teacher, 1)
    weights = [Fraction(1, 2), Fraction(1, 8), Fraction(3, 8)]
    expected_kl = sum(float(w) * (float(t)*math.log(float(t/s))
                      + float(1-t)*math.log(float((1-t)/(1-s)))) for w, s, t in zip(weights, p, q))
    expected_value = sum(float(w)*d*d/2 for w, d in zip(weights, [0.5, 0.5, -3]))
    assert result['policy_kl'].item() == pytest.approx(expected_kl, abs=1e-14)
    assert result['value_error'].item() == pytest.approx(expected_value, abs=1e-14)
    result['loss'].backward()
    assert student.weight.grad[0].tolist() == pytest.approx([float(w*(s-t)) for w, s, t in zip(weights, p, q)], abs=1e-14)
    assert student.weight.grad[2].tolist() == pytest.approx([float(w)*d for w, d in zip(weights, [0.5, 0.5, -3])], abs=1e-14)
    changed = table_model([Fraction(3, 4), *p[1:]], [0.5, 1.5, -1])
    assert env.components(changed, teacher, 1)['occupancy'].tolist() == pytest.approx([1, 0.75, 0.25])


@pytest.mark.parametrize('policy', ['COPY', 'RESET'])
def test_compatible_exploit_copy_optimizer_policy_and_exactly_once(tmp_path, policy):
    initial = members()
    store = PopulationCheckpoint(tmp_path/'population.json', mdp(), initial)
    result = store.exploit(**request('COPY', policy))
    state = store.snapshot()
    assert result['status'] == 'committed'
    assert state['members']['parent'] == initial['parent']
    assert state['members']['child']['tensors'] == initial['parent']['tensors']
    assert state['members']['child']['updates'] == 7
    if policy == 'COPY':
        assert state['members']['child']['velocity'] == initial['parent']['velocity']
    else:
        _, velocity = restore_member(state['members']['child'])
        assert all(torch.count_nonzero(v) == 0 for v in velocity.values())
    assert store.exploit(**request('COPY', policy)) == result
    assert store.snapshot() == state
    assert store.accounting() == {'work_unit': 'finite_expectation_gradient_update', 'lower': 0, 'upper': 0}
    assert len(state['lineage']) == 1
    with pytest.raises(ValueError, match='different request'):
        store.exploit(**{**request('COPY', policy), 'seed': 20})


def test_real_architecture_distillation_and_teacher_isolation(tmp_path):
    task = mdp()
    initial = members()
    store = PopulationCheckpoint(tmp_path/'population.json', task, initial)
    args = request(weights=(*([1]*16), 0.5, 0))
    before, _ = restore_member(make_member(args['architecture'], OPTIONS, seed=19))
    teacher, _ = restore_member(initial['parent'])
    start = task.components(before, teacher, 1)
    result = store.exploit(**args)
    assert result['status'] == 'committed'
    state = store.snapshot()
    after, _ = restore_member(state['members']['child'])
    finish = task.components(after, teacher, 1)
    assert finish['policy_kl'] < start['policy_kl']
    assert finish['value_error'] < start['value_error']
    assert state['members']['child']['architecture'] == args['architecture']
    assert state['members']['parent'] == initial['parent']
    assert store.accounting()['lower'] == store.accounting()['upper'] == 18
    assert len(result['trace']) == 18
    assert result['trace'][-1]['loss'] == -result['trace'][-1]['return']
    assert not all(torch.equal(a, b) for a, b in zip(before.parameters(), after.parameters()))


class Crash(BaseException):
    pass


@pytest.mark.parametrize('boundary', range(1, 7))
@pytest.mark.parametrize('timing', ['before', 'after'])
def test_each_durable_transfer_boundary(tmp_path, monkeypatch, boundary, timing):
    initial = members()
    reference = PopulationCheckpoint(tmp_path/'reference.json', mdp(), initial)
    expected = reference.exploit(**request())
    store = PopulationCheckpoint(tmp_path/'interrupted.json', mdp(), initial)
    original_write = population.atomic_json
    writes = 0

    def interrupted_write(path, value):
        nonlocal writes
        writes += 1
        if writes == boundary and timing == 'before':
            raise Crash()
        original_write(path, value)
        if writes == boundary and timing == 'after':
            raise Crash()

    monkeypatch.setattr(population, 'atomic_json', interrupted_write)
    with pytest.raises(Crash):
        store.exploit(**request())
    monkeypatch.setattr(population, 'atomic_json', original_write)
    recovered = PopulationCheckpoint(tmp_path/'interrupted.json', mdp())
    before = recovered.snapshot()['events'].get('event-1')
    uncertain = before is not None and before['inflight']
    result = recovered.exploit(**request())
    state = recovered.snapshot()
    assert state['members']['parent'] == initial['parent']
    if uncertain:
        assert result['status'] == 'interrupted'
        assert state['members']['child'] == initial['child']
        assert state['lineage'] == []
        assert recovered.accounting()['upper'] == recovered.accounting()['lower'] + 1
    else:
        assert result == expected
        assert state['members']['child'] == reference.snapshot()['members']['child']
        assert recovered.accounting()['lower'] == recovered.accounting()['upper'] == 2
    assert recovered.exploit(**request()) == result
    assert recovered.snapshot() == state


def test_failed_transfer_rolls_back_child_retains_spent_work(tmp_path, monkeypatch):
    task = mdp()
    store = PopulationCheckpoint(tmp_path/'state.json', task, members())
    before = store.snapshot()['members']
    components = task.components
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError('intentional nonfinite training failure')
        return components(*args)

    monkeypatch.setattr(task, 'components', fail_second)
    outcome = store.exploit(**request())
    assert outcome['status'] == 'failed'
    assert 'intentional' in outcome['error']
    assert store.snapshot()['members'] == before
    assert store.accounting()['lower'] == 1 and store.accounting()['upper'] == 2
    assert store.exploit(**request()) == outcome and calls == 2


def test_copy_refuses_shape_or_function_optimizer_mismatch(tmp_path):
    store = PopulationCheckpoint(tmp_path/'state.json', mdp(), members())
    original = store.snapshot()
    with pytest.raises(ValueError, match='Incompatible'):
        store.exploit(**{**request('COPY', 'COPY'), 'architecture': config(4)})
    with pytest.raises(ValueError, match='function'):
        store.exploit(**{**request('COPY', 'COPY'), 'architecture': {**config(), 'activation': 'relu'}})
    assert store.snapshot() == original
    outcome = store.exploit(**{**request('COPY', 'RESET'), 'architecture': {**config(), 'activation': 'relu'}})
    assert outcome['status'] == 'committed'


def test_restart_and_construction_preserve_global_rng(tmp_path):
    torch.manual_seed(10)
    rng = torch.random.get_rng_state().clone()
    store = PopulationCheckpoint(tmp_path/'state.json', mdp(), members())
    args = {**request('RESTART'), 'architecture': config(5)}
    outcome = store.exploit(**args)
    assert torch.equal(torch.random.get_rng_state(), rng)
    assert outcome['candidate'] == make_member(config(5), OPTIONS, seed=19)
    assert outcome['candidate']['updates'] == 0


def test_checkpoint_integrity_objective_and_lineage_refusals(tmp_path):
    path = tmp_path/'state.json'
    task = mdp()
    store = PopulationCheckpoint(path, task, members())
    store.exploit(**request('COPY', 'COPY'))
    original = path.read_text()
    data = json.loads(original)
    data['payload']['members']['child']['updates'] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='checksum'):
        store.snapshot()
    path.write_text(original)
    changed = FiniteMDP([1.0], [[[0.0], [0.0]]], [[0, 1]], horizon=1)
    with pytest.raises(ValueError, match='objective'):
        PopulationCheckpoint(path, changed)
    data = json.loads(original)
    data['payload']['lineage'] = []
    data['sha256'] = population._digest(data['payload'])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='lineage'):
        store.snapshot()
    path.write_text(original)
    task.rewards[0, 0] = 2
    with pytest.raises(ValueError, match='changed'):
        store.snapshot()


@pytest.mark.parametrize('weights', [[], [1], [0, 0], [1, 1], [1, 0, 0.5, 0], [1, float('nan'), 0], [True, 0]])
def test_refuse_undeclared_or_invalid_annealing(tmp_path, weights):
    store = PopulationCheckpoint(tmp_path/'state.json', mdp(), members())
    with pytest.raises(ValueError, match='anneal'):
        store.exploit(**request(weights=weights))
    assert not store.snapshot()['events']


@pytest.mark.parametrize('bad', [-0.1, 1.1, float('nan'), True])
def test_invalid_mdp_discount_refused(bad):
    with pytest.raises(ValueError):
        FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1, discount=bad)


def test_published_distillation_coefficients_keep_rl_active():
    env = FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1,
                    rl_weight=1, policy_weight=5, value_weight=0)
    student = table_model([Fraction(1, 2)], [4])
    teacher = table_model([Fraction(3, 4)], [-10])
    result = env.components(student, teacher, 1)
    result['loss'].backward()
    assert student.weight.grad[0, 0].item() == pytest.approx(-1.5, abs=1e-14)
    assert student.weight.grad[2, 0].item() == 0
    final = env.components(student, teacher, 0)
    assert final['loss'].item() == -0.5


def test_population_budget_and_resigned_member_change_refused(tmp_path):
    store = PopulationCheckpoint(tmp_path/'state.json', mdp(), members(), max_updates=2)
    assert store.train('train-1', 'parent', 2)['status'] == 'committed'
    before = store.snapshot()
    with pytest.raises(ValueError, match='remaining update budget'):
        store.train('train-2', 'child', 1)
    assert store.snapshot() == before
    assert store.train('train-1', 'parent', 2)['status'] == 'committed'
    assert store.accounting()['upper'] == 2
    data = json.loads(store.path.read_text())
    data['payload']['members']['parent']['updates'] += 1
    data['sha256'] = population._digest(data['payload'])
    store.path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='lineage replay'):
        store.snapshot()


def pbt_members():
    return {str(i): make_member(config(), {**OPTIONS, 'learning_rate': 0.03*(i+1)}, seed=i)
            for i in range(4)}


def test_pbt_truncation_lineage_exploration_and_budget(tmp_path):
    store = PopulationCheckpoint(tmp_path/'population.json', mdp(), pbt_members(), max_updates=16)
    controller = LocalPBT(tmp_path/'pbt.json', store, seed=7)
    result = controller.run(2, updates_per_round=2)
    for index, row in enumerate(result['rounds']):
        assert row['status'] == 'complete'
        assert len(row['plan']) == 1
        action = row['plan'][0]
        assert row['scores'][action['parent']] == max(row['scores'].values())
        assert row['scores'][action['child']] == min(row['scores'].values())
        snapshot = store.snapshot()
        event = snapshot['events'][action['event_id']]
        assert event['candidate']['tensors'] == event['teacher']['tensors']
        assert event['candidate']['velocity'] == event['teacher']['velocity']
        assert event['candidate']['optimizer']['learning_rate'] == pytest.approx(
            event['teacher']['optimizer']['learning_rate'] * action['factor'])
        assert len([e for e in snapshot['events'] if e.startswith(f'pbt:{index}:train:')]) == 4
    assert store.accounting()['lower'] == store.accounting()['upper'] == 16
    retained = store.snapshot()
    assert controller.run(2, updates_per_round=2) == result
    assert store.snapshot() == retained
    with pytest.raises(ValueError, match='remaining update budget'):
        controller.run(3, updates_per_round=2)
    assert store.snapshot() == retained


@pytest.mark.parametrize('boundary', [1, 2, 3])
@pytest.mark.parametrize('timing', ['before', 'after'])
def test_pbt_controller_acknowledgement_recovery(tmp_path, monkeypatch, boundary, timing):
    initial = pbt_members()
    baseline = PopulationCheckpoint(tmp_path/'baseline-pop.json', mdp(), initial)
    expected = LocalPBT(tmp_path/'baseline-pbt.json', baseline, seed=7).run(1, updates_per_round=1)
    store = PopulationCheckpoint(tmp_path/'population.json', mdp(), initial)
    controller = LocalPBT(tmp_path/'pbt.json', store, seed=7)
    original_write = population_search.atomic_json
    writes = 0

    def fail_write(path, value):
        nonlocal writes
        writes += 1
        if writes == boundary and timing == 'before':
            raise Crash()
        original_write(path, value)
        if writes == boundary and timing == 'after':
            raise Crash()

    monkeypatch.setattr(population_search, 'atomic_json', fail_write)
    with pytest.raises(Crash):
        controller.run(1, updates_per_round=1)
    monkeypatch.setattr(population_search, 'atomic_json', original_write)
    recovered = LocalPBT(tmp_path/'pbt.json', PopulationCheckpoint(tmp_path/'population.json', mdp()), seed=7)
    assert recovered.run(1, updates_per_round=1) == expected
    assert store.snapshot() == baseline.snapshot()
    assert store.accounting()['upper'] == 4
