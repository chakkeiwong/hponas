"""Late/foreign progress and incompatible checkpoints cannot alter live work."""

import copy
from dataclasses import replace

import pytest

from hponas import LocalExecutor, Study
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers import RandomSearcher
from hponas.space import Knob, SearchSpace


@pytest.mark.parametrize("policy", ["legacy_bootstrap", "syne_tune_0_13_0"])
@pytest.mark.parametrize("damage,message", [
    ("schema", "Unsupported ASHA checkpoint schema"),
    ("rungs", "Checkpoint rungs differ from scheduler configuration"),
    ("policy", "Checkpoint ASHA promotion policy differs; select legacy_bootstrap explicitly for legacy recovery"),
])
def test_asha_rejected_checkpoint_keeps_state_and_precise_recovery_diagnostic(policy, damage, message):
    scheduler = ASHAScheduler(ASHAConfig(eta=2, r_min=1, r_max=4, promotion_policy=policy))
    scheduler.report("live", 1, 5)
    before = scheduler.state_dict()
    invalid = copy.deepcopy(before)
    if damage == "schema":
        invalid["schema_version"] = 3
    elif damage == "rungs":
        invalid["rungs"] = [1, 99]
    else:
        invalid["config"]["promotion_policy"] = "legacy_bootstrap" if policy != "legacy_bootstrap" else "syne_tune_0_13_0"
    with pytest.raises(ValueError) as exc:
        scheduler.load_state_dict(invalid)
    assert str(exc.value) == message
    assert scheduler.state_dict() == before


@pytest.mark.parametrize("version", [None, 1])
def test_reference_asha_requires_versioned_checkpoint(version):
    scheduler = ASHAScheduler(ASHAConfig())
    invalid = scheduler.state_dict()
    if version is None:
        invalid.pop("schema_version")
    else:
        invalid["schema_version"] = version
    with pytest.raises(ValueError) as exc:
        scheduler.load_state_dict(invalid)
    assert str(exc.value) == "Reference ASHA requires a versioned checkpoint"


def live_study():
    study = Study(RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=9),
                  LocalExecutor(), lambda c: 1, budget=1,
                  scheduler=ASHAScheduler(ASHAConfig(r_min=4, r_max=4)))
    study._new_trial()
    trial = next(iter(study.trials.values()))
    report = ProgressReport(trial.trial_id, trial.root_trial_id, 1, 5, 1, .5)
    return study, report


def test_late_progress_receives_terminal_cancel_without_changing_committed_work():
    study, report = live_study()
    study._pending.clear()
    before = copy.deepcopy(study._snapshot())
    assert study._on_progress(report) == ReportDecision("cancel", "evaluation_already_finished")
    assert study._snapshot() == before


@pytest.mark.parametrize("changes,message", [
    ({"root_trial_id": "foreign"}, "Progress identity or version differs"),
    ({"schema_version": 2}, "Progress identity or version differs"),
    ({"step": 0}, "Progress outside assigned fidelity"),
    ({"step": 5}, "Progress outside assigned fidelity"),
])
def test_rejected_progress_preserves_scheduler_and_accounting(changes, message):
    study, report = live_study()
    before = copy.deepcopy(study._snapshot())
    with pytest.raises(ValueError) as exc:
        study._on_progress(replace(report, **changes))
    assert str(exc.value) == message
    assert study._snapshot() == before
