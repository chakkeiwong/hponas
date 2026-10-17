"""Finite accounting and policy arithmetic from the pinned NePS PriorBand.

Reference: automl/neps 3f7475b5afaaacdace56f25357ddfbf0e5616157.
Physical work and the reference's latest-fidelity activation proxy are distinct.
The full runtime and continuous mutation distributions are not implemented here.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math


def finite(value, name, minimum=0):
    if (type(value) not in (int, float) or not math.isfinite(value) or value < minimum):
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return value


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def bracket_widths(count, eta, start=0):
    """Pinned NePS floor rule, distinct from the paper's ceiling variant."""
    if type(eta) is not int or eta < 2 or type(count) is not int or count < 1:
        raise ValueError("Positive rung count and integral eta >=2 are required")
    if type(start) is not int or not 0 <= start < count:
        raise ValueError("Invalid bracket start index")
    scale = count // (count - start)
    return [scale * eta ** (count - i - 1) for i in range(start, count)]


class PriorBand:
    """Replayable finite policy ledger; observations name cumulative fidelities.

    Sampling APIs take unambiguous zero-based rung *indices*. Incumbents use
    the latest observation for each root (including low-fidelity roots).
    Promotion makes a root pending until its new evaluation completes.
    """

    def __init__(self, *, rungs, eta, bracket_id="priorband-finite-v3"):
        bracket_widths(len(rungs), eta)
        if (type(rungs) is not list or not rungs
                or any(type(r) not in (int, float) or not math.isfinite(r) or r <= 0 for r in rungs)
                or rungs != sorted(set(rungs))):
            raise ValueError("Strictly increasing positive finite rungs required")
        if type(bracket_id) is not str or not bracket_id:
            raise ValueError("Nonempty bracket identity required")
        self.rungs = [float(r) for r in rungs]
        self.eta, self.bracket_id = eta, bracket_id
        self.config_map = bracket_widths(len(rungs), eta)
        self._rows, self._latest, self._events = {}, {}, []

    @property
    def identity(self):
        return identity({"schema": "priorband-policy-v3", "rungs": self.rungs,
                         "eta": self.eta, "bracket_id": self.bracket_id,
                         "tie_policy": "first-observed", "invalid_scores": "refuse"})

    @property
    def bracket_cost(self):
        previous, total = Fraction(0), Fraction(0)
        for width, rung in zip(self.config_map, self.rungs):
            current = Fraction(rung)
            total += width * (current - previous)
            previous = current
        return total

    def begin(self, trial_id, *, root, rung):
        if (type(trial_id) is not str or not trial_id or trial_id in self._rows
                or type(root) is not str or not root or type(rung) not in (int, float)
                or rung not in self.rungs):
            raise ValueError("Unique evaluation, root and declared fidelity required")
        previous = self._rows.get(self._latest.get(root))
        if previous and (previous["status"] != "completed" or previous["rung"] >= rung):
            raise ValueError("A promotion requires a completed lower-fidelity observation")
        self._rows[trial_id] = {"root": root, "rung": float(rung), "value": None,
                                "work": 0, "status": "pending"}
        self._latest[root] = trial_id
        self._events.append({"action": "begin", "trial_id": trial_id, "root": root, "rung": float(rung)})

    def observe(self, trial_id, *, rung, value, work, status="completed", root=None):
        if status not in {"completed", "failed"}:
            raise ValueError("Observation must be completed or failed")
        finite(work, "work")
        if status == "completed":
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Completed values must be finite")
        elif value is not None:
            raise ValueError("A failed observation has no objective value")
        existing = self._rows.get(trial_id)
        root = (existing["root"] if existing else trial_id) if root is None else root
        if existing:
            if existing["status"] != "pending" or existing["root"] != root or existing["rung"] != rung:
                raise ValueError("Conflicting or repeated observation")
        else:
            self.begin(trial_id, root=root, rung=rung)
        self._rows[trial_id].update(value=value, work=work, status=status)
        self._events.append({"action": "observe", "trial_id": trial_id, "rung": float(rung),
                             "value": value, "work": work, "status": status, "root": root})

    def incumbent(self):
        finite_rows = [self._rows[eid] for eid in self._latest.values()
                       if self._rows[eid]["status"] == "completed"]
        return min(finite_rows, key=lambda row: row["value"])["root"] if finite_rows else None

    def resources(self):
        """All measured work, including failed evaluations and repeated prefixes."""
        return sum(row["work"] for row in self._rows.values())

    def reference_resources(self):
        """Latest completed cumulative fidelity per root; this is not real cost."""
        return sum(Fraction(self._rows[eid]["rung"]) for eid in self._latest.values()
                   if self._rows[eid]["status"] == "completed")

    def can_activate(self):
        populated = any(row["rung"] == self.rungs[-1] and row["status"] == "completed"
                        for row in self._rows.values())
        return populated and self.reference_resources() >= self.bracket_cost

    def prior_to_incumbent_ratio(self, *, style="constant", scores=None):
        if style == "constant":
            return Fraction(self.eta, self.eta + 1), Fraction(1, self.eta + 1)
        if style != "dynamic":
            raise ValueError("Only constant and dynamic ratios are supported")
        for rung in reversed(self.rungs):
            rows = [row for row in self._rows.values()
                    if row["rung"] == rung and row["status"] == "completed"]
            if len(rows) < self.eta:
                continue
            top = sorted(rows, key=lambda row: row["value"])[:max(len(rows)//self.eta, self.eta)]
            if type(scores) is not dict or any(row["root"] not in scores for row in top):
                raise ValueError("Dynamic weights require scores for every selected root")
            totals = [Fraction(0), Fraction(0)]
            for i, row in enumerate(top):
                pair = scores[row["root"]]
                if type(pair) not in (tuple, list) or len(pair) != 2:
                    raise ValueError("Expected paired prior/incumbent scores")
                for j, value in enumerate(pair):
                    if type(value) not in (int, Fraction) or value < 0:
                        raise ValueError("Exact nonnegative rational scores required")
                    totals[j] += (len(top)-i) * value
            if not sum(totals):
                raise ValueError("Zero dynamic score sum has no defined reference ratio")
            return tuple(value / sum(totals) for value in totals)
        return self.prior_to_incumbent_ratio(style="constant")

    def sampling_weights(self, rung_index, *, prior_weight_type="geometric",
                         inc_style="constant", scores=None):
        if type(rung_index) is not int or not 0 <= rung_index < len(self.rungs):
            raise ValueError("Sampling requires a zero-based rung index")
        if prior_weight_type == "geometric":
            weight = Fraction(self.eta ** rung_index)
        elif prior_weight_type == "linear":
            weight = 1 + Fraction(rung_index, max(1, len(self.rungs)-1)) * (self.eta-1)
        elif prior_weight_type == "50-50":
            weight = Fraction(1)
        else:
            raise ValueError("Unknown prior weight policy")
        prior, inc = self.prior_to_incumbent_ratio(style=inc_style, scores=scores)
        if not self.can_activate():
            prior, inc = Fraction(1), Fraction(0)
        return {"random": 1/(1+weight), "prior": weight*prior/(1+weight), "inc": weight*inc/(1+weight)}

    def state_dict(self):
        return deepcopy({"schema": "priorband-policy-state-v3", "identity": self.identity,
                         "rows": self._rows, "latest": self._latest, "events": self._events})

    def load_state_dict(self, state):
        if (type(state) is not dict or set(state) != set(self.state_dict())
                or state.get("schema") != "priorband-policy-state-v3" or state.get("identity") != self.identity
                or type(state.get("events")) is not list):
            raise ValueError("PriorBand checkpoint identity or shape differs")
        restored = type(self)(rungs=self.rungs, eta=self.eta, bracket_id=self.bracket_id)
        try:
            for event in state["events"]:
                args = {k: deepcopy(v) for k, v in event.items() if k != "action"}
                if event["action"] == "begin":
                    restored.begin(**args)
                elif event["action"] == "observe":
                    restored.observe(**args)
                else:
                    raise ValueError("Unknown policy event")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Malformed PriorBand event") from exc
        if restored.state_dict() != state:
            raise ValueError("PriorBand state differs from event replay")
        self.__dict__.update(restored.__dict__)
