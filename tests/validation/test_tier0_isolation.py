import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from validation.tier0_isolation import run_isolated, verify_isolated, verify_sequence


def rewrite(root, ref, edit):
    path = root / ref["path"]
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))
    return {"path": ref["path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_real_children_are_fresh_ordered_and_receive_no_parent_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HPONAS_PARENT_MARKER", "parent state must not cross")
    refs = [run_isolated(tmp_path, f"job-{i}", {"operation": "engineering_probe"}, timeout_seconds=10)[0]
            for i in range(2)]
    reports = verify_sequence(tmp_path, refs)
    assert all(report["status"] == "complete" for report in reports)
    assert len({report["output"]["pid"] for report in reports} | {os.getpid()}) == 3
    assert all(report["output"]["inherited_marker"] is None for report in reports)
    assert all(not report["certifies_independence"] for report in reports)
    assert reports[0]["output"]["cwd"] != reports[1]["output"]["cwd"]
    with pytest.raises(ValueError, match="order"):
        verify_sequence(tmp_path, refs[::-1])
    with pytest.raises(ValueError, match="Duplicate"):
        verify_sequence(tmp_path, [refs[0], refs[0]])
    with pytest.raises(FileExistsError):
        run_isolated(tmp_path, "job-0", {"operation": "engineering_probe"}, timeout_seconds=10)


def test_child_failure_and_timeout_are_preserved_without_success_or_retry(tmp_path):
    ref, report = run_isolated(tmp_path, "failed", {"operation": "engineering_probe", "fail": True}, timeout_seconds=10)
    assert report["status"] == "failed" and report["output"] is None
    assert verify_isolated(tmp_path, ref) == report
    ref, report = run_isolated(tmp_path, "interrupted", {"operation": "engineering_probe"}, timeout_seconds=.000001)
    assert report["status"] == "interrupted" and report["output"] is None
    assert json.loads((tmp_path / ref["path"]).read_text())["timed_out"]


def test_child_exit_racing_timeout_preserves_interruption_record(tmp_path, monkeypatch):
    from validation import tier0_isolation

    class ExitedProcess:
        pid = os.getpid() + 500000
        returncode = 0
        waits = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return 0

    def gone(*args):
        raise ProcessLookupError("group already exited")

    monkeypatch.setattr(tier0_isolation.subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr(tier0_isolation.os, "killpg", gone)
    ref, report = run_isolated(tmp_path, "race", {"operation": "engineering_probe"}, timeout_seconds=1)
    assert report["status"] == "interrupted" and report["output"] is None
    assert json.loads((tmp_path / ref["path"]).read_text())["timed_out"]


@pytest.mark.parametrize("fault", ["pid", "parent", "time", "source", "request", "log"])
def test_rebound_observations_are_checked_against_independent_child_record(tmp_path, fault):
    ref, _ = run_isolated(tmp_path, "job", {"operation": "engineering_probe"}, timeout_seconds=10)
    if fault == "pid":
        ref = rewrite(tmp_path, ref, lambda record: record.update(pid=record["pid"] + 1))
    elif fault == "parent":
        ref = rewrite(tmp_path, ref, lambda record: record.update(parent_pid=record["parent_pid"] + 1))
    elif fault == "time":
        ref = rewrite(tmp_path, ref, lambda record: record.update(finish_ns=record["launch_ns"]))
    elif fault == "request":
        (tmp_path / "processes/job/request.json").write_text('{}')
    elif fault == "source":
        with pytest.raises(ValueError, match="source"):
            verify_sequence(tmp_path, [ref], expected_source="0" * 64)
        return
    else:
        (tmp_path / "processes/job/stdout.log").write_text("tampered")
    with pytest.raises(ValueError):
        verify_isolated(tmp_path, ref)


def test_real_search_worker_still_refuses_incomplete_design_before_workload(tmp_path):
    from validation.tier0_design import load_design

    design = load_design("validation/designs/tier0_candidate_v2_1.json")
    _, report = run_isolated(tmp_path, "unready", {"operation": "search", "design": design,
        "entry": "V05", "task": next(iter(design["tasks"])), "arm": "gp_log", "seed": 0, "phase": "pilot"}, timeout_seconds=30)
    assert report["status"] == "failed" and report["output"] is None
    response = json.loads((tmp_path / "processes/unready/response.json").read_text())
    # Fresh mutation copies deliberately lack .git. The isolated child strips
    # the parent's GIT_DIR and correctly refuses that context even earlier.
    checkout = Path(__file__).resolve().parents[2]
    expected = "Incomplete Tier 0 design" if (checkout / ".git").exists() else "AuditContextError"
    assert expected in response["failure"]
    assert not list(tmp_path.rglob("policy.pkl"))
