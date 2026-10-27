"""
Schedulers: allocate budget across running trials.

Survey reference: Ch 15 sec:scheduler-interface, Ch 5 (multifidelity).

R1 spike: ASHA with async promotion, no median stopping yet.
Tier 0: adds median rule, PASHA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Callable, Literal, Optional

import numpy as np

SchedulerDecision = Literal["continue", "stop", "pause"]


def _validate_rungs(config):
    if (
        not np.isfinite([config.eta, config.r_min, config.r_max]).all()
        or config.eta <= 1
        or config.r_min <= 0
        or config.r_max < config.r_min
    ):
        raise ValueError("Require finite eta>1 and 0<r_min<=r_max")


def _upsert_report(population, trial_id, value):
    for index, (tid, _) in enumerate(population):
        if tid == trial_id:
            population[index] = (trial_id, value)
            return
    population.append((trial_id, value))


def _ceil_population_ratio(population_size, eta):
    """Ceil(n/eta) for the exact represented reduction factor, without rounding.

    Dividing integers through a float can round n/eta down to an integer and
    under-promote. Use integer arithmetic for both integral and float eta.
    Callers already validate positive, finite eta.
    """
    if isinstance(eta, (int, np.integer)):
        numerator, denominator = int(eta), 1
    else:
        numerator, denominator = eta.as_integer_ratio()
    return -(-(population_size * denominator) // numerator)


def _promotion_cutoff(population, eta):
    """Pinned reference's linear quantile without overflowing a subtraction.

    NumPy's interpolation can form ``right - left`` and overflow for opposite
    extreme finite losses. Convex weighted terms preserve the source policy.
    The caller supplies at least two observations.
    """
    values = sorted(value for _, value in population)
    virtual = (len(values) - 1) * (1 / eta) + 1
    index = int(virtual)
    fraction = virtual - index
    return fraction * values[index] + (1 - fraction) * values[index - 1]


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
    promotion_policy: str = "syne_tune_0_13_0"
    median_min_completed: int = 5
    report_grid: tuple[float, ...] = ()

    def __post_init__(self):
        _validate_rungs(self)
        if self.promotion_policy not in {"syne_tune_0_13_0", "legacy_bootstrap"}:
            raise ValueError("Unknown ASHA promotion_policy")
        if (isinstance(self.median_min_completed, bool)
                or not isinstance(self.median_min_completed, int)
                or self.median_min_completed < 1):
            raise ValueError("median_min_completed must be a positive integer")
        self.report_grid = tuple(self.report_grid)
        if any(not np.isfinite(s) or s <= 0 or s > self.r_max for s in self.report_grid):
            raise ValueError("report_grid must contain finite steps in (0, r_max]")
        if tuple(sorted(set(self.report_grid))) != self.report_grid:
            raise ValueError("report_grid must be strictly increasing")
        if (self.median_stopping and self.promotion_policy != "legacy_bootstrap"
                and not self.report_grid):
            raise ValueError("Streamed median stopping requires an explicit report_grid")


class ASHAScheduler:
    """
    Asynchronous Successive Halving (ASHA) scheduler (Ch 5 roadmap-03, ch05-01).

    Survey verdict: include, T0, days.
    Contract: scheduler impl: asha.
    Validation: V02 (async correctness), V06 (nearly-free early stopping).

    Reference promotion: Syne Tune 0.13.0 quantile policy. Optional median
    pruning uses completed trials on an explicit streamed report grid.
    """

    def __init__(self, config: ASHAConfig):
        _validate_rungs(config)
        self.config = config

        # Compute rung budgets: [r_min, r_min*η, r_min*η^2, ..., r_max]
        self.rungs: list[float] = []
        r = config.r_min
        while r < config.r_max:
            self.rungs.append(r)
            next_r = r * config.eta
            if next_r <= r:
                raise ValueError("Rung budgets must strictly increase at float precision")
            r = next_r
        self.rungs.append(config.r_max)

        # Track trials: trial_id -> (current_rung_idx, current_fidelity, best_value_so_far, status)
        self._trial_state: dict[str, tuple[int, float, Optional[float], str]] = {}

        # Track rung populations: rung_idx -> list of (trial_id, value) tuples
        # Each trial occupies at most one entry at a rung
        self._rung_populations: dict[int, list[tuple[str, float]]] = {
            i: [] for i in range(len(self.rungs))
        }

        # Median stopping: track all observations at each fidelity for running median
        # fidelity -> list of values
        self._fidelity_history: dict[float, list[float]] = {}
        self._median_reports = {}
        self._last_reports = {}
        self._running_histories = {}
        self._terminal = {}

    def report(self, trial_id: str, fidelity: float, value: float,
               *, is_progress: bool = False) -> SchedulerDecision:
        """Report a normalized loss; only streamed reports enter median histories.

        Endpoint completion is recorded separately by ``finish``. A rung result
        alone never makes a trial a completed median reference.
        """
        if self.config.promotion_policy == "legacy_bootstrap":
            return self._legacy_report(trial_id, fidelity, value)
        if not np.isfinite([fidelity, value]).all() or fidelity <= 0:
            raise ValueError("Reports require positive fidelity and a finite value")
        previous = self._trial_state.get(trial_id)
        if trial_id in self._terminal or (previous and previous[-1] == "stopped"):
            return "stop"
        last = self._last_reports.get(trial_id)
        if last and fidelity <= last[0]:
            if fidelity == last[0] and value != last[1]:
                raise ValueError("Conflicting duplicate scheduler report")
            if previous and previous[-1] == "active":
                return "continue"
            return last[2] if fidelity == last[0] else "continue"
        if previous and previous[-1] == "paused":
            # Training may resume only after an explicit promotion.
            return "pause"
        if is_progress:
            history = self._running_histories.setdefault(trial_id, {})
            history[fidelity] = value
            if self._median_should_stop(trial_id, fidelity):
                self._trial_state[trial_id] = (-1, fidelity, value, "stopped")
                self._last_reports[trial_id] = (fidelity, value, "stop")
                self._terminal[trial_id] = "pruned"
                return "stop"
        rung_idx = self._fidelity_to_rung(fidelity)
        decision = "continue"
        if rung_idx is not None:
            _upsert_report(self._rung_populations[rung_idx], trial_id, value)
            decision = "stop" if rung_idx == len(self.rungs) - 1 else "pause"
            self._trial_state[trial_id] = (
                rung_idx, fidelity, value, "stopped" if decision == "stop" else "paused"
            )
        self._last_reports[trial_id] = (fidelity, value, decision)
        return decision

    def _median_should_stop(self, trial_id, step):
        if not self.config.median_stopping or step not in self.config.report_grid:
            return False
        prefix = [s for s in self.config.report_grid if s <= step]
        current = self._running_histories[trial_id]
        if any(s not in current for s in prefix):
            return False  # Missing steps are never interpolated.
        references = []
        for tid, status in self._terminal.items():
            history = self._running_histories.get(tid, {})
            if status == "completed" and tid != trial_id and all(s in history for s in prefix):
                references.append(float(np.mean([history[s] for s in prefix])))
        return (len(references) >= self.config.median_min_completed
                and np.mean([current[s] for s in prefix]) > np.median(references))

    def finish(self, trial_id: str, status: str) -> None:
        """Record terminal training status, distinct from a completed rung call."""
        if status not in {"completed", "failed", "cancelled", "pruned"}:
            raise ValueError("Unknown terminal trial status")
        prior = self._terminal.get(trial_id)
        if prior:
            if prior != status:
                raise ValueError("Conflicting terminal trial status")
            return
        if status == "completed":
            last = self._last_reports.get(trial_id)
            if last is None or self._fidelity_to_rung(last[0]) != len(self.rungs) - 1:
                raise ValueError("Completion requires a full-fidelity report")
        self._terminal[trial_id] = status
        if trial_id in self._trial_state:
            rung, fidelity, value, _ = self._trial_state[trial_id]
            self._trial_state[trial_id] = (rung, fidelity, value, "stopped")

    def promote(self) -> list[tuple[str, float]]:
        """Dispatch one reference-eligible trial, preferring the highest rung.

        Linear 1/eta quantile with at least two observations; ties qualify.
        Ineligible trials remain paused and promoted trials stay in the cutoff
        population. Repeated calls can fill multiple available worker slots.
        """
        if self.config.promotion_policy == "legacy_bootstrap":
            return self._legacy_promote()
        for rung_idx in reversed(range(len(self.rungs) - 1)):
            population = self._rung_populations[rung_idx]
            if len(population) < 2:
                continue
            cutoff = _promotion_cutoff(population, self.config.eta)
            for tid, value in sorted(population, key=lambda entry: entry[1]):
                state = self._trial_state[tid]
                if (value <= cutoff and state[0] == rung_idx and state[-1] == "paused"
                        and tid not in self._terminal):
                    target = self.rungs[rung_idx + 1]
                    self._trial_state[tid] = (rung_idx + 1, target, value, "active")
                    return [(tid, target)]
        return []

    def _legacy_report(self, trial_id: str, fidelity: float, value: float) -> SchedulerDecision:
        """
        Called as metrics stream in (Ch 15 contract).

        Returns: continue (keep training), stop (kill trial), pause (wait for promotion).
        Survey: ASHA and median rule live entirely behind this verb.

        Tier 0: adds median stopping rule (Ch 5 roadmap-03, ch05-01).
        Median rule: stop if value > median of all values seen at this fidelity.
        """
        if not np.isfinite([fidelity, value]).all() or fidelity <= 0:
            raise ValueError("Reports require positive fidelity and a finite value")
        previous = self._trial_state.get(trial_id)
        if previous and (fidelity < previous[1] or previous[-1] == "stopped"):
            return "stop" if previous[-1] == "stopped" else "continue"
        # Determine which rung this fidelity corresponds to
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            # Not at a rung boundary
            # Apply median stopping if enabled
            if self.config.median_stopping:
                if fidelity not in self._fidelity_history:
                    self._fidelity_history[fidelity] = []
                reports = self._median_reports.setdefault(fidelity, {})
                reports[trial_id] = value
                self._fidelity_history[fidelity] = list(reports.values())

                # Stop if worse than median (minimize objective)
                history = self._fidelity_history[fidelity]
                if (
                    len(history) >= 5
                ):  # Need at least 5 observations for reliable median
                    median = np.median(history)
                    if value > median:
                        self._trial_state[trial_id] = (-1, fidelity, value, "stopped")
                        return "stop"

            return "continue"

        # At a rung boundary
        # Update trial state with best value so far
        if trial_id not in self._trial_state:
            best_val = value
        else:
            _, _, prev_best, _ = self._trial_state[trial_id]
            best_val = value if prev_best is None else min(value, prev_best)

        # Replace the prior report at this rung
        _upsert_report(self._rung_populations[rung_idx], trial_id, value)

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (rung_idx, fidelity, best_val, "stopped")
            return "stop"

        # In async ASHA, we can't make stop/pause decisions at report time because
        # we don't know the final population. Mark everything as paused; promote()
        # will select the top k trials when called.
        self._trial_state[trial_id] = (rung_idx, fidelity, best_val, "paused")
        return "pause"

    def _legacy_promote(self) -> list[tuple[str, float]]:
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
                n_promote = _ceil_population_ratio(n_pop, self.config.eta)

            # Sort by value (ascending = best first)
            sorted_pop = sorted(pop, key=lambda x: x[1])

            # Top n_promote trials get promoted, rest get stopped
            promoted_ids = {tid for tid, _ in sorted_pop[:n_promote]}

            # Update states and build promotion list
            for trial_id, (trial_rung, fidelity, best_val, status) in list(
                self._trial_state.items()
            ):
                if trial_rung == rung_idx and status == "paused":
                    if trial_id in promoted_ids:
                        # Promote this trial
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        to_promote.append((trial_id, next_fidelity))
                        self._trial_state[trial_id] = (
                            next_rung,
                            next_fidelity,
                            best_val,
                            "active",
                        )
                    else:
                        # Stop this trial
                        self._trial_state[trial_id] = (
                            trial_rung,
                            fidelity,
                            best_val,
                            "stopped",
                        )

        return to_promote

    def state_dict(self) -> dict[str, Any]:
        """Serialize scheduler state for checkpointing."""
        import copy

        return {
            "schema_version": 2,
            "config": asdict(self.config),
            "rungs": copy.deepcopy(self.rungs),
            "trial_state": copy.deepcopy(self._trial_state),
            "rung_populations": copy.deepcopy(self._rung_populations),
            "fidelity_history": copy.deepcopy(self._fidelity_history),
            "median_reports": copy.deepcopy(self._median_reports),
            "last_reports": copy.deepcopy(self._last_reports),
            "running_histories": copy.deepcopy(self._running_histories),
            "terminal": copy.deepcopy(self._terminal),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Validate restoration on an isolated scheduler before replacing state."""
        import copy

        candidate = copy.copy(self)
        candidate._restore_state(state)
        self.__dict__.update(candidate.__dict__)

    def _restore_state(self, state: dict[str, Any]) -> None:
        """Restore scheduler state from checkpoint."""
        import copy

        state = copy.deepcopy(state)
        config = dict(state["config"])
        config.setdefault("promotion_policy", "legacy_bootstrap")
        if config["promotion_policy"] != self.config.promotion_policy:
            raise ValueError("Checkpoint ASHA promotion policy differs; select legacy_bootstrap explicitly for legacy recovery")
        if state.get("schema_version", 1) not in (1, 2):
            raise ValueError("Unsupported ASHA checkpoint schema")
        self.config = ASHAConfig(**config)
        if self.config.promotion_policy != "legacy_bootstrap" and state.get("schema_version") != 2:
            raise ValueError("Reference ASHA requires a versioned checkpoint")
        if list(state["rungs"]) != ASHAScheduler(self.config).rungs:
            raise ValueError("Checkpoint rungs differ from scheduler configuration")
        self.rungs = list(state["rungs"])

        # Convert trial_state: JSON converts tuples to lists, so convert back
        self._trial_state = {}
        for trial_id, trial_data in state["trial_state"].items():
            # trial_data might be list or tuple depending on source
            if isinstance(trial_data, list):
                self._trial_state[trial_id] = tuple(trial_data)
            else:
                self._trial_state[trial_id] = trial_data

        # Convert rung_populations: JSON converts int keys to strings and tuples to lists
        self._rung_populations = {}
        for rung_key, pop_list in state["rung_populations"].items():
            # Convert string key back to int
            rung_idx = int(rung_key) if isinstance(rung_key, str) else rung_key
            # Convert lists back to tuples
            self._rung_populations[rung_idx] = [
                tuple(item) if isinstance(item, list) else item for item in pop_list
            ]

        self._fidelity_history = {
            float(k): list(v) for k, v in state["fidelity_history"].items()
        }
        self._median_reports = {
            float(k): dict(v) for k, v in state.get("median_reports", {}).items()
        }
        self._last_reports = {k: tuple(v) for k, v in state.get("last_reports", {}).items()}
        self._running_histories = {
            tid: {float(s): v for s, v in history.items()}
            for tid, history in state.get("running_histories", {}).items()
        }
        self._terminal = dict(state.get("terminal", {}))

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index (or None if not at a boundary)."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:  # floating-point tolerance
                return i
        return None


@dataclass
class BudgetedASHAConfig:
    """
    Shared promotion-budget controls for ASHA.

    This legacy policy was previously mislabeled PASHA. Progressive resource
    allocation is implemented separately by PASHAConfig/PASHAScheduler below.

    η: reduction factor
    r_min: minimum fidelity
    r_max: maximum fidelity
    promotion_budget: total fidelity budget available for promotions
    """

    eta: int = 3
    r_min: float = 1.0
    r_max: float = 27.0
    promotion_budget: Optional[float] = 100.0

    def __post_init__(self):
        _validate_rungs(self)
        if self.promotion_budget is not None and (
            isinstance(self.promotion_budget, bool)
            or not np.isfinite(self.promotion_budget)
            or self.promotion_budget < 0
        ):
            raise ValueError("promotion_budget must be finite and nonnegative or None")


class BudgetedASHAScheduler:
    """
    ASHA with an additional shared budget for incremental promotion fidelity.

    Retained for callers and checkpoints of the earlier budget-only policy;
    budget pooling alone is not PASHA's ranking-stabilization algorithm.
    """

    def __init__(self, config: BudgetedASHAConfig):
        _validate_rungs(config)
        self.config = config

        # Compute rung budgets
        self.rungs: list[float] = []
        r = config.r_min
        while r < config.r_max:
            self.rungs.append(r)
            next_r = r * config.eta
            if next_r <= r:
                raise ValueError("Rung budgets must strictly increase at float precision")
            r = next_r
        self.rungs.append(config.r_max)

        # Track trials: trial_id -> (current_rung_idx, current_fidelity, best_value_so_far, budget_spent, status)
        self._trial_state: dict[
            str, tuple[int, float, Optional[float], float, str]
        ] = {}

        # Track rung populations: rung_idx -> list of (trial_id, value) tuples
        self._rung_populations: dict[int, list[tuple[str, float]]] = {
            i: [] for i in range(len(self.rungs))
        }

        # Track total budget spent on promotions
        self._budget_spent = 0.0

    def report(self, trial_id: str, fidelity: float, value: float) -> SchedulerDecision:
        """
        Report a trial observation.

        Same stopping logic as ASHA, with a shared promotion budget.
        """
        if not np.isfinite([fidelity, value]).all() or fidelity <= 0:
            raise ValueError("Reports require positive fidelity and a finite value")
        previous = self._trial_state.get(trial_id)
        if previous and (fidelity < previous[1] or previous[-1] == "stopped"):
            return "stop" if previous[-1] == "stopped" else "continue"
        # Determine which rung this fidelity corresponds to
        rung_idx = self._fidelity_to_rung(fidelity)
        if rung_idx is None:
            return "continue"

        # Update trial state: track best value seen so far
        if trial_id not in self._trial_state:
            best_val = value
            budget = 0.0
        else:
            _, _, prev_best, budget, _ = self._trial_state[trial_id]
            best_val = value if prev_best is None else min(value, prev_best)

        # Record at rung
        _upsert_report(self._rung_populations[rung_idx], trial_id, value)

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (
                rung_idx,
                fidelity,
                best_val,
                budget,
                "stopped",
            )
            return "stop"

        # Mark everything as paused; promote() will select based on
        # ranking and budget availability.
        self._trial_state[trial_id] = (rung_idx, fidelity, best_val, budget, "paused")
        return "pause"

    def promote(self) -> list[tuple[str, float]]:
        """
        Promote paused trials if budget allows.

        Track budget consumption per promotion. Decide which paused trials
        to promote based on ranking within each rung and available budget.
        """
        to_promote: list[tuple[str, float]] = []

        # For each rung, decide which paused trials to promote
        for rung_idx in range(self._promotion_rung_limit()):
            pop = self._rung_populations[rung_idx]
            if not pop:
                continue

            # Calculate how many to promote from this rung
            n_pop = len(pop)
            # Edge case: when n_pop <= eta, promote all to establish the pipeline
            if n_pop <= self.config.eta:
                n_promote = n_pop
            else:
                n_promote = _ceil_population_ratio(n_pop, self.config.eta)

            # Sort by value (ascending = best first)
            sorted_pop = sorted(pop, key=lambda x: x[1])

            # Top n_promote trials are candidates for promotion
            promoted_ids = {tid for tid, _ in sorted_pop[:n_promote]}

            # Update states and build promotion list (budget-constrained)
            for trial_id, (trial_rung, fidelity, best_val, budget, status) in list(
                self._trial_state.items()
            ):
                if trial_rung == rung_idx and status == "paused":
                    if trial_id in promoted_ids:
                        # Try to promote this trial if budget allows
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        promotion_cost = next_fidelity - fidelity

                        if (
                            self.config.promotion_budget is None
                            or self._budget_spent + promotion_cost
                            <= self.config.promotion_budget
                        ):
                            to_promote.append((trial_id, next_fidelity))
                            self._budget_spent += promotion_cost
                            new_budget = budget + promotion_cost
                            self._trial_state[trial_id] = (
                                next_rung,
                                next_fidelity,
                                best_val,
                                new_budget,
                                "active",
                            )
                        else:
                            # Budget exhausted, stop this trial
                            self._trial_state[trial_id] = (
                                trial_rung,
                                fidelity,
                                best_val,
                                budget,
                                "stopped",
                            )
                    else:
                        # Not in top k, stop this trial
                        self._trial_state[trial_id] = (
                            trial_rung,
                            fidelity,
                            best_val,
                            budget,
                            "stopped",
                        )

        return to_promote

    def _promotion_rung_limit(self):
        return len(self.rungs) - 1

    def state_dict(self):
        import copy

        return copy.deepcopy(
            {
                "config": asdict(self.config),
                "rungs": self.rungs,
                "trial_state": self._trial_state,
                "rung_populations": self._rung_populations,
                "budget_spent": self._budget_spent,
            }
        )

    def load_state_dict(self, state):
        self.config = type(self.config)(**state["config"])
        self.rungs = list(state["rungs"])
        self._trial_state = {k: tuple(v) for k, v in state["trial_state"].items()}
        self._rung_populations = {
            int(k): [tuple(v) for v in values]
            for k, values in state["rung_populations"].items()
        }
        self._budget_spent = float(state["budget_spent"])

    def _fidelity_to_rung(self, fidelity: float) -> Optional[int]:
        """Map a fidelity value to its rung index."""
        for i, r in enumerate(self.rungs):
            if abs(fidelity - r) < 1e-6:
                return i
        return None


@dataclass
class PASHAConfig(BudgetedASHAConfig):
    """Progressive ASHA: grow resource limits only when rankings disagree.

    ``ranking_epsilon=None`` estimates a soft-ranking tolerance from observed
    reversals that reverse back (Bohdal et al., 2023). A fixed nonnegative
    epsilon uses the same soft-ranking rule without automatic estimation.
    An optional promotion_budget is an independent compute cap.
    """

    promotion_budget: Optional[float] = None
    ranking_epsilon: Optional[float] = None

    def __post_init__(self):
        super().__post_init__()
        if self.ranking_epsilon is not None and (
            isinstance(self.ranking_epsilon, bool)
            or not np.isfinite(self.ranking_epsilon)
            or self.ranking_epsilon < 0
        ):
            raise ValueError("ranking_epsilon must be finite and nonnegative or None")


class PASHAScheduler(BudgetedASHAScheduler):
    """PASHA's progressive resource cap over the ASHA promotion interface.

    Start at the second fidelity. Compare the same survivors at the current
    top two rungs; an ordering change outside the previous rung's epsilon
    groups opens one higher rung. Stable trials remain paused and eligible
    if later observations require more resource. Sparse reports estimate
    noise only from jointly observed fidelities; missing reports are not
    imputed. Promotions use the pinned Syne Tune quantile rule, not the
    legacy budget scheduler's bootstrap policy. See the SPEC-03 correction.
    """

    def __init__(self, config: PASHAConfig):
        super().__init__(config)
        self._current_top = min(1, len(self.rungs) - 1)
        self._epsilon = config.ranking_epsilon or 0.0
        self._resource_reports = {}

    @property
    def current_max_fidelity(self):
        return self.rungs[self._current_top]

    def _promotion_rung_limit(self):
        return self._current_top

    def promote(self) -> list[tuple[str, float]]:
        """Dispatch one eligible trial below the progressive resource cap.

        A rung needs two observations and uses the linear 1/eta quantile.
        Ties qualify, and previously promoted observations stay in the cutoff
        population. Other trials remain paused for reconsideration as results
        arrive. The optional incremental budget is a separate compute limit.
        """
        for rung_idx in reversed(range(self._current_top)):
            population = self._rung_populations[rung_idx]
            if len(population) < 2:
                continue
            cutoff = _promotion_cutoff(population, self.config.eta)
            target = self.rungs[rung_idx + 1]
            for tid, value in sorted(population, key=lambda entry: entry[1]):
                current, fidelity, best, spent, status = self._trial_state[tid]
                if current != rung_idx or status != "paused" or value > cutoff:
                    continue
                cost = target - fidelity
                if (self.config.promotion_budget is not None
                        and self._budget_spent + cost > self.config.promotion_budget):
                    continue
                self._budget_spent += cost
                self._trial_state[tid] = (rung_idx + 1, target, best, spent + cost, "active")
                return [(tid, target)]
        return []

    def report(self, trial_id, fidelity, value):
        if not np.isfinite([fidelity, value]).all() or fidelity <= 0:
            raise ValueError("Reports require positive fidelity and a finite value")
        previous = self._trial_state.get(trial_id)
        reports = self._resource_reports.get(trial_id, {})
        if previous and previous[-1] == "stopped":
            return "stop"
        if reports and fidelity <= max(reports):
            if fidelity == max(reports):
                if value != reports[fidelity]:
                    raise ValueError("Conflicting duplicate scheduler report")
                if previous and previous[-1] == "paused":
                    return "pause"
            return "continue"
        if fidelity > self.current_max_fidelity + 1e-6:
            raise ValueError("Report exceeds PASHA's current maximum fidelity")
        if previous and previous[-1] == "paused":
            return "pause"  # An explicit promotion must precede resumed training.
        decision = super().report(trial_id, fidelity, value)
        self._resource_reports.setdefault(trial_id, {})[float(fidelity)] = float(value)
        if self.config.ranking_epsilon is None:
            self._update_epsilon()
        self._maybe_increase_resources()
        return decision

    def _update_epsilon(self):
        # The terminal fidelity is not a promotion rung in the published
        # reference. Keep the final nonterminal pair when the cap reaches it.
        comparison_top = min(self._current_top, len(self.rungs) - 2)
        if comparison_top <= 0:
            return
        from itertools import combinations

        lower = self.rungs[comparison_top - 1]
        upper = self.rungs[comparison_top]
        distances = []
        for first, second in combinations(sorted(self._resource_reports), 2):
            a, b = self._resource_reports[first], self._resource_reports[second]
            shared = sorted(a.keys() & b.keys(), reverse=True)
            latest = next((r for r in shared if lower < r <= upper), None)
            if latest is None:
                continue
            ordering = a[latest] > b[latest]
            reversed_once = False
            for resource in (r for r in shared if r < latest):
                older_ordering = a[resource] > b[resource]
                if older_ordering != ordering:
                    reversed_once = True
                elif reversed_once:
                    distances.append(abs(a[latest] - b[latest]))
                    break
        if distances:
            self._epsilon = float(np.percentile(distances, 90))

    def _maybe_increase_resources(self):
        if self._current_top == 0 or self._current_top == len(self.rungs) - 1:
            return
        top = self._rung_populations[self._current_top]
        previous = dict(self._rung_populations[self._current_top - 1])
        if len(top) < 2 or any(tid not in previous for tid, _ in top):
            return  # No assertion of stability from unpaired observations.
        top_ids = {tid for tid, _ in top}
        old_order = sorted(
            ((tid, val) for tid, val in previous.items() if tid in top_ids),
            key=lambda item: item[1],
        )
        # The reference preserves arrival order among tied scores. Sorting
        # trial IDs instead can manufacture a rank reversal and open the cap.
        new_order = sorted(top, key=lambda item: item[1])
        # Same positional epsilon-group criterion as the published soft ranking.
        for (new_id, _), (_, old_value) in zip(new_order, old_order):
            if abs(previous[new_id] - old_value) > self._epsilon:
                self._current_top += 1
                return

    def state_dict(self):
        import copy

        return {
            **super().state_dict(),
            "policy": "pasha-progressive-quantile-v2",
            "current_top": self._current_top,
            "epsilon": self._epsilon,
            "resource_reports": copy.deepcopy(self._resource_reports),
        }

    def load_state_dict(self, state):
        if state.get("policy") == "pasha-progressive-v1":
            raise ValueError("Legacy PASHA promotion policy cannot resume as quantile-v2; retain its source or restart")
        if state.get("policy") != "pasha-progressive-quantile-v2":
            raise ValueError("Budget-only checkpoint requires BudgetedASHAScheduler")
        config = PASHAConfig(**state["config"])
        restored = type(self)(config)
        if list(state["rungs"]) != restored.rungs:
            raise ValueError("Checkpoint rungs differ from PASHA configuration")
        BudgetedASHAScheduler.load_state_dict(restored, state)
        top, epsilon = state["current_top"], state["epsilon"]
        if isinstance(top, bool) or not isinstance(top, int) or not (
            min(1, len(restored.rungs) - 1) <= top < len(restored.rungs)
        ):
            raise ValueError("Invalid PASHA resource cap in checkpoint")
        if not np.isfinite(epsilon) or epsilon < 0:
            raise ValueError("Invalid PASHA ranking tolerance in checkpoint")
        restored._current_top = top
        restored._epsilon = float(epsilon)
        restored._resource_reports = {
            tid: {float(r): float(v) for r, v in reports.items()}
            for tid, reports in state["resource_reports"].items()
        }
        self.__dict__.update(restored.__dict__)


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

    def __post_init__(self):
        _validate_rungs(self)


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
        _validate_rungs(config)
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
        while r < config.r_max:
            self.rungs.append(r)
            next_r = r * config.eta
            if next_r <= r:
                raise ValueError("Rung budgets must strictly increase at float precision")
            r = next_r
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
        obj_values = np.array(
            [objectives[obj_name] for obj_name in self.config.objectives]
        )

        if not np.isfinite(fidelity) or fidelity <= 0:
            raise ValueError("Reports require positive finite fidelity")
        if not np.isfinite(obj_values).all():
            self._vetoed_trials.add(trial_id)
            self._trial_state[trial_id] = (
                -1,
                fidelity,
                np.zeros(self.n_objectives),
                "vetoed",
                True,
            )
            return "stop"
        previous = self._trial_state.get(trial_id)
        if previous and (
            fidelity < previous[1] or previous[3] in ("stopped", "vetoed")
        ):
            return "stop" if previous[3] in ("stopped", "vetoed") else "continue"
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
                    self._trial_state[trial_id] = (
                        rung_idx,
                        fidelity,
                        obj_values,
                        "vetoed",
                        True,
                    )
                    return "stop"

        # Carry forward the veto flag; a trial vetoed earlier stays vetoed.
        if trial_id not in self._trial_state:
            vetoed = False
        else:
            vetoed = self._trial_state[trial_id][4]

        # A trial vetoed at an earlier rung stays stopped and is kept out of the
        # rung population, matching the early return above on the vetoing report.
        if vetoed:
            self._trial_state[trial_id] = (
                rung_idx,
                fidelity,
                obj_values,
                "vetoed",
                True,
            )
            return "stop"

        # Record at rung
        _upsert_report(self._rung_populations[rung_idx], trial_id, obj_values)

        # At final rung, stop
        if rung_idx == len(self.rungs) - 1:
            self._trial_state[trial_id] = (
                rung_idx,
                fidelity,
                obj_values,
                "stopped",
                vetoed,
            )
            return "stop"

        # Pause and wait for promotion decision
        self._trial_state[trial_id] = (rung_idx, fidelity, obj_values, "paused", vetoed)
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
                n_promote = _ceil_population_ratio(n_pop, self.config.eta)

            # Rank by Pareto fronts, then by hypervolume contribution within front
            ranked = self._rank_population(pop)

            promoted_ids = set(ranked[:n_promote])

            # Update states and build promotion list
            for trial_id, (trial_rung, fidelity, obj_values, status, vetoed) in list(
                self._trial_state.items()
            ):
                if trial_rung == rung_idx and status == "paused" and not vetoed:
                    if trial_id in promoted_ids:
                        # Promote
                        next_rung = rung_idx + 1
                        next_fidelity = self.rungs[next_rung]
                        to_promote.append((trial_id, next_fidelity))
                        self._trial_state[trial_id] = (
                            next_rung,
                            next_fidelity,
                            obj_values,
                            "active",
                            False,
                        )
                    else:
                        # Stop
                        self._trial_state[trial_id] = (
                            trial_rung,
                            fidelity,
                            obj_values,
                            "stopped",
                            False,
                        )

        return to_promote

    def state_dict(self):
        return {
            "config": asdict(self.config),
            "rungs": list(self.rungs),
            "reference_point": self.reference_point.tolist(),
            "trial_state": {
                k: [v[0], v[1], v[2].tolist(), v[3], v[4]]
                for k, v in self._trial_state.items()
            },
            "rung_populations": {
                k: [(tid, y.tolist()) for tid, y in pop]
                for k, pop in self._rung_populations.items()
            },
            "vetoed_trials": sorted(self._vetoed_trials),
            "gate_count": len(self._gates),
        }

    def load_state_dict(self, state):
        # Gate callables must be registered by the caller before restoring.
        if len(self._gates) != state["gate_count"]:
            raise ValueError("Restore requires the same registered veto gates")
        self.config = MOASHAConfig(**state["config"])
        self.n_objectives = len(self.config.objectives)
        self.rungs = list(state["rungs"])
        self.reference_point = np.asarray(state["reference_point"], dtype=float)
        self._trial_state = {
            k: (v[0], v[1], np.asarray(v[2]), v[3], v[4])
            for k, v in state["trial_state"].items()
        }
        self._rung_populations = {
            int(k): [(tid, np.asarray(y)) for tid, y in pop]
            for k, pop in state["rung_populations"].items()
        }
        self._vetoed_trials = set(state["vetoed_trials"])

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

        # Non-dominated sorting (assign front indices)
        fronts = self._fast_non_dominated_sort(objectives)

        # Rank by front, then by hypervolume contribution within front
        ranked = []
        for front in fronts:
            if not front:
                continue

            contributions = self._compute_hypervolume_contributions(
                [(trial_ids[i], objectives[i]) for i in front]
            )

            # Sort front by contribution (descending)
            front_ranked = sorted(
                zip(front, contributions), key=lambda x: x[1], reverse=True
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

        from hponas.reporting_mo import hypervolume

        total = hypervolume(objectives, self.reference_point)
        return [
            max(
                0.0,
                total
                - hypervolume(np.delete(objectives, i, axis=0), self.reference_point),
            )
            for i in range(len(objectives))
        ]

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
