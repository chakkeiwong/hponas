import copy
import json
from pathlib import Path

import pytest

from validation.tier0_analysis import training_seed
from validation.tier0_design import canonical_digest, study_stream_slot
from validation.tier0_protected_evaluation import freeze_incumbent_plan, protected_curve, protected_seed
from validation.tier0_rank_design import rank_curve_endpoints


@pytest.fixture
def example():
    root = Path(__file__).resolve().parents[2]
    design = json.loads((root / "validation/designs/tier0_candidate_v1.json").read_text())
    task = next(iter(design["tasks"]))
    design["tasks"][task]["budget"]["seconds"] = 10
    design["budget_grid"] = [0, .2, .4, .6, .8, 1]
    slot = study_stream_slot(design, task, 10000)
    record = {"entry": "V04-T0", "task": task, "seed": 10000, "arm": "gp_log",
              "design_digest": canonical_digest(design), "rng_stream_slot": slot,
              "budget_seconds": 10, "elapsed_seconds": 11, "status": "complete", "accounting_complete": True,
              "observations": [
                  {"index": i, "completed_seconds": time, "value": value, "training_seed": training_seed(slot, i),
                   "artifact_refs": {"checkpoint": {"path": f"fake_{i}.pkl", "sha256": str(i) * 64}}}
                  for i, (time, value) in enumerate([(1, 2), (3, 5), (5, 4), (7, 5), (11, 100)])]}
    return design, record


def receipts(plan, values):
    return [{"observation_index": item["observation_index"], "plan_digest": canonical_digest(plan),
             "checkpoint_sha256": item["checkpoint"]["sha256"], "seed": item["seed"],
             "returns": [values[item["observation_index"]]] * item["episodes"]}
            for item in plan["evaluations"]]


def test_protected_values_cannot_reselect_the_search_incumbent(example):
    plan = freeze_incumbent_plan(*example)
    assert plan["incumbent_indices"] == [None, 0, 1, 1, 1, 1]
    assert [p["observation_index"] for p in plan["evaluations"]] == [0, 1]
    scores = protected_curve(plan, receipts(plan, {0: 100, 1: -100}))
    assert scores == [(False, None), (True, 100), (True, -100), (True, -100), (True, -100), (True, -100)]
    comparison = rank_curve_endpoints(scores, [(False, None)] + [(True, 0)] * 5, plan["budget_grid"])
    assert comparison["final_win"] == (-1, -1)
    assert comparison["anytime_win"] == pytest.approx((-.4, -.4))
    assert plan["feeds_searcher"] is False
    assert plan["certifies_acceptance"] is False


def test_every_actual_episode_is_disjoint_from_training_and_search_namespaces():
    # Check all phases/tasks of the actual candidate, including boundary seeds.
    root = Path(__file__).resolve().parents[2]
    design = json.loads((root / "validation/designs/tier0_candidate_v1.json").read_text())
    training, search, protected = set(), set(), set()
    for task, info in design["tasks"].items():
        count, episodes = info["budget"]["trial_limit"], info["settings"]["eval_episodes"]
        for blocks in design["seed_sets"].values():
            for block in blocks:
                slot = study_stream_slot(design, task, block)
                for index in range(count):
                    base = training_seed(slot, index)
                    training.add(base)
                    search.update(range(base + 100000, base + 100000 + episodes))
                    protected_base = protected_seed(slot, index, episodes)
                    seeds = set(range(protected_base, protected_base + episodes))
                    assert not seeds & protected
                    protected.update(seeds)
    assert not protected & (training | search)
    assert len(protected) == 135 * 50 * 10
    assert min(protected) >= 0 and max(protected) < 2 ** 32


def test_missing_episode_or_policy_cannot_be_dropped(example):
    plan = freeze_incumbent_plan(*example)
    rows = receipts(plan, {0: 2, 1: 3})
    rows[1]["returns"][0] = None
    assert protected_curve(plan, rows)[-1] is None
    assert protected_curve(plan, rows[:1])[-1] is None
    rows[1]["returns"].pop()
    with pytest.raises(ValueError, match="All planned test episodes"):
        protected_curve(plan, rows)


def test_malformed_episode_cannot_be_reclassified_as_missing(example):
    plan = freeze_incumbent_plan(*example)
    rows = receipts(plan, {0: 1, 1: 2})
    rows[0]["returns"][0] = "unverified"
    with pytest.raises(ValueError, match="integrity error"):
        protected_curve(plan, rows)


@pytest.mark.parametrize("key,value", [("seed", 1), ("checkpoint_sha256", "f" * 64), ("plan_digest", "f" * 64)])
def test_receipts_are_bound_to_plan_policy_and_disjoint_seeds(example, key, value):
    plan = freeze_incumbent_plan(*example)
    rows = receipts(plan, {0: 1, 1: 2})
    rows[0][key] = value
    with pytest.raises(ValueError, match="differs from frozen"):
        protected_curve(plan, rows)


def test_changed_search_trace_changes_plan_even_if_incumbents_agree(example):
    design, record = example
    original = freeze_incumbent_plan(design, record)
    record["observations"][2]["value"] = 3
    changed = freeze_incumbent_plan(design, record)
    assert original["incumbent_indices"] == changed["incumbent_indices"]
    assert canonical_digest(original) != canonical_digest(changed)
    with pytest.raises(ValueError, match="differs from frozen"):
        protected_curve(changed, receipts(original, {0: 1, 1: 2}))


def test_wrong_stream_incomplete_trace_and_extra_policies_rejected(example):
    design, record = example
    for key, value in [("rng_stream_slot", 1), ("status", "failed"), ("accounting_complete", False),
                       ("elapsed_seconds", 9), ("budget_seconds", 9)]:
        changed = copy.deepcopy(record)
        changed[key] = value
        with pytest.raises(ValueError):
            freeze_incumbent_plan(design, changed)
    plan = freeze_incumbent_plan(design, record)
    rows = receipts(plan, {0: 1, 1: 2})
    rows.append(dict(rows[0], observation_index=2))
    with pytest.raises(ValueError, match="unselected"):
        protected_curve(plan, rows)


def test_protected_mean_of_extreme_finite_episodes_does_not_overflow(example):
    plan = freeze_incumbent_plan(*example)
    result = protected_curve(plan, receipts(plan, {0: 1e308, 1: -1e308}))
    assert result[-1] == (True, -1e308)


@pytest.mark.parametrize("slot,index,episodes", [(True, 0, 10), (32768, 0, 10), (0, True, 10),
                                                  (0, 0, False), (0, 0, 0), (0, 9000, 10)])
def test_protected_seed_allocation_refuses_overlap_and_bad_counts(slot, index, episodes):
    with pytest.raises(ValueError):
        protected_seed(slot, index, episodes)
