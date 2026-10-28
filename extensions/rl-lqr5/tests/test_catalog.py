import numpy as np
import torch
from ray.rllib.algorithms.sac.torch.default_sac_torch_rl_module import DefaultSACTorchRLModule
from ray.rllib.core.columns import Columns

from hponas_rl_lqr5.catalog import LiteralSACCatalog, model_config, sac_config
from hponas_rl_lqr5.environment import FiniteLQR5Env


def make(config):
    env = FiniteLQR5Env()
    module = DefaultSACTorchRLModule(observation_space=env.observation_space,
        action_space=env.action_space, model_config=model_config(config), catalog_class=LiteralSACCatalog)
    module.make_target_networks()
    return module


def linears(*modules):
    return [(m.in_features, m.out_features) for root in modules for m in root.modules()
            if isinstance(m, torch.nn.Linear)]


def test_all_depth_pairs_actual_hidden_layers_independent_parameters_and_targets():
    for actor_depth in (2, 3, 4):
        for critic_depth in (2, 3, 4):
            for widths in ([8, 37, 64, 16], [64, 8, 13, 64]):
                actor = widths[:actor_depth]; critic = list(reversed(widths))[:critic_depth]
                config = dict(actor_hiddens=actor, critic_hiddens=critic,
                              actor_lr=.000173, critic_lr=.002731)
                module = make(config)
                actor_layers = linears(module.pi_encoder, module.pi)
                critic_layers = linears(module.qf_encoder, module.qf)
                assert actor_layers == list(zip([6]+actor, actor+[2]))
                assert critic_layers == list(zip([7]+critic, critic+[1]))
                assert linears(module.qf_twin_encoder, module.qf_twin) == critic_layers
                assert linears(module.target_qf_encoder, module.target_qf) == critic_layers
                groups = [(module.pi_encoder, module.pi), (module.qf_encoder, module.qf),
                          (module.qf_twin_encoder, module.qf_twin),
                          (module.target_qf_encoder, module.target_qf),
                          (module.target_qf_twin_encoder, module.target_qf_twin)]
                pointers = [{p.data_ptr() for m in group for p in m.parameters()} for group in groups]
                assert all(not pointers[i]&pointers[j] for i in range(5) for j in range(i))
                batch = {Columns.OBS: torch.randn(7, 6), Columns.ACTIONS: torch.zeros(7, 1)}
                logits = module.forward_inference(batch)[Columns.ACTION_DIST_INPUTS]
                assert logits.shape == (7, 2)
                action = module.get_inference_action_dist_cls().from_logits(logits).to_deterministic().sample()
                assert action.shape == (7, 1) and torch.all(torch.abs(action) <= 1)
                assert module.compute_q_values(batch).shape == (7,)
                assert module.forward_target(batch).shape == (7,)
                assert torch.isfinite(module.compute_q_values(batch)).all()


def test_rates_reach_actual_sac_configuration_without_grid_quantization():
    row = dict(actor_hiddens=[8, 16], critic_hiddens=[13, 37, 64], actor_lr=.000173, critic_lr=.002731)
    config = sac_config(row, seed=19)
    assert config.actor_lr == row['actor_lr'] and config.critic_lr == row['critic_lr']
    assert config.env is FiniteLQR5Env and config.seed == 19 and config.gamma == .99
    assert config.model_config['actor_hiddens'] == [8, 16]
    assert config.model_config['critic_hiddens'] == [13, 37, 64]
    assert config.model_config['head_fcnet_hiddens'] == []


def test_parameter_range_from_actual_modules():
    counts = []
    for widths in ([8, 8], [64]*4):
        module = make(dict(actor_hiddens=widths, critic_hiddens=widths, actor_lr=.001, critic_lr=.001))
        actor = sum(p.numel() for m in (module.pi_encoder, module.pi) for p in m.parameters())
        critic = sum(p.numel() for m in (module.qf_encoder, module.qf) for p in m.parameters())
        counts.append((actor, critic, actor+2*critic, sum(p.numel() for p in module.parameters())))
    assert counts == [(146, 145, 436, 726), (13058, 13057, 39172, 65286)]
