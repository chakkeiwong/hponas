"""
Schedulers: allocate budget across running trials.

Survey reference: Ch 15 sec:scheduler-interface, Ch 5 (multifidelity).

R1 spike: ASHA with async promotion, no median stopping yet.
Tier 0: adds median rule, PASHA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal, Optional

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

        # Track rung populations: rung_idx -> list of (trial_id, value) tuples
        # Duplicates are allowed (same trial can report multiple times at same rung)
        self._rung_populations: dict[int, list[tuple[str, float]]] = {
            i: [] for i in range(len(self.rungs))
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

        # Record at rung (allow duplicates - same trial can report multiple times)
        self._rung_populations[rung_idx].append((trial_id, value))

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, "stopped")
            return "stop"

        # In async ASHA, we can't make stop/pause decisions at report time because
        # we don't know the final population. Mark everything as paused; promote()
        # will select the top k trials when called.
        self._trial_state[trial_id] = (rung_idx, fidelity, value, "paused")
        return "pause"

    def promote(self) -> list[tuple[str, float]]:
        """
        Return paused trials to resume, with their next fidelity budget (Ch 15 contract).

        Survey: asynchronous promotion against results-so-far is the ASHA rule.
        This method looks at the current rung populations and promotes the top 1/eta
        trials from each rung to the next rung.
        """
        to_promote: list[tuple[str, float]] = []

        # For each rung, decide which paused trials to promote
        for rung_idx in range(len(self.rungs) - 1):  # don't promote from final rung
            pop = self._rung_populations[rung_idx]
            if not pop:
                continue

            # Calculate how many to promote from this rung
            n_pop = len(pop)
            # Edge case: when n_pop <= eta, promote all to establish the pipeline
            if n_pop <= self.config.eta:
                n_promote = n_pop
            else:
                n_promote = max(1, math.ceil(n_pop / self.config.eta))

            # Sort by value (ascending = best first)
            sorted_pop = sorted(pop, key=lambda x: x[1])

            # Top n_promote trials get promoted, rest get stopped
            promoted_ids = {tid for tid, _ in sorted_pop[:n_promote]}

            # Update states and build promotion list
            for trial_id, (trial_rung, fidelity, best_val, status) in list(self._trial_state.items()):
                if trial_rung == rung_idx and status == "paused":
                    if trial_id in promoted_ids:
                        # Promote this trial
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        to_promote.append((trial_id, next_fidelity))
                        self._trial_state[trial_id] = (next_rung, next_fidelity, best_val, "active")
                    else:
                        # Stop this trial
                        self._trial_state[trial_id] = (trial_rung, fidelity, best_val, "stopped")

        return to_promote

    def state_dict(self) -> dict[str, Any]:
        """Serialize scheduler state for checkpointing."""
        import copy
        return {
            "config": {
                "eta": self.config.eta,
                "r_min": self.config.r_min,
                "r_max": self.config.r_max,
            },
            "rungs": copy.deepcopy(self.rungs),
            "trial_state": copy.deepcopy(self._trial_state),
            "rung_populations": copy.deepcopy(self._rung_populations),
            "fidelity_history": copy.deepcopy(self._fidelity_history),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore scheduler state from checkpoint."""
        self.rungs = state["rungs"]
        self._trial_state = state["trial_state"]
        self._rung_populations = state["rung_populations"]
        self._fidelity_history = state["fidelity_history"]

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

        # Track rung populations: rung_idx -> list of (trial_id, value) tuples
        self._rung_populations: dict[int, list[tuple[str, float]]] = {
            i: [] for i in range(len(self.rungs))
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
        self._rung_populations[rung_idx].append((trial_id, value))

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "stopped")
            return "stop"

        # In async PASHA, mark everything as paused; promote() will select based on
        # ranking and budget availability.
        self._trial_state[trial_id] = (rung_idx, fidelity, value, self._trial_state[trial_id][3], "paused")
        return "pause"

    def promote(self) -> list[tuple[str, float]]:
        """
        Promote paused trials if budget allows.

        PASHA: track budget consumption per promotion. Decides which paused trials
        to promote based on ranking within each rung and available budget.
        """
        to_promote: list[tuple[str, float]] = []

        # For each rung, decide which paused trials to promote
        for rung_idx in range(len(self.rungs) - 1):  # don't promote from final rung
            pop = self._rung_populations[rung_idx]
            if not pop:
                continue

            # Calculate how many to promote from this rung
            n_pop = len(pop)
            # Edge case: when n_pop <= eta, promote all to establish the pipeline
            if n_pop <= self.config.eta:
                n_promote = n_pop
            else:
                n_promote = max(1, math.ceil(n_pop / self.config.eta))

            # Sort by value (ascending = best first)
            sorted_pop = sorted(pop, key=lambda x: x[1])

            # Top n_promote trials are candidates for promotion
            promoted_ids = {tid for tid, _ in sorted_pop[:n_promote]}

            # Update states and build promotion list (budget-constrained)
            for trial_id, (trial_rung, fidelity, best_val, budget, status) in list(self._trial_state.items()):
                if trial_rung == rung_idx and status == "paused":
                    if trial_id in promoted_ids:
                        # Try to promote this trial if budget allows
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        promotion_cost = next_fidelity - fidelity

                        if self._budget_spent + promotion_cost <= self.config.promotion_budget:
                            to_promote.append((trial_id, next_fidelity))
                            self._budget_spent += promotion_cost
                            new_budget = budget + promotion_cost
                            self._trial_state[trial_id] = (next_rung, next_fidelity, best_val, new_budget, "active")
                        else:
                            # Budget exhausted, stop this trial
                            self._trial_state[trial_id] = (trial_rung, fidelity, best_val, budget, "stopped")
                    else:
                        # Not in top k, stop this trial
                        self._trial_state[trial_id] = (trial_rung, fidelity, best_val, budget, "stopped")

        return to_promote

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:
                return i
        return None


@dataclass
class MOASHAConfig:
    """
    MO-ASHA hyperparameters (Tier 1 multi-objective scheduler).

    Survey: Ch 7 multi-objective methods.
    Extension of ASHA to multi-objective case using hypervolume contribution.
    """
    r_min: float  # Minimum budget per trial
    r_max: float  # Maximum budget per trial
    eta: float = 3.0  # Reduction factor (promote top 1/eta each rung)
    objectives: list[str] = None  # Objective names (minimize all)
    reference_point: Optional[list[float]] = None  # Reference point for hypervolume


class MOASHAScheduler:
    """
    Multi-objective ASHA: successive halving with Pareto-based ranking.

    Survey: Ch 5 (successive halving), Ch 7 (multi-objective methods).
    BUILD_PROGRAM_v2.md: Tier 1 MO stack.

    Features:
    - Hypervolume contribution ranking for promotion
    - Pareto front tracking
    - 2-3 objectives (Tier 1 scope)
    - Veto gates: correctness constraints evaluated at every rung

    Algorithm:
    1. Trials report multi-objective values at rungs
    2. Evaluate veto gates (if registered); failing trials are stopped immediately
    3. Compute hypervolume contribution of each non-vetoed trial
    4. Promote top 1/eta by hypervolume contribution
    5. Stop the rest

    Veto gates (Ch 15 contracts):
    - Register predicates via `gate(predicate)` that are evaluated at every rung
    - A trial failing any gate is discarded regardless of objective quality
    - Vetoed trials are never promoted, even if Pareto-optimal
    - Used by V13 (sampler correctness) and V10 (MO constraint satisfaction)
    """

    def __init__(self, config: MOASHAConfig):
        self.config = config

        if config.objectives is None or len(config.objectives) < 2:
            raise ValueError("MO-ASHA requires at least 2 objectives")

        self.n_objectives = len(config.objectives)

        # Reference point for hypervolume (anti-ideal point)
        if config.reference_point is None:
            self.reference_point = np.ones(self.n_objectives) * 1.1
        else:
            self.reference_point = np.array(config.reference_point)

        # Compute rung budgets
        self.rungs: list[float] = []
        r = config.r_min
        while r <= config.r_max:
            self.rungs.append(r)
            r *= config.eta
        if self.rungs[-1] < config.r_max:
            self.rungs.append(config.r_max)

        # Track trials: trial_id -> (rung_idx, fidelity, objectives, status, vetoed)
        self._trial_state: dict[str, tuple[int, float, np.ndarray, str, bool]] = {}

        # Track rung populations: rung_idx -> list of (trial_id, objectives) tuples
        self._rung_populations: dict[int, list[tuple[str, np.ndarray]]] = {
            i: [] for i in range(len(self.rungs))
        }

        # Veto gates: predicates evaluated at every rung
        self._gates: list[Callable[[str, dict[str, float]], bool]] = []
        self._vetoed_trials: set[str] = set()

    def report(
        self, trial_id: str, fidelity: float, objectives: dict[str, float]
    ) -> SchedulerDecision:
        """
        Report multi-objective values for a trial.

        Args:
            trial_id: Trial identifier
            fidelity: Current fidelity level
            objectives: Dict mapping objective names to values (minimize all)

        Returns:
            SchedulerDecision: continue, stop, or pause
        """
        # Extract objective values in configured order
        obj_values = np.array([objectives[obj_name] for obj_name in self.config.objectives])

        # Determine rung
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            # Not at rung boundary, continue training
            return "continue"

        # At rung boundary: evaluate veto gates
        if self._gates and trial_id not in self._vetoed_trials:
            for gate_fn in self._gates:
                if not gate_fn(trial_id, objectives):
                    # Veto this trial
                    self._vetoed_trials.add(trial_id)
                    self._trial_state[trial_id] = (rung_idx, fidelity, obj_values, "vetoed", True)
                    return "stop"

        # Update trial state
        if trial_id not in self._trial_state:
            self._trial_state[trial_id] = (rung_idx, fidelity, obj_values, "active", False)
        else:
            prev_rung, _, prev_objs, status, vetoed = self._trial_state[trial_id]
            self._trial_state[trial_id] = (rung_idx, fidelity, obj_values, "active", vetoed)

        # Record at rung
        self._rung_populations[rung_idx].append((trial_id, obj_values))

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            trial_rung, trial_fid, trial_obj, _, vetoed = self._trial_state[trial_id]
            self._trial_state[trial_id] = (trial_rung, trial_fid, trial_obj, "stopped", vetoed)
            return "stop"

        # Pause and wait for promotion decision
        trial_rung, trial_fid, trial_obj, _, vetoed = self._trial_state[trial_id]
        self._trial_state[trial_id] = (trial_rung, trial_fid, trial_obj, "paused", vetoed)
        return "pause"

    def promote(self) -> list[tuple[str, float]]:
        """
        Promote trials based on hypervolume contribution.

        Returns:
            List of (trial_id, next_fidelity) for trials to resume
        """
        to_promote: list[tuple[str, float]] = []

        for rung_idx in range(len(self.rungs) - 1):
            # Filter out vetoed trials from the population
            pop = [
                (tid, obj)
                for tid, obj in self._rung_populations[rung_idx]
                if tid not in self._vetoed_trials
            ]
            if not pop:
                continue

            n_pop = len(pop)

            # Edge case: promote all if population too small
            if n_pop <= self.config.eta:
                n_promote = n_pop
            else:
                n_promote = max(1, math.ceil(n_pop / self.config.eta))

            # Rank by Pareto fronts, then by hypervolume contribution within front
            ranked = self._rank_population(pop)

            promoted_ids = set(ranked[:n_promote])

            # Update states and build promotion list
            for trial_id, (trial_rung, fidelity, obj_values, status, vetoed) in list(self._trial_state.items()):
                if trial_rung == rung_idx and status == "paused" and not vetoed:
                    if trial_id in promoted_ids:
                        # Promote
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        to_promote.append((trial_id, next_fidelity))
                        self._trial_state[trial_id] = (next_rung, next_fidelity, obj_values, "active", False)
                    else:
                        # Stop
                        self._trial_state[trial_id] = (trial_rung, fidelity, obj_values, "stopped", False)

        return to_promote

    def gate(self, predicate: Callable[[str, dict[str, float]], bool]) -> None:
        """
        Register a veto gate evaluated at every rung.

        A trial failing any gate is discarded regardless of its objective values.
        Multiple gates can be registered; a trial must pass all gates to avoid veto.

        Survey reference: Ch 15 contracts (gate predicate), Ch 7 MO-ASHA correctness.

        Args:
            predicate: Function(trial_id, objectives) -> bool
                       Returns True if trial passes, False if trial should be vetoed
        """
        self._gates.append(predicate)

    def get_vetoed_trials(self) -> list[str]:
        """
        Return trial IDs that failed any gate.

        Returns:
            Sorted list of vetoed trial IDs
        """
        return sorted(self._vetoed_trials)

    def _rank_population(self, population: list[tuple[str, np.ndarray]]) -> list[str]:
        """
        Rank population by Pareto fronts, then hypervolume within each front.

        Args:
            population: List of (trial_id, objectives) tuples

        Returns:
            List of trial_ids in ranked order (best first)
        """
        if len(population) == 0:
            return []

        # Extract objectives and trial IDs
        trial_ids = [tid for tid, _ in population]
        objectives = np.array([obj for _, obj in population])

        # Adapt reference point to observed data
        # Use worst observed value per objective + 10% margin
        adapted_ref = np.max(objectives, axis=0) * 1.1

        # Non-dominated sorting (assign front indices)
        fronts = self._fast_non_dominated_sort(objectives)

        # Rank by front, then by hypervolume contribution within front
        ranked = []
        for front in fronts:
            if not front:
                continue

            # Compute hypervolume contributions for this front
            front_objs = objectives[front]
            contributions = []
            for i, idx in enumerate(front):
                # Dominated volume from this point to reference point
                distances = np.maximum(0.0, adapted_ref - front_objs[i])
                contrib = np.prod(distances)
                contributions.append(contrib)

            # Sort front by contribution (descending)
            front_ranked = sorted(
                zip(front, contributions),
                key=lambda x: x[1],
                reverse=True
            )

            # Add to ranked list
            for idx, _ in front_ranked:
                ranked.append(trial_ids[idx])

        return ranked

    def _fast_non_dominated_sort(self, objectives: np.ndarray) -> list[list[int]]:
        """
        Fast non-dominated sorting (NSGA-II algorithm).

        Args:
            objectives: (n_trials, n_objectives) array

        Returns:
            List of fronts, each front is a list of indices
        """
        n = len(objectives)
        domination_count = np.zeros(n, dtype=int)
        dominated_solutions = [[] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                if self._pareto_dominates(objectives[i], objectives[j]):
                    dominated_solutions[i].append(j)
                    domination_count[j] += 1
                elif self._pareto_dominates(objectives[j], objectives[i]):
                    dominated_solutions[j].append(i)
                    domination_count[i] += 1

        fronts = []
        current_front = [i for i in range(n) if domination_count[i] == 0]

        while current_front:
            fronts.append(current_front)
            next_front = []
            for i in current_front:
                for j in dominated_solutions[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        next_front.append(j)
            current_front = next_front

        return fronts

    def _compute_hypervolume_contributions(
        self, population: list[tuple[str, np.ndarray]]
    ) -> list[float]:
        """
        Compute hypervolume contribution of each trial.

        Args:
            population: List of (trial_id, objectives) tuples

        Returns:
            List of hypervolume contributions (higher = better)
        """
        if len(population) == 0:
            return []

        # Extract objectives
        objectives = np.array([obj for _, obj in population])

        # Compute Pareto front
        pareto_mask = self._compute_pareto_mask(objectives)

        # Contribution = hypervolume with this point - hypervolume without
        # Simplified: use dominated hypervolume approximation
        contributions = []
        for i, obj in enumerate(objectives):
            if pareto_mask[i]:
                # On Pareto front: compute dominated volume
                contrib = self._dominated_hypervolume(obj)
            else:
                # Dominated: zero contribution
                contrib = 0.0
            contributions.append(contrib)

        return contributions

    def _compute_pareto_mask(self, objectives: np.ndarray) -> np.ndarray:
        """
        Compute mask of non-dominated solutions (Pareto front).

        Args:
            objectives: (n_trials, n_objectives) array

        Returns:
            Boolean mask: True for Pareto-optimal trials
        """
        n = len(objectives)
        is_pareto = np.ones(n, dtype=bool)

        for i in range(n):
            # Check if any other point dominates this one
            for j in range(n):
                if i == j:
                    continue
                if self._pareto_dominates(objectives[j], objectives[i]):
                    is_pareto[i] = False
                    break

        return is_pareto

    def _pareto_dominates(self, obj_a: np.ndarray, obj_b: np.ndarray) -> bool:
        """Check if obj_a dominates obj_b (minimize all objectives)."""
        return np.all(obj_a <= obj_b) and np.any(obj_a < obj_b)

    def _dominated_hypervolume(self, objectives: np.ndarray) -> float:
        """
        Compute dominated hypervolume of a single point.

        Simplified version: product of distances to reference point.
        For proper hypervolume, would need more complex algorithm.

        Args:
            objectives: Objective values for one trial

        Returns:
            Dominated hypervolume (approximation)
        """
        # Distance from each objective to reference point
        distances = np.maximum(0.0, self.reference_point - objectives)

        # Product gives dominated hypervolume (rectangular approximation)
        return np.prod(distances)

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:
                return i
        return None
