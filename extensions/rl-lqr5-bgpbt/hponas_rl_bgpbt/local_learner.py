"""Explicit local device placement for upstream SAC without Ray auto-init."""
import torch
from ray.rllib.algorithms.sac.torch.sac_torch_learner import SACTorchLearner


class AssignedDeviceSACLearner(SACTorchLearner):
    def __init__(self, *, assigned_device, **kwargs):
        self.assigned_device=torch.device(assigned_device)
        if str(self.assigned_device) not in ('cpu','cuda:0'):
            raise ValueError('One executor-assigned device required')
        super().__init__(**kwargs)
        if self.config.num_learners or self.config.num_gpus_per_learner:
            raise ValueError('Standalone learner cannot request Ray-managed resources')

    def _make_module(self):
        # TorchLearner's earlier CPU setup avoids Ray AIR device discovery.
        # This hook precedes module tensors, lazy alpha and all optimizer state.
        self._device=self.assigned_device
        if self._learner_connector is not None:
            self._learner_connector=self.config.build_learner_connector(
                input_observation_space=None,input_action_space=None,device=self._device)
        return super()._make_module()
