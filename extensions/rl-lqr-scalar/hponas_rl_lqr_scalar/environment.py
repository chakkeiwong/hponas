"""Scalar control with one/three actuators and an irrelevant-state diagnostic."""
import gymnasium as gym
import numpy as np
from .reference import LQRSpec

class ScalarLQREnv(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self,config=None):
        self.specification=LQRSpec(**dict(config or {}));s=self.specification
        if s!=LQRSpec(case=s.case):raise ValueError('Fixed scalar diagnostic training contract required')
        self.action_space=gym.spaces.Box(-s.action_limit,s.action_limit,(s.actions,),dtype=np.float32)
        bound=np.nextafter(np.float32(s.state_bound),np.float32(np.inf))
        self.observation_space=gym.spaces.Box(np.array([-bound]*s.states+[0.],np.float32),np.array([bound]*s.states+[1.],np.float32))
        self._state=np.zeros(s.states);self._step=s.horizon
    def _observe(self):
        return np.array([*self._state,(self.specification.horizon-self._step)/self.specification.horizon],dtype=np.float32)
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if options:raise ValueError('Initial law cannot be overridden')
        s=self.specification;self._state=s.initial_scale*(2*self.np_random.integers(2,size=10)-1)[:s.states];self._step=0
        return self._observe(),{}
    def step(self,action):
        s=self.specification;u=np.asarray(action,dtype=np.float64)
        if self._step>=s.horizon:raise ValueError('Reset after terminal transition')
        if u.shape!=(s.actions,) or not np.isfinite(u).all() or (abs(u)>s.action_limit).any():raise ValueError('Finite feasible action required')
        cost=float(self._state@s.Q@self._state+u@s.R@u)
        w=s.noise_vector*(2*int(self.np_random.integers(2))-1)
        self._state=s.A@self._state+s.B@u+w;self._step+=1
        terminal=s.gamma*float(self._state@s.Q@self._state) if self._step==s.horizon else 0.
        return self._observe(),-(cost+terminal),self._step==s.horizon,False,dict(stage_cost=cost,discounted_terminal_cost=terminal)
