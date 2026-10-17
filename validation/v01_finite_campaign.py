"""Frozen finite V01 execution and independent acceptance reconstruction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from tools.source_identity import ROOT
from validation.benchmark_catalog import LandscapeTable
from validation.tabular_projection import FiniteLandscapeProjection
from validation.tier0_objectivity import read_bound_json
from validation.v01_contract import SEARCHERS, SCOPE, _file, binding, case_inventory, load_frozen, prepare_contract
from validation.v01_scheduler_traces import compare_scheduler_table_traces, verify_scheduler_table_traces
from validation.v01_table_traces import compare_table_traces, reconstruct_reference


def _write(root, name, value):
    path = Path(root) / name
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return binding(path, root)


def _projection(corpus, case):
    table = next(row for row in corpus["tables"] if row["id"] == case["table"])
    projection = FiniteLandscapeProjection(LandscapeTable(_file(table["source"])),
                                          log_columns=corpus["log_columns"])
    if case["table_seed"] not in projection.table.seeds:
        raise ValueError("Corpus table seed is not recorded")
    return projection


def observables(trace, *, scheduler, maximum, resource_unit=None):
    """Recorded-cell selections and work units; no inferred training runtime.

    Compare incumbents at equal fidelity. Strict improvement preserves the
    earliest observed trial on ties. Missing observations spend no invented
    resource and yield no invented score.
    """
    incumbents, history, consumed, missing = {}, [], 0, []
    for index, row in enumerate(trace["rows"]):
        if scheduler and row["kind"] not in {"report", "missing"}:
            continue
        if row["status"] != "finite":
            missing.append({key: row[key] for key in ("config_id", "seed", "training_steps", "status")})
            continue
        fidelity = row["training_steps"]
        consumed += resource_unit if scheduler else fidelity
        previous = incumbents.get(fidelity)
        if previous is None or row["value"] > previous["score"]:
            incumbents[fidelity] = {"config_id": row["config_id"], "score": row["value"],
                                   "observation_index": index,
                                   "trial_id": row["trial_id"] if scheduler else str(row["index"])}
        history.append({"observation_index": index, "training_steps": fidelity,
                        "recorded_training_steps_consumed": consumed,
                        "incumbent": dict(incumbents[fidelity])})
    return {"anytime": history, "final_incumbent": incumbents.get(maximum),
            "recorded_training_steps_consumed": consumed, "missing_cells": missing,
            "cost_kind": "recorded_training_steps_not_measured_training_time"}


def verify_case(projection, case, report):
    """Independently reconstruct reference, table values and policy selection."""
    scheduler = case["component"] not in SEARCHERS
    maximum = max(projection.table.training_steps)
    if scheduler:
        recipe = report["recipe"]
        if (recipe.get("component") != case["component"] or recipe.get("optimizer_seed") != case["optimizer_seed"]
                or recipe.get("table_seed") != case["table_seed"] or recipe.get("root_count") != case["count"]):
            raise ValueError("Scheduler case differs from frozen inventory")
        comparison = verify_scheduler_table_traces(projection, report)
        agrees = comparison["exact_trace_agreement"]
        unit = recipe["resource_unit"]
    else:
        if report.get("component") != case["component"]:
            raise ValueError("Searcher case differs from frozen inventory")
        for name in ("actual", "reference"):
            recipe = report[name]
            if (recipe.get("optimizer_seed") != case["optimizer_seed"] or recipe.get("table_seed") != case["table_seed"]
                    or recipe.get("requested_count") != case["count"] or recipe.get("training_steps") != maximum):
                raise ValueError("Searcher case differs from frozen inventory")
        comparison = reconstruct_reference(projection, report)
        agrees, unit = comparison["exact_cell_agreement"], None
    outcomes = {name: observables(report[name], scheduler=scheduler, maximum=maximum, resource_unit=unit)
                for name in ("actual", "reference")}
    agrees = agrees and outcomes["actual"] == outcomes["reference"]
    expected_missing = case.get("expected_missing")
    refusal = (agrees and not comparison["complete_traces"] and expected_missing is not None
               and all(outcomes[name]["missing_cells"] == [expected_missing]
                       and report[name]["status"] == "unresolved_cell"
                       and report[name]["rows"][-1]["status"] == expected_missing["status"]
                       for name in ("actual", "reference")))
    satisfied = (comparison["complete_traces"] and expected_missing is None) or refusal
    return {"id": case["id"], "agrees": agrees, "complete": comparison["complete_traces"],
            "expected_missing_verified": refusal, "coverage_satisfied": satisfied,
            "comparison": comparison, "observations": outcomes}


def campaign(run_dir):
    """Freeze first, retain every case slot, write once, then reconstruct."""
    root = Path(run_dir).resolve() / "finite-v01"
    root.mkdir(exist_ok=False)
    contract = prepare_contract()
    corpus = read_bound_json(ROOT, contract["corpus"])
    contract_ref = _write(root, "contract.json", contract)
    start = time.monotonic_ns()
    opening = {"kind": "v01_execution_open", "schema_version": 1, "contract": contract_ref,
               "frozen_ns": start, "timestamp": datetime.now(timezone.utc).isoformat(),
               "pid": os.getpid(), "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    opening_ref = _write(root, "opening.json", opening)
    records = []
    cap = corpus["resource"]["maximum_elapsed_seconds"]
    for index, case in enumerate(contract["cases"]):
        begin = time.monotonic_ns()
        record = {"case": case, "start_ns": begin}
        if (begin - start) / 1e9 >= cap:
            record.update(state="resource_cap")
        else:
            try:
                projection = _projection(corpus, case)
                kwargs = dict(optimizer_seed=case["optimizer_seed"], table_seed=case["table_seed"], count=case["count"])
                if case["component"] in SEARCHERS:
                    raw = compare_table_traces(projection, case["component"],
                                               training_steps=max(projection.table.training_steps), **kwargs)
                else:
                    raw = compare_scheduler_table_traces(projection, case["component"], **kwargs)
                record.update(state="observed", report=_write(root, f"case-{index:03d}.json", raw))
            except Exception as exc:
                record.update(state="execution_error", error={"type": type(exc).__name__, "message": str(exc)})
        record["finish_ns"] = time.monotonic_ns()
        records.append(record)
        _write(root, f"execution-{index:03d}.json", record)
    execution = {"kind": "v01_finite_execution", "schema_version": 1, "contract": contract_ref,
                 "opening": opening_ref, "finish_ns": time.monotonic_ns(),
                 "cases": [binding(root / f"execution-{i:03d}.json", root) for i in range(len(records))]}
    result = {"validation_id": "V01", "schema_version": 2, "scope": SCOPE,
              "source_digest": contract["source_digest"], "run_dir": str(root),
              "contract": contract_ref, "execution": _write(root, "execution.json", execution)}
    # Preserve the full raw envelope even if integrity reconstruction raises.
    _write(root, "raw-result.json", result)
    result["recomputed"] = recompute(result)
    return result


def _time(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Invalid V01 monotonic execution time")
    return value


def recompute(result):
    """Ignore all supplied summaries/verdicts; reject missing/substituted slots."""
    if (result.get("validation_id") != "V01" or result.get("schema_version") != 2
            or result.get("scope") != SCOPE):
        raise ValueError("Unknown finite V01 identity/schema/scope")
    root = Path(result["run_dir"]).resolve()
    contract, corpus = load_frozen(root, result["contract"])
    if result.get("source_digest") != contract["source_digest"]:
        raise ValueError("V01 result source differs from its freeze")
    expected = case_inventory(corpus)
    execution = read_bound_json(root, result["execution"])
    if (execution.get("kind") != "v01_finite_execution" or execution.get("schema_version") != 1
            or execution.get("contract") != result["contract"]
            or contract["cases"] != expected or len(execution.get("cases", [])) != len(expected)):
        raise ValueError("V01 execution lost its frozen complete inventory")
    opening = read_bound_json(root, execution["opening"])
    if (opening.get("kind") != "v01_execution_open" or opening.get("schema_version") != 1
            or opening.get("contract") != result["contract"] or type(opening.get("pid")) is not int
            or opening["pid"] <= 0 or not opening.get("boot_id") or not opening.get("timestamp")):
        raise ValueError("V01 execution opening differs from freeze")
    start = previous = _time(opening["frozen_ns"])
    end = _time(execution["finish_ns"])
    if end < start:
        raise ValueError("V01 execution ended before freeze")
    cap = corpus["resource"]["maximum_elapsed_seconds"]
    details, errors, missing = [], [], []
    for case, ref in zip(expected, execution["cases"]):
        record = read_bound_json(root, ref)
        begin, finish = _time(record["start_ns"]), _time(record["finish_ns"])
        if record.get("case") != case or not previous <= begin <= finish <= end:
            raise ValueError("V01 case inventory or execution order differs from freeze")
        previous = finish
        if record["state"] == "resource_cap":
            if (begin - start) / 1e9 < cap or "report" in record or "error" in record:
                raise ValueError("Unsupported V01 resource-cap omission")
            missing.append(case["id"])
        elif record["state"] == "execution_error":
            error = record.get("error", {})
            if "report" in record or not isinstance(error.get("type"), str) or not error["type"] or "message" not in error:
                raise ValueError("V01 execution error has no retained cause")
            errors.append({"id": case["id"], **error})
        elif record["state"] == "observed":
            if (begin - start) / 1e9 >= cap or "error" in record:
                raise ValueError("V01 case started after resource exhaustion")
            projection = _projection(corpus, case)
            raw = read_bound_json(root, record["report"])
            details.append(verify_case(projection, case, raw))
        else:
            raise ValueError("Unknown V01 case execution state")
    discrepancies = [row["id"] for row in details if not row["agrees"]]
    incomplete = [row["id"] for row in details if not row["complete"]]
    unsatisfied = [row["id"] for row in details if not row["coverage_satisfied"]]
    elapsed = (end - start) / 1e9
    verdict = ("FAIL" if discrepancies else "INCONCLUSIVE" if
               unsatisfied or errors or missing or elapsed > cap else "PASS")
    return {"verdict": verdict, "planned_cases": len(expected), "observed_cases": len(details),
            "complete_cases": sum(row["complete"] for row in details), "discrepancies": discrepancies,
            "verified_missing_refusals": sum(row["expected_missing_verified"] for row in details),
            "unsatisfied_cases": unsatisfied,
            "incomplete_cases": incomplete, "execution_errors": errors, "unexecuted_cases": missing,
            "elapsed_seconds": elapsed, "resource_cap_seconds": cap, "cases": details,
            "claim": "finite_corpus_only", "certifies_distributional_equivalence": False}


def recompute_result(result):
    return recompute(result)["verdict"]
