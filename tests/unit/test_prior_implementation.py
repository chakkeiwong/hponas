"""Exact finite law, censored draws, and latest-fidelity policy accounting."""
from copy import deepcopy
from fractions import Fraction as Q
import json
from math import comb
import pytest

from hponas.prior_sampling import FiniteGuardedPrior, guarded_probabilities
from hponas.prior_band import PriorBand


def test_guarded_masses_and_legacy_finite_pool_counterexample():
    assert guarded_probabilities([1, 1], [3, 1], Q(1, 2)) == (Q(5, 8), Q(3, 8))
    # For the prior branch alone the target A mass is 3/4; a two-draw pool gives 5/8.
    pool = sum(comb(2, k)*Q(3*k, 2+2*k)*Q(1, 2)**2 for k in range(3))
    assert pool == Q(5, 8) and pool != Q(3, 4)
    assert Q(1, 2)*pool + Q(1, 4) == Q(9, 16)  # also wrong after the guard


def test_pending_branch_preserves_exact_stream_through_json_recovery():
    baseline = FiniteGuardedPrior([1, 1], [3, 1], Q(1, 2), 0)
    expected = []
    while len(expected) < 20:
        value = baseline.advance(1000)
        if value is not None:
            expected.append(value)
    trial = FiniteGuardedPrior([1, 1], [3, 1], Q(1, 2), 0)
    observed, checkpoints = [], 0
    while len(observed) < 20:
        value = trial.advance(1)
        if value is not None:
            observed.append(value)
        state = json.loads(json.dumps(trial.state_dict()))
        restored = FiniteGuardedPrior([1, 1], [3, 1], Q(1, 2), 999)
        restored.load_state_dict(state)
        trial = restored
        checkpoints += int(state['pending_prior'])
    assert observed == expected and checkpoints > 0 and trial.state_dict() == baseline.state_dict()


@pytest.mark.parametrize('damage', [lambda s: s.update(law_sha256='0'*64), lambda s: s.update(proposal_count=-1),
                                    lambda s: s['rng_state'][1].__setitem__(0, -1), lambda s: s.update(extra=1)])
def test_prior_refuses_corrupt_checkpoint_without_mutating_live_state(damage):
    prior = FiniteGuardedPrior([1, 1], [3, 1], Q(1, 2), 7)
    prior.advance(1)
    before = prior.state_dict()
    bad = deepcopy(before)
    damage(bad)
    with pytest.raises(ValueError):
        prior.load_state_dict(bad)
    assert prior.state_dict() == before


def test_policy_activation_is_not_physical_cost_or_full_fidelity_incumbent_filter():
    band = PriorBand(rungs=[1, 3, 9], eta=3)
    band.observe('z-first', rung=1, value=0., work=100)
    band.observe('a-later', rung=9, value=0., work=9)
    assert band.incumbent() == 'z-first'  # stable insertion tie, not lexical
    assert band.resources() == 109 and band.reference_resources() == 10
    assert not band.can_activate() and band.bracket_cost == 21
    band.observe('third', rung=9, value=2., work=9)
    band.observe('fourth', rung=3, value=3., work=3)
    assert band.can_activate()
    band.begin('z-promoted', root='z-first', rung=3)
    assert band.incumbent() == 'a-later'
    band.observe('z-promoted', root='z-first', rung=3, value=-1., work=2)
    assert band.incumbent() == 'z-first' and band.reference_resources() == 24
    band.observe('failed', rung=9, value=None, work=9, status='failed')
    assert band.reference_resources() == 24 and band.resources() == 132
    state = json.loads(json.dumps(band.state_dict()))
    restored = PriorBand(rungs=[1, 3, 9], eta=3)
    restored.load_state_dict(state)
    assert restored.state_dict() == state
    bad = deepcopy(state)
    bad['rows']['z-first']['work'] += 1
    with pytest.raises(ValueError):
        restored.load_state_dict(bad)
    assert restored.state_dict() == state


def test_dynamic_fallback_and_zero_score_refusal():
    band = PriorBand(rungs=[1, 3, 9], eta=3)
    assert band.prior_to_incumbent_ratio(style='dynamic') == (Q(3, 4), Q(1, 4))
    for i in range(3):
        band.observe(str(i), rung=1, value=i, work=1)
    scores = {str(i): p for i, p in enumerate([(1, 4), (2, 2), (6, 1)])}
    assert band.prior_to_incumbent_ratio(style='dynamic', scores=scores) == (Q(13, 30), Q(17, 30))
    with pytest.raises(ValueError, match='Zero'):
        band.prior_to_incumbent_ratio(style='dynamic', scores={str(i): (0, 0) for i in range(3)})
    with pytest.raises(ValueError):
        band.sampling_weights(True)
