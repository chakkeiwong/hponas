"""RLlib SAC catalog with independently configured actor and critic paths."""
from ray.rllib.algorithms.sac.sac_catalog import SACCatalog
from ray.rllib.core.columns import Columns
from ray.rllib.core.models.configs import MLPEncoderConfig, MLPHeadConfig, MultiStreamEncoderConfig
from ray.rllib.utils.annotations import override
from ray.rllib.core.distribution.torch.torch_distribution import TorchSquashedGaussian, TorchDeterministic


class BoundedDeterministicSquashedGaussian(TorchSquashedGaussian):
    """Keep upstream SAC sampling/loss; squash the mean for deterministic use.

    Ray 2.58's base to_deterministic returns the pre-tanh location. This adapter
    supplies the usual feasible tanh(mean) controller without changing training.
    """
    def to_deterministic(self):
        return TorchDeterministic(loc=self._squash(self.loc))


class IndependentSACCatalog(SACCatalog):
    """Separate actor encoder/head and critic stream/fusion/head dimensions.

    RLlib still supplies the SAC learner, twin critics, targets and optimizer
    updates. Only model construction is specialized for this finite benchmark.
    """

    def __init__(self, observation_space, action_space, model_config_dict, view_requirements=None):
        self.actor_hiddens = tuple(model_config_dict.get('actor_hiddens', model_config_dict.get('fcnet_hiddens', (32,))))
        self.critic_hiddens = tuple(model_config_dict.get('critic_hiddens', (32,)))
        self.critic_fusion_hiddens = tuple(model_config_dict.get('critic_fusion_hiddens', self.critic_hiddens))
        if not self.actor_hiddens or not self.critic_hiddens or not self.critic_fusion_hiddens:
            raise ValueError('Actor and critic hidden dimensions must be nonempty')
        super().__init__(observation_space, action_space, model_config_dict, view_requirements)
        # SACCatalog uses this field only when building the actor head. The
        # critic head is replaced below with an independent configuration.
        self.pi_and_qf_head_hiddens = list(self.actor_hiddens)
        self.qf_head_config = MLPHeadConfig(
            input_dims=(self.critic_fusion_hiddens[-1],),
            hidden_layer_dims=list(self.critic_hiddens),
            hidden_layer_activation=model_config_dict.get('critic_activation', 'tanh'),
            output_layer_activation='linear', output_layer_dim=1,
        )

    @override(SACCatalog)
    def _build_qf_encoder_continuous(self, framework):
        critic_activation = self._model_config_dict.get('critic_activation', 'tanh')
        obs = MLPEncoderConfig(
            input_dims=self.observation_space.shape,
            hidden_layer_dims=list(self.critic_hiddens),
            hidden_layer_activation=critic_activation,
        )
        action = MLPEncoderConfig(
            input_dims=self.action_space.shape,
            hidden_layer_dims=list(self.critic_hiddens),
            hidden_layer_activation=critic_activation,
        )
        self.qf_encoder_config = MultiStreamEncoderConfig(
            base_encoder_configs={Columns.OBS: obs, Columns.ACTIONS: action},
            hidden_layer_dims=list(self.critic_fusion_hiddens),
            hidden_layer_activation=critic_activation,
        )
        return self.qf_encoder_config.build(framework=framework)

    @override(SACCatalog)
    def get_action_dist_cls(self, framework):
        if framework != 'torch':
            raise ValueError('This companion supports Torch only')
        return BoundedDeterministicSquashedGaussian
