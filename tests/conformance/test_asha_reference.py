"""Independent pinned promotion reference and completed-trial median contract."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from hponas.schedulers import ASHAConfig, ASHAScheduler


@pytest.fixture(scope="module")
def vendor():
    directory = Path(__file__).resolve().parents[1] / "fixtures/syne_tune_0_13_0"
    sources = {
        "hyperband_stopping.py": "6c51776f5a974b88fc17d25372ab1b11cf1e422c4bec55c45f3fd272ba77e026",
        "hyperband_promotion.py": "6e1dce23f38793af42a2878b7ce7473330306fa672f4b2d24faa49d9e356c155",
    }
    namespace = {"__name__": "pinned_syne_tune_reference"}
    for name, expected_hash in sources.items():
        path = directory / name
        source = path.read_bytes()
        assert hashlib.sha256(source).hexdigest() == expected_hash
        tree = ast.parse(source)
        tree.body = [
            node
            for node in tree.body
            if not (
                isinstance(node, ast.ImportFrom)
                and node.module == "syne_tune.optimizer.schedulers.hyperband_stopping"
            )
        ]
        exec(compile(tree, str(path), "exec"), namespace)
    return namespace


def drain(scheduler):
    result = []
    while promotion := scheduler.promote():
        assert len(promotion) == 1
        assert promotion[0] not in result, 'Scheduler repeated an already emitted promotion'
        result.extend(promotion)
    return result


@pytest.mark.parametrize(
    "values", [[], [0], [0, 1], [0, 1, 2], [0, 1, 2, 3], list(range(7)), [1] * 4,
               [-1e308, 1e308], [-1e308, -1e308, 1e308, 1e308]]
)
@pytest.mark.parametrize("maximize", [False, True])
def test_promotion_matches_pinned_source(vendor, values, maximize):
    mode = "max" if maximize else "min"
    ref = vendor["PromotionRungSystem"]([1, 3], [1 / 3, 1 / 3], "loss", mode, "step", 9)
    rung = ref._rungs[-1]
    scheduler = ASHAScheduler(ASHAConfig(r_max=9))
    for i, value in enumerate(values):
        metric = -value if maximize else value
        rung.add(vendor["PromotionRungEntry"](str(i), metric))
        scheduler.report(str(i), 1, -metric if maximize else metric)
    expected = []
    while candidate := ref.on_task_schedule("unused"):
        expected.append((candidate["trial_id"], candidate["milestone"]))
    assert drain(scheduler) == expected
    assert drain(scheduler) == []


def test_late_results_reopen_waiting_candidates_after_recovery():
    scheduler = ASHAScheduler(ASHAConfig(r_max=9))
    for i in range(4):
        scheduler.report(str(i), 1, i)
    assert drain(scheduler) == [("0", 3), ("1", 3)]
    assert scheduler._trial_state["2"][-1] == "paused"
    restored = ASHAScheduler(ASHAConfig(r_max=9))
    restored.load_state_dict(json.loads(json.dumps(scheduler.state_dict())))
    for target in (scheduler, restored):
        for i in range(4, 7):
            target.report(str(i), 1, 96 + i)
        assert drain(target) == [("2", 3)]
    assert restored.state_dict() == scheduler.state_dict()


def test_highest_rung_first_and_promoted_population_retained():
    scheduler = ASHAScheduler(ASHAConfig(r_max=9))
    for rung in (1, 3):
        for i in range(4):
            scheduler.report(f"{rung}-{i}", rung, i)
    assert scheduler.promote() == [("3-0", 9)]
    assert scheduler.promote() == [("3-1", 9)]
    assert scheduler.promote() == [("1-0", 3)]
    assert len(scheduler._rung_populations[1]) == 4


def test_duplicate_stale_and_conflicting_reports():
    scheduler = ASHAScheduler(ASHAConfig(r_max=3))
    for tid in ("a", "b"):
        scheduler.report(tid, 1, 0)
    before = scheduler.state_dict()
    assert scheduler.report("a", 1, 0) == "pause"
    assert scheduler.state_dict() == before
    with pytest.raises(ValueError, match="Conflicting"):
        scheduler.report("a", 1, -1)
    assert scheduler.promote() == [("a", 3)]
    assert scheduler.report("a", 1, 0) == "continue"
    assert scheduler.report("a", 2, 0, is_progress=True) == "continue"
    assert scheduler.report("a", 3, 0) == "stop"
    scheduler.finish("a", "completed")
    before = scheduler.state_dict()
    assert scheduler.report("a", 1, -100) == "stop"
    scheduler.finish("a", "completed")
    assert scheduler.state_dict() == before


def test_legacy_checkpoint_requires_explicit_policy():
    legacy = ASHAScheduler(ASHAConfig(promotion_policy="legacy_bootstrap"))
    legacy.report("single", 1, 0)
    state = legacy.state_dict()
    state.pop("schema_version")
    state["config"].pop("promotion_policy")
    default = ASHAScheduler(ASHAConfig())
    before = default.state_dict()
    with pytest.raises(ValueError, match="policy differs"):
        default.load_state_dict(state)
    assert default.state_dict() == before
    legacy.load_state_dict(state)
    assert legacy.promote() == [("single", 3)]


def median_scheduler():
    return ASHAScheduler(
        ASHAConfig(r_min=4, r_max=4, median_stopping=True, report_grid=(1, 2, 3, 4))
    )


def reference_trial(scheduler, tid, status="completed", missing=False):
    for step in (2, 3, 4) if missing else (1, 2, 3, 4):
        scheduler.report(tid, step, 5, is_progress=True)
    scheduler.finish(tid, status)


def test_live_rung_results_failed_and_missing_references_do_not_enable_median():
    scheduler = median_scheduler()
    for i in range(5):
        assert scheduler.report(f"live-{i}", 1, i * 100, is_progress=True) == "continue"
        reference_trial(scheduler, f"failed-{i}", "failed")
        reference_trial(scheduler, f"missing-{i}", missing=True)
        scheduler.report(f"endpoint-{i}", 4, 5)
    assert scheduler.report("candidate", 1, 1000, is_progress=True) == "continue"


def test_median_uses_running_averages_and_five_completed_references():
    scheduler = median_scheduler()
    for i in range(4):
        reference_trial(scheduler, str(i))
    # Passes startup guard. Its next point is better, but its running average
    # (10 + 2) / 2 is worse than the completed-reference mean of 5.
    assert scheduler.report("candidate", 1, 10, is_progress=True) == "continue"
    reference_trial(scheduler, "fifth")
    restored = median_scheduler()
    restored.load_state_dict(json.loads(json.dumps(scheduler.state_dict())))
    for target in (scheduler, restored):
        assert target.report("candidate", 2, 2, is_progress=True) == "stop"
        assert target.report("candidate", 3, -100, is_progress=True) == "stop"
        assert target.report("equal", 1, 5, is_progress=True) == "continue"
        assert (
            target.report("incomplete-prefix", 2, 500, is_progress=True) == "continue"
        )
    assert restored.state_dict() == scheduler.state_dict()


def test_completion_and_grid_are_explicit():
    with pytest.raises(ValueError, match="report_grid"):
        ASHAConfig(median_stopping=True)
    scheduler = ASHAScheduler(ASHAConfig(r_max=3))
    scheduler.report("rung-only", 1, 0)
    with pytest.raises(ValueError, match="full-fidelity"):
        scheduler.finish("rung-only", "completed")
    scheduler.finish("rung-only", "cancelled")
    assert scheduler.report("rung-only", 3, 0) == "stop"
    with pytest.raises(ValueError, match="terminal"):
        scheduler.finish("rung-only", "completed")
