"""Supplement membership must follow all original fidelities, never rewards."""

import copy
import csv
import json
from pathlib import Path

import pytest

from validation.v01_contract import RULE, CORPUS, binding, case_inventory
from validation.v01_data_coverage import complete_domain_bytes, verify_complete_domain, verify_coverage_extension


@pytest.fixture
def domain(tmp_path):
    source = tmp_path / "original.csv"
    with source.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["config_id", "seed", "training_steps", "performance", "hp_config.x"])
        for config in range(4):
            for seed in (0, 1):
                for fidelity in (100, 200, 300):
                    value = -1000 if config == 0 else config * 100
                    if (seed, config, fidelity) in {(0, 1, 100), (0, 2, 200), (1, 0, 300)}:
                        value = ""
                    writer.writerow([config, seed, fidelity, value, config / 3])
    ids, fidelities, data = complete_domain_bytes(source, 0)
    derived = tmp_path / "derived.csv"
    derived.write_bytes(data)
    row = {"id": "supplement", "table_seed": 0, "role": "complete_domain", "source": binding(derived, tmp_path),
           "expected_missing": {}, "derivation": {"rule": RULE["complete_domain"],
           "original_source": binding(source, tmp_path), "configuration_ids": ids, "fidelities": fidelities}}
    return tmp_path, row


def test_complete_domain_includes_worst_score_and_all_original_fidelities(domain):
    root, row = domain
    assert row["derivation"]["configuration_ids"] == [0, 3]
    assert verify_complete_domain(row, root)["fidelities"] == [100, 200, 300]


@pytest.mark.parametrize("fault", ["subset", "values", "order", "fidelity", "seed", "exception"])
def test_self_consistent_hashes_do_not_allow_changed_derivation(domain, fault):
    root, row = domain
    if fault in {"subset", "values", "order"}:
        path = root / row["source"]["path"]
        rows = list(csv.reader(path.open()))
        if fault == "subset":
            rows = rows[:1] + rows[4:]
            row["derivation"]["configuration_ids"] = [3]
        elif fault == "values":
            rows[1][3] = "999"
        else:
            rows[1:] = reversed(rows[1:])
        with path.open("w", newline="") as handle:
            csv.writer(handle).writerows(rows)
        row["source"] = binding(path, root)
    elif fault == "fidelity":
        row["derivation"]["fidelities"] = [300]
    elif fault == "seed":
        row["table_seed"] = 1
    else:
        row["expected_missing"] = {"23/Random": {}}
    with pytest.raises(ValueError):
        verify_complete_domain(row, root)


@pytest.mark.parametrize("fault", ["drop", "reorder", "recipe", "exceptions", "source", "all_missing"])
def test_authorized_extension_preserves_original_coverage(fault):
    root = Path(__file__).resolve().parents[2]
    corpus = copy.deepcopy(json.loads((root / CORPUS).read_text()))
    if fault == "drop":
        corpus["tables"].pop(0)
    elif fault == "reorder":
        corpus["tables"][0], corpus["tables"][1] = corpus["tables"][1], corpus["tables"][0]
    elif fault == "recipe":
        corpus["optimizer_seeds"] = [24]
    elif fault == "exceptions":
        corpus["tables"][1]["expected_missing"] = {}
    elif fault == "source":
        corpus["tables"][-1]["derivation"]["original_source"] = corpus["tables"][0]["source"]
    else:
        corpus["tables"][-1]["expected_missing"] = corpus["tables"][1]["expected_missing"]
    with pytest.raises(ValueError):
        verify_coverage_extension(corpus, root)


def test_complete_supplement_cannot_declare_missing_exceptions():
    root = Path(__file__).resolve().parents[2]
    corpus = json.loads((root / CORPUS).read_text())
    corpus["tables"][-1]["expected_missing"] = corpus["tables"][1]["expected_missing"]
    with pytest.raises(ValueError, match="original cases"):
        case_inventory(corpus)
