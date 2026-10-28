import pytest
from hponas_rl_lqr_repair.adapter import SACMember,Actor,digest
from hponas_rl_lqr_repair.experiments import BASE,ROOT,read
from hponas_rl_lqr_repair.transfer import distill,critic_adapt

@pytest.mark.parametrize('method',['plain','informed'])
def test_transfer_preserves_donor_and_freezes_actor(method):
    r=next(r for r in read(BASE/'learner-result.json')['rows'] if r['method']==method and r['seed']==10801)
    donor=SACMember.restore(ROOT/r['checkpoint']['path']);original=SACMember.identity(donor.state())
    config=dict(donor.config,actor_hiddens=[16,16],critic_hiddens=[16,16])
    child,receipt=distill(donor,config,10893,steps=4,adapt_steps=4)
    assert receipt['teacher_unchanged'] and len(receipt['after_adaptation'])==7
    assert receipt['adaptation']['actor_unchanged'] and receipt['adaptation']['alpha_unchanged']
    assert SACMember.identity(donor.state())==original
    restored=SACMember.restore(child.state());before=digest(Actor(restored.module).state_dict())
    critic_adapt(child,2);critic_adapt(restored,2)
    assert digest(Actor(child.module).state_dict())==before
    assert SACMember.identity(child.state())==SACMember.identity(restored.state())
