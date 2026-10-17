"""Run the integrated optimizer on real checkpointed quadratic updates."""
from copy import deepcopy
import json

import pytest

from hponas import CategoricalPriorBandSearcher, Knob, SearchSpace, PriorBandScheduler
from hponas import LocalExecutor, Study, PriorPendingError
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.store import Store
from workloads.streaming_quadratic import StreamingQuadratic
from validation.multifidelity_reference import value as exact


def searcher(cap=1, default=18, seed=0):
    return CategoricalPriorBandSearcher(SearchSpace([Knob('eta_index','categorical',list(range(1,26)))]),
                                        {'eta_index':default},rungs=[1,2,4,8],eta=2,seed=seed,max_proposals=cap)


def scheduler():
    return PriorBandScheduler(rungs=[1,2,4,8],eta=2,default_at_target=True)


def test_joint_priorband_checkpoint_pending_recovery_and_replay(tmp_path):
    store=Store(tmp_path/'priorband.sqlite')
    events=EventLog(tmp_path/'events.jsonl')
    workload=StreamingQuadratic()
    pending=0
    for attempt in range(100):
        target=Study(searcher(),LocalExecutor(),workload,budget=21,study_name='priorband',
                     maximize=False,scheduler=scheduler(),continuation='resume',store=store,event_log=events)
        if attempt:
            target.load_checkpoint()
        try:
            result=target.run()
        except PriorPendingError:
            pending+=1
            snapshot=store.load_study_snapshot('priorband')
            assert snapshot['searcher_state']['sampler']['pending_prior']
            continue
        break
    else:
        pytest.fail('Pending draw never completed under bounded diagnostic')
    assert pending>0
    assert result.n_trials==33
    assert len(workload.updates)==result.total_cost==100
    assert all(r.status in {'completed','paused'} for r in result.history)
    roots=[t for t in target.trials.values() if not t.parent_trial_id]
    assert [t.fidelity for t in roots]==[8]+[1]*8+[2]*4+[4]*4+[8]*4
    assert roots[0].config.values=={'eta_index':18}
    assert target.searcher.policy.resources()==100
    for row in result.history:
        index=target.trials[row.trial_id].config['eta_index']
        assert row.objective_value==pytest.approx(float(exact(index,int(row.fidelity))),abs=1e-12)
    assert any(context.get('mixture',{}).get('inc','0')!='0' for context in target.searcher._contexts)
    baseline=Study(searcher(1000),LocalExecutor(),StreamingQuadratic(),budget=21,study_name='priorband',
                   maximize=False,scheduler=scheduler(),continuation='resume')
    expected=baseline.run()
    assert [(r.trial_id,r.objective_value,r.fidelity) for r in result.history]==[(r.trial_id,r.objective_value,r.fidelity) for r in expected.history]
    engine=ReplayEngine(searcher(),events,seed=0,scheduler=scheduler())
    passed,message,_,_=engine.verify_determinism(21)
    assert passed,message
    assert engine.searcher.get_state()==target.searcher.get_state()
    assert engine.scheduler.state_dict()==target.scheduler.state_dict()
    store.close()


@pytest.mark.parametrize('damage', ['weights','policy','trial','default','direction','counter'])
def test_integrated_checkpoint_identity_and_policy_corruption_refused(tmp_path,damage):
    source=Study(searcher(1000),LocalExecutor(),StreamingQuadratic(),budget=5,study_name='short',
                 maximize=False,scheduler=scheduler(),continuation='resume')
    source.run()
    before=deepcopy(source._snapshot())
    bad=deepcopy(before)
    inner=bad['searcher_state']
    if damage=='weights': inner['contexts'][-1]['weights'][0]='999'
    elif damage=='policy': inner['policy']['rows']['short_trial_0']['work']+=1
    elif damage=='trial': inner['trials']['short_trial_0']['values']['eta_index']=19
    elif damage=='default': inner['contract']['distribution']['default']['eta_index']=19
    elif damage=='direction': inner['maximize']=True
    elif damage=='counter': inner['sampler']['started_draws']+=1
    path=tmp_path/'bad.json'
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        source.load_checkpoint(path)
    assert source._snapshot()==before


def test_plain_study_requires_the_matching_scheduler():
    # Uniform admission now refuses the missing scheduler before any proposal.
    with pytest.raises(ValueError,match='matching'):
        Study(searcher(),LocalExecutor(),StreamingQuadratic(),budget=2,maximize=False)


def test_completed_sampler_cannot_rebind_to_an_earlier_mixture():
    source=Study(searcher(1000),LocalExecutor(),StreamingQuadratic(),budget=21,
                 maximize=False,scheduler=scheduler(),continuation='resume')
    source.run()
    state=source.searcher.get_state()
    bad=deepcopy(state)
    bad['context']=deepcopy(bad['contexts'][1])
    sampler=source.searcher._make_sampler(bad['context'])
    sampler.advance(10000)
    bad['sampler']=sampler.state_dict()
    with pytest.raises(ValueError,match='last retained mixture'):
        source.searcher.set_state(bad)
    assert source.searcher.get_state()==state


@pytest.mark.parametrize('damage', ['lineage','duplicate_draw','direction'])
def test_policy_and_public_study_ledgers_must_agree(damage):
    source=Study(searcher(1000),LocalExecutor(),StreamingQuadratic(),budget=21,
                 maximize=False,scheduler=scheduler(),continuation='resume')
    source.run()
    state=source._snapshot()
    if damage=='lineage':
        promoted=next(tid for tid,root in state['roots'].items() if tid!=root)
        state['roots'][promoted]=promoted
    elif damage=='duplicate_draw':
        # Two identical configurations can represent distinct draws. Reusing
        # the same draw identity must not masquerade as two independent roots.
        roots=[tid for tid,root in state['roots'].items() if tid==root]
        a,b=next((a,b) for i,a in enumerate(roots) for b in roots[i+1:]
                 if source.searcher.trials[a].values==source.searcher.trials[b].values)
        source.searcher.trials[b].config_id=source.searcher.trials[a].config_id
        for tid in state['trials']:
            state['trials'][tid]['config']=source.searcher.trials[tid].to_dict()
    else:
        state['maximize']=True
    with pytest.raises(ValueError):
        source.searcher.validate_study_snapshot(state)
