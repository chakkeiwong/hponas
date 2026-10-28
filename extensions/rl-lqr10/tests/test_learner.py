from copy import deepcopy
import numpy as np
import pytest
import torch
from hponas_rl_lqr10.adapter import SACMember
from hponas_rl_lqr10.transfer import distill
from hponas_rl_lqr10.scoring import action_rows
from hponas_rl_lqr10.tasks import run_task,task
from hponas_rl_lqr10.study_v2 import selection

CONFIG=dict(actor_hiddens=[8,12],critic_hiddens=[12,8],actor_lr=.001,critic_lr=.002)

@pytest.fixture(scope='module')
def trained():
    m=SACMember(CONFIG,4101);m.train(320);return m.state()


def test_actual_ten_state_sac_and_four_optimizers(trained):
    m=SACMember.restore(trained)
    assert m.observation.shape==(11,)
    assert m.state()['contract']['states']==10 and m.state()['contract']['horizon']==30
    assert set(m.counters()['adam_steps'].values())=={16}
    assert m.counters()['alpha']!=pytest.approx(.01,abs=1e-8)


def test_restore_and_same_rng_continuation(trained,tmp_path):
    a=SACMember.restore(trained);identity=a.save(tmp_path/'checkpoint.pt')
    b=SACMember.restore(tmp_path/'checkpoint.pt')
    assert b.identity(b.state())==identity
    a.train(32);b.train(32)
    assert a.identity(a.state())==b.identity(b.state()) and a.score()==b.score()


def test_changed_architecture_and_copy(trained):
    t=SACMember.restore(trained);identity=t.identity(t.state())
    c=dict(CONFIG,actor_hiddens=[12,8,8],critic_hiddens=[8,8,8,8])
    s,r=distill(t,c,4102,16);s.train(16)
    assert s.config==c and r['teacher_unchanged'] and s.observation.shape==(11,)
    assert t.identity(t.state())==identity and set(s.counters()['adam_steps'].values())=={4}
    child=t.compatible_copy(dict(CONFIG,actor_lr=.0003),4103);child.train(16)
    assert child.counters()['rates']['policy']==.0003


def test_old_environment_checkpoint_rejected(trained):
    wrong=deepcopy(trained);wrong['contract']['states']=5
    with pytest.raises(ValueError,match='mismatch'):SACMember.restore(wrong)


def test_actor_export_dimensions_and_sample_score(trained,tmp_path):
    m=SACMember.restore(trained);r=m.score(tmp_path/'actor.pt')
    a=torch.jit.load(str(tmp_path/'actor.pt'))
    assert a(torch.zeros(4,11)).shape==(4,1)
    assert r['paths']==1024 and r['evaluation_seed']==1030001 and not r['exact_policy_expectation']
    assert r['gap']>=0 and r['pathwise_identity_error']<r['tolerance']
    assert len(np.unique(action_rows(a,np.zeros((17,10)),4)))==1


def test_task_replay_refuses_unknown_intent_and_preserves_work(tmp_path):
    request=task(tmp_path/'committed','fresh',CONFIG,4104,272)
    first=run_task(request);second=run_task(request)
    assert first==second and first['work']['transitions']==272
    uncertain=tmp_path/'uncertain';uncertain.mkdir();(uncertain/'intent.json').write_text('{}')
    with pytest.raises(RuntimeError,match='Uncertain'):run_task(task(uncertain,'fresh',CONFIG,4105,272))


def test_selection_ignores_zero_update_copies():
    def row(name,cost,updates):return dict(task=dict(directory=name,config=CONFIG),score=dict(cost=cost),work=dict(sac_updates=updates))
    assert selection([row('copy',1,0),row('trained',2,1)])['task']=='trained'
