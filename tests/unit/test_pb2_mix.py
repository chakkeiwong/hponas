from copy import deepcopy

import pytest

from hponas.pb2_mix import PB2MixExplorer
from hponas.population import PopulationCheckpoint, make_member
from hponas.population_search import LocalPBT
from workloads.finite_mdp import FiniteMDP


def task():
    return FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1)


def members():
    return {str(i): make_member({'width': 2, 'depth': 1, 'input_dim': 1, 'output_dim': 3},
                               {'learning_rate': 0.03*(i+1), 'momentum': [0, 0.25, 0.5][i%3]}, seed=i)
            for i in range(4)}


def test_pb2_mix_uses_actual_increments_categories_and_replay(tmp_path):
    pop = PopulationCheckpoint(tmp_path/'population.json', task(), members(), max_updates=16)
    explorer = PB2MixExplorer(increment_bound=1, seed=3, horizon=4, fit_iterations=2)
    controller = LocalPBT(tmp_path/'controller.json', pop, seed=7, explorer=explorer)
    result = controller.run(2, updates_per_round=2)
    for index, row in enumerate(result['rounds']):
        evidence = row['exploration']
        assert len(evidence['x']) == (index+1)*4
        expected = [(result['rounds'][i]['scores'][name]-old['score'])
                    for i in range(index+1) for name, old in result['rounds'][i]['training_inputs'].items()]
        assert evidence['increments'] == pytest.approx(expected, abs=1e-15)
        action = row['plan'][0]
        category = evidence['selection']['selected'][0]
        assert action['optimizer']['momentum'] == explorer.contract['momenta'][category]
        assert 0.001 <= action['optimizer']['learning_rate'] <= 1
        candidates = evidence['acquisitions'][0]['evaluations']
        assert evidence['acquisitions'][0]['selected']['ucb'] == max(x['ucb'] for x in candidates)
        assert len(evidence['bandit']['payload']['history']) == index
    before = pop.snapshot()
    recovered = LocalPBT(tmp_path/'controller.json', PopulationCheckpoint(tmp_path/'population.json', task()),
                         seed=7, explorer=PB2MixExplorer(increment_bound=1, seed=3, horizon=4, fit_iterations=2))
    assert recovered.run(2, updates_per_round=2) == result
    assert pop.snapshot() == before
    assert pop.accounting()['upper'] == 16


def test_explicit_gain_bound_is_not_estimated_from_favorable_outcomes():
    explorer = PB2MixExplorer(increment_bound=1)
    assert explorer._increment(-1) == -1
    assert explorer._increment(1) == 1
    with pytest.raises(ValueError, match='declared objective bound'):
        explorer._increment(1.1)


def test_changed_pb2_options_refuse_resume(tmp_path):
    pop = PopulationCheckpoint(tmp_path/'population.json', task(), members())
    LocalPBT(tmp_path/'controller.json', pop, explorer=PB2MixExplorer(increment_bound=1))
    with pytest.raises(ValueError, match='options'):
        LocalPBT(tmp_path/'controller.json', pop, explorer=PB2MixExplorer(increment_bound=2))


def test_population_refuses_optimistic_gain_scale_before_any_training(tmp_path):
    pop = PopulationCheckpoint(tmp_path/'population.json', task(), members())
    with pytest.raises(ValueError, match='analytic objective range'):
        LocalPBT(tmp_path/'controller.json', pop, explorer=PB2MixExplorer(increment_bound=0.1))
    assert pop.accounting()['upper'] == 0
