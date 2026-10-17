"""Finite acquisition must visit legal untried points before replicating."""
import json
import builtins
from unittest.mock import patch

import hponas.searchers.gp_searcher as gp_module

import pytest
import torch

from hponas import Config, GPSearcher, Knob, Result, SearchSpace
from hponas.types import Parameter, ParameterType, SearchSpace as LegacySpace


def populated():
    searcher = GPSearcher(SearchSpace([Knob("width", "ordinal", (1, 4))]),
                          seed=20261006, maximize=False)
    for index, width in enumerate([4, 1, 4, 1, 4]):
        tid = str(index)
        searcher.trials[tid] = Config({"width": width})
        searcher.observe(Result(tid, {1: 5.75, 4: 2.0}[width]))
    return searcher


def test_real_acquisition_visits_both_untried_widths_and_replays_checkpoint():
    searcher = populated()
    restored = GPSearcher(searcher.search_space, seed=0)
    restored.set_state(json.loads(json.dumps(searcher.get_state())))
    first = searcher.suggest()
    assert restored.suggest().values == first.values
    assert first["width"] in {2, 3}
    searcher.trials["5"] = first
    searcher.observe(Result("5", {2: 2.25, 3: 1.75}[first["width"]]))
    second = searcher.suggest()
    assert {first["width"], second["width"]} == {2, 3}
    searcher.trials["6"] = second
    searcher.observe(Result("6", {2: 2.25, 3: 1.75}[second["width"]]))
    assert searcher.get_best(maximize=False).objective_value == 1.75
    # Exhaustion permits another valid observation without crashing the caller.
    assert searcher.suggest()["width"] in {1, 2, 3, 4}


def test_pending_configuration_is_not_duplicated_when_an_untried_choice_exists():
    searcher = populated()
    searcher.trials["pending"] = Config({"width": 2})
    assert searcher.suggest().values == {"width": 3}


def test_single_proposal_acquires_only_from_unseen_physical_choices(monkeypatch):
    """An acquisition preferring a seen point must never receive that point."""
    searcher = populated()
    searcher.trials["pending"] = Config({"width": 2})
    requested = []

    def ordered_acquisition(acquisition, *, q, choices):
        requested.append(q)
        # The stub deliberately chooses the lowest encoded width. An omitted
        # unseen filter would repeat width 1 even though width 3 is available.
        order = torch.argsort(choices[:, 0])
        return choices[order[:q]], torch.tensor(0., dtype=choices.dtype)

    monkeypatch.setattr(gp_module, "optimize_acqf_discrete", ordered_acquisition)
    proposal = searcher.suggest()
    assert proposal.values == {"width": 3}
    assert requested == [1]


def test_conditional_and_log_integer_domains_are_enumerated_physically():
    space = SearchSpace([Knob("family", "categorical", ["a", "b"]),
                         Knob("depth", "ordinal", (1, 3), transform="log",
                              condition=("family", "b"))])
    searcher = GPSearcher(space)
    assert [c.values for c in searcher._finite_configs()] == [
        {"family": "a"}, {"family": "b", "depth": 1},
        {"family": "b", "depth": 2}, {"family": "b", "depth": 3}]


def test_finite_legacy_space_preserves_choices():
    space = LegacySpace({"x": Parameter("x", ParameterType.DISCRETE, choices=[2, 5, 11])})
    assert [c.values for c in GPSearcher(space)._finite_configs()] == [
        {"x": 2}, {"x": 5}, {"x": 11}]


class GuardedRange:
    """Observe forbidden materialization without allocating the domain."""
    def __init__(self, *args):
        self.values = builtins.range(*args)

    def __iter__(self):
        # Avoid len(range), which legitimately overflows above Py_ssize_t.
        if self.values.step != 1:
            raise AssertionError("Unexpected finite-domain range step")
        count = max(0, self.values.stop-self.values.start)
        if count > 4096:
            raise AssertionError("Oversized domain was iterated before refusal")
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]


@pytest.mark.parametrize("specs", [
    [("x", "continuous", (0., 1.))],
    [("x", "ordinal", (1, 10**12))],
    [("x", "ordinal", (1, 10**19))],
    [("x", "ordinal", (1, 65)), ("y", "ordinal", (1, 65))],
])
def test_unbounded_or_large_domains_do_not_materialize(specs):
    knobs = [Knob(*spec) for spec in specs]
    with patch.object(gp_module, "range", GuardedRange, create=True):
        assert GPSearcher(SearchSpace(knobs))._finite_configs() is None


@pytest.mark.parametrize("count", [4095, 4096, 4097])
def test_finite_enumeration_boundary_is_exact_and_bounded(count):
    searcher = GPSearcher(SearchSpace([Knob("x", "ordinal", (1, count))]))
    with patch.object(gp_module, "range", GuardedRange, create=True):
        values = searcher._finite_configs()
    if count > 4096:
        assert values is None
    else:
        assert [row.values for row in values] == [{"x": i} for i in builtins.range(1, count+1)]
