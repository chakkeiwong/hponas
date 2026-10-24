"""DOC-01 finite response HPO and trained equilibrium coordinate NAS.

The design is frozen in design.json. No sibling-project imports or services.
Run through program_operations/doc_ops.py for the reviewed execution envelope.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import itertools
import json
import math
from pathlib import Path
import time

import numpy as np
from scipy.special import expit
import torch

from hponas import (EvaluationContext, EvaluationFold, EvaluationObjective,
                    Knob, LocalExecutor, RandomSearcher, SearchSpace,
                    SobolSearcher, GPSearcher, Study, StudyBudget, StudyDeclaration)
from hponas.searchers_tpe import TPESearcher
from hponas.store import Store

DESIGN = json.loads(Path(__file__).with_name('design.json').read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def publish(path, payload):
    """Exclusive complete artifact; identical retries are permitted."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical(payload) + '\n'
    if path.exists():
        if path.is_symlink() or path.read_text() != content:
            raise ValueError('Conflicting retained output: ' + str(path))
    else:
        with path.open('x') as output:
            output.write(content)
    return str(path)


def load_artifact(path):
    value = json.loads(Path(path).read_text())
    if set(value) != {'payload', 'sha256'} or digest(value['payload']) != value['sha256']:
        raise ValueError('Artifact digest differs')
    return value['payload']


def logistic_fit(config, rows):
    cfg = DESIGN['response']
    x = np.column_stack((np.ones(len(rows)), np.asarray(rows)[:, :2]))
    y = np.asarray(rows)[:, 2]
    alpha, ratio = config['alpha'], config['l1_ratio']
    l1, l2 = alpha * ratio, alpha * (1 - ratio)
    step = 1 / (np.linalg.norm(x, 2) ** 2 / (4 * len(x)) + l2)
    w = np.zeros(3)
    for iteration in range(1, cfg['max_iterations'] + 1):
        grad = x.T @ (expit(x @ w) - y) / len(x) + l2 * np.r_[0., w[1:]]
        new = w - step * grad
        new[1:] = np.sign(new[1:]) * np.maximum(abs(new[1:]) - step * l1, 0)
        w = new
        grad = x.T @ (expit(x @ w) - y) / len(x) + l2 * np.r_[0., w[1:]]
        residual = np.where(w[1:] != 0, abs(grad[1:] + l1 * np.sign(w[1:])),
                            np.maximum(abs(grad[1:]) - l1, 0))
        kkt = float(max(abs(grad[0]), max(residual)))
        if kkt <= cfg['kkt_tolerance']:
            break
    else:
        raise ValueError('Logistic KKT tolerance not reached')
    return {'weights': w.tolist(), 'iterations': iteration, 'kkt': kkt}


def logistic_score(model, rows):
    rows = np.asarray(rows)
    logits = np.column_stack((np.ones(len(rows)), rows[:, :2])) @ np.asarray(model['weights'])
    return float(np.mean(np.logaddexp(0, logits) - rows[:, 2] * logits)), {'probabilities': expit(logits).tolist()}


class Policy(torch.nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        layers = []
        size = 2
        for _ in range(depth):
            layers.extend([torch.nn.Linear(size, width, dtype=torch.float64), torch.nn.Tanh()])
            size = width
        layers.append(torch.nn.Linear(size, 1, dtype=torch.float64))
        self.net = torch.nn.Sequential(*layers)

    def forward(self, states):
        return states[:, 0] * self.net(states).squeeze(-1)


def residual(model, states):
    cfg = DESIGN['equilibrium']
    future = torch.stack((cfg['rho'] * states[:, 0], states[:, 1]), dim=1)
    return model(states) - cfg['beta'] * model(future) - states[:, 1] * states[:, 0]


def neural_fit(config, rows, seed):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = Policy(config['width'], config['depth'])
        states = torch.tensor(rows, dtype=torch.float64)
        optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
        for _ in range(DESIGN['equilibrium']['epochs']):
            optimizer.zero_grad()
            loss = residual(model, states).square().mean()
            loss.backward()
            optimizer.step()
        layers = [{'weight': layer.weight.detach().tolist(), 'bias': layer.bias.detach().tolist()}
                  for layer in model.net if isinstance(layer, torch.nn.Linear)]
    return {'layers': layers, 'parameters': sum(p.numel() for p in model.parameters()),
            'epochs': DESIGN['equilibrium']['epochs']}


def neural_score(saved, rows):
    width, depth = len(saved['layers'][0]['bias']), len(saved['layers']) - 1
    model = Policy(width, depth)
    with torch.no_grad():
        for layer, source in zip((x for x in model.net if isinstance(x, torch.nn.Linear)), saved['layers']):
            layer.weight.copy_(torch.tensor(source['weight'], dtype=torch.float64))
            layer.bias.copy_(torch.tensor(source['bias'], dtype=torch.float64))
    states = torch.tensor(rows, dtype=torch.float64, requires_grad=True)
    y = model(states)
    jac = torch.autograd.grad(y.sum(), states)[0]
    cfg = DESIGN['equilibrium']
    x, a = states[:, 0], states[:, 1]
    ref = a * x / (1 - cfg['beta'] * cfg['rho'])
    ref_jac = torch.stack((a, x), dim=1) / (1 - cfg['beta'] * cfg['rho'])
    errors = (jac - ref_jac).detach().abs().max(dim=0).values
    res = residual(model, states).detach()
    y = y.detach()
    return float(res.square().mean()), {
        'y': y.tolist(), 'z': (cfg['lambda'] * y + x.detach()).tolist(),
        'jacobian': jac.detach().tolist(), 'residual': res.tolist(),
        'policy_max_error': float((y - ref.detach()).abs().max()),
        'state_derivative_max_error': float(errors[0]),
        'parameter_derivative_max_error': float(errors[1]),
        'boundary_error': 0., 'structural_error': 0.}


class Objective:
    def __init__(self, name, replicate, directory):
        self.name, self.replicate, self.directory = name, replicate, Path(directory)
        cfg = DESIGN[name]
        rng = np.random.default_rng(replicate)
        self.records, ids = {}, {}
        for role, n in zip(('train', 'validation', 'final'), cfg['rows']):
            if name == 'response':
                x = rng.normal(size=(n, 2))
                y = rng.binomial(1, expit(-.7 + 1.1 * x[:, 0] - .6 * x[:, 1]))
                rows = np.column_stack((x, y)).tolist()
            else:
                rows = np.column_stack((rng.uniform(*cfg['state_range'], n),
                                        rng.uniform(*cfg['parameter_range'], n))).tolist()
            ids[role] = []
            for i, row in enumerate(rows):
                key = role + '_' + str(i)
                ids[role].append(key)
                self.records[key] = row
        self.axes = ('alpha', 'l1_ratio') if name == 'response' else ('width', 'depth', 'learning_rate')
        self.space = SearchSpace([Knob(axis, 'ordinal', (0, len(cfg[axis]) - 1)) for axis in self.axes])
        self.declaration = StudyDeclaration(
            objective_id=name + ':validation-loss:v1', model_id=name + ':doc01-fit:v1',
            data_id=name + ':' + digest(self.records), protocol_id='doc01:' + digest(DESIGN),
            objectives=(EvaluationObjective('loss', 'min', 'NLL' if name == 'response' else 'squared_equilibrium_residual'),),
            tuning_folds=(EvaluationFold('validation', tuple(ids['train']), tuple(ids['validation'])),),
            final_folds=(EvaluationFold('final', tuple(ids['train'] + ids['validation']), tuple(ids['final'])),),
            tuning_seeds=tuple(DESIGN['tuning_seeds']), final_seeds=tuple(DESIGN['final_seeds']))
        self.calls = 0

    @property
    def configurations(self):
        return [dict(zip(self.axes, values)) for values in itertools.product(
            *(range(len(DESIGN[self.name][a])) for a in self.axes))]

    def physical(self, config):
        if set(config) != set(self.axes) or any(type(config[a]) is not int or not 0 <= config[a] < len(DESIGN[self.name][a]) for a in self.axes):
            raise ValueError('Invalid finite configuration')
        return {a: DESIGN[self.name][a][config[a]] for a in self.axes}

    @property
    def work_unit(self):
        return 'logistic_row_gradient_visits' if self.name == 'response' else 'neural_parameter_row_proxy'

    @property
    def max_work(self):
        cfg = DESIGN[self.name]
        train = sum(cfg['rows'][:2]); score = max(cfg['rows'][1:])
        if self.name == 'response':
            return 2 * cfg['max_iterations'] * train + score
        return 2 * (cfg['epochs'] * train + score) * 105

    def __call__(self, config, seed, evaluation, trial_id):
        self.calls += 1
        if evaluation.declaration_identity != self.declaration.identity:
            raise ValueError('Declaration differs')
        expected = self.declaration.tuning_folds if evaluation.role == 'tuning' else self.declaration.final_folds if evaluation.role == 'final' else ()
        if evaluation.fold not in expected:
            raise ValueError('Role or fold differs')
        fold = evaluation.fold
        train, score = ([self.records[k] for k in keys] for keys in (fold.train_ids, fold.score_ids))
        physical = self.physical(config)
        if self.name == 'response':
            model = logistic_fit(physical, train)
            loss, metrics = logistic_score(model, score)
            work = 2 * model['iterations'] * len(train) + len(score)
        else:
            model = neural_fit(physical, train, self.replicate * 10000 + seed)
            loss, metrics = neural_score(model, score)
            work = 2 * (model['epochs'] * len(train) + len(score)) * model['parameters']
        if not math.isfinite(loss):
            raise ValueError('Nonfinite fit')
        payload = {'name': self.name, 'replicate': self.replicate, 'config': config,
                   'physical': physical, 'seed': seed, 'role': evaluation.role,
                   'train_ids': list(fold.train_ids), 'score_ids': list(fold.score_ids),
                   'declaration_identity': self.declaration.identity,
                   'model': model, 'loss': loss, 'metrics': metrics, 'work': work, 'work_unit': self.work_unit}
        path = publish(self.directory / 'models' / (trial_id + '.json'), {'payload': payload, 'sha256': digest(payload)})
        return {'value': loss, 'artifacts': {'model': path},
                'metadata': {'resource': {'work': work, 'unit': self.work_unit}}}


def searcher(method, objective, replicate):
    if method == 'random':
        return RandomSearcher(objective.space, seed=replicate)
    if method == 'sobol':
        return SobolSearcher(objective.space, seed=replicate, scramble=True)
    if method == 'gp':
        return GPSearcher(objective.space, seed=replicate, initial_random_samples=4, num_restarts=2, maximize=False)
    if method == 'tpe':
        return TPESearcher(objective.space, seed=replicate)
    raise ValueError('Unknown method')


def make_study(name, replicate, method, directory, store):
    objective = Objective(name, replicate, directory)
    budget = DESIGN['search_budget']
    return Study(searcher(method, objective, replicate), LocalExecutor(), objective,
                 budget=budget, maximize=False, study_name=name + '_' + method + '_' + str(replicate),
                 checkpoint_dir=directory, store=store, declaration=objective.declaration,
                 architecture_coordinates=('width', 'depth') if name == 'equilibrium' else (),
                 resource_budget=StudyBudget(configurations=budget, work_unit=objective.work_unit,
                     tuning_work=2 * budget * objective.max_work, final_work=2 * objective.max_work,
                     max_work_per_call=objective.max_work))


def run(name, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    publish(destination / 'design.json', DESIGN)
    outcomes = []
    start = time.perf_counter()
    for replicate in DESIGN['replicates']:
        reference = Objective(name, replicate, destination / str(replicate) / 'grid')
        publish(destination / str(replicate) / 'data.json', reference.records)
        publish(destination / str(replicate) / 'declaration.json', reference.declaration.contract)
        begin = time.perf_counter(); table = []
        for index, config in enumerate(reference.configurations):
            values = []
            for seed in DESIGN['tuning_seeds']:
                context = EvaluationContext('tuning', reference.declaration.tuning_folds[0], reference.declaration.identity)
                values.append(reference(config, seed, context, f'grid_{index}_{seed}')['value'])
            table.append({'config': config, 'physical': reference.physical(config), 'losses': values, 'mean': float(np.mean(values))})
        oracle = min(row['mean'] for row in table)
        grid_seconds = time.perf_counter() - begin
        publish(destination / str(replicate) / 'grid.json', {'rows': table, 'minimum': oracle, 'seconds': grid_seconds})
        for method in DESIGN['methods']:
            directory = destination / str(replicate) / method
            directory.mkdir()
            with closing(Store(directory / 'study.sqlite')) as store:
                study = make_study(name, replicate, method, directory, store)
                begin = time.perf_counter()
                result = study.run()
                seconds = time.perf_counter() - begin
                report = store.read_report(study.study_name)
                publish(directory / 'report.json', report)
                publish(directory / 'result.json', result.to_dict())
                raw = [load_artifact(p) for p in sorted((directory / 'models').glob('*.json'))]
                final = [row for row in raw if row['role'] == 'final']
                observed = [study.trials[tid].config.values for tid in study.results]
                resumed = make_study(name, replicate, method, directory, store)
                resumed.load_checkpoint()
                before = canonical(store.read_report(study.study_name))
                resumed_result = resumed.run()
                unchanged = before == canonical(store.read_report(study.study_name))
                if resumed.objective_fn.calls or not unchanged or resumed_result.best_value != result.best_value:
                    raise AssertionError('Completed resume changed objective/report/selection')
                summary = {'replicate': replicate, 'method': method, 'best_config': result.best_config.values,
                           'physical': reference.physical(result.best_config.values), 'best_tuning': result.best_value,
                           'reference_minimum': oracle, 'regret': result.best_value - oracle,
                           'final_mean': float(np.mean([row['loss'] for row in final])),
                           'proposals': len(observed), 'unique': len({canonical(x) for x in observed}),
                           'failures': sum(r.status != 'completed' for r in study.results.values()),
                           'seconds': seconds, 'grid_seconds': grid_seconds,
                           'final_metrics': [row['metrics'] for row in final],
                           'resource': study.resource_report(), 'resume_unchanged': unchanged}
                if name == 'response':
                    test = np.asarray([v for k,v in reference.records.items() if k.startswith('final_')])
                    logits = -.7 + 1.1 * test[:, 0] - .6 * test[:, 1]
                    summary['known_dgp_final_nll'] = float(np.mean(np.logaddexp(0, logits) - test[:,2]*logits))
                publish(directory / 'summary.json', summary)
                outcomes.append(summary)
                print(json.dumps({k: summary[k] for k in ('replicate','method','regret','final_mean','seconds','failures')}), flush=True)
    result = {'name': name, 'design_sha256': digest(DESIGN), 'rows': outcomes, 'elapsed_seconds': time.perf_counter() - start,
              'claim': 'Descriptive finite demonstration only; exhaustive oracle and independent checks are separately retained'}
    publish(destination / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('name', choices=('response', 'equilibrium'))
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    run(args.name, args.destination)
