from copy import deepcopy
import numpy as np
import pytest
import torch
from ray.rllib.core.columns import Columns
from hponas_rl_lqr_scalar.adapter import SACMember,Actor
from hponas_rl_lqr_scalar.transfer import distill
from hponas_rl_lqr_scalar.scoring import action_rows
from hponas_rl_lqr_scalar.tasks import run_task,task
from hponas_rl_lqr_scalar.study_v2 import selection
CONFIG=dict(actor_hiddens=[8,12],critic_hiddens=[12,8],actor_lr=.001,critic_lr=.002)

@pytest.fixture(scope='module',params=['scalar1','scalar3','padded3'])
def trained(request):
    m=SACMember(CONFIG,5101,case=request.param);m.train(320);return m.state()

def test_real_actor_gaussian_and_twin_critic_shapes(trained):
    m=SACMember.restore(trained);d=m.actions
    assert m.observation.shape==(m.specification.states+1,) and len(m.replay[0][1])==d
    assert set(m.counters()['adam_steps'].values())=={16}
    obs=torch.zeros(4,m.specification.states+1);act=torch.zeros(4,d)
    logits=m.module.forward_inference({Columns.OBS:obs})[Columns.ACTION_DIST_INPUTS]
    assert logits.shape==(4,2*d)
    actor=Actor(m.module);actions=actor(obs)
    assert actions.shape==(4,d) and (abs(actions)<=1).all()
    first=[p for p in m.module.qf_encoder.parameters() if p.ndim==2][0]
    assert first.shape[1]==m.specification.states+1+d
    batch={Columns.OBS:obs,Columns.ACTIONS:act}
    for encoder,head in [(m.module.qf_encoder,m.module.qf),(m.module.qf_twin_encoder,m.module.qf_twin)]:
        q=m.module._qf_forward_train_helper(batch,encoder,head);assert q.numel()==4
    assert next(m.module.qf_encoder.parameters()).data_ptr()!=next(m.module.qf_twin_encoder.parameters()).data_ptr()

def test_exact_recovery_and_wrong_dimension_refusal(trained,tmp_path):
    a=SACMember.restore(trained);identity=a.save(tmp_path/'checkpoint.pt');b=SACMember.restore(tmp_path/'checkpoint.pt',case=a.case)
    assert b.identity(b.state())==identity
    a.train(32);b.train(32);assert a.identity(a.state())==b.identity(b.state())
    with pytest.raises(ValueError,match='mismatch'):SACMember.restore(trained,case='scalar1' if a.case!='scalar1' else 'scalar3')
    wrong=deepcopy(trained);wrong['contract']['B'][0][0]=.9
    with pytest.raises(ValueError,match='mismatch'):SACMember.restore(wrong)

def test_changed_architecture_transfer_and_action_export(trained,tmp_path):
    t=SACMember.restore(trained);identity=t.identity(t.state())
    c=dict(CONFIG,actor_hiddens=[12,8,8],critic_hiddens=[8,8,8,8])
    s,r=distill(t,c,5102,16);s.train(16)
    assert s.actions==t.actions and r['teacher_unchanged'] and t.identity(t.state())==identity
    assert set(s.counters()['adam_steps'].values())=={4}
    child=t.compatible_copy(dict(CONFIG,actor_lr=.0003),5103);child.train(16)
    assert child.actions==t.actions and child.counters()['rates']['policy']==.0003
    result=s.score(tmp_path/'actor.pt');a=torch.jit.load(str(tmp_path/'actor.pt'))
    assert a(torch.zeros(4,t.specification.states+1)).shape==(4,t.actions)
    assert result['paths']==1024 and result['evaluation_seed']==1060001
    values=action_rows(a,np.zeros((17,t.specification.states)),4);assert np.array_equal(values,np.tile(values[0],(17,1)))
    other=SACMember(c,5102,case='scalar1' if t.case!='scalar1' else 'scalar3')
    with pytest.raises(ValueError,match='environment mismatch'):distill(t,c,5102,1,other)

@pytest.mark.parametrize('m',['scalar1','scalar3','padded3'])
def test_task_replay_and_checkpoint_dimension_isolation(tmp_path,m):
    request=task(tmp_path/'committed','fresh',CONFIG,5104,272,case=m)
    first=run_task(request);assert first==run_task(request) and first['work']['transitions']==272
    wrong=task(tmp_path/'wrong','train',CONFIG,5104,0,input_path=tmp_path/'committed/checkpoint.pt',case='scalar1' if m!='scalar1' else 'scalar3')
    with pytest.raises(ValueError,match='mismatch'):run_task(wrong)
    uncertain=tmp_path/'uncertain';uncertain.mkdir();(uncertain/'intent.json').write_text('{}')
    with pytest.raises(RuntimeError,match='Uncertain'):run_task(task(uncertain,'fresh',CONFIG,5105,272,case=m))

def test_selection_ignores_untrained_copies():
    def row(name,cost,updates):return dict(task=dict(directory=name,config=CONFIG),score=dict(cost=cost),work=dict(sac_updates=updates))
    assert selection([row('copy',1,0),row('trained',2,1)])['task']=='trained'
