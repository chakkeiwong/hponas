"""Five coupled states and one bounded continuous control action."""
import gymnasium as gym
import numpy as np

from .reference import LQR5Spec


class FiniteLQR5Env(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, config=None):
        self.specification = LQR5Spec(**dict(config or {}))
        s = self.specification
        self.action_space = gym.spaces.Box(-s.action_limit, s.action_limit, (1,), dtype=np.float32)
        bound = np.nextafter(np.float32(s.state_bound), np.float32(np.inf))
        self.observation_space = gym.spaces.Box(
            np.array([-bound]*5+[0.], dtype=np.float32),
            np.array([bound]*5+[1.], dtype=np.float32))
        self._state = np.zeros(5); self._step = s.horizon

    def _observe(self):
        s = self.specification
        return np.array([*self._state, (s.horizon-self._step)/s.horizon], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options:
            raise ValueError('The initial law cannot be overridden')
        self._state = self.specification.initial_scale*(2*self.np_random.integers(2, size=5)-1)
        self._step = 0
        return self._observe(), {}

    def step(self, action):
        s = self.specification; action = np.asarray(action)
        if self._step >= s.horizon:
            raise ValueError('Episode ended; reset before stepping')
        if action.shape != (1,) or not np.isfinite(action).all() or abs(float(action[0])) > s.action_limit:
            raise ValueError('One finite feasible action required; no clipping')
        u = float(action[0]); cost = float(self._state@self._state+.1*u*u)
        noise = s.noise_vector*(2*int(self.np_random.integers(2))-1)
        self._state = s.A@self._state+s.B[:, 0]*u+noise
        self._step += 1
        done = self._step == s.horizon
        terminal = s.gamma*float(self._state@self._state) if done else 0.
        return self._observe(), -(cost+terminal), done, False, {
            'stage_cost': cost, 'discounted_terminal_cost': terminal, 'noise': noise.copy()}
