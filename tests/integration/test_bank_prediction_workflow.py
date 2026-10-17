"""Configured prediction searches, isolated evaluation, artifacts and recovery."""
from contextlib import closing
from copy import deepcopy
import json
from statistics import fmean

import pytest

from hponas.store import Store
from workloads.bank_prediction import prediction_profile, predict
from workloads.bank_workflow import load_artifact, write_artifact
from tests.validation.test_bank_prediction import reference, TOL


@pytest.mark.parametrize('name',['ridge','bernoulli','censored','ar'])
def test_public_workflow_selection_final_reports_work_and_model_reload(tmp_path,name):
    profile=prediction_profile(name)
    with closing(Store(tmp_path/'study.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=4); result=study.run()
        expected=[]
        for item in result.history:
            config=study.trials[item.trial_id].config.values
            expected.append(fmean(reference(name,config,f)['loss'] for f in profile.declaration.tuning_folds))
        assert result.best_value==pytest.approx(min(expected),rel=TOL,abs=TOL)
        assert [r.objective_value for r in study.searcher.history]==pytest.approx(expected,rel=TOL,abs=TOL)
        config=result.best_config.values
        final=fmean(reference(name,config,f)['loss'] for f in profile.declaration.final_folds)
        assert result.evaluation['final'][0]['objectives']['loss']['mean']==pytest.approx(final,rel=TOL,abs=TOL)
        assert len(study.searcher.history)==4
        assert all(r.metadata['evaluation']['role']=='tuning' for r in study.searcher.history)
        report=study.report(); assert report==store.read_report(study.study_name)
        tuning_work=4*sum(len(f.train_ids)+len(f.score_ids) for f in profile.declaration.tuning_folds)
        final_work=sum(len(f.train_ids)+len(f.score_ids) for f in profile.declaration.final_folds)
        assert report['resources']['tuning']['measured_work']==tuning_work
        assert report['resources']['final']['measured_work']==final_work
        assert len(report['artifacts'])==4*len(profile.declaration.tuning_folds)+len(profile.declaration.final_folds)
        for artifact in report['artifacts']:
            saved=load_artifact(artifact['path'],profile=profile)
            assert saved['role']==artifact['role'] and saved['seed']==artifact['seed']
            assert saved['determinism']
            rows=[profile.records[i] for i in saved['score_ids']]
            assert predict(saved['model'],rows)==saved['predictions']
        restored=profile.make_study(tmp_path,store,budget=4); restored.load_checkpoint()
        def forbidden(config,seed,evaluation,trial_id): pytest.fail('Committed work repeated')
        restored.objective_fn=forbidden; restored.run()
        assert restored.report()==report


@pytest.mark.parametrize('name',['ridge','bernoulli','censored','ar'])
@pytest.mark.parametrize('role',['tuning','final'])
def test_interrupted_profile_recovers_committed_records_without_reselection(tmp_path,name,role):
    profile=prediction_profile(name)
    with closing(Store(tmp_path/'study.sqlite')) as store:
        original=profile.make_study(tmp_path,store,budget=3); fn=original.objective_fn; calls=[]
        def interrupted(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('simulated interruption')
            return fn(config,seed,evaluation,trial_id)
        original.objective_fn=interrupted
        with pytest.raises(KeyboardInterrupt): original.run()
        raw=store.load_study_snapshot(original.study_name)
        committed={r['result']['trial_id'] for part in ('tuning','final') for rows in raw['evaluation'][part].values() for r in rows}
        selection=deepcopy(raw['evaluation']['selection'])
        resumed=profile.make_study(tmp_path,store,budget=3); resumed.load_checkpoint()
        resumed_calls=[]; objective=resumed.objective_fn
        def record(config,seed,evaluation,trial_id):
            resumed_calls.append(trial_id)
            return objective(config,seed,evaluation,trial_id)
        resumed.objective_fn=record; result=resumed.run()
        assert not committed.intersection(resumed_calls)
        assert resumed_calls[0]==calls[-1]
        assert result.evaluation['outcome']=='completed'
        assert len(resumed.searcher.history)==3
        if role=='final': assert result.evaluation['selection']==selection
        assert result.resources[role]['charged_work']>result.resources[role]['measured_work']


def test_artifact_corruption_schema_identity_and_overwrite_are_refused(tmp_path):
    profile=prediction_profile('ridge'); profile.run(tmp_path,budget=2)
    path=next((tmp_path/'models').glob('*.json')); saved=load_artifact(path,profile=profile)
    with pytest.raises(ValueError,match='configuration'): load_artifact(path,config={'ridge':-1})
    with pytest.raises(ValueError,match='identity'): load_artifact(path,profile=prediction_profile('ar'))
    changed={**saved,'role':'invented'}
    with pytest.raises(ValueError,match='differs'): write_artifact(path,changed)
    assert load_artifact(path)==saved
    raw=json.loads(path.read_text());raw['payload']['loss']=-999;path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='digest'): load_artifact(path)
    raw['schema']='unknown';path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='schema'): load_artifact(path)


def test_maintained_example_resumes_without_overwriting_report(tmp_path):
    from examples.bank_tuning import run
    first=run('ar',tmp_path,budget=3)
    second=run('ar',tmp_path,budget=3,resume=True)
    assert first['report']==second['report']
    with pytest.raises(ValueError,match='explicit resume'): run('ar',tmp_path,budget=3)
