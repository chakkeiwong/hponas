"""Public prediction front, source-independent arrays, final isolation and resume."""
from contextlib import closing

import pytest

from hponas.store import Store
from workloads.bank_nas import nas_prediction_profile,CONTRACT
from workloads.bank_solvers import solver_profile
from workloads.bank_neural import evaluate
from workloads.bank_workflow import load_artifact


def test_observed_prediction_front_is_independently_enumerated_and_models_reload(tmp_path):
    from examples.bank_tuning import run
    output=run('nas_prediction',tmp_path,budget=32);report=output['report'];profile=nas_prediction_profile()
    eligible=[(t['trial_id'],t['vector']['objectives']) for t in report['trials']
              if all(v<=CONTRACT['constraints'][key] for key,v in t['vector']['constraints'].items())]
    expected=[tid for tid,p in eligible if not any(all(q[k]<=p[k] for k in p) and any(q[k]<p[k] for k in p) for _,q in eligible)]
    assert report['selection']['trial_ids']==expected and expected
    work={'tuning':0,'final':0}
    for artifact in report['artifacts']:
        saved=load_artifact(artifact['path'],profile=profile);work[saved['role']]+=saved['work']
        nodes=[profile.records[i]['x'] for i in saved['score_ids']]
        assert evaluate(saved['model'],nodes)['values']==saved['predictions']['values']
        with pytest.raises(ValueError,match='identity'):load_artifact(artifact['path'],profile=solver_profile())
    for role in work:assert report['resources'][role]['measured_work']==work[role]
    assert run('nas_prediction',tmp_path,budget=32,resume=True)['report']==report


@pytest.mark.parametrize('role',['tuning','final'])
def test_neural_prediction_recovery_preserves_committed_models_and_front(tmp_path,role):
    profile=nas_prediction_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=8);fn=study.objective_fn.fn;calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('prediction NAS recovery probe')
            return fn(config,seed,evaluation,trial_id)
        study.objective_fn.fn=interrupt
        with pytest.raises(KeyboardInterrupt):study.run()
        state=store.load_study_snapshot(study.study_name)
        committed={r['result']['trial_id'] for rows in state['evaluation']['tuning'].values() for r in rows}
        restored=profile.make_study(tmp_path,store,budget=8);restored.load_checkpoint()
        seen=[];original=restored.objective_fn.fn
        def record(config,seed,evaluation,trial_id):
            seen.append(trial_id);return original(config,seed,evaluation,trial_id)
        restored.objective_fn.fn=record;result=restored.run()
        assert not committed.intersection(seen) and seen[0]==calls[-1]
        assert result.evaluation['outcome']=='completed' and len(restored.searcher.history)==8
        if role=='final':assert result.evaluation['selection']==state['evaluation']['selection']
        assert all(r.metadata['evaluation']['role']=='tuning' for r in restored.searcher.history)
