"""Exact on-policy control for small, finite, stationary policy/value models.

This workload enumerates expectations; it is not a PPO or simulator benchmark.
Substochastic transition rows represent termination. Rewards are immediate and
the policy is stationary over the declared finite horizon.
"""
from __future__ import annotations

import hashlib
import json
import math

import torch


class FiniteMDP:
    def __init__(self, initial, transitions, rewards, *, horizon, discount=1.0,
                 observations=None, rl_weight=None, policy_weight=1.0, value_weight=0.5):
        if type(horizon) is not int or not 1 <= horizon <= 64:
            raise ValueError('Horizon must be in [1,64]')
        if isinstance(discount, bool) or not math.isfinite(discount) or not 0 <= discount <= 1:
            raise ValueError('Discount must be in [0,1]')
        self.initial = torch.as_tensor(initial, dtype=torch.float64).clone()
        self.transitions = torch.as_tensor(transitions, dtype=torch.float64).clone()
        self.rewards = torch.as_tensor(rewards, dtype=torch.float64).clone()
        if self.rewards.ndim != 2:
            raise ValueError('Rewards must have state/action shape')
        self.states, self.actions = self.rewards.shape
        if not 1 <= self.states <= 64 or not 2 <= self.actions <= 16:
            raise ValueError('Finite workload size is outside the bounded contract')
        if (self.initial.shape != (self.states,)
                or self.transitions.shape != (self.states, self.actions, self.states)):
            raise ValueError('Initial or transition shape differs')
        self.observations = (torch.eye(self.states, dtype=torch.float64) if observations is None
                             else torch.as_tensor(observations, dtype=torch.float64).clone())
        if (self.observations.ndim != 2 or self.observations.shape[0] != self.states
                or not 1 <= self.observations.shape[1] <= 64):
            raise ValueError('Observation shape differs')
        if not all(torch.isfinite(x).all() for x in
                   (self.initial, self.transitions, self.rewards, self.observations)):
            raise ValueError('Nonfinite MDP data')
        if (torch.any(self.initial < 0) or torch.any(self.transitions < 0)
                or abs(float(self.initial.sum()) - 1) > 1e-12
                or torch.any(self.transitions.sum(-1) > 1 + 1e-12)):
            raise ValueError('Invalid initial or transition probability')
        self.horizon, self.discount = horizon, float(discount)
        for name, value in [('rl_weight', rl_weight), ('policy_weight', policy_weight),
                            ('value_weight', value_weight)]:
            if name == 'rl_weight' and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('Loss coefficients must be finite and nonnegative')
        self.rl_weight, self.policy_weight, self.value_weight = rl_weight, policy_weight, value_weight

    @property
    def return_bounds(self):
        """Conservative analytic return range, including zero after termination."""
        mass = sum(self.discount**step for step in range(self.horizon))
        return min(0.0, float(self.rewards.min()))*mass, max(0.0, float(self.rewards.max()))*mass

    @property
    def contract(self):
        return {'kind': 'finite_stationary_mdp_v1', 'initial': self.initial.tolist(),
                'transitions': self.transitions.tolist(), 'rewards': self.rewards.tolist(),
                'observations': self.observations.tolist(), 'horizon': self.horizon,
                'discount': self.discount,
                'coefficients': {'rl': self.rl_weight, 'policy': self.policy_weight,
                                 'value_squared': self.value_weight,
                                 'rl_none_means': 'one minus imitation schedule weight'},
                'imitation': 'KL(teacher||student) plus half squared teacher-value error',
                'occupancy': 'normalized undiscounted student occupancy, detached for imitation gradient',
                'rl': 'negative exact finite-horizon discounted return',
                'work_unit': 'one full finite-expectation gradient update'}

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.contract, sort_keys=True,
                                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    def components(self, student, teacher, imitation_weight):
        if (isinstance(imitation_weight, bool) or not math.isfinite(imitation_weight)
                or not 0 <= imitation_weight <= 1):
            raise ValueError('Imitation weight must be in [0,1]')
        outputs = student(self.observations)
        with torch.no_grad():
            targets = teacher(self.observations)
        expected_shape = (self.states, self.actions + 1)
        if outputs.shape != expected_shape or targets.shape != expected_shape:
            raise ValueError('Policy/value output shape differs from MDP')
        if not torch.isfinite(outputs).all() or not torch.isfinite(targets).all():
            raise ValueError('Nonfinite policy/value output')
        log_student = torch.log_softmax(outputs[:, :self.actions], dim=-1)
        log_teacher = torch.log_softmax(targets[:, :self.actions], dim=-1)
        probability = log_student.exp()
        transition = torch.einsum('sa,san->sn', probability, self.transitions)
        reward = (probability * self.rewards).sum(-1)
        distribution = self.initial
        occupancy = torch.zeros_like(distribution)
        expected_return = outputs.new_zeros(())
        for step in range(self.horizon):
            occupancy = occupancy + distribution
            expected_return = expected_return + self.discount ** step * distribution @ reward
            distribution = distribution @ transition
        weights = (occupancy / occupancy.sum()).detach()
        policy_kl = (weights * (log_teacher.exp() * (log_teacher - log_student)).sum(-1)).sum()
        value_error = (weights * (outputs[:, -1] - targets[:, -1]).square()).sum() / 2
        rl_weight = 1 - imitation_weight if self.rl_weight is None else self.rl_weight
        loss = imitation_weight * (self.policy_weight * policy_kl + 2 * self.value_weight * value_error) - rl_weight * expected_return
        if not torch.isfinite(loss):
            raise ValueError('Nonfinite distillation objective')
        return {'loss': loss, 'policy_kl': policy_kl, 'value_error': value_error,
                'return': expected_return, 'occupancy': occupancy.detach()}
