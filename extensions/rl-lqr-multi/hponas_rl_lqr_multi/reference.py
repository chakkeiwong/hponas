"""Polynomial-time exact LQR reference and sampled nonlinear-policy regret."""
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
import math
import numpy as np


@dataclass(frozen=True)
class LQRSpec:
    states: int = 10
    actions: int = 2
    horizon: int = 30
    gamma: float = .99
    initial_scale: float = .5
    noise_scale: float = .025
    action_limit: float = 1.

    def __post_init__(self):
        if type(self.states) is not int or not 1 <= self.states <= 64:
            raise ValueError('Integer state count 1--64 required')
        if type(self.actions) is not int or not 1 <= self.actions <= self.states:
            raise ValueError('Integer action count 1--states required')
        if type(self.horizon) is not int or not 1 <= self.horizon <= 128:
            raise ValueError('Integer horizon 1--128 required')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
               for v in (self.gamma,self.initial_scale,self.noise_scale,self.action_limit)):
            raise ValueError('Finite specification required')
        if not (0 < self.gamma <= 1 and self.initial_scale > 0 and self.noise_scale >= 0 and self.action_limit > 0):
            raise ValueError('Invalid LQR specification')

    @property
    def A(self): return .8*np.eye(self.states)+.12*np.roll(np.eye(self.states),1,axis=0)
    @property
    def B(self): return np.eye(self.states)[:,:self.actions]
    @property
    def Q(self): return np.eye(self.states)
    @property
    def R(self): return .1*np.eye(self.actions)
    @property
    def noise_vector(self): return self.noise_scale*(-1.)**np.arange(self.states)
    @property
    def state_bound(self):
        bound=value=self.initial_scale
        for _ in range(self.horizon):
            value=.92*value+self.action_limit+self.noise_scale
            bound=max(bound,value)
        return float(bound)

    def contract(self):
        return dict(states=self.states,actions=self.actions,horizon=self.horizon,gamma=self.gamma,
            A=self.A.tolist(),B=self.B.tolist(),Q=self.Q.tolist(),terminal_Q=self.Q.tolist(),R=self.R.tolist(),
            initial_scale=self.initial_scale,noise_vector=self.noise_vector.tolist(),action_limit=self.action_limit,
            noise_covariance_rank=int(self.noise_scale>0),initial_covariance_rank=self.states,
            path_count=2**(self.states+self.horizon),evaluation='sampled_regret_with_analytic_reference_v1')


@lru_cache(maxsize=16)
def riccati(spec=LQRSpec()):
    a,b,q,r,g=spec.A,spec.B,spec.Q,spec.R,spec.gamma
    p=np.empty((spec.horizon+1,spec.states,spec.states));p[-1]=q
    k=np.empty((spec.horizon,spec.actions,spec.states));s=np.empty((spec.horizon,spec.actions,spec.actions));c=np.zeros(spec.horizon+1)
    w=spec.noise_vector
    for t in reversed(range(spec.horizon)):
        s[t]=r+g*b.T@p[t+1]@b
        k[t]=np.linalg.solve(s[t],g*b.T@p[t+1]@a)
        p[t]=q+g*a.T@p[t+1]@a-k[t].T@s[t]@k[t]
        c[t]=g*(c[t+1]+w@p[t+1]@w)
    for x in (p,k,s,c):x.setflags(write=False)
    return dict(P=p,K=k,S=s,constant=c,optimal_cost=float(spec.initial_scale**2*np.trace(p[0])+c[0]))


def condensed_reference(spec=LQRSpec()):
    matrices=[];gains=[];d=spec.states;m=spec.actions
    for t in range(spec.horizon):
        n=spec.horizon-t
        powers=[np.linalg.matrix_power(spec.A,i) for i in range(n+1)]
        f=np.vstack(powers);g=np.zeros((d*(n+1),n*m))
        for i in range(1,n+1):
            for j in range(i):g[d*i:d*(i+1),m*j:m*(j+1)]=powers[i-1-j]@spec.B
        discounts=np.repeat(spec.gamma**np.arange(n+1),d)
        h=g.T@(discounts[:,None]*g)+np.kron(np.diag(spec.gamma**np.arange(n)),spec.R)
        cross=g.T@(discounts[:,None]*f);u=np.linalg.solve(h,cross)
        matrices.append(f.T@(discounts[:,None]*f)-cross.T@u);gains.append(u[:m])
    p=np.array(matrices+[np.eye(d)])
    cost=spec.initial_scale**2*np.trace(p[0])+math.fsum(spec.gamma**(t+1)*float(spec.noise_vector@p[t+1]@spec.noise_vector) for t in range(spec.horizon))
    return dict(P=p,K=np.array(gains),optimal_cost=float(cost))


def linear_cost(gains,spec=LQRSpec()):
    covariance=spec.initial_scale**2*np.eye(spec.states);cost=0.
    for t in range(spec.horizon):
        k=gains[t];cost+=spec.gamma**t*float(np.trace((spec.Q+k.T@spec.R@k)@covariance))
        closed=spec.A-spec.B@k
        covariance=closed@covariance@closed.T+np.outer(spec.noise_vector,spec.noise_vector)
    return cost+spec.gamma**spec.horizon*float(np.trace(spec.Q@covariance))


def oracle_report(spec=LQRSpec()):
    ref=riccati(spec);other=condensed_reference(spec)
    coefficients=spec.initial_scale*np.eye(spec.states);bounds=[];coordinate_bounds=[]
    for t in range(spec.horizon):
        row_bound=np.abs(ref['K'][t]@coefficients).sum(axis=1)
        coordinate_bounds.append(row_bound.tolist());bounds.append(float(row_bound.max()))
        coefficients=np.column_stack(((spec.A-spec.B@ref['K'][t])@coefficients,spec.noise_vector))
    feasible=max(bounds)<=spec.action_limit
    report=dict(spec=spec.contract(),optimal_cost=ref['optimal_cost'],
        zero_action_cost=linear_cost(np.zeros_like(ref['K']),spec),
        oracle_linear_moment_cost=linear_cost(ref['K'],spec),
        max_oracle_action_bound=max(bounds),per_time_oracle_action_bound=bounds,per_time_coordinate_bounds=coordinate_bounds,oracle_attainable=feasible,
        condensed_P_error=float(np.max(abs(ref['P']-other['P']))),
        condensed_K_error=float(np.max(abs(ref['K']-other['K']))),
        condensed_cost_error=abs(ref['optimal_cost']-other['optimal_cost']),
        K=ref['K'].tolist(),P=ref['P'].tolist(),S=ref['S'].tolist())
    if not feasible: raise ValueError('Unconstrained oracle is not certified attainable inside action bounds')
    if max(report['condensed_P_error'],report['condensed_K_error'],report['condensed_cost_error'])>1e-10:
        raise ValueError('Independent quadratic reference mismatch')
    return report


def sample_paths(spec,count,seed):
    if type(count) is not int or count<2: raise ValueError('At least two independent paths required')
    rng=np.random.default_rng(seed)
    initial=(2*rng.integers(2,size=(count,spec.states))-1)*spec.initial_scale
    noise=(2*rng.integers(2,size=(count,spec.horizon,1))-1)*spec.noise_vector
    return initial,noise


def exhaustive_paths(spec):
    if spec.states+spec.horizon>16: raise ValueError('Exhaustive diagnostic exceeds bounded size')
    signs=np.asarray(list(product((-1.,1.),repeat=spec.states+spec.horizon)))
    return signs[:,:spec.states]*spec.initial_scale,signs[:,spec.states:,None]*spec.noise_vector


def evaluate_paths(policy,initial,noise,spec=LQRSpec(),return_arrays=False):
    n=len(initial);ref=riccati(spec);x=initial.copy();cost=np.zeros(n);regret=np.zeros((n,spec.horizon));martingale=np.zeros(n)
    baseline=np.einsum('bi,ij,bj->b',x,ref['P'][0],x)+ref['constant'][0]
    for t in range(spec.horizon):
        u=np.asarray(policy(x.copy(),t),dtype=np.float64)
        if u.shape!=(n,spec.actions) or not np.isfinite(u).all() or (abs(u)>spec.action_limit).any():
            raise ValueError('One finite feasible vector action per state required')
        cost+=spec.gamma**t*(np.square(x).sum(1)+.1*np.square(u).sum(1))
        delta=u+x@ref['K'][t].T
        regret[:,t]=spec.gamma**t*np.einsum('bi,ij,bj->b',delta,ref['S'][t],delta)
        mean_next=x@spec.A.T+u@spec.B.T;w=noise[:,t]
        martingale+=spec.gamma**(t+1)*(2*np.einsum('bi,ij,bj->b',mean_next,ref['P'][t+1],w)
            +np.einsum('bi,ij,bj->b',w,ref['P'][t+1],w)-spec.noise_vector@ref['P'][t+1]@spec.noise_vector)
        x=mean_next+w
    cost+=spec.gamma**spec.horizon*np.square(x).sum(1);gaps=regret.sum(1)
    error=float(np.max(abs(cost-baseline-gaps-martingale)))
    tolerance=4096*spec.horizon*np.finfo(float).eps*max(1.,float(np.max(abs(cost))))
    if error>tolerance:raise ValueError('Pathwise quadratic accounting failed')
    gap=float(gaps.mean());se=float(gaps.std(ddof=1)/np.sqrt(n))
    result=dict(cost=ref['optimal_cost']+gap,optimal_cost=ref['optimal_cost'],gap=gap,gap_standard_error=se,
        gap_normal95=[max(0.,gap-1.959963984540054*se),gap+1.959963984540054*se],
        uncertainty='IID normal approximation conditional on frozen policy; not a finite-sample certificate',
        direct_rollout_mean=float(cost.mean()),direct_rollout_standard_error=float(cost.std(ddof=1)/np.sqrt(n)),
        per_time_gap=regret.mean(0).tolist(),paths=n,pathwise_identity_error=error,tolerance=tolerance,
        exact_policy_expectation=False,estimator='analytic_optimum_plus_mean_quadratic_advantage')
    if return_arrays:result.update(path_gaps=gaps,path_costs=cost,regret_by_time=regret)
    return result


def sample_policy(policy,spec=LQRSpec(),count=1024,seed=1050001,return_arrays=False):
    initial,noise=sample_paths(spec,count,seed)
    result=evaluate_paths(policy,initial,noise,spec,return_arrays)
    result['evaluation_seed']=seed
    return result
