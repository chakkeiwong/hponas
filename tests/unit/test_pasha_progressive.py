"""Progressive resource allocation, published soft ranking and exact recovery."""

import json

import pytest

from hponas import Knob, SearchSpace, RandomSearcher, LocalExecutor, Study
from hponas.events import EventLog
from hponas.replay import ReplayEngine
from hponas.schedulers import PASHAConfig, PASHAScheduler, BudgetedASHAConfig, BudgetedASHAScheduler


def scheduler(**options):
    return PASHAScheduler(PASHAConfig(eta=3, r_min=1, r_max=27, **options))


def first_rung(target):
    for tid, value in [("a", 0.), ("b", 1.), ("c", 2.), ("d", 3.)]:
        assert target.report(tid, 1, value) == "pause"
    assert target.promote() == [("a", 3)]
    assert target.promote() == [("b", 3)]
    assert target.promote() == []


def restore(target):
    saved = json.loads(json.dumps(target.state_dict()))
    other = scheduler()
    other.load_state_dict(saved)
    assert other.state_dict() == target.state_dict()
    return other


def test_stable_ranking_holds_cap_then_late_survivor_reversal_releases_paused_trials():
    target = scheduler(ranking_epsilon=0.)
    first_rung(target)
    target.report("a", 3, .1)
    target.report("b", 3, .9)
    assert target.current_max_fidelity == 3
    assert target.promote() == []
    target = restore(target)
    for tid in ("e", "f", "g"):
        target.report(tid, 1, 100.)
    assert target.promote() == [("c", 3)]
    target.report("c", 3, -.2)
    assert target.current_max_fidelity == 9
    assert target.promote() == [("c", 9)]
    assert target.promote() == []
    target = restore(target)
    target.report("c", 9, -.3)
    assert target.current_max_fidelity == 9
    assert target.promote() == []


def test_dense_temporary_reversal_updates_noise_tolerance_but_permanent_one_grows():
    target = scheduler()
    first_rung(target)
    target.report("a", 2, 1.)
    target.report("b", 2, 0.)
    target.report("a", 3, 0.)
    target.report("b", 3, 1.)
    assert target.state_dict()["epsilon"] == 1.
    assert target.current_max_fidelity == 3
    target = restore(target)
    assert target.promote() == []
    permanent = scheduler()
    first_rung(permanent)
    permanent.report("a", 2, 0.)
    permanent.report("b", 2, 1.)
    permanent.report("a", 3, 1.)
    permanent.report("b", 3, 0.)
    assert permanent.state_dict()["epsilon"] == 0.
    assert permanent.current_max_fidelity == 9


def test_published_soft_ranking_reference_cases():
    from tests.fixtures.pasha_reference_cases import REFERENCE as fixture
    assert len(fixture["cases"]) == 144
    for case in fixture["cases"]:
        target = scheduler(ranking_epsilon=case["epsilon"])
        for i, score in enumerate(case["previous"]):
            target.report(str(i), 1, score)
        # Compare the complete population at one decision boundary, avoiding an
        # earlier partial-population decision in this criterion-only fixture.
        target._rung_populations[1] = [(str(i), float(rank)) for rank, i in enumerate(case["top_order"])]
        target._maybe_increase_resources()
        assert target.current_max_fidelity == (9 if case["increase"] else 3), case


def test_sparse_unpaired_single_and_stale_reports_do_not_manufacture_rank_changes():
    target = scheduler()
    target.report("a", 1, 1.)
    assert target.promote() == []
    target.report("b", 1, 2.)
    assert target.promote() == [("a", 3)]
    target.report("a", 3, 0.)
    assert target.promote() == []
    target.report("unpaired", 3, -2.)
    assert target.current_max_fidelity == 3
    before = target.state_dict()
    target.report("a", 1, -100.)
    assert target.state_dict() == before
    with pytest.raises(ValueError, match="maximum"):
        target.report("a", 9, 0.)
    assert target.state_dict() == before


def test_progressive_study_stops_at_stable_cap_and_replays(tmp_path):
    target = scheduler()
    log = EventLog(tmp_path / "pasha.jsonl")
    study = Study(RandomSearcher(SearchSpace([Knob("x", "continuous", (0., 1.))]), seed=1),
                  LocalExecutor(), lambda c, fidelity: c["x"], budget=9, maximize=False,
                  scheduler=target, checkpoint_dir=tmp_path, event_log=log, legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')
    result = study.run()
    assert result.n_trials > 9
    assert {r.fidelity for r in result.history} == {1, 3}
    assert target.current_max_fidelity == 3
    assert result.best_value == min(r.objective_value for r in result.history if r.fidelity == 3)
    assert restore(target).promote() == []
    replayed = scheduler()
    engine = ReplayEngine(RandomSearcher(study.searcher.search_space, seed=1), log, 1, replayed)
    ok, message, _, _ = engine.verify_determinism(9)
    assert ok, message
    assert replayed.state_dict() == target.state_dict()


def test_budget_only_checkpoint_is_not_silently_reinterpreted():
    old = BudgetedASHAScheduler(BudgetedASHAConfig())
    old.report("a", 1, 0.)
    target = scheduler()
    before = target.state_dict()
    with pytest.raises(ValueError, match="BudgetedASHAScheduler"):
        target.load_state_dict(old.state_dict())
    assert target.state_dict() == before


def test_old_progressive_checkpoint_is_not_reinterpreted_under_new_promotions():
    target = scheduler()
    first_rung(target)
    before = target.state_dict()
    old = dict(before, policy="pasha-progressive-v1")
    with pytest.raises(ValueError, match="promotion policy"):
        target.load_state_dict(old)
    assert target.state_dict() == before


@pytest.mark.parametrize("field", ["ranking_epsilon", "promotion_budget"])
@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf")])
def test_invalid_controls(field, value):
    with pytest.raises(ValueError, match="finite"):
        scheduler(**{field: value})


def test_single_fidelity_has_no_promotions():
    target = PASHAScheduler(PASHAConfig(r_min=1, r_max=1))
    assert target.report("a", 1, 0.) == "stop"
    assert target.promote() == []
