import math
import numpy as np
import pytest
import torch
from hponas_rl_lqr_scale.reference import LQRSpec,oracle_report,riccati,sample_policy,linear_cost
from hponas_rl_lqr_scale.environment import ScaleLQREnv
from hponas_rl_lqr_scale.catalog import MatrixEncoder
from hponas_rl_lqr_scale.adapter import SACMember,Actor,digest
from hponas_rl_lqr_scale.experiments import CONFIG,CASES
from hponas_rl_lqr_scale.diagnostics import greedy_report,probes

@pytest.mark.parametrize('case',CASES)
def test_reference_feasible_and_independent(case):
    s=LQRSpec.from_case(case);r=oracle_report(s)
    assert r['oracle_attainable'] and r['condensed_cost_error']<1e-10
    if s.states==1:assert abs(r['optimal_cost']-.28666258546745116)<1e-12
    ref=riccati(s);score=sample_policy(lambda x,t:-x@ref['K'][t].T,spec=s,count=128)
    assert score['gap']<1e-25 and score['pathwise_identity_error']<1e-10
    assert np.linalg.matrix_rank(s.Q)==s.states
    assert np.linalg.matrix_rank(s.B)==min(s.states,s.actions)

@pytest.mark.parametrize('case',['s1a5','s1a10','s10a5','s10a10'])
def test_terminal_critic_values_gradients_and_environment(case):
    s=LQRSpec.from_case(case);enc=MatrixEncoder([8,8],s).double()
    obs=torch.randn(12,s.states+1,dtype=torch.float64);obs[:,-1]=1/30;u=torch.randn(12,s.actions,dtype=torch.float64,requires_grad=True)
    q=enc({'obs':obs,'actions':u})['encoder_out'][:,0];x=obs[:,:s.states];y=x@enc.A.T+u@enc.B.T
    expected=-x.square().sum(-1)-(u*(u@enc.R)).sum(-1)-s.gamma*(y.square().sum(-1)+enc.w.square().sum())
    assert (q-expected).abs().max()<1e-12
    g=torch.autograd.grad(q.sum(),u)[0];expected_g=-2*u@enc.R-2*s.gamma*y@enc.B
    assert (g-expected_g).abs().max()<1e-12
    if s.states==1:
        obs[:,-1]=.5;v=u.mean(-1,keepdim=True).expand_as(u)
        a=enc({'obs':obs,'actions':u})['encoder_out'][:,0];b=enc({'obs':obs,'actions':v})['encoder_out'][:,0]
        assert (b-a-(u-v).square().sum(-1)*float(enc.R[0,0])).abs().max()<1e-12
    env=ScaleLQREnv({'case':case});ob,_=env.reset(seed=19)
    for t in range(30):
        state=env._state.copy();act=np.zeros(s.actions,dtype=np.float32);nxt,reward,done,trunc,info=env.step(act)
        expected=-(state@state+(.99*(env._state@env._state) if t==29 else 0))
        assert abs(reward-expected)<1e-12 and done==(t==29) and not trunc
        assert env.observation_space.contains(nxt)
    with pytest.raises(ValueError):env.step(act)

@pytest.mark.parametrize('case',['s1a5','s1a10','s10a5','s10a10'])
def test_actor_pairing_symmetry_and_restore(case):
    a=SACMember(CONFIG,10991,case=case,method='matrix');b=SACMember(CONFIG,10991,case=case,method='symmetric')
    assert digest(Actor(a.module).state_dict())==digest(Actor(b.module).state_dict())
    assert torch.equal(a.torch_rng,b.torch_rng)
    for member in [a,b]:
        member.train(320);copy=SACMember.restore(member.state(),case=case)
        member.train(32);copy.train(32)
        assert SACMember.identity(member.state())==SACMember.identity(copy.state())
        for row in greedy_report(member):
            assert row['feasible']==(row['max_action_bound']<=1)
            assert (row['exact_cost'] is not None)==row['feasible']
            if row['feasible']:assert row['exact_cost']>=riccati(member.specification)['optimal_cost']-1e-12
    result=probes(b);assert result['odd_action_max_error']==0 and result['zero_action_max_abs']==0
    obs=torch.randn(16,b.specification.states+1);obs[:,-1]=.5;ref=obs.clone();ref[:,:-1]*=-1
    p=b.module.forward_inference({'obs':obs})['action_dist_inputs'];q=b.module.forward_inference({'obs':ref})['action_dist_inputs']
    mu,sd=p.chunk(2,-1);rm,rs=q.chunk(2,-1)
    assert torch.equal(mu,-rm) and torch.equal(sd,rs)
    traced=torch.jit.trace(Actor(b.module),obs);assert torch.equal(traced(obs),Actor(b.module)(obs))

@pytest.mark.parametrize('case',['s0a5','s1a11','s10a4','padded10','s5a5'])
def test_refuse_unreviewed_case(case):
    with pytest.raises(ValueError):LQRSpec.from_case(case)
