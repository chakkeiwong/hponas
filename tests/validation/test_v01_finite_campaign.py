"""Finite acceptance decisions and adversarial raw evidence, on artificial data."""

import copy
import csv
import json

import pytest

from validation.evidence import decision
from validation.v01_contract import RULE, SCOPE, REFERENCES, SEARCHERS, SCHEDULERS, binding, case_inventory
import validation.v01_contract as contract_module
import validation.v01_finite_campaign as campaign_module


@pytest.fixture
def artificial(tmp_path, monkeypatch):
    """Only tests substitute the authorized corpus; production loads exact bytes."""
    source = tmp_path / "curves.csv"
    with source.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.x"])
        for index in range(21):
            for step in range(1, 11):
                writer.writerow([index, 0, 100 * step, index + step / 100, index / 20])
    corpus = {"kind": "v01_finite_corpus", "schema_version": 2, "scope": SCOPE,
              "components": list(SEARCHERS + SCHEDULERS), "references": REFERENCES, "rule": RULE,
              "tables": [{"id": "artificial", "source": binding(source, tmp_path), "table_seed": 0,
                          "role": "original", "expected_missing": {}}],
              "optimizer_seeds": [23], "searcher_counts": {name: 2 for name in SEARCHERS},
              "scheduler_root_count": 6, "log_columns": [],
              "resource": {"maximum_elapsed_seconds": 600, "threads": 1, "device": "cpu"}}
    corpus["searcher_counts"]["LegacyGP"] = 1
    corpus_ref = campaign_module._write(tmp_path, "corpus.json", corpus)
    frozen = {"kind": "v01_frozen_finite_contract", "scope": SCOPE, "schema_version": 1,
              "source_digest": "f" * 64, "corpus": corpus_ref, "cases": case_inventory(corpus)}
    monkeypatch.setattr(campaign_module, "ROOT", tmp_path)
    monkeypatch.setattr(contract_module, "ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "_file", lambda ref: contract_module._file(ref, tmp_path))
    monkeypatch.setattr(campaign_module, "prepare_contract", lambda: copy.deepcopy(frozen))
    monkeypatch.setattr(contract_module, "prepare_contract", lambda: copy.deepcopy(frozen))
    return tmp_path, corpus, frozen


def _read(root, ref):
    return json.loads((root / ref["path"]).read_text())


def _replace(root, ref, value):
    path = root / ref["path"]
    path.write_text(json.dumps(value, allow_nan=False))
    return binding(path, root)


def _mutate_record(result, function, index=0):
    from pathlib import Path

    root = Path(result["run_dir"])
    execution = _read(root, result["execution"])
    record = _read(root, execution["cases"][index])
    function(root, record)
    execution["cases"][index] = _replace(root, execution["cases"][index], record)
    result["execution"] = _replace(root, result["execution"], execution)


def test_complete_artificial_inventory_passes_without_producer_verdict(artificial):
    root, _, _ = artificial
    result = campaign_module.campaign(root)
    assert result["recomputed"]["complete_cases"] == 9
    assert result["recomputed"]["verdict"] == "PASS"
    result["recomputed"] = {"verdict": "FAIL"}
    result["passed"], result["verdict"] = False, "FAIL"
    assert decision("V01", result) == "PASS"
    with pytest.raises(FileExistsError):
        campaign_module.campaign(root)


@pytest.mark.parametrize("fault", ["drop", "duplicate", "reorder", "source", "contract", "raw_hash", "recipe", "chronology"])
def test_corrupt_inventory_or_binding_cannot_certify(artificial, fault):
    from pathlib import Path

    root, _, frozen = artificial
    result = campaign_module.campaign(root)
    run = Path(result["run_dir"])
    execution = _read(run, result["execution"])
    if fault in {"drop", "duplicate", "reorder"}:
        if fault == "drop":
            execution["cases"].pop()
        elif fault == "duplicate":
            execution["cases"][1] = execution["cases"][0]
        else:
            execution["cases"].reverse()
        result["execution"] = _replace(run, result["execution"], execution)
    elif fault == "source":
        frozen["source_digest"] = "a" * 64
    elif fault == "contract":
        altered = _read(run, result["contract"])
        altered["cases"].pop()
        result["contract"] = _replace(run, result["contract"], altered)
    else:
        def change(base, record):
            if fault == "raw_hash":
                raw = _read(base, record["report"])
                raw["reference"]["rows"][0]["value"] += 1
                _replace(base, record["report"], raw)  # Intentionally retain old binding.
            elif fault == "recipe":
                record["case"]["optimizer_seed"] += 1
            else:
                record["start_ns"] = 1
        _mutate_record(result, change)
    with pytest.raises(ValueError):
        decision("V01", result)


def test_changed_original_table_cannot_certify_even_if_summary_claims_pass(artificial):
    root, _, _ = artificial
    result = campaign_module.campaign(root)
    source = root / "curves.csv"
    source.write_text(source.read_text().replace(",0,100,0.01,", ",0,100,999.0,"))
    with pytest.raises(ValueError, match="Changed V01 input bytes"):
        decision("V01", result)


@pytest.mark.parametrize("fault", ["value", "both_paths"])
def test_matching_forged_reports_do_not_bypass_reference_reconstruction(artificial, fault):
    root, corpus, _ = artificial
    result = campaign_module.campaign(root)

    def change(base, record):
        raw = _read(base, record["report"])
        for name in ("actual", "reference"):
            if fault == "value":
                raw[name]["rows"][0]["value"] = 999.
            else:
                projection = campaign_module._projection(corpus, record["case"])
                raw[name]["rows"][0] = {"index": 0, **projection.evaluate([0.], seed=0, training_steps=1000)}
        record["report"] = _replace(base, record["report"], raw)
    _mutate_record(result, change)
    with pytest.raises(ValueError):
        decision("V01", result)


def test_missing_execution_is_inconclusive_and_does_not_hide_discrepancy(artificial):
    root, corpus, _ = artificial
    result = campaign_module.campaign(root)

    def lose_execution(base, record):
        del record["report"]
        record.update(state="execution_error", error={"type": "RuntimeError", "message": "retained cause"})
    _mutate_record(result, lose_execution, index=1)
    assert decision("V01", result) == "INCONCLUSIVE"

    def disagree(base, record):
        raw = _read(base, record["report"])
        projection = campaign_module._projection(corpus, record["case"])
        raw["actual"]["rows"][0] = {"index": 0, **projection.evaluate([0.], seed=0, training_steps=1000)}
        record["report"] = _replace(base, record["report"], raw)
    _mutate_record(result, disagree)
    assert decision("V01", result) == "FAIL"


def test_retained_missing_cells_are_inconclusive(artificial, monkeypatch):
    root, corpus, frozen = artificial
    source = root / "curves.csv"
    rows = list(csv.reader(source.open()))
    for row in rows[1:]:
        row[3] = ""
    with source.open("w", newline="") as handle:
        csv.writer(handle).writerows(rows)
    corpus["tables"][0]["source"] = binding(source, root)
    frozen["corpus"] = _replace(root, frozen["corpus"], corpus)
    result = campaign_module.campaign(root)
    assert result["recomputed"]["observed_cases"] == 9
    assert result["recomputed"]["complete_cases"] == 0
    assert decision("V01", result) == "INCONCLUSIVE"
    assert all(row["observations"]["actual"]["missing_cells"] for row in result["recomputed"]["cases"])


@pytest.mark.parametrize("fault", [None, "wrong_cell", "lost_execution", "forged_completion"])
def test_only_frozen_exact_missing_refusals_satisfy_coverage(artificial, fault):
    root, corpus, frozen = artificial
    source = root / "curves.csv"
    rows = list(csv.reader(source.open()))
    for row in rows[1:]:
        row[3] = ""
    with source.open("w", newline="") as handle:
        csv.writer(handle).writerows(rows)
    corpus["tables"][0]["source"] = binding(source, root)
    # Test-only preparation of the expected source cells precedes the freeze.
    for case in case_inventory(corpus):
        projection = campaign_module._projection(corpus, case)
        kwargs = dict(optimizer_seed=23, table_seed=0, count=case["count"])
        if case["component"] in SEARCHERS:
            raw = campaign_module.compare_table_traces(projection, case["component"], training_steps=1000, **kwargs)
        else:
            raw = campaign_module.compare_scheduler_table_traces(projection, case["component"], **kwargs)
        last = raw["reference"]["rows"][-1]
        corpus["tables"][0]["expected_missing"][f"23/{case['component']}"] = {
            key: last[key] for key in ("config_id", "seed", "training_steps", "status")}
    if fault == "wrong_cell":
        corpus["tables"][0]["expected_missing"]["23/Random"]["config_id"] += 1
    frozen["cases"] = case_inventory(corpus)
    frozen["corpus"] = _replace(root, frozen["corpus"], corpus)
    result = campaign_module.campaign(root)
    if fault == "lost_execution":
        def lose(base, record):
            del record["report"]
            record.update(state="execution_error", error={"type": "RuntimeError", "message": "retained"})
        _mutate_record(result, lose)
    if fault == "forged_completion":
        def forge(base, record):
            raw = _read(base, record["report"])
            raw["actual"]["status"] = raw["reference"]["status"] = "complete"
            record["report"] = _replace(base, record["report"], raw)
        _mutate_record(result, forge)
        with pytest.raises(ValueError):
            decision("V01", result)
    else:
        assert decision("V01", result) == ("PASS" if fault is None else "INCONCLUSIVE")
        assert result["recomputed"]["complete_cases"] == 0
        if fault is None:
            assert result["recomputed"]["verified_missing_refusals"] == 9
            assert len(result["recomputed"]["incomplete_cases"]) == 9


def test_cap_overshoot_vetoes_pass_and_premature_cap_omission_is_invalid(artificial):
    from pathlib import Path

    root, _, _ = artificial
    result = campaign_module.campaign(root)
    run = Path(result["run_dir"])
    execution = _read(run, result["execution"])
    opening = _read(run, execution["opening"])
    execution["finish_ns"] = opening["frozen_ns"] + 601_000_000_000
    result["execution"] = _replace(run, result["execution"], execution)
    assert decision("V01", result) == "INCONCLUSIVE"

    def skip(base, record):
        del record["report"]
        record["state"] = "resource_cap"
    _mutate_record(result, skip)
    with pytest.raises(ValueError, match="resource-cap omission"):
        decision("V01", result)


def test_incumbents_use_earliest_tie_and_do_not_mix_fidelities():
    rows = [{"kind": "report", "trial_id": tid, "status": "finite", "training_steps": fidelity,
             "value": value, "config_id": config} for tid, fidelity, value, config in
            [("0", 100, 100., 9), ("1", 100, 100., 2), ("0", 200, 2., 9), ("1", 200, 4., 2)]]
    result = campaign_module.observables({"rows": rows}, scheduler=True, maximum=200, resource_unit=100)
    assert result["anytime"][1]["incumbent"]["config_id"] == 9
    assert result["final_incumbent"]["config_id"] == 2
    assert result["final_incumbent"]["score"] == 4.
    assert result["recorded_training_steps_consumed"] == 400


def test_live_authorized_contract_retains_all_prior_tables_and_nine_components():
    frozen = contract_module.prepare_contract()
    assert len(frozen["cases"]) == 45
    assert {case["table"] for case in frozen["cases"]} == {"ant", "halfcheetah", "hopper", "humanoid", "halfcheetah-complete"}
    assert sum(case["expected_missing"] is not None for case in frozen["cases"]) == 9
    assert frozen["coverage"]["configurations"] == 187
    assert {case["component"] for case in frozen["cases"]} == set(SEARCHERS + SCHEDULERS)
    assert frozen["rule"] == RULE
