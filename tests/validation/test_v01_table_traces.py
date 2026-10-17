"""Short independent vendor loops on artificial recorded tables; no acceptance."""

import copy
import csv

import pytest

from validation.benchmark_catalog import LandscapeTable
from validation.tabular_projection import FiniteLandscapeProjection
from validation.v01_table_traces import compare_table_traces, reconstruct_reference, verify_table_traces


def table(tmp_path, *, missing=False):
    path = tmp_path / "artificial.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.x", "hp_config.y"])
        for i in range(5):
            for j in range(5):
                x, y = i / 4, j / 4
                writer.writerow([5 * i + j, 1, 10, "" if missing else -((x - .25)**2 + (y - .75)**2), x, y])
    return FiniteLandscapeProjection(LandscapeTable(path))


@pytest.mark.parametrize("component,count", [("Random", 8), ("Sobol", 8), ("TPE", 12),
                                             ("CMA-ES", 12), ("GP", 6), ("LegacyGP", 3)])
def test_both_actors_execute_their_own_projected_table_loop(tmp_path, component, count, monkeypatch):
    projection = table(tmp_path)
    report = compare_table_traces(projection, component, optimizer_seed=23,
                                  table_seed=1, training_steps=10, count=count)
    result = report["comparison"]
    assert result["complete_traces"] and result["exact_cell_agreement"]
    assert result["maximum_absolute_proposal_difference"] < 1e-10
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["certifies_acceptance"] is False
    assert result["certifies_distributional_equivalence"] is False
    assert len(report["actual"]["rows"]) == len(report["reference"]["rows"]) == count
    assert verify_table_traces(projection, report) == result
    import validation.v01_table_traces as traces

    monkeypatch.setattr(traces, "_wrapper", lambda *args: pytest.fail("wrapper used as oracle"))
    assert reconstruct_reference(projection, report) == result


def test_matching_fabricated_paths_with_valid_table_cells_are_rejected(tmp_path):
    projection = table(tmp_path)
    report = compare_table_traces(projection, "Random", optimizer_seed=23,
                                  table_seed=1, training_steps=10, count=8)
    for name in ("actual", "reference"):
        report[name]["rows"][0] = {"index": 0, **projection.evaluate([0., 0.], seed=1, training_steps=10)}
    assert verify_table_traces(projection, report)["exact_cell_agreement"]
    with pytest.raises(ValueError, match="independently reconstructed"):
        reconstruct_reference(projection, report)


def test_wrong_vendor_proposal_changes_its_own_recorded_outcome(tmp_path, monkeypatch):
    import validation.v01_table_traces as traces

    projection = table(tmp_path)
    monkeypatch.setattr(traces, "_vendor", lambda *args: (lambda: [0., 0.], lambda *args: None))
    report = compare_table_traces(projection, "Random", optimizer_seed=23,
                                  table_seed=1, training_steps=10, count=8)
    assert report["comparison"]["cell_mismatch_indices"]
    assert not report["comparison"]["exact_cell_agreement"]
    assert all(row["config_id"] == 0 for row in report["reference"]["rows"])
    assert any(row["config_id"] != 0 for row in report["actual"]["rows"])


def test_missing_table_cell_stops_without_imputation_or_replacement(tmp_path):
    projection = table(tmp_path, missing=True)
    report = compare_table_traces(projection, "TPE", optimizer_seed=23,
                                  table_seed=1, training_steps=10, count=12)
    for name in ("actual", "reference"):
        assert report[name]["status"] == "unresolved_cell"
        assert len(report[name]["rows"]) == 1
        assert report[name]["rows"][0]["value"] is None
    assert not report["comparison"]["complete_traces"]
    assert report["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("fault", ["value", "config_id", "drop", "recipe", "repeat"])
def test_changed_raw_table_evidence_cannot_hide_behind_summary(tmp_path, fault):
    projection = table(tmp_path)
    report = compare_table_traces(projection, "Random", optimizer_seed=23,
                                  table_seed=1, training_steps=10, count=8)
    report = copy.deepcopy(report)
    if fault in {"value", "config_id"}:
        report["reference"]["rows"][0][fault] = 99999
    elif fault == "drop":
        report["reference"]["rows"].pop()
    elif fault == "recipe":
        report["reference"]["optimizer_seed"] += 1
    else:
        report["reference"]["rows"][1] = report["reference"]["rows"][0]
    with pytest.raises(ValueError):
        verify_table_traces(projection, report)
