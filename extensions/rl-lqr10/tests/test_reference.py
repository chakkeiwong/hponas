import numpy as np
import pytest
from hponas_rl_lqr10.reference import (LQRSpec,riccati,oracle_report,linear_cost,
    sample_paths,exhaustive_paths,evaluate_paths,sample_policy)
from hponas_rl_lqr10.environment import FiniteLQR10Env


def test_ten_state_horizon_thirty_reference_and_global_action_feasibility():
    s=LQRSpec();r=oracle_report(s)
    assert r['spec']['states']==10 and r['spec']['horizon']==30
    assert r['spec']['path_count']==1099511627776
    assert r['oracle_attainable'] and r['max_oracle_action_bound']<1
    assert abs(r['oracle_linear_moment_cost']-r['optimal_cost'])<1e-10
    assert r['zero_action_cost']>r['optimal_cost']>0


def test_small_exhaustive_regret_identity_with_nonlinear_policy():
    s=LQRSpec(states=2,horizon=3);x,w=exhaustive_paths(s)
    r=evaluate_paths(lambda x,t:.3*np.tanh(x[:,:1]+.1*t),x,w,s)
    assert abs(r['direct_rollout_mean']-r['cost'])<1e-12
    assert abs(sum(r['per_time_gap'])-r['gap'])<1e-12
    assert r['pathwise_identity_error']<r['tolerance']


def test_oracle_sampled_advantage_zero_and_zero_policy_matches_moments():
    s=LQRSpec(states=2,horizon=3);x,w=exhaustive_paths(s);k=riccati(s)['K']
    r=evaluate_paths(lambda x,t:-x@k[t].T,x,w,s)
    z=evaluate_paths(lambda x,t:np.zeros((len(x),1)),x,w,s)
    assert r['gap']==pytest.approx(0,abs=1e-30)
    assert z['cost']==pytest.approx(linear_cost(np.zeros_like(k),s),abs=1e-12)


def test_iid_seeds_are_reproducible_and_distinct():
    s=LQRSpec();a=sample_paths(s,1024,1030001);b=sample_paths(s,1024,1030002)
    assert all(np.array_equal(x,y) for x,y in zip(a,sample_paths(s,1024,1030001)))
    assert not np.array_equal(a[0],b[0]) and not np.array_equal(a[1],b[1])
    assert a[0].shape==(1024,10) and a[1].shape==(1024,30,10)
    with pytest.raises(ValueError,match='Exhaustive'):exhaustive_paths(s)


def test_episode_terminal_discount_and_observation():
    e=FiniteLQR10Env();obs,_=e.reset(seed=91)
    assert obs.shape==(11,) and obs[-1]==1
    total=0.;stages=0.
    for t in range(30):
        obs,reward,done,truncated,info=e.step(np.array([0.],np.float32))
        total-=.99**t*reward;stages+=.99**t*info['stage_cost']
        assert done==(t==29) and not truncated
    expected=stages+.99**30*(e._state@e._state)
    assert total==pytest.approx(expected,abs=1e-12) and obs[-1]==0
    with pytest.raises(ValueError,match='Reset'):e.step(np.array([0.]))


def test_infeasible_actions_and_invalid_dimensions_refuse():
    for values in [dict(states=True),dict(horizon=0),dict(gamma=float('nan'))]:
        with pytest.raises(ValueError):LQRSpec(**values)
    with pytest.raises(ValueError):sample_policy(lambda x,t:np.full((len(x),1),2.),count=8)
    with pytest.raises(ValueError):FiniteLQR10Env(dict(states=5))


def test_sampling_uncertainty_not_mislabeled_exact():
    r=sample_policy(lambda x,t:np.zeros((len(x),1)),count=1024)
    assert not r['exact_policy_expectation'] and r['gap_standard_error']>0
    assert len(r['per_time_gap'])==30 and r['gap_normal95'][0]<=r['gap']<=r['gap_normal95'][1]
