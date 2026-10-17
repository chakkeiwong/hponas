"""End-to-end artifact fixtures: no PPO training, pickle loading or certification."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from validation.evidence import decision
from validation.tier0_campaign import run_study
from validation.tier0_design import (
    ARMS, DEFAULT_DESIGN, RANK_ANALYSIS, canonical_digest, design_errors, load_design, require_campaign_ready,
    require_confirmation_sizing,
)
from validation.tier0_inference import require_acceptance_inference
from validation.tier0_rank_campaign import (
    campaign, execute_protected_bundle, freeze_search_bundle, recompute_protected, verify_campaign_isolation,
)


def bind(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))
    return bind(path)


def read(ref):
    return json.loads(Path(ref["path"]).read_text())


@pytest.fixture
def fixture_campaign(tmp_path):
    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    assert design["schema_version"] == 2
    task_id = next(iter(design["tasks"]))
    design["tasks"] = {task_id: design["tasks"][task_id]}
    design["entry_tasks"] = {entry: [task_id] for entry in ARMS}
    design["selected_counts"]["pilot"] = {entry: 5 for entry in ARMS}
    design["resource"].update(protected_cap_seconds=1000, campaign_cap_seconds=10000)
    task = design["tasks"][task_id]
    task["budget"].update(seconds=10, max_overshoot_seconds=2, protected_policy_cap_seconds=10)
    design["budget_grid"] = [0, .2, .4, .6, .8, 1]
    refs = []
    for entry, arms in ARMS.items():
        for seed in design["seed_sets"]["pilot"]:
            for arm in arms:
                elapsed = [0.0]

                def objective(config, actual_seed, index):
                    elapsed[0] += 2
                    directory = tmp_path / "policies" / f"{entry}-{seed}-{arm}-{index}"
                    directory.mkdir(parents=True)
                    checkpoint = directory / "policy.pkl"
                    checkpoint.write_bytes(b"inert test bytes; never unpickled")
                    recipe = directory / "recipe.json"
                    write(recipe, {"settings": task["settings"], "config": {**task["fixed_config"], **config},
                                   "training_seed": actual_seed, "search_seed": actual_seed + 100000})
                    curve = directory / "learning_curve.json"
                    write(curve, [{"steps": task["settings"]["max_timesteps"]}])
                    value = float(index + 1)
                    return {"value": value, "metadata": {"workload": "brax_ppo", "settings": task["settings"],
                            "training_seed": actual_seed, "search_seed": actual_seed + 100000,
                            "search_returns": [value] * task["settings"]["eval_episodes"]},
                            "artifacts": {"checkpoint": str(checkpoint), "recipe": str(recipe), "learning_curve": str(curve)}}

                record = run_study(design, entry, task_id, seed, arm, "pilot", objective, clock=lambda: elapsed[0])
                assert record["status"] == "complete"
                refs.append(write(tmp_path / "search" / f"{entry}-{seed}-{arm}.json", record))
    return design, tmp_path, refs


def evaluate_fixture(root, frozen, *, mode="normal", cap_increment=1):
    elapsed, calls = [0.0], []

    def evaluator(checkpoint, seed):
        # The whole Cartesian product and all plans are already on disk before
        # the first protected observation; a real pickle loader is never called.
        bundle = read(frozen)
        assert all(slot["plan"] is None or Path(slot["plan"]["path"]).exists() for slot in bundle["slots"])
        elapsed[0] += cap_increment
        calls.append((checkpoint, seed))
        if mode == "raises":
            raise RuntimeError("injected protected evaluation failure")
        episodes = read(bind(checkpoint.parent / "recipe.json"))["settings"]["eval_episodes"]
        candidate = "gp_log" in str(checkpoint) or "tpe_log" in str(checkpoint)
        value = -1 if candidate else 1  # Opposite to any claimed winner in aggregates.
        values = [float(value)] * episodes
        if mode == "nonfinite":
            values[-1] = float("inf")
        if mode == "drop_episode":
            values.pop()
        return {"seed": seed, "returns": values, "value": 999999}  # Aggregate is ignored.

    ref = execute_protected_bundle(root, frozen, evaluator=evaluator, clock=lambda: elapsed[0])
    return ref, calls


def test_active_candidate_adopts_claim_but_has_truthful_remaining_freeze_errors(tmp_path):
    design = load_design()
    errors = design_errors(design)
    for fragment in ("planning alternative", "protected", "budget"):
        assert any(fragment in error for error in errors), (fragment, errors)
    assert not any("selector" in error or "reviewer" in error for error in errors)
    assert not any("scale bounds" in error or "regret reference" in error or "independent task clusters" in error for error in errors)
    with pytest.raises(ValueError, match="Incomplete Tier 0 design"):
        campaign("V04-T0", tmp_path, design_path=DEFAULT_DESIGN, phase="pilot")
    assert not list(tmp_path.iterdir())


def test_only_full_adopted_inference_contract_is_eligible_not_a_method_label():
    require_acceptance_inference(copy.deepcopy(RANK_ANALYSIS))
    for key in RANK_ANALYSIS:
        changed = copy.deepcopy(RANK_ANALYSIS)
        changed.pop(key)
        with pytest.raises(ValueError, match="STAT-03"):
            require_acceptance_inference(changed)
    with pytest.raises(ValueError, match="STAT-03"):
        require_acceptance_inference({"method": RANK_ANALYSIS["method"]})


def test_legacy_sized_receipt_cannot_authorize_rank_confirmation(tmp_path):
    from validation.tier0_sizing import size_from_pilot

    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    design["selected_counts"]["confirmation"] = {entry: 20 for entry in ARMS}
    design["sizing_receipt"] = write(tmp_path / "old-bootstrap.json", {
        "entries": {entry: {"engineering_fixture": False, "verdict": "SIZED", "chosen_n": 20}
                    for entry in ARMS}})
    with pytest.raises(ValueError, match="prospective protected-rank sizing"):
        require_confirmation_sizing(design, "confirmation")
    require_confirmation_sizing(design, "pilot")  # No confirmation count borrowed for the pilot.
    with pytest.raises(ValueError, match="legacy bootstrap sizing"):
        size_from_pilot(design, [])


@pytest.mark.parametrize("fault", [None, "missing_search", "output", "late_search", "early_protected",
                                   "wrong_freeze", "protected_output", "probe", "search_timeout",
                                   "protected_timeout", "missing_timeout", "nonfinite_timeout"])
def test_campaign_isolation_binds_outputs_and_search_protected_order(fixture_campaign, monkeypatch, fault):
    from validation import tier0_isolation

    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen)
    bundle = read(frozen)
    reports = [{"payload": {"operation": "search", "design": design, "phase": "pilot",
                            **{k: read(ref)[k] for k in ("entry", "task", "seed", "arm")}},
                "status": "complete", "output": read(ref), "launch_ns": 1, "finish_ns": 2,
                "elapsed_seconds": read(ref)["elapsed_seconds"], "timeout_seconds": 12} for ref in refs]
    for row in read(evaluated)["receipts"]:
        receipt = read(row["receipt"])
        plan = read(bundle["slots"][row["slot_index"]]["plan"])
        item = next(item for item in plan["evaluations"] if item["observation_index"] == receipt["observation_index"])
        reports.append({"payload": {"operation": "protected", "root": str(root), "search_freeze": frozen,
                                     "checkpoint": item["checkpoint"], "seed": item["seed"]},
                        "status": "complete", "output": {"seed": item["seed"], "returns": receipt["returns"]},
                        "launch_ns": 4, "finish_ns": 5, "elapsed_seconds": receipt["elapsed_seconds"],
                        "timeout_seconds": 10})
    manifest = write(root / "process-isolation.json", {"kind": "rank_campaign_process_sequence_v1",
        "source_digest": "fixture", "search_freeze": frozen, "freeze_ns": 3, "processes": []})
    monkeypatch.setattr(tier0_isolation, "verify_sequence", lambda *args, **kwargs: reports)
    if fault == "missing_search":
        reports.pop(0)
    elif fault == "output":
        reports[0]["output"]["seed"] += 1
    elif fault == "late_search":
        reports[0]["finish_ns"] = 4
    elif fault == "early_protected":
        reports[-1]["launch_ns"] = 2
    elif fault == "wrong_freeze":
        reports[-1]["payload"]["search_freeze"] = {}
    elif fault == "protected_output":
        reports[-1]["output"]["returns"][0] += 1
    elif fault == "probe":
        reports[0]["payload"]["operation"] = "engineering_probe"
    elif fault == "search_timeout":
        reports[0]["timeout_seconds"] = design["resource"]["campaign_cap_seconds"]
    elif fault == "protected_timeout":
        reports[-1]["timeout_seconds"] = design["resource"]["campaign_cap_seconds"]
    elif fault == "missing_timeout":
        reports[0].pop("timeout_seconds")
    elif fault == "nonfinite_timeout":
        reports[-1]["timeout_seconds"] = float("nan")
    if fault:
        with pytest.raises(ValueError):
            verify_campaign_isolation(root, frozen, evaluated, manifest, "fixture")
    else:
        assert verify_campaign_isolation(root, frozen, evaluated, manifest, "fixture")["jobs_verified"] == len(reports)


@pytest.mark.parametrize("campaign_cap", [7, 10000])
def test_campaign_limits_children_to_study_policy_and_remaining_allocation(fixture_campaign, monkeypatch, campaign_cap):
    from validation import tier0_isolation, tier0_rank_campaign

    design, root, refs = fixture_campaign
    design["resource"]["campaign_cap_seconds"] = campaign_cap
    records = {}
    for ref in refs:
        record = read(ref)
        record["design_digest"] = canonical_digest(design)
        records[record["entry"], record["task"], record["seed"], record["arm"]] = record
    observed = []

    def isolated(_root, job, payload, *, timeout_seconds):
        observed.append((payload["operation"], timeout_seconds))
        if payload["operation"] == "search":
            output = records[tuple(payload[k] for k in ("entry", "task", "seed", "arm"))]
        else:
            output = {"seed": payload["seed"], "returns": [1.0] * 10}
        return {"path": job, "sha256": "0" * 64}, {"status": "complete", "output": output}

    monkeypatch.setattr(tier0_rank_campaign, "load_design", lambda path: design)
    monkeypatch.setattr(tier0_rank_campaign, "require_campaign_ready", lambda *args: None)
    monkeypatch.setattr(tier0_isolation, "run_isolated", isolated)
    # Launch-limit regression only: genuine subprocess/chronology tests and
    # the independent excessive-timeout rejection tests remain separate.
    monkeypatch.setattr(tier0_rank_campaign, "verify_campaign_isolation", lambda *args: {})
    monkeypatch.setattr(tier0_rank_campaign.time, "monotonic", lambda: 0.0)
    campaign("V05", root, design_path="fixture", phase="pilot")
    assert {operation for operation, _ in observed} == {"search", "protected"}
    assert all(timeout == min(campaign_cap, 12 if operation == "search" else 10)
               for operation, timeout in observed)


@pytest.mark.parametrize("phase,count,expected_searches", [("pilot", 46, 1), ("pilot", 100, 9),
                                                           ("confirmation", 20, 80)])
def test_pilot_search_failure_stops_only_when_fixed_sizing_is_futile(
        fixture_campaign, monkeypatch, phase, count, expected_searches):
    from validation import tier0_isolation, tier0_phase_contracts, tier0_rank_campaign

    design, root, _ = fixture_campaign
    design["sizing_policy"] = copy.deepcopy(tier0_phase_contracts.JOINT_SIZING_POLICY)
    design["sampling"]["selection_algorithm"] = tier0_phase_contracts.SAMPLING
    design["phase_freeze"] = None  # Inert launch fixture, never phase certification.
    design["seed_sets"][phase] = list(range(10000, 10000 + count))
    design["selected_counts"][phase] = {entry: count for entry in ARMS}
    seen = []

    def interrupted(_root, job, payload, *, timeout_seconds):
        seen.append(payload)
        assert payload["operation"] == "search"  # No protected workload may start.
        return {"path": job, "sha256": "0" * 64}, {"status": "interrupted", "output": None}

    monkeypatch.setattr(tier0_rank_campaign, "load_design", lambda path: design)
    monkeypatch.setattr(tier0_rank_campaign, "require_campaign_ready", lambda *args: None)
    monkeypatch.setattr(tier0_isolation, "run_isolated", interrupted)
    monkeypatch.setattr(tier0_phase_contracts, "campaign_directory", lambda *args: root)
    monkeypatch.setattr(tier0_rank_campaign, "verify_campaign_isolation", lambda *args: {})
    result = campaign("V04-T0", root, design_path="inert-fixture", phase=phase)
    assert len(seen) == expected_searches
    assert result["verdict"] == "INCONCLUSIVE" and result["certifies_acceptance"] is False
    assert result["planned_studies"] == count * 4
    bundle = read(result["search_freeze"])
    assert len(bundle["slots"]) == count * 4 and all(slot["search"] is None for slot in bundle["slots"])
    evaluation = read(result["protected_evaluations"])
    assert not evaluation["receipts"]
    assert evaluation["skipped_for_pilot_search_futility"] is (phase == "pilot")
    if phase == "pilot":
        # Multiple arms failing in the same vector count only once. At 100
        # vectors, two bad vectors still permit sizing; the third does not.
        assert result["pilot_search_futility"]["known_bad_vectors"] == (1 if count == 46 else 3)
    else:
        assert result["pilot_search_futility"] is None
    rebuilt = recompute_protected(root, result["search_freeze"], result["protected_evaluations"])
    assert rebuilt["entries"]["V04-T0"]["counts"]["loss_cap_void"]


def test_unjustified_protected_skip_is_rejected_from_frozen_artifacts(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen)
    report = read(evaluated)
    report["skipped_for_pilot_search_futility"] = True
    altered = write(root / "forged-skip.json", report)
    with pytest.raises(ValueError, match="independently reconstructed"):
        recompute_protected(root, frozen, altered)


def test_search_freeze_protected_scores_and_all_nine_components_recompute(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, calls = evaluate_fixture(root, frozen)
    report = recompute_protected(root, frozen, evaluated)
    assert len(calls) == 5 * (4 + 2) * 5
    assert len(set(calls)) == len(calls)
    assert report["cost"] == {"search_elapsed_seconds": 300, "protected_elapsed_seconds": 150,
                              "protected_policy_seconds": 150, "combined_measured_seconds": 450}
    assert report["budget_veto"] is False
    for entry, components in [("V04-T0", 8), ("V05", 1)]:
        result = report["entries"][entry]
        assert len(result["components"]) == components
        assert result["counts"]["independent_vectors"] == 5
        assert result["counts"]["loss_cap_void"] is False
        assert len(result["lower_rows"]) == 5
        assert all(value < 0 for row in result["lower_rows"] for value in row)
        assert result["verdict"] == "INCONCLUSIVE"
    assert report["certifies_acceptance"] is False
    assert all(row["search_values"] == [1, 2, 3, 4, 5] for row in report["raw_study_outcomes"])


def test_missing_whole_search_stays_in_denominator_and_voids_affected_entry(fixture_campaign):
    design, root, refs = fixture_campaign
    omitted = refs[0]
    frozen = freeze_search_bundle(design, root, refs[1:], entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen)
    report = recompute_protected(root, frozen, evaluated)
    entry = report["entries"][read(omitted)["entry"]]
    assert entry["counts"]["loss_cap_void"]
    assert entry["counts"]["unresolved_per_arm"][read(omitted)["arm"]] == 1
    assert len(entry["lower_rows"]) == 5
    assert entry["entry_p_value"] == 1


@pytest.mark.parametrize("mode", ["raises", "nonfinite"])
def test_all_test_episodes_retained_on_failure(fixture_campaign, mode):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, calls = evaluate_fixture(root, frozen, mode=mode)
    report = recompute_protected(root, frozen, evaluated)
    assert len(calls) == 150
    raw = read(read(evaluated)["receipts"][0]["receipt"])
    assert len(raw["returns"]) == design["tasks"][next(iter(design["tasks"]))]["settings"]["eval_episodes"]
    assert any(value is None for value in raw["returns"])
    for entry in report["entries"].values():
        assert entry["counts"]["loss_cap_void"]
        assert entry["entry_p_value"] == 1


def test_bad_evaluator_contract_is_an_integrity_failure(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    with pytest.raises(ValueError, match="Malformed protected"):
        evaluate_fixture(root, frozen, mode="drop_episode")
    assert not (root / "protected-stage/evaluations/manifest.json").exists()


def test_no_retries_or_refreeze_after_test_outcomes(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluate_fixture(root, frozen)
    with pytest.raises(FileExistsError):
        evaluate_fixture(root, frozen)
    with pytest.raises(FileExistsError):
        freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")


def test_real_evaluator_path_rechecks_phase_before_any_evaluation(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    with pytest.raises(ValueError, match="Incomplete Tier 0 design"):
        execute_protected_bundle(root, frozen, evaluator=lambda *args: pytest.fail("Uncertified evaluator called"),
                                 acceptance=True)
    assert not (root / "protected-stage/evaluations").exists()


def test_missing_or_changed_search_study_cannot_be_silently_dropped(fixture_campaign):
    design, root, refs = fixture_campaign
    with pytest.raises(ValueError, match="Duplicate or unplanned"):
        freeze_search_bundle(design, root, refs + [refs[0]], entries=list(ARMS), phase="pilot")
    record = read(refs[0])
    record["phase"] = "confirmation"
    refs[0] = write(Path(refs[0]["path"]), record)
    with pytest.raises(ValueError, match="phase or accounting"):
        freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    assert not (root / "protected-stage").exists()


def test_changes_to_unselected_policy_artifacts_also_block_test_execution(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    record = read(refs[0])
    Path(record["observations"][0]["artifact_refs"]["recipe"]["path"]).write_text("{}")
    with pytest.raises(ValueError, match="Changed"):
        evaluate_fixture(root, frozen)
    assert not (root / "protected-stage/evaluations").exists()


def test_cross_directory_policy_cannot_be_loaded_even_with_matching_hash(fixture_campaign, tmp_path):
    design, root, refs = fixture_campaign
    record = read(refs[0])
    outside = tmp_path.parent / "outside-policy-inert.pkl"
    outside.write_bytes(b"never execute")
    record["observations"][0]["artifact_refs"]["checkpoint"] = bind(outside)
    refs[0] = write(Path(refs[0]["path"]), record)
    with pytest.raises(ValueError, match="escapes"):
        freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    assert not (root / "protected-stage").exists()


def test_unclassified_interruption_preserves_prefix_and_bounds_later_grid(fixture_campaign):
    design, root, refs = fixture_campaign
    record = read(refs[0])
    record.update(status="failed", elapsed_seconds=5, failure="unclassified worker interruption")
    record["observations"] = record["observations"][:2]
    refs[0] = write(Path(refs[0]["path"]), record)
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen)
    report = recompute_protected(root, frozen, evaluated)
    outcome = report["raw_study_outcomes"][0]
    assert outcome["protected_curve"][:3] == [(False, None), (True, -1.0), (True, -1.0)]
    assert outcome["protected_curve"][3:] == [None] * 3


def test_remaining_cap_stops_new_work_and_missing_tests_remain_planned(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated = execute_protected_bundle(root, frozen,
                evaluator=lambda *a: pytest.fail("No allocation remains"), clock=lambda: 0.0,
                remaining_total_seconds=0)
    report = recompute_protected(root, frozen, evaluated)
    assert read(evaluated)["receipts"] == []
    assert all(entry["counts"]["loss_cap_void"] for entry in report["entries"].values())


def test_cost_overshoot_and_forged_summary_are_recomputed(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen, cap_increment=11)
    assert recompute_protected(root, frozen, evaluated)["budget_veto"]
    forged = read(evaluated)
    forged["elapsed_seconds"] = 0
    forged_ref = write(root / "forged-cost.json", forged)
    with pytest.raises(ValueError, match="omits measured"):
        recompute_protected(root, frozen, forged_ref)


def test_duplicate_receipts_and_changed_selected_plan_are_rejected(fixture_campaign):
    design, root, refs = fixture_campaign
    frozen = freeze_search_bundle(design, root, refs, entries=list(ARMS), phase="pilot")
    evaluated, _ = evaluate_fixture(root, frozen)
    duplicate = read(evaluated)
    duplicate["receipts"].append(duplicate["receipts"][0])
    with pytest.raises(ValueError, match="Duplicate protected"):
        recompute_protected(root, frozen, write(root / "duplicate.json", duplicate))
    bundle = read(frozen)
    plan = read(bundle["slots"][0]["plan"])
    plan["incumbent_indices"][-1] = 0
    bundle["slots"][0]["plan"] = write(root / "false-plan.json", plan)
    with pytest.raises(ValueError, match="reproduced"):
        recompute_protected(root, write(root / "false-freeze.json", bundle), evaluated)


def test_acceptance_dispatch_cannot_trust_pass_field_or_temporary_artifacts(tmp_path):
    assert decision("V05", {"schema_version": 3, "validation_id": "V05", "claim": "protected_paired_rank_finite_suite_v1",
                            "run_dir": str(tmp_path), "verdict": "PASS", "certifies_acceptance": True}) == "INCONCLUSIVE"
    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    design["status"] = "certified"
    with pytest.raises(ValueError, match="Incomplete"):
        require_campaign_ready(design, "pilot")
