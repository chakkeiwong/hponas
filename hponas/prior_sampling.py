"""Exact finite guarded priors and resumable rejection over declared cells."""
from fractions import Fraction
import hashlib
import json
import math
import random


def _rational(value):
    if type(value) not in (int, Fraction):
        raise ValueError("Finite exact rational inputs are required")
    return Fraction(value)


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid nonnegative integer")
    return value


def _json_lists(value):
    if isinstance(value, tuple):
        return [_json_lists(item) for item in value]
    return value


class FiniteGuardedPrior:
    """Draw from ``(1-alpha)B + alpha*wB/Z`` over finite declared cells.

    The prior branch is selected once. A bounded call can return ``None`` while
    preserving that branch and the exact Python RNG state. Generic callables and
    uncertified continuous envelopes are rejected by this class's finite scope.
    """

    def __init__(self, base, weights, alpha, seed, *, cell_identity="finite-cells-v1"):
        self.base = tuple(_rational(v) for v in base)
        self.weights = tuple(_rational(v) for v in weights)
        self.alpha = _rational(alpha)
        if (not self.base or len(self.base) != len(self.weights) or any(v <= 0 for v in self.base)
                or any(v < 0 for v in self.weights) or not 0 <= self.alpha < 1):
            raise ValueError("Finite support, nonnegative weights and alpha in [0,1) required")
        if type(cell_identity) is not str or not cell_identity:
            raise ValueError("Ordered cell identity is required")
        _integer(seed)
        if seed >= 2**64:
            raise ValueError("Seed outside the supported integer range")
        total = sum(self.base)
        self.base = tuple(v / total for v in self.base)
        denominator = math.lcm(*(v.denominator for v in self.base))
        self._base_masses = tuple(int(v * denominator) for v in self.base)
        self._base_total = sum(self._base_masses)
        self.envelope = max(self.weights)
        self._effective_alpha = self.alpha if self.envelope else Fraction(0)
        self._can_reject = bool(self._effective_alpha and any(v < self.envelope for v in self.weights))
        self.law = {"cell_identity": cell_identity, "base": list(map(str, self.base)),
                    "weights": list(map(str, self.weights)), "alpha": str(self.alpha),
                    "envelope": str(self.envelope), "algorithm": "guard-once-resumable-rejection-v1",
                    "rng": "python-random-state-v3"}
        self.law_sha256 = hashlib.sha256(json.dumps(self.law, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self._rng = random.Random(seed)
        self.pending_prior = False
        self.proposal_count = self.started_draws = self.completed_draws = 0

    def _bernoulli(self, probability):
        if probability == 0: return False
        if probability == 1: return True
        return self._rng.randrange(probability.denominator) < probability.numerator

    def _base_draw(self):
        value = self._rng.randrange(self._base_total)
        for index, mass in enumerate(self._base_masses):
            if value < mass: return index
            value -= mass
        raise RuntimeError("Finite base draw escaped its support")

    def advance(self, max_proposals):
        _integer(max_proposals, 1)
        if not self.pending_prior:
            self.started_draws += 1
            self.pending_prior = self._bernoulli(self._effective_alpha)
            if not self.pending_prior:
                self.proposal_count += 1; self.completed_draws += 1
                return self._base_draw()
        for _ in range(max_proposals):
            index = self._base_draw(); self.proposal_count += 1
            if self._bernoulli(self.weights[index] / self.envelope):
                self.pending_prior = False; self.completed_draws += 1
                return index
        return None

    def state_dict(self):
        return {"schema": "finite-guarded-rejection-state-v1", "law_sha256": self.law_sha256,
                "rng_state": _json_lists(self._rng.getstate()), "pending_prior": self.pending_prior,
                "proposal_count": self.proposal_count, "started_draws": self.started_draws,
                "completed_draws": self.completed_draws}

    def load_state_dict(self, state):
        if type(state) is not dict or set(state) != set(self.state_dict()):
            raise ValueError("Unexpected checkpoint shape")
        if state["schema"] != "finite-guarded-rejection-state-v1" or state["law_sha256"] != self.law_sha256 or type(state["pending_prior"]) is not bool:
            raise ValueError("Checkpoint law or pending state differs")
        pending, proposed = state["pending_prior"], _integer(state["proposal_count"])
        started, completed = _integer(state["started_draws"]), _integer(state["completed_draws"])
        if (started != completed + int(pending) or proposed < completed + int(pending)
                or (not started and proposed) or (not self._can_reject and (pending or proposed != completed))):
            raise ValueError("Checkpoint counters contradict pending state")
        raw = state["rng_state"]
        if (type(raw) is not list or len(raw) != 3 or type(raw[0]) is not int or raw[0] != 3
                or type(raw[1]) is not list or len(raw[1]) != 625
                or any(type(x) is not int or not 0 <= x < 2**32 for x in raw[1][:-1])
                or not any(raw[1][:-1]) or type(raw[1][-1]) is not int or not 0 <= raw[1][-1] <= 624
                or raw[2] is not None):
            raise ValueError("Unsupported or malformed generator state")
        rng = random.Random(0); rng.setstate((3, tuple(raw[1]), None))
        self._rng, self.pending_prior, self.proposal_count = rng, pending, proposed
        self.started_draws, self.completed_draws = started, completed


def guarded_probabilities(base, weights, alpha):
    """Exact normalized guarded masses for finite support."""
    base, weights, alpha = tuple(_rational(v) for v in base), tuple(_rational(v) for v in weights), _rational(alpha)
    if len(base) != len(weights) or not base or any(v <= 0 for v in base) or any(v < 0 for v in weights) or not 0 <= alpha < 1:
        raise ValueError("Invalid finite guarded law")
    base = tuple(v / sum(base) for v in base); normalizer = sum(b*w for b,w in zip(base, weights))
    if normalizer == 0: return base
    return tuple((1-alpha)*b + alpha*b*w/normalizer for b,w in zip(base, weights))
