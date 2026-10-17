"""Bind the frozen V02 input population to candidate replay execution.

This package prepares the exact source, dependencies and integration recipes
for objective phase checks. Binding inputs alone cannot establish acceptance.
"""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np

from hponas.persistence import atomic_json
from tools.source_identity import ROOT, source_digest
from validation.reference_checks import REFERENCE_FILES
from validation.tier0_design import canonical_digest
from validation.v02_event_grammar import GRAMMAR, execute_case, recipe, verify_population
from validation.v02_raw_reconstruction import CRASH_PLAN, CONCURRENT_PLAN

POPULATION = "docs/program/evidence/2026-09-29/stat-03/v02-proposed-population.json"
POPULATION_SHA256 = "589e4c5a1381d47069497fcefeaddf595d5f8afedf769fad2757431c249bb675"
SCENARIOS = {
    "gp_replay": {"seed": 42, "n_trials": 20},
    "asha_replay": {"seed": 43, "n_trials": 30},
    "crash_resume": {"seed": 44, "n_trials": 50},
    "concurrent_replay": {"seed": 45, "n_trials": 20, "workers": 4},
    "adversarial_events": {},
    "non_vacuity": {},
    "streamed_replay": {"seed": 47, "n_trials": 2},
    "cancelled_replay": {"seed": 48, "n_trials": 1},
}
PACKAGES = ("numpy", "scipy", "torch", "botorch", "gpytorch", "ray")


def binding(path):
    path = Path(path).resolve()
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _read(ref, root=ROOT):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Exact V02 path/hash binding required")
    root = Path(root).resolve()
    path = (root / ref["path"]).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("V02 artifact escapes its bound root")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("Missing V02 bound artifact") from exc
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Changed V02 bound artifact")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate V02 JSON field")
            result[key] = value
        return result

    def reject(value):
        raise ValueError(f"Nonfinite V02 JSON: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject)


def frozen_population():
    """Verify the original proposal bytes and every input; never select on output."""
    snapshot = _read({"path": POPULATION, "sha256": POPULATION_SHA256})
    cases = snapshot.get("cases", [])
    if (snapshot.get("kind") != "v02_proposed_input_population"
            or snapshot.get("grammar") != GRAMMAR or snapshot.get("case_count") != 10000
            or len(cases) != 10000 or snapshot.get("numpy_version") != np.__version__
            or snapshot.get("reference_hashes") != REFERENCE_FILES
            or snapshot.get("generator") != binding(ROOT / "validation/v02_event_grammar.py")
            or snapshot.get("integration_scenario_ids") != list(SCENARIOS)
            or snapshot.get("kind_counts") != dict(Counter(case.get("kind") for case in cases))):
        raise ValueError("Frozen V02 population identity differs from its source recipe")
    if any(case != recipe(index) for index, case in enumerate(cases)):
        raise ValueError("Frozen V02 cases differ from the prespecified population")
    return snapshot


def prepare_contract():
    """Produce a reviewable candidate from exact inputs, never an approval."""
    frozen_population()
    return {
        "kind": "v02_bound_event_contract", "schema_version": 2, "status": "candidate",
        "source_digest": source_digest(), "python_version": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in PACKAGES},
        "protocol_register": binding(ROOT / "validation/protocols.json"),
        "individual_protocol": binding(ROOT / "validation/protocols/v02_protocol.md"),
        "input_population": {"path": POPULATION, "sha256": POPULATION_SHA256},
        "scenarios": {name: dict(options) for name, options in SCENARIOS.items()}, "case_count": 10000,
        "criterion": "zero_specification_violations_exact_replay",
        "raw_outcome_contract": {"crash": copy.deepcopy(CRASH_PLAN),
                                 "concurrency": {**copy.deepcopy(CONCURRENT_PLAN), "executor": "ray"},
                                 "verifier": binding(ROOT / "validation/v02_raw_reconstruction.py"),
                                 "producer": binding(ROOT / "validation/v02_fault_execution.py")},
        "certifies_acceptance": False,
        "scope": "Frozen ASHA bottom-rung grammar plus eight integration scenarios; not all asynchronous schedules",
    }


def verify_contract(contract):
    # Reconstruct the specification from code and original input, not from a
    # caller's claimed source identity, scenario list or PASS field.
    if contract != prepare_contract():
        raise ValueError("V02 contract differs from current source, dependencies or frozen inputs")
    return True


def freeze_contract(run_dir, contract):
    verify_contract(contract)
    path = Path(run_dir).resolve() / "v02-contract.json"
    if path.exists():
        raise ValueError("Refusing to replace frozen V02 inputs")
    canonical_digest(contract)
    atomic_json(path, contract)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def execute_population(contract):
    """Execute the committed cases, preserving order and every case identity."""
    verify_contract(contract)
    snapshot = frozen_population()
    return {"grammar": GRAMMAR, "count": 10000, "reference_hashes": dict(REFERENCE_FILES),
            "cases": [{"spec": spec, "actual": execute_case(spec)} for spec in snapshot["cases"]]}


def verify_bound_result(result):
    """Verify input/source binding and raw inventory; never certify the campaign.

    The surrounding evidence gate independently replays actual event logs and
    checks scenario outcomes. This adds no acceptance interpretation to an
    uncertified deterministic fixture.
    """
    if result.get("evidence_kind") != "bound_candidate_event_grammar":
        raise ValueError("Unknown V02 bound evidence kind")
    root = Path(result["run_dir"]).resolve()
    ref = result["input_contract"]
    if (root / ref["path"]).resolve() != root / "v02-contract.json":
        raise ValueError("V02 input contract is outside its campaign")
    contract = _read(ref, root)
    verify_contract(contract)
    scenarios = result.get("scenarios", [])
    ids = [scenario.get("id") for scenario in scenarios]
    if len(ids) != len(SCENARIOS) or set(ids) != set(SCENARIOS):
        raise ValueError("Complete unique V02 scenario inventory required")
    for scenario in scenarios:
        if any(scenario.get(k) != v for k, v in SCENARIOS[scenario["id"]].items()):
            raise ValueError("V02 integration recipe differs from its frozen contract")
        if "event_log" in scenario:
            event_ref = scenario["event_log"]
            path = (root / event_ref["path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("V02 event log escapes its campaign or is missing")
            if hashlib.sha256(path.read_bytes()).hexdigest() != event_ref["sha256"]:
                raise ValueError("Changed V02 bound event log")
    report = result.get("event_population", {})
    if [case.get("spec") for case in report.get("cases", [])] != frozen_population()["cases"]:
        raise ValueError("Executed V02 inputs differ from the frozen population")
    return verify_population(report)
