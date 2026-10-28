"""Gymnasium interface to the independently specified finite stochastic LQR."""
import gymnasium as gym
import numpy as np

from .reference import LQRSpec


class FiniteLQREnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, config=None):
        self.specification = LQRSpec(**dict(config or {}))
        s = self.specification
        self.action_space = gym.spaces.Box(-s.action_limit, s.action_limit, (1,), dtype=np.float32)
        bound = np.nextafter(np.float32(s.state_bound), np.float32(np.inf))
        self.observation_space = gym.spaces.Box(
            np.array([-bound, 0.], dtype=np.float32), np.array([bound, 1.], dtype=np.float32))
        self._state = 0.
        self._step = s.horizon

    def _observe(self):
        return np.asarray([self._state, (self.specification.horizon-self._step)/self.specification.horizon],
                          dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options:
            raise ValueError('The benchmark initial-state law cannot be overridden')
        self._step = 0
        self._state = self.specification.initial*(2*int(self.np_random.integers(2))-1)
        return self._observe(), {}

    def step(self, action):
        s = self.specification
        action = np.asarray(action)
        if self._step >= s.horizon:
            raise ValueError('Episode ended; reset before stepping')
        if action.shape != (1,) or not np.isfinite(action).all() or abs(float(action[0])) > s.action_limit:
            raise ValueError('One finite feasible action is required; no clipping')
        u = float(action[0])
        cost = s.q*self._state**2+s.r*u*u
        noise = s.noise*(2*int(self.np_random.integers(2))-1)
        self._state = s.a*self._state+s.b*u+noise
        self._step += 1
        terminated = self._step == s.horizon
        terminal = s.gamma*s.terminal_q*self._state**2 if terminated else 0.
        return self._observe(), -(cost+terminal), terminated, False, {
            'stage_cost': cost, 'discounted_terminal_cost': terminal, 'noise': noise}
