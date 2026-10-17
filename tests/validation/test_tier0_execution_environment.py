"""The frozen device/loader choice cannot change across phase allocations."""

import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from validation.tier0_design import load_design
from validation.tier0_isolation import run_isolated, verify_isolated
from validation.tier0_phase_contracts import (
    execution_environment_errors, experiment_digest, require_execution_environment,
)


@pytest.fixture
def runtime(monkeypatch):
    design = load_design()
    design["execution_environment"]["python"] = sys.executable
    for key, value in design["execution_environment"]["variables"].items():
        monkeypatch.setenv(key, value)
    return design


def test_resource_resize_cannot_change_experiment_device_or_loader(runtime):
    changed = copy.deepcopy(runtime)
    changed["resource"]["campaign_cap_seconds"] = 100
    assert experiment_digest(changed) == experiment_digest(runtime)
    changed["execution_environment"]["variables"]["XLA_PYTHON_CLIENT_MEM_FRACTION"] = ".10"
    assert experiment_digest(changed) != experiment_digest(runtime)


@pytest.mark.parametrize("field,value", [
    ("CUDA_VISIBLE_DEVICES", "0"), ("JAX_PLATFORMS", "cpu"),
    ("LD_LIBRARY_PATH", "relative/path"), ("XLA_PYTHON_CLIENT_MEM_FRACTION", "nan"),
])
def test_bad_runtime_cannot_be_frozen(runtime, field, value):
    runtime["execution_environment"]["variables"][field] = value
    assert execution_environment_errors(runtime)


def test_actual_environment_and_worker_backend_are_checked(runtime, monkeypatch):
    require_execution_environment(runtime)
    monkeypatch.setenv("JAX_PLATFORMS", "cpu")
    with pytest.raises(ValueError, match="Actual execution environment"):
        require_execution_environment(runtime)
    monkeypatch.setenv("JAX_PLATFORMS", "cuda")
    device = SimpleNamespace(device_kind=runtime["execution_environment"]["device_kind"])
    fake = SimpleNamespace(default_backend=lambda: "gpu", devices=lambda: [device])
    monkeypatch.setitem(sys.modules, "jax", fake)
    require_execution_environment(runtime, inspect_device=True)
    fake.devices = lambda: [device, device]
    with pytest.raises(ValueError, match="backend/device"):
        require_execution_environment(runtime, inspect_device=True)


def test_child_receipt_retains_and_independently_checks_frozen_environment(runtime, monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "unrelated-parent-device")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/unrelated/parent/libraries")
    # Incomplete budgets refuse the workload; this executes only the real
    # process/bootstrap path, with no JAX device initialization or PPO.
    ref, report = run_isolated(tmp_path, "unready", {"operation": "search", "design": runtime,
        "entry": "V05", "task": next(iter(runtime["tasks"])), "arm": "gp_log",
        "seed": 10000, "phase": "pilot"}, timeout_seconds=30)
    assert report["status"] == "failed" and report["output"] is None
    path = tmp_path / ref["path"]
    record = json.loads(path.read_text())
    assert all(record["environment"][key] == value
               for key, value in runtime["execution_environment"]["variables"].items())
    assert verify_isolated(tmp_path, ref) == report
    record["environment"]["CUDA_VISIBLE_DEVICES"] = "different-device"
    path.write_text(json.dumps(record))
    rebound = {"path": ref["path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="Recorded execution environment"):
        verify_isolated(tmp_path, rebound)
