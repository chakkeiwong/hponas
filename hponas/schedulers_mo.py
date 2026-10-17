"""Constraint-bound MO promotion with advisory quality signals by default."""
from copy import deepcopy
import json

from hponas.multi_objective import ObjectiveSpec
from hponas.schedulers import MOASHAConfig, MOASHAScheduler


class MultiObjectiveScheduler:
    """Endpoint rung scheduling under the exact metric contract.

    Default advisory mode promotes every feasible configuration. Explicit
    experimental Pareto selection runs MO-ASHA, without asserting V10 safety.
    Absolute constraint vetoes apply in both modes and persist across rungs.
    """

    def __init__(self, *, objectives, constraints=None, work_unit="integer_operations", r_min=1., r_max=8., eta=2., selection="advisory"):
        if selection not in {"advisory", "experimental_pareto"}:
            raise ValueError("Unknown multi-objective promotion selection")
        self.spec = ObjectiveSpec(objectives, constraints=constraints, work_unit=work_unit)
        self.metric_identity = self.spec.identity
        self.selection = selection
        self._scheduler = MOASHAScheduler(MOASHAConfig(r_min, r_max, eta, self.spec.names, [1.]*len(objectives)))
        self.config = self._scheduler.config
        self._events = []

    def report(self, trial_id, fidelity, observation):
        row = self.spec.validate_observation(observation)
        values = self.spec.normalize(row["objectives"]) if row["status"] == "completed" and row["feasible"] else [float("nan")]*len(self.spec.names)
        decision = self._scheduler.report(trial_id, fidelity, dict(zip(self.spec.names, values)))
        self._events.append({"kind": "report", "trial_id": trial_id, "fidelity": fidelity,
                             "observation": deepcopy(row), "decision": decision})
        return decision

    def promote(self):
        if self.selection == "experimental_pareto":
            promotions = self._scheduler.promote()
        else:
            promotions = []
            for tid, (rung, fidelity, values, state, vetoed) in list(self._scheduler._trial_state.items()):
                if state == "paused" and not vetoed:
                    next_fidelity = self._scheduler.rungs[rung+1]
                    promotions.append((tid, next_fidelity))
                    self._scheduler._trial_state[tid] = (rung+1, next_fidelity, values, "active", False)
        self._events.append({"kind": "promote", "promotions": [list(p) for p in promotions]})
        return promotions

    def state_dict(self):
        return deepcopy({"kind": "fixed_metric_mo_scheduler_v1", "metric": self.spec.contract,
                         "selection": self.selection, "config": self._scheduler.state_dict()["config"],
                         "events": self._events, "scheduler": self._scheduler.state_dict()})

    def load_state_dict(self, state):
        current = self.state_dict()
        if any(state.get(k) != current[k] for k in ["kind", "metric", "selection", "config"]):
            raise ValueError("Multi-objective scheduler checkpoint identity differs")
        restored = type(self)(**self.spec.contract, r_min=self.config.r_min, r_max=self.config.r_max,
                              eta=self.config.eta, selection=self.selection)
        for event in state["events"]:
            if event["kind"] == "report":
                restored.report(event["trial_id"], event["fidelity"], event["observation"])
            elif event["kind"] == "promote":
                restored.promote()
            else:
                raise ValueError("Unknown scheduler checkpoint event")
            if restored._events[-1] != event:
                raise ValueError("Scheduler decisions do not replay exactly")
        if json.dumps(restored.state_dict(), sort_keys=True) != json.dumps(state, sort_keys=True):
            raise ValueError("Scheduler state does not match its event ledger")
        self.__dict__.update(restored.__dict__)
