"""Bounded development-only PPO compatibility/timing, separate from acceptance."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
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


def profile_errors(plan):
    """A profiling phase has no power, holdout or confirmation prerequisites."""
    from workloads.rl_routine import RLSettings, validate_config

    errors = []
    if (plan.get("kind") != "tier0_development_profile_v1" or plan.get("role") != "development"
            or plan.get("certifies_acceptance") is not False or plan.get("device") not in {"cpu", "cuda"}):
        errors.append("Explicit development-only profile contract required")
    if plan.get("device") == "cuda" and (type(plan.get("gpu_index")) is not int or plan["gpu_index"] < 0):
        errors.append("Development CUDA profile requires one explicit GPU index")
    cap = plan.get("cap_seconds")
    if isinstance(cap, bool) or not isinstance(cap, (float, int)) or not math.isfinite(cap) or not 0 < cap <= 360:
        errors.append("Development profile requires a hard cap at most 360 wall seconds on one device")
    if (type(plan.get("training_seed")) is not int or not 0 <= plan["training_seed"] < 1000
            or type(plan.get("evaluation_seed")) is not int or not 1000 <= plan["evaluation_seed"] < 10000):
        errors.append("Separate development seeds required")
    try:
        settings = RLSettings(**plan["settings"])
        valid, reason = validate_config(plan["config"])
        if not valid:
            errors.append(reason)
        if settings.max_timesteps > 100000:
            errors.append("Development profile exceeds bounded training fidelity")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Incomplete development recipe: {exc}")
    if not isinstance(plan.get("authorization_basis"), str) or not plan["authorization_basis"].strip():
        errors.append("Development execution authorization basis missing")
    return errors


def _write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _worker(directory, digest):
    plan = read_bound_json(directory, {"path": "plan.json", "sha256": digest})
    errors = profile_errors(plan)
    if errors:
        raise ValueError("; ".join(errors))
    from workloads.rl_routine import RLSettings, evaluate_checkpoint, rl_routine
    import jax

    expected = "cpu" if plan["device"] == "cpu" else "gpu"
    if jax.default_backend() != expected or len(jax.devices()) != 1:
        raise ValueError("Development allocation requires exactly its one declared device")
    _write(directory / "environment.json", {"python": sys.executable, "backend": jax.default_backend(),
           "devices": [str(device) for device in jax.devices()], "source_digest": source_digest(),
           "xla_flags": os.environ.get("XLA_FLAGS"),
           "compiler_packages": {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()
                                 if dist.metadata["Name"] in {"nvidia-cuda-nvcc", "nvidia-nvvm",
                                                             "jax-cuda13-plugin", "jax-cuda13-pjrt"}},
           "versions": {package: importlib.metadata.version(package) for package in
                        ("jax", "jaxlib", "brax", "torch", "botorch", "optuna")}})
    started = time.monotonic()
    raw = rl_routine(plan["config"], seed=plan["training_seed"], settings=RLSettings(**plan["settings"]),
                     artifact_dir=directory / "policies", trial_id="development")
    trained = time.monotonic()
    _write(directory / "search.json", raw)
    evaluated = evaluate_checkpoint(raw["artifacts"]["checkpoint"], plan["evaluation_seed"])
    _write(directory / "evaluation.json", evaluated)
    _write(directory / "timing.json", {"search_seconds": trained - started,
           "separate_evaluation_seconds": time.monotonic() - trained,
           "role": "development", "certifies_acceptance": False})


def run_profile(plan, directory):
    errors = profile_errors(plan)
    if errors:
        raise ValueError("; ".join(errors))
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    _write(directory / "plan.json", plan)
    digest = hashlib.sha256((directory / "plan.json").read_bytes()).hexdigest()
    fingerprint = source_digest()
    _write(directory / "freeze.json", {"source_digest": fingerprint, "plan_sha256": digest,
           "monotonic_ns": time.monotonic_ns(), "certifies_acceptance": False})
    command = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", str(directory), "--sha256", digest]
    environment = {**os.environ, "JAX_PLATFORMS": plan["device"],
                   "CUDA_VISIBLE_DEVICES": "" if plan["device"] == "cpu" else str(plan["gpu_index"]),
                   "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                   "XDG_CACHE_HOME": str(directory / "cache")}
    started, timeout = time.monotonic(), False
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            code = process.wait(timeout=plan["cap_seconds"])
        except subprocess.TimeoutExpired:
            timeout = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Exit racing the timeout does not erase its record.
            code = process.wait()
    elapsed = time.monotonic() - started
    files = [{"path": str(path.relative_to(directory)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(directory.rglob("*")) if path.is_file()]
    complete = code == 0 and not timeout and (directory / "timing.json").is_file() and source_digest() == fingerprint
    report = {"kind": "tier0_development_profile_result_v1", "role": "development", "source_digest": fingerprint,
              "plan_sha256": digest, "command": command, "exit_code": code, "timed_out": timeout,
              "elapsed_seconds_including_startup": elapsed, "files": files,
              "status": "complete" if complete else "timeout" if timeout else "failed",
              "timing_is_lower_bound": timeout, "certifies_acceptance": False,
              "claim": "Single fixed development recipe on one declared device; no full-campaign throughput extrapolation"}
    _write(directory / "result.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--sha256")
    parser.add_argument("--plan")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.worker:
        _worker(Path(args.worker), args.sha256)
    else:
        result = run_profile(json.loads(Path(args.plan).read_text()), args.output)
        print(json.dumps({k: result[k] for k in ("status", "elapsed_seconds_including_startup", "certifies_acceptance")}))


if __name__ == "__main__":
    main()
