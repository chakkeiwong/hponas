"""Actual source studies, protected histories and interrupted transfer workflow."""
from contextlib import closing
from copy import deepcopy
import json
import math
import time

import pytest

from hponas import (Config, EvaluationFold, EvaluationObjective, LocalExecutor, Knob,
                    RandomSearcher, SearchSpace, Study, StudyDeclaration)
from hponas.rgpe import RGPESearcher, prepare_rgpe_history
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.store import Store
from hponas.warm_history import digest, target_context


def declaration(data='target-data', **changes):
    values = dict(objective_id='loss:v1', model_id='line:v1', data_id=data, protocol_id='repeat:v1',
        objectives=(EvaluationObjective('loss', 'min', 'units'),),
        tuning_folds=(EvaluationFold('tune-a', ('train-a',), ('score-a',)),
                      EvaluationFold('tune-b', ('train-b',), ('score-b',))),
        final_folds=(EvaluationFold('final', ('train-a', 'score-a'), ('sealed',)),),
        tuning_seeds=(2, 4), final_seeds=(12, 14))
    values.update(changes)
    return StudyDeclaration(**values)


def space(): return SearchSpace([Knob('x', 'ordinal', (0, 5))])


def context(**changes):
    values = dict(study_id='target', task_id='target-task', model_family='line', task_domain='finite',
                  objective_key='loss:v1', direction='minimize', history_cutoff=time.time()+1)
    values.update(changes)
    return target_context(space(), **values)


class Sequence(RandomSearcher):
    def suggest(self): return Config({'x': len(self.history)})


def objective(config, seed, evaluation):
    if evaluation.role == 'final': return {'value': -1e12-config['x'], 'cost': 3.}
    return {'value': config['x']+seed+(10 if evaluation.fold.name == 'tune-b' else 0), 'cost': 2.}


def source(store, sid='past', *, declared=None, task=None):
    study = Study(Sequence(space(), seed=1), LocalExecutor(), objective, budget=4, maximize=False,
                  study_name=sid, store=store, declaration=declared or declaration('past-data'))
    study.run()
    store.freeze_warm_history(sid, task_id=task or sid+'-task', model_family='line', task_domain='finite',
                              objective_key='loss:v1')
    return study


def target(store, saved=None, fn=objective, **changes):
    searcher = (RGPESearcher.from_store(space(), store, context=context(), declaration=declaration(), n_initial=2)
                if saved is None else RGPESearcher.from_state(space(), saved))
    values = dict(searcher=searcher, executor=LocalExecutor(), objective_fn=fn, budget=5, maximize=False,
                  study_name='target', store=store, declaration=declaration())
    values.update(changes)
    return Study(**values)


def test_real_declared_sources_keep_raw_tuning_proof_and_exclude_final_sentinel(tmp_path):
    with closing(Store(tmp_path/'store.db')) as store:
        source(store)
        saved = prepare_rgpe_history(space(), store, context=context(), declaration=declaration(), n_initial=2)
        assert len(saved['sources']) == 1
        proof = saved['sources'][0]['tuning_proof']
        assert [p['value'] for p in proof] == [8., 9., 10., 11.]
        assert len(proof[0]['repetitions']) == 4
        assert '-1000000000000' not in json.dumps(saved)
        run = target(store); result = run.run()
        assert [r.objective_value for r in run.searcher.history[:2]] == [8., 9.]
        assert result.best_value == 8.
        assert len(run.searcher.history) == 5
        assert all(r.metadata['evaluation']['role'] == 'tuning' for r in run.searcher.history)
        assert result.evaluation['final'][0]['objectives']['loss']['mean'] < -1e11
        assert result.evaluation['selection'] == ['target_trial_0']
        assert run.searcher.posterior([{'x': 2}])['weights']['past'] > 0.


@pytest.mark.parametrize('kind,reason', [
    ('protocol', 'incompatible_declaration_protocol_id'),
    ('task', 'held_out'), ('target', 'held_out'),
    ('protected', 'protected_target_final_exposure'),
    ('legacy', 'missing_declared_tuning_proof'),
    ('cutoff', 'outside_history_cutoff'),
])
def test_history_rejection_prevents_attractive_but_ineligible_transfer(tmp_path, kind, reason):
    with closing(Store(tmp_path/'store.db')) as store:
        changes = {}
        if kind == 'protocol': changes['declared'] = declaration('past-data', protocol_id='other:v1')
        elif kind == 'task': changes['task'] = 'target-task'
        elif kind == 'protected': changes['declared'] = declaration('target-data',
            tuning_folds=(EvaluationFold('tune-a', ('sealed',), ('other-score',)),),
            final_folds=(EvaluationFold('final', ('sealed',), ('other-final',)),))
        if kind == 'legacy':
            run = Study(Sequence(space(),seed=1), LocalExecutor(), lambda c: -1e20, budget=4, maximize=False,
                        study_name='past', store=store, legacy_reason='Role-proof refusal counterexample')
            run.run()
            store.freeze_warm_history('past',task_id='past-task',model_family='line',task_domain='finite',objective_key='loss:v1')
        else: source(store, sid='target' if kind == 'target' else 'past', **changes)
        saved = prepare_rgpe_history(space(),store,context=context(history_cutoff=0. if kind=='cutoff' else time.time()+1),
                                      declaration=declaration(),n_initial=2)
        assert saved['sources'] == [] and saved['selection']['seeds'] == []
        assert saved['excluded'][0]['reason'] == reason


@pytest.mark.parametrize('kind', ['seed', 'raw_value', 'aggregate', 'trial', 'identity'])
def test_source_snapshot_corruption_is_not_promoted_to_valid_transfer(tmp_path,kind):
    with closing(Store(tmp_path/'store.db')) as store:
        source(store)
        state=store.load_study_snapshot('past'); first='past_trial_0'
        if kind=='seed': state['evaluation']['tuning'][first][0]['seed']=99
        elif kind=='raw_value': state['evaluation']['tuning'][first][0]['result']['objective_value']=-999.
        elif kind=='aggregate': state['results'][first]['objective_value']=-999.
        elif kind=='trial': state['trials'][first]['trial_id']='other'
        elif kind=='identity': state['evaluation']['identity']='other'
        with store._conn:
            store._conn.execute('UPDATE study_snapshots SET payload=? WHERE study_id=?',(json.dumps(state),'past'))
        with pytest.raises(ValueError):
            prepare_rgpe_history(space(),store,context=context(),declaration=declaration(),n_initial=2)


def test_bundle_rehash_does_not_hide_false_raw_proof(tmp_path):
    with closing(Store(tmp_path/'store.db')) as store:
        source(store)
        saved=prepare_rgpe_history(space(),store,context=context(),declaration=declaration(),n_initial=2)
        saved['sources'][0]['tuning_proof'][0]['repetitions'][0]['result']['objective_value']=-1e20
        saved['binding']=digest({k:v for k,v in saved.items() if k!='binding'})
        with pytest.raises(ValueError,match='tuning proof'):
            RGPESearcher(space(),saved,n_initial=2)


@pytest.mark.parametrize('role', ['tuning','final'])
def test_interruption_recovers_bundle_and_commits_without_final_feedback(tmp_path,role):
    with closing(Store(tmp_path/'store.db')) as store:
        source(store); calls=[]
        def interrupted(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if role=='tuning' and len(calls)==10 or role=='final' and evaluation.role=='final':
                raise KeyboardInterrupt('simulated interruption')
            return objective(config,seed,evaluation)
        run=target(store,fn=interrupted)
        with pytest.raises(KeyboardInterrupt): run.run()
        state=store.load_study_snapshot('target')
        committed={r['result']['trial_id'] for part in ('tuning','final')
                   for rows in state['evaluation'][part].values() for r in rows}
        saved=deepcopy(state['searcher_state']); selection=deepcopy(state['evaluation']['selection'])
        source(store,'newly-arrived')  # recovery must never query/reorder this source
        resumed_calls=[]
        def resumed(config,seed,evaluation,trial_id):
            resumed_calls.append(trial_id)
            return objective(config,seed,evaluation)
        restored=target(store,saved,fn=resumed); restored.load_checkpoint()
        assert restored.searcher.bundle==saved['bundle']
        result=restored.run()
        assert resumed_calls[0]==calls[-1] and not committed.intersection(resumed_calls)
        assert len(restored.searcher.history)==5 and result.best_value==8.
        assert result.evaluation['uncertain_evaluations']==[calls[-1]]
        if role=='final': assert result.evaluation['selection']==selection


def test_failed_target_repetition_is_retained_and_not_fitted(tmp_path):
    with closing(Store(tmp_path/'store.db')) as store:
        source(store)
        def failed(config,seed,evaluation):
            if evaluation.role=='tuning' and config['x']==0 and seed==4: return {'value':math.nan,'cost':7.}
            return objective(config,seed,evaluation)
        run=target(store,fn=failed); result=run.run()
        assert result.history[0].status=='failed' and math.isnan(result.history[0].objective_value)
        assert result.best_value==9. and result.history[0].cost==18.
        assert run.searcher.posterior([{'x':0}])['weights']['past']>0.
        restored=target(store,run.searcher.get_state(),fn=failed);restored.load_checkpoint()
        assert restored.run().best_value==9.


@pytest.mark.parametrize('kind', ['protocol','legacy','scheduler','concurrency'])
def test_actual_study_protocol_and_unsupported_compositions_refuse_before_dispatch(tmp_path,kind):
    with closing(Store(tmp_path/'store.db')) as store:
        changes={}
        if kind=='protocol': changes['declaration']=declaration(protocol_id='other:v1')
        elif kind=='legacy': changes.update(declaration=None,legacy_reason='Explicit refusal test')
        elif kind=='scheduler': changes['scheduler']=ASHAScheduler(ASHAConfig(r_min=1,r_max=3))
        elif kind=='concurrency': changes['max_concurrent']=2
        with pytest.raises(ValueError): target(store,**changes)
