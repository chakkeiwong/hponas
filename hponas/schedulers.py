"""
Schedulers: allocate budget across running trials.

Survey reference: Ch 15 sec:scheduler-interface, Ch 5 (multifidelity).

R1 spike: ASHA with async promotion, no median stopping yet.
Tier 0: adds median rule, PASHA option.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

SchedulerDecision = Literal["continue", "stop", "pause"]


@dataclass
class ASHAConfig:
    """
    ASHA hyperparameters (Ch 5).

    η: reduction factor (default 3)
    r_min: minimum fidelity budget per trial
    r_max: maximum fidelity (full run)
    """
    eta: int = 3
    r_min: float = 1.0
    r_max: float = 27.0


class ASHAScheduler:
    """
    Asynchronous Successive Halving (ASHA) scheduler (Ch 5 roadmap-03, ch05-01).

    Survey verdict: include, T0, days.
    Contract: scheduler impl: asha.
    Validation: V02 (async correctness), V06 (nearly-free early stopping).

    Spike: async promotion, rung bookkeeping, no median stopping yet.
    Tier 0: add median rule (~2d).
    """

    def __init__(self, config: ASHAConfig):
        self.config = config

        # Compute rung budgets: [r_min, r_min*η, r_min*η^2, ..., r_max]
        self.rungs: list[float] = []
        r = config.r_min
        while r <= config.r_max:
            self.rungs.append(r)
            r *= config.eta
        if self.rungs[-1] < config.r_max:
            self.rungs.append(config.r_max)

        # Track trials: trial_id -> (current_rung_idx, current_fidelity, best_value_so_far)
        self._trial_state: dict[str, tuple[int, float, Optional[float]]] = {}

        # Track rung populations: rung_idx -> list of (trial_id, value_at_rung)
        self._rung_populations: dict[int, list[tuple[str, float]]] = {
            i: [] for i in range(len(self.rungs))
        }

    def report(
        self, trial_id: str, fidelity: float, value: float
    ) -> SchedulerDecision:
        """
        Called as metrics stream in (Ch 15 contract).

        Returns: continue (keep training), stop (kill trial), pause (wait for promotion).
        Survey: ASHA and median rule live entirely behind this verb.
        """
        # Determine which rung this fidelity corresponds to
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            # Not at a rung boundary, continue
            return "continue"

        # Update trial state
        if trial_id not in self._trial_state:
            self._trial_state[trial_id] = (rung_idx, fidelity, value)
        else:
            prev_rung, _, prev_val = self._trial_state[trial_id]
            best_val = value if prev_val is None else min(value, prev_val)  # assume minimize
            self._trial_state[trial_id] = (rung_idx, fidelity, best_val)

        # Record at rung
        self._rung_populations[rung_idx].append((trial_id, value))

        # Decide: promote if trial is in the top 1/η of this rung
        if rung_idx == len(self.rungs) - 1:
            # At final rung, stop
            return "stop"

        # Check ranking at this rung
        pop = sorted(self._rung_populations[rung_idx], key=lambda x: x[1])  # sort by value
        n_pop = len(pop)
        n_promote = max(1, math.ceil(n_pop / self.config.eta))

        # Is this trial in the top n_promote?
        trial_rank = next((i for i, (tid, _) in enumerate(pop) if tid == trial_id), None)
        if trial_rank is None or trial_rank >= n_promote:
            return "stop"
        else:
            return "pause"  # wait for promotion to next rung

    def promote(self) -> list[tuple[str, float]]:
        """
        Return paused trials to resume, with their next fidelity budget (Ch 15 contract).

        Survey: asynchronous promotion against results-so-far is the ASHA rule.
        """
        to_promote: list[tuple[str, float]] = []
        for trial_id, (rung_idx, fidelity, _) in self._trial_state.items():
            if rung_idx < len(self.rungs) - 1:
                next_rung = rung_idx + 1
                next_fidelity = self.rungs[next_rung]
                if next_fidelity > fidelity:
                    to_promote.append((trial_id, next_fidelity))
                    # Update state to reflect promotion
                    self._trial_state[trial_id] = (next_rung, next_fidelity, self._trial_state[trial_id][2])
        return to_promote

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index (or None if not at a boundary)."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:  # floating-point tolerance
                return i
        return None
