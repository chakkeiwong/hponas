"""Declared evaluation roles and a durable ledger isolated from search feedback.

Callers own their data and fitting code. The package checks the declared split
identities and execution transitions; it cannot inspect undeclared data access.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import hashlib
import inspect
import json
import math
import time
from statistics import fmean, stdev

from hponas.types import Config, Result, Trial


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Nonempty declared identity required")


def _nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _ids(values):
    if not isinstance(values, (tuple, list)):
        raise ValueError("An explicit sequence of identities is required")
    for value in values:
        _name(value)
    if len(values) != len(set(values)):
        raise ValueError("Repeated split identity")
    return tuple(values)


@dataclass(frozen=True)
class EvaluationFold:
    """Named data roles; times include label/information availability.

    ``grouped`` requires disjoint entities. ``temporal`` requires a strictly
    later score time plus a declared nonnegative information gap. Repeated
    entities in temporal forecasting are allowed; future information is not.
    """

    name: str
    train_ids: tuple[str, ...]
    score_ids: tuple[str, ...]
    mode: str = "rows"
    train_groups: tuple[str, ...] = ()
    score_groups: tuple[str, ...] = ()
    train_until: float | None = None
    score_from: float | None = None
    score_until: float | None = None
    gap: float = 0.0

    def __post_init__(self):
        _name(self.name)
        for key in ("train_ids", "score_ids", "train_groups", "score_groups"):
            object.__setattr__(self, key, _ids(getattr(self, key)))
        if not self.train_ids or not self.score_ids or set(self.train_ids) & set(self.score_ids):
            raise ValueError("Training and score identities must be nonempty and disjoint")
        if self.mode not in {"rows", "grouped", "temporal", "known_answer"}:
            raise ValueError("Unknown evaluation split mode")
        if self.mode == "grouped" and (not self.train_groups or not self.score_groups
                or set(self.train_groups) & set(self.score_groups)):
            raise ValueError("Grouped evaluation requires disjoint declared entities")
        if type(self.gap) not in (int, float) or not math.isfinite(self.gap) or self.gap < 0:
            raise ValueError("Information gap must be finite and nonnegative")
        if self.mode == "temporal":
            if any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in (self.train_until, self.score_from, self.score_until)):
                raise ValueError("Temporal evaluation requires finite information times")
            if self.score_from <= self.train_until + self.gap:
                raise ValueError("Temporal score must follow all training information and gap")
            if self.score_until < self.score_from:
                raise ValueError("Score information end cannot precede score start")
        elif any(v is not None for v in (self.train_until, self.score_from, self.score_until)) or self.gap != 0:
            raise ValueError("Time bounds require temporal split mode")


@dataclass(frozen=True)
class EvaluationObjective:
    name: str
    direction: str
    unit: str

    def __post_init__(self):
        _name(self.name)
        _name(self.unit)
        if self.direction not in {"min", "max"}:
            raise ValueError("Objective direction must be min or max")


@dataclass(frozen=True)
class StudyDeclaration:
    """Versioned scientific identities and a fixed mean/complete-case protocol.

    Defaults provide repetitions, not a statistical precision guarantee. Any
    failed repetition fails its candidate; it is never silently dropped. Final
    roles and seeds are disjoint from all tuning exposures. Each fold fits only
    its declared training data, including preprocessing (caller trust boundary).
    """

    objective_id: str
    model_id: str
    data_id: str
    protocol_id: str
    objectives: tuple[EvaluationObjective, ...]
    tuning_folds: tuple[EvaluationFold, ...]
    final_folds: tuple[EvaluationFold, ...]
    tuning_seeds: tuple[int, ...] = (0, 1)
    final_seeds: tuple[int, ...] = (1000, 1001)
    opt_out_reason: str | None = None
    streaming_steps: tuple[float, ...] = ()

    def __post_init__(self):
        for key in ("objective_id", "model_id", "data_id", "protocol_id"):
            _name(getattr(self, key))
        if (not isinstance(self.streaming_steps, (tuple, list))
                or any(type(s) not in (int, float) or not math.isfinite(s) or s <= 0 for s in self.streaming_steps)
                or list(self.streaming_steps) != sorted(set(self.streaming_steps))):
            raise ValueError('Streaming barriers must be finite, positive and strictly increasing')
        object.__setattr__(self, 'streaming_steps', tuple(self.streaming_steps))
        for key, cls in (("objectives", EvaluationObjective), ("tuning_folds", EvaluationFold),
                         ("final_folds", EvaluationFold)):
            values = getattr(self, key)
            if not isinstance(values, (tuple, list)) or any(not isinstance(v, cls) for v in values):
                raise ValueError("Typed objective/fold declarations required")
            object.__setattr__(self, key, tuple(values))
        if not self.objectives or not self.tuning_folds:
            raise ValueError("Objectives and tuning folds are required")
        if len({o.name for o in self.objectives}) != len(self.objectives):
            raise ValueError("Objective names must be unique")
        folds = self.tuning_folds + self.final_folds
        if len({f.name for f in folds}) != len(folds) or len({f.mode for f in folds}) != 1:
            raise ValueError("Folds require unique names and one evaluation mode")
        for key in ("tuning_seeds", "final_seeds"):
            seeds = getattr(self, key)
            if (not isinstance(seeds, (tuple, list)) or any(type(s) is not int or s < 0 for s in seeds)
                    or len(seeds) != len(set(seeds))):
                raise ValueError("Seeds must be unique nonnegative integers")
            object.__setattr__(self, key, tuple(seeds))
        if not self.tuning_seeds or set(self.tuning_seeds) & set(self.final_seeds):
            raise ValueError("Tuning seeds required and final seeds must be disjoint")
        if self.opt_out_reason is None:
            if not self.final_seeds or not self.final_folds:
                raise ValueError("Final evaluation requires folds and seeds, or an explicit opt-out")
        else:
            _name(self.opt_out_reason)
            if self.final_seeds or self.final_folds:
                raise ValueError("An opt-out cannot claim a final evaluation")
        exposed = {i for f in self.tuning_folds for i in f.train_ids + f.score_ids}
        exposed_groups = {i for f in self.tuning_folds for i in f.train_groups + f.score_groups}
        for fold in self.final_folds:
            if exposed.intersection(fold.score_ids):
                raise ValueError("Final score identities were exposed during tuning")
            if fold.mode == "grouped" and exposed_groups.intersection(fold.score_groups):
                raise ValueError("Final score entities were exposed during tuning")
            if fold.mode == "temporal" and any(fold.score_from <= f.score_until + fold.gap for f in self.tuning_folds):
                raise ValueError("Final temporal evaluation must follow tuning scores")
        final_ids = {i for f in self.final_folds for i in f.score_ids}
        if any(final_ids.intersection(f.train_ids) for f in self.final_folds):
            raise ValueError("Final scoring data cannot train another final fold")
        if folds[0].mode == 'grouped':
            final_groups = {i for f in self.final_folds for i in f.score_groups}
            if any(final_groups.intersection(f.train_groups) for f in self.final_folds):
                raise ValueError("Final scoring entities cannot train another final fold")

    @property
    def contract(self):
        declared = asdict(self)
        if not self.streaming_steps:
            declared.pop('streaming_steps')  # Preserve endpoint declaration identities.
        return json.loads(json.dumps({"version": 2 if self.streaming_steps else 1, **declared, "aggregation": "equal_fold_seed_mean",
            "failure_policy": "fail_candidate", "constraint_policy": "all_repetitions",
            "preprocessing": "fit_training_only", "refit": "fit_per_declared_fold",
            "selection": "scalar_best" if len(self.objectives) == 1 else "feasible_pareto_front"}))

    @property
    def identity(self):
        return _identity(self.contract)

    @classmethod
    def from_contract(cls, contract):
        """Reconstruct typed declarations without accepting altered policy tags."""
        values = {field.name:contract[field.name] for field in fields(cls) if field.name in contract}
        for key, kind in (('objectives',EvaluationObjective),('tuning_folds',EvaluationFold),
                          ('final_folds',EvaluationFold)):
            values[key] = tuple(kind(**row) for row in values[key])
        declaration = cls(**values)
        if declaration.contract != contract:
            raise ValueError('Unsupported evaluation declaration policy or version')
        return declaration


@dataclass(frozen=True)
class EvaluationContext:
    role: str
    fold: EvaluationFold
    declaration_identity: str
    work_limit: float | None = None
    work_unit: str | None = None


class _RoleObjective:
    def __init__(self, fn, context):
        self.fn, self.context = fn, context
        self.parameters = inspect.signature(fn).parameters

    def __call__(self, config, fidelity=1., seed=None, trial_id=None, root_trial_id=None,
                 checkpoint=None, resume_from=0.):
        values = dict(fidelity=fidelity, seed=seed, trial_id=trial_id, root_trial_id=root_trial_id,
                      checkpoint=checkpoint, resume_from=resume_from, evaluation=self.context)
        return self.fn(config, **{k: v for k, v in values.items() if k in self.parameters})


class EvaluationController:
    def __init__(self, declaration, *, maximize, spec=None):
        if not isinstance(declaration, StudyDeclaration):
            raise TypeError("declaration must be a StudyDeclaration")
        self.declaration, self.spec = declaration, spec
        expected = ([(o['name'], o['direction']) for o in spec.contract['objectives']] if spec else
                    [(declaration.objectives[0].name, 'max' if maximize else 'min')])
        if [(o.name, o.direction) for o in declaration.objectives] != expected:
            raise ValueError("Study and evaluation objective directions/names differ")
        self.state = {'version': 1, 'identity': declaration.identity, 'contract': declaration.contract,
                      'phase': 'tuning', 'tuning': {}, 'final': {}, 'selection': [],
                      'inflight': None, 'uncertain': []}

    def validate_callable(self, fn, *, continuation='restart'):
        original = getattr(fn, 'fn', fn) if self.spec is not None else fn
        parameters = inspect.signature(original).parameters
        if ('evaluation' not in parameters
                or parameters['evaluation'].kind == inspect.Parameter.POSITIONAL_ONLY):
            raise ValueError("Declared objectives must accept an explicit evaluation context")
        if ('reporter' in parameters) != bool(self.declaration.streaming_steps):
            raise ValueError('Declared streaming requires a reporter and explicit streaming_steps barriers')
        if ('seed' not in parameters or parameters['seed'].kind == inspect.Parameter.POSITIONAL_ONLY):
            raise ValueError("Declared objectives must accept the assigned seed explicitly")
        if (continuation == 'resume' or self.declaration.streaming_steps) and any(k not in parameters or parameters[k].kind == inspect.Parameter.POSITIONAL_ONLY
                                            for k in ('checkpoint', 'resume_from')):
            raise ValueError("Resumed declared objectives require checkpoint and resume_from")

    def tasks(self, trial, role):
        folds = self.declaration.tuning_folds if role == 'tuning' else self.declaration.final_folds
        seeds = self.declaration.tuning_seeds if role == 'tuning' else self.declaration.final_seeds
        return [(fold, seed, f'{trial.trial_id}_{role}_{i}') for i, (fold, seed) in
                enumerate((fold, seed) for fold in folds for seed in seeds)]

    def aggregate(self, trial, rows, *, cancelled=False, role='tuning'):
        results = [Result(**row['result']) for row in rows]
        cancelled = cancelled or any(r.status == 'cancelled' for r in results)
        valid = not cancelled and len(results) == len(self.tasks(trial, role)) and all(r.status == 'completed' and r.is_valid() for r in results)
        metadata = {'evaluation': {'identity': self.declaration.identity, 'role': role,
                                  'records': deepcopy(rows), 'aggregation': 'equal_fold_seed_mean'},
                    'execution': {'elapsed_seconds': math.fsum(r.metadata.get('execution', {}).get('elapsed_seconds', 0.) for r in results),
                                  'accounting': 'lower_bound_after_interruption' if any(r.trial_id in self.state['uncertain'] for r in results) else 'measured'}}
        if self.spec:
            vectors = [self.spec.validate_result(r) for r in results]
            valid = valid and all(v and v['status'] == 'completed' for v in vectors)
            if all(v is not None for v in vectors):
                metadata['multi_objective'] = self.spec.observation(
                    objectives={k: fmean(v['objectives'][k] for v in vectors) for k in self.spec.names} if valid else None,
                    constraints={k: max(v['constraints'][k] for v in vectors) for k in self.spec.contract['constraints']} if valid else None,
                    work=sum(v['work'] for v in vectors), status='completed' if valid else 'failed')
            value = 0. if valid else math.nan
        else:
            value = fmean(r.objective_value for r in results) if valid else math.nan
        metadata['artifacts'] = {f'{r.trial_id}:{k}': v for r in results
                                 for k, v in r.metadata.get('artifacts', {}).items()}
        checkpoints = {str(i): r.metadata.get('checkpoint') for i, r in enumerate(results)}
        if valid and all(v is not None for v in checkpoints.values()):
            metadata['checkpoint'] = checkpoints
        pruned = any(r.status == 'pruned' for r in results)
        return Result(trial.trial_id, value, math.fsum(r.cost for r in results), trial.fidelity,
                      metadata, 'completed' if valid else 'cancelled' if cancelled else 'pruned' if pruned else 'failed')

    def validate_record(self, result, tid, fidelity):
        execution = result.metadata.get('execution', {})
        if (result.trial_id != tid or type(result.fidelity) not in (int, float) or result.fidelity != fidelity
                or not _nonnegative(result.cost) or not _nonnegative(execution.get('elapsed_seconds'))
                or execution.get('accounting') not in {'measured', 'not_dispatched', 'lower_bound_after_interruption'}
                or result.status not in ({'completed', 'failed', 'timeout', 'nan', 'inf', 'cancelled'}
                                        | ({'pruned'} if self.declaration.streaming_steps else set()))
                or (result.status == 'completed' and not result.is_valid())):
            raise ValueError("Invalid repetition result identity, status or accounting")
        if execution['accounting'] == 'not_dispatched' and (
                result.status not in ({'cancelled', 'failed', 'pruned'} if self.declaration.streaming_steps else {'cancelled'})
                or result.cost != 0 or execution['elapsed_seconds'] != 0):
            raise ValueError("Undispatched repetition cannot claim work")
        if self.spec:
            self.spec.validate_result(result)

    def run_group(self, study, trial, role):
        rows = self.state[role].setdefault(trial.trial_id, [])
        for i, (fold, seed, tid) in enumerate(self.tasks(trial, role)):
            if i < len(rows):
                continue
            if self.state['inflight'] is not None:
                old = self.state['inflight']['trial_id']
                if old not in self.state['uncertain']:
                    self.state['uncertain'].append(old)
            if study._resources is not None:
                study._resources.abandon_inflight()
            self.state['inflight'] = None
            checkpoint = None
            if role == 'tuning' and trial.resume_from > 0:
                previous = self.state['tuning'].get(trial.parent_trial_id, [])
                if len(previous) <= i:
                    raise ValueError("Missing repetition checkpoint for promotion")
                checkpoint = previous[i]['result']['metadata'].get('checkpoint')
                if checkpoint is None:
                    raise ValueError("Promotion requires every repetition's own checkpoint")
            child = Trial(Config(deepcopy(trial.config.values)), tid, seed=seed, fidelity=trial.fidelity,
                          root_trial_id=tid, continuation=trial.continuation if role == 'tuning' else 'restart',
                          resume_from=trial.resume_from if role == 'tuning' else 0., checkpoint=checkpoint)
            cancelled = role == 'tuning' and trial.root_trial_id in study._cancel_requested
            refusal = study._resources.refusal(role) if study._resources is not None else None
            if role == 'tuning':
                refusal = ('cancel_requested' if cancelled else study._stop_reason or refusal
                           or ('compute_budget_exhausted' if study._cap_reached() else None))
            if refusal:
                if role == 'tuning' and not cancelled:
                    study._stop_reason = study._stop_reason or refusal
                result = Result(tid, math.nan, 0., trial.fidelity,
                    {'stop_reason': refusal,
                     'execution': {'elapsed_seconds': 0., 'accounting': 'not_dispatched'}}, 'cancelled')
            else:
                self.state['inflight'] = {'role': role, 'parent': trial.trial_id, 'index': i, 'trial_id': tid}
                resources = study._resources
                if resources is not None:
                    resources.begin(tid, role)
                study.save_checkpoint()
                fn = _RoleObjective(study.objective_fn, EvaluationContext(role, fold, self.declaration.identity,
                    resources.budget.max_work_per_call if resources else None, resources.budget.work_unit if resources else None))
                started = time.monotonic()
                result = (study.executor.execute_async(child, fn).result() if getattr(study.executor, 'mode', None) == 'async'
                          else study.executor.execute(child, fn))
                # Ray's controller may return without a worker execution record
                # after transport loss. Retain elapsed driver time and unknown
                # work explicitly instead of losing this failed repetition.
                if 'attempts' in result.metadata:
                    execution = result.metadata.setdefault('execution', {})
                    missing = 'elapsed_seconds' not in execution
                    execution['elapsed_seconds'] = max(execution.get('elapsed_seconds', 0.), time.monotonic()-started)
                    execution['duration_scope'] = 'endpoint_dispatch_including_transport'
                    if missing or result.metadata['attempts'] > 1:
                        if tid not in self.state['uncertain']:
                            self.state['uncertain'].append(tid)
                        execution['accounting'] = 'lower_bound_after_interruption'
                self.validate_record(result, tid, trial.fidelity)
                if resources is not None:
                    resources.complete(result, self.spec)
            self.validate_record(result, tid, trial.fidelity)
            if tid in self.state['uncertain'] and not refusal:
                result.metadata.setdefault('execution', {})['accounting'] = 'lower_bound_after_interruption'
            rows.append({'fold': fold.name, 'seed': seed, 'result': deepcopy(result.to_dict())})
            self.state['inflight'] = None
            study.save_checkpoint()
        if role == 'tuning':
            return self.aggregate(trial, rows, cancelled=trial.root_trial_id in study._cancel_requested)
        return None

    def uncommitted_elapsed(self, committed):
        return math.fsum(row['result']['metadata'].get('execution', {}).get('elapsed_seconds', 0.)
                         for tid, rows in self.state['tuning'].items() if tid not in committed for row in rows)

    def resource_records(self):
        return {row['result']['trial_id']: (role, row['result']) for role in ('tuning', 'final')
                for rows in self.state[role].values() for row in rows}

    def resource_role(self, tid):
        record = self.resource_records().get(tid)
        return record[0] if record is not None else None

    def finish(self, study):
        if self.state['phase'] == 'tuning':
            if self.spec:
                selection = [row['trial_id'] for row in study.get_pareto_front()]
            else:
                best = study.get_best_so_far()
                selection = [best.trial_id] if best else []
            self.state['selection'] = selection
            self.state['phase'] = 'selection_frozen'
            study.save_checkpoint()
        if self.state['phase'] == 'selection_frozen':
            self.state['phase'] = 'opted_out' if self.declaration.opt_out_reason else 'final_evaluation'
            study.save_checkpoint()
        if self.state['phase'] == 'final_evaluation':
            for tid in self.state['selection']:
                self.run_group(study, study.trials[tid], 'final')
            self.state['phase'] = 'reported'
            study.save_checkpoint()

    def outcome(self):
        return evaluation_outcome(self.state)

    def _summaries(self, role, trial_ids, *, include_records=False):
        summaries = []
        for tid in trial_ids:
            rows = self.state[role].get(tid, [])
            results = [Result(**row['result']) for row in rows]
            expected = len(getattr(self.declaration, role+'_folds')) * len(getattr(self.declaration, role+'_seeds'))
            complete = len(results) == expected and expected > 0
            valid = complete and all(r.is_valid() and r.status == 'completed' for r in results)
            values = {}
            for objective in self.declaration.objectives:
                raw = ([r.metadata['multi_objective']['objectives'][objective.name] for r in results] if self.spec and valid else
                       [r.objective_value for r in results] if valid else [])
                values[objective.name] = {'mean': fmean(raw) if raw else None,
                    'sample_std': stdev(raw) if len(raw) > 1 else None, 'n': len(raw)}
            summaries.append({'trial_id': tid, 'status': 'completed' if valid else 'failed' if complete else 'incomplete',
                              'expected_repetitions': expected, 'recorded_repetitions': len(rows),
                              'objectives': values,
                              'feasible': (all(r.metadata['multi_objective']['feasible'] for r in results)
                                           if self.spec and valid else bool(valid))})
            if include_records:
                summaries[-1]['records'] = deepcopy(rows)
        return summaries

    def report(self):
        # Derive both projections from raw records; reports cannot change the
        # saved aggregation, selection, or searcher feedback on recovery.
        tuning = self._summaries('tuning', self.state['tuning'])
        final = self._summaries('final', self.state['selection'], include_records=True)
        final_rows = [r['result'] for rows in self.state['final'].values() for r in rows]
        return {'status': self.state['phase'], 'outcome': self.outcome(), 'identity': self.declaration.identity,
                'contract': self.declaration.contract, 'selection': list(self.state['selection']),
                'tuning': tuning, 'final': final, 'opt_out_reason': self.declaration.opt_out_reason,
                'final_cost': math.fsum(r['cost'] for r in final_rows),
                'final_elapsed_seconds': math.fsum(r['metadata'].get('execution', {}).get('elapsed_seconds', 0.) for r in final_rows),
                'uncertain_evaluations': list(self.state['uncertain']),
                'claim': 'declared_evaluation_workflow_only; no statistical precision or application-validity guarantee'}

    def restore(self, saved, trials, results, *, finished, maximize, endpoint, cancelled):
        expected_keys = set(self.state)
        if (not isinstance(saved, dict) or set(saved) != expected_keys or saved['version'] != 1
                or saved['identity'] != self.declaration.identity or saved['contract'] != self.declaration.contract):
            raise ValueError("Checkpoint declaration/evaluation identity differs")
        if saved['phase'] not in {'tuning', 'selection_frozen', 'final_evaluation', 'reported', 'opted_out'}:
            raise ValueError("Invalid evaluation phase")
        if (not isinstance(saved['uncertain'], list) or any(not isinstance(t, str) for t in saved['uncertain'])
                or len(saved['uncertain']) != len(set(saved['uncertain']))):
            raise ValueError("Invalid uncertain evaluation ledger")
        for role in ('tuning', 'final'):
            if not isinstance(saved[role], dict) or not set(saved[role]) <= set(trials):
                raise ValueError("Evaluation records without candidate")
            for tid, rows in saved[role].items():
                tasks = self.tasks(trials[tid], role)
                if not isinstance(rows, list) or len(rows) > len(tasks):
                    raise ValueError("Evaluation repetition count differs")
                for row, (fold, seed, rid) in zip(rows, tasks):
                    if (not isinstance(row, dict) or set(row) != {'fold', 'seed', 'result'} or row['fold'] != fold.name
                            or type(row['seed']) is not int or row['seed'] != seed):
                        raise ValueError("Evaluation role/seed differs")
                    result = Result(**row['result'])
                    self.validate_record(result, rid, trials[tid].fidelity)
                    if (result.metadata['execution']['accounting'] != 'not_dispatched'
                            and (rid in saved['uncertain']) != (result.metadata['execution']['accounting'] == 'lower_bound_after_interruption')):
                        raise ValueError("Repetition accounting uncertainty differs")
        task_ids = {rid for role in ('tuning', 'final') for trial in trials.values() for _, _, rid in self.tasks(trial, role)}
        if not set(saved['uncertain']) <= task_ids:
            raise ValueError("Unknown uncertain repetition")
        active = saved['inflight']
        if active is not None:
            if not isinstance(active, dict) or set(active) != {'role', 'parent', 'index', 'trial_id'}:
                raise ValueError("Invalid inflight repetition")
            role, tid, i = active['role'], active['parent'], active['index']
            if role not in {'tuning', 'final'} or tid not in trials or type(i) is not int or i < 0:
                raise ValueError("Invalid inflight repetition role")
            tasks = self.tasks(trials[tid], role)
            if i != len(saved[role].get(tid, [])) or i >= len(tasks) or active['trial_id'] != tasks[i][2]:
                raise ValueError("Inflight repetition disagrees with committed ledger")
            if role == 'tuning' and tid in results:
                raise ValueError("Completed candidate has inflight repetition")
        candidate_state = deepcopy(self.state)
        self.state = deepcopy(saved)
        try:
            for tid, result in results.items():
                rows = saved['tuning'].get(tid, [])
                if len(rows) != len(self.tasks(trials[tid], 'tuning')):
                    raise ValueError("Committed candidate lacks complete repetition ledger")
                aggregate = self.aggregate(trials[tid], rows,
                    cancelled=result.status == 'cancelled' and trials[tid].root_trial_id in cancelled)
                if (aggregate.status != result.status or aggregate.cost != result.cost
                        or aggregate.fidelity != result.fidelity
                        or aggregate.metadata['execution'] != result.metadata.get('execution')
                        or not (aggregate.objective_value == result.objective_value or
                                math.isnan(aggregate.objective_value) and math.isnan(result.objective_value))
                        or json.dumps(aggregate.metadata['evaluation'], sort_keys=True) != json.dumps(result.metadata.get('evaluation'), sort_keys=True)):
                    raise ValueError("Candidate aggregate differs from raw repetition records")
                if self.spec and aggregate.metadata.get('multi_objective') != result.metadata.get('multi_objective'):
                    raise ValueError("Candidate vector differs from repetition records")
        except BaseException:
            self.state = candidate_state
            raise
        selection = saved['selection']
        if (not isinstance(selection, list) or any(not isinstance(t, str) for t in selection)
                or len(selection) != len(set(selection)) or not set(selection) <= set(results)):
            raise ValueError("Invalid frozen selection")
        if saved['phase'] != 'tuning':
            if finished is not True or set(trials) != set(results) or active is not None and active['role'] == 'tuning':
                raise ValueError("Final evaluation began before tuning finished")
            if self.spec:
                expected = self.spec.summarize(list(results.values()), endpoint_fidelity=endpoint)['front_trial_ids']
            else:
                eligible = [r for r in results.values() if r.status == 'completed' and r.is_valid() and r.fidelity == endpoint]
                best = (max if maximize else min)(eligible, key=lambda r: r.objective_value) if eligible else None
                expected = [best.trial_id] if best else []
            if selection != expected:
                raise ValueError("Frozen selection differs from tuning-only result")
        elif selection or saved['final'] or active and active['role'] == 'final':
            raise ValueError("Final data entered tuning phase")
        if not set(saved['final']) <= set(selection):
            raise ValueError("Final evaluation contains an unselected candidate")
        if saved['phase'] in {'selection_frozen', 'opted_out'} and (saved['final'] or active is not None):
            raise ValueError("Final data contradicts frozen/opt-out phase")
        if (saved['phase'] == 'opted_out') != (bool(self.declaration.opt_out_reason) and saved['phase'] not in {'tuning', 'selection_frozen'}):
            raise ValueError("Evaluation opt-out phase differs")
        if saved['phase'] == 'reported':
            if active is not None or any(len(saved['final'].get(tid, [])) != len(self.tasks(trials[tid], 'final')) for tid in selection):
                raise ValueError("Reported evaluation is incomplete")
        self.state = deepcopy(saved)


def legacy_evaluation_report(reason=None):
    return {'status': 'legacy_unqualified', 'reason': reason or 'Historical record without an evaluation declaration or legacy reason'}


def evaluation_controller(declaration, *, maximize, spec=None):
    if declaration.streaming_steps:
        from hponas.evaluation_streaming import StreamingEvaluationController
        return StreamingEvaluationController(declaration, maximize=maximize, spec=spec)
    return EvaluationController(declaration, maximize=maximize, spec=spec)


def evaluation_outcome(state):
    """Keep terminal scientific failure distinct from finishing the workflow."""
    if state['phase'] != 'reported':
        return state['phase']
    if not state['selection']:
        return 'no_selection'
    expected = len(state['contract']['final_folds']) * len(state['contract']['final_seeds'])
    for tid in state['selection']:
        rows = state['final'].get(tid, [])
        if len(rows) != expected:
            return 'incomplete'
        if any(r['result']['status'] != 'completed' or not Result(**r['result']).is_valid() for r in rows):
            return 'failed'
    if any(not row['result']['metadata'].get('multi_objective', {}).get('feasible', True)
           for rows in state['final'].values() for row in rows):
        return 'infeasible'
    return 'completed'
