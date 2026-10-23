"""Two independent tiny trainable adapters; no fixture-controller inheritance.

These caller-owned datasets and optimizers demonstrate the local interface.
They do not establish effectiveness on a banking deployment.
"""
from copy import deepcopy
import hashlib
import json
import math


def _identity(kind, data):
    return kind + ':' + hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


class LinearSGDAdapter:
    """One-parameter least squares, actual momentum SGD, mean squared error."""
    work_unit = 'linear_momentum_gradient_update'

    def __init__(self, data):
        self.data = deepcopy(data)
        if not data or any(len(row) != 2 or not all(_finite(v) for v in row) for row in data.values()):
            raise ValueError('Finite (x,y) data required')
        self.identity = _identity('linear-sgd-v1', self.data)

    def _config(self, config):
        if (set(config) != {'model', 'lr', 'momentum'} or config['model'] != 'linear'
                or not _finite(config['lr']) or not 0 < config['lr'] <= 1
                or not _finite(config['momentum']) or not 0 <= config['momentum'] < 1):
            raise ValueError('Incompatible linear/SGD configuration')

    def initialize(self, config, *, seed, evaluation):
        self._config(config)
        return dict(model='linear-sgd-v1', w=0., velocity=0., updates=0)

    def checkpoint(self, runtime):
        return deepcopy(runtime)

    def restore(self, checkpoint, config, *, seed, evaluation):
        self._config(config)
        if (set(checkpoint) != {'model', 'w', 'velocity', 'updates'}
                or checkpoint['model'] != 'linear-sgd-v1'
                or not all(_finite(checkpoint[k]) for k in ('w', 'velocity'))
                or type(checkpoint['updates']) is not int or checkpoint['updates'] < 0):
            raise ValueError('Incompatible linear checkpoint')
        return deepcopy(checkpoint)

    def train(self, runtime, config, *, evaluation):
        self._config(config)
        rows = [self.data[key] for key in evaluation.fold.train_ids]
        gradient = math.fsum(2 * x * (runtime['w'] * x - y) for x, y in rows) / len(rows)
        runtime['velocity'] = config['momentum'] * runtime['velocity'] + gradient
        runtime['w'] -= config['lr'] * runtime['velocity']
        runtime['updates'] += 1

    def evaluate(self, runtime, *, evaluation):
        rows = [self.data[key] for key in evaluation.fold.score_ids]
        return math.fsum((runtime['w'] * x - y)**2 for x, y in rows) / len(rows)

    def transfer(self, checkpoint, source_config, target_config, *, optimizer_policy, seed, evaluation):
        self._config(source_config)
        self._config(target_config)
        runtime = self.restore(checkpoint, source_config, seed=seed, evaluation=evaluation)
        if optimizer_policy == 'RESET':
            runtime['velocity'] = 0.
        elif optimizer_policy != 'COPY':
            raise ValueError('Explicit optimizer COPY/RESET required')
        return runtime


class LogisticAdamAdapter:
    """Binary logistic regression with intercept and bias-corrected Adam."""
    work_unit = 'logistic_adam_gradient_update'

    def __init__(self, data):
        self.data = deepcopy(data)
        if (not data or any(len(row) != 2 or not _finite(row[0]) or row[1] not in (0, 1)
                            for row in data.values())):
            raise ValueError('Finite binary-labelled (x,y) data required')
        self.identity = _identity('logistic-adam-v1', self.data)

    def _config(self, config):
        if (set(config) != {'model', 'lr', 'beta1', 'beta2'} or config['model'] != 'logistic'
                or not _finite(config['lr']) or not 0 < config['lr'] <= 1
                or any(not _finite(config[k]) or not 0 <= config[k] < 1 for k in ('beta1', 'beta2'))):
            raise ValueError('Incompatible logistic/Adam configuration')

    def initialize(self, config, *, seed, evaluation):
        self._config(config)
        return dict(model='logistic-adam-v1', w=[0., 0.], m=[0., 0.], v=[0., 0.], t=0)

    def checkpoint(self, runtime):
        return deepcopy(runtime)

    def restore(self, checkpoint, config, *, seed, evaluation):
        self._config(config)
        if (set(checkpoint) != {'model', 'w', 'm', 'v', 't'}
                or checkpoint['model'] != 'logistic-adam-v1'
                or any(not isinstance(checkpoint[k], list) or len(checkpoint[k]) != 2
                       or not all(_finite(v) for v in checkpoint[k]) for k in ('w', 'm', 'v'))
                or any(v < 0 for v in checkpoint['v'])
                or type(checkpoint['t']) is not int or checkpoint['t'] < 0):
            raise ValueError('Incompatible Adam checkpoint')
        return deepcopy(checkpoint)

    def train(self, runtime, config, *, evaluation):
        self._config(config)
        rows = [self.data[key] for key in evaluation.fold.train_ids]
        gradients = [[], []]
        for x, y in rows:
            z = runtime['w'][0] * x + runtime['w'][1]
            p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            gradients[0].append((p - y) * x)
            gradients[1].append(p - y)
        runtime['t'] += 1
        t, b1, b2 = runtime['t'], config['beta1'], config['beta2']
        for i in range(2):
            g = math.fsum(gradients[i]) / len(rows)
            runtime['m'][i] = b1 * runtime['m'][i] + (1 - b1) * g
            runtime['v'][i] = b2 * runtime['v'][i] + (1 - b2) * g*g
            runtime['w'][i] -= config['lr'] * (runtime['m'][i] / (1 - b1**t)) / (
                math.sqrt(runtime['v'][i] / (1 - b2**t)) + 1e-8)

    def evaluate(self, runtime, *, evaluation):
        losses = []
        for key in evaluation.fold.score_ids:
            x, y = self.data[key]
            z = runtime['w'][0] * x + runtime['w'][1]
            losses.append(max(z, 0) + math.log1p(math.exp(-abs(z))) - y*z)
        return math.fsum(losses) / len(losses)

    def transfer(self, checkpoint, source_config, target_config, *, optimizer_policy, seed, evaluation):
        self._config(source_config)
        self._config(target_config)
        if optimizer_policy == 'COPY' and any(source_config[k] != target_config[k] for k in ('beta1', 'beta2')):
            raise ValueError('Changed Adam decay requires optimizer RESET')
        runtime = self.restore(checkpoint, source_config, seed=seed, evaluation=evaluation)
        if optimizer_policy == 'RESET':
            runtime.update(m=[0., 0.], v=[0., 0.], t=0)
        elif optimizer_policy != 'COPY':
            raise ValueError('Explicit optimizer COPY/RESET required')
        return runtime


def main():
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from hponas import StudyDeclaration, EvaluationFold, EvaluationObjective
    from hponas.population_adapter import AdapterPopulation

    declaration = StudyDeclaration('squared-error', 'linear', 'synthetic-linear', 'pbt-demo-v1',
        (EvaluationObjective('mse', 'min', 'squared_units'),),
        (EvaluationFold('tuning', ('train1', 'train2'), ('validation',)),),
        (EvaluationFold('final', ('train1', 'train2'), ('heldout',)),))
    data = {'train1': (1., 2.), 'train2': (2., 4.), 'validation': (1., 2.), 'heldout': (3., 6.)}
    config = lambda lr: dict(model='linear', lr=lr, momentum=0.)
    with TemporaryDirectory() as directory:
        result = AdapterPopulation(Path(directory)/'population.json', LinearSGDAdapter(data),
            declaration, {'a': config(.05), 'b': config(.1)}, exploration_configs=[config(.2)],
            max_updates=12).run()
        print(json.dumps({k: result[k] for k in ('status', 'selection', 'final_mean', 'accounting')}, indent=2))


if __name__ == '__main__':
    main()
