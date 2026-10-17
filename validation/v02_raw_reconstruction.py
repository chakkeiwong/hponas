"""Independent reconstruction of the declared V02 fault fixtures.

No Study, searcher, ReplayEngine, executor or producer objective is imported.
Direct NumPy MT19937 draws define the reference suggestions; the mathematical
polynomial defines their outcomes. Raw records establish consistency under the
recorded local process/clock model, not authentication of an untrusted host or
coverage of every possible crash point and asynchronous schedule.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


CRASH_PLAN = {"kind": "v02_crash_plan_v1", "seed": 44, "count": 50, "interrupt_index": 25,
              "exit_code": 73, "study_name": "crash", "objective": "negative_square_x_minus_0.4",
              "cost_per_completed_trial": 1.0, "workers": 1}
CONCURRENT_PLAN = {"kind": "v02_concurrent_plan_v1", "seed": 45, "count": 20, "workers": 4,
                   "study_name": "concurrent", "objective": "negative_square_x_minus_0.4",
                   "cost_per_completed_trial": 1.0, "orders": ["forward", "reverse"],
                   "barrier_timeout_seconds": 15}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate raw evidence key")
        result[key] = value
    return result


def _number(value):
    parsed = float(value)
    _require(math.isfinite(parsed), "Nonfinite raw evidence number")
    return parsed


def _json(raw):
    return json.loads(raw, object_pairs_hook=_object, parse_float=_number, parse_constant=_number)


def _bytes(root, ref):
    _require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "Exact raw path/hash binding required")
    _require(isinstance(ref["path"], str) and bool(ref["path"]), "Raw path missing")
    root = Path(root).resolve()
    relative = Path(ref["path"])
    path = (root / relative).resolve()
    _require(not relative.is_absolute() and path.is_relative_to(root) and path != root,
             "Raw artifact escapes its run")
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == ref["sha256"], "Changed raw artifact")
    return raw


def _read(root, ref):
    result = _json(_bytes(root, ref))
    _require(isinstance(result, dict), "Raw artifact must be an object")
    return result


def _reference(seed, count):
    generator = np.random.RandomState(seed)
    points = [float(generator.uniform(0., 1.)) for _ in range(count)]
    state = generator.get_state()
    return points, [state[0], state[1].tolist(), state[2], state[3], state[4]]


def _journal(root, run, *, stage, indices, incomplete=()):
    expected = {(i, event) for i in indices for event in ("start", "finish") if not (i in incomplete and event == "finish")}
    records, paths = {}, set()
    refs = run.get("journal", [])
    _require(len(refs) == len(expected), "Incomplete or duplicate worker journal inventory")
    for ref in refs:
        path = (Path(root) / ref["path"]).resolve()
        _require(path not in paths, "Duplicate raw journal path")
        paths.add(path)
        pieces = path.name.split(".")
        _require(len(pieces) == 3 and pieces[0].isdigit() and pieces[-1] == "json", "Malformed journal identity")
        key = (int(pieces[0]), pieces[1])
        _require(key in expected and key not in records, "Duplicate or unplanned journal identity")
        row = _read(root, ref)
        _require(row.get("stage") == stage, "Journal execution stage differs")
        records[key] = row
    if paths:
        parents = {p.parent for p in paths}
        _require(len(parents) == 1, "Journal spans different run directories")
        _require(set(next(iter(parents)).glob("*.json")) == paths, "Undeclared raw journal files")
    for index in indices:
        start = records[index, "start"]
        for key in ("pid", "thread", "start_ns"):
            _require(type(start.get(key)) is int and start[key] > 0, "Invalid worker clock or identity")
        for key in ("host", "boot_id"):
            _require(isinstance(start.get(key), str) and bool(start[key]), "Missing worker clock origin")
        _require("finish_ns" not in start and "value" not in start, "Start record contains future outcome")
        if index not in incomplete:
            finish = records[index, "finish"]
            _require({k: v for k, v in finish.items() if k not in {"finish_ns", "value", "cost"}} == start,
                     "Worker finish disagrees with its start")
            _require(type(finish.get("finish_ns")) is int and finish["finish_ns"] > start["start_ns"],
                     "Invalid worker interval")
    return records


def _snapshot(root, run, plan, *, suggested, completed, finished, journal):
    state = _read(root, run["checkpoint"])
    name, seed, count, width = (plan[k] for k in ("study_name", "seed", "count", "workers"))
    points, rng_state = _reference(seed, suggested)
    ids = [f"{name}_trial_{i}" for i in range(suggested)]
    complete_ids = ids[:completed]
    controls = {"schema_version": 3, "study_name": name, "budget": count, "max_concurrent": width,
                "maximize": True, "n_suggested": suggested, "n_completed": completed, "finished": finished,
                "scheduler_class": None, "scheduler_state": None, "continuation": "restart",
                "compute_budget_seconds": None, "pending": ids[completed:], "roots": {tid: tid for tid in ids},
                "stop_reason": None, "outcome": "completed" if finished else None,
                "cancel_requested": [], "report_cache": {}, "accounting_incomplete": []}
    _require(all(state.get(k) == v for k, v in controls.items()), "Checkpoint controls, counts or pending ledger differ")
    for key in ("n_suggested", "n_completed", "budget", "max_concurrent", "schema_version"):
        _require(type(state.get(key)) is int, "Checkpoint integer is malformed")
    _require(type(state.get("finished")) is bool and state.get("maximize") is True, "Checkpoint boolean is malformed")
    _require(state.get("searcher_class") == "hponas.searchers.random_searcher.RandomSearcher", "Wrong searcher identity")
    trials, results = state.get("trials", {}), state.get("results", {})
    _require(set(trials) == set(ids) and set(results) == set(complete_ids), "Checkpoint trial/result inventory differs")
    for index, tid in enumerate(ids):
        trial = trials[tid]
        value = -((points[index] - .4) ** 2)
        _require(trial.get("config") == {"values": {"x": points[index]}, "config_id": None},
                 "Configuration differs from independent NumPy reference")
        expected_trial = {"trial_id": tid, "seed": seed + index, "fidelity": 1.0, "root_trial_id": tid,
                          "parent_trial_id": None, "continuation": "restart", "resume_from": 0., "checkpoint": None,
                          "status": "completed" if index < completed else "pending",
                          "value": value if index < completed else None, "cost": 1.0}
        _require(all(trial.get(k) == v for k, v in expected_trial.items()), "Trial outcome/context differs")
        start = journal[index, "start"]
        _require(start.get("trial_id") == tid and start.get("seed") == seed + index
                 and start.get("config") == {"x": points[index]}, "Worker input differs from reference")
        if index < completed:
            result, finish = results[tid], journal[index, "finish"]
            _require(finish.get("value") == value and finish.get("cost") == 1., "Worker outcome differs from polynomial")
            required_result = {"trial_id": tid, "objective_value": value, "cost": 1., "fidelity": 1., "status": "completed"}
            _require(all(result.get(k) == v for k, v in required_result.items()), "Result differs from polynomial/context")
            _require(result.get("metadata", {}).get("v02_worker") == finish, "Result has no matching raw worker outcome")
    searcher = state.get("searcher_state", {})
    _require(searcher.get("seed") == seed and searcher.get("rng_state") == rng_state,
             "Checkpoint random state differs from independent NumPy reference")
    _require(searcher.get("history") == [results[tid] for tid in complete_ids], "Searcher history differs from raw outcomes")
    _require(searcher.get("trials") == {tid: trials[tid]["config"] for tid in ids}, "Searcher trial inventory differs")
    expected_events = []
    for first in range(0, suggested, width):
        for tid in ids[first:first + width]:
            expected_events.append({"kind": "suggest", "trial_id": tid,
                                    "data": {"config": trials[tid]["config"]["values"],
                                             "seed": seed, "fidelity": 1.0}})
        for tid in complete_ids[first:first + width]:
            expected_events.append({"kind": "observe", "trial_id": tid,
                                    "data": {k: v for k, v in results[tid].items() if k != "trial_id"}})
    _require(state.get("events") == expected_events, "Checkpoint event ledger differs from independent dispatch/observe sequence")
    log = [_json(line) for line in _bytes(root, run["event_log"]).splitlines() if line.strip()]
    projection = [{"event_id": i, "event_type": e["kind"], "timestamp": 0.,
                   "trial_id": e["trial_id"], "data": e["data"]} for i, e in enumerate(expected_events)]
    _require(log == projection, "Event export differs from complete checkpoint ledger")
    return state


def verify_crash(root, scenario):
    _require((scenario.get("id"), scenario.get("seed"), scenario.get("n_trials")) == ("crash_resume", 44, 50),
             "Crash scenario recipe differs")
    raw = scenario.get("raw_evidence", {})
    _require(raw.get("kind") == "v02_crash_raw_v1", "Raw crash evidence required")
    _require(_read(root, raw["plan"]) == CRASH_PLAN, "Crash plan differs")
    before = _journal(root, raw["before"], stage="before_crash", indices=range(26), incomplete=(25,))
    after = _journal(root, raw["after"], stage="after_crash", indices=range(25, 50))
    pre = _snapshot(root, raw["before"], CRASH_PLAN, suggested=26, completed=25, finished=False, journal=before)
    joined = {**before, **after}
    final = _snapshot(root, raw["after"], CRASH_PLAN, suggested=50, completed=50, finished=True, journal=joined)
    process = _read(root, raw["process"])
    _require(process.get("returncode") == 73 and type(process.get("pid")) is int, "Wrong recorded process exit")
    starts = [before[i, "start"] for i in range(26)]
    _require(all(row["pid"] == process["pid"] for row in starts), "Crash worker PID differs from launcher")
    _require(type(process.get("started_ns")) is int and type(process.get("finished_ns")) is int,
             "Process clock missing")
    _require(process["started_ns"] < min(r["start_ns"] for r in starts)
             <= max(r["start_ns"] for r in starts) < process["finished_ns"], "Process interval does not enclose the crash")
    _require(all(after[i, "start"]["pid"] != process["pid"]
                 and after[i, "start"]["start_ns"] > process["finished_ns"] for i in range(25, 50)),
             "Resume does not follow the exited process")
    clocks = {(row["host"], row["boot_id"]) for row in [*starts, *(after[i, "start"] for i in range(25, 50))]}
    _require(len(clocks) == 1, "Crash chronology requires the same host and boot clock")
    _require(final["events"][:len(pre["events"])] == pre["events"], "Resume changed the committed event prefix")
    _require(all(final["results"][tid] == result for tid, result in pre["results"].items()),
             "Resume changed a previously committed result")
    return {"reconstructed": True, "committed_at_interruption": 25, "pending_at_interruption": 1,
            "completed_after_resume": 50, "reexecuted_committed_trials": 0, "cost": 50.,
            "reference": "numpy_MT19937_and_direct_polynomial", "certifies_acceptance": False}


def verify_concurrency(root, scenario, *, executor_kind="ray"):
    _require(executor_kind in {"ray", "local_threads"}, "Unknown concurrency verifier mode")
    _require((scenario.get("id"), scenario.get("seed"), scenario.get("n_trials"), scenario.get("workers"))
             == ("concurrent_replay", 45, 20, 4), "Concurrency scenario recipe differs")
    raw = scenario.get("raw_evidence", {})
    _require(raw.get("kind") == "v02_concurrent_raw_v1", "Raw concurrency evidence required")
    _require(_read(root, raw["plan"]) == {**CONCURRENT_PLAN, "executor": executor_kind}, "Concurrency plan/executor differs")
    _require(set(raw.get("runs", {})) == {"forward", "reverse"}, "Both completion orders required")
    summaries = {}
    for order, run in raw["runs"].items():
        journal = _journal(root, run, stage=order, indices=range(20))
        _snapshot(root, run, CONCURRENT_PLAN, suggested=20, completed=20, finished=True, journal=journal)
        clocks = {(journal[i, "start"]["host"], journal[i, "start"]["boot_id"]) for i in range(20)}
        _require(len(clocks) == 1, "Concurrent clocks must share a host and boot")
        end_order = []
        for first in range(0, 20, 4):
            batch = list(range(first, first + 4))
            starts = [journal[i, "start"] for i in batch]
            ends = [journal[i, "finish"] for i in batch]
            identities = {(row["pid"], row["thread"]) for row in starts}
            _require(len(identities) == 4, "Four distinct worker contexts required")
            if executor_kind == "ray":
                _require(len({row["pid"] for row in starts}) == 4, "Ray evidence requires four worker processes")
            _require(max(row["start_ns"] for row in starts) < min(row["finish_ns"] for row in ends),
                     "Recorded intervals do not demonstrate four-way overlap")
            actual = sorted(batch, key=lambda i: journal[i, "finish"]["finish_ns"])
            expected = batch if order == "forward" else batch[::-1]
            _require(actual == expected, "Recorded completion order differs from frozen schedule")
            end_order.extend(actual)
        summaries[order] = {"completed": 20, "cost": 20., "four_way_overlap_batches": 5,
                            "completion_order": end_order}
    primary = scenario.get("event_log", {})
    reference = raw["runs"]["forward"]["event_log"]
    _require((Path(root) / primary.get("path", "")).resolve() == (Path(root) / reference["path"]).resolve()
             and primary.get("sha256") == reference["sha256"], "Primary event log differs from reconstructed run")
    return {"reconstructed": True, "executor": executor_kind, "orders": summaries,
            "reference": "numpy_MT19937_and_direct_polynomial", "certifies_acceptance": False}
