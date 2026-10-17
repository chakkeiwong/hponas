"""Inventory, provenance, optimizer identity and result/accounting corruption."""
from copy import deepcopy
import json

import pytest

from validation import stylized_campaign as sc
from workloads.stylized import evaluate, get_case


@pytest.fixture
def evidence():
    case = get_case("filter-a")
    spec = {**sc.contract("V04-T0"), "cases": [case], "seeds": [sc.SEEDS[0]], "methods": ["random"]}
    records = [sc.run_study("V04-T0", case, sc.SEEDS[0], "random")]
    probes = [{"case": case["id"], "config": config, "observation": evaluate(case["id"], config)}
              for config in sc.probes(case)]
    return spec, records, probes


def test_full_inventory_and_ungated_regret(evidence):
    spec, records, probes = evidence
    summary = sc.reconstruct(spec, records, probes)
    assert summary["verdict"] == "PASS"
    assert summary["studies"][0]["best_regret_curve"][-1] > 0
    for entry, trials in [("V04-T0", 1024), ("V05", 128)]:
        assert len(list(sc.slots(sc.contract(entry))))*sc.TRIALS == trials


@pytest.mark.parametrize("defect", ["omitted_slot", "seed", "method", "config", "selection",
                                  "coordinate", "cost", "summary_cost", "probe"])
def test_reject_forged_trace(evidence, defect):
    spec, records, probes = deepcopy(evidence)
    record = records[0]
    if defect == "omitted_slot":
        records.clear()
    elif defect == "seed":
        record["seed"] += 1
    elif defect == "method":
        record["method"] = "sobol"
    elif defect == "config":
        record["observations"][0]["config"]["gain"] = .321
    elif defect == "selection":
        record["selected_index"] = 100
    elif defect == "coordinate":
        record["observations"][0]["coordinates"] = [0.]
    elif defect == "cost":
        record["observations"][0]["search_seconds"] = -1
    elif defect == "summary_cost":
        record["elapsed_seconds"] = 0.
    elif defect == "probe":
        probes.pop()
    with pytest.raises(ValueError):
        sc.reconstruct(spec, records, probes)


def test_failed_numerical_probe_is_not_accepted(evidence):
    spec, records, probes = evidence
    probes[0]["observation"]["value"] += 1
    assert sc.reconstruct(spec, records, probes)["verdict"] == "FAIL"


def test_missing_trials_retained_inconclusive(evidence):
    spec, records, probes = evidence
    records[0].update(status="incomplete", observations=[], selected_index=None)
    result = sc.reconstruct(spec, records, probes)
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["missing_trials"] == 16


def test_v05_shared_physical_initialization_and_independent_coordinates():
    case = get_case("ridge-a")
    prefix = sc.initial_configs(case, sc.SEEDS[0])
    for method in ["gp_log", "gp_linear"]:
        searcher = sc.make_searcher(case, method, sc.SEEDS[0])
        for i, expected in enumerate(prefix):
            proposal = sc._proposal(searcher, prefix, i)
            assert proposal.values == expected
            encoder = sc.SpaceEncoder(searcher.search_space)
            coordinates = encoder.encode(proposal).tolist()
            sc.verify_coordinates(case, method, {"config": expected, "coordinates": coordinates,
                                                "decoded": encoder.decode(coordinates)})
        assert searcher.n_suggestions == 5


def test_bound_artifacts_reconstructed_not_supplied_flags(tmp_path, monkeypatch, evidence):
    spec, _, _ = evidence
    original_freeze = sc.freeze
    monkeypatch.setattr(sc, "contract", lambda entry: deepcopy(spec))
    result = sc.campaign("V04-T0", tmp_path)
    result.update(passed=False, verdict="FAIL")
    assert sc.recompute_result("V04-T0", result) == "PASS"
    wrong = deepcopy(result)
    wrong["summary"]["studies"][0]["search_seconds"] += 1
    with pytest.raises(ValueError, match="summary"):
        sc.recompute_result("V04-T0", wrong)
    for field in ["source_digest", "protocol_sha256", "registry_sha256"]:
        monkeypatch.setattr(sc, "freeze", lambda entry, path, field=field:
                            {**original_freeze(entry, path), field: "0"*64})
        with pytest.raises(ValueError, match="Frozen"):
            sc.recompute_result("V04-T0", result)
    monkeypatch.setattr(sc, "freeze", original_freeze)
    path = tmp_path / "traces.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["method"] = "sobol"
    path.write_text("\n".join(json.dumps(r) for r in records)+"\n")
    with pytest.raises(ValueError, match="artifact"):
        sc.recompute_result("V04-T0", result)
    result["traces"] = sc._binding(path)
    with pytest.raises(ValueError, match="identities"):
        sc.recompute_result("V04-T0", result)
