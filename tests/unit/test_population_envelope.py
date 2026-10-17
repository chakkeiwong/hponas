"""Reject impossible population schedules before any training or publication."""
from copy import deepcopy

import pytest

from hponas.bg_pbt import LocalBGPBT
from hponas.generational_transfer import ArchitectureGeneration
from hponas.pb2_mix import PB2MixExplorer
from hponas.population import PopulationCheckpoint, make_member
from hponas.population_search import LocalPBT
from workloads.finite_mdp import FiniteMDP


def inputs():
    task = FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1,
                     rl_weight=1, policy_weight=5, value_weight=0)
    pool = [dict(width=w, depth=d, input_dim=1, output_dim=3, activation='tanh')
            for w, d in [(1, 1), (2, 1), (3, 1), (2, 2)]]
    members = {str(i): make_member(pool[i], {'learning_rate': 0.1, 'momentum': 0.25}, seed=i)
               for i in range(2)}
    return task, pool, members


@pytest.mark.parametrize('problem', ['gp_capacity', 'bandit_horizon'])
def test_local_schedule_refused_before_first_gradient(tmp_path, monkeypatch, problem):
    task, _, members = inputs()
    if problem == 'gp_capacity':
        members = {str(i): deepcopy(members[str(i % 2)]) for i in range(4)}
    rounds = 128 if problem == 'gp_capacity' else 3
    explorer = PB2MixExplorer(increment_bound=1, horizon=128 if problem == 'gp_capacity' else 2)
    store = PopulationCheckpoint(tmp_path/'population.json', task, members, max_updates=1024)
    controller = LocalPBT(tmp_path/'controller.json', store, explorer=explorer)

    def unexpected(*args, **kwargs):
        pytest.fail('Training started before rejecting an unsupported full schedule')

    monkeypatch.setattr(store, 'train', unexpected)
    before = store.snapshot()
    with pytest.raises(ValueError, match='envelope|horizon'):
        controller.run(rounds, updates_per_round=1)
    assert store.snapshot() == before
    assert controller._read()['rounds'] == []


@pytest.mark.parametrize('problem', ['dimensions', 'rung', 'population_budget', 'gp_capacity', 'gain_bound'])
def test_bg_contract_refused_before_program_publication(tmp_path, problem):
    task, pool, members = inputs()
    options = dict(increment_bound=1, generations=2, max_rounds=1, patience=1,
                   distillation_rungs=(1, 2), max_updates=1000000, fit_iterations=1)
    if problem == 'dimensions':
        pool[-1]['input_dim'] = 2
    elif problem == 'rung':
        options['distillation_rungs'] = (1, 1025)
    elif problem == 'population_budget':
        options.update(max_rounds=33, updates_per_round=1024)
    elif problem == 'gp_capacity':
        members = {str(i): deepcopy(members[str(i % 2)]) for i in range(4)}
        pool += [{**config, 'width': config['width']+10} for config in pool]
        options['max_rounds'] = 128
    else:
        options['increment_bound'] = 0.5
    with pytest.raises(ValueError):
        LocalBGPBT(tmp_path/'program', task, members, pool, **options)
    assert not (tmp_path/'program').exists()


def test_generation_rejects_incompatible_teacher_before_publication(tmp_path):
    task, pool, members = inputs()
    teacher = make_member({**pool[0], 'output_dim': 4}, members['0']['optimizer'])
    with pytest.raises(ValueError):
        ArchitectureGeneration(tmp_path/'transfer', task, teacher, pool,
                               survivors=2, rungs=(1, 2), max_updates=6)
    assert not (tmp_path/'transfer').exists()
