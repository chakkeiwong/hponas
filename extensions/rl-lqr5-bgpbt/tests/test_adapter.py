from copy import deepcopy
import numpy as np
import pytest
import torch

from hponas_rl_bgpbt.adapter import SACMember, digest
from hponas_rl_bgpbt.transfer import distill

CONFIG={'actor_hiddens':[8,12],'critic_hiddens':[12,8], 'actor_lr':.001,'critic_lr':.002}


@pytest.fixture(scope='module')
def trained():
    m=SACMember(CONFIG,17); m.train(320)
    return m.state()


def test_actual_sac_four_optimizers_targets_and_entropy(trained):
    m=SACMember.restore(trained)
    assert set(m.counters()['adam_steps'])=={'policy','qf','qf_twin','alpha'}
    assert set(m.counters()['adam_steps'].values())=={16}
    assert m.counters()['alpha'] != pytest.approx(.01,abs=1e-8)
    assert any(not torch.equal(p,q) for a,b in m.module.get_target_network_pairs()
               for p,q in zip(a.parameters(),b.parameters()))


def test_restore_and_exact_cpu_continuation(trained,tmp_path):
    a=SACMember.restore(trained); identity=a.save(tmp_path/'checkpoint.pt')
    b=SACMember.restore(tmp_path/'checkpoint.pt')
    assert SACMember.identity(b.state())==identity
    a.train(32); b.train(32)
    assert SACMember.identity(a.state())==SACMember.identity(b.state())
    assert a.score()==b.score()


def test_compatible_copy_changes_both_persistent_rates(trained):
    a=SACMember.restore(trained); before=SACMember.identity(a.state())
    c=dict(CONFIG,actor_lr=.00071,critic_lr=.00023)
    b=a.compatible_copy(c,50)
    assert digest(a.state()['module'])==digest(b.state()['module'])
    assert a.counters()['adam_steps']==b.counters()['adam_steps']
    assert digest(a.replay)==digest(b.replay)
    assert digest(a.torch_rng)!=digest(b.torch_rng)
    b.train(16)
    assert b.counters()['rates']['policy']==pytest.approx(c['actor_lr'])
    assert b.counters()['rates']['qf']==pytest.approx(c['critic_lr'])
    assert b.counters()['rates']['qf_twin']==pytest.approx(c['critic_lr'])
    assert SACMember.identity(a.state())==before
    with pytest.raises(ValueError,match='distillation'):
        a.compatible_copy(dict(c,actor_hiddens=[8,8,8]),51)


def test_changed_shape_distillation_teacher_and_target_contract(trained):
    teacher=SACMember.restore(trained); identity=SACMember.identity(teacher.state())
    config=dict(CONFIG,actor_hiddens=[16,8,8],critic_hiddens=[8,16,8,8])
    student,receipt=distill(teacher,config,88,16)
    assert sum(receipt['final_losses']) < sum(receipt['initial_losses'])
    assert receipt['steps']==16 and receipt['gradient_components']==48
    assert SACMember.identity(teacher.state())==identity
    assert student.config==config
    assert set(student.counters()['adam_steps'].values())=={0}
    for a,b in student.module.get_target_network_pairs():
        assert digest(a.state_dict())==digest(b.state_dict())
    assert student.counters()['alpha']==teacher.counters()['alpha']
    student.train(16)
    assert set(student.counters()['adam_steps'].values())=={4}


def test_role_and_environment_mismatch_refused(trained):
    for field,value in [('role','confirmation'),('contract',{})]:
        wrong=deepcopy(trained); wrong[field]=value
        with pytest.raises(ValueError,match='mismatch'): SACMember.restore(wrong)


def test_exact_score_identity_and_export(trained,tmp_path):
    m=SACMember.restore(trained); result=m.score(tmp_path/'actor.pt')
    assert result['paths']==8192
    assert result['gap']>=-result['tolerance']
    assert result['identity_error']<=result['tolerance']
    actor=torch.jit.load(str(tmp_path/'actor.pt'))
    assert torch.isfinite(actor(torch.zeros(3,6))).all()


def test_finite_law_inference_enforces_shared_history_actions():
    from hponas_rl_bgpbt.scoring import action_rows
    from hponas_rl_lqr5.reference import enumerate_policy
    # Deliberate position-sensitive rounding witness: a duplicated history must
    # never choose a different action merely because of its future-noise row.
    class PositionSensitive(torch.nn.Module):
        def forward(self,obs):
            return .1*obs[:,:1]+(torch.arange(len(obs))%2).float()[:,None]*1e-6
    actor=PositionSensitive()
    states=np.zeros((17,5))
    assert len(np.unique(action_rows(actor,states,0)))==1
    report=enumerate_policy(lambda x,t: action_rows(actor,x,t))
    assert report['identity_error']<=report['tolerance']
