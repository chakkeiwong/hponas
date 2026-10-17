"""Finite Hyperband cycles with synchronous, fixed NePS bracket widths.

This scheduler supplies allocation only. PriorBand's sampling policy is separate.
Ties use registration order. Failed slots are retained and never promoted; a
failed bracket may consequently finish with fewer endpoints than its quota.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
import math

from hponas.prior_band import PriorBand, bracket_widths, identity


@dataclass(frozen=True)
class PriorBandConfig:
    r_min: float
    r_max: float
    eta: int
    promotion_policy: str = "neps_sync_finite_v1"


class PriorBandScheduler:
    def __init__(self, *, rungs, eta, bracket_id="priorband-hyperband-v1", default_at_target=False):
        validated = PriorBand(rungs=rungs, eta=eta, bracket_id=bracket_id)
        self.rungs = validated.rungs
        if any(self.rungs[i] * eta != self.rungs[i+1] for i in range(len(rungs)-1)):
            raise ValueError("Finite Hyperband requires geometric rungs")
        self.bracket_id = bracket_id
        if type(default_at_target) is not bool:
            raise ValueError("default_at_target must be boolean")
        self.default_at_target = default_at_target
        self.config = PriorBandConfig(self.rungs[0], self.rungs[-1], eta)
        self._brackets, self._trials, self._terminal, self._events = [], {}, {}, []

    @property
    def metric_identity(self):
        return identity({"rungs": self.rungs, "config": asdict(self.config), "id": self.bracket_id,
                         "tie_policy": "registration_order", "failures": "no_replacement",
                         "default_at_target": self.default_at_target})

    @property
    def next_start_rung(self):
        if self._brackets:
            last = self._brackets[-1]
            if len(last["roots"]) < last["widths"][0]:
                return last["start"]
        return len(self._brackets) % len(self.rungs)

    def register_trial(self, trial_id):
        if type(trial_id) is not str or not trial_id or trial_id in self._trials:
            raise ValueError("New unique root trial ID required")
        if self.default_at_target and not self._trials:
            self._trials[trial_id] = {"bracket": None, "rung": len(self.rungs)-1,
                                      "state": "active", "reports": {}}
            self._events.append({"action": "register", "trial_id": trial_id, "fidelity": self.rungs[-1]})
            return self.rungs[-1]
        start = self.next_start_rung
        if not self._brackets or len(self._brackets[-1]["roots"]) == self._brackets[-1]["widths"][0]:
            self._brackets.append({"start": start, "widths": bracket_widths(len(self.rungs), self.config.eta, start),
                                   "roots": [], "selected": {}})
        bracket = self._brackets[-1]
        bracket["roots"].append(trial_id)
        self._trials[trial_id] = {"bracket": len(self._brackets)-1, "rung": start,
                                  "state": "active", "reports": {}}
        self._events.append({"action": "register", "trial_id": trial_id, "fidelity": self.rungs[start]})
        return self.rungs[start]

    def report(self, trial_id, fidelity, value, *, is_progress=False):
        if trial_id not in self._trials:
            raise ValueError("Register each root before reporting")
        if (type(fidelity) not in (int, float) or not math.isfinite(fidelity) or fidelity <= 0
                or type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("Reports require positive finite fidelity and finite loss")
        trial = self._trials[trial_id]
        if trial_id in self._terminal:
            return "stop"
        target = self.rungs[trial["rung"]]
        if fidelity > target:
            raise ValueError("Report exceeds its assigned fidelity")
        if fidelity < target:
            return "continue"
        key = str(trial["rung"])
        if key in trial["reports"]:
            if trial["reports"][key] != value:
                raise ValueError("Conflicting duplicate report")
            return "stop" if target == self.rungs[-1] else "pause"
        trial["reports"][key] = value
        trial["state"] = "endpoint" if target == self.rungs[-1] else "paused"
        self._events.append({"action": "report", "trial_id": trial_id, "fidelity": fidelity, "value": value})
        return "stop" if target == self.rungs[-1] else "pause"

    def finish(self, trial_id, status):
        if trial_id not in self._trials or status not in {"completed", "failed", "pruned", "cancelled"}:
            raise ValueError("Known root and terminal status required")
        if trial_id in self._terminal:
            if self._terminal[trial_id] != status:
                raise ValueError("Conflicting terminal status")
            return
        trial = self._trials[trial_id]
        if status == "completed" and trial["state"] != "endpoint":
            raise ValueError("Completion requires a full-fidelity report")
        self._terminal[trial_id], trial["state"] = status, "terminal"
        self._events.append({"action": "finish", "trial_id": trial_id, "status": status})

    def promote(self):
        # Oldest bracket first; no decision until all assigned rung evaluations
        # have either reported or failed. The whole decision is frozen once.
        for bracket in self._brackets:
            if len(bracket["roots"]) < bracket["widths"][0]:
                continue
            members = bracket["roots"]
            for rung in range(bracket["start"], len(self.rungs)-1):
                key = str(rung)
                if key in bracket["selected"]:
                    members = bracket["selected"][key]
                    continue
                if any(key not in self._trials[tid]["reports"] and tid not in self._terminal for tid in members):
                    break
                eligible = [tid for tid in members if tid not in self._terminal]
                quota = bracket["widths"][rung-bracket["start"]+1]
                winners = sorted(eligible, key=lambda tid: self._trials[tid]["reports"][key])[:quota]
                bracket["selected"][key] = winners
                for tid in members:
                    if tid not in winners and tid not in self._terminal:
                        self._terminal[tid], self._trials[tid]["state"] = "pruned", "terminal"
                for tid in winners:
                    self._trials[tid].update(rung=rung+1, state="active")
                result = [(tid, self.rungs[rung+1]) for tid in winners]
                self._events.append({"action": "promote", "promotions": [list(row) for row in result]})
                return result
        return []

    def state_dict(self):
        return deepcopy({"schema": "priorband-scheduler-state-v2", "identity": self.metric_identity,
                         "config": asdict(self.config), "rungs": self.rungs, "brackets": self._brackets,
                         "trials": self._trials, "terminal": self._terminal, "events": self._events})

    def validate_study_snapshot(self, state):
        roots = {tid: trial for tid, trial in state["trials"].items()
                 if state["roots"][tid] == tid}
        if set(roots) != set(self._trials):
            raise ValueError("Scheduler roots differ from Study")
        for root, trial in roots.items():
            row = self._trials[root]
            start = (self._brackets[row["bracket"]]["start"] if row["bracket"] is not None
                     else len(self.rungs)-1)
            if trial["fidelity"] != self.rungs[start]:
                raise ValueError("Root fidelity differs from its Hyperband bracket")
            assigned = [t["fidelity"] for tid, t in state["trials"].items()
                        if state["roots"][tid] == root]
            if max(assigned) != self.rungs[row["rung"]]:
                raise ValueError("Promoted fidelity differs from scheduler state")
            for rung, value in row["reports"].items():
                fidelity = self.rungs[int(rung)]
                matches = [tid for tid, t in state["trials"].items()
                           if state["roots"][tid] == root and t["fidelity"] == fidelity]
                if len(matches) != 1:
                    raise ValueError("Scheduler report has no unique evaluation")
                tid = matches[0]
                result = state["results"].get(tid)
                progress = state.get("report_cache", {}).get(tid, {})
                raw = next((entry["value"] for step, entry in progress.items()
                            if float(step) == fidelity), None)
                if raw is None and result and result["status"] in {"completed", "paused"}:
                    raw = result["objective_value"]
                expected = (-raw if state["maximize"] else raw) if raw is not None else None
                if expected != value:
                    raise ValueError("Scheduler report differs from evaluation ledger")

    def load_state_dict(self, state):
        if (type(state) is not dict or set(state) != set(self.state_dict())
                or state.get("schema") != "priorband-scheduler-state-v2"
                or state.get("identity") != self.metric_identity or type(state.get("events")) is not list):
            raise ValueError("PriorBand scheduler identity or shape differs")
        restored = type(self)(rungs=self.rungs, eta=self.config.eta, bracket_id=self.bracket_id,
                              default_at_target=self.default_at_target)
        try:
            for event in state["events"]:
                action = event["action"]
                if action == "register":
                    if restored.register_trial(event["trial_id"]) != event["fidelity"]:
                        raise ValueError("Bracket assignment replay differs")
                elif action == "report":
                    restored.report(event["trial_id"], event["fidelity"], event["value"])
                elif action == "finish":
                    restored.finish(event["trial_id"], event["status"])
                elif action == "promote":
                    if [list(row) for row in restored.promote()] != event["promotions"]:
                        raise ValueError("Promotion replay differs")
                else:
                    raise ValueError("Unknown scheduler event")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Malformed scheduler event") from exc
        if restored.state_dict() != state:
            raise ValueError("Scheduler state differs from replay")
        self.__dict__.update(restored.__dict__)
