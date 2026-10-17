"""Independent recorded-curve scheduler traces and evidence corruption."""

import copy
import csv

import pytest

from validation.benchmark_catalog import LandscapeTable
from validation.tabular_projection import FiniteLandscapeProjection
from validation.v01_scheduler_traces import compare_scheduler_table_traces, verify_scheduler_table_traces


def projection(tmp_path, *, missing=False):
    path = tmp_path / "curves.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.x"])
        for index in range(41):
            for step in range(1, 11):
                score = (index if step < 3 else -index) + .01 * step
                writer.writerow([index, 1, 100 * step, "" if missing else score, index / 40])
    return FiniteLandscapeProjection(LandscapeTable(path))


@pytest.mark.parametrize("component", ["ASHA", "Median", "PASHA"])
def test_independent_scheduler_loops_reconstruct_recorded_cells(tmp_path, component, monkeypatch):
    import validation.v01_scheduler_traces as traces

    table = projection(tmp_path)
    report = compare_scheduler_table_traces(table, component, optimizer_seed=23, table_seed=1, count=30)
    assert report["comparison"]["exact_trace_agreement"]
    assert report["comparison"]["complete_traces"]
    assert report["comparison"]["certifies_distributional_equivalence"] is False
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["certifies_acceptance"] is False
    # Verification regenerates the independent reference without invoking the
    # tested scheduler or accepting producer decisions as the oracle.
    monkeypatch.setattr(traces, "_Wrapper", lambda *args: pytest.fail("wrapper used as oracle"))
    assert verify_scheduler_table_traces(table, report) == report["comparison"]
    rows = report["actual"]["rows"]
    assert any(row["kind"] == "new" for row in rows)
    if component != "Median":
        assert any(row["kind"] == "promotion" for row in rows)
    else:
        assert any(row["kind"] == "report" and row["decision"] == "stop" and row["step"] < 10 for row in rows)


@pytest.mark.parametrize("component", ["ASHA", "Median", "PASHA"])
def test_missing_cell_is_visible_without_imputation_or_favorable_replacement(tmp_path, component):
    table = projection(tmp_path, missing=True)
    report = compare_scheduler_table_traces(table, component, optimizer_seed=23, table_seed=1, count=30)
    for trace in (report["actual"], report["reference"]):
        assert trace["status"] == "unresolved_cell"
        assert trace["roots_started"] == 1
        assert trace["rows"][-1]["value"] is None
    assert not report["comparison"]["complete_traces"]
    assert report["certifies_acceptance"] is False


@pytest.mark.parametrize("fault", ["value", "decision", "drop", "cap", "proposal", "recipe", "source"])
def test_corrupt_both_copies_and_matching_summaries_still_cannot_pass(tmp_path, fault):
    table = projection(tmp_path)
    report = compare_scheduler_table_traces(table, "PASHA", optimizer_seed=23, table_seed=1, count=20)
    report = copy.deepcopy(report)
    for trace in (report["actual"], report["reference"]):
        row = next(row for row in trace["rows"] if row["kind"] == "report")
        if fault == "drop":
            trace["rows"].pop()
        elif fault == "recipe":
            report["recipe"]["root_count"] += 1
        elif fault == "source":
            report["reference_sources"]["hyperband_pasha.py"] = "0" * 64
        elif fault == "proposal":
            row["proposal"] = [0]
        else:
            row[fault] = "continue" if fault == "decision" else 99999
    with pytest.raises(ValueError):
        verify_scheduler_table_traces(table, report)


def test_wrong_wrapper_behavior_exposes_its_own_diverging_trajectory(tmp_path, monkeypatch):
    import validation.v01_scheduler_traces as traces

    table = projection(tmp_path)
    monkeypatch.setattr(traces._Wrapper, "schedule", lambda self: None)
    report = compare_scheduler_table_traces(table, "ASHA", optimizer_seed=23, table_seed=1, count=20)
    assert not report["comparison"]["exact_trace_agreement"]
    assert report["comparison"]["mismatch_indices"]
    assert not report["comparison"]["equal_trace_lengths"]
