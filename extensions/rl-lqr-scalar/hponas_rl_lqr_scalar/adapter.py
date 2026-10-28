"""Explicit sampling/replay around the upstream RLlib SAC Torch learner.

Only trusted local checkpoints are supported. No oracle data enter training.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random

import numpy as np
import torch
from ray.rllib.core.columns import Columns
from ray.rllib.core import DEFAULT_MODULE_ID
from ray.rllib.policy.sample_batch import SampleBatch, MultiAgentBatch
from ray.rllib.utils.metrics import NUM_ENV_STEPS_SAMPLED_LIFETIME
from ray.rllib.utils.schedules.scheduler import Scheduler

from .catalog import sac_config
from .environment import ScalarLQREnv
from .reference import LQRSpec, sample_policy
from hponas_rl_lqr5.search import validate
from hponas_rl_bgpbt.work import charged_training
from .scoring import action_rows

MID = DEFAULT_MODULE_ID
ENV_SCHEMA = 3
BATCH = 128
WARMUP = 256
CAPACITY = 32768


def digest(value):
    """Stable scientific identity independent of serialization container bytes."""
    h = hashlib.sha256()
    def visit(x):
        if torch.is_tensor(x):
            visit(x.detach().cpu().numpy())
        elif isinstance(x, np.ndarray):
            h.update(str(x.dtype).encode()); h.update(str(x.shape).encode()); h.update(x.tobytes())
        elif isinstance(x, dict):
            for k in sorted(x, key=str):
                visit(str(k)); visit(x[k])
        elif isinstance(x, (tuple, list)):
            h.update(b'[')
            for v in x: visit(v)
            h.update(b']')
        else:
            h.update(repr(x).encode()); h.update(b'\0')
    visit(value)
    return h.hexdigest()


def cpu_copy(x):
    if torch.is_tensor(x): return x.detach().cpu().clone()
    if isinstance(x, dict): return {k: cpu_copy(v) for k, v in x.items()}
    if isinstance(x, list): return [cpu_copy(v) for v in x]
    if isinstance(x, tuple): return tuple(cpu_copy(v) for v in x)
    return deepcopy(x)


class Actor(torch.nn.Module):
    def __init__(self, module):
        super().__init__()
        self.encoder = deepcopy(module.pi_encoder).cpu()
        self.head = deepcopy(module.pi).cpu()

    def forward(self, obs):
        logits = self.head(self.encoder({'obs': obs})['encoder_out'])
        return torch.tanh(logits.chunk(2, dim=-1)[0])


class SACMember:
    def __init__(self, config, seed, device='cpu', case='scalar3'):
        self.specification = LQRSpec(case=case)
        self.case = self.specification.case
        self.actions = self.specification.actions
        self.config = validate(config)
        self.seed, self.device = int(seed), str(device)
        if self.device not in ('cpu', 'cuda:0'):
            raise ValueError('One isolated CPU or visible GPU required')
        torch.set_num_threads(1)
        torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
        if device == 'cuda:0':
            if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
                raise ValueError('GPU worker requires exactly one visible CUDA device')
            torch.cuda.manual_seed(seed)
        self.env = ScalarLQREnv({"case":self.case})
        config_obj = sac_config(self.config, seed, self.case)
        config_obj.learners(num_learners=0, num_gpus_per_learner=0)
        config_obj.training(train_batch_size_per_learner=BATCH, n_step=1,
                            target_network_update_freq=0)
        if device=='cpu':
            self.learner = config_obj.build_learner(env=self.env)
        else:
            from hponas_rl_bgpbt.local_learner import AssignedDeviceSACLearner
            self.learner=AssignedDeviceSACLearner(config=config_obj,assigned_device=device,
                module_spec=config_obj.get_multi_rl_module_spec(env=self.env))
            self.learner.build()
        self.module = self.learner.module[MID].unwrapped()
        if str(next(self.module.parameters()).device) != self.device:
            raise ValueError('Learner device differs from worker assignment')
        self.rng = np.random.default_rng(seed + 17)
        self.observation, _ = self.env.reset(seed=seed + 31)
        self.replay = []
        self.transitions = self.updates = self.distill_updates = 0
        self._capture_rng()

    def _capture_rng(self):
        self.torch_rng = torch.get_rng_state().clone()
        self.cuda_rng = torch.cuda.get_rng_state().cpu() if self.device != 'cpu' else None
        self.python_rng = random.getstate()
        self.numpy_rng = np.random.get_state()

    def _activate_rng(self):
        torch.set_rng_state(self.torch_rng)
        if self.device != 'cpu' and self.cuda_rng is not None:
            torch.cuda.set_rng_state(self.cuda_rng)
        random.setstate(self.python_rng); np.random.set_state(self.numpy_rng)

    def fork_random_streams(self, seed):
        """Preserve donor state, fork future sampling for an exploited child."""
        torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
        if self.device != 'cpu': torch.cuda.manual_seed(seed)
        self.rng = np.random.default_rng(seed+17)
        self.env.np_random.bit_generator.state = np.random.default_rng(seed+31).bit_generator.state
        self.seed = int(seed); self._capture_rng()

    def optimizers(self):
        return dict(self.learner.get_optimizers_for_module(MID))

    def set_rates(self, actor_lr, critic_lr):
        config = validate(dict(self.config, actor_lr=actor_lr, critic_lr=critic_lr))
        for name, optimizer in self.optimizers().items():
            rate = config['actor_lr'] if name == 'policy' else config['critic_lr'] if name.startswith('qf') else .0003
            scheduler = Scheduler(fixed_value_or_schedule=rate, framework='torch',
                                  device=self.learner._device)
            self.learner._optimizer_lr_schedules[optimizer] = scheduler
            for group in optimizer.param_groups: group['lr'] = rate
        self.config = config
        self.learner.config.actor_lr = actor_lr
        self.learner.config.critic_lr = critic_lr

    def counters(self):
        steps = {}
        for name, opt in self.optimizers().items():
            values = [int(s['step'].item()) for s in opt.state.values() if 'step' in s]
            if len(set(values)) > 1: raise ValueError('Unequal Adam steps within optimizer')
            steps[name] = values[0] if values else 0
        return {'transitions': self.transitions, 'sac_updates': self.updates,
                'distillation_updates': self.distill_updates, 'adam_steps': steps,
                'rates': {n: float(o.param_groups[0]['lr']) for n, o in self.optimizers().items()},
                'alpha': float(self.learner.curr_log_alpha[MID].detach().exp().cpu().item()),
                'replay_size': len(self.replay), 'device': self.device}

    def _update(self):
        if len(self.replay) < BATCH: raise ValueError('Insufficient training replay')
        rows = [self.replay[int(i)] for i in self.rng.integers(len(self.replay), size=BATCH)]
        obs, actions, rewards, next_obs, dones = zip(*rows)
        batch = SampleBatch({Columns.OBS: np.asarray(obs, np.float32),
            Columns.ACTIONS: np.asarray(actions, np.float32),
            Columns.REWARDS: np.asarray(rewards, np.float32),
            Columns.NEXT_OBS: np.asarray(next_obs, np.float32),
            Columns.TERMINATEDS: np.asarray(dones, bool),
            'weights': np.ones(BATCH, np.float32), 'n_step': np.ones(BATCH, np.float32)})
        self.learner.update(batch=MultiAgentBatch({MID: batch}, BATCH),
                            timesteps={NUM_ENV_STEPS_SAMPLED_LIFETIME: self.transitions})
        self.updates += 1

    @charged_training
    def train(self, transitions, extra_updates=0):
        if type(transitions) is not int or transitions < 0 or transitions % 4:
            raise ValueError('Nonnegative multiples of four transitions required')
        if type(extra_updates) is not int or extra_updates < 0:
            raise ValueError('Nonnegative explicit replay update count required')
        self._activate_rng()
        for _ in range(transitions):
            if self.transitions < WARMUP:
                action = self.rng.uniform(-1, 1, size=self.actions).astype(np.float32)
            else:
                with torch.no_grad():
                    obs = torch.as_tensor(self.observation[None], device=self.device)
                    logits = self.module.forward_exploration({Columns.OBS: obs})[Columns.ACTION_DIST_INPUTS]
                    dist = self.module.get_exploration_action_dist_cls().from_logits(logits)
                    action = dist.sample().cpu().numpy()[0]
            next_obs, reward, done, truncated, _ = self.env.step(action)
            if truncated: raise ValueError('Unexpected truncation in finite task')
            self.replay.append((self.observation.copy(), action.copy(), reward, next_obs.copy(), done))
            if len(self.replay) > CAPACITY: self.replay.pop(0)
            self.observation = next_obs
            self.transitions += 1
            if done: self.observation, _ = self.env.reset()
            if self.transitions > WARMUP and self.transitions % 4 == 0: self._update()
        for _ in range(extra_updates): self._update()
        if not all(torch.isfinite(p).all().item() for p in self.module.parameters()):
            raise ValueError('Nonfinite SAC parameters')
        if not torch.isfinite(self.learner.curr_log_alpha[MID]).all():
            raise ValueError('Nonfinite SAC temperature')
        self._capture_rng()
        return self.counters()

    def score(self, export=None):
        actor = Actor(self.module).eval()
        if export is not None:
            traced = torch.jit.trace(actor, torch.zeros(1, self.specification.states+1), check_trace=True)
            torch.jit.save(traced, str(export))
        result = sample_policy(lambda x,t: action_rows(actor,x,t), spec=self.specification)
        return {k: v for k, v in result.items() if not isinstance(v, np.ndarray)}

    def state(self):
        return cpu_copy({'schema': ENV_SCHEMA, 'contract': self.specification.contract(), 'role': 'training',
            'config': self.config, 'seed': self.seed, 'learner': self.learner.get_state(),
            # Full Torch state explicitly includes target networks even if RLlib filters them.
            'module': self.module.state_dict(), 'alpha': self.learner.curr_log_alpha[MID],
            'target_clock': dict(self.learner.last_update_ts_by_mid),
            'replay': self.replay, 'rng': self.rng.bit_generator.state,
            'env': {'state': self.env._state, 'step': self.env._step,
                    'rng': self.env.np_random.bit_generator.state, 'observation': self.observation},
            'torch_rng': self.torch_rng, 'cuda_rng': self.cuda_rng,
            'python_rng': self.python_rng, 'numpy_rng': self.numpy_rng,
            'transitions': self.transitions, 'updates': self.updates,
            'distill_updates': self.distill_updates})

    @staticmethod
    def identity(state):
        return digest({k: v for k, v in state.items() if k != 'learner'} | {
            'optimizers': state['learner']['optimizer'],
            'weights_seq_no': state['learner']['weights_seq_no']})

    def save(self, path):
        path = Path(path); temp = path.with_suffix('.partial')
        state = self.state(); torch.save(state, temp)
        with temp.open('rb') as f: os.fsync(f.fileno())
        temp.replace(path)
        return self.identity(state)

    @classmethod
    def restore(cls, state_or_path, device='cpu', case=None):
        state = (torch.load(state_or_path, map_location='cpu', weights_only=False)
                 if isinstance(state_or_path, (str, Path)) else deepcopy(state_or_path))
        saved_case = state['contract'].get('case')
        spec = LQRSpec(case=saved_case)
        if (case is not None and saved_case != case) or state['schema'] != ENV_SCHEMA or state['contract'] != spec.contract() or state['role'] != 'training':
            raise ValueError('Checkpoint environment/role/schema mismatch')
        member = cls(state['config'], state['seed'], device, case=saved_case)
        learner_state = deepcopy(state['learner'])
        learner_state['weights_seq_no'] = 0  # Force restoration, even into an existing sequence.
        member.learner.set_state(learner_state)
        member.learner._weights_seq_no = state['learner']['weights_seq_no']
        member.module.load_state_dict(state['module'], strict=True)
        with torch.no_grad(): member.learner.curr_log_alpha[MID].copy_(state['alpha'].to(device))
        member.learner.last_update_ts_by_mid.update(state['target_clock'])
        member.replay = state['replay']; member.rng.bit_generator.state = state['rng']
        member.env._state = state['env']['state']; member.env._step = state['env']['step']
        member.env.np_random.bit_generator.state = state['env']['rng']
        member.observation = state['env']['observation']
        for key in ('torch_rng', 'python_rng', 'numpy_rng', 'transitions', 'updates', 'distill_updates'):
            setattr(member, key, state[key])
        if device != 'cpu' and state['cuda_rng'] is not None: member.cuda_rng = state['cuda_rng']
        member.set_rates(state['config']['actor_lr'], state['config']['critic_lr'])
        return member

    def compatible_copy(self, config, seed):
        config = validate(config)
        if any(config[k] != self.config[k] for k in ('actor_hiddens', 'critic_hiddens')):
            raise ValueError('Changed shapes require distillation')
        child = self.restore(self.state(), self.device, case=self.case)
        child.set_rates(config['actor_lr'], config['critic_lr']); child.fork_random_streams(seed)
        return child
