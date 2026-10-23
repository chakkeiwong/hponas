"""Serial checkpoint barriers for repeated, protected streaming evaluation.

Each declared barrier advances every repetition once. The scheduler sees only
the complete cohort at that fidelity. A barrier segment is a separately metered
call; checkpoint state and the role/seed never cross repetition boundaries.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import inspect
import json
import math
from queue import Empty, Queue
import time

from hponas.evaluation import EvaluationController, EvaluationContext, _nonnegative
from hponas.executors.reporting import ProgressReport, ReportDecision
from hponas.types import Trial, Result, Config


class _StreamingRoleObjective:
    def __init__(self, fn, context):
        self.fn, self.context = fn, context
        self.parameters = inspect.signature(fn).parameters

    def __call__(self, config, fidelity=1., seed=None, trial_id=None, root_trial_id=None,
                 checkpoint=None, resume_from=0., reporter=None):
        values = dict(fidelity=fidelity, seed=seed, trial_id=trial_id, root_trial_id=root_trial_id,
                      checkpoint=checkpoint, resume_from=resume_from, reporter=reporter, evaluation=self.context)
        return self.fn(config, **{k: v for k, v in values.items() if k in self.parameters})


def execute_reported(study, child, objective, callback):
    """Keep all ledger/SQLite mutations on the caller thread for local and Ray."""
    study.executor.prepare()
    channel = Queue()
    def report(message):
        reply = Future()
        channel.put((message, reply))
        return reply.result()
    with ThreadPoolExecutor(max_workers=1) as controller:
        future = (study.executor.execute_async(child, objective, on_report=report)
                  if getattr(study.executor, 'mode', None) == 'async' else
                  controller.submit(study.executor.execute, child, objective, on_report=report))
        try:
            while not future.done():
                try:
                    message, reply = channel.get(timeout=.01)
                except Empty:
                    continue
                try:
                    with study._control_lock:
                        reply.set_result(callback(message))
                except BaseException as exc:
                    reply.set_exception(exc)
                    raise
            return future.result()
        finally:
            while not future.done():
                try:
                    _, reply = channel.get(timeout=.01)
                    reply.set_result(ReportDecision('cancel', 'study_interrupted'))
                except Empty:
                    pass


class StreamingEvaluationController(EvaluationController):
    def __init__(self, declaration, *, maximize, spec=None):
        super().__init__(declaration, maximize=maximize, spec=spec)
        self.maximize = maximize
        self.state.update(version=2, streaming={}, live=None, lost=[])

    def plan(self, trial, role):
        start = trial.resume_from if role == 'tuning' else 0.
        if trial.fidelity not in self.declaration.streaming_steps:
            raise ValueError('Assigned endpoint is absent from declared streaming barriers')
        return [(step, i, fold, seed, rid, f'{rid}_barrier_{j}')
                for j, step in enumerate(self.declaration.streaming_steps) if start < step <= trial.fidelity
                for i, (fold, seed, rid) in enumerate(self.tasks(trial, role))]

    def resource_records(self):
        return {r['result']['trial_id']: (group['role'], r['result'])
                for group in self.state['streaming'].values() for r in group['segments']}

    def resource_role(self, tid):
        raw = self.resource_records()
        if tid in raw:
            return raw[tid][0]
        return next((row['role'] for row in self.state['lost'] if row['trial_id'] == tid), None)

    def uncommitted_elapsed(self, committed):
        raw = self.resource_records()
        total = math.fsum(row['result']['metadata']['execution']['elapsed_seconds']
            for group in self.state['streaming'].values() if group['role'] == 'tuning' and group['parent'] not in committed
            for row in group['segments'])
        pending_ids = {sid for group in self.state['streaming'].values()
                       if group['role'] == 'tuning' and group['parent'] not in committed
                       for sid in self._group_segment_ids(group)}
        total += math.fsum(row['elapsed_seconds'] for row in self.state['lost']
                          if row['trial_id'] in pending_ids and row['trial_id'] not in raw)
        if self.state['live'] is not None and self.state['inflight']['role'] == 'tuning':
            total += self.state['live']['elapsed_seconds']
        return total

    def _group_segment_ids(self, group):
        # Segment identifiers are derived from the fixed role and repetition
        # roster, never accepted as arbitrary prefixes from a checkpoint.
        count = len(getattr(self.declaration, group['role']+'_folds')) * len(getattr(self.declaration, group['role']+'_seeds'))
        return {f"{group['parent']}_{group['role']}_{i}_barrier_{j}"
                for i in range(count) for j in range(len(self.declaration.streaming_steps))}

    def _abandon(self, study):
        active = self.state['inflight']
        if active is None:
            return
        last = self.state['live'] or {}
        self.state['lost'].append({'trial_id': active['trial_id'], 'role': active['role'],
            'cost': last.get('cost', 0.), 'elapsed_seconds': last.get('elapsed_seconds', 0.)})
        parent = study.trials[active['parent']]
        rid = self.tasks(parent, active['role'])[active['index']][2]
        for identity in (active['trial_id'], rid):
            if identity not in self.state['uncertain']:
                self.state['uncertain'].append(identity)
        if study._resources is not None:
            study._resources.abandon_inflight()
        self.state['inflight'] = self.state['live'] = None

    def _repetitions(self, trial, group, step, control=None):
        """Reconstruct each endpoint and all paid segments from raw evidence."""
        rows = []
        for i, (fold, seed, rid) in enumerate(self.tasks(trial, group['role'])):
            raw = [Result(**row['result']) for row in group['segments'] if row['index'] == i]
            recorded = {r.trial_id for r in raw}
            identities = {p[5] for p in self.plan(trial, group['role']) if p[1] == i}
            uncommitted = [r for r in self.state['lost'] if r['trial_id'] in identities-recorded]
            last = raw[-1] if raw else None
            valid = last is not None and last.fidelity == step and last.status == 'completed' and last.is_valid()
            status = ('cancelled' if control and control['action'] == 'cancel' else
                      'pruned' if control and control['action'] == 'stop' else
                      'failed' if control or not valid else 'completed')
            metadata = {'execution': {'elapsed_seconds': math.fsum(r.metadata['execution']['elapsed_seconds'] for r in raw)
                                                       + math.fsum(r['elapsed_seconds'] for r in uncommitted),
                         'accounting': 'lower_bound_after_interruption' if rid in self.state['uncertain'] else
                                       'measured' if raw else 'not_dispatched'},
                        'stream_segments': [r.trial_id for r in raw], 'stream_step': step}
            if last is not None:
                if 'checkpoint' in last.metadata:
                    metadata['checkpoint'] = deepcopy(last.metadata['checkpoint'])
                if 'artifacts' in last.metadata:
                    metadata['artifacts'] = deepcopy(last.metadata['artifacts'])
            if self.spec:
                vectors = [self.spec.validate_result(r) for r in raw]
                vector = vectors[-1] if vectors else None
                metadata['multi_objective'] = self.spec.observation(
                    objectives=vector['objectives'] if status == 'completed' else None,
                    constraints=vector['constraints'] if status == 'completed' else None,
                    work=sum(v['work'] for v in vectors if v is not None),
                    status='completed' if status == 'completed' else 'failed')
            result = Result(rid, last.objective_value if status == 'completed' else math.nan,
                            math.fsum(r.cost for r in raw)+math.fsum(r['cost'] for r in uncommitted),
                            trial.fidelity, metadata, status)
            rows.append({'fold': fold.name, 'seed': seed, 'result': result.to_dict()})
        return rows

    def run_group(self, study, trial, role):
        tasks = self.tasks(trial, role)
        rows = self.state[role].setdefault(trial.trial_id, [])
        if len(rows) == len(tasks):
            return self.aggregate(trial, rows) if role == 'tuning' else None
        key = role+':'+trial.trial_id
        group = self.state['streaming'].setdefault(key, {'role': role, 'parent': trial.trial_id,
                                                       'segments': [], 'barriers': [], 'control': None})
        self._abandon(study)
        plan = self.plan(trial, role)
        width = len(tasks)
        for offset, (step, i, fold, seed, rid, sid) in enumerate(plan):
            if group['control']:
                break
            if offset >= len(group['segments']):
                resources = study._resources
                refusal = resources.refusal(role) if resources is not None else None
                if role == 'tuning':
                    refusal = ('cancel_requested' if trial.root_trial_id in study._cancel_requested else
                               study._stop_reason or refusal or ('compute_budget_exhausted' if study._cap_reached() else None))
                if refusal:
                    group['control'] = {'action': 'cancel', 'reason': refusal, 'step': step}
                    if role == 'tuning' and refusal != 'cancel_requested':
                        study._stop_reason = study._stop_reason or refusal
                    break
                prior = [row for row in group['segments'] if row['index'] == i]
                checkpoint, start = None, 0.
                if prior:
                    checkpoint = prior[-1]['result']['metadata'].get('checkpoint')
                    start = prior[-1]['step']
                elif role == 'tuning' and trial.resume_from:
                    checkpoint = self.state['tuning'][trial.parent_trial_id][i]['result']['metadata'].get('checkpoint')
                    start = trial.resume_from
                if start and checkpoint is None:
                    raise ValueError('A streaming repetition cannot resume without its own checkpoint')
                child = Trial(Config(deepcopy(trial.config.values)), sid, seed=seed, fidelity=step,
                              root_trial_id=rid, continuation='resume' if start else 'restart',
                              resume_from=start, checkpoint=checkpoint)
                self.state['inflight'] = {'role': role, 'parent': trial.trial_id, 'index': i,
                                           'trial_id': sid, 'step': step}
                if resources is not None:
                    resources.begin(sid, role)
                study.save_checkpoint()
                context = EvaluationContext(role, fold, self.declaration.identity,
                    resources.budget.max_work_per_call if resources else None, resources.budget.work_unit if resources else None)
                def report(message):
                    if message.trial_id != sid or message.root_trial_id != rid or not start < message.step <= step:
                        raise ValueError('Streaming segment report identity or fidelity differs')
                    self.state['live'] = message.to_dict()
                    study.save_checkpoint()
                    if resources is not None:
                        seconds = getattr(resources.budget, role+'_seconds')
                        if seconds is not None and resources.usage(role)['elapsed_seconds'] + message.elapsed_seconds >= seconds:
                            if role == 'tuning':
                                study._stop_reason = 'tuning_seconds_exhausted'
                            return ReportDecision('cancel', role+'_seconds_exhausted')
                    if role == 'tuning':
                        if trial.root_trial_id in study._cancel_requested:
                            return ReportDecision('cancel', 'user_cancellation')
                        if study._cap_reached():
                            study._stop_reason = 'compute_budget_exhausted'
                            return ReportDecision('cancel', study._stop_reason)
                    return ReportDecision()
                started = time.monotonic()
                result = execute_reported(study, child, _StreamingRoleObjective(study.objective_fn, context), report)
                execution = result.metadata.setdefault('execution', {})
                missing = 'elapsed_seconds' not in execution and 'attempts' in result.metadata
                execution.setdefault('elapsed_seconds', time.monotonic()-started)
                execution.setdefault('accounting', 'measured')
                if missing or result.metadata.get('attempts', 1) > 1:
                    for identity in (sid, rid):
                        if identity not in self.state['uncertain']:
                            self.state['uncertain'].append(identity)
                if result.is_valid() and result.metadata.get('checkpoint') is None:
                    result.status = 'failed'
                    result.metadata['error'] = 'Streaming barriers require a durable repetition checkpoint'
                losses = [row for row in self.state['lost'] if row['trial_id'] == sid]
                result.metadata['streaming_attempt'] = {'cost': result.cost, 'elapsed_seconds': execution['elapsed_seconds']}
                result.cost += math.fsum(row['cost'] for row in losses)
                execution['elapsed_seconds'] += math.fsum(row['elapsed_seconds'] for row in losses)
                if sid in self.state['uncertain']:
                    execution['accounting'] = 'lower_bound_after_interruption'
                self.validate_record(result, sid, step)
                if resources is not None:
                    resources.complete(result, self.spec)
                group['segments'].append({'step': step, 'index': i, 'result': deepcopy(result.to_dict())})
                self.state['inflight'] = self.state['live'] = None
                if result.status != 'completed' or not result.is_valid():
                    group['control'] = {'action': 'cancel' if result.status == 'cancelled' else 'failed',
                                        'reason': 'incomplete_repetition', 'step': step}
                study.save_checkpoint()
            # Complete barriers can be replayed after a crash between scheduler
            # application and recording the barrier; Study's decision cache is durable.
            if i == width-1 and not group['control'] and len(group['barriers']) <= offset//width:
                repeated = self._repetitions(trial, group, step)
                aggregate = self.aggregate(trial, repeated, role=role)
                if not aggregate.is_valid():
                    raise ValueError('Incomplete repeated barrier cannot reach a scheduler')
                if role == 'tuning':
                    progress = ProgressReport(trial.trial_id, trial.root_trial_id, step, aggregate.objective_value,
                        aggregate.cost, aggregate.metadata['execution']['elapsed_seconds'],
                        aggregate.metadata.get('checkpoint'), metadata={'multi_objective': aggregate.metadata['multi_objective']} if self.spec else None)
                    decision = study._on_progress(progress, ledger_accounted=True)
                else:
                    decision = ReportDecision('continue', 'protected_final_evaluation')
                if decision.action == 'pause' and step != trial.fidelity:
                    raise ValueError('Scheduler pause must coincide with its assigned endpoint')
                group['barriers'].append({'step': step, 'value': aggregate.objective_value,
                    'vector': aggregate.metadata.get('multi_objective'), 'decision': decision.__dict__})
                if decision.action in ('cancel', 'stop'):
                    group['control'] = {**decision.__dict__, 'step': step}
                study.save_checkpoint()
        through = (group['control']['step'] if group['control'] else trial.fidelity)
        self.state[role][trial.trial_id] = self._repetitions(trial, group, through, group['control'])
        study.save_checkpoint()
        return self.aggregate(trial, self.state[role][trial.trial_id],
                              cancelled=trial.root_trial_id in study._cancel_requested) if role == 'tuning' else None

    def restore(self, saved, trials, results, **kwargs):
        if not isinstance(saved, dict) or set(saved) != set(self.state) or saved['version'] != 2:
            raise ValueError('Streaming checkpoint schema differs')
        candidate = type(self)(self.declaration, maximize=self.maximize, spec=self.spec)
        candidate.state = deepcopy(saved)
        if (not isinstance(saved['uncertain'], list) or any(not isinstance(s, str) for s in saved['uncertain'])
                or len(set(saved['uncertain'])) != len(saved['uncertain'])):
            raise ValueError('Invalid streaming uncertainty ledger')
        valid_segments, repetitions, raw = {}, set(), {}
        for role in ('tuning', 'final'):
            for trial in trials.values():
                for step, i, fold, seed, rid, sid in self.plan(trial, role):
                    valid_segments[sid] = (role, trial.trial_id, i, step, rid)
                    repetitions.add(rid)
        if not isinstance(saved['lost'], list) or not isinstance(saved['streaming'], dict):
            raise ValueError('Invalid streaming ledger')
        for role in ('tuning', 'final'):
            if any(role+':'+tid not in saved['streaming'] for tid in saved[role]):
                raise ValueError('Repetition ledger lacks raw streaming group')
        for row in saved['lost']:
            if (not isinstance(row, dict) or set(row) != {'trial_id', 'role', 'cost', 'elapsed_seconds'}
                    or row['trial_id'] not in valid_segments or row['role'] != valid_segments[row['trial_id']][0]
                    or not _nonnegative(row['cost']) or not _nonnegative(row['elapsed_seconds'])
                    or row['trial_id'] not in saved['uncertain']):
                raise ValueError('Invalid lost streaming attempt')
        if not set(saved['uncertain']) <= set(valid_segments) | repetitions:
            raise ValueError('Unknown uncertain streaming identity')
        for sid in set(saved['uncertain']) & set(valid_segments):
            if valid_segments[sid][4] not in saved['uncertain']:
                raise ValueError('Repetition uncertainty omitted')
        for key, group in saved['streaming'].items():
            if (set(group) != {'role', 'parent', 'segments', 'barriers', 'control'}
                    or group['role'] not in ('tuning', 'final') or group['parent'] not in trials
                    or key != group['role']+':'+group['parent']):
                raise ValueError('Streaming group identity differs')
            role, trial = group['role'], trials[group['parent']]
            if role == 'final' and (saved['phase'] not in ('final_evaluation', 'reported')
                                    or trial.trial_id not in saved['selection']):
                raise ValueError('Final streaming work precedes frozen selection')
            plan = self.plan(trial, role)
            if (not isinstance(group['segments'], list) or not isinstance(group['barriers'], list)
                    or len(group['segments']) > len(plan)):
                raise ValueError('Excess streaming segments')
            for position, row in enumerate(group['segments']):
                step, i, fold, seed, rid, sid = plan[position]
                if set(row) != {'step', 'index', 'result'} or row['step'] != step or row['index'] != i:
                    raise ValueError('Streaming segment order differs')
                result = Result(**row['result'])
                candidate.validate_record(result, sid, step)
                attempt = result.metadata.get('streaming_attempt', {})
                losses = [r for r in saved['lost'] if r['trial_id'] == sid]
                if (set(attempt) != {'cost', 'elapsed_seconds'} or not all(_nonnegative(v) for v in attempt.values())
                        or result.cost != attempt['cost'] + math.fsum(r['cost'] for r in losses)
                        or result.metadata['execution']['elapsed_seconds'] != attempt['elapsed_seconds'] + math.fsum(r['elapsed_seconds'] for r in losses)
                        or (sid in saved['uncertain']) != (result.metadata['execution']['accounting'] == 'lower_bound_after_interruption')):
                    raise ValueError('Streaming attempt accounting differs')
                if position < len(group['segments'])-1 and not result.is_valid():
                    raise ValueError('Work continued after a failed repetition')
                raw[sid] = row['result']
            control = group['control']
            if control is not None:
                if (set(control) != {'action', 'reason', 'step'} or control['action'] not in ('cancel', 'stop', 'failed')
                        or control['step'] not in [p[0] for p in plan] or not isinstance(control['reason'], str)):
                    raise ValueError('Invalid streaming control')
            width = len(self.tasks(trial, role))
            count = len(group['segments'])
            # A checkpoint can precede the current barrier commit, but work
            # cannot pass a previous barrier before its decision is durable.
            if not max(0, (count-1)//width) <= len(group['barriers']) <= count//width:
                raise ValueError('Streaming work passed an uncommitted barrier')
            for j, barrier in enumerate(group['barriers']):
                end = (j+1)*width
                if end > len(group['segments']):
                    raise ValueError('Scheduler saw an incomplete repetition barrier')
                prefix = {**group, 'segments': group['segments'][:end]}
                step = plan[end-1][0]
                reconstructed = candidate.aggregate(trial, candidate._repetitions(trial, prefix, step), role=role)
                if (set(barrier) != {'step', 'value', 'vector', 'decision'} or not reconstructed.is_valid()
                        or barrier['step'] != step or barrier['value'] != reconstructed.objective_value
                        or barrier['vector'] != reconstructed.metadata.get('multi_objective')):
                    raise ValueError('Barrier differs from independent repetition aggregation')
                decision = ReportDecision(**barrier['decision'])
                if (decision.action == 'pause' and step != trial.fidelity
                        or decision.action in ('stop', 'cancel') and
                        (end != count or j != len(group['barriers'])-1 or
                         control != {**barrier['decision'], 'step': step})):
                    raise ValueError('Work continued beyond a terminal streaming decision')
                if role == 'final' and barrier['decision'] != ReportDecision('continue', 'protected_final_evaluation').__dict__:
                    raise ValueError('Final repetition reached tuning control')
            last_failed = bool(count and not Result(**group['segments'][-1]['result']).is_valid())
            if last_failed and (control is None or control['action'] not in ('failed', 'cancel')
                                or control['step'] != plan[count-1][0]):
                raise ValueError('Failed repetition lacks its terminal control')
            if control and control['action'] == 'failed' and not last_failed:
                raise ValueError('Failure control lacks a failed repetition')
            rows = saved[role].get(trial.trial_id, [])
            if rows:
                if control is None and (len(group['segments']) != len(plan) or len(group['barriers'])*width != len(plan)):
                    raise ValueError('Completed streaming group is missing barriers')
                expected = candidate._repetitions(trial, group, control['step'] if control else trial.fidelity, control)
                if json.dumps(rows, sort_keys=True) != json.dumps(expected, sort_keys=True):
                    raise ValueError('Repeated endpoint differs from raw streaming segments')
        active = saved['inflight']
        if active is not None:
            if set(active) != {'role', 'parent', 'index', 'trial_id', 'step'} or active['trial_id'] not in valid_segments:
                raise ValueError('Invalid inflight streaming segment')
            role, parent, i, step, rid = valid_segments[active['trial_id']]
            if (active != {'role': role, 'parent': parent, 'index': i, 'trial_id': active['trial_id'], 'step': step}
                    or active['trial_id'] in raw or saved[role].get(parent)):
                raise ValueError('Inflight streaming identity differs')
            group = saved['streaming'][role+':'+parent]
            if saved['phase'] in ('reported', 'selection_frozen', 'opted_out') or role == 'tuning' and saved['phase'] != 'tuning':
                raise ValueError('Inflight streaming work contradicts evaluation phase')
            if self.plan(trials[parent], role)[len(group['segments'])][5] != active['trial_id'] or group['control']:
                raise ValueError('Inflight streaming order differs')
        if saved['live'] is not None:
            live = ProgressReport(**saved['live'])
            start = 0.
            if active is not None:
                plan = self.plan(trials[active['parent']], active['role'])
                position = next(i for i, p in enumerate(plan) if p[5] == active['trial_id'])
                index = plan[position][1]
                prior = [p[0] for p in plan[:position] if p[1] == index]
                start = prior[-1] if prior else trials[active['parent']].resume_from if active['role'] == 'tuning' else 0.
            if (active is None or live.trial_id != active['trial_id'] or live.root_trial_id != valid_segments[live.trial_id][4]
                    or not start < live.step <= active['step'] or not all(_nonnegative(v) for v in (live.cost, live.elapsed_seconds))
                    or not math.isfinite(live.value) or live.schema_version != 1):
                raise ValueError('Invalid live streaming report')
            if self.spec:
                self.spec.validate_observation(live.metadata['multi_objective'])
        # Reuse endpoint selection/role/aggregate checks after reconstructing
        # the projected repetition ledger from the separately validated segments.
        projected = {k: deepcopy(v) for k, v in saved.items() if k not in ('streaming', 'live', 'lost')}
        projected.update(version=1, inflight=None, uncertain=[r for r in saved['uncertain'] if r in repetitions])
        base = EvaluationController(self.declaration, maximize=self.maximize, spec=self.spec)
        base.restore(projected, trials, results, **kwargs)
        self.state = deepcopy(saved)

    def validate_study_snapshot(self, state):
        for group in self.state['streaming'].values():
            if group['role'] != 'tuning':
                continue
            cache = {float(step): row for step, row in state['report_cache'].get(group['parent'], {}).items()}
            for barrier in group['barriers']:
                entry = cache.get(barrier['step'])
                metric = barrier['vector'] if self.spec else (-barrier['value'] if self.maximize else barrier['value'])
                if (entry is None or entry['value'] != barrier['value'] or entry.get('metric') != metric
                        or entry['decision'] != barrier['decision']):
                    raise ValueError('Streaming barrier and scheduler decision cache differ')
            terminal = [b for b in group['barriers'] if b['decision']['action'] in ('stop', 'cancel')]
            if terminal and group['control'] != {**terminal[-1]['decision'], 'step': terminal[-1]['step']}:
                raise ValueError('Terminal streaming decision was changed')
            if group['control'] and group['control']['action'] == 'stop' and not terminal:
                raise ValueError('Streaming pruning lacks a complete scheduler barrier')
