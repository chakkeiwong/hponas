"""Deploy a frozen learned linear controller only with a verified action envelope.

No Riccati coefficients are used to build gains. The certificate describes the
specified initial/noise law and mathematical real-arithmetic dynamics, not an
arbitrary external environment. A failed envelope must not be hidden by clipping.
"""
from dataclasses import dataclass
import numpy as np
import torch
from .reference import LQRSpec,linear_cost

@dataclass
class LearnedController:
    gains: np.ndarray
    spec: LQRSpec
    critic: str

    def __post_init__(self):
        self.gains=np.array(self.gains,dtype=np.float64,copy=True)
        if self.gains.shape!=(self.spec.horizon,self.spec.actions,self.spec.states) or not np.isfinite(self.gains).all():
            raise ValueError('Finite time-indexed gains matching the contract required')
        self.gains.setflags(write=False)

    @classmethod
    def from_member(cls,member,critic='q1'):
        if critic not in ('q1','q2'):raise ValueError('Explicit twin critic required; no oracle selection')
        s=member.specification;e=member.module.qf_encoder if critic=='q1' else member.module.qf_twin_encoder
        times=torch.tensor([[(s.horizon-t)/s.horizon] for t in range(s.horizon)],dtype=torch.float32,device=member.device)
        with torch.no_grad():p,_=e.continuation(times)
        p=p.cpu().numpy().astype(float)
        gains=[np.linalg.solve(s.R+s.gamma*s.B.T@q@s.B,s.gamma*s.B.T@q@s.A) for q in p]
        return cls(np.asarray(gains),s,critic)

    def certificate(self):
        s=self.spec;coeff=s.initial_scale*np.eye(s.states);bounds=[]
        for k in self.gains:
            bounds.append(float(abs(k@coeff).sum(1).max()))
            coeff=np.column_stack(((s.A-s.B@k)@coeff,s.noise_vector))
        feasible=max(bounds)<=s.action_limit
        return dict(case=s.case,critic=self.critic,feasible=feasible,max_action_bound=max(bounds),per_time_action_bounds=bounds,
            exact_expected_cost=linear_cost(self.gains,s) if feasible else None,
            contract=s.contract(),scope='Mathematical controller and stated stochastic law; no general environment or floating-point deployment certification.')

    def __call__(self,states,time):
        if type(time) is not int or not 0<=time<self.spec.horizon:raise ValueError('Valid integer decision time required')
        x=np.asarray(states,dtype=np.float64)
        if x.ndim!=2 or x.shape[1]!=self.spec.states or not np.isfinite(x).all():raise ValueError('Finite state rows required')
        action=-x@self.gains[time].T
        if (abs(action)>self.spec.action_limit).any():raise ValueError('State outside controller action envelope; refusing silent clipping')
        return action

    def torch_module(self):
        if not self.certificate()['feasible']:raise ValueError('Cannot export uncertified bounded controller')
        return LinearActor(self.gains)

class LinearActor(torch.nn.Module):
    def __init__(self,gains):
        super().__init__();self.register_buffer('gains',torch.tensor(gains,dtype=torch.float64));self.horizon=len(gains)
    def forward(self,obs):
        # [physical states, remaining-time fraction]; clamped integer indexing
        # handles only float32 clock rounding, not out-of-contract physical states.
        t=torch.round(self.horizon*(1-obs[:,-1])).long().clamp(0,self.horizon-1)
        return -torch.bmm(self.gains[t],obs[:,:-1].double().unsqueeze(-1)).squeeze(-1)
