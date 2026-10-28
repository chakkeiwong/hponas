"""Actual layer lists for RLlib SAC; no duplicated encoder/head hidden layers."""
import torch
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.algorithms.sac.sac_catalog import SACCatalog
from ray.rllib.core.columns import Columns
from ray.rllib.core.distribution.torch.torch_distribution import TorchSquashedGaussian, TorchDeterministic
from ray.rllib.core.models.configs import MLPEncoderConfig, MLPHeadConfig
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from .environment import FiniteLQR5Env
from .search import validate


class BoundedGaussian(TorchSquashedGaussian):
    def to_deterministic(self):
        return TorchDeterministic(loc=self._squash(self.loc))


class StateActionEncoder(torch.nn.Module):
    def __init__(self, width, hiddens):
        super().__init__()
        self.encoder = MLPEncoderConfig(input_dims=(width,), hidden_layer_dims=list(hiddens),
                                       hidden_layer_activation='tanh').build(framework='torch')

    def forward(self, batch):
        return self.encoder({Columns.OBS: torch.cat((batch[Columns.OBS], batch[Columns.ACTIONS]), dim=-1)})


class LiteralSACCatalog(SACCatalog):
    def __init__(self, observation_space, action_space, model_config_dict, view_requirements=None):
        self.actor_hiddens = tuple(model_config_dict['actor_hiddens'])
        self.critic_hiddens = tuple(model_config_dict['critic_hiddens'])
        # Validate the shape contract even when a caller bypasses sac_config.
        validate({'actor_hiddens': self.actor_hiddens, 'critic_hiddens': self.critic_hiddens,
                  'actor_lr': .001, 'critic_lr': .001})
        config = dict(model_config_dict, fcnet_hiddens=list(self.actor_hiddens),
                      fcnet_activation='tanh', head_fcnet_hiddens=[], head_fcnet_activation='tanh')
        super().__init__(observation_space, action_space, config, view_requirements)
        self.qf_head_config = MLPHeadConfig(input_dims=(self.critic_hiddens[-1],),
            hidden_layer_dims=[], output_layer_dim=1, output_layer_activation='linear')

    def _build_qf_encoder_continuous(self, framework):
        if framework != 'torch':
            raise ValueError('Five-state companion supports Torch only')
        return StateActionEncoder(self.observation_space.shape[0]+self.action_space.shape[0], self.critic_hiddens)

    def get_action_dist_cls(self, framework):
        if framework != 'torch':
            raise ValueError('Five-state companion supports Torch only')
        return BoundedGaussian


def model_config(config):
    c = validate(config)
    return {'actor_hiddens': c['actor_hiddens'], 'critic_hiddens': c['critic_hiddens'],
            'fcnet_hiddens': c['actor_hiddens'], 'fcnet_activation': 'tanh',
            'head_fcnet_hiddens': [], 'head_fcnet_activation': 'tanh', 'twin_q': True}


def sac_config(config, seed=0):
    """Build a configuration; this function does not start Ray or train.

    Training controls are provisional. The old 64-update run was not reliable
    learning evidence; actual training requires prospective calibration.
    """
    c = validate(config)
    return (SACConfig().framework('torch')
        .environment(env=FiniteLQR5Env, clip_actions=False, normalize_actions=False)
        .rl_module(model_config=model_config(c), rl_module_spec=RLModuleSpec(catalog_class=LiteralSACCatalog))
        .env_runners(num_env_runners=0, num_envs_per_env_runner=1)
        .learners(num_learners=0, num_gpus_per_learner=0)
        .training(twin_q=True, gamma=.99, actor_lr=c['actor_lr'], critic_lr=c['critic_lr'],
                  alpha_lr=.0003, initial_alpha=.01, tau=.005, target_entropy='auto')
        .debugging(seed=seed))
