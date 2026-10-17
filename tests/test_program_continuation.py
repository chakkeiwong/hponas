"""Phase boundaries and scientific blockers must not hide eligible repair."""

import copy

import pytest

from tools.program_continuation import continuation


@pytest.fixture
def plan():
    return {"work_items": [
        {"id": "STAT", "state": "in_progress", "dependencies": [], "decision_dependencies": []},
        {"id": "VAL", "state": "blocked", "dependencies": ["STAT"], "decision_dependencies": ["FREEZE"]}],
        "decisions": [{"id": "FREEZE", "status": "open"}], "evidence": [{"id": "E"}],
        "continuation": {"policy": "repair_verify_refresh_advance_v1", "steps": [
            {"id": "repair", "work_item": "VAL", "kind": "preparation", "state": "planned",
             "dependencies": [], "action": "Repair independent raw reconstruction", "done_when": "Adversarial raw checks pass", "evidence_refs": []},
            {"id": "campaign", "work_item": "VAL", "kind": "execution", "state": "planned",
             "dependencies": ["repair"], "action": "Execute frozen evidence campaign", "done_when": "Raw evidence and recomputed outcome exist", "evidence_refs": []}]}}


def test_blocked_acceptance_does_not_block_eligible_preparation(plan):
    result = continuation(plan)
    assert result["status"] == "CONTINUE" and not result["stop_eligible"]
    assert result["next_step"]["id"] == "repair"
    assert result["waiting"] == [{"id": "campaign", "dependencies": ["repair", "STAT", "FREEZE"]}]


def test_finished_repair_refreshes_unrepresented_dependencies_instead_of_stopping(plan):
    plan["continuation"]["steps"][0].update(state="complete", evidence_refs=["E"])
    assert continuation(plan)["status"] == "REFRESH_PHASE"
    assert not continuation(plan)["stop_eligible"]


def test_external_blocker_only_stops_dependents(plan):
    blocked = copy.deepcopy(plan["continuation"]["steps"][0])
    blocked.update(id="facts", state="blocked", evidence_refs=["E"], blocker={
        "kind": "missing_external_evidence", "fact": "No independently anchored historical event exists",
        "attempted_resolution": "Checked all retained source and event records",
        "resume_when": "A verifiable anchor is available or the prospective design is justified"})
    plan["continuation"]["steps"].insert(0, blocked)
    assert continuation(plan)["next_step"]["id"] == "repair"
    plan["continuation"]["steps"][1]["dependencies"] = ["facts"]
    result = continuation(plan)
    assert result["status"] == "BLOCKED" and result["stop_eligible"]


@pytest.mark.parametrize("fault", ["implementation", "no_evidence", "no_attempt", "no_resume"])
def test_software_backlog_or_unexplained_unknown_is_not_an_external_blocker(plan, fault):
    step = plan["continuation"]["steps"][0]
    step.update(state="blocked", evidence_refs=["E"], blocker={"kind": "missing_external_evidence",
                "fact": "missing", "attempted_resolution": "read sources", "resume_when": "source supplied"})
    if fault == "implementation":
        step["blocker"]["kind"] = "unimplemented_verifier"
    elif fault == "no_evidence":
        step["evidence_refs"] = []
    else:
        step["blocker"].pop("attempted_resolution" if fault == "no_attempt" else "resume_when")
    with pytest.raises(ValueError, match="blocker"):
        continuation(plan)


@pytest.mark.parametrize("fault", ["cycle", "unknown", "unbound", "premature", "duplicate"])
def test_queue_integrity_refuses_false_handoffs(plan, fault):
    a, b = plan["continuation"]["steps"]
    if fault == "cycle":
        a["dependencies"] = ["campaign"]
    elif fault == "unknown":
        a["dependencies"] = ["missing"]
    elif fault == "unbound":
        a["state"] = "complete"
    elif fault == "premature":
        b.update(state="complete", evidence_refs=["E"])
    else:
        b["id"] = a["id"]
    with pytest.raises(ValueError):
        continuation(plan)


def test_queue_completion_requires_next_phase_refresh_until_master_is_complete(plan):
    for step in plan["continuation"]["steps"]:
        step.update(state="complete", evidence_refs=["E"])
    assert continuation(plan)["status"] == "REFRESH_PHASE"
    for work in plan["work_items"]:
        work["state"] = "complete"
    assert continuation(plan)["status"] == "COMPLETE"
    assert continuation(plan)["scientific_acceptance"] is False


def test_shared_dependency_graph_with_external_blocker_has_linear_visits(plan):
    """A single blocked branch must not enumerate every path through a DAG."""
    visits = 0

    class Dependencies(list):
        def __iter__(self):
            nonlocal visits
            visits += 1
            # Count operations rather than relying on a machine-speed timeout.
            assert visits < 1000, "Shared predecessors were traversed exponentially"
            return super().__iter__()

    template = plan['continuation']['steps'][0]
    shared = []
    previous = []
    for level in range(24):
        current = [f'level-{level}-{side}' for side in range(2)]
        for ident in current:
            shared.append({**template, 'id': ident, 'state': 'complete',
                           'dependencies': Dependencies(previous), 'evidence_refs': ['E']})
        previous = current
    blocked = {**template, 'id': 'facts', 'state': 'blocked', 'evidence_refs': ['E'],
               'blocker': {'kind': 'missing_external_evidence', 'fact': 'No eligible history',
                           'attempted_resolution': 'Read retained histories', 'resume_when': 'History exists'}}
    # Execute needs an unresolved work/decision prerequisite. Campaign reaches
    # the completed diamond graph through execute while assessing blockers.
    execute = {**template, 'id': 'execute', 'kind': 'execution',
               'dependencies': Dependencies(previous)}
    campaign = {**plan['continuation']['steps'][1], 'dependencies': ['execute']}
    plan['continuation']['steps'] = [*shared, blocked, campaign, execute]
    result = continuation(plan)
    assert result['status'] == 'REFRESH_PHASE'
    assert not result['stop_eligible']
    assert result['external_blockers'][0]['id'] == 'facts'
