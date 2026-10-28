import ray
import torch
from hponas_rl_bgpbt.adapter import SACMember,digest
from hponas_rl_bgpbt.local_learner import AssignedDeviceSACLearner
from hponas_rl_lqr5.catalog import sac_config
from hponas_rl_lqr5.environment import FiniteLQR5Env


def test_assigned_device_preserves_upstream_construction_without_ray(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Ray startup forbidden')
    monkeypatch.setattr(ray,'init',forbidden)
    c=dict(actor_hiddens=[8,12],critic_hiddens=[12,8],actor_lr=.001,critic_lr=.002)
    member=SACMember(c,17)
    torch.manual_seed(17)
    config=sac_config(c,17).learners(num_learners=0,num_gpus_per_learner=0)
    config.training(train_batch_size_per_learner=128,n_step=1,target_network_update_freq=0)
    learner=AssignedDeviceSACLearner(config=config,assigned_device='cpu',
        module_spec=config.get_multi_rl_module_spec(env=FiniteLQR5Env()))
    learner.build()
    assert digest(learner.module['default_policy'].state_dict())==digest(member.module.state_dict())
    assert not ray.is_initialized()
    assert str(learner.curr_log_alpha['default_policy'].device)=='cpu'
    assert set(dict(learner.get_optimizers_for_module('default_policy')))=={'policy','qf','qf_twin','alpha'}
