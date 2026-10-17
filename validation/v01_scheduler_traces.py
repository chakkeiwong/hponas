"""Independent scheduler loops on recorded learning curves, engineering only.

Each actor generates its own configurations and reads its own table outcomes.
Table fidelities become consecutive reporting units; no reward is interpolated.
PASHA explicitly uses a sorted-set reference adapter because the verbatim
source's epsilon can depend on hash order. This is not whole-vendor equivalence.
"""

from __future__ import annotations

import statistics

import numpy as np

from validation.reference_checks import PASHA_SHA256, REFERENCE_FILES, pasha_reference, promotion_reference

SCHEDULERS = ("ASHA", "Median", "PASHA")


class _Wrapper:
    def __init__(self, component, maximum):
        from hponas.schedulers import ASHAConfig, ASHAScheduler, PASHAConfig, PASHAScheduler

        self.component, self.maximum = component, maximum
        if component == "PASHA":
            self.scheduler = PASHAScheduler(PASHAConfig(r_max=maximum))
        else:
            self.scheduler = ASHAScheduler(ASHAConfig(
                r_min=maximum if component == "Median" else 1, r_max=maximum,
                median_stopping=component == "Median", report_grid=tuple(range(1, maximum + 1))))

    def schedule(self):
        promotion = self.scheduler.promote()
        return promotion[0] if promotion else None

    def add(self, tid, start, target):
        pass

    def report(self, tid, step, loss):
        if self.component == "PASHA":
            decision = self.scheduler.report(tid, step, loss)
            return decision, self.scheduler.current_max_fidelity, self.scheduler._epsilon
        return self.scheduler.report(tid, step, loss, is_progress=True), self.maximum, None

    def finish(self, tid, step, decision):
        if self.component != "PASHA" and decision == "stop":
            pruned = self.scheduler._terminal.get(tid) == "pruned" or step < self.maximum
            self.scheduler.finish(tid, "pruned" if pruned else "completed")


class _PromotionReference:
    def __init__(self, component, maximum):
        self.component, self.maximum = component, maximum
        namespace = pasha_reference(canonical_pairs=True) if component == "PASHA" else promotion_reference()
        kind = "PASHARungSystem" if component == "PASHA" else "PromotionRungSystem"
        self.scheduler = namespace[kind]([1, 3, 9], [1/3] * 3, "loss", "min", "step", maximum)

    def schedule(self):
        promotion = self.scheduler.on_task_schedule("unused")
        return (promotion["trial_id"], promotion["milestone"]) if promotion else None

    def add(self, tid, start, target):
        self.scheduler.on_task_add(tid, 0, new_config=start == 0,
                                   resume_from=start, milestone=target)

    def report(self, tid, step, loss):
        report = self.scheduler.on_task_report(tid, {"step": step, "loss": loss}, 0)
        decision = ("continue" if report["task_continues"] else
                    "stop" if step == self.maximum else "pause")
        cap = self.scheduler.current_max_t if self.component == "PASHA" else self.maximum
        epsilon = float(self.scheduler.epsilon) if self.component == "PASHA" else None
        return decision, cap, epsilon

    def finish(self, tid, step, decision):
        self.scheduler.on_task_remove(tid)


class _MedianReference:
    """Independent completed-reference running-mean rule from D-SCHEDULER."""

    def __init__(self, maximum):
        self.maximum, self.curves, self.completed = maximum, {}, []

    def schedule(self):
        return None

    def add(self, tid, start, target):
        self.curves[tid] = []

    def report(self, tid, step, loss):
        curve = self.curves[tid]
        curve.append(loss)
        references = [statistics.mean(self.curves[ref][:step]) for ref in self.completed]
        prune = len(references) >= 5 and statistics.mean(curve) > statistics.median(references)
        return "stop" if prune or step == self.maximum else "continue", self.maximum, None

    def finish(self, tid, step, decision):
        # A pruned final report is not a successful completed reference. The
        # driver supplies that distinction using the reference's own scores.
        if step == self.maximum:
            values = [statistics.mean(self.curves[ref]) for ref in self.completed]
            if len(values) < 5 or statistics.mean(self.curves[tid]) <= statistics.median(values):
                self.completed.append(tid)


def _reference(component, maximum):
    return _MedianReference(maximum) if component == "Median" else _PromotionReference(component, maximum)


def _recipe(projection, component, optimizer_seed, table_seed, count):
    grid = sorted(projection.table.training_steps)
    if (component not in SCHEDULERS or type(count) is not int or not 1 <= count <= 50
            or type(optimizer_seed) is not int or not 0 <= optimizer_seed < 2**31
            or type(table_seed) is not int or table_seed not in projection.table.seeds):
        raise ValueError("Known scheduler, recorded seed and bounded diagnostic count required")
    if not 10 <= len(grid) <= 27 or grid != [grid[0] * i for i in range(1, len(grid) + 1)]:
        raise ValueError("Scheduler table needs 10 to 27 equally spaced recorded fidelities")
    # This bounded recipe has exactly three nonterminal geometric rungs.
    maximum = len(grid)
    return {"component": component, "optimizer_seed": optimizer_seed, "table_seed": table_seed,
            "root_count": count, "report_grid": grid, "maximum": maximum,
            "rungs": [maximum] if component == "Median" else [1, 3, 9, maximum],
            "resource_unit": grid[0], "direction": "maximize_recorded_return",
            "dispatch": "one_worker_promotions_before_new_roots", "missing": "halt_without_replacement",
            "reference": {"ASHA": "syne_tune_0_13_0_verbatim_promotion",
                          "PASHA": "syne_tune_0_13_0_sorted_set_pair_adapter",
                          "Median": "independent_completed_reference_running_mean"}[component]}


def _trace(projection, actor, recipe):
    rng = np.random.RandomState(recipe["optimizer_seed"])
    rows, points, last_steps, next_trial = [], {}, {}, 0
    while True:
        dispatch = actor.schedule()
        if dispatch:
            tid, target = dispatch
            start = last_steps[tid]
            kind = "promotion"
        elif next_trial < recipe["root_count"]:
            tid, start = str(next_trial), 0
            target = recipe["maximum"] if recipe["component"] == "Median" else 1
            points[tid] = rng.uniform(size=len(projection.coordinates)).tolist()
            next_trial += 1
            kind = "new"
        else:
            return {"rows": rows, "status": "complete", "roots_started": next_trial}
        rows.append({"kind": kind, "trial_id": tid, "start": start, "target": target,
                     "proposal": points[tid]})
        actor.add(tid, start, target)
        for step in range(int(start) + 1, int(target) + 1):
            cell = projection.evaluate(points[tid], seed=recipe["table_seed"],
                                       training_steps=recipe["report_grid"][step - 1])
            if cell["status"] != "finite":
                rows.append({"kind": "missing", "trial_id": tid, "step": step, **cell})
                return {"rows": rows, "status": "unresolved_cell", "roots_started": next_trial}
            decision, cap, epsilon = actor.report(tid, step, -cell["value"])
            rows.append({"kind": "report", "trial_id": tid, "step": step, **cell,
                         "decision": decision, "cap": cap, "epsilon": epsilon})
            last_steps[tid] = step
            if decision != "continue":
                break
        actor.finish(tid, step, decision)


def compare_scheduler_table_traces(projection, component, *, optimizer_seed, table_seed, count):
    recipe = _recipe(projection, component, optimizer_seed, table_seed, count)
    actual = _trace(projection, _Wrapper(component, recipe["maximum"]), recipe)
    reference = _trace(projection, _reference(component, recipe["maximum"]), recipe)
    report = {"kind": "v01_scheduler_table_trace", "recipe": recipe,
              "projection": projection.specification, "projection_digest": projection.digest,
              "reference_sources": {**REFERENCE_FILES, "hyperband_pasha.py": PASHA_SHA256},
              "actual": actual, "reference": reference, "verdict": "INCONCLUSIVE",
              "certifies_acceptance": False, "cost_kind": "external_table_runtime_not_recorded"}
    report["comparison"] = verify_scheduler_table_traces(projection, report)
    return report


def verify_scheduler_table_traces(projection, report):
    """Rebuild reference decisions from original cells without the wrapper.

    The complete actual trajectory must match the independently regenerated
    reference to agree. This verifies numerical traces, not execution origin,
    all-seed equality in law, or the unmodified PASHA epsilon implementation.
    """
    supplied = report["recipe"]
    recipe = _recipe(projection, supplied["component"], supplied["optimizer_seed"],
                     supplied["table_seed"], supplied["root_count"])
    if (report.get("kind") != "v01_scheduler_table_trace" or supplied != recipe
            or report.get("projection_digest") != projection.digest
            or report.get("projection") != projection.specification
            or report.get("reference_sources") != {**REFERENCE_FILES, "hyperband_pasha.py": PASHA_SHA256}):
        raise ValueError("Scheduler trace recipe/source binding changed")
    reference = _trace(projection, _reference(recipe["component"], recipe["maximum"]), recipe)
    if report["reference"] != reference:
        raise ValueError("Scheduler reference trace differs from independently reconstructed table decisions")
    actual = report["actual"]
    for row in actual["rows"]:
        if row["kind"] in {"report", "missing"}:
            cell = projection.evaluate(row["proposal"], seed=recipe["table_seed"],
                                       training_steps=recipe["report_grid"][row["step"]-1])
            if any(row.get(key) != value for key, value in cell.items()):
                raise ValueError("Scheduler trace outcome differs from original recorded cell")
    mismatches = [index for index, (a, b) in enumerate(zip(actual["rows"], reference["rows"])) if a != b]
    return {"exact_trace_agreement": actual == reference, "mismatch_indices": mismatches,
            "equal_trace_lengths": len(actual["rows"]) == len(reference["rows"]),
            "complete_traces": actual["status"] == reference["status"] == "complete",
            "certifies_distributional_equivalence": False,
            "reference_envelope": recipe["reference"]}
