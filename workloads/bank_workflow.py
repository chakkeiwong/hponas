"""Small caller-owned bank adapters over the framework-neutral public API.

These synthetic profiles demonstrate contracts, not empirical bank performance.
Objectives receive only the declared fold's rows; arbitrary caller code remains
responsible for respecting information boundaries outside this adapter.
"""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Callable

from hponas import (EvaluationFold, Knob, LocalExecutor, RandomSearcher,
                    SearchSpace, Study, StudyBudget, StudyDeclaration,
                    MultiObjectiveStudy, MultiObjectiveRandomSearcher, IncompleteStudyError)
from hponas.store import Store

WORK_UNIT = 'fit_and_score_rows'
DETERMINISM = 'Finite synthetic rows and deterministic fitting; seed repetitions add no information.'


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


def identity(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_artifact(path, payload):
    """Atomically publish once; permit identical deterministic crash recovery."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical({'schema': 'bank_model_artifact_v1',
                         'payload': payload, 'sha256': identity(payload)})+'\n'
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.model-', mode='w') as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        try:
            os.link(handle.name, path)
        except FileExistsError:
            if path.read_text() != encoded:
                raise ValueError('Artifact identity/content differs from committed model')
    return str(path)


def load_artifact(path, *, profile=None, config=None):
    record = json.loads(Path(path).read_text())
    if (set(record) != {'schema','payload','sha256'}
            or record['schema'] != 'bank_model_artifact_v1'
            or identity(record['payload']) != record['sha256']):
        raise ValueError('Artifact schema or content digest differs')
    value = record['payload']
    if profile is not None and value['declaration_identity'] != profile.declaration.identity:
        raise ValueError('Artifact profile/declaration identity differs')
    if config is not None and value['config'] != dict(config):
        raise ValueError('Artifact configuration or architecture differs')
    return value


def validate_rows(records, fold):
    if not isinstance(fold, EvaluationFold):
        raise ValueError('Typed evaluation fold required')
    rows = []
    for role, ids in (('train',fold.train_ids),('score',fold.score_ids)):
        try: selected = [deepcopy(records[i]) for i in ids]
        except KeyError as exc: raise ValueError('Declared row is missing') from exc
        if any(r.get('id') != ident for r,ident in zip(selected,ids)):
            raise ValueError('Row identity differs')
        if fold.mode == 'grouped':
            groups = fold.train_groups if role == 'train' else fold.score_groups
            if {r.get('group') for r in selected} != set(groups):
                raise ValueError('Row entity differs from declared group')
        if fold.mode == 'temporal':
            for row in selected:
                t, available = row.get('time'), row.get('feature_time')
                if (type(t) not in (int,float) or type(available) not in (int,float)
                        or not math.isfinite(t) or not math.isfinite(available) or available >= t):
                    raise ValueError('Feature is unavailable at decision time')
                if role == 'train' and t > fold.train_until:
                    raise ValueError('Training information exceeds declared time')
                if role == 'score' and not fold.score_from <= t <= fold.score_until:
                    raise ValueError('Scoring information differs from declared time')
        rows.append(selected)
    return tuple(rows)


@dataclass(frozen=True)
class BankProfile:
    name: str
    choices: dict
    declaration: StudyDeclaration
    records: dict
    evaluator: Callable
    vector_contract: dict | None = None
    work_unit: str = WORK_UNIT
    max_work_per_call: float | None = None

    def __post_init__(self):
        if not re.fullmatch(r'[a-z][a-z0-9_]*', self.name):
            raise ValueError('Simple profile name required')
        object.__setattr__(self, 'records', deepcopy(self.records))
        object.__setattr__(self, 'choices', deepcopy(self.choices))
        object.__setattr__(self, '_records_identity', identity(self.records))
        object.__setattr__(self, '_choices_identity', identity(self.choices))
        object.__setattr__(self, 'vector_contract', deepcopy(self.vector_contract))
        object.__setattr__(self, '_vector_identity', identity(self.vector_contract))
        for fold in self.declaration.tuning_folds+self.declaration.final_folds:
            validate_rows(self.records, fold)
        if not self.declaration.data_id.endswith(':'+self._records_identity):
            raise ValueError('Profile records differ from declared data identity')
        if not self.choices or any(len(v) < 2 for v in self.choices.values()):
            raise ValueError('Finite nontrivial search choices required')
        if self.work_unit!=WORK_UNIT and (type(self.max_work_per_call) not in (int,float)
                or not math.isfinite(self.max_work_per_call) or self.max_work_per_call<=0):
            raise ValueError('Non-row work requires an explicit finite call reservation')
        if self.vector_contract is not None and self.vector_contract['work_unit']!=self.work_unit:
            raise ValueError('Vector and adapter work units differ')

    def evaluate(self, config, fold):
        config = dict(config)
        if set(config) != set(self.choices) or any(
                type(config[k]) is bool or config[k] not in values for k,values in self.choices.items()):
            raise ValueError('Configuration outside declared finite domain')
        if fold not in self.declaration.tuning_folds+self.declaration.final_folds:
            raise ValueError('Undeclared evaluation fold')
        if identity(self.records) != self._records_identity:
            raise ValueError('Profile data changed after declaration')
        if identity(self.choices) != self._choices_identity:
            raise ValueError('Search domain changed after profile construction')
        if identity(self.vector_contract)!=self._vector_identity:
            raise ValueError('Vector contract changed after profile construction')
        train, score = validate_rows(self.records, fold)
        result = self.evaluator(config, train, score)
        if (not math.isfinite(result['loss']) or type(result['work']) not in (int,float)
                or not math.isfinite(result['work']) or result['work']<0
                or (self.work_unit==WORK_UNIT and result['work']!=len(train)+len(score))
                or (self.max_work_per_call is not None and result['work']>self.max_work_per_call)):
            raise ValueError('Invalid endpoint loss or declared work meter')
        canonical(result)  # Refuse nonfinite or unserializable artifact measurements.
        return result

    def objective(self, directory):
        directory = Path(directory)
        def objective(config, seed, evaluation, trial_id):
            if evaluation.declaration_identity != self.declaration.identity:
                raise ValueError('Evaluation declaration identity differs')
            folds = {'tuning':self.declaration.tuning_folds, 'final':self.declaration.final_folds}
            seeds = {'tuning':self.declaration.tuning_seeds, 'final':self.declaration.final_seeds}
            if (evaluation.role not in folds or evaluation.fold not in folds[evaluation.role]
                    or seed not in seeds[evaluation.role]):
                raise ValueError('Evaluation role, fold or seed differs')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', trial_id):
                raise ValueError('Unsafe trial identity')
            result = self.evaluate(config,evaluation.fold)
            payload = dict(profile=self.name,declaration_identity=self.declaration.identity,
                config=dict(config),role=evaluation.role,fold=evaluation.fold.name,seed=seed,
                train_ids=list(evaluation.fold.train_ids),score_ids=list(evaluation.fold.score_ids),
                determinism=DETERMINISM,**result)
            path = write_artifact(directory/'models'/(trial_id+'.json'),payload)
            if self.vector_contract is not None:
                return {'objectives':result['objectives'],'constraints':result['constraints'],
                        'work':result['work'],'artifacts':{'model':path}}
            return {'value':result['loss'], 'artifacts':{'model':path}, 'metadata':{
                'resource':{'work':result['work'],'unit':self.work_unit},
                'profile':{'name':self.name,'determinism':DETERMINISM,
                           'assessment':deepcopy(result.get('assessment'))}}}
        return objective

    def make_study(self, directory, store, *, budget=8, search_seed=19):
        if type(budget) is not int or not 1 <= budget <= 32:
            raise ValueError('Profile search budget must be in [1,32]')
        folds = self.declaration.tuning_folds+self.declaration.final_folds
        maximum = self.max_work_per_call or max(len(f.train_ids)+len(f.score_ids) for f in folds)
        tuning_calls = len(self.declaration.tuning_folds)*len(self.declaration.tuning_seeds)
        final_calls = len(self.declaration.final_folds)*len(self.declaration.final_seeds)
        space=SearchSpace([Knob(k,'categorical',v) for k,v in self.choices.items()])
        if self.vector_contract is not None:
            kind=MultiObjectiveStudy
            searcher=MultiObjectiveRandomSearcher(space,seed=search_seed,**self.vector_contract)
            options=deepcopy(self.vector_contract)
            final_calls*=budget  # Every sampled candidate could be on the front.
        else:
            kind=Study;searcher=RandomSearcher(space,seed=search_seed);options={'maximize':False}
        return kind(searcher,LocalExecutor(),self.objective(directory),**options,
            budget=budget,study_name='bank_'+self.name,store=store,
            declaration=self.declaration,checkpoint_dir=directory,
            # Reserve one uncertain interrupted call in each role as well as
            # the planned calls; loss of a worker is charged, never free work.
            resource_budget=StudyBudget(budget,self.work_unit,(budget*tuning_calls+1)*maximum,
                                       (final_calls+1)*maximum,maximum))

    def run(self, directory, *, budget=8, resume=False):
        directory = Path(directory); directory.mkdir(parents=True,exist_ok=True)
        if (directory/'study.sqlite').exists() and not resume:
            raise ValueError('Existing study requires explicit resume or a fresh directory')
        with closing(Store(directory/'study.sqlite')) as store:
            study = self.make_study(directory,store,budget=budget)
            if resume: study.load_checkpoint()
            try: result = study.run()
            except IncompleteStudyError as exc:
                if self.vector_contract is None: raise
                result=exc.result
            report = study.report()
            path = directory/'report.json'
            if path.exists():
                if json.loads(path.read_text()) != report:
                    raise ValueError('Existing completed report differs; use a fresh output directory')
            else: study.export_report(path)
            final_assessments=[{'artifact':a['path'],'assessment':load_artifact(a['path'],profile=self).get('assessment')}
                               for a in report['artifacts'] if a['role']=='final']
            return {'profile':self.name,'result':result.to_dict(),'report':report,
                    'final_assessments':final_assessments,
                    'scientific_acceptance':False}
