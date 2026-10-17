"""Final finite V02 freeze: event population, raw scenarios and mandatory suites."""

from __future__ import annotations

import copy
import importlib.metadata
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from tools.source_identity import ROOT, source_digest
from validation.tier0_objectivity import read_bound_json
from validation.v01_contract import binding
from validation.v01_finite_campaign import _write
from validation.v02_contract import prepare_contract
from validation.v02_raw_reconstruction import _json
from validation import v02_conformance

SCOPE = "recorded_event_and_runtime_conformance_v1"
CAP = 600
SCHEDULER_CONFIGS = {
    "asha_replay": {"r_min": 1, "r_max": 9, "eta": 3},
    "streamed_replay": {"r_min": 1, "r_max": 4, "eta": 2},
    "cancelled_replay": {"r_min": 4, "r_max": 4, "eta": 3},
}
for _config in SCHEDULER_CONFIGS.values():
    _config.update(median_stopping=False, promotion_policy="syne_tune_0_13_0", median_min_completed=5, report_grid=[])


def verify_recipes(result):
    if result.get("evidence_kind") != "bound_candidate_event_grammar":
        raise ValueError("Final V02 requires bound raw execution; diagnostic evidence cannot substitute")
    for scenario in result.get("scenarios", []):
        if scenario.get("scheduler_config") != SCHEDULER_CONFIGS.get(scenario.get("id")):
            raise ValueError("V02 scheduler recipe differs from its frozen specification")


def final_contract():
    register = json.loads((ROOT / "validation/protocols.json").read_text())
    if register["entries"]["V02"].get("scope_contract") != SCOPE:
        raise ValueError("Final V02 scope not bound in protocol register")
    threads = {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")}
    if any(value != "1" for value in threads.values()):
        raise ValueError("Set OMP_NUM_THREADS=1 and OPENBLAS_NUM_THREADS=1 before V02 execution")
    return {"kind": "v02_final_finite_contract", "schema_version": 1, "scope": SCOPE,
            "base_contract": prepare_contract(), "conformance": v02_conformance.collect_inventory(),
            "conformance_dependencies": {name: importlib.metadata.version(name) for name in
                                         ("pytest", "hypothesis", "sortedcontainers", "cloudpickle")},
            "thread_environment": threads, "scheduler_recipes": copy.deepcopy(SCHEDULER_CONFIGS),
            "cap_seconds": CAP, "rule": "any_discrepancy_fails_all_required_observations_complete_to_pass",
            "trust": "instrumented_local_host_not_external_authentication"}


def campaign(run_dir):
    from validation.v02_state_replay import campaign as base_campaign

    root = Path(run_dir).resolve()
    contract = final_contract()
    ref = _write(root, "v02-final-contract.json", contract)
    frozen = time.monotonic_ns()
    base = base_campaign(root)
    _write(root, "v02-base-result.json", base)
    conformance_dir = root / "conformance"
    conformance_dir.mkdir(exist_ok=False)
    remaining = CAP - (time.monotonic_ns() - frozen) / 1e9
    execution = v02_conformance.execute(conformance_dir, timeout=max(.001, remaining))
    result = {**base, "schema_version": 2, "scope": SCOPE,
              "source_digest": contract["base_contract"]["source_digest"],
              "final_contract": ref, "frozen_ns": frozen, "finish_ns": time.monotonic_ns(),
              "conformance_execution": _write(root, "conformance-execution.json", execution)}
    result.pop("certifies_acceptance", None)
    _write(root, "v02-final-raw-result.json", result)
    return result


def verify_observations(root, scenario):
    """Validate raw scores/configurations against independent mathematical inputs.

    Replay state checks remain additional requirements, not a replacement for
    checking that recorded objective values really follow the fixed fixture.
    """
    name = scenario["id"]
    if name == "adversarial_events":
        points = np.random.RandomState(45).uniform(size=20).tolist()
        reference = [[{"x": x} for x in points], [-((x - .4)**2) for x in points]]
        expected = {"arrival_order": reference, "unique_rung_population": 2,
                    "single_promotion": [["a", 3]], "stale_report_no_repromotion": []}
        cases = scenario["cases"]
        return (len(cases) == len(expected) and {row["name"] for row in cases} == set(expected)
                and all(row["actual"] == row["expected"] == expected[row["name"]] for row in cases))
    if name == "non_vacuity":
        return scenario["cases"] == [{"name": "empty_log_rejected", "expected": False, "actual": False}]
    if name in {"crash_resume", "concurrent_replay"}:
        return True  # Independent raw polynomial/process reconstruction in base gate.
    ref = scenario["event_log"]
    path = Path(ref["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()) or binding(path, root)["sha256"] != ref["sha256"]:
        raise ValueError("V02 event input changed or escapes its run")
    rows = [_json(line) for line in path.read_bytes().splitlines() if line.strip()]
    if not rows or [row["event_id"] for row in rows] != list(range(len(rows))):
        raise ValueError("V02 raw event inventory is incomplete")
    from validation.v01_table_traces import _vendor
    import torch

    previous_threads = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        suggest, observe = _vendor("GP" if name == "gp_replay" else "Random", 1, scenario["seed"])
        configs, observed, suggested, resources = {}, set(), [], []
        for row in rows:
            kind, tid, data = row["event_type"], row["trial_id"], row["data"]
            if kind == "suggest":
                if tid in configs or data["config"] != {"x": suggest()[0]} or data["seed"] != scenario["seed"]:
                    return False
                configs[tid] = data["config"]
                suggested.append(tid)
            elif kind == "promote":
                if tid in configs or data["config"] != configs[data["root"]]:
                    return False
                configs[tid] = data["config"]
            elif kind == "observe":
                value = 5. if name in {"streamed_replay", "cancelled_replay"} else -((configs[tid]["x"] - .4)**2)
                if (tid in observed or data["objective_value"] != value or not math.isfinite(data["cost"])
                        or data["cost"] < 0):
                    return False
                observed.add(tid)
                resources.append(data["cost"])
                if name == "gp_replay":
                    observe(len(observed) - 1, [configs[tid]["x"]], value)
            elif kind == "progress":
                if name not in {"streamed_replay", "cancelled_replay"} or data["value"] != 5.:
                    return False
            elif kind == "report":
                value = 5. if name == "streamed_replay" else (configs[tid]["x"] - .4)**2
                if data["value"] != value:
                    return False
        if len(suggested) != scenario["n_trials"] or observed != set(configs):
            return False
        if name == "streamed_replay" and sum(resources) != 8.:
            return False
        if name == "cancelled_replay" and sum(resources) != 2.:
            return False
        return True
    finally:
        torch.set_num_threads(previous_threads)


def recompute_result(result):
    if result.get("validation_id") != "V02" or result.get("schema_version") != 2 or result.get("scope") != SCOPE:
        raise ValueError("Unknown final V02 schema/identity/scope")
    verify_recipes(result)
    root = Path(result["run_dir"]).resolve()
    contract = read_bound_json(root, result["final_contract"])
    if contract != final_contract() or result.get("source_digest") != source_digest():
        raise ValueError("Final V02 contract differs from current source or complete inventory")
    base_contract = read_bound_json(root, {"path": "v02-contract.json", "sha256": result["input_contract"]["sha256"]})
    if base_contract != contract["base_contract"]:
        raise ValueError("V02 strata do not share the frozen input contract")
    execution = read_bound_json(root, result["conformance_execution"])
    times = [result["frozen_ns"], execution["start_ns"], execution["finish_ns"], result["finish_ns"]]
    if any(type(t) is not int or t <= 0 for t in times) or times != sorted(times):
        raise ValueError("V02 conformance execution precedes its freeze")
    suite = v02_conformance.verify(root / "conformance", execution, contract["conformance"])
    from validation.evidence import decision

    base = copy.deepcopy(result)
    base["schema_version"] = 1
    old = decision("V02", base)
    if old == "FAIL" or suite == "FAIL" or not all(verify_observations(root, row) for row in base["scenarios"]):
        return "FAIL"
    if old != "INCONCLUSIVE":
        raise ValueError("Unexpected base V02 outcome")
    if suite != "PASS" or (times[-1] - times[0]) / 1e9 > CAP:
        return "INCONCLUSIVE"
    return "PASS"
