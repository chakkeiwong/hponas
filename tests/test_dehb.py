"""Behavioral DEHB report, mixed-space and durable continuation checks."""
from copy import deepcopy
import json
import numpy as np
import pytest

from hponas import DEHBController, SearchSpace, Knob, Result, LocalExecutor


def space():
    return SearchSpace([Knob('x', 'continuous', (0., 1.)), Knob('y', 'continuous', (0., 1.))])


def report(controller, trial):
    value = sum((x - .375)**2 for x in trial.config.values.values()) + 1 / trial.fidelity
    result = Result(trial.trial_id, value, trial.fidelity, trial.fidelity)
    controller.tell(result)
    return result


def test_checkpoint_json_continues_at_every_boundary_and_preserves_pending_identity():
    uninterrupted = DEHBController(space(), seed=3)
    resumed = DEHBController(space(), seed=3)
    for _ in range(65):
        a, b = uninterrupted.ask(), resumed.ask()
        assert a.to_dict() == b.to_dict()
        state = json.loads(json.dumps(resumed.state_dict()))
        resumed = DEHBController(space(), seed=3)
        resumed.load_state_dict(state)
        assert resumed.ask().to_dict() == b.to_dict()
        report(uninterrupted, a)
        report(resumed, b)
        assert resumed.state_dict() == uninterrupted.state_dict()
    assert uninterrupted.bracket >= 6
    assert uninterrupted.best()['job']['fidelity'] == 9


@pytest.mark.parametrize('bad', ['unknown', 'fidelity', 'nan', 'infinite_cost', 'failure', 'negative_cost'])
def test_invalid_report_cannot_consume_or_change_pending_work(bad):
    obj = DEHBController(space())
    trial = obj.ask()
    result = Result(trial.trial_id, 1., 1., trial.fidelity)
    if bad == 'unknown': result.trial_id = 'wrong'
    elif bad == 'fidelity': result.fidelity = 9.
    elif bad == 'nan': result.objective_value = float('nan')
    elif bad == 'infinite_cost': result.cost = float('inf')
    elif bad == 'failure': result.status = 'failed'
    else: result.cost = -1.
    before = obj.state_dict()
    with pytest.raises(ValueError): obj.tell(result)
    assert obj.state_dict() == before


def test_exact_duplicate_is_idempotent_and_conflicting_duplicate_is_refused():
    obj = DEHBController(space())
    result = report(obj, obj.ask())
    obj.ask()
    before = obj.state_dict()
    obj.tell(result)
    assert obj.state_dict() == before
    result.objective_value += 1
    with pytest.raises(ValueError, match='Conflicting'): obj.tell(result)
    assert obj.state_dict() == before


@pytest.mark.parametrize('bad', ['coordinate', 'parent', 'pending', 'space', 'seed'])
def test_checkpoint_changes_are_refused_atomically(bad):
    obj = DEHBController(space())
    report(obj, obj.ask())
    obj.ask()
    before = obj.state_dict()
    state = deepcopy(before)
    if bad == 'coordinate': state['history'][0]['job']['config'][0] += .01
    elif bad == 'parent': state['history'][0]['job']['parent_id'] = 100
    elif bad == 'pending': state['pending']['config_id'] += 1
    elif bad == 'space': state['space']['knobs'][0]['bounds'] = [0., 2.]
    else: state['options']['seed'] += 1
    with pytest.raises(ValueError): obj.load_state_dict(state)
    assert obj.state_dict() == before


def test_native_executor_mixed_and_conditional_space_and_known_quadratic():
    mixed = SearchSpace([Knob('kind', 'categorical', ['a', 'b']),
        Knob('width', 'ordinal', (2, 8)), Knob('lr', 'continuous', (.001, .1), transform='log'),
        Knob('extra', 'continuous', (0., 1.), condition=('kind', 'b'))])
    obj = DEHBController(mixed)
    executor = LocalExecutor()
    def objective(values, fidelity):
        assert (values['kind'] == 'b') == ('extra' in values)
        state = np.array([1., 2.])
        for _ in range(int(fidelity)):
            state -= values['lr'] * np.array([1., 3.]) * state
        expected = (1 - values['lr'])**(2*int(fidelity)) + 4*(1 - 3*values['lr'])**(2*int(fidelity))
        assert abs(float(state @ state) - expected) < 1e-12
        return {'value': float(state @ state), 'cost': fidelity}
    for _ in range(25):
        trial = obj.ask()
        mixed.validate_config(trial.config.values)
        result = executor.execute(trial, objective)
        obj.tell(result)
    executor.shutdown()
    assert obj.best() is not None


@pytest.mark.parametrize('kwargs', [{'eta': 1}, {'max_fidelity': 1}, {'seed': True},
    {'mutation_factor': -1}, {'crossover_probability': 2}, {'eta': float('nan')},
    {'min_fidelity': 0}, {'eta': 100000}])
def test_invalid_controls_refused(kwargs):
    with pytest.raises(ValueError): DEHBController(space(), **kwargs)
