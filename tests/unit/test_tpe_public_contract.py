"""Optuna reference behavior for mixed, conditional and logarithmic knobs."""

import copy
from unittest.mock import patch

import optuna
import pytest

from hponas.searchers_tpe import TPESearcher
from hponas.space import Knob, SearchSpace


def mixed_space():
    return SearchSpace([
        Knob("kind", "categorical", ["a", "b"]),
        Knob("optional", "continuous", (0.0, 1.0), condition=("kind", "a")),
        Knob("rate", "continuous", (1e-5, 0.1), transform="log"),
        Knob("depth", "ordinal", (1, 8)),
        Knob("tail", "continuous", (-1.0, 1.0)),
        Knob("second_rate", "continuous", (1e-3, 1.0), transform="log"),
        Knob("second_depth", "ordinal", (10, 20)),
        Knob("color", "categorical", ["red", "blue"]),
    ])


@pytest.mark.parametrize("seed", [None, 17])
def test_tpe_mixed_public_proposals_match_independent_optuna_ask_tell(seed):
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    searcher = TPESearcher(mixed_space()) if seed is None else TPESearcher(mixed_space(), seed=seed)
    reference = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=0 if seed is None else seed))
    kinds = set()
    for step in range(14):
        trial = reference.ask()
        kind = trial.suggest_categorical("kind", ["a", "b"])
        expected = {"kind": kind}
        kinds.add(kind)
        if kind == "a":
            expected["optional"] = trial.suggest_float("optional", 0.0, 1.0)
        expected.update(rate=trial.suggest_float("rate", 1e-5, 0.1, log=True),
                        depth=trial.suggest_int("depth", 1, 8),
                        tail=trial.suggest_float("tail", -1.0, 1.0))
        expected.update(second_rate=trial.suggest_float("second_rate", 1e-3, 1.0, log=True),
                        second_depth=trial.suggest_int("second_depth", 10, 20),
                        color=trial.suggest_categorical("color", ["red", "blue"]))
        actual, = searcher.propose(1)
        assert actual == expected
        value = expected["tail"] - expected["rate"] + step / 10
        searcher.observe({"config": actual, "value": value})
        reference.tell(trial, -value)
    assert kinds == {"a", "b"}
    saved = searcher.state_dict()
    restored = TPESearcher(mixed_space(), seed=93)
    restored.load_state_dict(saved)
    assert restored.propose(2) == searcher.propose(2)


def test_tpe_unknown_observation_is_refused_without_consuming_pending_asks():
    searcher = TPESearcher(mixed_space(), seed=9)
    searcher.propose(2)
    before = copy.deepcopy(searcher.state_dict())
    config = {"kind": "missing"}
    with pytest.raises(ValueError) as caught:
        searcher.observe({"config": config, "value": 2.0})
    assert str(caught.value) == f"TPESearcher.observe() called with config not in pending set: {config}"
    assert searcher.state_dict() == before
    recovered = TPESearcher(mixed_space())
    recovered.load_state_dict(before)
    assert searcher.propose(1) == recovered.propose(1)


def test_tpe_missing_dependency_retains_actionable_diagnostic():
    with patch("hponas.searchers_tpe.OPTUNA_AVAILABLE", False):
        with pytest.raises(ImportError) as caught:
            TPESearcher(mixed_space())
    assert str(caught.value) == "TPESearcher requires optuna: pip install optuna"


def test_tpe_refuses_a_public_knob_changed_to_an_unsupported_kind():
    space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
    searcher = TPESearcher(space)
    space.knobs[0].kind = "unsupported"
    with pytest.raises(ValueError) as caught:
        searcher.propose(1)
    assert str(caught.value) == "Unknown knob kind: unsupported"
