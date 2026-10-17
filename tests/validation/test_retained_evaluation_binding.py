"""Retained development requests use repository-local immutable bindings."""

import hashlib
import json
from pathlib import Path
import runpy

import pytest


@pytest.mark.parametrize("fault", [None, "changed_plan", "wrong_runtime"])
def test_retained_worker_reads_root_bindings_and_checks_runtime(tmp_path, monkeypatch, fault):
    from tools import source_identity
    from validation import tier0_phase_contracts
    from workloads import rl_routine

    namespace = runpy.run_path(str(Path(__file__).resolve().parents[2] /
        "docs/program/evidence/2026-10-01/scope-adoption/run_retained_study_evaluations.py"))
    worker = namespace["worker"]
    monkeypatch.setitem(worker.__globals__, "ROOT", tmp_path)
    monkeypatch.setattr(source_identity, "source_digest", lambda: "fixture")

    def binding(path):
        return {"path": str(path.relative_to(tmp_path)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def write(path, value):
        path.write_text(json.dumps(value))
        return binding(path)

    root, child = tmp_path / "original", tmp_path / "attempt"
    root.mkdir()
    child.mkdir()
    checkpoint = root / "policy.pkl"
    checkpoint.write_bytes(b"inert; never unpickled")
    policy = {"path": str(checkpoint), "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
    search = write(root / "search.json", {"observations": [{"artifact_refs": {"checkpoint": policy}}]})
    item = {"observation_index": 0, "checkpoint": policy, "seed": 123217680}
    schedule = write(root / "schedule.json", {"evaluations": [item]})
    workload = tmp_path / "workload.py"
    workload.write_text("# inert fixture\n")
    plan = {"source_digest": "fixture", "workload": binding(workload), "dependencies": {},
            "data_artifacts": [], "execution_environment": {"fixture": True},
            "original_run": str(root), "search": search, "schedule": schedule, "evaluations": [item]}
    ref = write(tmp_path / "plan.json", plan)
    write(child / "request.json", {"plan": ref, "index": 0})
    checked, evaluated = [], []

    def environment(design, *, inspect_device):
        # Without the sampling key the production runtime guard returns early.
        assert design["sampling"]["selection_algorithm"] == tier0_phase_contracts.SAMPLING
        assert inspect_device is True
        checked.append(design)
        if fault == "wrong_runtime":
            raise ValueError("Actual backend/device differs")

    def evaluate(path, seed):
        assert checked and path == checkpoint and seed == item["seed"]
        evaluated.append((path, seed))
        return {"seed": seed, "returns": [1.0] * 10}

    monkeypatch.setattr(tier0_phase_contracts, "require_execution_environment", environment)
    monkeypatch.setattr(rl_routine, "evaluate_checkpoint", evaluate)
    if fault == "changed_plan":
        (tmp_path / "plan.json").write_text('{}')
    if fault:
        with pytest.raises(ValueError):
            worker(child)
        assert not evaluated and not (child / "evaluation.json").exists()
    else:
        worker(child)
        assert len(evaluated) == 1
        assert json.loads((child / "evaluation.json").read_text())["returns"] == [1.0] * 10
