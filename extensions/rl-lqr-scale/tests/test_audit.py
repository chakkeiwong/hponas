from copy import deepcopy

import pytest
import torch

from hponas_rl_lqr_scale.audit import bound, verify_score, independent_cost
from hponas_rl_lqr_scale.experiments import bind
from hponas_rl_lqr_scale.reference import LQRSpec, sample_policy
from hponas_rl_lqr_scalar.scoring import action_rows


ACTUAL = dict(cost=0.3, se=0.00001, direct=0.301)
SAVED = dict(cost=0.3, gap_standard_error=0.00001, direct_rollout_mean=0.301)
FIELDS = [('cost', 'cost'), ('se', 'gap_standard_error'),
          ('direct', 'direct_rollout_mean')]


def test_score_reconstruction_accepts_matching_values():
    verify_score(ACTUAL, SAVED)


@pytest.mark.parametrize('actual,reported', FIELDS)
def test_score_reconstruction_rejects_corrupted_values(actual, reported):
    changed = deepcopy(SAVED)
    changed[reported] += 0.01
    with pytest.raises(ValueError, match='Score reconstruction mismatch'):
        verify_score(ACTUAL, changed)


@pytest.mark.parametrize('actual,reported', FIELDS)
def test_score_reconstruction_rejects_nonfinite_values(actual, reported):
    for value in [float('nan'), float('inf'), -float('inf')]:
        changed = deepcopy(SAVED)
        changed[reported] = value
        with pytest.raises(ValueError, match='Score reconstruction mismatch'):
            verify_score(ACTUAL, changed)
        changed = deepcopy(ACTUAL)
        changed[actual] = value
        with pytest.raises(ValueError, match='Score reconstruction mismatch'):
            verify_score(changed, SAVED)


def test_artifact_guard_rejects_changed_and_missing_bytes(tmp_path):
    path = tmp_path / 'artifact.json'
    path.write_text('{"score": 1}\n')
    expected = bind(path)
    bound(expected)
    path.write_text('{"score": 2}\n')
    with pytest.raises(ValueError, match='Artifact changed'):
        bound(expected)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        bound(expected)


@pytest.mark.parametrize('case', ['s1a5', 's10a10'])
def test_independent_direct_cost_uses_float64_action_arithmetic(case):
    spec = LQRSpec.from_case(case)

    class Actor(torch.nn.Module):
        def forward(self, obs):
            return torch.linspace(0.113, 0.319, spec.actions).expand(len(obs), -1)

    actor = Actor()
    stored = sample_policy(lambda x, t: action_rows(actor, x, t),
                           spec=spec, count=128, seed=10998)
    replay = independent_cost(actor, spec, 128, 10998)
    verify_score(replay, stored)
    assert abs(replay['direct'] - stored['direct_rollout_mean']) < 1e-12
