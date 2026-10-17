"""Feasible finite fronts, protected evaluation, neural artifacts and recovery."""
from contextlib import closing

import pytest

from hponas.store import Store
from hponas import Config,IncompleteStudyError,MultiObjectiveRandomSearcher
from workloads.bank_solvers import solver_profile,feasible,CONTRACT
from workloads.bank_neural import evaluate,configurations
from workloads.bank_workflow import load_artifact


class EnumeratedNetworks(MultiObjectiveRandomSearcher):
    def suggest(self):
        return Config(configurations()[len(self.trials)])


def recovery_study(profile,directory,store):
    study=profile.make_study(directory,store,budget=16)
    study.searcher=EnumeratedNetworks(study.searcher.search_space,seed=19,**CONTRACT)
    return study


def test_public_neural_front_matches_enumerated_feasible_observations_and_reloads(tmp_path):
    profile=solver_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=32);result=study.run();report=study.report()
        rows=[(t['trial_id'],t['vector']) for t in report['trials']]
        eligible=[(tid,v['objectives']) for tid,v in rows if feasible(v['constraints'])]
        expected=[tid for tid,p in eligible if not any(all(q[k]<=p[k] for k in p) and any(q[k]<p[k] for k in p) for _,q in eligible)]
        assert expected and report['selection']['trial_ids']==expected
        assert len(study.searcher.history)==32
        assert all(r.metadata['evaluation']['role']=='tuning' for r in study.searcher.history)
        assert report==store.read_report(study.study_name)
        tuning=final=0
        for artifact in report['artifacts']:
            saved=load_artifact(artifact['path'],profile=profile)
            nodes=[profile.records[i]['x'] for i in saved['score_ids']]
            actual=evaluate(saved['model'],nodes+[0.])
            assert actual['values'][:-1]==saved['predictions']['values']
            assert actual['derivatives'][:-1]==saved['predictions']['derivatives']
            if saved['role']=='tuning':tuning+=saved['work']
            else:final+=saved['work']
        assert report['resources']['tuning']['measured_work']==tuning
        assert report['resources']['final']['measured_work']==final
        restored=profile.make_study(tmp_path,store,budget=32);restored.load_checkpoint()
        restored.run();assert restored.report()==report


@pytest.mark.parametrize('role',['tuning','final'])
def test_vector_profile_recovers_and_keeps_selected_front(tmp_path,role):
    profile=solver_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=recovery_study(profile,tmp_path,store);fn=study.objective_fn.fn;calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if (role=='tuning' and len(calls)==2) or (role=='final' and evaluation.role=='final'):
                raise KeyboardInterrupt('vector neural recovery probe')
            return fn(config,seed,evaluation,trial_id)
        study.objective_fn.fn=interrupt
        with pytest.raises(KeyboardInterrupt):study.run()
        state=store.load_study_snapshot(study.study_name)
        committed={r['result']['trial_id'] for rows in state['evaluation']['tuning'].values() for r in rows}
        restored=recovery_study(profile,tmp_path,store);restored.load_checkpoint()
        seen=[];original=restored.objective_fn.fn
        def record(config,seed,evaluation,trial_id):
            seen.append(trial_id);return original(config,seed,evaluation,trial_id)
        restored.objective_fn.fn=record;result=restored.run()
        assert not committed.intersection(seen) and seen[0]==calls[-1]
        assert result.evaluation['outcome']=='completed'
        if role=='final':assert result.evaluation['selection']==state['evaluation']['selection']
        assert result.resources[role]['charged_work']>result.resources[role]['measured_work']


def test_maintained_vector_example_keeps_explicit_feasibility_outcome(tmp_path):
    from examples.bank_tuning import run
    output=run('solver',tmp_path,budget=16)
    # This retained random sequence misses all four mathematically feasible
    # configurations in its first sixteen proposals. It must remain explicit.
    assert output['report']['selection']['trial_ids']==[]
    assert output['final_assessments']==[]
    assert output['result']['reason']=='no_feasible_full_fidelity_result'
    assert run('solver',tmp_path,budget=16,resume=True)['report']==output['report']


def test_empty_feasible_front_is_explicit_and_cannot_use_small_scalar_loss(tmp_path):
    profile=solver_profile()
    with closing(Store(tmp_path/'store.sqlite')) as store:
        study=profile.make_study(tmp_path,store,budget=1)
        study.searcher.suggest=lambda:Config({'width':2,'depth':1,'activation':'tanh','representation':1,'ridge':.0625})
        with pytest.raises(IncompleteStudyError) as error:study.run()
        assert error.value.result.front==[]
        assert study.report()['selection']['trial_ids']==[]
        assert not study.report()['evaluation_records']['final']
