import copy
import hashlib
import json
import math

import pytest

from validation.tier0_design import load_design
from validation.tier0_phase_contracts import KL_SIZING_POLICY, SIZING_POLICY
from validation.tier0_pilot_sizing import ideal_pilot_screen, kl_lower, size_pilot_vectors
from validation.tier0_rank_design import rank_components


def ideal_rows(n, grid):
    return {entry: [[1 - grid[1] if key[-1] == "anytime_win" else 1.0
                    for key in rank_components(entry)]] * n for entry in ("V04-T0", "V05")}


def test_kl_bound_covers_an_exact_nonbinary_law():
    n, error = 8, .05
    probabilities = (.2, .3, .5)
    actual_mean = .5 * probabilities[1] + probabilities[2]
    miss = 0.0
    for zeros in range(n + 1):
        for halves in range(n - zeros + 1):
            ones = n - zeros - halves
            lower = kl_lower((.5 * halves + ones) / n, n, error)
            if lower > actual_mean:
                miss += math.comb(n, zeros) * math.comb(n - zeros, halves) * math.prod(
                    p ** k for p, k in zip(probabilities, (zeros, halves, ones)))
    assert 0 < miss <= error
    assert kl_lower(1, n, error) == pytest.approx(error ** (1 / n))
    assert kl_lower(0, n, error) == 0


@pytest.mark.parametrize("n", [5, 20])
def test_ideal_small_pilot_is_futile_under_the_prespecified_rule(n):
    result = ideal_pilot_screen(n, load_design()["budget_grid"])
    assert result["verdict"] == "INFEASIBLE_UNDER_RULE"
    assert all(row["chosen_n"] is None for row in result["entries"].values())
    assert not result["certifies_acceptance"]


def test_sufficient_evidence_has_positive_sizing_route_and_bad_component_blocks_it():
    grid = load_design()["budget_grid"]
    rows = ideal_rows(1000, grid)
    losses = {entry: [False] * 1000 for entry in rows}
    result = size_pilot_vectors(rows, losses, grid, policy=SIZING_POLICY)
    assert result["verdict"] == "SIZED"
    assert all(5 <= row["chosen_n"] <= 20 for row in result["entries"].values())
    for item in result["entries"].values():
        selected = item["chosen_n"]
        assert next(r for r in item["frontier"] if r["n"] == selected)["power_lower_conditional_on_resources"] >= .8
        assert all(r["power_lower_conditional_on_resources"] < .8 for r in item["frontier"] if r["n"] < selected)
    rows = copy.deepcopy(rows)
    for row in rows["V04-T0"]:
        row[0] = 0
    result = size_pilot_vectors(rows, losses, grid, policy=SIZING_POLICY)
    assert result["verdict"] == "INFEASIBLE_UNDER_RULE"
    assert result["entries"]["V05"]["chosen_n"] is not None


def test_unresolved_vectors_cannot_be_dropped_to_get_power():
    grid = load_design()["budget_grid"]
    rows = ideal_rows(1000, grid)
    losses = {entry: [True] * 100 + [False] * 900 for entry in rows}
    result = size_pilot_vectors(rows, losses, grid, policy=SIZING_POLICY)
    assert result["verdict"] == "INFEASIBLE_UNDER_RULE"
    losses["V05"].pop()
    with pytest.raises(ValueError, match="planned pilot"):
        size_pilot_vectors(rows, losses, grid, policy=SIZING_POLICY)


@pytest.mark.parametrize("fault", ["nan", "support", "components", "boolean", "policy"])
def test_unsupported_inputs_refused(fault):
    grid = [0, .1, 1]
    rows = ideal_rows(5, grid)
    rows = copy.deepcopy(rows)
    policy = copy.deepcopy(SIZING_POLICY)
    if fault == "nan":
        rows["V05"][0][0] = math.nan
    elif fault == "support":
        rows["V04-T0"][0][1] = 1.0
    elif fault == "components":
        rows["V05"][0].append(1)
    elif fault == "boolean":
        rows["V05"][0][0] = True
    else:
        policy["planning_error"] = .5
    with pytest.raises(ValueError):
        size_pilot_vectors(rows, {entry: [False] * 5 for entry in rows}, grid, policy=policy)


@pytest.fixture
def sizing_bridge(tmp_path, monkeypatch):
    """Exercise the receipt bridge using already-verified raw-layer fixtures.

    Raw artifact/process reconstruction has independent integration tests. This
    isolates compatibility, chronology, resource and sizing decisions at their
    interface; the synthetic records are never treated as campaign evidence.
    """
    from validation import tier0_rank_campaign, tier0_phase_contracts, tier0_isolation
    from validation.tier0_phase_contracts import experiment_digest

    design = load_design()
    design["seed_sets"]["pilot"] = list(range(1000))
    design["selected_counts"] = {"pilot": {e: 1000 for e in ("V04-T0", "V05")},
                                 "confirmation": {"V04-T0": 11, "V05": 11}}
    design["sizing_policy"] = copy.deepcopy(SIZING_POLICY)
    design["resource"].update(campaign_cap_seconds=1600, protected_cap_seconds=800)
    pilot = copy.deepcopy(design)
    pilot["resource"].update(campaign_cap_seconds=100000, protected_cap_seconds=50000)
    verified = []
    raw = {}

    def bind(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    refs = {}
    for entry in ("V04-T0", "V05"):
        result = {"phase": "pilot", "run_dir": entry, "search_freeze": {}, "protected_evaluations": {},
                  "process_isolation": {}, "duration_seconds": 1000, "verdict": "PASS"}
        refs[entry] = bind(entry + ".json", result)
        raw[entry] = {"entries": {entry: {"lower_rows": ideal_rows(1000, design["budget_grid"])[entry]}},
                      "raw_study_outcomes": [{"identity": [entry, "task", seed, "arm"], "unresolved": False} for seed in range(1000)],
                      "budget_veto": False}
    receipt = {"kind": "independent_pilot_rank_sizing_receipt_v1", "experiment_digest": experiment_digest(design),
               "pilot_results": refs, "verdict": "FAIL", "chosen_n": 5}  # Labels ignored.
    design["sizing_receipt"] = bind("sizing.json", receipt)
    monkeypatch.setattr(tier0_rank_campaign, "recompute_result", lambda entry, result: verified.append(entry))
    monkeypatch.setattr(tier0_rank_campaign, "_load_bundle", lambda *args: ({}, pilot, []))
    monkeypatch.setattr(tier0_rank_campaign, "_read", lambda *args: {"processes": []})
    monkeypatch.setattr(tier0_rank_campaign, "recompute_protected", lambda root, *args: raw[root])
    monkeypatch.setattr(tier0_isolation, "verify_sequence", lambda *args, **kwargs:
                        [{"finish_ns": 10, "observer": {"boot_id": "fixture"}}])
    monkeypatch.setattr(tier0_phase_contracts, "verify_phase_freeze", lambda *args:
                        {"recorded_ns": 20, "boot_id": "fixture"})
    return design, pilot, raw, receipt, bind, verified, tmp_path


def test_receipt_bridge_selects_from_reconstructed_vectors_not_supplied_labels(sizing_bridge):
    from validation.tier0_pilot_sizing import verify_sizing_receipt

    design, _, _, _, _, verified, root = sizing_bridge
    report = verify_sizing_receipt(design, "confirmation", root)
    assert report["verdict"] == "SIZED"
    assert verified == ["V04-T0", "V05"]
    assert report["entries"]["V05"]["chosen_n"] == 11


@pytest.mark.parametrize("fault", ["count", "experiment", "loss", "raw_cost", "allocation", "reuse", "tamper", "chronology"])
def test_receipt_bridge_refuses_reuse_incompatible_data_and_favorable_relabeling(sizing_bridge, monkeypatch, fault):
    from validation.tier0_pilot_sizing import verify_sizing_receipt
    from validation import tier0_phase_contracts

    design, pilot, raw, receipt, bind, _, root = sizing_bridge
    if fault == "count":
        design["selected_counts"]["confirmation"]["V05"] = 20
        design["resource"].update(campaign_cap_seconds=2000, protected_cap_seconds=1000)
    elif fault == "experiment":
        pilot["budget_grid"] = [0, .5, 1]
    elif fault == "loss":
        for row in raw["V05"]["raw_study_outcomes"]:
            row["unresolved"] = True
    elif fault == "raw_cost":
        raw["V05"]["budget_veto"] = True
    elif fault == "allocation":
        design["resource"]["protected_cap_seconds"] = 1
    elif fault == "reuse":
        receipt["pilot_results"]["V05"] = bind("reused.json", {"phase": "confirmation", "verdict": "PASS"})
        design["sizing_receipt"] = bind("changed-sizing.json", receipt)
    elif fault == "tamper":
        (root / "V05.json").write_text('{}')
    else:
        monkeypatch.setattr(tier0_phase_contracts, "verify_phase_freeze", lambda *args:
                            {"recorded_ns": 5, "boot_id": "fixture"})
    with pytest.raises(ValueError):
        verify_sizing_receipt(design, "confirmation", root)


def test_loss_bound_uses_the_exact_registered_ten_percent_allowance():
    from scipy.stats import binom

    report = ideal_pilot_screen(277, load_design()["budget_grid"], policy=KL_SIZING_POLICY)
    assert report["verdict"] == "SIZED"
    assert ideal_pilot_screen(276, load_design()["budget_grid"], policy=KL_SIZING_POLICY)["verdict"] == "INFEASIBLE_UNDER_RULE"
    for item in report["entries"].values():
        q = item["unresolved_probability_upper"]
        for row in item["frontier"]:
            n = row["n"]
            assert row["unresolved_veto_upper"] == pytest.approx(binom.sf(n // 10, n, q))
            # This is an upper bound for the per-arm veto even when a bad
            # vector loses every task in the same arm; exactly 10% is allowed.
            assert row["unresolved_veto_upper"] <= min(1, n * q)
