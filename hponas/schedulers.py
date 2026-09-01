"""
Schedulers: allocate budget across running trials.

Survey reference: Ch 15 sec:scheduler-interface, Ch 5 (multifidelity).

R1 spike: ASHA with async promotion, no median stopping yet.
Tier 0: adds median rule, PASHA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

SchedulerDecision = Literal["continue", "stop", "pause"]


@dataclass
class ASHAConfig:
    """
    ASHA hyperparameters (Ch 5).

    η: reduction factor (default 3)
    r_min: minimum fidelity budget per trial
    r_max: maximum fidelity (full run)
    median_stopping: enable median stopping rule (Ch 5)
    """
    eta: int = 3
    r_min: float = 1.0
    r_max: float = 27.0
    median_stopping: bool = False


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

        # Track trials: trial_id -> (current_rung_idx, current_fidelity, best_value_so_far, status)
        self._trial_state: dict[str, tuple[int, float, Optional[float], str]] = {}

        # Track rung populations: rung_idx -> dict of trial_id -> value (unique trials per rung)
        self._rung_populations: dict[int, dict[str, float]] = {
            i: {} for i in range(len(self.rungs))
        }

        # Median stopping: track all observations at each fidelity for running median
        # fidelity -> list of values
        self._fidelity_history: dict[float, list[float]] = {}

    def report(
        self, trial_id: str, fidelity: float, value: float
    ) -> SchedulerDecision:
        """
        Called as metrics stream in (Ch 15 contract).

        Returns: continue (keep training), stop (kill trial), pause (wait for promotion).
        Survey: ASHA and median rule live entirely behind this verb.

        Tier 0: adds median stopping rule (Ch 5 roadmap-03, ch05-01).
        Median rule: stop if value > median of all values seen at this fidelity.
        """
        # Determine which rung this fidelity corresponds to
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            # Not at a rung boundary
            # Apply median stopping if enabled
            if self.config.median_stopping:
                if fidelity not in self._fidelity_history:
                    self._fidelity_history[fidelity] = []
                self._fidelity_history[fidelity].append(value)

                # Stop if worse than median (minimize objective)
                history = self._fidelity_history[fidelity]
                if len(history) >= 5:  # Need at least 5 observations for reliable median
                    median = np.median(history)
                    if value > median:
                        return "stop"

            return "continue"

        # At a rung boundary
        # Update trial state
        if trial_id not in self._trial_state:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, "active")
        else:
            prev_rung, _, prev_val, status = self._trial_state[trial_id]
            best_val = value if prev_val is None else min(value, prev_val)  # assume minimize
            self._trial_state[trial_id] = (rung_idx, fidelity, best_val, "active")

        # Record at rung (unique trials only, keep best value)
        self._rung_populations[rung_idx][trial_id] = value

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, "stopped")
            return "stop"

        # Check ranking at this rung
        pop = sorted(self._rung_populations[rung_idx].items(), key=lambda x: x[1])  # sort by value
        n_pop = len(pop)
        n_promote = max(1, math.ceil(n_pop / self.config.eta))

        # Is this trial in the top n_promote?
        trial_rank = next((i for i, (tid, _) in enumerate(pop) if tid == trial_id), None)
        if trial_rank is None or trial_rank >= n_promote:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, "stopped")
            return "stop"
        else:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, "paused")
            return "pause"  # wait for promotion to next rung

    def promote(self) -> list[tuple[str, float]]:
        """
        Return paused trials to resume, with their next fidelity budget (Ch 15 contract).

        Survey: asynchronous promotion against results-so-far is the ASHA rule.
        """
        to_promote: list[tuple[str, float]] = []
        for trial_id, (rung_idx, fidelity, best_val, status) in list(self._trial_state.items()):
            # Only promote trials that are paused
            if status == "paused" and rung_idx < len(self.rungs) - 1:
                next_rung = rung_idx + 1
                next_fidelity = self.rungs[next_rung]
                to_promote.append((trial_id, next_fidelity))

                # Update state to reflect promotion
                self._trial_state[trial_id] = (next_rung, next_fidelity, best_val, "active")

        return to_promote

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index (or None if not at a boundary)."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:  # floating-point tolerance
                return i
        return None


@dataclass
class PASHAConfig:
    """
    PASHA (Promotion-based ASHA) hyperparameters (Ch 5 roadmap-03, ch05-05).

    Survey verdict: include, T0, ~4 engineer-days.
    Contract: PASHA is ASHA with promotion budget pooling.

    η: reduction factor
    r_min: minimum fidelity
    r_max: maximum fidelity
    promotion_budget: total fidelity budget available for promotions
    """
    eta: int = 3
    r_min: float = 1.0
    r_max: float = 27.0
    promotion_budget: float = 100.0


class PASHAScheduler:
    """
    PASHA (Promotion-based ASHA) scheduler (Ch 5 roadmap-03, ch05-05).

    Survey verdict: include, T0, ~4 engineer-days.
    Contract: ASHA with shared promotion budget instead of fixed rung counts.
    Validation: V02 (async correctness).

    Difference from ASHA: promotions are budget-constrained rather than
    population-fraction based. More efficient when fidelity costs vary.
    """

    def __init__(self, config: PASHAConfig):
        self.config = config

        # Compute rung budgets
        self.rungs: list[float] = []
        r = config.r_min
        while r <= config.r_max:
            self.rungs.append(r)
            r *= config.eta
        if self.rungs[-1] < config.r_max:
            self.rungs.append(config.r_max)

        # Track trials: trial_id -> (current_rung_idx, current_fidelity, best_value_so_far, budget_spent, status)
        self._trial_state: dict[str, tuple[int, float, Optional[float], float, str]] = {}

        # Track rung populations (unique trials per rung)
        self._rung_populations: dict[int, dict[str, float]] = {
            i: {} for i in range(len(self.rungs))
        }

        # Track total budget spent on promotions
        self._budget_spent = 0.0

    def report(
        self, trial_id: str, fidelity: float, value: float
    ) -> SchedulerDecision:
        """
        Report a trial observation.

        PASHA: same stopping logic as ASHA, but promotion is budget-gated.
        """
        # Determine which rung this fidelity corresponds to
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            return "continue"

        # Update trial state
        if trial_id not in self._trial_state:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, 0.0, "active")
        else:
            prev_rung, _, prev_val, budget, status = self._trial_state[trial_id]
            best_val = value if prev_val is None else min(value, prev_val)
            self._trial_state[trial_id] = (rung_idx, fidelity, best_val, budget, "active")

        # Record at rung
        self._rung_populations[rung_idx][trial_id] = value

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "stopped")
            return "stop"

        # Check ranking at this rung
        pop = sorted(self._rung_populations[rung_idx].items(), key=lambda x: x[1])
        n_pop = len(pop)
        n_promote = max(1, math.ceil(n_pop / self.config.eta))

        # Is this trial in the top n_promote?
        trial_rank = next((i for i, (tid, _) in enumerate(pop) if tid == trial_id), None)
        if trial_rank is None or trial_rank >= n_promote:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "stopped")
            return "stop"

        # PASHA: check if we have budget for promotion
        next_rung_budget = self.rungs[rung_idx + 1] - self.rungs[rung_idx]
        if self._budget_spent + next_rung_budget > self.config.promotion_budget:
            # Budget exhausted, stop instead of pausing
            self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "stopped")
            return "stop"

        self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "paused")
        return "pause"

    def promote(self) -> list[tuple[str, float]]:
        """
        Promote paused trials if budget allows.

        PASHA: track budget consumption per promotion.
        """
        to_promote: list[tuple[str, float]] = []
        for trial_id, (rung_idx, fidelity, best_val, budget, status) in list(self._trial_state.items()):
            # Only promote paused trials
            if status == "paused" and rung_idx < len(self.rungs) - 1:
                next_rung = rung_idx + 1
                next_fidelity = self.rungs[next_rung]

                # Calculate budget for this promotion
                promotion_cost = next_fidelity - fidelity

                # Check budget
                if self._budget_spent + promotion_cost <= self.config.promotion_budget:
                    to_promote.append((trial_id, next_fidelity))
                    self._budget_spent += promotion_cost

                    # Update state
                    new_budget = budget + promotion_cost
                    self._trial_state[trial_id] = (next_rung, next_fidelity, best_val, new_budget, "active")

        return to_promote

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:
                return i
        return None
