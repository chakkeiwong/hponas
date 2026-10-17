"""Rejected checkpoints preserve a live optimizer and give precise diagnostics."""

import copy

import pytest

from hponas import CMAESSearcher, Config, Knob, Result, SearchSpace
from hponas.schedulers import PASHAConfig, PASHAScheduler
from hponas.searchers_tpe import TPESearcher


def space():
    return SearchSpace([Knob("x", "continuous", (0., 1.)), Knob("y", "continuous", (0., 1.))])


@pytest.mark.parametrize("damage,message", [
    ("kind", "TPE checkpoint requires complete version 2 ask/tell ledger"),
    ("version", "TPE checkpoint requires complete version 2 ask/tell ledger"),
    ("config", "TPE sampler changed; checkpoint cannot be replayed exactly"),
    ("event", "Unknown TPE checkpoint event"),
])
def test_tpe_refuses_checkpoint_without_replacing_live_state(damage, message):
    target = TPESearcher(space(), seed=13)
    config = target.propose(1)[0]
    target.observe({"config": config, "value": 7})
    target.propose(1)
    original = target.state_dict()
    other = TPESearcher(space(), seed=29)
    other.propose(1)
    state = other.state_dict()
    if damage == "kind":
        state["kind"] = "other"
    elif damage == "version":
        state["schema_version"] = 1
    elif damage == "config":
        state["events"][0]["configs"][0]["x"] = -1
    else:
        state["events"].append({"action": "unknown"})
    with pytest.raises(ValueError) as exc:
        target.load_state_dict(state)
    assert str(exc.value) == message
    assert target.state_dict() == original
    reference = TPESearcher(space(), seed=13)
    reference.load_state_dict(original)
    assert target.propose(2) == reference.propose(2)


def test_tpe_restored_observations_do_not_alias_the_input_checkpoint():
    target = TPESearcher(space(), seed=13)
    config = target.propose(1)[0]
    target.observe({"config": config, "value": 7})
    state = target.state_dict()
    original = copy.deepcopy(state)
    target.load_state_dict(state)
    state["events"][1]["result"]["config"]["x"] = -100
    assert target.state_dict() == original


@pytest.mark.parametrize("damage,message", [
    ("kind", "Unsupported CMA-ES checkpoint"),
    ("schema_version", "Unsupported CMA-ES checkpoint"),
    ("versions", "CMA-ES checkpoint requires identical vendor versions"),
    ("space", "CMA-ES checkpoint search space differs"),
    ("config", "CMA-ES checkpoint does not replay exactly"),
    ("event", "Unknown CMA-ES checkpoint event"),
])
def test_cma_checkpoint_refusal_is_precise_and_atomic(damage, message):
    target = CMAESSearcher(space(), seed=13)
    target.suggest()
    original = target.get_state()
    state = copy.deepcopy(original)
    if damage == "config":
        state["events"][0]["config"]["x"] = -1
    elif damage == "event":
        state["events"].append({"action": "unknown"})
    else:
        state[damage] = "different"
    with pytest.raises(ValueError) as exc:
        target.set_state(state)
    assert str(exc.value) == message
    assert target.get_state() == original


def test_cma_input_checkpoint_cannot_mutate_restored_observation_metadata():
    target = CMAESSearcher(space(), seed=13)
    target.trials["a"] = target.suggest()
    target.observe(Result("a", 7, metadata={"trace": [1, 2]}))
    target.trials["pending"] = Config({"x": .2, "y": .3})
    state = target.get_state()
    original = copy.deepcopy(state)
    target.set_state(state)
    state["history"][0]["metadata"]["trace"].append(99)
    assert target.get_state() == original


@pytest.mark.parametrize("field,value,message", [
    ("policy", "pasha-progressive-v1", "Legacy PASHA promotion policy cannot resume as quantile-v2; retain its source or restart"),
    ("policy", "budget-only", "Budget-only checkpoint requires BudgetedASHAScheduler"),
    ("rungs", [1, 99], "Checkpoint rungs differ from PASHA configuration"),
    *[("current_top", value, "Invalid PASHA resource cap in checkpoint") for value in [True, 1.5, 0, 3]],
    *[("epsilon", value, "Invalid PASHA ranking tolerance in checkpoint") for value in [-.1, float("nan"), float("inf")]],
])
def test_pasha_invalid_checkpoint_keeps_the_live_scheduler(field, value, message):
    target = PASHAScheduler(PASHAConfig(r_min=1, r_max=4, eta=2))
    target.report("live", 1, 2)
    original = target.state_dict()
    state = copy.deepcopy(original)
    state[field] = value
    with pytest.raises(ValueError) as exc:
        target.load_state_dict(state)
    assert str(exc.value) == message
    assert target.state_dict() == original


@pytest.mark.parametrize("r_max", [1, 2, 4])
def test_pasha_recovery_accepts_minimum_valid_resource_cap(r_max):
    target = PASHAScheduler(PASHAConfig(r_min=1, r_max=r_max, eta=2))
    original = target.state_dict()
    target.load_state_dict(copy.deepcopy(original))
    assert target.state_dict() == original


def test_two_rung_pasha_cannot_restore_a_cap_below_its_initial_level():
    target = PASHAScheduler(PASHAConfig(r_min=1, r_max=2, eta=2))
    original = target.state_dict()
    invalid = copy.deepcopy(original)
    invalid["current_top"] = 0
    with pytest.raises(ValueError, match="^Invalid PASHA resource cap in checkpoint$"):
        target.load_state_dict(invalid)
    assert target.state_dict() == original


def test_tpe_callers_cannot_rewrite_accepted_proposals_or_observations():
    target = TPESearcher(space(), seed=13)
    proposed = target.propose(1)[0]
    submitted = {"config": proposed, "value": 7, "metadata": {"nested": [1]}}
    target.observe(submitted)
    original = target.state_dict()
    proposed["x"] = -100
    submitted["metadata"]["nested"].append(2)
    assert target.state_dict() == original


def test_tpe_exported_checkpoint_cannot_rewrite_optimizer_or_future_proposals():
    target = TPESearcher(space(), seed=13)
    config = target.propose(1)[0]
    target.observe({"config": config, "value": 7, "metadata": {"trace": [1, 2]}})
    target.propose(1)
    original = copy.deepcopy(target.state_dict())
    exported = target.state_dict()
    exported["events"][0]["configs"][0]["x"] = -100
    exported["events"][1]["result"]["metadata"]["trace"].append(99)
    exported["events"][2]["configs"].clear()
    assert target.state_dict() == original
    restored = TPESearcher(space(), seed=29)
    restored.load_state_dict(original)
    assert target.propose(3) == restored.propose(3)
