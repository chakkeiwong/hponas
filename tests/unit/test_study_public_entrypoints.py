"""Public legacy, default-budget and scheduler-free reporting entrypoints."""

import json

import pytest

from hponas import IncompleteStudyError, LocalExecutor, RandomSearcher, Study
from hponas.space import SearchSpace, Knob


def searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=7)


def test_default_budget_runs_exactly_one_hundred_new_configurations():
    result = Study(searcher(), LocalExecutor(), lambda config: {"value": 2., "cost": 3.}, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert result.n_trials == 100 and len(result.history) == 100 and result.total_cost == 300.


def test_empty_study_space_refuses_before_execution():
    with pytest.raises(ValueError) as raised:
        Study(RandomSearcher(SearchSpace()), LocalExecutor(), lambda config: 2., legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    assert str(raised.value) == "Study requires a nonempty search space"


def test_legacy_searcher_is_adapted_with_the_requested_optimization_direction():
    class Legacy:
        space = SearchSpace([Knob("x", "continuous", (0., 1.))])
        seed = 7

        def __init__(self):
            self.observations = []

        def propose(self, count):
            assert count == 1
            return [{"x": .25}]

        def observe(self, observation):
            self.observations.append(observation)

        def state_dict(self):
            return {"observations": list(self.observations)}

        def load_state_dict(self, state):
            self.observations = list(state["observations"])

    legacy = Legacy()
    result = Study(legacy, LocalExecutor(), lambda config: {"value": 5., "cost": 3.},
                   budget=1, maximize=False, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert result.best_value == 5. and result.best_config.values == {"x": .25}
    assert legacy.observations == [{"config": {"x": .25}, "value": -5., "fidelity": 1., "cost": 3.}]


def test_scheduler_free_reporter_still_checkpoints_acknowledged_progress(tmp_path):
    def objective(config, reporter):
        reporter(1., 5., cost=3.)
        state = json.loads((tmp_path / "reporting_checkpoint.json").read_text())
        assert state["live_cost"] == {"reporting_trial_0": 3.}
        assert state["report_cache"]["reporting_trial_0"]["1.0"]["value"] == 5.
        return {"value": 5., "cost": 3.}

    result = Study(searcher(), LocalExecutor(), objective, budget=1,
                   checkpoint_dir=tmp_path, study_name="reporting", legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert result.best_value == 5. and result.total_cost == 3.


def test_no_valid_incumbent_explains_its_terminal_reason():
    with pytest.raises(IncompleteStudyError) as raised:
        Study(searcher(), LocalExecutor(), lambda config: float("nan"), budget=1, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately').run()
    assert str(raised.value) == "No valid results found at required fidelity: no_full_fidelity_result"
