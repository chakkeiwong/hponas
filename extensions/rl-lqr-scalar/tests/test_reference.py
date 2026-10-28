import numpy as np
import pytest
from hponas_rl_lqr_scalar.reference import LQRSpec,CASES,riccati,oracle_report,linear_cost,exhaustive_paths,evaluate_paths,sample_policy,sample_paths
from hponas_rl_lqr_scalar.environment import ScalarLQREnv

@pytest.mark.parametrize('case',CASES)
def test_matched_reference_and_feasible_optimum(case):
    s=LQRSpec(case=case);r=oracle_report(s);baseline=oracle_report(LQRSpec(case='scalar1'))
    assert np.array(r['K']).shape==(30,s.actions,s.states)
    assert r['oracle_attainable'] and r['max_oracle_action_bound']<1
    assert abs(r['optimal_cost']-r['oracle_linear_moment_cost'])<1e-10
    assert abs(r['optimal_cost']-baseline['optimal_cost'])<1e-12
    assert abs(r['zero_action_cost']-baseline['zero_action_cost'])<1e-12
    assert r['zero_action_cost']>r['optimal_cost']>0
    if case=='padded3':assert np.array_equal(riccati(s)['K'][:,:,1:],np.zeros((30,3,9)))

@pytest.mark.parametrize('case',CASES)
def test_exhaustive_nonlinear_vector_regret_and_decomposition(case):
    s=LQRSpec(case=case,horizon=3);x,w=exhaustive_paths(s);ref=riccati(s)
    def policy(x,t):return .2*np.tanh(x[:,:1]+np.arange(s.actions)[None,:]*.2+.1*t)
    r=evaluate_paths(policy,x,w,s)
    assert abs(r['direct_rollout_mean']-r['cost'])<1e-11
    assert r['gap']==pytest.approx(r['effective_gap']+r['nullspace_gap'],abs=1e-11)
    optimum=evaluate_paths(lambda x,t:-x@ref['K'][t].T,x,w,s)
    assert optimum['gap']==pytest.approx(0,abs=1e-25)
    if s.actions==3:assert r['nullspace_gap']>0
    else:assert r['nullspace_gap']==0

@pytest.mark.parametrize('case',['scalar3','padded3'])
def test_nullspace_actions_change_cost_not_active_state(case):
    s=LQRSpec(case=case,horizon=3);x,w=exhaustive_paths(s);k=riccati(s)['K'];null=np.array([.1,-.1,0.])
    r=evaluate_paths(lambda x,t:-x@k[t].T+null,x,w,s)
    expected=.1*(null@null)*sum(s.gamma**t for t in range(3))
    assert r['gap']==pytest.approx(expected,abs=1e-12)
    assert r['nullspace_gap']==pytest.approx(expected,abs=1e-12)
    assert r['effective_gap']<1e-25
    assert np.linalg.matrix_rank(s.B)==1

@pytest.mark.parametrize('case',CASES)
def test_training_environment_contract_and_terminal_discount(case):
    e=ScalarLQREnv({'case':case});s=e.specification;obs,_=e.reset(seed=91)
    assert obs.shape==(s.states+1,) and e.action_space.shape==(s.actions,)
    total=stages=0.
    for t in range(30):
        obs,reward,done,truncated,info=e.step(np.full(s.actions,.1,np.float32))
        total-=.99**t*reward;stages+=.99**t*info['stage_cost'];assert done==(t==29) and not truncated
    assert total==pytest.approx(stages+.99**30*(e._state@s.Q@e._state),abs=1e-11)
    with pytest.raises(ValueError,match='Reset'):e.step(np.zeros(s.actions))

def test_identical_active_sampling_and_known_policy_across_cases():
    scalar=LQRSpec(case='scalar1');base=sample_paths(scalar,1024,1060002)
    costs=[];envs=[ScalarLQREnv({'case':c}) for c in CASES]
    for e in envs:e.reset(seed=91)
    for t in range(30):
        for e in envs:e.step(np.full(e.specification.actions,.1/np.sqrt(e.specification.actions)))
        assert max(e._state[0] for e in envs)-min(e._state[0] for e in envs)<1e-14
    for case in CASES:
        s=LQRSpec(case=case);x,w=sample_paths(s,1024,1060002)
        assert np.array_equal(x[:,0],base[0][:,0]) and np.array_equal(w[:,:,0],base[1][:,:,0])
        r=evaluate_paths(lambda x,t:-.4*x[:,:1]*s.b[None,:],x,w,s);costs.append(r['cost'])
    assert max(costs)-min(costs)<1e-12

def test_refuse_changed_training_contract_and_bad_actions():
    for values in [dict(case='unknown'),dict(horizon=0),dict(gamma=float('nan'))]:
        with pytest.raises(ValueError):LQRSpec(**values)
    for values in [dict(case='scalar3',horizon=4),dict(case='scalar1',gamma=.9)]:
        with pytest.raises(ValueError):ScalarLQREnv(values)
    with pytest.raises(ValueError):sample_policy(lambda x,t:np.zeros((len(x),1)),count=8)
    with pytest.raises(ValueError):sample_policy(lambda x,t:np.full((len(x),3),2.),count=8)

def test_validation_holdout_distinct_and_uncertainty_explicit():
    s=LQRSpec();a=sample_paths(s,1024,1060001);b=sample_paths(s,1024,1060002)
    assert not np.array_equal(a[0],b[0]) and not np.array_equal(a[1],b[1])
    r=sample_policy(lambda x,t:np.zeros((len(x),s.actions)))
    assert not r['exact_policy_expectation'] and r['gap_standard_error']>0
    with pytest.raises(ValueError):exhaustive_paths(s)
