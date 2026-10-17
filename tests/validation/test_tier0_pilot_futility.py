"""Futility uses fixed sizing and irrevocable losses, never early success."""

import copy

import pytest

from validation.tier0_joint_pilot_sizing import optimistic_pilot_completion
from validation.tier0_phase_contracts import JOINT_SIZING_POLICY
from validation.tier0_rank_campaign import _pilot_search_futility


@pytest.mark.parametrize("count,last_possible,first_futile", [(46, 0, 1), (100, 2, 3), (200, 8, 9)])
def test_exact_pilot_futility_boundaries(count, last_possible, first_futile):
    assert not optimistic_pilot_completion(count, last_possible)["futile"]
    bound = optimistic_pilot_completion(count, first_futile)
    assert bound["futile"] and bound["optimistic_chosen_n"] is None
    assert bound["maximum_good_vectors"] == count - first_futile
    assert bound["certifies_acceptance"] is False


@pytest.mark.parametrize("count,bad", [(True, 0), (46, True), (4, 0), (46, -1), (46, 47), (46, 1.0)])
def test_invalid_loss_counts_are_not_futility_evidence(count, bad):
    with pytest.raises(ValueError):
        optimistic_pilot_completion(count, bad)


def test_rule_phase_and_reserved_seeds_bind_the_futility_shortcut():
    design = {"sizing_policy": copy.deepcopy(JOINT_SIZING_POLICY),
              "selected_counts": {"pilot": {"V04-T0": 46}},
              "seed_sets": {"pilot": list(range(46))}}
    assert _pilot_search_futility(design, "pilot", {"V04-T0": set()}) is None
    assert _pilot_search_futility(design, "pilot", {"V04-T0": {0}})["futile"]
    assert _pilot_search_futility(design, "confirmation", {"V04-T0": {0}}) is None
    with pytest.raises(ValueError, match="reservation"):
        _pilot_search_futility(design, "pilot", {"V04-T0": {46}})
    design["sizing_policy"]["method"] = "unreviewed_rule"
    assert _pilot_search_futility(design, "pilot", {"V04-T0": {0}}) is None
