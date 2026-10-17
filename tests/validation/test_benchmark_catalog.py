"""Real-source parsing and refusal checks; no optimization or training runs."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from validation.benchmark_catalog import LandscapeTable, lcbench_instances, verify_source_bundle


def write_table(tmp_path, rows):
    path = tmp_path / "landscape.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.learning_rate"])
        writer.writerows(rows)
    return path


def test_lookup_retains_missing_cells_without_interpolation_or_invented_cost(tmp_path):
    table = LandscapeTable(write_table(tmp_path, [
        [0, 0, 10, 2, .01], [0, 0, 20, "", .01],
        [0, 1, 10, 5, .01], [0, 1, 20, "NaN", .01],
        [1, 0, 10, 6, .03], [1, 0, 20, -1e20, .03],
    ]))
    assert table.lookup(0, 0, 20)["status"] == "blank"
    assert table.lookup(0, 1, 20)["status"] == "nonfinite"
    assert table.lookup(1, 0, 20)["value"] == -1e20
    assert table.lookup(1, 0, 20)["cost_seconds"] is None
    with pytest.raises(ValueError, match="off-table"):
        table.lookup(1, 1, 20)
    report = table.profile()
    assert report["terminal_statuses"] == {"absent": 1, "blank": 1, "finite": 1, "nonfinite": 1}
    assert report["terminal_missing_fraction"] == .75
    assert report["absent_grid_cells"] == 2
    assert report["independent_hpo_studies"] == 0
    assert not report["provides_population_support_bound"]


@pytest.mark.parametrize("extra,match", [
    ([0, 0, 10, 1, .01], "Duplicate"),
    ([0, 1, 10, 1, .02], "Configuration changes"),
    ([-1, 0, 10, 1, .01], "config ID"),
    ([1, 0, 0, 1, .01], "training steps"),
    ([1, 0, 10, 1, "NaN"], "Nonfinite physical"),
])
def test_malformed_landscape_is_refused(tmp_path, extra, match):
    with pytest.raises(ValueError, match=match):
        LandscapeTable(write_table(tmp_path, [[0, 0, 10, 1, .01], extra]))


def test_source_bundle_detects_changes_and_escape(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("external source\n")
    source = {"path": path.name, "url": "https://example.org/pinned/source", "revision": "pinned-revision",
              "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"schema_version": 1, "kind": "benchmark-source-bundle", "sources": [source]}
    receipt = tmp_path / "manifest.json"
    receipt.write_text(json.dumps(manifest))
    assert verify_source_bundle(receipt)[path.name] == path
    path.write_text("changed source\n")
    with pytest.raises(ValueError, match="Changed benchmark source"):
        verify_source_bundle(receipt)
    source["path"] = "../outside.csv"
    receipt.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid"):
        verify_source_bundle(receipt)


def test_lcbench_eligibility_uses_configuration_domain_not_embedding_vocab(tmp_path):
    space, encoding = tmp_path / "space.json", tmp_path / "encoding.json"
    space.write_text(json.dumps({"hyperparameters": [
        {"name": "OpenML_task_id", "type": "categorical", "choices": ["34", "2"]}]}))
    encoding.write_text(json.dumps({"OpenML_task_id": {"#na#": 0, "2": 1, "34": 2, "99": 3}}))
    result = lcbench_instances(space, encoding)
    assert result["instances"] == ["2", "34"]
    assert result["encoding_only_ids"] == ["99"]
    assert not result["supports_live_ppo_claim"]


def test_pinned_external_sources_and_landscape_failure_counts():
    root = Path(__file__).resolve().parents[2] / "docs/program/evidence/2026-09-29/stat-03/task-sources"
    sources = verify_source_bundle(root / "manifest.json")
    expected_missing = {"ant": 2, "halfcheetah": 771, "hopper": 0, "humanoid": 0}
    for env, missing in expected_missing.items():
        report = LandscapeTable(sources[f"arlbench_landscape_{env}_ppo.csv"]).profile()
        assert report["rows"] == 25600
        assert report["configurations"] == 256
        assert report["terminal_expected_cells"] == 2560
        assert sum(n for status, n in report["terminal_statuses"].items() if status != "finite") == missing
        assert report["terminal_training_steps"] == 50000000
        assert report["terminal_finite_min"] < -1e10
        assert not report["scale_adopted"]
    instances = lcbench_instances(sources["yahpo_lcbench_config_space.json"], sources["yahpo_lcbench_encoding.json"])
    assert len(instances["instances"]) == 34
    assert instances["encoding_only_ids"] == ["167083"]
