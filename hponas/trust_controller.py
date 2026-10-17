"""Replayable q=1 trust-region controller and primary-paper box geometry.

This is a controller component, not a complete optimizer. Mixed geometry is
validated by the searcher's declared typed-space policy. Raw improvement moves
the center; the configured relative margin controls expansion counters only.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math


def positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(label + " must be a positive integer")
    return value


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite real number")
    return float(value)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Options:
    dimension: int
    initial_length: float
    minimum_length: float
    maximum_length: float
    success_tolerance: int
    failure_tolerance: int
    relative_improvement: float = 0.0
    geometry: str = "continuous"

    def __post_init__(self):
        for name in ("dimension", "success_tolerance", "failure_tolerance"):
            positive_int(getattr(self, name), name)
        for name in ("initial_length", "minimum_length", "maximum_length"):
            finite(getattr(self, name), name)
        if not 0 < self.minimum_length <= self.initial_length <= self.maximum_length <= 2:
            raise ValueError("Lengths must satisfy 0 < minimum <= initial <= maximum <= 2")
        finite(self.relative_improvement, "relative improvement")
        if self.relative_improvement < 0 or self.geometry not in {"continuous", "typed_product_v1"}:
            raise ValueError("Unsupported improvement margin or geometry")


class Controller:
    def __init__(self, options):
        if not isinstance(options, Options):
            raise ValueError("Controller requires explicit immutable options")
        self.options = options
        self._status = "needs_initialization"
        self._generation = -1
        self._best = None
        self._center = None
        self._length = options.initial_length
        self._successes = self._failures = 0
        self._pending = None
        self._seen = set()
        self._journal = []

    def _identity(self, trial_id):
        if not isinstance(trial_id, str) or not trial_id or trial_id in self._seen:
            raise ValueError("Trial identity is missing or previously consumed")
        return trial_id

    def _point(self, point):
        if not isinstance(point, (list, tuple)) or len(point) != self.options.dimension:
            raise ValueError("Point dimension differs")
        point = [finite(v, "coordinate") for v in point]
        if any(v < 0 or v > 1 for v in point):
            raise ValueError("Point lies outside the unit cube")
        return point

    def initialize(self, trial_id, point, value):
        if self._status not in ("needs_initialization", "needs_restart") or self._pending is not None:
            raise ValueError("Initialization requires a new or retired local region")
        ident = self._identity(trial_id)
        point = self._point(point)
        value = finite(value, "initial objective")
        self._generation += 1
        self._center, self._best = point, value
        self._length = self.options.initial_length
        self._successes = self._failures = 0
        self._status = "active"
        self._seen.add(ident)
        self._journal.append({"action": "initialize", "trial_id": ident, "point": point.copy(), "value": value})

    def bounds(self, lengthscales):
        if self._status != "active":
            raise ValueError("A retired or uninitialized region has no proposal bounds")
        if not isinstance(lengthscales, (list, tuple)) or len(lengthscales) != self.options.dimension:
            raise ValueError("Lengthscale dimension differs")
        scales = [finite(v, "lengthscale") for v in lengthscales]
        if any(v <= 0 for v in scales):
            raise ValueError("Lengthscales must be positive")
        logs = [math.log(v) for v in scales]
        mean_log = math.fsum(logs) / len(logs)
        sides = []
        for value in logs:
            log_side = math.log(self._length) + value - mean_log
            if abs(log_side) > 700:
                raise ValueError("Lengthscale anisotropy exceeds the numeric domain")
            sides.append(math.exp(log_side))
        return {"lower": [max(0., c-s/2) for c, s in zip(self._center, sides)],
                "upper": [min(1., c+s/2) for c, s in zip(self._center, sides)], "unclipped_sides": sides}

    def propose(self, trial_id, point, lengthscales):
        if self._status != "active" or self._pending is not None:
            raise ValueError("One active region permits one owned pending proposal")
        ident = self._identity(trial_id)
        point = self._point(point)
        box = self.bounds(lengthscales)
        if (self.options.geometry == "continuous"
                and any(v < lo or v > hi for v, lo, hi in zip(point, box["lower"], box["upper"]))):
            raise ValueError("Proposal lies outside the current trust region")
        self._pending = {"trial_id": ident, "point": point.copy(), "generation": self._generation}
        self._seen.add(ident)
        self._journal.append({"action": "propose", "trial_id": ident, "point": point.copy(),
                              "lengthscales": [float(v) for v in lengthscales]})

    def observe(self, trial_id, value):
        if self._status != "active" or self._pending is None or self._pending["trial_id"] != trial_id:
            raise ValueError("Observation has no matching owned pending trial")
        value = finite(value, "objective")
        success = value < self._best - self.options.relative_improvement * abs(self._best)
        if value < self._best:
            self._center, self._best = self._pending["point"].copy(), value
        self._complete(success)
        self._journal.append({"action": "observe", "trial_id": trial_id, "value": value})

    def fail(self, trial_id):
        """Count failed work without inventing a finite objective observation."""
        if self._status != "active" or self._pending is None or self._pending["trial_id"] != trial_id:
            raise ValueError("Failure has no matching owned pending trial")
        self._complete(False)
        self._journal.append({"action": "fail", "trial_id": trial_id})

    def _complete(self, success):
        if success:
            self._successes += 1
            self._failures = 0
        else:
            self._failures += 1
            self._successes = 0
        if self._successes == self.options.success_tolerance:
            self._length = min(self.options.maximum_length, 2 * self._length)
            self._successes = self._failures = 0
        elif self._failures == self.options.failure_tolerance:
            self._length /= 2
            self._successes = self._failures = 0
        if self._length < self.options.minimum_length:
            self._status = "needs_restart"
        self._pending = None

    def retire(self, reason):
        """Retire an empty typed neighborhood without fabricating failures."""
        if self._status != 'active' or self._pending is not None or reason != 'empty_typed_region':
            raise ValueError('Only an active, idle, empty typed region may retire')
        self._status = 'needs_restart'
        self._journal.append({'action': 'retire', 'reason': reason})

    def snapshot(self):
        return {"status": self._status, "generation": self._generation, "best": self._best,
                "center": deepcopy(self._center), "length": self._length, "successes": self._successes,
                "failures": self._failures, "pending": deepcopy(self._pending)}

    def state_dict(self):
        payload = {"schema": "q1_trust_controller_v2", "options": asdict(self.options),
                   "journal": deepcopy(self._journal), "snapshot": self.snapshot()}
        return {"payload": payload, "sha256": digest(payload)}

    @classmethod
    def from_state(cls, state, expected_options):
        if not isinstance(state, dict) or set(state) != {"payload", "sha256"}:
            raise ValueError("Malformed controller checkpoint")
        payload = deepcopy(state["payload"])
        if (not isinstance(payload, dict) or set(payload) != {"schema", "options", "journal", "snapshot"}
                or payload["schema"] != "q1_trust_controller_v2"
                or digest(payload) != state["sha256"] or payload["options"] != asdict(expected_options)
                or not isinstance(payload["journal"], list) or len(payload["journal"]) > 100000):
            raise ValueError("Changed options, content or unsupported checkpoint")
        fresh = cls(expected_options)
        for row in payload["journal"]:
            if not isinstance(row, dict) or "action" not in row:
                raise ValueError("Malformed controller journal")
            action = row["action"]
            fields = {"initialize": {"action", "trial_id", "point", "value"},
                      "propose": {"action", "trial_id", "point", "lengthscales"},
                      "observe": {"action", "trial_id", "value"},
                      "fail": {"action", "trial_id"},
                      "retire": {"action", "reason"}}
            if action not in fields or set(row) != fields[action]:
                raise ValueError("Unknown action or fields in controller journal")
            getattr(fresh, action)(**{k: v for k, v in row.items() if k != "action"})
        if fresh.snapshot() != payload["snapshot"]:
            raise ValueError("Snapshot differs from independently replayed inputs")
        return fresh
