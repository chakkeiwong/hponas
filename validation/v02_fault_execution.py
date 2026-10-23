"""Record actual V02 process interruption and ordered concurrent CPU fixtures.

The independent verifier lives in v02_raw_reconstruction and never imports
Study, ReplayEngine, this objective or its result summaries. No workload is run.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from validation.v02_raw_reconstruction import CRASH_PLAN, CONCURRENT_PLAN


ROOT = Path(__file__).resolve().parents[1]


def write_once(path, value):
    """Publish complete evidence once; polling workers never see partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temporary.open("x") as handle:
        json.dump(value, handle, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)  # Exclusive publication; never replace an observation.
    finally:
        temporary.unlink()


def bind(root, path):
    path = Path(path).resolve()
    return {"path": str(path.relative_to(Path(root).resolve())),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _space():
    from hponas import Knob, SearchSpace

    return SearchSpace([Knob("x", "continuous", (0.0, 1.0))])


def recorded_objective(config, trial_id, seed, *, journal, stage, order=None):
    """A fixed polynomial with independently persisted start/finish observations."""
    journal = Path(journal)
    index = int(trial_id.rsplit("_", 1)[1])
    start = {"trial_id": trial_id, "config": config, "seed": seed, "stage": stage,
             "pid": os.getpid(), "thread": threading.get_ident(), "host": socket.gethostname(),
             "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
             "start_ns": time.monotonic_ns()}
    write_once(journal / f"{index}.start.json", start)
    if stage == "before_crash" and index == CRASH_PLAN["interrupt_index"]:
        os._exit(CRASH_PLAN["exit_code"])
    if order is not None:
        width = CONCURRENT_PLAN["workers"]
        batch = list(range(index // width * width, (index // width + 1) * width))
        ordered = batch if order == "forward" else batch[::-1]
        position = ordered.index(index)
        deadline = time.monotonic() + CONCURRENT_PLAN["barrier_timeout_seconds"]
        needed = [journal / f"{item}.start.json" for item in batch]
        if position:
            needed.append(journal / f"{ordered[position - 1]}.finish.json")
        while not all(path.is_file() for path in needed):
            if time.monotonic() >= deadline:
                raise TimeoutError("V02 bounded worker barrier did not complete")
            time.sleep(.002)
    value = -((config["x"] - .4) ** 2)
    finish = {**start, "finish_ns": time.monotonic_ns(), "value": value, "cost": 1.0}
    write_once(journal / f"{index}.finish.json", finish)
    return {"value": value, "cost": 1.0, "metadata": {"v02_worker": finish}}


def _study(directory, *, name, seed, count, objective, executor=None, width=1):
    from hponas import LocalExecutor, RandomSearcher, Study
    from hponas.events import EventLog

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    log = EventLog(directory / "events.jsonl")
    study = Study(RandomSearcher(_space(), seed=seed), executor or LocalExecutor(), objective,
                  budget=count, study_name=name, checkpoint_dir=directory, event_log=log, max_concurrent=width, legacy_reason='Frozen validation protocol owns independent evaluation roles')
    return study


def _run_bindings(root, directory, name):
    directory = Path(directory)
    return {"checkpoint": bind(root, directory / f"{name}_checkpoint.json"),
            "event_log": bind(root, directory / "events.jsonl"),
            "journal": [bind(root, path) for path in sorted((directory / "journal").glob("*.json"))]}


def crash_worker(directory):
    directory = Path(directory)
    objective = functools.partial(recorded_objective, journal=str(directory / "journal"), stage="before_crash")
    study = _study(directory, name="crash", seed=44, count=50, objective=objective)
    study.run()
    raise RuntimeError("Crash fixture unexpectedly returned")


def execute_crash(root):
    """Preserve the interruption checkpoint before any resume can overwrite it."""
    from hponas import LocalExecutor

    root = Path(root).resolve()
    directory = root / "crash-raw"
    directory.mkdir(parents=True, exist_ok=False)
    write_once(directory / "plan.json", CRASH_PLAN)
    command = [sys.executable, "-m", "validation.v02_fault_execution", "--crash-worker", str(directory / "before")]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    started = time.monotonic_ns()
    with (directory / "stdout.txt").open("xb") as stdout, (directory / "stderr.txt").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        try:
            returncode = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
    write_once(directory / "process.json", {"command": command, "pid": process.pid,
               "returncode": returncode, "started_ns": started, "finished_ns": time.monotonic_ns()})
    if returncode != CRASH_PLAN["exit_code"]:
        raise RuntimeError(f"Crash process returned {returncode}; raw output retained in {directory}")
    before = _run_bindings(root, directory / "before", "crash")
    after_dir = directory / "after"
    objective = functools.partial(recorded_objective, journal=str(after_dir / "journal"), stage="after_crash")
    resumed = _study(after_dir, name="crash", seed=0, count=50, objective=objective, executor=LocalExecutor())
    resumed.load_checkpoint(directory / "before/crash_checkpoint.json")
    resumed.run()
    return {"id": "crash_resume", "n_trials": 50, "seed": 44,
            "raw_evidence": {"kind": "v02_crash_raw_v1", "plan": bind(root, directory / "plan.json"),
                             "process": bind(root, directory / "process.json"),
                             "before": before, "after": _run_bindings(root, after_dir, "crash")},
            "cases": [{"name": "raw_evidence_required", "expected": True, "actual": True}]}


def execute_concurrency(root, *, executor_kind="ray"):
    """Two instrumented four-worker runs with opposite completion orders.

    Local threads are useful engineering fixtures. Only actual Ray process
    evidence can satisfy the frozen concurrent_replay scenario's executor rule.
    """
    from hponas import LocalExecutor, RayExecutor

    if executor_kind not in {"ray", "local_threads"}:
        raise ValueError("Unknown concurrent fixture executor")
    root = Path(root).resolve()
    directory = root / "concurrent-raw"
    directory.mkdir(parents=True, exist_ok=False)
    write_once(directory / "plan.json", {**CONCURRENT_PLAN, "executor": executor_kind})
    runs = {}
    for order in ("forward", "reverse"):
        run = directory / order
        executor = (RayExecutor(num_workers=4, max_retries=0, timeout=45) if executor_kind == "ray"
                    else LocalExecutor(mode="async", max_workers=4))
        objective = functools.partial(recorded_objective, journal=str(run / "journal"), stage=order, order=order)
        study = _study(run, name="concurrent", seed=45, count=20, objective=objective, executor=executor, width=4)
        study.run()
        runs[order] = _run_bindings(root, run, "concurrent")
    primary_log = runs["forward"]["event_log"]
    return {"id": "concurrent_replay", "n_trials": 20, "seed": 45, "workers": 4,
            "event_log": {**primary_log, "path": str(root / primary_log["path"])}, "scheduler_config": None,
            "raw_evidence": {"kind": "v02_concurrent_raw_v1", "plan": bind(root, directory / "plan.json"),
                             "runs": runs},
            "cases": [{"name": "raw_evidence_required", "expected": True, "actual": True}]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crash-worker", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--executor", choices=("ray", "local_threads"), default="ray")
    args = parser.parse_args()
    if args.crash_worker:
        crash_worker(args.crash_worker)
        return
    if args.output_dir is None:
        parser.error("--output-dir required")
    from tools.source_identity import source_digest
    from validation.v02_raw_reconstruction import verify_crash, verify_concurrency

    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    frozen_source = source_digest()
    write_once(root / "freeze.json", {"source_digest": frozen_source, "executor": args.executor,
                                      "kind": "v02_raw_engineering_freeze"})
    crash = execute_crash(root)
    concurrent = execute_concurrency(root, executor_kind=args.executor)
    report = {"kind": "v02_raw_engineering_execution", "source_digest": frozen_source,
              "certifies_acceptance": False, "verdict": "INCONCLUSIVE",
              "scenarios": [crash, concurrent],
              "reconstruction": {"crash": verify_crash(root, crash),
                                 "concurrency": verify_concurrency(root, concurrent, executor_kind=args.executor)}}
    if source_digest() != frozen_source:
        raise ValueError("Source changed during raw V02 engineering execution")
    write_once(root / "report.json", report)
    print("Raw crash and concurrency evidence reconstructed; engineering only, acceptance INCONCLUSIVE.")


if __name__ == "__main__":
    main()
