from copy import deepcopy

import pytest

from hponas.bg_population import BGPopulationExplorer
from hponas.bg_pbt import LocalBGPBT
from hponas import bg_pbt
from hponas.population import PopulationCheckpoint, make_member
from hponas.population_search import LocalPBT
from workloads.finite_mdp import FiniteMDP


def task(rewards=None):
    return FiniteMDP([1], [[[0], [0]]], [[1, 0]] if rewards is None else rewards,
                    horizon=1, rl_weight=1, policy_weight=5, value_weight=0)


def config(width=2, depth=1):
    return dict(width=width, depth=depth, input_dim=1, output_dim=3, activation='tanh')


def members():
    return {str(i): make_member(config(i+1), {'learning_rate': 0.1, 'momentum': 0.25}, seed=i+5) for i in range(2)}


def test_contextual_region_and_global_restart_are_actual_gp_paths(tmp_path):
    # Constant rewards force unsuccessful updates; two contractions collapse
    # the radius and exercise the mandatory global GP restart path.
    store = PopulationCheckpoint(tmp_path/'population.json', task([[0, 0]]), members(), max_updates=6)
    explorer = BGPopulationExplorer(increment_bound=1, fit_iterations=1, failure_tolerance=1,
                                    initial_numeric=0.2, minimum_numeric=0.15)
    controller = LocalPBT(tmp_path/'controller.json', store, explorer=explorer)
    result = controller.run(3, updates_per_round=1)
    assert result['rounds'][1]['exploration']['region']['restarts'] == 1
    for row in result['rounds']:
        diagnostic = row['exploration']
        assert diagnostic['gp_options']['family'] == 'bgpbt'
        if diagnostic['restart']:
            restart = diagnostic['restart']
            assert restart['ucb'][restart['index']] == max(restart['ucb'])
        for acquisition in diagnostic['acquisitions']:
            selected = acquisition['selected']
            center = acquisition['center']
            assert selected[2:4] == center[2:4]  # width and depth stay fixed context
            assert selected[5:] == center[5:]
            assert acquisition['numeric_bounds'][0] <= selected[1] <= acquisition['numeric_bounds'][1]
            assert selected[4] in acquisition['categories']
    assert controller.run(3, updates_per_round=1) == result
    assert store.accounting()['upper'] == 6


def test_two_bg_generations_use_frozen_teacher_architecture_bo_and_exact_budget(tmp_path):
    initial = members()
    pool = [config(w, d) for w, d in [(1, 1), (2, 1), (3, 1), (2, 2)]]
    kwargs = dict(increment_bound=1, generations=2, max_rounds=1, patience=1,
                  updates_per_round=1, distillation_rungs=(1, 2), seed=7, max_updates=10, fit_iterations=1)
    controller = LocalBGPBT(tmp_path, task(), initial, pool, **kwargs)
    result = controller.run()
    assert result['status'] == 'complete'
    assert result['accounting'] == {'lower': 10, 'upper': 10, 'allocated': 10}
    first, second = result['generations']
    assert first['trigger'] == second['trigger'] == 'maximum_age'
    assert len(first['architecture_search']['bo_indices']) == 1
    assert len(first['architecture_search']['random_indices']) == 3
    assert first['transfer_accounting']['upper'] == 6
    assert first['teacher_sha256']
    assert len(result['final_members']) == 2
    assert LocalBGPBT(tmp_path, task(), initial, pool, **kwargs).run() == result
    with pytest.raises(ValueError, match='budget'):
        LocalBGPBT(tmp_path/'under', task(), initial, pool, **{**kwargs, 'max_updates': 9})


@pytest.fixture(scope='module')
def generation_reference(tmp_path_factory):
    pool = [config(w, d) for w, d in [(1, 1), (2, 1), (3, 1), (2, 2)]]
    kwargs = dict(increment_bound=1, generations=2, max_rounds=1, patience=1,
                  updates_per_round=1, distillation_rungs=(1, 2), seed=7, max_updates=10, fit_iterations=1)
    result = LocalBGPBT(tmp_path_factory.mktemp('bg-reference'), task(), members(), pool, **kwargs).run()
    return pool, kwargs, result


class Crash(BaseException):
    pass


@pytest.mark.parametrize('boundary', range(1, 8))
@pytest.mark.parametrize('timing', ['before', 'after'])
def test_generation_program_acknowledgements_resume_exactly(tmp_path, monkeypatch, generation_reference, boundary, timing):
    pool, kwargs, expected = generation_reference
    controller = LocalBGPBT(tmp_path, task(), members(), pool, **kwargs)
    original_write = bg_pbt.atomic_json
    calls = 0

    def write(path, value):
        nonlocal calls
        calls += 1
        if calls == boundary and timing == 'before':
            raise Crash()
        original_write(path, value)
        if calls == boundary and timing == 'after':
            raise Crash()

    monkeypatch.setattr(bg_pbt, 'atomic_json', write)
    with pytest.raises(Crash):
        controller.run()
    monkeypatch.setattr(bg_pbt, 'atomic_json', original_write)
    assert LocalBGPBT(tmp_path, task(), members(), pool, **kwargs).run() == expected
