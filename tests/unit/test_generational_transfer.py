from copy import deepcopy

import pytest

from hponas import generational_transfer
from hponas.generational_transfer import ArchitectureGeneration
from hponas.population import make_member
from workloads.finite_mdp import FiniteMDP


def task():
    return FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1,
                    rl_weight=1, policy_weight=5, value_weight=0)


def options():
    config = dict(width=2, depth=1, input_dim=1, output_dim=3)
    teacher = make_member(config, {'learning_rate': 0.05, 'momentum': 0.25}, seed=5)
    proposals = [{**config, 'width': width, 'depth': depth} for width, depth in [(1, 1), (2, 1), (3, 2), (4, 2)]]
    return dict(teacher=teacher, proposals=proposals, survivors=2, rungs=[1, 2, 4], seed=17, max_updates=10)


def test_known_halving_allocation_teacher_and_successor_recovery(tmp_path):
    kwargs = options()
    before = deepcopy(kwargs['teacher'])
    generation = ArchitectureGeneration(tmp_path, task(), **kwargs)
    result = generation.run()
    assert result['status'] == 'complete'
    assert result['accounting'] == {'lower': 10, 'upper': 10, 'allocated': 10}
    assert len(result['survivors']) == 2
    assert [len(row['scores']) for row in result['rungs']] == [4, 2, 2]
    for row in result['rungs']:
        selected = [row['scores'][str(i)] for i in row['survivors']]
        rejected = [row['scores'][str(i)] for i in row['eliminated']]
        assert not rejected or min(selected) >= max(rejected)
    for member in result['survivors'].values():
        assert member['updates'] == 4
    for index in range(4):
        store = generation._store(index)
        assert store.snapshot()['members']['teacher'] == before
        assert store.accounting()['upper'] in {1, 4}
    assert kwargs['teacher'] == before
    recovered = ArchitectureGeneration(tmp_path, task(), **kwargs)
    assert recovered.run() == result
    assert recovered.accounting()['upper'] == 10


class Crash(BaseException):
    pass


@pytest.mark.parametrize('boundary', [1, 2, 3, 4])
@pytest.mark.parametrize('timing', ['before', 'after'])
def test_generation_boundaries_do_not_repeat_candidate_training(tmp_path, monkeypatch, boundary, timing):
    baseline = ArchitectureGeneration(tmp_path/'baseline', task(), **options()).run()
    generation = ArchitectureGeneration(tmp_path/'crash', task(), **options())
    original = generational_transfer.atomic_json
    calls = 0

    def write(path, value):
        nonlocal calls
        calls += 1
        if calls == boundary and timing == 'before':
            raise Crash()
        original(path, value)
        if calls == boundary and timing == 'after':
            raise Crash()

    monkeypatch.setattr(generational_transfer, 'atomic_json', write)
    with pytest.raises(Crash):
        generation.run()
    monkeypatch.setattr(generational_transfer, 'atomic_json', original)
    assert ArchitectureGeneration(tmp_path/'crash', task(), **options()).run() == baseline
    assert generation.accounting()['upper'] == 10


def test_generation_refuses_insufficient_budget_and_wrong_loss_contract(tmp_path):
    with pytest.raises(ValueError, match='budget'):
        ArchitectureGeneration(tmp_path/'low', task(), **{**options(), 'max_updates': 9})
    convex = FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1)
    with pytest.raises(ValueError, match='independent RL'):
        ArchitectureGeneration(tmp_path/'loss', convex, **options())
