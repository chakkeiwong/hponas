"""Causal support status survives complete public fitting and recovery."""
from contextlib import closing
from statistics import fmean

import pytest

from hponas.store import Store
from workloads.bank_causal import causal_profile, predict_nuisance, assess_effect
from workloads.bank_workflow import load_artifact
from validation.bank_references import causal_reference


@pytest.mark.parametrize('variant,status',[
    ('causal','identified_finite_model'),('causal_overlap','unsupported_overlap'),
    ('causal_unidentified','unidentified')])
def test_example_retains_final_causal_status_and_reloads_actual_models(tmp_path,variant,status):
    from examples.bank_tuning import run
    result=run(variant,tmp_path,budget=4)
    profile=causal_profile(overlap=variant!='causal_overlap',identified=variant!='causal_unidentified')
    final=result['final_assessments'];assert len(final)==1
    assert final[0]['assessment']['status']==status
    if status!='identified_finite_model':
        assert final[0]['assessment']['effect'] is None
        assert final[0]['assessment']['bounds']==[-8,8]
    report=result['report']
    assert report['resources']['tuning']['measured_work']==4*2*32
    assert report['resources']['final']['measured_work']==48
    assert len(report['artifacts'])==9
    for artifact in report['artifacts']:
        saved=load_artifact(artifact['path'],profile=profile)
        assert not set(saved['model']['train_ids']).intersection(saved['score_ids'])
        score=[profile.records[i] for i in saved['score_ids']]
        prediction=predict_nuisance(saved['model'],score)
        assert prediction==saved['predictions']
        assert assess_effect(saved['model'],score,prediction)==saved['assessment']
    for rows in report['evaluation_records']['final'].values():
        assert rows[0]['result']['metadata']['profile']['assessment']['status']==status
    assert run(variant,tmp_path,budget=4,resume=True)['report']==report


def test_actual_nuisance_selection_and_final_assessment_use_separate_fits(tmp_path):
    profile=causal_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=6);result=study.run()
        expected=[causal_reference(**study.trials[r.trial_id].config.values)['loss'] for r in result.history]
        assert result.best_value==pytest.approx(min(expected),abs=2**-38)
        assert len(study.searcher.history)==6
        assert all(r.metadata['evaluation']['role']=='tuning' for r in study.searcher.history)
        config=result.best_config.values
        final_record=next(iter(study.report()['evaluation_records']['final'].values()))[0]
        assessment=final_record['result']['metadata']['profile']['assessment']
        assert assessment['effect']==pytest.approx(causal_reference(**config,training_groups=2)['effect'],abs=2**-38)
        assert result.evaluation['final'][0]['objectives']['loss']['mean']==pytest.approx(
            causal_reference(**config,training_groups=2)['loss'],abs=2**-38)


@pytest.mark.parametrize('overlap,identified',[(True,True),(False,True),(True,False)])
@pytest.mark.parametrize('role',['tuning','final'])
def test_causal_recovery_preserves_committed_folds_and_protected_selection(tmp_path,overlap,identified,role):
    profile=causal_profile(overlap=overlap,identified=identified)
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=3);original=study.objective_fn;calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('causal recovery probe')
            return original(config,seed,evaluation,trial_id)
        study.objective_fn=interrupt
        with pytest.raises(KeyboardInterrupt):study.run()
        state=store.load_study_snapshot(study.study_name)
        committed={r['result']['trial_id'] for part in ('tuning','final') for rows in state['evaluation'][part].values() for r in rows}
        resumed=profile.make_study(tmp_path,store,budget=3);resumed.load_checkpoint()
        seen=[];fn=resumed.objective_fn
        def record(config,seed,evaluation,trial_id):
            seen.append(trial_id);return fn(config,seed,evaluation,trial_id)
        resumed.objective_fn=record;result=resumed.run()
        assert not committed.intersection(seen)
        assert seen[0]==calls[-1] and result.evaluation['outcome']=='completed'
        assert result.resources[role]['charged_work']>result.resources[role]['measured_work']
        if role=='final': assert result.evaluation['selection']==state['evaluation']['selection']


def test_changed_identification_contract_cannot_resume_as_original(tmp_path):
    original=causal_profile();original.run(tmp_path,budget=2)
    with closing(Store(tmp_path/'other.sqlite')) as store:
        target=causal_profile(identified=False).make_study(tmp_path,store,budget=2)
        with pytest.raises(ValueError,match='identity differs'):
            target.load_checkpoint(tmp_path/'bank_causal_checkpoint.json')
