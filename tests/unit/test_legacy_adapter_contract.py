"""The dictionary-searcher bridge preserves Study semantics and recovery."""

import copy
from types import SimpleNamespace

import pytest

from hponas.searchers.adapter import LegacySearcherAdapter
from hponas.space import Knob, SearchSpace
from hponas.types import Config, Result


class RecordingLegacySearcher:
    def __init__(self):
        self.space = SearchSpace([Knob("x", "continuous", (0.0, 1.0))])
        self.seed = 19
        self.index = 0
        self.request_sizes = []
        self.observations = []

    def propose(self, count):
        self.request_sizes.append(count)
        configs = [{"x": (self.index + i) / 10} for i in range(count)]
        self.index += count
        return configs

    def observe(self, observation):
        self.observations.append(copy.deepcopy(observation))

    def state_dict(self):
        return {"index": self.index, "observations": copy.deepcopy(self.observations)}

    def load_state_dict(self, state):
        self.index = state["index"]
        self.observations = copy.deepcopy(state["observations"])


def test_adapter_rejects_multiobjective_searcher_before_running_it():
    with pytest.raises(TypeError, match="[Ss]calar"):
        LegacySearcherAdapter(SimpleNamespace(objectives=["loss", "cost"]))


def test_adapter_wraps_one_proposal_and_preserves_search_space_and_seed():
    legacy = RecordingLegacySearcher()
    legacy.objectives = []
    adapter = LegacySearcherAdapter(legacy)
    assert adapter.search_space is legacy.space
    assert adapter.seed == 19
    assert adapter.maximize is True
    configs = [adapter.suggest(), adapter.suggest()]
    assert all(isinstance(c, Config) for c in configs)
    assert [c.values for c in configs] == [{"x": 0.0}, {"x": 0.1}]
    assert legacy.request_sizes == [1, 1]


@pytest.mark.parametrize("maximize,expected", [(True, 3.5), (False, -3.5)])
def test_observe_forwards_matching_config_direction_fidelity_and_cost(
    maximize, expected
):
    legacy = RecordingLegacySearcher()
    adapter = LegacySearcherAdapter(legacy, maximize=maximize)
    adapter.trials = {"other": Config({"x": 0.8}), "trial": Config({"x": 0.2})}
    result = Result("trial", 3.5, cost=7.25, fidelity=4.0)
    adapter.observe(result)
    assert legacy.observations == [
        {"config": {"x": 0.2}, "value": expected, "fidelity": 4.0, "cost": 7.25}
    ]
    assert adapter.history == [result]
    # Revision is explicitly unsupported: neither history nor the legacy model changes.
    with pytest.raises(ValueError, match="already observed"):
        adapter.observe(Result("trial", -10.0))
    assert adapter.history == [result]
    assert len(legacy.observations) == 1


@pytest.mark.parametrize(
    "value,status",
    [
        (2.0, "failed"),
        (float("nan"), "completed"),
        (float("inf"), "completed"),
        (2.0, "timeout"),
    ],
)
def test_invalid_results_stay_in_history_without_being_fitted(value, status):
    legacy = RecordingLegacySearcher()
    adapter = LegacySearcherAdapter(legacy)
    adapter.trials["bad"] = Config({"x": 0.2})
    result = Result("bad", value, status=status)
    adapter.observe(result)
    assert len(adapter.history) == 1 and adapter.history[0] is result
    assert legacy.observations == []
    with pytest.raises(ValueError, match="already observed"):
        adapter.observe(Result("bad", 1.0))
    assert legacy.observations == []


def test_checkpoint_restores_history_trial_mapping_direction_and_legacy_sequence():
    adapter = LegacySearcherAdapter(RecordingLegacySearcher(), maximize=False)
    adapter.trials["first"] = adapter.suggest()
    result = Result("first", 2.0, cost=3.0, fidelity=4.0)
    adapter.observe(result)
    state = copy.deepcopy(adapter.get_state())
    expected_next = adapter.suggest()
    restored = LegacySearcherAdapter(RecordingLegacySearcher(), maximize=True)
    restored.seed = 99
    restored.set_state(state)
    assert restored.seed == 19
    assert restored.history == [result]
    assert restored.trials == {"first": Config({"x": 0.0})}
    assert restored.maximize is False
    assert restored.suggest() == expected_next
    restored.trials["second"] = Config({"x": 0.7})
    restored.observe(Result("second", 5.0, cost=6.0, fidelity=8.0))
    assert restored.searcher.observations == [
        {"config": {"x": 0.0}, "value": -2.0, "fidelity": 4.0, "cost": 3.0},
        {"config": {"x": 0.7}, "value": -5.0, "fidelity": 8.0, "cost": 6.0},
    ]


def test_snapshot_validation_delegates_the_full_ledger_and_propagates_refusal():
    class ValidatingLegacy(RecordingLegacySearcher):
        def validate_study_snapshot(self, state):
            self.validated = copy.deepcopy(state)
            if state["study_name"] != "expected":
                raise ValueError("Snapshot belongs to another task")

    legacy = ValidatingLegacy()
    adapter = LegacySearcherAdapter(legacy)
    state = {"study_name": "expected", "results": {"trial": {"value": 3.0}}}
    adapter.validate_study_snapshot(state)
    assert legacy.validated == state
    with pytest.raises(ValueError, match="^Snapshot belongs to another task$"):
        adapter.validate_study_snapshot({"study_name": "wrong"})


@pytest.mark.parametrize("direction", [None, 0, 1, "false"])
def test_invalid_checkpoint_direction_is_refused_without_changing_live_state(direction):
    adapter = LegacySearcherAdapter(RecordingLegacySearcher())
    before = adapter.get_state()
    damaged = copy.deepcopy(before)
    damaged["maximize"] = direction
    with pytest.raises(ValueError) as error:
        adapter.set_state(damaged)
    assert str(error.value) == "Legacy adapter direction must be boolean"
    assert adapter.get_state() == before
