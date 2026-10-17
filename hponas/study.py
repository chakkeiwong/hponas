"""Study orchestration with a durable evaluation ledger and deterministic batches."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import Future, ThreadPoolExecutor
import copy
import inspect
import json
import math
from pathlib import Path
from queue import Queue, Empty
import threading
import time
import uuid

from hponas.encoding import as_knob_space
from hponas.evaluation import EvaluationController, legacy_evaluation_report
from hponas.capabilities import admit
from hponas.budgets import ResourceController
from hponas.persistence import atomic_json
from hponas.types import Config, Trial, Result
from hponas.executors.reporting import ReportDecision
from hponas.searchers.base import PendingSuggestionError, SearchSpaceExhaustedError, SearchBudgetExhaustedError


@dataclass
class StudyResult:
    best_config: Config | None
    best_value: float | None
    history: list[Result]
    n_trials: int
    total_cost: float
    status: str = "completed"
    reason: str | None = None
    total_elapsed_seconds: float = 0.0
    evaluation: dict | None = None
    resources: dict | None = None

    def to_dict(self):
        return {
            "best_config": self.best_config.to_dict() if self.best_config else None,
            "best_value": self.best_value,
            "history": [r.to_dict() for r in self.history],
            "n_trials": self.n_trials,
            "total_cost": self.total_cost,
            "status": self.status,
            "reason": self.reason,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "evaluation": copy.deepcopy(self.evaluation),
            "resources": copy.deepcopy(self.resources),
        }


class IncompleteStudyError(RuntimeError):
    """The ledger is durable, but no valid incumbent meets the study fidelity."""

    def __init__(self, result):
        self.result = result
        super().__init__(
            f"No valid results found at required fidelity: {result.reason}"
        )


class Study:
    """Optimize a scalar objective using a fixed number of new configurations.

    With a scheduler, promoted evaluations are additional entries in the ledger;
    ``budget`` limits new configurations, not total compute. Batch observations
    commit in dispatch order. Pending work can run again after a process crash;
    committed completed work is never dispatched again. Objectives with external
    side effects must therefore use trial identity for their own idempotency.
    """

    def __init__(
        self,
        searcher,
        executor,
        objective_fn,
        budget=None,
        maximize=True,
        study_name=None,
        checkpoint_dir=None,
        store=None,
        event_log=None,
        scheduler=None,
        max_concurrent=None,
        continuation="restart",
        compute_budget_seconds=None,
        declaration=None,
        resource_budget=None,
        architecture_coordinates=(),
    ):
        self._resources = ResourceController(resource_budget) if resource_budget is not None else None
        if self._resources is not None:
            if budget is not None and (type(budget) is not int or budget != resource_budget.configurations):
                raise ValueError('Configuration count differs from resource budget')
            if compute_budget_seconds is not None and (type(compute_budget_seconds) not in (int, float)
                    or compute_budget_seconds != resource_budget.tuning_seconds):
                raise ValueError('Tuning time cap differs from resource budget')
            budget = resource_budget.configurations
            compute_budget_seconds = resource_budget.tuning_seconds
        elif budget is None:
            budget = 100
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise ValueError("budget must be a positive integer")
        if not isinstance(maximize, bool):
            raise ValueError("maximize must be boolean")
        if not hasattr(searcher, "suggest"):
            from hponas.searchers.adapter import LegacySearcherAdapter

            searcher = LegacySearcherAdapter(searcher, maximize=maximize)
        if getattr(searcher, "multi_objective_spec", None) is not None and not getattr(self, "_vector_objectives", False):
            raise ValueError("A multi-objective searcher requires MultiObjectiveStudy")
        if not as_knob_space(searcher.search_space).knobs:
            raise ValueError("Study requires a nonempty search space")
        self.searcher, self.executor, self.objective_fn = (
            searcher,
            executor,
            objective_fn,
        )
        self.budget, self.maximize = budget, maximize
        if hasattr(searcher, "maximize"):
            searcher.maximize = maximize
        self.study_name = study_name or f"study_{uuid.uuid4().hex[:8]}"
        if hasattr(searcher, "validate_study_context"):
            searcher.validate_study_context(self.study_name)
        self.checkpoint_dir = (
            Path(checkpoint_dir) if checkpoint_dir is not None else None
        )
        self.store, self.event_log, self.scheduler = store, event_log, scheduler
        if continuation not in {"restart", "resume"}:
            raise ValueError("continuation must be restart or resume")
        if compute_budget_seconds is not None and (
            isinstance(compute_budget_seconds, bool)
            or not math.isfinite(compute_budget_seconds)
            or compute_budget_seconds <= 0
        ):
            raise ValueError("compute_budget_seconds must be finite and positive")
        self.continuation = continuation
        self.compute_budget_seconds = compute_budget_seconds
        self.max_concurrent = (
            max_concurrent
            if max_concurrent is not None
            else getattr(executor, "num_workers", None)
            or (
                getattr(executor, "max_workers", 1)
                if getattr(executor, "mode", None) == "async"
                else 1
            )
        )
        if (
            not isinstance(self.max_concurrent, int)
            or isinstance(self.max_concurrent, bool)
            or self.max_concurrent < 1
        ):
            raise ValueError("max_concurrent must be a positive integer")
        if scheduler is not None and not all(
            hasattr(scheduler, n)
            for n in ("report", "promote", "state_dict", "load_state_dict")
        ):
            raise TypeError("Scheduler must support reports, promotion and checkpoints")
        if hasattr(self.searcher, "validate_study_controls"):
            self.searcher.validate_study_controls(self.max_concurrent, scheduler)
        self._architecture_coordinates = tuple(architecture_coordinates)
        self._admission = admit(searcher, scheduler=scheduler, workers=self.max_concurrent,
                                declared=declaration is not None, architecture=architecture_coordinates)
        if self._resources is not None:
            resource_budget.validate_study(declaration, getattr(self, '_vector_objectives', False), self.max_concurrent)
            if getattr(executor, 'max_retries', 0) != 0:
                raise ValueError('StudyBudget requires executor max_retries=0; reserve each retry through Study recovery')
            spec = getattr(self, 'spec', None)
            if spec is not None and spec.contract['work_unit'] != resource_budget.work_unit:
                raise ValueError('Vector work unit differs from resource budget')
        self.trials, self.results = {}, {}
        self.n_completed = 0
        self._n_suggested = 0
        self._roots = {}
        self._pending = []
        self._events = []
        self._finished = False
        self._report_cache = {}
        self._live_elapsed = {}
        self._abandoned_elapsed = {}
        self._live_cost = {}
        self._abandoned_cost = {}
        self._cancel_requested = set()
        self._control_lock = threading.RLock()
        self._stop_reason = None
        self._outcome = None
        self._accounting_incomplete = set()
        try:
            self._streaming_objective = (
                "reporter" in inspect.signature(objective_fn).parameters
            )
        except (TypeError, ValueError):
            self._streaming_objective = False
        self._evaluation = (EvaluationController(declaration, maximize=maximize,
                            spec=getattr(self, "spec", None)) if declaration is not None else None)
        if self._evaluation is not None:
            self._evaluation.validate_callable(objective_fn, continuation=continuation)

    def _event(self, kind, trial_id, **data):
        self._events.append({"kind": kind, "trial_id": trial_id, "data": data})

    def _new_trial(self):
        if hasattr(self.searcher, "set_scheduler_context"):
            self.searcher.set_scheduler_context(self.scheduler)
        try:
            config = self.searcher.suggest()
        except PendingSuggestionError:
            # A capped sampler may have selected a branch and consumed random
            # choices without producing a config. Persist that state before
            # yielding; retrying from the previous completed draw biases it.
            self._event("suggest_pending", self.study_name, schema_version=1)
            self.save_checkpoint()
            raise
        except SearchSpaceExhaustedError:
            self._stop_reason = "search_space_exhausted"
            self._event("search_exhausted", self.study_name, schema_version=1)
            return
        except SearchBudgetExhaustedError:
            self._stop_reason = "search_budget_exhausted"
            self._event("search_budget_exhausted", self.study_name, schema_version=1)
            return
        as_knob_space(self.searcher.search_space).validate_config(config.values)
        self._register_suggestion(config)

    def _register_suggestion(self, config):
        tid = f"{self.study_name}_trial_{self._n_suggested}"
        fidelity = (
            self.scheduler.register_trial(tid)
            if self.scheduler is not None and hasattr(self.scheduler, "register_trial")
            else self.scheduler.config.r_min if self.scheduler else 1.0
        )
        trial = Trial(
            config,
            tid,
            seed=(self.searcher.seed or 0) + self._n_suggested,
            fidelity=fidelity,
            root_trial_id=tid,
            continuation=self.continuation,
        )
        self._n_suggested += 1
        self._roots[tid] = tid
        self.trials[tid] = trial
        self.searcher.trials[tid] = config
        if hasattr(self.searcher, "register_trial"):
            self.searcher.register_trial(trial)
        self._pending.append(tid)
        self._event("suggest", tid, config=config.values, seed=self.searcher.seed,
                    fidelity=fidelity)

    def _new_batch(self, count):
        # The entire proposal is registered before any dispatch/checkpoint.
        # An interrupted objective therefore reuses exactly this pending set.
        try:
            configs = self.searcher.suggest_batch(count)
        except PendingSuggestionError:
            self._event('suggest_pending', self.study_name, schema_version=1)
            self.save_checkpoint()
            raise
        except (SearchSpaceExhaustedError, SearchBudgetExhaustedError) as exc:
            self._stop_reason = 'search_space_exhausted' if isinstance(exc, SearchSpaceExhaustedError) else 'search_budget_exhausted'
            self._event(self._stop_reason, self.study_name, schema_version=1)
            return
        if not isinstance(configs, list) or not 1 <= len(configs) <= count:
            raise ValueError('Batch proposal must return one through the requested count')
        for config in configs:
            as_knob_space(self.searcher.search_space).validate_config(config.values)
        for config in configs:
            self._register_suggestion(config)
        self._event('suggest_batch', self.study_name, trial_ids=list(self._pending[-len(configs):]),
                    requested=count, joint=True)

    def _promotions(self):
        if self.scheduler is None:
            return
        if self._reference_scheduler():
            for root in sorted(self._cancel_requested):
                if root not in self.scheduler._terminal:
                    self._event("cancel_request", root, schema_version=1, root=root)
                    self.scheduler.finish(root, "cancelled")
                    self._event(
                        "finish", root, schema_version=1, root=root, status="cancelled"
                    )
        promotions = self.scheduler.promote()
        self._event(
            "promotion_round", self.study_name, promotions=[list(p) for p in promotions]
        )
        for root, fidelity in promotions:
            parent = max(
                (t for t in self.trials.values() if self._roots[t.trial_id] == root),
                key=lambda t: t.fidelity,
            )
            tid = f"{root}_fidelity_{fidelity:g}"
            if tid in self.trials:
                continue
            trial = Trial(
                parent.config,
                tid,
                seed=parent.seed,
                fidelity=fidelity,
                parent_trial_id=parent.trial_id,
                root_trial_id=root,
                continuation=self.continuation,
                resume_from=parent.fidelity if self.continuation == "resume" else 0.0,
                checkpoint=(
                    self.results[parent.trial_id].metadata.get("checkpoint")
                    if self.continuation == "resume"
                    else None
                ),
            )
            self.trials[tid] = trial
            self._roots[tid] = root
            self.searcher.trials[tid] = trial.config
            if hasattr(self.searcher, "register_trial"):
                self.searcher.register_trial(trial)
            self._pending.append(tid)
            self._event(
                "promote",
                tid,
                root=root,
                parent=parent.trial_id,
                config=trial.config.values,
                from_fidelity=parent.fidelity,
                to_fidelity=fidelity,
                continuation=trial.continuation,
                resume_from=trial.resume_from,
                checkpoint=trial.checkpoint,
            )

    def cancel_trial(self, trial_id):
        """Request cooperative cancellation by evaluation or root identity."""
        with self._control_lock:
            if trial_id not in self._roots:
                raise ValueError("Unknown trial identity")
            root = self._roots[trial_id]
            self._cancel_requested.add(root)

    def _reference_scheduler(self):
        return (
            self.scheduler is not None
            and hasattr(self.scheduler, "finish")
            and getattr(self.scheduler.config, "promotion_policy", None)
            != "legacy_bootstrap"
        )

    def _elapsed(self):
        return (
            sum(
                r.metadata.get("execution", {}).get("elapsed_seconds", 0.0)
                for r in self.results.values()
            )
            + sum(self._live_elapsed.values())
            + sum(self._abandoned_elapsed.values())
            + (self._evaluation.uncommitted_elapsed(self.results) if self._evaluation else 0.)
        )

    def _cap_reached(self):
        return (
            self.compute_budget_seconds is not None
            and self._elapsed() >= self.compute_budget_seconds
        )

    def _on_progress(self, report):
        """Run on the study thread so scheduler, SQLite and checkpoint order agree."""
        tid = report.trial_id
        if tid not in self._pending:
            return ReportDecision("cancel", "evaluation_already_finished")
        trial = self.trials[tid]
        root = self._roots[tid]
        if report.schema_version != 1 or report.root_trial_id != root:
            raise ValueError("Progress identity or version differs")
        if not (trial.resume_from < report.step <= trial.fidelity):
            raise ValueError("Progress outside assigned fidelity")
        self._live_elapsed[tid] = report.elapsed_seconds
        self._live_cost[tid] = report.cost
        cache = self._report_cache.setdefault(tid, {})
        cached = cache.get(report.step)
        if cached and cached["value"] != report.value:
            raise ValueError("Conflicting duplicate progress value")
        applied, scheduler_decision = False, None
        if self._cap_reached():
            self._stop_reason = "compute_budget_exhausted"
            decision = ReportDecision("cancel", self._stop_reason)
        elif root in self._cancel_requested:
            self._event("cancel_request", tid, schema_version=1, root=root)
            decision = ReportDecision("cancel", "user_cancellation")
        elif cached:
            decision = ReportDecision(**cached["decision"])
        elif (
            trial.parent_trial_id
            and report.step <= self.trials[trial.parent_trial_id].fidelity
        ):
            # Restarted promotions pay for this prefix without presenting it as
            # new evidence or pausing again at a rung already promoted.
            decision = ReportDecision("continue", "repeated_work")
        else:
            value = -report.value if self.maximize else report.value
            if self.scheduler:
                options = {"is_progress": True} if self._reference_scheduler() else {}
                scheduler_decision = self.scheduler.report(
                    root, report.step, value, **options
                )
                applied = True
            action = scheduler_decision or "continue"
            terminal = getattr(self.scheduler, "_terminal", {}).get(root)
            if (
                action == "stop"
                and report.step == trial.fidelity
                and terminal != "pruned"
            ):
                action = (
                    "continue"  # Full-fidelity training still must return successfully.
                )
            decision = ReportDecision(action)
        cache.setdefault(
            report.step, {"value": report.value, "decision": decision.__dict__}
        )
        self._event(
            "progress",
            tid,
            **{k: v for k, v in report.to_dict().items() if k != "trial_id"},
            root=root,
            normalized_value=-report.value if self.maximize else report.value,
            scheduler_applied=applied,
            scheduler_decision=scheduler_decision,
            control=decision.__dict__,
            compute_budget_seconds=self.compute_budget_seconds,
            total_elapsed_seconds=self._elapsed(),
        )
        self.save_checkpoint()
        return decision

    def _accept(self, result):
        if result.trial_id not in self._pending:
            raise ValueError("Executor returned an unknown or completed trial")
        trial = self.trials[result.trial_id]
        if self._evaluation is not None and trial.root_trial_id in self._cancel_requested and result.status != 'cancelled':
            cancelled = self._evaluation.aggregate(trial, self._evaluation.state['tuning'][trial.trial_id], cancelled=True)
            if 'multi_objective_context' in result.metadata:
                cancelled.metadata['multi_objective_context'] = result.metadata['multi_objective_context']
            result = cancelled
        if result.fidelity != trial.fidelity:
            raise ValueError("Executor changed trial fidelity")
        tid = result.trial_id
        # A stopped checkpoint can be accepted without another dispatch. Its
        # acknowledged prefix is still paid work, even when the cancellation
        # result itself has zero cost. Final and live costs are cumulative for
        # the same attempt; abandoned attempts are additional work.
        result.cost = max(
            result.cost, self._live_cost.pop(tid, 0.0)
        ) + self._abandoned_cost.pop(tid, 0.0)
        execution = result.metadata.setdefault("execution", {})
        execution["elapsed_seconds"] = max(
            execution.get("elapsed_seconds", 0.0), self._live_elapsed.pop(tid, 0.0)
        ) + self._abandoned_elapsed.pop(tid, 0.0)
        if tid in self._accounting_incomplete:
            execution["accounting"] = "lower_bound_after_interruption"
        if self._roots[tid] in self._cancel_requested and result.is_valid():
            result.status = "cancelled"
        if self.scheduler is not None and result.is_valid():
            # Observers can retain an immutable result/event ledger. Finalize
            # this metadata before notifying them so recovery sees the same row.
            result.metadata["training_status"] = (
                "completed"
                if result.fidelity == self.scheduler.config.r_max
                else "paused"
            )
        self.results[result.trial_id] = result
        trial.status, trial.value, trial.cost = (
            result.status,
            result.objective_value,
            result.cost,
        )
        self.searcher.observe(result)
        self.n_completed = len(self.results)
        self._pending.remove(result.trial_id)
        self._event(
            "observe",
            result.trial_id,
            **{k: v for k, v in result.to_dict().items() if k != "trial_id"},
        )
        if self.scheduler is not None and result.is_valid():
            value = self._scheduler_value(result)
            decision = self.scheduler.report(
                self._roots[result.trial_id], result.fidelity, value
            )
            self._event(
                "report",
                result.trial_id,
                root=self._roots[result.trial_id],
                fidelity=result.fidelity,
                value=value,
                decision=decision,
            )
        if self._reference_scheduler():
            root = self._roots[result.trial_id]
            if (
                result.status == "completed"
                and result.fidelity == self.scheduler.config.r_max
            ):
                self.scheduler.finish(root, "completed")
                self._event("finish", tid, schema_version=1, root=root, status="completed")
            elif not result.is_valid():
                terminal = (
                    result.status
                    if result.status in {"pruned", "cancelled"}
                    else "failed"
                )
                self.scheduler.finish(root, terminal)
                self._event("finish", tid, schema_version=1, root=root, status=terminal)
        self.save_checkpoint()

    def _scheduler_value(self, result):
        return -result.objective_value if self.maximize else result.objective_value

    def _execute_batch(self, batch):
        """Pump worker reports while retaining dispatch-order final observations."""
        # Ray's owned service processes must outlive the temporary collector
        # thread. Starting them there can tie their parent-death signal to it.
        if hasattr(self.executor, "prepare"):
            self.executor.prepare()
        channel = Queue()

        def on_report(report):
            reply = Future()
            channel.put((report, reply))
            return reply.result()

        def execute(trial):
            started = time.monotonic()
            result = self.executor.execute(
                trial, self.objective_fn, on_report=on_report
            )
            result.metadata.setdefault("execution", {}).setdefault(
                "elapsed_seconds", time.monotonic() - started
            )
            return result

        for trial in batch:
            tid = trial.trial_id
            if tid in self._live_elapsed:
                # A crashed worker can have performed work since its last
                # acknowledged report. Keep that unknown suffix visible.
                self._accounting_incomplete.add(tid)
            self._abandoned_elapsed[tid] = self._abandoned_elapsed.get(
                tid, 0
            ) + self._live_elapsed.pop(tid, 0)
            self._abandoned_cost[tid] = self._abandoned_cost.get(
                tid, 0
            ) + self._live_cost.pop(tid, 0)
        self.save_checkpoint()
        # All callbacks are marshalled back here, including those from Ray's
        # collectors and from LocalExecutor's timeout subprocesses.
        with ThreadPoolExecutor(max_workers=1) as control:
            if getattr(self.executor, "mode", None) == "async":
                futures = [
                    self.executor.execute_async(
                        t, self.objective_fn, on_report=on_report
                    )
                    for t in batch
                ]
                batched = False
            elif hasattr(self.executor, "execute_batch"):
                futures = [
                    control.submit(
                        self.executor.execute_batch,
                        batch,
                        self.objective_fn,
                        on_report=on_report,
                    )
                ]
                batched = True
            else:
                futures = [control.submit(execute, t) for t in batch]
                batched = False
            try:
                for future in futures:
                    while not future.done():
                        try:
                            report, reply = channel.get(timeout=0.01)
                        except Empty:
                            continue
                        try:
                            with self._control_lock:
                                reply.set_result(self._on_progress(report))
                        except BaseException as exc:
                            reply.set_exception(exc)
                            raise
                    for result in future.result() if batched else [future.result()]:
                        self._accept(result)
            finally:
                # Release cooperative workers even when checkpointing or an
                # objective interrupts the run; never strand a report waiter.
                while any(not f.done() for f in futures):
                    try:
                        _, reply = channel.get(timeout=0.01)
                        reply.set_result(ReportDecision("cancel", "study_interrupted"))
                    except Empty:
                        pass

    def run(self):
        try:
            if self._evaluation is not None and self._evaluation.state["phase"] != "tuning":
                self._evaluation.finish(self)
                return self._build_result()
            while True:
                if self._cap_reached():
                    self._stop_reason = "compute_budget_exhausted"
                if self._resources is not None:
                    self._stop_reason = self._stop_reason or self._resources.refusal('tuning')
                if not self._pending:
                    if not self._stop_reason:
                        self._promotions()
                    while (
                        not self._stop_reason
                        and len(self._pending) < self.max_concurrent
                        and self._n_suggested < self.budget
                    ):
                        slots = min(self.max_concurrent - len(self._pending), self.budget - self._n_suggested)
                        support = getattr(self.searcher, 'support', None)
                        if slots > 1 and support is not None and support.joint_batch:
                            self._new_batch(min(slots, getattr(self.searcher, 'max_batch_size', slots)))
                            break
                        self._new_trial()
                    self.save_checkpoint()
                if not self._pending:
                    self._finished = True
                    self._outcome = (
                        "incomplete"
                        if not self._has_full_fidelity_result()
                        else (self._stop_reason or "completed")
                    )
                    self.save_checkpoint()
                    break
                batch = [
                    self.trials[tid] for tid in self._pending[: self.max_concurrent]
                ]
                if self._stop_reason and self._evaluation is None:
                    for trial in batch:
                        if trial.trial_id in self._live_elapsed:
                            self._accounting_incomplete.add(trial.trial_id)
                        self._accept(
                            Result(
                                trial.trial_id,
                                math.nan,
                                0,
                                trial.fidelity,
                                {"stop_reason": self._stop_reason},
                                "cancelled",
                            )
                        )
                elif self._evaluation is not None:
                    # Persist each fold/seed endpoint before the single aggregate
                    # observation. Final evaluation uses a separate ledger below.
                    for trial in batch:
                        self._accept(self._evaluation.run_group(self, trial, "tuning"))
                elif (
                    self.scheduler is not None
                    or self.compute_budget_seconds is not None
                    or self._streaming_objective
                ):
                    self._execute_batch(batch)
                elif getattr(self.executor, "mode", None) == "async":
                    futures = [
                        self.executor.execute_async(t, self.objective_fn) for t in batch
                    ]
                    for future in futures:
                        self._accept(future.result())
                elif hasattr(self.executor, "execute_batch") and len(batch) > 1:
                    for result in self.executor.execute_batch(batch, self.objective_fn):
                        self._accept(result)
                else:
                    for trial in batch:
                        self._accept(self.executor.execute(trial, self.objective_fn))
            if self._evaluation is not None:
                self._evaluation.finish(self)
            return self._build_result()
        finally:
            self.executor.shutdown()

    def _has_full_fidelity_result(self):
        return self.get_best_so_far() is not None

    def _build_result(self):
        best = self.get_best_so_far()
        evaluation = self.evaluation_report()
        status, reason = self._result_status(evaluation, self._stop_reason)
        outcome = StudyResult(
            self.trials[best.trial_id].config if best else None,
            best.objective_value if best else None,
            list(self.results.values()), self.n_completed,
            sum(r.cost for r in self.results.values()) + evaluation.get("final_cost", 0.), status,
            (self._stop_reason or "no_full_fidelity_result") if best is None else reason,
            self._elapsed() + evaluation.get("final_elapsed_seconds", 0.), evaluation, self.resource_report(),
        )
        if best is None:
            raise IncompleteStudyError(outcome)
        return outcome

    def _result_status(self, evaluation, reason):
        final_outcome = evaluation.get('outcome')
        if final_outcome in {'failed', 'infeasible', 'incomplete'}:
            return 'final_evaluation_' + final_outcome, 'final_evaluation_' + final_outcome
        return self._outcome, reason

    def evaluation_report(self):
        """Final measurements are reported here, never in the searcher's history."""
        return self._evaluation.report() if self._evaluation is not None else legacy_evaluation_report()

    def resource_report(self):
        if self._resources is not None:
            return {**self._resources.report(), 'configurations_proposed': self._n_suggested,
                    'tuning_evaluations': len(self.results), 'admission': copy.deepcopy(self._admission)}
        return {'mode': 'legacy_controls', 'configuration_limit': self.budget,
                'configurations_proposed': self._n_suggested, 'tuning_evaluations': len(self.results),
                'tuning_elapsed_seconds': self._elapsed(), 'tuning_seconds_limit': self.compute_budget_seconds,
                'work_unit': None, 'full_run_equivalents': None, 'final_work_reserved': False,
                'admission': copy.deepcopy(self._admission)}

    def _snapshot_extension(self):
        return {}

    def _snapshot(self):
        state = {
            "schema_version": 5 if self._resources is not None else 4 if self._evaluation is not None else 3,
            "evaluation": copy.deepcopy(self._evaluation.state) if self._evaluation is not None else None,
            "resources": copy.deepcopy(self._resources.state) if self._resources is not None else None,
            "admission": copy.deepcopy(self._admission),
            "study_name": self.study_name,
            "budget": self.budget,
            "maximize": self.maximize,
            "max_concurrent": self.max_concurrent,
            "n_completed": self.n_completed,
            "n_suggested": self._n_suggested,
            "space": as_knob_space(self.searcher.search_space).to_dict(),
            "trials": {k: v.to_dict() for k, v in self.trials.items()},
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "searcher_class": type(self.searcher).__module__
            + "."
            + type(self.searcher).__name__,
            "searcher_state": self.searcher.get_state(),
            "scheduler_class": type(self.scheduler).__module__
            + "."
            + type(self.scheduler).__name__
            if self.scheduler
            else None,
            "scheduler_state": self.scheduler.state_dict() if self.scheduler else None,
            "finished": self._finished,
            "roots": self._roots,
            "pending": self._pending,
            "events": self._events,
            "continuation": self.continuation,
            "compute_budget_seconds": self.compute_budget_seconds,
            "report_cache": self._report_cache,
            "live_elapsed": self._live_elapsed,
            "abandoned_elapsed": self._abandoned_elapsed,
            "live_cost": self._live_cost,
            "abandoned_cost": self._abandoned_cost,
            "cancel_requested": sorted(self._cancel_requested),
            "stop_reason": self._stop_reason,
            "outcome": self._outcome,
            "accounting_incomplete": sorted(self._accounting_incomplete),
        }
        state.update(self._snapshot_extension())
        from hponas.diagnostics import paired_rung_diagnostics
        state['rung_diagnostics'] = paired_rung_diagnostics(state)
        return state

    def save_checkpoint(self):
        state = self._snapshot()
        if self.store is not None:
            self.store.save_study_snapshot(state)
        if self.checkpoint_dir is not None:
            atomic_json(
                self.checkpoint_dir / f"{self.study_name}_checkpoint.json", state
            )
        if self.event_log is not None:
            self.event_log.replace_study_events(self._events)

    def rung_diagnostics(self):
        """Descriptive observed-pair ranks against declared full tuning fidelity."""
        return self._snapshot()['rung_diagnostics']

    def report(self):
        """Complete local workflow report, including protected evaluation outputs."""
        from hponas.reporting import study_report
        return study_report(self._snapshot())

    def export_report(self, destination):
        from hponas.reporting import export_study_report
        return export_study_report(self._snapshot(), destination)

    def load_checkpoint(self, checkpoint_path=None):
        if checkpoint_path is None:
            if self.store is None:
                raise ValueError("A checkpoint path or Store is required")
            state = self.store.load_study_snapshot(self.study_name)
        else:
            state = json.loads(Path(checkpoint_path).read_text())
        if state is None:
            raise ValueError("No study checkpoint found")
        if state.get("schema_version") not in (2, 3, 4, 5):
            raise ValueError(
                "Unsupported checkpoint schema; migrate the legacy checkpoint explicitly"
            )
        if (state.get("evaluation") is not None) != (self._evaluation is not None):
            raise ValueError("Checkpoint declaration/evaluation policy differs; explicit migration required")
        if (state["schema_version"] in (4, 5)) != (state.get("evaluation") is not None):
            raise ValueError("Checkpoint declaration schema differs")
        if ((state.get('resources') is not None) != (self._resources is not None)
                or (state['schema_version'] == 5) != (state.get('resources') is not None)):
            raise ValueError('Checkpoint resource policy differs')
        if (
            state.get("space") is not None
            and state["space"] != as_knob_space(self.searcher.search_space).to_dict()
        ):
            raise ValueError("Checkpoint search space differs")
        actual_class = (
            type(self.searcher).__module__ + "." + type(self.searcher).__name__
        )
        if state.get("searcher_class", actual_class) != actual_class:
            raise ValueError("Checkpoint searcher differs")
        if bool(state.get("scheduler_state")) != (self.scheduler is not None):
            raise ValueError("Checkpoint scheduler differs")
        scheduler_class = (
            type(self.scheduler).__module__ + "." + type(self.scheduler).__name__
            if self.scheduler
            else None
        )
        if state.get("scheduler_class") != scheduler_class:
            raise ValueError("Checkpoint scheduler class differs")
        trials = {
            k: Trial(**{**v, "config": Config(**v["config"])})
            for k, v in state["trials"].items()
        }
        results = {k: Result(**v) for k, v in state["results"].items()}
        if not set(results) <= set(trials):
            raise ValueError("Results without trial configurations")
        budget, maximize = state["budget"], state["maximize"]
        max_concurrent = state.get("max_concurrent", 1)
        for name, value in (("budget", budget), ("max_concurrent", max_concurrent)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Checkpoint {name} must be a positive integer")
        if not isinstance(maximize, bool):
            raise ValueError("Checkpoint maximize must be boolean")
        n_suggested = state.get("n_suggested", len(trials))
        roots = state.get("roots", {k: k for k in trials})
        pending = state.get("pending", [k for k in trials if k not in results])
        if set(pending) & set(results):
            raise ValueError("Completed trials marked pending")
        if len(set(pending)) != len(pending) or set(pending) != set(trials) - set(
            results
        ):
            raise ValueError("Checkpoint pending ledger is inconsistent")
        if set(roots) != set(trials) or not set(roots.values()) <= set(trials):
            raise ValueError("Checkpoint trial roots are inconsistent")
        if (
            not isinstance(n_suggested, int)
            or isinstance(n_suggested, bool)
            or n_suggested != len(set(roots.values()))
            or n_suggested > budget
        ):
            raise ValueError("Checkpoint suggestion count is inconsistent")
        for tid, trial in trials.items():
            if tid != trial.trial_id or (
                tid in results and results[tid].trial_id != tid
            ):
                raise ValueError("Checkpoint trial identities differ")
            as_knob_space(self.searcher.search_space).validate_config(
                trial.config.values
            )
        restored_scheduler = copy.deepcopy(self.scheduler)
        if restored_scheduler:
            restored_scheduler.load_state_dict(state["scheduler_state"])
        continuation = state.get("continuation", "restart")
        if continuation != self.continuation:
            raise ValueError("Checkpoint continuation policy differs")
        compute_budget = state.get("compute_budget_seconds")
        if compute_budget is not None and (
            isinstance(compute_budget, bool)
            or not math.isfinite(compute_budget)
            or compute_budget <= 0
        ):
            raise ValueError("Invalid checkpoint compute budget")
        for field in (
            "live_elapsed",
            "abandoned_elapsed",
            "live_cost",
            "abandoned_cost",
        ):
            ledger = state.get(field, {})
            if not set(ledger) <= set(pending) or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                or v < 0
                for v in ledger.values()
            ):
                raise ValueError(f"Invalid checkpoint {field} ledger")
        report_cache = {
            tid: {float(k): v for k, v in entries.items()}
            for tid, entries in state.get("report_cache", {}).items()
        }
        if not set(report_cache) <= set(trials):
            raise ValueError("Progress cache without trial")
        for tid, entries in report_cache.items():
            for step, entry in entries.items():
                if (
                    not math.isfinite(step)
                    or not 0 < step <= trials[tid].fidelity
                    or not math.isfinite(entry["value"])
                ):
                    raise ValueError("Invalid checkpoint progress report")
                ReportDecision(**entry["decision"])
        for tid, trial in trials.items():
            if trial.root_trial_id is None and state["schema_version"] == 2:
                trial.root_trial_id = roots[tid]
            if trial.root_trial_id not in (None, roots[tid]):
                raise ValueError("Checkpoint progress root differs")
            if trial.continuation != continuation:
                raise ValueError("Checkpoint trial continuation differs")
            if (
                not math.isfinite(trial.resume_from)
                or not 0 <= trial.resume_from < trial.fidelity
            ):
                raise ValueError("Invalid checkpoint resume fidelity")
            if continuation == "restart" and (
                trial.resume_from != 0 or trial.checkpoint is not None
            ):
                raise ValueError("Restart checkpoint contains resume state")
        restored_searcher = copy.deepcopy(self.searcher)
        restored_searcher.set_state(state["searcher_state"])
        if hasattr(restored_searcher, "maximize"):
            restored_searcher.maximize = maximize
        if hasattr(restored_searcher, "validate_study_context"):
            restored_searcher.validate_study_context(state["study_name"])
        if hasattr(restored_searcher, "validate_study_controls"):
            restored_searcher.validate_study_controls(max_concurrent, restored_scheduler)
        admission = admit(restored_searcher, scheduler=restored_scheduler, workers=max_concurrent,
                          declared=self._evaluation is not None, architecture=self._architecture_coordinates)
        if state.get('admission', admission) != admission:
            raise ValueError('Checkpoint capability or architecture declaration differs')
        self._validate_checkpoint_extension(state, restored_searcher)
        if hasattr(restored_searcher, "validate_study_snapshot"):
            restored_searcher.validate_study_snapshot(state)
        if restored_scheduler is not None and hasattr(restored_scheduler, "validate_study_snapshot"):
            restored_scheduler.validate_study_snapshot(state)
        restored_evaluation = copy.deepcopy(self._evaluation)
        if restored_evaluation is not None:
            if maximize != self.maximize:
                raise ValueError("Checkpoint evaluation direction differs")
            endpoint = (getattr(restored_scheduler, "current_max_fidelity", restored_scheduler.config.r_max)
                        if restored_scheduler else 1.)
            restored_evaluation.restore(state["evaluation"], trials, results,
                finished=state.get("finished", False), maximize=maximize, endpoint=endpoint,
                cancelled=set(state.get('cancel_requested', [])))
            if json.dumps([r.to_dict() for r in restored_searcher.history], sort_keys=True) != json.dumps(list(state['results'].values()), sort_keys=True):
                raise ValueError('Declared searcher and Study observation ledgers differ')
            for tid, result in results.items():
                trial = trials[tid]
                if (any(getattr(result, k) != getattr(trial, k) for k in ('status', 'cost', 'fidelity'))
                        or not (result.objective_value == trial.value or math.isnan(result.objective_value) and math.isnan(trial.value))):
                    raise ValueError('Declared result and trial accounting differ')
        restored_resources = copy.deepcopy(self._resources)
        if restored_resources is not None:
            resource_budget = restored_resources.budget
            if budget != resource_budget.configurations or compute_budget != resource_budget.tuning_seconds:
                raise ValueError('Checkpoint controls differ from resource contract')
            resource_budget.validate_study(restored_evaluation.declaration, getattr(self, '_vector_objectives', False), max_concurrent)
            restored_resources.restore(state['resources'], restored_evaluation, getattr(self, 'spec', None))
        # Validate the ledger and controls before replacing a live study. A
        # rejected checkpoint must not leave partially restored trial state.
        from hponas.diagnostics import read_rung_diagnostics
        read_rung_diagnostics(state)
        self.trials, self.results = trials, results
        self.study_name, self.budget, self.maximize = (
            state["study_name"],
            budget,
            maximize,
        )
        self.max_concurrent = max_concurrent
        self.n_completed, self._n_suggested = len(results), n_suggested
        self._roots, self._pending = roots, pending
        self._finished = state.get("finished", False)
        self._events = state.get("events", [])
        self.searcher.__dict__.update(restored_searcher.__dict__)
        if hasattr(self.searcher, "maximize"):
            self.searcher.maximize = self.maximize
        if self.scheduler:
            self.scheduler.__dict__.update(restored_scheduler.__dict__)
        self.compute_budget_seconds = compute_budget
        self._report_cache = report_cache
        self._live_elapsed = state.get("live_elapsed", {})
        self._abandoned_elapsed = state.get("abandoned_elapsed", {})
        self._live_cost = state.get("live_cost", {})
        self._abandoned_cost = state.get("abandoned_cost", {})
        self._cancel_requested = set(state.get("cancel_requested", []))
        self._stop_reason = state.get("stop_reason")
        self._outcome = state.get("outcome")
        self._accounting_incomplete = set(state.get("accounting_incomplete", []))
        self._evaluation = restored_evaluation
        self._resources = restored_resources
        self._admission = admission
        if self.event_log:
            self.event_log.replace_study_events(self._events)

    def _validate_checkpoint_extension(self, state, restored_searcher):
        if state.get("multi_objective") is not None:
            raise ValueError("A vector checkpoint requires MultiObjectiveStudy")

    def get_history(self):
        return list(self.results.values())

    def get_best_so_far(self):
        valid = [
            r for r in self.results.values() if r.is_valid() and r.status == "completed"
        ]
        if self.scheduler:
            target_fidelity = getattr(
                self.scheduler, "current_max_fidelity", self.scheduler.config.r_max
            )
            valid = [r for r in valid if r.fidelity == target_fidelity]
        if not valid:
            return None
        return (max if self.maximize else min)(valid, key=lambda r: r.objective_value)
