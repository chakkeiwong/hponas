"""Fresh-interpreter job execution with independently checkable local records.

This isolates Python state and restricts the worker's input interface. It is not
an OS security sandbox or proof of probabilistic independence: workers share a
host, filesystem and PRNG implementation. Campaign evidence retains that limit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from tools.source_identity import source_digest  # noqa: E402
from validation.tier0_objectivity import read_bound_json  # noqa: E402

POLICY = "fresh_interpreter_bound_jobs_v1"
LIMITS = ["Local host/process records are not externally authenticated chronology.",
          "Fresh interpreter state and a fixed input interface do not prove stochastic independence.",
          "Workers share a trusted host/filesystem; this is not an adversarial OS sandbox."]


def _write(path, data):
    with path.open("x") as handle:
        json.dump(data, handle, allow_nan=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _ref(root, path):
    return {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _boot():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _identity():
    # The start tick disambiguates PID reuse. Parse after the final ')' because
    # process names may themselves contain spaces or parentheses.
    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": os.getpid(), "parent_pid": os.getppid(), "start_tick": int(stat[19]), "boot_id": _boot()}


def _frozen_environment(payload):
    """Resolve the declared experiment for search and protected jobs alike."""
    from validation.tier0_phase_contracts import SAMPLING, execution_environment_errors

    if payload.get("operation") == "search":
        design = payload["design"]
    elif payload.get("operation") == "protected":
        root = Path(payload["root"])
        bundle = read_bound_json(root, payload["search_freeze"])
        design = read_bound_json(root, bundle["design"])
    else:
        return {}
    if design.get("sampling", {}).get("selection_algorithm") != SAMPLING:
        return {}
    errors = execution_environment_errors(design)
    if errors:
        raise ValueError("; ".join(errors))
    if design["execution_environment"]["python"] != sys.executable:
        raise ValueError("Isolated interpreter differs from frozen experiment")
    return design["execution_environment"]["variables"]


def run_isolated(root, job_id, payload, *, timeout_seconds):
    """Run one fixed worker entry point; retain timeouts/failures without retry."""
    if (not isinstance(job_id, str) or not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in job_id)
            or isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
            or payload.get("operation") not in {"search", "protected", "engineering_probe"}):
        raise ValueError("Invalid isolated job or timeout")
    root = Path(root).resolve()
    directory = root / "processes" / job_id
    directory.mkdir(parents=True, exist_ok=False)
    request = {"policy": POLICY, "payload": payload, "nonce": os.urandom(32).hex(),
               "source_digest": source_digest(), "parent_pid": os.getpid(), "boot_id": _boot()}
    _write(directory / "request.json", request)
    request_ref = _ref(root, directory / "request.json")
    # -I ignores caller PYTHONPATH/user-site. Only the fixed script adds this
    # checkout; no arbitrary callable/module is deserialized from job input.
    command = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker",
               str(directory / "request.json"), "--sha256", request_ref["sha256"]]
    environment = {k: os.environ[k] for k in ("PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES") if k in os.environ}
    environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       XDG_CACHE_HOME=str(directory / "cache"))
    environment.update(_frozen_environment(payload))
    launch = time.monotonic_ns()
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, close_fds=True, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Child/group exited between the timeout and termination.
            process.wait(timeout=10)
    finish = time.monotonic_ns()
    response = directory / "response.json"
    observation = {"policy": POLICY, "request": request_ref, "pid": process.pid,
                   "parent_pid": os.getpid(), "boot_id": request["boot_id"], "launch_ns": launch,
                   "finish_ns": finish, "timeout_seconds": timeout_seconds, "timed_out": timed_out,
                   "exit_code": process.returncode, "command": command, "environment": environment,
                   "stdout": _ref(root, directory / "stdout.log"), "stderr": _ref(root, directory / "stderr.log"),
                   "response": _ref(root, response) if response.exists() else None}
    if _ref(root, directory / "request.json") != request_ref:
        raise ValueError("Worker changed its frozen input")
    _write(directory / "process.json", observation)
    ref = _ref(root, directory / "process.json")
    report = verify_isolated(root, ref)
    if source_digest() != request["source_digest"]:
        raise ValueError("Source changed during isolated job")
    return ref, report


def verify_isolated(root, ref):
    """Reconcile parent observations, child identity/timing and exact input/output."""
    root = Path(root).resolve()
    record = read_bound_json(root, ref)
    request = read_bound_json(root, record["request"])
    directory = (root / record["request"]["path"]).parent
    expected_command = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker",
                        str(directory / "request.json"), "--sha256", record["request"]["sha256"]]
    environment = record.get("environment", {})
    timeout = record.get("timeout_seconds")
    if (record.get("policy") != POLICY or request.get("policy") != POLICY
            or record["command"] != expected_command or record["parent_pid"] != request["parent_pid"]
            or record["boot_id"] != request["boot_id"] or record["pid"] == record["parent_pid"]
            or any(type(record[k]) is not int or record[k] <= 0 for k in ("launch_ns", "finish_ns", "pid", "parent_pid"))
            or record["finish_ns"] < record["launch_ns"] or type(record["timed_out"]) is not bool
            or type(record["exit_code"]) is not int or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0
            or not set(environment) <= {"PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES", "OMP_NUM_THREADS",
                                         "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "XDG_CACHE_HOME",
                                         "JAX_PLATFORMS", "XLA_PYTHON_CLIENT_MEM_FRACTION"}
            or any(environment.get(key) != "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"))
            or environment.get("XDG_CACHE_HOME") != str(directory / "cache")):
        raise ValueError("Invalid process launch identity or ordering")
    if any(environment.get(key) != value for key, value in _frozen_environment(request["payload"]).items()):
        raise ValueError("Recorded execution environment differs from frozen experiment")
    for name in ("stdout", "stderr"):
        path = (root / record[name]["path"]).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != record[name]["sha256"]:
            raise ValueError("Changed process log")
    response = read_bound_json(root, record["response"]) if record["response"] else None
    status, output, identity = "interrupted", None, None
    if response is not None:
        identity = response["identity"]
        if (identity["pid"] != record["pid"] or identity["parent_pid"] != record["parent_pid"]
                or identity["boot_id"] != record["boot_id"] or type(identity["start_tick"]) is not int
                or identity["start_tick"] < 0 or response["request_sha256"] != record["request"]["sha256"]
                or response["nonce"] != request["nonce"] or response["source_digest"] != request["source_digest"]
                or not record["launch_ns"] <= response["start_ns"] <= response["finish_ns"] <= record["finish_ns"]):
            raise ValueError("Child identity, input or timing differs from parent observation")
        if response["status"] not in {"complete", "failed"}:
            raise ValueError("Unknown child completion status")
        if response["status"] == "complete" and record["exit_code"] == 0 and not record["timed_out"]:
            status, output = "complete", response["output"]
        elif record["exit_code"] == 0 and not record["timed_out"] and response["status"] == "failed":
            status = "failed"
    elif record["exit_code"] == 0 and not record["timed_out"]:
        raise ValueError("Successful child has no output evidence")
    return {"policy": POLICY, "status": status, "payload": request["payload"], "output": output,
            "process_identity": identity, "source_digest": request["source_digest"],
            "observer": {"boot_id": record["boot_id"], "pid": record["parent_pid"]},
            "launch_ns": record["launch_ns"], "finish_ns": record["finish_ns"],
            "timeout_seconds": timeout,
            "elapsed_seconds": (record["finish_ns"] - record["launch_ns"]) / 1e9,
            "certifies_independence": False, "limitations": LIMITS}


def verify_sequence(root, refs, *, expected_source=None):
    reports, identities, previous, observer = [], set(), None, None
    if len({(ref["path"], ref["sha256"]) for ref in refs}) != len(refs):
        raise ValueError("Duplicate process receipt")
    for ref in refs:
        item = verify_isolated(root, ref)
        if observer is not None and item["observer"] != observer:
            raise ValueError("Process sequence crosses observer or host boot")
        observer = item["observer"]
        if expected_source is not None and item["source_digest"] != expected_source:
            raise ValueError("Process uses a different source snapshot")
        identity = item["process_identity"]
        if identity is not None:
            key = (identity["boot_id"], identity["pid"], identity["start_tick"])
            if key in identities:
                raise ValueError("Job process reused")
            identities.add(key)
        if previous is not None and item["launch_ns"] < previous:
            raise ValueError("Jobs overlap or process order changed")
        previous = item["finish_ns"]
        reports.append(item)
    return reports


def _execute(payload, directory):
    operation = payload["operation"]
    if operation == "engineering_probe":
        # No scientific workload or arbitrary user-supplied executable.
        if payload.get("fail"):
            raise RuntimeError("Injected engineering failure")
        return {"pid": os.getpid(), "cwd": str(Path.cwd()), "inherited_marker": os.environ.get("HPONAS_PARENT_MARKER"),
                "siblings_visible_in_cwd": sorted(path.name for path in directory.iterdir()),
                "value": sum(i * i for i in range(100))}
    if operation == "search":
        from validation.tier0_campaign import _ppo_objective, run_study
        from validation.tier0_design import require_campaign_ready
        design = payload["design"]
        require_campaign_ready(design, payload["phase"])
        from validation.tier0_phase_contracts import require_execution_environment

        require_execution_environment(design, inspect_device=True)
        return run_study(design, payload["entry"], payload["task"], payload["seed"], payload["arm"], payload["phase"],
                         _ppo_objective(design["tasks"][payload["task"]], directory, "policy"))
    if operation == "protected":
        from validation.tier0_rank_campaign import _read
        from validation.tier0_design import require_campaign_ready
        from workloads.rl_routine import evaluate_checkpoint
        root = Path(payload["root"])
        # The parent independently verifies every search before freezing and
        # again at acceptance. A child needs its frozen checkpoint/recipe, not
        # an expensive replay of every other optimizer for every policy.
        bundle = _read(root, payload["search_freeze"])
        design = _read(root, bundle["design"])
        require_campaign_ready(design, bundle["phase"])
        from validation.tier0_phase_contracts import require_execution_environment

        require_execution_environment(design, inspect_device=True)
        matching = []
        for slot in bundle["slots"]:
            if slot["plan"] is not None:
                plan = _read(root, slot["plan"])
                matching.extend((slot, item) for item in plan["evaluations"]
                                if item["checkpoint"] == payload["checkpoint"] and item["seed"] == payload["seed"])
        if len(matching) != 1:
            raise ValueError("Protected job is not a unique frozen policy/seed")
        slot, item = matching[0]
        record = _read(root, slot["search"])
        observation = record["observations"][item["observation_index"]]
        for name, ref in observation["artifact_refs"].items():
            _read(root, ref, parse=name != "checkpoint")
        return evaluate_checkpoint(_read(root, payload["checkpoint"], parse=False), payload["seed"])
    raise ValueError("Unknown fixed worker operation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    directory = args.worker.resolve().parent
    request = read_bound_json(directory, {"path": args.worker.name, "sha256": args.sha256})
    start = time.monotonic_ns()
    response = {"identity": _identity(), "request_sha256": args.sha256, "nonce": request["nonce"],
                "source_digest": source_digest(), "start_ns": start}
    if response["source_digest"] != request["source_digest"] or request["policy"] != POLICY:
        raise ValueError("Source/policy differs before execution")
    try:
        output = _execute(request["payload"], directory)
        json.dumps(output, allow_nan=False)
        response.update(status="complete", output=output)
    except Exception as exc:
        response.update(status="failed", output=None, failure=f"{type(exc).__name__}: {exc}")
    response["finish_ns"] = time.monotonic_ns()
    _write(directory / "response.json", response)


if __name__ == "__main__":
    main()
