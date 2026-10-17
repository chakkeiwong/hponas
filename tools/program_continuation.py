"""Compute eligible work at a repair/phase boundary without granting acceptance."""

from __future__ import annotations

import argparse
from functools import cache
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.program_state import ROOT, REGISTER, read_json

POLICY = "repair_verify_refresh_advance_v1"
STATES = {"planned", "in_progress", "complete", "blocked"}
EXTERNAL = {"missing_external_evidence", "unavailable_infrastructure", "resource_authorization", "scope_authorization", "user_pause"}


def continuation(program):
    queue = program.get("continuation")
    if not isinstance(queue, dict) or queue.get("policy") != POLICY:
        raise ValueError("Continuous repair/refresh policy missing")
    rows = queue.get("steps")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Continuation steps missing")
    work = {item["id"]: item for item in program["work_items"]}
    evidence = {item["id"] for item in program["evidence"]}
    steps = {}
    for step in rows:
        ident = step.get("id")
        if not isinstance(ident, str) or not ident or ident in steps:
            raise ValueError("Duplicate or invalid continuation step")
        if step.get("work_item") not in work or step.get("state") not in STATES:
            raise ValueError(f"{ident}: unknown work item/state")
        if step.get("kind") not in {"preparation", "execution"}:
            raise ValueError(f"{ident}: explicit preparation/execution scope required")
        if not all(isinstance(step.get(k), str) and step[k].strip() for k in ("action", "done_when")):
            raise ValueError(f"{ident}: concrete action/completion criterion required")
        refs = step.get("evidence_refs", [])
        if not isinstance(refs, list) or not set(refs) <= evidence:
            raise ValueError(f"{ident}: unbound continuation evidence")
        if step["state"] == "complete" and not refs:
            raise ValueError(f"{ident}: completion requires evidence")
        if step["state"] == "blocked":
            blocker = step.get("blocker", {})
            if (blocker.get("kind") not in EXTERNAL or not refs
                    or not all(isinstance(blocker.get(k), str) and blocker[k].strip()
                               for k in ("fact", "attempted_resolution", "resume_when"))):
                raise ValueError(f"{ident}: blocker requires external fact, evidence, attempt and resumption condition")
        steps[ident] = step
    visiting, visited = set(), set()

    def visit(ident):
        if ident in visiting:
            raise ValueError("Continuation dependency cycle")
        if ident in visited:
            return
        visiting.add(ident)
        dependencies = steps[ident].get("dependencies")
        if not isinstance(dependencies, list) or len(set(dependencies)) != len(dependencies):
            raise ValueError(f"{ident}: invalid dependencies")
        for dependency in dependencies:
            if dependency not in steps:
                raise ValueError(f"{ident}: unknown continuation dependency")
            visit(dependency)
            if steps[ident]["state"] in {"complete", "in_progress"} and steps[dependency]["state"] != "complete":
                raise ValueError(f"{ident}: predecessor is incomplete")
        visiting.remove(ident)
        visited.add(ident)

    for ident in steps:
        visit(ident)
    ready, waiting, blockers = [], [], []
    decisions = {item["id"]: item["status"] for item in program.get("decisions", [])}
    for step in rows:
        if step["state"] == "complete":
            continue
        if step["state"] == "blocked":
            blockers.append({"id": step["id"], **step["blocker"]})
            continue
        missing = [key for key in step["dependencies"] if steps[key]["state"] != "complete"]
        if step["kind"] == "execution":
            owner = work[step["work_item"]]
            missing += [key for key in owner["dependencies"] if work[key]["state"] != "complete"]
            missing += [key for key in owner["decision_dependencies"] if decisions.get(key) != "accepted"]
        if missing:
            waiting.append({"id": step["id"], "dependencies": missing})
        else:
            ready.append({"id": step["id"], "work_item": step["work_item"], "action": step["action"]})
    incomplete = [step for step in rows if step["state"] != "complete"]
    external_ids = {item["id"] for item in blockers}

    @cache
    def external_dependency(ident):
        if ident in external_ids:
            return True
        if ident not in steps:
            return False  # Unrepresented master prerequisite: refresh the plan.
        if steps[ident]["state"] == "complete":
            return False  # A resolved prerequisite cannot carry a live blocker.
        return any(external_dependency(dep) for dep in steps[ident]["dependencies"])

    blocked_only = bool(blockers) and all(
        any(external_dependency(dep) for dep in item["dependencies"]) for item in waiting)
    master_complete = all(w["state"] == "complete" for w in work.values())
    status = ("CONTINUE" if ready else "COMPLETE" if master_complete and not incomplete else
              "BLOCKED" if incomplete and blocked_only else "REFRESH_PHASE")
    return {"policy": POLICY, "status": status, "ready": ready, "waiting": waiting,
            "external_blockers": blockers, "next_step": ready[0] if ready else None,
            "master_complete": master_complete, "stop_eligible": status in {"BLOCKED", "COMPLETE"},
            "scientific_acceptance": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", default=ROOT / REGISTER)
    args = parser.parse_args()
    print(json.dumps(continuation(read_json(args.program)), indent=2))


if __name__ == "__main__":
    main()
