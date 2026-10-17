"""Full decision studies retain signed, bounded and unidentifiable outcomes."""
from contextlib import closing

import pytest

from hponas.store import Store
from workloads.bank_decisions import decision_profile,reload_decision
from workloads.bank_workflow import load_artifact
from validation.bank_references import valuation_reference,allocation_reference

NAMES=['valuation','valuation_unidentified','wallet','allocation','allocation_uncertain']


@pytest.mark.parametrize('name',NAMES)
def test_public_decision_study_retains_actual_selection_units_and_final_assessments(tmp_path,name):
    from examples.bank_tuning import run
    output=run(name,tmp_path,budget=4);profile=decision_profile(name);report=output['report']
    actual=[]
    for trial in report['trials']:
        config=trial['config']['values']
        if name.startswith('valuation'):expected=valuation_reference(config['alpha'])['loss']
        elif name=='wallet':
            import math
            expected=math.log(2)
        else:expected=allocation_reference(config['shrinkage'],uncertain=name=='allocation_uncertain')['loss']
        actual.append(expected)
    assert output['result']['best_value']==pytest.approx(min(actual),abs=2**-38)
    assert report['resources']['tuning']['measured_work']==32
    assert report['resources']['final']['measured_work']==8
    final=output['final_assessments'];assert len(final)==1
    if name=='valuation_unidentified':assert final[0]['assessment']['npv'] is None
    if name=='wallet':assert final[0]['assessment']['latent_mean'] is None
    if name=='allocation_uncertain':assert final[0]['assessment']['point_identified_optimum'] is None
    for artifact in report['artifacts']:
        saved=load_artifact(artifact['path'],profile=profile)
        decision=reload_decision(saved['model']);assert decision
        assert saved['assessment']['unit']
    for rows in report['evaluation_records']['final'].values():
        assert rows[0]['result']['metadata']['profile']['assessment']==final[0]['assessment']
    assert run(name,tmp_path,budget=4,resume=True)['report']==report


@pytest.mark.parametrize('name',NAMES)
@pytest.mark.parametrize('role',['tuning','final'])
def test_decision_recovery_keeps_committed_calls_frozen_selection_and_bounds(tmp_path,name,role):
    profile=decision_profile(name)
    with closing(Store(tmp_path/'study.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=3);fn=study.objective_fn;calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('decision recovery probe')
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
        assert result.evaluation['outcome']=='completed' and len(restored.searcher.history)==3
        assert all(r.metadata['evaluation']['role']=='tuning' for r in restored.searcher.history)
        if role=='final':assert result.evaluation['selection']==state['evaluation']['selection']
