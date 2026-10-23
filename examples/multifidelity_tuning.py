"""Bounded self-contained ASHA/median, resume/restart and crash examples.

Run from the checkout: python -m examples.multifidelity_tuning --output-dir /tmp/mf
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import tempfile

from hponas import IncompleteStudyError, LocalExecutor, Study
from hponas.schedulers import ASHAConfig, ASHAScheduler
from hponas.searchers.base import BaseSearcher
from hponas.space import Knob, SearchSpace
from hponas.types import Config
from workloads.streaming_quadratic import StreamingQuadratic


def exact(index, step):
    eta = Fraction(index, 40)
    return (1-eta)**(2*step)/100 + (1-3*eta)**(2*step)


def close(actual, expected):
    if not math.isclose(actual, float(expected), rel_tol=1e-10, abs_tol=1e-13):
        raise ValueError(f"Independent trajectory mismatch: {actual} != {expected}")


class FixedInventory(BaseSearcher):
    def __init__(self, order):
        super().__init__(SearchSpace([Knob("eta_index", "integer", (1, 25))]), seed=0)
        self.order, self.cursor = list(order), 0

    def suggest(self):
        if self.cursor >= len(self.order):
            raise ValueError("Fixed proposal inventory exhausted")
        config = Config({"eta_index": self.order[self.cursor]})
        self.cursor += 1
        return config

    def get_state(self):
        return {**super().get_state(), "order": self.order.copy(), "cursor": self.cursor}

    def set_state(self, state):
        if state.get("order") != self.order or type(state.get("cursor")) is not int or not 0 <= state["cursor"] <= len(self.order):
            raise ValueError("Changed proposal inventory or cursor")
        super().set_state(state)
        self.cursor = state["cursor"]


class InterruptibleQuadratic(StreamingQuadratic):
    def __init__(self, *, crash=False):
        super().__init__()
        self.crash, self.crashed = crash, False

    def _after_report(self, step):
        if self.crash and not self.crashed and step == 3:
            self.crashed = True
            raise KeyboardInterrupt("Injected after durable non-rung report")


def scheduler(median, *, full=False):
    return ASHAScheduler(ASHAConfig(r_min=8 if full else 1, r_max=8, eta=2,
                                  median_stopping=median, report_grid=tuple(range(1,9))))


def run_one(output, name, order, policy, median, *, full=False, crash=False):
    directory = output/name
    directory.mkdir()
    workload = InterruptibleQuadratic(crash=crash)
    executor = LocalExecutor()
    study = Study(FixedInventory(order), executor, workload, budget=len(order), maximize=False,
                  scheduler=scheduler(median, full=full), continuation=policy,
                  checkpoint_dir=directory if crash else None, study_name=name, legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
    try:
        try:
            outcome = study.run()
        except KeyboardInterrupt:
            if not crash or not workload.crashed:
                raise
            retained_checkpoint = directory/(name+"_checkpoint.json")
            (directory/"interrupted_checkpoint.json").write_bytes(retained_checkpoint.read_bytes())
            executor.shutdown()
            executor = LocalExecutor()
            study = Study(FixedInventory(order), executor, workload, maximize=False,
                          scheduler=scheduler(median, full=full), continuation=policy,
                          checkpoint_dir=directory, study_name=name, legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
            study.load_checkpoint(retained_checkpoint)
            outcome = study.run()
        except IncompleteStudyError as exc:
            outcome = exc.result
    finally:
        executor.shutdown()
    if crash and not workload.crashed:
        raise ValueError("Frozen interruption point was not reached")
    close(outcome.total_cost, len(workload.updates))
    endpoints = []
    for result in outcome.history:
        trial = study.trials[result.trial_id]
        if result.status == "completed":
            close(result.objective_value, exact(trial.config.values["eta_index"], int(trial.fidelity)))
        endpoints.append({"trial": trial.to_dict(), "result": result.to_dict()})
    full_indices = sorted({study.trials[r.trial_id].config.values["eta_index"] for r in outcome.history
                           if r.status == "completed" and study.trials[r.trial_id].fidelity == 8})
    exact_order = sorted(range(1,26), key=lambda i: exact(i,8))
    best_index = min(full_indices, key=lambda i: exact(i,8)) if full_indices else None
    if best_index is not None:
        close(outcome.best_value, exact(best_index,8))
    top3 = exact_order[:3]
    summary = {"name": name, "policy": policy, "median": median, "full_reference": full,
               "crash_injected": crash, "status": outcome.status, "physical_updates": len(workload.updates),
               "accounted_cost": outcome.total_cost, "evaluations": len(outcome.history),
               "full_fidelity_indices": full_indices, "full_fidelity_best_index": best_index,
               "full_fidelity_best_value": outcome.best_value, "exact_optimal_index": exact_order[0],
               "optimal_reached_full_fidelity": exact_order[0] in full_indices,
               "exact_top3_indices": top3, "top3_reached_full_fidelity": sorted(set(top3)&set(full_indices)),
               "not_reached_full_fidelity_indices": sorted(set(order)-set(full_indices))}
    (directory/"raw.json").write_text(json.dumps({"summary": summary, "calls": workload.calls,
        "updates": workload.updates, "endpoints": endpoints, "events": study._events,
        "scheduler": study.scheduler.state_dict()}, indent=2, allow_nan=False)+"\n")
    return summary



def orders():
    return {"ascending": list(range(1,26)), "descending": list(range(25,0,-1)),
            "alternating": [v for pair in zip(range(1,13), range(25,13,-1)) for v in pair]+[13]}


def run(directory):
    proposals = orders()
    runs = [run_one(directory, "full", proposals["ascending"], "resume", False, full=True)]
    for name, order in proposals.items():
        for median in [False, True]:
            for policy in ["resume", "restart"]:
                runs.append(run_one(directory, f"{name}-{policy}-median{int(median)}", order, policy, median))
    runs.append(run_one(directory, "crash-resume", proposals["ascending"], "resume", False, crash=True))
    with (directory / "summary.json").open("x") as handle:
        json.dump({"scope": "finite streaming/accounting conformance", "V06_accepted": False, "runs": runs}, handle, indent=2)
        handle.write("\n")
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="multifidelity-", dir=args.output_dir))
    runs = run(directory)
    print(json.dumps({"directory": str(directory), "cases": len(runs), "V06_accepted": False,
                      "physical_updates": sum(r["physical_updates"] for r in runs)}))


if __name__ == "__main__":
    main()
