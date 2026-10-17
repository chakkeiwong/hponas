"""Small actual method executions with retained checkpoints and initial tensors."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from unittest.mock import patch

import torch

from hponas.bg_pbt import LocalBGPBT
from hponas.bg_population import BGPopulationExplorer
from hponas.pb2_mix import PB2MixExplorer
from hponas.population import PopulationCheckpoint, make_member
from hponas.population_bandit import TimeVaryingExp3, inclusion_probabilities
from hponas.population_gp import TemporalOptions, TemporalPopulationGP
from hponas.population_search import LocalPBT
from workloads.finite_mdp import FiniteMDP


def task(two_state=False, constant=False):
    if two_state:
        return FiniteMDP([1, 0], [[[0, 1], [0, 0]], [[0, 0], [0, 0]]],
                         [[1, 0], [2, -1]], horizon=2, discount=0.5,
                         rl_weight=1, policy_weight=5, value_weight=0.5)
    return FiniteMDP([1], [[[0], [0]]], [[0, 0]] if constant else [[1, 0]],
                     horizon=1, rl_weight=1, policy_weight=5, value_weight=0)


def pool(dimensions=1):
    return [dict(width=w, depth=d, input_dim=dimensions, output_dim=3,
                 activation='tanh', normalization='none')
            for w, d in [(1, 1), (2, 1), (3, 1), (2, 2)]]


def members(dimensions=1):
    return {str(i): make_member(pool(dimensions)[i], {'learning_rate': 0.1, 'momentum': 0.25}, seed=i+5)
            for i in range(2)}


class SimulatedCrash(BaseException):
    """Interruption outside the recoverable-exception path."""


def execute_slot(spec, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    kind = spec['kind']
    if kind == 'algebra':
        objective = task(two_state=True)
        student = torch.tensor([[0.0, 0.0, 0.25], [0.0, 0.0, -0.5]], dtype=torch.float64, requires_grad=True)
        teacher = torch.tensor([[0.5, -0.5, 1.0], [-0.25, 0.25, -1.0]], dtype=torch.float64)
        rows = []
        for weight in [0.0, 0.5, 1.0]:
            result = objective.components(lambda _: student, lambda _: teacher, weight)
            gradient, = torch.autograd.grad(result['loss'], student)
            rows.append({'weight': weight, 'outputs': student.detach().tolist(), 'teacher_outputs': teacher.tolist(),
                         'components': {k: v.detach().tolist() for k, v in result.items()},
                         'gradient': gradient.tolist()})
        return {'objective': objective.contract, 'rows': rows}
    if kind == 'gp':
        rows = []
        x, y, q, pending = [[0, 0, 0], [1, 0.5, 1]], [0.25, -0.5], [[2, 0.25, 1], [2, 1, 0]], [[2, 0.25, 1]]
        for family in ['pb2_mix', 'bgpbt']:
            gp = TemporalPopulationGP([0], [1], TemporalOptions(family=family, decay=0.75, mixture=0.25, noise=0.5))
            gp.observe(x, y)
            mean, variance = gp.predict(q)
            pending_mean, pending_variance = gp.predict(q, pending=pending)
            rows.append({'options': asdict(gp.options), 'x': x, 'y': y, 'query': q, 'pending': pending,
                         'kernel': gp.kernel(x, q).tolist(), 'mean': mean.tolist(), 'variance': variance.tolist(),
                         'pending_mean': pending_mean.tolist(), 'pending_variance': pending_variance.tolist()})
        return {'rows': rows}
    if kind == 'bandit':
        rows = []
        for weights, batch, gamma in [([8, 1, 1], 2, 0.2), ([1, 2, 3], 1, 0.4), ([1, 3, 7], 3, 0.2)]:
            p, w, capped = inclusion_probabilities(weights, batch, gamma)
            rows.append({'weights': weights, 'batch': batch, 'gamma': gamma,
                         'probabilities': p.tolist(), 'clipped_weights': w.tolist(), 'clipped': capped})
        bandit = TimeVaryingExp3(3, 2, 4, seed=17)
        for index in range(3):
            selection = bandit.ask()
            bandit.tell({arm: [0.0, 0.5, 1.0][(arm+index) % 3] for arm in selection['selected']})
        return {'distributions': rows, 'bandit': bandit.state_dict()}

    objective = task(two_state=kind in {'transfer', 'interruption'},
                     constant=spec.get('method') == 'bgpbt')
    initials = {}
    original_write = PopulationCheckpoint._write

    def retain_initial(store, state):
        original_write(store, state)
        name = str(store.path.relative_to(directory))
        values = initials.setdefault(name, {})
        for ident, event in state['events'].items():
            if ident not in values and event['completed_updates'] == 0 and not event['inflight']:
                values[ident] = deepcopy(event['candidate'])

    with patch.object(PopulationCheckpoint, '_write', retain_initial):
        if kind in {'transfer', 'interruption'}:
            initial = members(2)
            store = PopulationCheckpoint(directory/'population.json', objective, initial, max_updates=3)
            request = dict(event_id='transfer', parent='0', child='1', architecture=pool(2)[3],
                           optimizer=initial['0']['optimizer'], mode='DISTILL', optimizer_policy='RESET',
                           weights=[1, 0.5, 0], seed=11)
            if kind == 'interruption':
                with patch.object(objective, 'components', side_effect=SimulatedCrash):
                    try:
                        store.exploit(**request)
                    except SimulatedCrash:
                        pass
            outcome = store.exploit(**request)
        elif kind == 'population':
            initial = members()
            store = PopulationCheckpoint(directory/'population.json', objective, initial, max_updates=2*spec['rounds'])
            explorer = None
            if spec['method'] == 'pb2_mix':
                explorer = PB2MixExplorer(increment_bound=1, fit_iterations=1, seed=7, horizon=4)
            elif spec['method'] == 'bgpbt':
                explorer = BGPopulationExplorer(increment_bound=1, fit_iterations=1, failure_tolerance=1,
                                                initial_numeric=0.2, minimum_numeric=0.15)
            controller = LocalPBT(directory/'controller.json', store, seed=7, explorer=explorer)
            if spec['recovery']:
                original = controller._write
                def acknowledge(state):
                    original(state)
                    if state['rounds'] and state['rounds'][-1]['status'] == 'exploiting':
                        raise SimulatedCrash()
                with patch.object(controller, '_write', acknowledge):
                    try:
                        controller.run(spec['rounds'], updates_per_round=1)
                    except SimulatedCrash:
                        pass
            outcome = controller.run(spec['rounds'], updates_per_round=1)
        elif kind == 'generations':
            outcome = LocalBGPBT(directory, objective, members(), pool(), increment_bound=1,
                generations=2, max_rounds=1, patience=1, updates_per_round=1,
                distillation_rungs=(1, 2), max_updates=10, seed=7, fit_iterations=1).run()
        else:
            raise ValueError('Unknown population slot')
    return {'objective': objective.contract, 'initial_candidates': initials, 'outcome': outcome,
            'files': {str(path.relative_to(directory)): json.loads(path.read_text())
                      for path in sorted(directory.rglob('*.json'))}}
