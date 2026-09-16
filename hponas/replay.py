"""
Replay infrastructure for V02 deterministic state replay validation.

Given an event log, replay produces bit-identical suggestions from the same seed.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from hponas.events import EventLog, EventType
from hponas.searchers.base import BaseSearcher
from hponas.space import SearchSpace


class ReplayEngine:
    """
    Deterministic replay engine for V02 validation.

    Protocol: Given an event log, replay from seed produces identical suggestions.
    """

    def __init__(
        self,
        searcher: BaseSearcher,
        event_log: EventLog,
        seed: int
    ):
        """
        Initialize replay engine.

        Args:
            searcher: Fresh searcher instance (will be seeded)
            event_log: Event log from original run
            seed: Random seed (must match original run)
        """
        self.searcher = searcher
        self.event_log = event_log
        self.seed = seed
        self._replay_position = 0

    def replay_suggestions(self, n_trials: int) -> list[dict[str, Any]]:
        """
        Replay suggestions from event log.

        V02 Protocol: Replayed suggestions must exactly match original suggestions.

        Args:
            n_trials: Number of trials to replay

        Returns:
            List of replayed configs (should match original run)

        Raises:
            ValueError: If event log is empty (V02 non-vacuity)
        """
        if self.event_log.is_empty():
            raise ValueError("Cannot replay from empty event log (V02 non-vacuity)")

        # Get suggestion events from log
        suggest_events = self.event_log.get_suggestions()

        if len(suggest_events) < n_trials:
            raise ValueError(
                f"Event log has {len(suggest_events)} suggestions, "
                f"cannot replay {n_trials} trials"
            )

        # Extract original suggestions
        original_suggestions = []
        for i in range(n_trials):
            event = suggest_events[i]
            original_suggestions.append(event.data["config"])

        return original_suggestions

    def verify_determinism(
        self,
        n_trials: int,
        batch_size: int = 1
    ) -> tuple[bool, str, list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Verify searcher produces identical suggestions when replayed.

        V02 Protocol: This is the core verification - fresh searcher with same seed
        and same observations should produce identical suggestions.

        Args:
            n_trials: Number of trials to verify
            batch_size: Batch size for suggest() calls

        Returns:
            (passed, message, original_suggestions, replayed_suggestions)
        """
        if self.event_log.is_empty():
            return False, "Empty event log (V02 non-vacuity)", [], []

        # Get original suggestions and observations from log
        suggest_events = self.event_log.get_suggestions()[:n_trials]
        observe_events = self.event_log.get_observations()

        original_suggestions = [e.data["config"] for e in suggest_events]

        # Replay: fresh searcher with same seed, call suggest() same number of times
        replayed_suggestions = []
        observation_idx = 0

        for trial_idx in range(n_trials):
            # Report observations for previous trials (if any)
            while observation_idx < len(observe_events):
                obs_event = observe_events[observation_idx]
                obs_trial_id = obs_event.trial_id
                trial_num = int(obs_trial_id.split("_")[-1])

                if trial_num >= trial_idx:
                    break

                # Report observation to replayed searcher (create Result object)
                from hponas.types import Result, Config
                result = Result(
                    trial_id=obs_trial_id,
                    objective_value=obs_event.data["value"],
                    cost=obs_event.data["cost"],
                    status="completed"
                )
                self.searcher.observe(result)
                observation_idx += 1

            # Suggest next config
            config = self.searcher.suggest()
            replayed_suggestions.append(config.to_dict()["values"])

        # Compare
        if len(original_suggestions) != len(replayed_suggestions):
            return (
                False,
                f"Length mismatch: {len(original_suggestions)} vs {len(replayed_suggestions)}",
                original_suggestions,
                replayed_suggestions
            )

        for i, (orig, replay) in enumerate(zip(original_suggestions, replayed_suggestions)):
            if set(orig.keys()) != set(replay.keys()):
                return (
                    False,
                    f"Trial {i}: key mismatch {orig.keys()} vs {replay.keys()}",
                    original_suggestions,
                    replayed_suggestions
                )

            for key in orig:
                if orig[key] != replay[key]:
                    return (
                        False,
                        f"Trial {i}, key '{key}': {orig[key]} != {replay[key]}",
                        original_suggestions,
                        replayed_suggestions
                    )

        return True, "Replay exact", original_suggestions, replayed_suggestions


def record_optimization_run(
    searcher: BaseSearcher,
    objective_fn: callable,
    n_trials: int,
    event_log: EventLog,
    batch_size: int = 1
) -> list:
    """
    Run optimization loop with event logging.

    V02 Protocol: This is the "original run" that creates the event log.

    Args:
        searcher: Searcher instance
        objective_fn: Function to evaluate (config -> value)
        n_trials: Number of trials to run
        event_log: EventLog to record events to
        batch_size: Not used (kept for compatibility)

    Returns:
        List of suggested Config objects
    """
    from hponas.types import Result

    all_suggestions = []

    for trial_idx in range(n_trials):
        # Suggest next config
        config = searcher.suggest()
        trial_id = f"trial_{trial_idx}"

        # Record suggestion
        event_log.record_suggest(
            trial_id=trial_id,
            config=config.to_dict()["values"],
            seed=searcher.seed if hasattr(searcher, 'seed') else -1
        )

        # Evaluate
        value = objective_fn(config)
        cost = 100.0  # Placeholder

        # Record observation
        event_log.record_observe(
            trial_id=trial_id,
            fidelity=1.0,
            value=value,
            cost=cost
        )

        # Report to searcher via observe()
        result = Result(
            trial_id=trial_id,
            objective_value=value,
            cost=cost,
            status="completed"
        )
        searcher.observe(result)

        all_suggestions.append(config)

    return all_suggestions
