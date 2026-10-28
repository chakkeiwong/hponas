"""No-training structural and negative controls before the allocated smoke."""
from copy import deepcopy
import numpy as np
import pytest
import torch
from ray.rllib.algorithms.sac.torch.default_sac_torch_rl_module import DefaultSACTorchRLModule
from ray.rllib.core.columns import Columns
from ray.rllib.core.distribution.torch.torch_distribution import TorchSquashedGaussian
from hponas_rl_lqr.catalog import IndependentSACCatalog, BoundedDeterministicSquashedGaussian
from hponas_rl_lqr.environment import FiniteLQREnv
from hponas_rl_lqr.experiment import (roster, _model_config, parameter_audit,
                                    PortableActor, FiniteRosterSearcher, space_and_budget)


def make(row):
    env = FiniteLQREnv()
    module = DefaultSACTorchRLModule(observation_space=env.observation_space,
        action_space=env.action_space, model_config={**_model_config(row), 'twin_q': True},
        catalog_class=IndependentSACCatalog)
    module.make_target_networks()
    return module


def test_independent_actor_critic_coordinates_and_forward_shapes():
    records = []
    for row in roster()[::2]:
        module = make(row)
        audit = parameter_audit(module)
        obs = torch.zeros(7, 2)
        with torch.no_grad():
            output = module.forward_inference({Columns.OBS: obs})
            assert output[Columns.ACTION_DIST_INPUTS].shape == (7, 2)
            q = module.compute_q_values({Columns.OBS: obs, Columns.ACTIONS: torch.zeros(7, 1)})
            assert q.shape == (7,) and torch.isfinite(q).all()
            assert module.forward_target({Columns.OBS: obs, Columns.ACTIONS: torch.zeros(7, 1)}).shape == (7,)
            actor = PortableActor(module)
            expected = module.get_inference_action_dist_cls().from_logits(output[Columns.ACTION_DIST_INPUTS]).to_deterministic().sample()
            assert torch.equal(actor(obs), expected)
        records.append(audit['shapes'])
    actor_shapes = [{k: v for k, v in r.items() if k.startswith('pi')} for r in records]
    critic_shapes = [{k: v for k, v in r.items() if k.startswith('qf')} for r in records]
    assert actor_shapes[0] == actor_shapes[1] != actor_shapes[2] == actor_shapes[3]
    assert critic_shapes[0] == critic_shapes[2] != critic_shapes[1] == critic_shapes[3]


def test_deterministic_squash_and_training_distribution_unchanged():
    logits = torch.tensor([[-10., -1.], [0., -2.], [10., 1.]])
    fixed = BoundedDeterministicSquashedGaussian.from_logits(logits)
    upstream = TorchSquashedGaussian.from_logits(logits)
    deterministic = fixed.to_deterministic().sample()
    assert torch.max(torch.abs(deterministic)) <= 1.
    assert torch.max(torch.abs(upstream.to_deterministic().sample())) > 1.
    torch.manual_seed(31)
    actions, logp = fixed.rsample_and_logp()
    torch.manual_seed(31)
    old_actions, old_logp = upstream.rsample_and_logp()
    assert torch.equal(actions, old_actions) and torch.equal(logp, old_logp)


def test_nonfinite_model_refused():
    module = make(roster()[0])
    with torch.no_grad():
        next(module.pi.parameters()).fill_(float('nan'))
    with pytest.raises(AssertionError, match='Nonfinite'):
        parameter_audit(module)


def test_roster_checkpoint_rejects_changed_search():
    space, _ = space_and_budget()
    searcher = FiniteRosterSearcher(space, roster())
    saved = searcher.get_state()
    searcher.set_state(saved)
    changed = deepcopy(saved)
    changed['finite_roster'][0]['lr_recipe'] = 1
    with pytest.raises(ValueError, match='roster'):
        searcher.set_state(changed)
    assert len(roster()) == 8
