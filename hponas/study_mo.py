"""Multi-objective execution on the durable Study evaluation ledger."""
from copy import deepcopy
from dataclasses import dataclass
import inspect
import json
import math

from hponas.multi_objective import ObjectiveSpec
from hponas.study import Study, IncompleteStudyError
from hponas.types import Result


@dataclass
class MultiObjectiveStudyResult:
    front: list
    history: list
    metrics: dict
    n_trials: int
    total_cost: float
    total_elapsed_seconds: float
    status: str
    reason: str | None
    evaluation: dict | None = None
    resources: dict | None = None

    def to_dict(self):
        return {"front": deepcopy(self.front), "history": [r.to_dict() for r in self.history],
                "metrics": deepcopy(self.metrics), "n_trials": self.n_trials, "total_cost": self.total_cost,
                "total_elapsed_seconds": self.total_elapsed_seconds, "status": self.status, "reason": self.reason,
                "evaluation": deepcopy(self.evaluation), 'resources': deepcopy(self.resources)}


class _VectorObjective:
    def __init__(self, fn, spec):
        self.fn, self.spec = fn, spec
        self.parameters = inspect.signature(fn).parameters
        if "reporter" in self.parameters:
            raise ValueError("Multi-objective execution currently supports endpoint reports only")

    def __call__(self, config, fidelity=1., seed=None, trial_id=None, root_trial_id=None,
                 checkpoint=None, resume_from=0., evaluation=None):
        context = dict(fidelity=fidelity, seed=seed, trial_id=trial_id, root_trial_id=root_trial_id,
                       checkpoint=checkpoint, resume_from=resume_from, evaluation=evaluation)
        if resume_from > 0 and not {"checkpoint", "resume_from"} <= set(self.parameters):
            raise ValueError("Resumed vector objective must accept checkpoint and resume_from")
        row = self.fn(config, **{k: v for k, v in context.items() if k in self.parameters})
        if not isinstance(row, dict) or not {"objectives", "constraints", "work"} <= set(row):
            raise ValueError("Vector objective must declare objectives, constraints and actual work")
        if set(row) - {"objectives", "constraints", "work", "status", "cost", "checkpoint", "artifacts"}:
            raise ValueError("Unknown vector objective output fields")
        observation = self.spec.observation(**{k: row[k] for k in ["objectives", "constraints", "work"]},
                                            status=row.get("status", "completed"))
        return {"value": 0. if observation["status"] == "completed" else math.nan,
                "metadata": {"multi_objective": observation},
                **{k: row[k] for k in ["cost", "checkpoint", "artifacts"] if k in row}}


class MultiObjectiveStudy(Study):
    """Return a Pareto front under a frozen contract, with no arbitrary best scalar.

    Uses the normal executor, Store, pending-trial and checkpoint mechanisms.
    The internal scalar carrier is always zero and is never an optimization
    target. Searchers consume the named vector and constraints from metadata.
    """

    _vector_objectives = True

    def __init__(self, searcher, executor, objective_fn, *, objectives, constraints=None, work_unit="integer_operations", **kwargs):
        self.spec = ObjectiveSpec(objectives, constraints=constraints, work_unit=work_unit)
        other = getattr(searcher, "multi_objective_spec", None)
        if other is None or other.contract != self.spec.contract:
            raise ValueError("Searcher and Study require the same frozen objective contract")
        if "maximize" in kwargs:
            raise ValueError("Directions belong to each declared objective")
        scheduler = kwargs.get("scheduler")
        if scheduler is not None and getattr(scheduler, "metric_identity", None) != self.spec.identity:
            raise ValueError("Multi-objective scheduler must bind the same frozen metric")
        endpoint = scheduler.config.r_max if scheduler else 1.
        if getattr(searcher, "model_fidelity", endpoint) != endpoint:
            raise ValueError("Searcher model fidelity must match the full study endpoint")
        super().__init__(searcher, executor, _VectorObjective(objective_fn, self.spec), maximize=False, **kwargs)

    def _accept(self, result):
        self.spec.validate_result(result)
        trial = self.trials[result.trial_id]
        result.metadata["multi_objective_context"] = {"root_trial_id": trial.root_trial_id,
                                                      "endpoint_fidelity": self.scheduler.config.r_max if self.scheduler else 1.}
        super()._accept(result)

    def _scheduler_value(self, result):
        return self.spec.validate_result(result)

    def summary(self, budget=None):
        endpoint = self.scheduler.config.r_max if self.scheduler else 1.
        return self.spec.summarize(list(self.results.values()), endpoint_fidelity=endpoint, budget=budget)

    def get_pareto_front(self):
        return [{"trial_id": tid, "config": deepcopy(self.trials[tid].config.values),
                 **deepcopy(self.results[tid].metadata["multi_objective"])}
                for tid in self.summary()["front_trial_ids"]]

    def get_best_so_far(self):
        raise ValueError("Multi-objective studies expose get_pareto_front(), not a scalar best")

    def _has_full_fidelity_result(self):
        return bool(self.summary()["front_trial_ids"])

    def _build_result(self):
        if hasattr(self.searcher, "finalize_pending"):
            self.searcher.finalize_pending()
            self.save_checkpoint()
        front = self.get_pareto_front()
        evaluation = self.evaluation_report()
        status, reason = self._result_status(evaluation, self._stop_reason or (None if front else 'no_feasible_full_fidelity_result'))
        outcome = MultiObjectiveStudyResult(front, list(self.results.values()), self.summary(),
                                           self.n_completed, sum(r.cost for r in self.results.values()) + evaluation.get("final_cost", 0.),
                                           self._elapsed() + evaluation.get("final_elapsed_seconds", 0.), status, reason, evaluation, self.resource_report())
        if not front:
            raise IncompleteStudyError(outcome)
        return outcome

    def _snapshot_extension(self):
        return {"multi_objective": {"identity": self.spec.identity, "contract": self.spec.contract}}

    def _validate_checkpoint_extension(self, state, restored_searcher):
        if state.get("multi_objective") != {"identity": self.spec.identity, "contract": self.spec.contract}:
            raise ValueError("Checkpoint objective contract differs")
        if state["maximize"] is not False:
            raise ValueError("Vector carrier direction differs")
        for row in state["results"].values():
            self.spec.validate_result(Result(**row))
            trial = state["trials"][row["trial_id"]]
            if any(row[k] != trial[k] for k in ["status", "cost", "fidelity"]):
                raise ValueError("Vector result and trial accounting differ")
            endpoint = self.scheduler.config.r_max if self.scheduler else 1.
            expected = {"root_trial_id": state["trials"][row["trial_id"]]["root_trial_id"], "endpoint_fidelity": endpoint}
            if row["metadata"].get("multi_objective_context") != expected:
                raise ValueError("Vector result lineage or endpoint differs")
        if json.dumps([r.to_dict() for r in restored_searcher.history], sort_keys=True) != json.dumps(list(state["results"].values()), sort_keys=True):
            raise ValueError("Vector searcher and Study observation ledgers differ")

    def load_checkpoint(self, checkpoint_path=None):
        super().load_checkpoint(checkpoint_path)
        # An endpoint-only snapshot cannot prove whether pending work began
        # before interruption. Preserve that uncertainty even after a retry.
        if self._evaluation is None:
            self._accounting_incomplete.update(self._pending)
