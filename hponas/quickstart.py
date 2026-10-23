"""Installed, caller-owned model examples with exact finite references.

Run ``python -m hponas.quickstart --model hinge --output /tmp/hinge-study``.
Only base dependencies are needed. These deterministic examples demonstrate
fitting, coordinate search and protected evaluation, not application efficacy.
The objective classes deliberately have no workload/fixture base class.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np

from hponas import (
    EvaluationFold, EvaluationObjective, Knob, LocalExecutor, SearchSpace,
    SobolSearcher, Study, StudyBudget, StudyDeclaration,
)
from hponas.store import Store

WORK_UNIT = 'row_visits_plus_fit_updates'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _publish_once(path, text):
    """Publish complete bytes; identical retries may not replace prior output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Publish only complete, fsynced bytes. A killed writer may leave a private
    # temporary file, but can never leave a truncated public model artifact.
    descriptor, temporary = tempfile.mkstemp(prefix='.model-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_text() != text:
                raise ValueError('Existing caller artifact differs from this evaluation')
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
    return str(path)


def _save_model(path, payload):
    """A retry may reproduce an artifact, but cannot silently replace it."""
    encoded = _canonical(payload)
    document = {'schema': 'hponas-caller-model-v1', 'payload': payload,
                'sha256': hashlib.sha256(encoded.encode()).hexdigest()}
    return _publish_once(path, _canonical(document) + '\n')


def load_model(path):
    """Verify retained bytes; the containing directory remains caller-trusted."""
    saved = json.loads(Path(path).read_text())
    if (not isinstance(saved, dict) or set(saved) != {'schema', 'payload', 'sha256'}
            or saved['schema'] != 'hponas-caller-model-v1'):
        raise ValueError('Unsupported caller model artifact schema')
    if hashlib.sha256(_canonical(saved['payload']).encode()).hexdigest() != saved['sha256']:
        raise ValueError('Caller model artifact digest differs')
    return saved['payload']


def _declaration(name, training, tuning, final):
    return StudyDeclaration(
        objective_id=name + ':loss:v1', model_id=name + ':caller-model:v1',
        data_id=name + ':synthetic-rows:v1', protocol_id='caller-example:fit-per-role:v1',
        objectives=(EvaluationObjective('loss', 'min', 'finite_model_loss'),),
        tuning_folds=(EvaluationFold('validation', tuple(training), tuple(tuning)),),
        final_folds=(EvaluationFold('sealed', tuple(training) + tuple(tuning), tuple(final)),),
        tuning_seeds=(0, 1), final_seeds=(1000, 1001))


def _context(model, evaluation):
    if evaluation.declaration_identity != model.declaration.identity:
        raise ValueError('Caller model evaluation declaration differs')
    folds = {'tuning': model.declaration.tuning_folds, 'final': model.declaration.final_folds}
    if evaluation.role not in folds or evaluation.fold not in folds[evaluation.role]:
        raise ValueError('Caller model evaluation role or fold differs')
    return evaluation.fold


class HingeRegressor:
    """Fit a fixed-hidden-feature ReLU network's readout by ridge regression.

    Width selects one or two fixed hidden features at centers 0 and 1. Hidden
    weights are not trained; output coefficients are fitted from training rows.
    ``1 + 2 relu(x) - relu(x-1)`` is exactly representable at width two/ridge zero.
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        self.records = {}
        roles = {'train': (-2., -1., 0., 1., 2.),
                 'validation': (-.5, .5, 1.5), 'final': (-1.5, .25, 1.75)}
        ids = {}
        for role, points in roles.items():
            ids[role] = []
            for index, x in enumerate(points):
                identity = role + '-' + str(index)
                self.records[identity] = (x, 1. + 2. * max(x, 0.) - max(x - 1., 0.))
                ids[role].append(identity)
        self.declaration = _declaration('fixed-relu-readout', ids['train'], ids['validation'], ids['final'])
        self.space = SearchSpace([Knob('width', 'ordinal', (1, 2)), Knob('ridge', 'ordinal', (0, 1))])
        self.reference = {'loss': 0., 'configuration': {'width': 2, 'ridge': 0},
                          'coefficients': [1., 2., -1.],
                          'basis': '1 + 2 relu(x) - relu(x-1)'}

    @staticmethod
    def fit(config, rows):
        if (set(config) != {'width', 'ridge'} or type(config['width']) is not int
                or config['width'] not in (1, 2) or type(config['ridge']) is not int
                or config['ridge'] not in (0, 1)):
            raise ValueError('Unsupported readout configuration')
        x = np.asarray([row[0] for row in rows])
        target = np.asarray([row[1] for row in rows])
        design = np.column_stack([np.ones(len(rows))] +
                                  [np.maximum(x - center, 0.) for center in range(config['width'])])
        penalty = np.diag([0.] + [float(config['ridge'])] * config['width'])
        coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
        return {'kind': 'fixed_relu_readout', 'centers': list(range(config['width'])),
                'coefficients': coefficients.tolist()}

    @staticmethod
    def predict(model, points):
        return [float(model['coefficients'][0] + sum(c * max(x - center, 0.)
                     for c, center in zip(model['coefficients'][1:], model['centers']))) for x in points]

    def __call__(self, config, seed, evaluation, trial_id):
        fold = _context(self, evaluation)
        training = [self.records[i] for i in fold.train_ids]
        scoring = [self.records[i] for i in fold.score_ids]
        fitted = self.fit(config, training)
        predictions = self.predict(fitted, [row[0] for row in scoring])
        loss = sum((prediction - row[1]) ** 2 for prediction, row in zip(predictions, scoring)) / len(scoring)
        work = len(training) + len(scoring) + 1
        payload = {'model': fitted, 'config': dict(config), 'seed': seed, 'role': evaluation.role,
                   'declaration_identity': self.declaration.identity, 'train_ids': list(fold.train_ids),
                   'score_ids': list(fold.score_ids), 'predictions': predictions, 'loss': loss,
                   'work': work, 'work_unit': WORK_UNIT}
        path = _save_model(self.directory / 'models' / (trial_id + '.json'), payload)
        return {'value': loss, 'artifacts': {'model': path},
                'metadata': {'resource': {'work': work, 'unit': WORK_UNIT}}}


class QuadraticAllocator:
    """Fit two simplex weights with projected gradient updates.

    The second asset has zero return. The first asset's training scenarios have
    mean 3 and population variance 4. Minimize variance/2 minus mean, so the
    exact weight is 3/4 and the exact objective is -9/8. This finite synthetic
    example is not an empirical risk or investment-performance claim.
    """

    def __init__(self, directory):
        self.directory = Path(directory)
        self.records = {role + '-' + str(i): value for role in ('train', 'validation', 'final')
                        for i, value in enumerate((1., 5., 1., 5.))}
        ids = {role: [role + '-' + str(i) for i in range(4)] for role in ('train', 'validation', 'final')}
        self.declaration = _declaration('quadratic-allocation', ids['train'], ids['validation'], ids['final'])
        self.space = SearchSpace([Knob('step_eighths', 'ordinal', (1, 2)),
                                  Knob('iterations', 'ordinal', (1, 2))])
        self.reference = {'loss': -9. / 8., 'weights': [.75, .25],
                          'configurations': [{'step_eighths': 2, 'iterations': k} for k in (1, 2)],
                          'derivation': 'J(w)=2w^2-3w; Jprime(w)=4w-3; w in [0,1]'}

    @staticmethod
    def fit(config, rows):
        if (set(config) != {'step_eighths', 'iterations'} or any(type(config[k]) is not int
                or config[k] not in (1, 2) for k in config)):
            raise ValueError('Unsupported allocation configuration')
        mean = sum(rows) / len(rows)
        variance = sum((value - mean) ** 2 for value in rows) / len(rows)
        weight = 0.
        trace = [weight]
        for _ in range(config['iterations']):
            weight = min(1., max(0., weight - config['step_eighths'] / 8. * (variance * weight - mean)))
            trace.append(weight)
        return {'kind': 'quadratic_simplex', 'weights': [weight, 1. - weight],
                'training_mean': mean, 'training_variance': variance, 'updates': trace}

    @staticmethod
    def predict(model, scenarios):
        return [model['weights'][0] * value for value in scenarios]

    def __call__(self, config, seed, evaluation, trial_id):
        fold = _context(self, evaluation)
        training = [self.records[i] for i in fold.train_ids]
        scoring = [self.records[i] for i in fold.score_ids]
        fitted = self.fit(config, training)
        predictions = self.predict(fitted, scoring)
        mean = sum(predictions) / len(predictions)
        loss = .5 * sum((value - mean) ** 2 for value in predictions) / len(predictions) - mean
        work = len(training) + len(scoring) + config['iterations']
        payload = {'model': fitted, 'config': dict(config), 'seed': seed, 'role': evaluation.role,
                   'declaration_identity': self.declaration.identity, 'train_ids': list(fold.train_ids),
                   'score_ids': list(fold.score_ids), 'predictions': predictions, 'loss': loss,
                   'work': work, 'work_unit': WORK_UNIT}
        path = _save_model(self.directory / 'models' / (trial_id + '.json'), payload)
        return {'value': loss, 'artifacts': {'model': path},
                'metadata': {'resource': {'work': work, 'unit': WORK_UNIT}}}


MODELS = {'hinge': HingeRegressor, 'allocation': QuadraticAllocator}


def make_study(name, directory, store):
    """Wire a plain caller model to the public declared evaluation API."""
    if name not in MODELS:
        raise ValueError('Choose hinge or allocation')
    directory = Path(directory)
    model = MODELS[name](directory)
    # Four unscrambled points cover both binary ordinal coordinates exactly.
    # Repetitions are deterministic; seeds retain their declared role identities.
    return Study(SobolSearcher(model.space, seed=7, scramble=False), LocalExecutor(), model,
                 budget=4, maximize=False, study_name='caller_' + name,
                 checkpoint_dir=directory, store=store, declaration=model.declaration,
                 architecture_coordinates=('width',) if name == 'hinge' else (),
                 resource_budget=StudyBudget(configurations=4, work_unit=WORK_UNIT,
                     tuning_work=160, final_work=64, max_work_per_call=16, full_run_work=16))


def run(name, directory, *, resume=False):
    """Run or explicitly resume; return actual results and finite reference regret."""
    if name not in MODELS:
        raise ValueError('Choose hinge or allocation')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / 'study.sqlite'
    if database.exists() and not resume:
        raise ValueError('Existing study requires explicit resume')
    if resume and not database.is_file():
        raise ValueError('No existing study to resume')
    if not database.exists() and any(directory.iterdir()):
        raise ValueError('A new study requires an empty directory')
    with closing(Store(database)) as store:
        study = make_study(name, directory, store)
        if resume:
            study.load_checkpoint()
        result = study.run()
        reference = dict(study.objective_fn.reference)
        reference['search_regret'] = result.best_value - reference['loss']
        report = store.read_report(study.study_name)
        _publish_once(directory / 'report.json', json.dumps(report, indent=2, allow_nan=False) + '\n')
        return {'model': name, 'result': result.to_dict(), 'report': report, 'reference': reference,
                'limits': {'deterministic_synthetic_examples': True, 'stochastic_precision_claim': False,
                           'empirical_bank_usefulness_established': False,
                           'posterior_convergence_established': False}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=tuple(MODELS), default='hinge')
    parser.add_argument('--output', type=Path, help='Empty run directory, or existing directory with --resume')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    if args.resume and args.output is None:
        parser.error('--resume requires --output')
    directory = args.output or Path(tempfile.mkdtemp(prefix='hponas-caller-'))
    outcome = run(args.model, directory, resume=args.resume)
    print(json.dumps({'model': outcome['model'], 'directory': str(directory.resolve()),
                      'selection': outcome['result']['best_config'], 'reference': outcome['reference'],
                      'evaluation': outcome['result']['evaluation']['outcome'],
                      'limits': outcome['limits']}, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
