import numpy as np
import pytest
from hponas_rl_lqr_multi.reference import LQRSpec,riccati,oracle_report,linear_cost,exhaustive_paths,evaluate_paths,sample_policy,sample_paths
from hponas_rl_lqr_multi.environment import FiniteLQR10Env

@pytest.mark.parametrize('m',[2,3,4,5])
def test_reference_independent_moments_and_each_coordinate_feasible(m):
    s=LQRSpec(actions=m);r=oracle_report(s)
    assert np.array(r['K']).shape==(30,m,10)
    assert np.array(r['S']).shape==(30,m,m)
    assert np.array(r['per_time_coordinate_bounds']).shape==(30,m)
    assert r['oracle_attainable'] and r['max_oracle_action_bound']<1
    assert abs(r['optimal_cost']-r['oracle_linear_moment_cost'])<1e-10
    assert r['zero_action_cost']>r['optimal_cost']>0
    assert r['spec']['path_count']==2**40

@pytest.mark.parametrize('m',[2,3,4,5])
def test_exhaustive_vector_nonlinear_regret_includes_cross_terms(m):
    s=LQRSpec(states=m,actions=m,horizon=3);x,w=exhaustive_paths(s);ref=riccati(s)
    assert np.max(abs(ref['S'][0]-np.diag(np.diag(ref['S'][0]))))>0
    policy=lambda x,t:.3*np.tanh(x+.1*t)
    r=evaluate_paths(policy,x,w,s,return_arrays=True)
    assert abs(r['direct_rollout_mean']-r['cost'])<1e-12
    delta=policy(x,0)+x@ref['K'][0].T
    assert np.allclose(r['regret_by_time'][:,0],np.einsum('bi,ij,bj->b',delta,ref['S'][0],delta),atol=1e-14)
    optimum=evaluate_paths(lambda x,t:-x@ref['K'][t].T,x,w,s)
    assert optimum['gap']==pytest.approx(0,abs=1e-25)
    zero=evaluate_paths(lambda x,t:np.zeros((len(x),m)),x,w,s)
    assert zero['cost']==pytest.approx(linear_cost(np.zeros_like(ref['K']),s),abs=1e-12)

@pytest.mark.parametrize('m',[2,3,4,5])
def test_every_actuator_dynamics_and_terminal_discount(m):
    for j in range(m):
        e=FiniteLQR10Env({'actions':m});z=FiniteLQR10Env({'actions':m})
        e.reset(seed=91);z.reset(seed=91);u=np.zeros(m);u[j]=.4
        e.step(u);z.step(np.zeros(m));expected=np.zeros(10);expected[j]=.4
        assert np.allclose(e._state-z._state,expected,atol=1e-14)
    obs,_=e.reset(seed=91);assert obs.shape==(11,) and e.action_space.shape==(m,)
    total=stages=0.
    for t in range(30):
        obs,reward,done,truncated,info=e.step(np.full(m,.1,np.float32))
        total-=.99**t*reward;stages+=.99**t*info['stage_cost'];assert done==(t==29) and not truncated
    assert total==pytest.approx(stages+.99**30*(e._state@e._state),abs=1e-11)
    with pytest.raises(ValueError,match='Reset'):e.step(np.zeros(m))

def test_dimension_and_training_contract_refusals():
    for values in [dict(actions=True),dict(actions=0),dict(actions=11),dict(gamma=float('nan'))]:
        with pytest.raises(ValueError):LQRSpec(**values)
    for values in [dict(actions=1),dict(actions=6),dict(actions=2,gamma=.9),dict(states=5)]:
        with pytest.raises(ValueError):FiniteLQR10Env(values)
    with pytest.raises(ValueError):sample_policy(lambda x,t:np.zeros((len(x),1)),count=8)
    with pytest.raises(ValueError):sample_policy(lambda x,t:np.full((len(x),2),2.),count=8)

def test_validation_holdout_independent_and_uncertainty_explicit():
    s=LQRSpec();a=sample_paths(s,1024,1050001);b=sample_paths(s,1024,1050002)
    assert all(np.array_equal(x,y) for x,y in zip(a,sample_paths(s,1024,1050001)))
    assert not np.array_equal(a[0],b[0]) and not np.array_equal(a[1],b[1])
    r=sample_policy(lambda x,t:np.zeros((len(x),2)))
    assert not r['exact_policy_expectation'] and r['gap_standard_error']>0
    with pytest.raises(ValueError):exhaustive_paths(s)
