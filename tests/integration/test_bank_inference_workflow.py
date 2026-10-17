"""Inference profile persistence and separate native-handoff artifacts."""
from contextlib import closing

import pytest

from hponas.store import Store
from workloads.bank_inference import inference_profile,predict_filter
from workloads.bank_workflow import load_artifact
from validation.bank_references import gaussian_sequence_reference


def test_predictive_likelihood_selection_final_records_and_reloaded_filter(tmp_path):
    profile=inference_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=6);result=study.run()
        expected=[gaussian_sequence_reference((.5,0.,-.25),study.trials[r.trial_id].config.values['observation_variance'])/3
                  for r in result.history]
        assert result.best_value==pytest.approx(min(expected),abs=2**-38)
        r=result.best_config.values['observation_variance']
        assert result.evaluation['final'][0]['objectives']['loss']['mean']==pytest.approx(
            gaussian_sequence_reference((.75,-.25,.5),r)/3,abs=2**-38)
        report=study.report();assert report==store.read_report(study.study_name)
        assert report['resources']['tuning']['measured_work']==36
        assert report['resources']['final']['measured_work']==9
        assert len(study.searcher.history)==6
        assert all(r.metadata['evaluation']['role']=='tuning' for r in study.searcher.history)
        for artifact in report['artifacts']:
            saved=load_artifact(artifact['path'],profile=profile)
            score=[profile.records[i] for i in saved['score_ids']]
            assert predict_filter(saved['model'],score)==saved['predictions']
            if saved['role']=='final':assert set(saved['model']['training_fits'])=={'train','tune'}
        restored=profile.make_study(tmp_path,store,budget=6);restored.load_checkpoint()
        def forbidden(config,seed,evaluation,trial_id):pytest.fail('Completed inference fit repeated')
        restored.objective_fn=forbidden;restored.run()
        assert restored.report()==report


@pytest.mark.parametrize('role',['tuning','final'])
def test_inference_resume_retains_executed_likelihoods_and_final_selection(tmp_path,role):
    profile=inference_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=3);fn=study.objective_fn;calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('inference recovery probe')
            return fn(config,seed,evaluation,trial_id)
        study.objective_fn=interrupt
        with pytest.raises(KeyboardInterrupt):study.run()
        state=store.load_study_snapshot(study.study_name)
        committed={r['result']['trial_id'] for rows in state['evaluation']['tuning'].values() for r in rows}
        restored=profile.make_study(tmp_path,store,budget=3);restored.load_checkpoint()
        seen=[];original=restored.objective_fn
        def record(config,seed,evaluation,trial_id):
            seen.append(trial_id);return original(config,seed,evaluation,trial_id)
        restored.objective_fn=record;result=restored.run()
        assert not committed.intersection(seen) and seen[0]==calls[-1]
        assert result.evaluation['outcome']=='completed'
        if role=='final':assert result.evaluation['selection']==state['evaluation']['selection']


def test_native_example_retains_all_pairs_and_target_separately(tmp_path):
    from examples.bank_inference_handoff import run
    output=run(tmp_path);saved=load_artifact(output['artifact'])
    assert saved['kind']=='native_inference_handoff'
    assert saved['handoff']==output['result']
    assert len(saved['handoff']['verified_pairs'])==9
    assert saved['handoff']['selection_policy']=='retain_all_freshly_verified_pairs'
    assert not saved['handoff']['posterior_assessment_used_for_selection']


def test_maintained_inference_profile_is_independent_of_native_candidate_ranking(tmp_path):
    from examples.bank_tuning import run
    output=run('inference',tmp_path,budget=3)
    assert output['final_assessments'][0]['assessment']['posterior_convergence']=='not_assessed'
    assert run('inference',tmp_path,budget=3,resume=True)['report']==output['report']
