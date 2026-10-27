"""Frozen finite 2/3-objective metrics with exact box-union hypervolume.

Bounds/directions are declared before observations. Reference is always the
worst declared normalized corner (1,...,1). Work is an integer operation count;
this module makes no statement about hardware time or parallel makespan.
"""
from copy import deepcopy
import hashlib
import json
import math


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("A finite real number is required")
    return float(value)


def front_indices(points):
    return [i for i, row in enumerate(points)
            if not any(all(a <= b for a, b in zip(other, row))
                       and any(a < b for a, b in zip(other, row)) for other in points)]


def volume(points):
    """Union of minimization boxes by recursive disjoint coordinate slabs."""
    points = sorted({tuple(p) for p in points if all(v < 1.0 for v in p)})
    if not points:
        return 0.0
    if len(points[0]) == 1:
        return 1.0 - min(p[0] for p in points)
    cuts = sorted({p[0] for p in points} | {1.0})
    return math.fsum((right-left)*volume([p[1:] for p in points if p[0] <= left])
                     for left, right in zip(cuts, cuts[1:]))


class MetricLedger:
    def __init__(self, objectives, *, feasibility_rule, work_unit="integer_operations"):
        if not isinstance(feasibility_rule, str) or not feasibility_rule.strip():
            raise ValueError("Named frozen feasibility rule is required")
        self._feasibility_rule = feasibility_rule
        if not isinstance(work_unit, str) or not work_unit.strip():
            raise ValueError("Named work unit required")
        self._work_unit = work_unit
        if not isinstance(objectives, list) or len(objectives) not in (2, 3):
            raise ValueError("Exactly two or three declared objectives are required")
        specs = []
        for obj in objectives:
            if not isinstance(obj, dict) or set(obj) != {"name", "direction", "lower", "upper"}:
                raise ValueError("Objective contract keys differ")
            if not isinstance(obj["name"], str) or not obj["name"] or obj["direction"] not in {"min", "max"}:
                raise ValueError("Named objective and explicit direction required")
            lower, upper = number(obj["lower"]), number(obj["upper"])
            if not lower < upper or not math.isfinite(upper-lower):
                raise ValueError("Objective requires a finite positive declared range")
            specs.append({**obj, "lower": lower, "upper": upper})
        if len({o["name"] for o in specs}) != len(specs):
            raise ValueError("Objective names must be unique")
        self._specs = specs
        self._rows = []

    @property
    def contract(self):
        return {"version": 1, "objectives": deepcopy(self._specs),
                "reference": [1.0]*len(self._specs), "work_unit": self._work_unit,
                "completion_order": "sequential", "failed_work": "included",
                "feasibility_rule": self._feasibility_rule}

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.contract, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def normalize(self, values):
        if not isinstance(values, (list, tuple)) or len(values) != len(self._specs):
            raise ValueError("Objective vector dimension differs")
        normalized = []
        for value, spec in zip(values, self._specs):
            value = number(value)
            lo, hi = spec["lower"], spec["upper"]
            if not lo <= value <= hi:
                raise ValueError("Objective outside frozen domain bounds")
            normalized.append((value-lo)/(hi-lo) if spec["direction"] == "min" else (hi-value)/(hi-lo))
        return normalized

    def append(self, row):
        if not isinstance(row, dict) or set(row) != {"trial_id", "values", "work", "status", "feasible"}:
            raise ValueError("Trial metric keys differ")
        if (not isinstance(row["trial_id"], str) or not row["trial_id"]
                or any(old["trial_id"] == row["trial_id"] for old in self._rows)):
            raise ValueError("Trial identities must be nonempty and unique")
        if type(row["work"]) is not int or row["work"] < 0:
            raise ValueError("Work must be a nonnegative integer operation count")
        if type(row["feasible"]) is not bool or row["status"] not in {"completed", "failed"}:
            raise ValueError("Explicit terminal status and feasibility required")
        if row["status"] == "completed":
            self.normalize(row["values"])
        elif row["values"] is not None or row["feasible"]:
            raise ValueError("Failed work has no valid objective contribution")
        self._rows.append(deepcopy(row))

    def summary(self, budget=None):
        total_work = sum(row["work"] for row in self._rows)
        if budget is None:
            budget = total_work
        if type(budget) is not int or budget < 0:
            raise ValueError("Budget must be a nonnegative integer operation count")
        consumed, indices, points, completed = 0, [], [], []
        for i, row in enumerate(self._rows):
            consumed += row["work"]
            if consumed > budget:
                break
            completed.append(row["trial_id"])
            if row["status"] == "completed" and row["feasible"]:
                indices.append(i)
                points.append(self.normalize(row["values"]))
        front = [indices[i] for i in front_indices(points)]
        return {"identity": self.identity, "budget": budget, "total_work": total_work,
                "finished_trial_ids": completed, "front_indices": front,
                "front_trial_ids": [self._rows[i]["trial_id"] for i in front],
                "hypervolume": volume(points), "reference": self.contract["reference"]}

    def curve(self, budgets):
        if not isinstance(budgets, list) or any(type(b) is not int or b < 0 for b in budgets):
            raise ValueError("Integer budget list required")
        if budgets != sorted(budgets):
            raise ValueError("Budget sequence must be nondecreasing")
        return [self.summary(budget) for budget in budgets]

    def state_dict(self):
        return {"identity": self.identity, "contract": self.contract, "rows": deepcopy(self._rows)}

    @classmethod
    def restore(cls, state, objectives, *, feasibility_rule, work_unit="integer_operations"):
        restored = cls(objectives, feasibility_rule=feasibility_rule, work_unit=work_unit)
        if (not isinstance(state, dict) or set(state) != {"identity", "contract", "rows"}
                or state["identity"] != restored.identity or state["contract"] != restored.contract
                or not isinstance(state["rows"], list)):
            raise ValueError("Checkpoint must match the exact frozen metric contract")
        for row in state["rows"]:
            restored.append(row)
        return restored


class ObjectiveSpec:
    """Frozen named objectives and constraints (each measurement <= its bound).

    Work counts actual incremental operations, independently of elapsed seconds.
    Unexpected worker failures retain unknown operation counts; they never create
    a fictitious zero-cost observation in a budget comparison.
    """

    def __init__(self, objectives, *, constraints=None, work_unit="integer_operations"):
        constraints = {} if constraints is None else constraints
        if not isinstance(constraints, dict) or any(not isinstance(k, str) or not k.strip() for k in constraints):
            raise ValueError("Named constraint upper bounds required")
        self._constraints = {k: number(v) for k, v in sorted(constraints.items())}
        rule = json.dumps({"rule": "all_measurements_le_upper_bound", "bounds": self._constraints}, sort_keys=True)
        self._template = MetricLedger(objectives, feasibility_rule=rule, work_unit=work_unit)

    @property
    def identity(self):
        return self._template.identity

    @property
    def names(self):
        return [o["name"] for o in self._template.contract["objectives"]]

    @property
    def contract(self):
        return {"objectives": self._template.contract["objectives"], "constraints": deepcopy(self._constraints),
                "work_unit": self._template.contract["work_unit"]}

    def normalize(self, values):
        if not isinstance(values, dict) or set(values) != set(self.names):
            raise ValueError("Exactly the declared named objective values are required")
        return self._template.normalize([values[name] for name in self.names])

    def observation(self, *, objectives, constraints, work, status="completed"):
        if type(work) is not int or work < 0:
            raise ValueError("Actual nonnegative integer incremental work required")
        if status not in {"completed", "failed"}:
            raise ValueError("Explicit completed/failed measurement status required")
        if status == "failed":
            if objectives is not None or constraints is not None:
                raise ValueError("Failed measurement must not supply objective/constraint values")
            feasible = False
        else:
            self.normalize(objectives)
            if not isinstance(constraints, dict) or set(constraints) != set(self._constraints):
                raise ValueError("Exactly the declared constraint measurements are required")
            constraints = {k: number(v) for k, v in constraints.items()}
            feasible = all(constraints[k] <= v for k, v in self._constraints.items())
        return deepcopy({"identity": self.identity, "objectives": objectives, "constraints": constraints,
                         "work": work, "status": status, "feasible": feasible})

    def validate_observation(self, row):
        if not isinstance(row, dict) or set(row) != {"identity", "objectives", "constraints", "work", "status", "feasible"}:
            raise ValueError("Multi-objective measurement schema differs")
        expected = self.observation(**{k: row[k] for k in ["objectives", "constraints", "work", "status"]})
        if row != expected or type(row["feasible"]) is not bool:
            raise ValueError("Multi-objective identity or feasibility differs")
        return expected

    def validate_result(self, result):
        payload = result.metadata.get("multi_objective")
        if payload is None:
            if result.is_valid():
                raise ValueError("Completed result is missing its objective vector")
            return None
        payload = self.validate_observation(payload)
        if result.is_valid() and (payload["status"] != "completed" or result.objective_value != 0.):
            raise ValueError("Multi-objective carrier/result status differs")
        return payload

    def summarize(self, results, *, endpoint_fidelity=1., budget=None):
        ledger = MetricLedger(self.contract["objectives"], feasibility_rule=self._template.contract["feasibility_rule"],
                              work_unit=self.contract["work_unit"])
        unknown = []
        for result in results:
            row = self.validate_result(result)
            if row is None or result.metadata.get("execution", {}).get("accounting") == "lower_bound_after_interruption":
                unknown.append(result.trial_id)
            completed = row is not None and row["status"] == "completed" and result.status == "completed"
            ledger.append({"trial_id": result.trial_id,
                           "values": [row["objectives"][k] for k in self.names] if completed else None,
                           "status": "completed" if completed else "failed",
                           "feasible": bool(completed and row["feasible"] and result.fidelity == endpoint_fidelity),
                           "work": row["work"] if row is not None else 0})
        if unknown and budget is not None:
            raise ValueError("An exact work-budget curve requires measured work for every attempt")
        summary = ledger.summary(budget)
        summary.update(contract=self.contract, endpoint_fidelity=endpoint_fidelity,
                       known_work_lower_bound=summary["total_work"], unmeasured_work_trial_ids=unknown,
                       exact_work=not unknown)
        if unknown:
            summary.update(total_work=None, budget=None)
        return summary
