"""Frozen V02 conformance inventory and per-phase pytest execution journal.

This is local process instrumentation, not authentication of a hostile host.
The fixed assertions extend the bottom-rung grammar to the adopted runtime
contracts. Counts alone, arbitrary suites and skipped checks cannot certify.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from tools.source_identity import ROOT, source_digest
from validation.v01_contract import binding
from validation.v02_raw_reconstruction import _json, _bytes

FILES = (
    "tests/conformance/test_asha_reference.py",
    "tests/conformance/test_pasha_reference.py",
    "tests/conformance/test_checkpoint_resume.py",
    "tests/conformance/test_scheduler_contract.py",
    "tests/integration/test_streaming_scheduler.py",
    "tests/integration/test_ray_streaming.py",
    "tests/integration/test_ray_cluster_ownership.py",
    "tests/unit/test_scheduler_report_contract.py",
    "tests/unit/test_promotion_lifecycle.py",
    "tests/unit/test_pasha_progressive.py",
    "tests/unit/test_scheduler_state.py",
    "tests/unit/test_study_checkpoint_contract.py",
    "tests/unit/test_streaming_reporting.py",
    "tests/unit/test_replay_contract.py",
)
SEED = 9202930


def pytest_addoption(parser):
    parser.addoption("--v02-journal")


def _append(config, row):
    with Path(config.getoption("--v02-journal")).open("a") as handle:
        handle.write(json.dumps(row, allow_nan=False) + "\n")


def pytest_sessionstart(session):
    path = Path(session.config.getoption("--v02-journal"))
    with path.open("x") as handle:
        handle.write(json.dumps({"kind": "start", "pid": os.getpid(), "source_digest": source_digest()}) + "\n")
    # logreport receives no config argument; capture it in this child only.
    global _CONFIG
    _CONFIG = session.config


def pytest_collection_finish(session):
    _append(session.config, {"kind": "collection", "nodeids": [item.nodeid for item in session.items]})


def pytest_runtest_logreport(report):
    _append(_CONFIG, {"kind": "test_phase", "nodeid": report.nodeid, "when": report.when,
                     "outcome": report.outcome, "duration": report.duration,
                     "wasxfail": hasattr(report, "wasxfail"),
                     "error": str(report.longrepr) if report.failed else None,
                     "failure_context": getattr(report, "hponas_failure_context", None)})


def failure_context(excinfo):
    """Retain actual study results/events for an unexplained runtime failure."""
    records = []
    for entry in excinfo.traceback:
        study = entry.frame.f_locals.get("self")
        if isinstance(getattr(study, "results", None), dict) and hasattr(study, "_events"):
            records.append({"results": {key: value.to_dict() for key, value in study.results.items()},
                            "events": study._events})
    # Failed results legitimately contain NaN. Preserve its meaning explicitly
    # while keeping the campaign journal strict JSON; this is diagnostic only.
    return json.loads(json.dumps(records, default=repr),
                      parse_constant=lambda value: {"nonfinite": value})


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and call.excinfo is not None:
        try:
            report.hponas_failure_context = failure_context(call.excinfo)
        except Exception as exc:
            report.hponas_failure_context = {"capture_error": repr(exc)}


def pytest_sessionfinish(session, exitstatus):
    _append(session.config, {"kind": "finish", "exitstatus": int(exitstatus), "source_digest": source_digest()})


def _launch(directory, *, collect, timeout):
    directory = Path(directory)
    journal, log = directory / "pytest.jsonl", directory / "pytest.log"
    command = [sys.executable, "-m", "pytest", "-q", "-p", "validation.v02_conformance",
               "--v02-journal", str(journal), f"--hypothesis-seed={SEED}", *FILES]
    if collect:
        command.append("--collect-only")
    start = time.monotonic_ns()
    with log.open("x") as handle:
        process = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            process.wait(timeout=timeout)
            code, timed_out = process.returncode, False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            code, timed_out = None, True
    return {"command": command, "pid": process.pid, "returncode": code, "timeout": timed_out,
            "start_ns": start, "finish_ns": time.monotonic_ns(),
            "journal": binding(journal, directory) if journal.exists() else None,
            "log": binding(log, directory)}


def collect_inventory():
    with tempfile.TemporaryDirectory(prefix="hponas-v02-collect-") as directory:
        execution = _launch(directory, collect=True, timeout=60)
        if execution["returncode"] != 0:
            raise ValueError("V02 conformance collection failed: " + (Path(directory) / "pytest.log").read_text()[-2000:])
        rows = [_json(line) for line in _bytes(directory, execution["journal"]).splitlines()]
    collections = [row["nodeids"] for row in rows if row["kind"] == "collection"]
    if len(collections) != 1 or not collections[0] or len(set(collections[0])) != len(collections[0]):
        raise ValueError("Empty, duplicate or ambiguous V02 conformance inventory")
    return {"files": [binding(ROOT / path) for path in FILES], "nodeids": collections[0],
            "hypothesis_seed": SEED, "source_digest": source_digest(),
            "fixture": binding(ROOT / "tests/fixtures/pasha_reference_cases.json")}


def execute(directory, *, timeout):
    return _launch(directory, collect=False, timeout=timeout)


def verify(directory, execution, plan):
    """Check every planned assertion phase, retaining failures and omissions."""
    directory = Path(directory).resolve()
    expected_command = [sys.executable, "-m", "pytest", "-q", "-p", "validation.v02_conformance",
                        "--v02-journal", str(directory / "pytest.jsonl"), f"--hypothesis-seed={SEED}", *FILES]
    if execution.get("command") != expected_command:
        raise ValueError("V02 conformance command differs from frozen suite")
    _bytes(directory, execution["log"])
    if execution.get("journal") is None:
        return "INCONCLUSIVE"
    rows = [_json(line) for line in _bytes(directory, execution["journal"]).splitlines()]
    if (not rows or rows[0].get("kind") != "start" or rows[0].get("source_digest") != plan["source_digest"]
            or type(rows[0].get("pid")) is not int or rows[0]["pid"] <= 0
            or rows[0]["pid"] != execution.get("pid")):
        raise ValueError("Invalid V02 conformance process/source")
    collections = [row["nodeids"] for row in rows if row["kind"] == "collection"]
    if collections != [plan["nodeids"]]:
        raise ValueError("V02 conformance omitted or substituted planned assertions")
    expected = [(node, phase) for node in plan["nodeids"] for phase in ("setup", "call", "teardown")]
    observed, failed, skipped = [], False, False
    for row in rows[1:]:
        if row["kind"] not in {"collection", "test_phase", "finish"}:
            raise ValueError("Unknown V02 conformance journal record")
        if row["kind"] != "test_phase":
            continue
        key = (row["nodeid"], row["when"])
        if key not in expected or key in observed or row["outcome"] not in {"passed", "failed", "skipped"}:
            raise ValueError("Unknown or duplicate V02 assertion phase")
        observed.append(key)
        failed |= row["outcome"] == "failed"
        skipped |= row["outcome"] == "skipped" or row["wasxfail"]
    finishes = [row for row in rows if row["kind"] == "finish"]
    if failed:
        return "FAIL"
    if (execution["timeout"] or execution["returncode"] != 0 or skipped or observed != expected or len(finishes) != 1):
        return "INCONCLUSIVE"
    if (rows[-1] != finishes[0] or finishes[0].get("source_digest") != plan["source_digest"]
            or finishes[0].get("exitstatus") != 0):
        raise ValueError("V02 conformance finish/source differs")
    return "PASS"
