"""Re-execute searcher and scheduler transitions in the recorded event order."""

from __future__ import annotations
import copy
import time
from hponas.events import EventType
from hponas.types import Config, Result, Trial
from hponas.searchers.base import PendingSuggestionError, SearchSpaceExhaustedError, SearchBudgetExhaustedError


class ReplayEngine:
    def __init__(self, searcher, event_log, seed, scheduler=None):
        self.searcher, self.event_log, self.seed, self.scheduler = (
            searcher,
            event_log,
            seed,
            scheduler,
        )
        self._initial = copy.deepcopy(searcher.get_state())
        self._scheduler_initial = (
            copy.deepcopy(scheduler.state_dict()) if scheduler else None
        )

    def replay_suggestions(self, n_trials):
        if self.event_log.is_empty():
            raise ValueError("Cannot replay from empty event log")
        passed, message, _, replayed = self.verify_determinism(n_trials)
        if not passed:
            raise ValueError(message)
        return replayed

    def verify_determinism(self, n_trials, batch_size=1):
        original, replayed = [], []
        if self.event_log.is_empty() or n_trials < 1:
            return False, "Empty event log or replay request", original, replayed
        self.searcher.set_state(copy.deepcopy(self._initial))
        if self.scheduler:
            self.scheduler.load_state_dict(copy.deepcopy(self._scheduler_initial))
        promotion_queue = []
        explicit_rounds = any(
            e.event_type == EventType.PROMOTION_ROUND
            for e in self.event_log.get_events()
        )
        seen_trials = set()
        trial_roots, observations = {}, {}
        cancellations = set()
        last_event = -1
        try:
            for event in self.event_log.get_events():
                if event.event_id <= last_event:
                    raise ValueError("Event order is not strictly increasing")
                last_event = event.event_id
                data = event.data
                if event.event_type == EventType.SEARCH_BUDGET_EXHAUSTED:
                    if data.get("schema_version") != 1:
                        raise ValueError("Unsupported search budget event version")
                    try:
                        self.searcher.suggest()
                    except SearchBudgetExhaustedError:
                        pass
                    else:
                        raise ValueError("Search budget was not exhausted")
                elif event.event_type == EventType.SEARCH_EXHAUSTED:
                    if data.get("schema_version") != 1:
                        raise ValueError("Unsupported exhaustion event version")
                    try:
                        self.searcher.suggest()
                    except SearchSpaceExhaustedError:
                        pass
                    else:
                        raise ValueError("Search space was not exhausted")
                elif event.event_type == EventType.SUGGEST_PENDING:
                    if data.get("schema_version") != 1:
                        raise ValueError("Unsupported pending suggestion version")
                    try:
                        if hasattr(self.searcher, "set_scheduler_context"):
                            self.searcher.set_scheduler_context(self.scheduler)
                        self.searcher.suggest()
                    except PendingSuggestionError:
                        pass
                    else:
                        raise ValueError("Pending suggestion unexpectedly completed")
                elif event.event_type == EventType.SUGGEST:
                    if len(original) == n_trials:
                        break
                    if event.trial_id in seen_trials:
                        raise ValueError("Duplicate suggestion identity")
                    seen_trials.add(event.trial_id)
                    trial_roots[event.trial_id] = event.trial_id
                    if hasattr(self.searcher, "set_scheduler_context"):
                        self.searcher.set_scheduler_context(self.scheduler)
                    config = self.searcher.suggest()
                    if self.scheduler is not None and hasattr(self.scheduler, "register_trial"):
                        fidelity = self.scheduler.register_trial(event.trial_id)
                        if data.get("fidelity") != fidelity:
                            raise ValueError("Initial scheduler fidelity mismatch")
                    original.append(data["config"])
                    replayed.append(config.values)
                    if config.values != data["config"]:
                        raise ValueError(f"Suggestion mismatch for {event.trial_id}")
                    self.searcher.trials[event.trial_id] = config
                    if hasattr(self.searcher, "register_trial"):
                        self.searcher.register_trial(Trial(config, event.trial_id,
                            fidelity=data["fidelity"], root_trial_id=event.trial_id))
                elif event.event_type == EventType.OBSERVE:
                    if event.trial_id not in self.searcher.trials:
                        raise ValueError("Observation without configuration")
                    result = Result(
                        event.trial_id,
                        data.get("objective_value", data.get("value")),
                        data.get("cost", 0.0),
                        data.get("fidelity", 1.0),
                        data.get("metadata", {}),
                        data.get("status", "completed"),
                    )
                    self.searcher.observe(result)
                    observations[event.trial_id] = result
                elif event.event_type == EventType.REPORT:
                    if self.scheduler is None:
                        raise ValueError("Scheduler required to replay report events")
                    actual = self.scheduler.report(
                        data["root"], data["fidelity"], data["value"]
                    )
                    if actual != data["decision"]:
                        raise ValueError("Scheduler report mismatch")
                elif event.event_type == EventType.PROGRESS:
                    if data.get("schema_version") != 1:
                        raise ValueError("Unsupported progress version")
                    if (
                        event.trial_id not in trial_roots
                        or event.trial_id in observations
                        or data["root"] != trial_roots[event.trial_id]
                        or data["root_trial_id"] != data["root"]
                    ):
                        raise ValueError("Progress identity or lifecycle mismatch")
                    if data["scheduler_applied"]:
                        if self.scheduler is None:
                            raise ValueError("Scheduler required to replay progress")
                        options = (
                            {"is_progress": True}
                            if (
                                hasattr(self.scheduler, "finish")
                                and getattr(
                                    self.scheduler.config, "promotion_policy", None
                                )
                                != "legacy_bootstrap"
                            )
                            else {}
                        )
                        actual = self.scheduler.report(
                            data["root"],
                            data["step"],
                            data["normalized_value"],
                            **options,
                        )
                        if actual != data["scheduler_decision"]:
                            raise ValueError("Scheduler progress mismatch")
                        action = actual
                        if (
                            actual == "stop"
                            and data["step"] == self.scheduler.config.r_max
                            and getattr(self.scheduler, "_terminal", {}).get(
                                data["root"]
                            )
                            != "pruned"
                        ):
                            action = "continue"
                        if data["control"]["action"] != action:
                            raise ValueError("Scheduler progress control mismatch")
                    if data["control"]["action"] == "cancel":
                        reason = data["control"]["reason"]
                        if reason == "user_cancellation":
                            if data["root"] not in cancellations:
                                raise ValueError("Cancellation without a request")
                        elif reason == "compute_budget_exhausted":
                            cap = data.get("compute_budget_seconds")
                            if cap is None or data["total_elapsed_seconds"] < cap:
                                raise ValueError(
                                    "Compute cancellation before budget exhaustion"
                                )
                        else:
                            raise ValueError("Unknown cancellation reason")
                elif event.event_type == EventType.CANCEL_REQUEST:
                    if data.get("schema_version") != 1 or data[
                        "root"
                    ] != trial_roots.get(event.trial_id):
                        raise ValueError("Cancellation identity or version mismatch")
                    cancellations.add(data["root"])
                elif event.event_type == EventType.FINISH:
                    if self.scheduler is None or not hasattr(self.scheduler, "finish"):
                        raise ValueError("Scheduler required to replay completion")
                    if data.get("schema_version") != 1:
                        raise ValueError("Unsupported completion version")
                    if data["root"] != trial_roots.get(event.trial_id):
                        raise ValueError("Completion identity mismatch")
                    observation = observations.get(event.trial_id)
                    expected = None
                    if observation:
                        expected = (
                            observation.status
                            if observation.status
                            in {"completed", "pruned", "cancelled"}
                            else "failed"
                        )
                    if data["status"] == "cancelled" and data["root"] in cancellations:
                        expected = "cancelled"
                    if data["status"] != expected:
                        raise ValueError("Completion disagrees with evaluation outcome")
                    self.scheduler.finish(data["root"], data["status"])
                elif event.event_type == EventType.PROMOTION_ROUND:
                    if self.scheduler is None:
                        raise ValueError(
                            "Scheduler required to replay promotion rounds"
                        )
                    if promotion_queue:
                        raise ValueError("Missing promotion events")
                    promotion_queue = list(self.scheduler.promote())
                    if [list(p) for p in promotion_queue] != data["promotions"]:
                        raise ValueError("Scheduler promotion round mismatch")
                elif event.event_type == EventType.PROMOTE:
                    if self.scheduler is None:
                        raise ValueError("Scheduler required to replay promotions")
                    if not promotion_queue and not explicit_rounds:
                        promotion_queue = list(self.scheduler.promote())
                    actual = promotion_queue.pop(0) if promotion_queue else None
                    expected = (data.get("root", event.trial_id), data["to_fidelity"])
                    if actual != expected:
                        raise ValueError("Scheduler promotion mismatch")
                    if "config" in data:
                        parent = self.searcher.trials.get(data.get("parent"))
                        self.searcher.trials[event.trial_id] = Config(
                            data["config"], parent.config_id if parent else None
                        )
                        if hasattr(self.searcher, "register_trial"):
                            self.searcher.register_trial(Trial(self.searcher.trials[event.trial_id],
                                event.trial_id, fidelity=data["to_fidelity"],
                                root_trial_id=data["root"], parent_trial_id=data.get("parent")))
                    trial_roots[event.trial_id] = data.get("root", event.trial_id)
                elif event.event_type == EventType.CULL:
                    raise ValueError("Cull event lacks a replayable scheduler report")
            if len(original) != n_trials:
                raise ValueError("Insufficient suggestion events")
            if promotion_queue:
                raise ValueError("Missing promotion events")
        except (KeyError, ValueError, TypeError, PendingSuggestionError, SearchSpaceExhaustedError) as exc:
            return False, str(exc), original, replayed
        return True, "Replay exact", original, replayed


def record_optimization_run(searcher, objective_fn, n_trials, event_log, batch_size=1):
    if n_trials < 1 or batch_size < 1:
        raise ValueError("Trials and batch size must be positive")
    all_suggestions = []
    for start in range(0, n_trials, batch_size):
        batch = []
        for index in range(start, min(start + batch_size, n_trials)):
            config = searcher.suggest()
            tid = f"trial_{index}"
            searcher.trials[tid] = config
            event_log.record_suggest(tid, config.values, searcher.seed)
            batch.append((tid, config))
            all_suggestions.append(config)
        for tid, config in batch:
            started = time.monotonic()
            value = float(objective_fn(config))
            cost = time.monotonic() - started
            event_log.record_observe(tid, 1.0, value, cost)
            searcher.observe(Result(tid, value, cost))
    return all_suggestions
