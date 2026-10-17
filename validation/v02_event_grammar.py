"""Frozen candidate adversarial event population with an independent oracle.

Generation is deterministic by case ID, not selected from passing examples.
Full acceptance still requires protocol certification of this population.
"""

import json
import numpy as np

from hponas.schedulers import ASHAConfig, ASHAScheduler
from validation.reference_checks import REFERENCE_FILES, promotion_reference, reference_promotions

GRAMMAR = "asha-progress-terminal-v1"
KINDS = ("arrival", "duplicate", "conflicting", "dropped", "late_terminal", "checkpoint")


def recipe(index):
    if type(index) is not int or not 0 <= index < 10000:
        raise ValueError("Case ID outside the declared 10,000-case population")
    rng = np.random.default_rng(92029 + index)
    size = 2 + index % 7
    values = rng.integers(-3, 4, size=size).tolist()  # Includes quantile ties.
    order = rng.permutation(size).tolist()
    kind = KINDS[index % len(KINDS)]
    if kind == "dropped":
        order = order[::2]
    return {"case_id": index, "kind": kind, "reports": [[str(i), values[i]] for i in order]}


def expected_case(spec, vendor):
    return {"promotions": reference_promotions(spec["reports"], vendor), "invariants": True}


def execute_case(spec):
    scheduler = ASHAScheduler(ASHAConfig(r_min=1, r_max=9))
    invariants = True
    for tid, value in spec["reports"]:
        scheduler.report(tid, 1, value, is_progress=True)
        if spec["kind"] == "duplicate":
            before = scheduler.state_dict()
            invariants &= scheduler.report(tid, 1, value, is_progress=True) == "pause"
            invariants &= before == scheduler.state_dict()
    if spec["kind"] == "conflicting":
        tid, value = spec["reports"][0]
        before = scheduler.state_dict()
        try:
            scheduler.report(tid, 1, value + 1, is_progress=True)
            invariants = False
        except ValueError:
            invariants &= before == scheduler.state_dict()
    if spec["kind"] == "checkpoint":
        state = json.loads(json.dumps(scheduler.state_dict()))
        restored = ASHAScheduler(scheduler.config)
        restored.load_state_dict(state)
        invariants &= restored.state_dict() == scheduler.state_dict()
        scheduler = restored
    promotions = []
    while promoted := scheduler.promote():
        invariants &= len(promoted) == 1
        promotions.extend([list(p) for p in promoted])
    invariants &= scheduler.promote() == []
    if spec["kind"] == "late_terminal":
        tid, value = spec["reports"][0]
        scheduler.finish(tid, "cancelled")
        before = scheduler.state_dict()
        invariants &= scheduler.report(tid, 3, value - 100, is_progress=True) == "stop"
        invariants &= before == scheduler.state_dict()
        scheduler.finish(tid, "cancelled")
        invariants &= before == scheduler.state_dict()
    return {"promotions": promotions, "invariants": bool(invariants)}


def population(count=10000):
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("Generated population must contain 1..10,000 cases")
    return {"grammar": GRAMMAR, "count": count, "reference_hashes": dict(REFERENCE_FILES),
            "cases": [{"spec": recipe(i), "actual": execute_case(recipe(i))} for i in range(count)]}


def verify_population(report, *, require_full=True):
    count = report.get("count")
    if (report.get("grammar") != GRAMMAR or report.get("reference_hashes") != REFERENCE_FILES
            or type(count) is not int or not 1 <= count <= 10000
            or (require_full and count != 10000) or len(report.get("cases", [])) != count):
        raise ValueError("Incomplete or changed event grammar population")
    reference = promotion_reference()
    for i, case in enumerate(report["cases"]):
        spec = recipe(i)
        if case.get("spec") != spec:
            raise ValueError("Generated case was changed, duplicated or selected post hoc")
        if case.get("actual") != expected_case(spec, reference):
            return False
    return True
