"""Ten physical states plus remaining-time observation, one control."""
import gymnasium as gym
import numpy as np
from .reference import LQRSpec

class FiniteLQR10Env(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self,config=None):
        self.specification=LQRSpec(**dict(config or {}));s=self.specification
        if s.states!=10 or s.horizon!=30: raise ValueError('Training contract is exactly ten states and thirty steps')
        self.action_space=gym.spaces.Box(-s.action_limit,s.action_limit,(1,),dtype=np.float32)
        bound=np.nextafter(np.float32(s.state_bound),np.float32(np.inf))
        self.observation_space=gym.spaces.Box(np.array([-bound]*10+[0.],np.float32),np.array([bound]*10+[1.],np.float32))
        self._state=np.zeros(10);self._step=s.horizon
    def _observe(self):
        return np.array([*self._state,(30-self._step)/30],dtype=np.float32)
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if options:raise ValueError('Initial law cannot be overridden')
        self._state=.5*(2*self.np_random.integers(2,size=10)-1);self._step=0
        return self._observe(),{}
    def step(self,action):
        s=self.specification;u=np.asarray(action)
        if self._step>=30:raise ValueError('Reset after terminal transition')
        if u.shape!=(1,) or not np.isfinite(u).all() or abs(float(u[0]))>s.action_limit:raise ValueError('Finite feasible action required')
        cost=float(self._state@self._state+.1*float(u[0])**2)
        w=s.noise_vector*(2*int(self.np_random.integers(2))-1)
        self._state=s.A@self._state+s.B[:,0]*float(u[0])+w;self._step+=1
        terminal=s.gamma*float(self._state@self._state) if self._step==30 else 0.
        return self._observe(),-(cost+terminal),self._step==30,False,dict(stage_cost=cost,discounted_terminal_cost=terminal)
