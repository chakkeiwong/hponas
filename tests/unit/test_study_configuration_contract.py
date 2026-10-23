"""Study construction refuses invalid budgets before work and preserves defaults."""

import json
from types import SimpleNamespace

import pytest

from hponas import LocalExecutor, RandomSearcher, Study
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.space import Knob, SearchSpace


def searcher():
    return RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=7)


@pytest.mark.parametrize("field,value,message", [
    *[("budget", v, "budget must be a positive integer") for v in (0, -1, True, 1.5)],
    *[("max_concurrent", v, "max_concurrent must be a positive integer") for v in (0, -1, True, 1.5)],
    *[("compute_budget_seconds", v, "compute_budget_seconds must be finite and positive")
      for v in (0., -1., True, float("inf"), float("nan"))],
    ("maximize", 1, "maximize must be boolean"),
    ("continuation", "other", "continuation must be restart or resume"),
])
def test_study_options_refuse_before_any_objective_work(field, value, message):
    with pytest.raises(ValueError) as raised:
        Study(searcher(), LocalExecutor(), lambda config: pytest.fail("Invalid options dispatched work"),
              **{field: value}, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    assert str(raised.value) == message


@pytest.mark.parametrize("executor_options,override,expected", [
    ({}, None, 1), ({"num_workers": 3}, None, 3),
    ({"mode": "async", "max_workers": 4}, None, 4),
    ({"mode": "async"}, None, 1), ({"mode": "sync", "max_workers": 4}, None, 1),
    ({"num_workers": 3, "mode": "async", "max_workers": 4}, 2, 2),
])
def test_concurrency_defaults_are_compatible_with_executor_interfaces(executor_options, override, expected):
    study = Study(searcher(), SimpleNamespace(**executor_options), lambda config: 2.,
                  max_concurrent=override, continuation="resume", compute_budget_seconds=.5, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    assert study.max_concurrent == expected
    assert study.continuation == "resume" and study.compute_budget_seconds == .5


@pytest.mark.parametrize("missing", ["report", "promote", "state_dict", "load_state_dict"])
def test_scheduler_interface_requires_recovery_as_well_as_reports(missing):
    methods = {name: lambda *a, **k: None for name in ("report", "promote", "state_dict", "load_state_dict")}
    del methods[missing]
    with pytest.raises(TypeError) as raised:
        Study(searcher(), LocalExecutor(), lambda config: 2., scheduler=SimpleNamespace(**methods), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    assert str(raised.value) == "Scheduler must support reports, promotion and checkpoints"


def test_new_study_checkpoint_has_no_phantom_completed_work(tmp_path):
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=1))
    study = Study(searcher(), LocalExecutor(), lambda config: {"value": 2., "cost": 3.},
                  budget=1, study_name="new", checkpoint_dir=tmp_path, scheduler=scheduler, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    study.save_checkpoint()
    state = json.loads((tmp_path / "new_checkpoint.json").read_text())
    assert state["n_completed"] == 0 and state["n_suggested"] == 0
    assert state["finished"] is False and state["stop_reason"] is None and state["outcome"] is None
    assert state["trials"] == {} and state["results"] == {} and state["pending"] == []
    restored = Study(searcher(), LocalExecutor(), lambda config: {"value": 2., "cost": 3.},
                     scheduler=ASHAScheduler(ASHAConfig(r_min=1, r_max=1)), legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    restored.load_checkpoint(tmp_path / "new_checkpoint.json")
    result = restored.run()
    assert result.n_trials == 1 and result.total_cost == 3. and result.best_value == 2.


@pytest.mark.parametrize('failure', [TypeError, ValueError])
def test_opaque_callable_still_runs_as_a_nonstreaming_objective(failure):
    from hponas.types import Result

    class OpaqueObjective:
        @property
        def __signature__(self):
            raise failure('No inspectable signature')

        def __call__(self, config):
            return 7.

    class OpaqueExecutor(LocalExecutor):
        def execute(self, trial, objective_fn, *, on_report=None):
            assert on_report is None
            return Result(trial.trial_id, objective_fn(trial.config.values), fidelity=trial.fidelity)

    target = Study(searcher(), OpaqueExecutor(), OpaqueObjective(), budget=1,
                   legacy_reason='Opaque callable compatibility contract')
    assert target._streaming_objective is False
    assert target.run().best_value == 7.
