import csv
import math

import numpy as np
import pytest

from validation.benchmark_catalog import LandscapeTable
from validation.tabular_projection import FiniteLandscapeProjection


def table(tmp_path, rows=None):
    path = tmp_path / "landscape.csv"
    rows = rows or [(8, 1, 10, "3", .001, 0, True, 4),
                    (2, 1, 10, "", .1, 1, False, 4),
                    (8, 1, 20, "-100000000000000000000", .001, 0, True, 4),
                    (2, 1, 20, "nan", .1, 1, False, 4)]
    with path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.rate",
                         "hp_config.width", "hp_config.normalized", "hp_config.constant"])
        writer.writerows(rows)
    return LandscapeTable(path)


def test_exact_table_roundtrip_and_absent_runtime(tmp_path):
    source = table(tmp_path)
    projection = FiniteLandscapeProjection(source, log_columns=["hp_config.rate"])
    assert len(projection.coordinates) == 3
    assert projection.specification["constants"] == {"hp_config.constant": 4.0}
    for index, config_id in enumerate(projection.ids):
        item = projection.evaluate(projection.points[index], seed=1, training_steps=10)
        assert item["config_id"] == config_id
        assert item["physical_config"] == source.configurations[config_id]
        assert item["squared_distance"] == 0
        assert item["cost_seconds"] is None
        assert item["certifies_acceptance"] is False
        assert item["interpolated"] is False


def test_midpoint_uses_declared_tie_break_not_best_reward(tmp_path):
    projection = FiniteLandscapeProjection(table(tmp_path), log_columns=["hp_config.rate"])
    result = projection.evaluate([.5, .5, .5], seed=1, training_steps=10)
    assert result["config_id"] == 2
    assert result["status"] == "blank"
    assert result["value"] is None
    assert projection.evaluate([.5, .5, .5], seed=1, training_steps=20)["status"] == "nonfinite"


def test_geometry_and_selection_do_not_depend_on_objective_outcomes(tmp_path):
    first = FiniteLandscapeProjection(table(tmp_path), log_columns=["hp_config.rate"])
    second = FiniteLandscapeProjection(table(tmp_path, [(8, 1, 10, "-1e200", .001, 0, True, 4),
                                                       (2, 1, 10, "1e200", .1, 1, False, 4)]),
                                       log_columns=["hp_config.rate"])
    np.testing.assert_array_equal(first.points, second.points)
    for proposal in ([0, 0, 0], [.5, .5, .5], [.8, .7, .2], [1, 1, 1]):
        assert first.project(proposal)["config_id"] == second.project(proposal)["config_id"]
    # Reward edits do change provenance even though geometry is invariant.
    assert first.digest != second.digest


@pytest.mark.parametrize("proposal", [[], [0], [0, 0, 0, 0], [True, False, True],
                                       [0, math.nan, 0], [0, math.inf, 0], [-.01, 0, 0],
                                       [1.01, 0, 0], [[0, 0, 0]], ["0", "0", "0"]])
def test_invalid_proposal_is_not_clipped_or_coerced(tmp_path, proposal):
    projection = FiniteLandscapeProjection(table(tmp_path))
    with pytest.raises(ValueError):
        projection.project(proposal)


def test_unknown_cells_stay_unavailable_and_invalid_log_geometry_is_refused(tmp_path):
    source = table(tmp_path)
    projection = FiniteLandscapeProjection(source)
    with pytest.raises(ValueError, match="No recorded cell"):
        projection.evaluate([0, 0, 0], seed=17, training_steps=10)
    for columns in (["missing"], ["hp_config.rate", "hp_config.rate"], ["hp_config.width"], ["hp_config.normalized"]):
        with pytest.raises(ValueError):
            FiniteLandscapeProjection(source, log_columns=columns)
