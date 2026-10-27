"""Model-neutral, single-writer local PBT with protected schedule refitting.

Adapters are trusted caller code. Work means completed training updates, not
CPU/GPU time. Failed/lost calls consume their reserved upper bound. JSON
checkpoints contain no executable serialization. Existing finite-MDP engines
and their method qualifications are independent of this interface.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import fcntl
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Protocol, Any

from hponas.evaluation import StudyDeclaration, EvaluationContext
from hponas.persistence import atomic_json


def _json(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


class PopulationAdapter(Protocol):
    """Structural caller interface; no model class or optimizer is imposed.

    ``train`` performs exactly one declared update. ``transfer`` returns a
    checkpoint for the target configuration, explicitly copying or resetting
    optimizer state, and refuses incompatible model/optimizer transformations.
    All checkpoint/restore methods must be deterministic and side-effect free.
    Dataset access must obey the supplied role/fold; this is a caller boundary.
    """
    identity: str
    work_unit: str

    def initialize(self, config: dict, *, seed: int, evaluation: EvaluationContext) -> Any: ...
    def checkpoint(self, runtime: Any) -> dict: ...
    def restore(self, checkpoint: dict, config: dict, *, seed: int,
                evaluation: EvaluationContext) -> Any: ...
    def train(self, runtime: Any, config: dict, *, evaluation: EvaluationContext) -> None: ...
    def evaluate(self, runtime: Any, *, evaluation: EvaluationContext) -> float: ...
    def transfer(self, checkpoint: dict, source_config: dict, target_config: dict, *,
                 optimizer_policy: str, seed: int, evaluation: EvaluationContext) -> dict: ...


class PopulationExecutionError(RuntimeError):
    """A durable failed/uncertain call; its input checkpoint remains authoritative."""


class AdapterPopulation:
    """Serial truncation PBT and a separate final refit from a frozen schedule.

    Each round copies the best member to the worst (stable name tie-breaks),
    then explores a seeded choice from the explicit configuration roster.
    There is no statistical superiority or distributed execution claim.
    """
    def __init__(self, path, adapter: PopulationAdapter, declaration: StudyDeclaration,
                 members: dict, *, exploration_configs, rounds=2, updates_per_round=1,
                 seed=0, optimizer_policy='COPY', max_updates):
        if (not isinstance(declaration, StudyDeclaration) or len(declaration.objectives) != 1
                or declaration.opt_out_reason is not None or declaration.streaming_steps):
            raise ValueError('Population requires scalar endpoint declarations and protected final evaluation')
        if any(not isinstance(getattr(adapter, key, None), str) or not getattr(adapter, key).strip()
               for key in ('identity', 'work_unit')):
            raise ValueError('Adapter identity and training work unit are required')
        if any(not callable(getattr(adapter, key, None)) for key in
               ('initialize', 'checkpoint', 'restore', 'train', 'evaluate', 'transfer')):
            raise ValueError('Complete population adapter protocol required')
        if (not isinstance(members, dict) or not 2 <= len(members) <= 16
                or any(not isinstance(k, str) or not k for k in members)
                or any(not isinstance(v, dict) or not v for v in members.values())):
            raise ValueError('Two to sixteen named configurations required')
        if (not isinstance(exploration_configs, (list, tuple)) or not 1 <= len(exploration_configs) <= 64
                or any(not isinstance(v, dict) or not v for v in exploration_configs)):
            raise ValueError('Explicit finite exploration configurations required')
        if (type(rounds) is not int or not 1 <= rounds <= 32
                or type(updates_per_round) is not int or not 1 <= updates_per_round <= 1024
                or type(seed) is not int or not 0 <= seed < 2**32
                or optimizer_policy not in ('COPY', 'RESET')):
            raise ValueError('Invalid population schedule or optimizer policy')
        nt = len(declaration.tuning_folds) * len(declaration.tuning_seeds)
        nf = len(declaration.final_folds) * len(declaration.final_seeds)
        allocation = rounds * updates_per_round * (len(members) * nt + nf)
        if (max(nt, nf) > 64 or type(max_updates) is not int
                or not allocation <= max_updates <= 65536):
            raise ValueError('Budget must reserve the full tuning and final schedule')
        self.path, self.adapter, self.declaration = Path(path), adapter, declaration
        self.contract = _json(dict(schema='adapter_population_v1', adapter=adapter.identity,
            work_unit=adapter.work_unit, declaration=declaration.contract, members=members,
            exploration=list(exploration_configs), rounds=rounds, updates=updates_per_round,
            seed=seed, optimizer_policy=optimizer_policy, max_updates=max_updates,
            allocated_updates=allocation, selection='best_to_worst_stable_name'))
        with self._lock():
            if self.path.exists():
                self._read()
            else:
                self._write(dict(contract=self.contract, events=[], status='tuning'))

    @contextmanager
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + '.lock').open('a') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write(self, state):
        atomic_json(self.path, {'payload': state, 'sha256': _digest(state)})

    def _read(self):
        envelope = json.loads(self.path.read_text())
        if (set(envelope) != {'payload', 'sha256'}
                or _digest(envelope['payload']) != envelope['sha256']):
            raise ValueError('Population checksum differs')
        state = envelope['payload']
        if (set(state) != {'contract', 'events', 'status'} or state['contract'] != self.contract
                or self.adapter.identity != self.contract['adapter']
                or self.adapter.work_unit != self.contract['work_unit']
                or state['status'] not in ('tuning', 'final', 'complete', 'failed')):
            raise ValueError('Population contract or state differs')
        keys = set()
        for i, event in enumerate(state['events']):
            if (set(event) != {'key', 'request', 'status', 'result', 'result_sha256', 'error'}
                    or not isinstance(event['key'], str) or event['key'] in keys
                    or event['status'] not in ('pending', 'committed', 'failed', 'interrupted')
                    or event['request'].get('operation') not in
                       ('initialize', 'train', 'evaluate', 'transfer', 'freeze', 'seal')
                    or event['request'].get('role') not in ('tuning', 'final')):
                raise ValueError('Malformed population event')
            keys.add(event['key'])
            if state['status'] == 'complete' and i == len(state['events']) - 1:
                if event['key'] != 'seal' or event['status'] != 'committed':
                    raise ValueError('Complete population lacks its final score seal')
            if event['status'] == 'committed':
                if event['result_sha256'] != _digest(event['result']) or event['error'] is not None:
                    raise ValueError('Committed population result differs')
            elif (i != len(state['events']) - 1 or event['result'] is not None
                    or event['result_sha256'] is not None):
                raise ValueError('Work follows an uncommitted population event')
        if sum(e['request']['operation'] == 'train' for e in state['events']) > self.contract['max_updates']:
            raise ValueError('Population reservations exceed budget')
        if (state['status'] == 'complete' and (not state['events']
                or state['events'][-1]['key'] != 'seal'
                or state['events'][-1]['status'] != 'committed')):
            raise ValueError('Complete population lacks its final score seal')
        return state

    def _call(self, key, request, fn):
        request = _json(request)
        events = self._state['events']
        if self._cursor < len(events):
            event = events[self._cursor]
            if event['key'] != key or event['request'] != request:
                raise ValueError('Population request/lineage differs from deterministic replay')
            self._cursor += 1
            if event['status'] == 'committed':
                return deepcopy(event['result'])
            if event['status'] == 'pending':
                event.update(status='interrupted', error='Lost call; reserved work is uncertain')
                self._state['status'] = 'failed'
                self._write(self._state)
            raise PopulationExecutionError(event['error'])
        if self._state['status'] in ('complete', 'failed'):
            raise ValueError('Terminal population has missing events')
        if request['operation'] == 'train' and sum(
                e['request']['operation'] == 'train' for e in events) >= self.contract['max_updates']:
            raise ValueError('Population training budget exhausted')
        event = dict(key=key, request=request, status='pending', result=None,
                     result_sha256=None, error=None)
        events.append(event)
        self._cursor += 1
        self._write(self._state)  # durable dispatch/reservation barrier
        try:
            result = _json(fn())
        except Exception as exc:
            event.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            self._state['status'] = 'failed'
            self._write(self._state)
            raise PopulationExecutionError(event['error']) from exc
        event.update(status='committed', result=result, result_sha256=_digest(result))
        if request['operation'] == 'freeze':
            self._state['status'] = 'final'
        self._write(self._state)
        return deepcopy(result)

    def _context(self, role, fold):
        return EvaluationContext(role, fold, self.declaration.identity,
                                 work_unit=self.contract['work_unit'])

    def _replicas(self, role):
        d = self.declaration
        folds, seeds = ((d.tuning_folds, d.tuning_seeds) if role == 'tuning'
                        else (d.final_folds, d.final_seeds))
        return [(self._context(role, fold), seed) for fold in folds for seed in seeds]

    def _checkpoint(self, runtime, config, context, seed):
        value = _json(self.adapter.checkpoint(runtime))
        if not isinstance(value, dict):
            raise ValueError('Adapter checkpoint must be a JSON object')
        restored = self.adapter.restore(deepcopy(value), deepcopy(config), seed=seed, evaluation=context)
        if _json(self.adapter.checkpoint(restored)) != value:
            raise ValueError('Adapter checkpoint does not round-trip exactly')
        return value

    def _action(self, key, operation, member, config, context, seed, checkpoint=None,
                *, source_config=None, parent=None, optimizer_policy=None):
        request = dict(operation=operation, role=context.role, fold=asdict(context.fold),
            declaration=self.declaration.identity, seed=seed, member=member, config=config,
            input_sha256=None if checkpoint is None else _digest(checkpoint))
        if operation == 'transfer':
            request.update(source_config=source_config, parent=parent, optimizer_policy=optimizer_policy)

        def perform():
            if operation == 'initialize':
                runtime = self.adapter.initialize(deepcopy(config), seed=seed, evaluation=context)
            elif operation == 'transfer':
                payload = self.adapter.transfer(deepcopy(checkpoint), deepcopy(source_config),
                    deepcopy(config), optimizer_policy=optimizer_policy, seed=seed, evaluation=context)
                runtime = self.adapter.restore(payload, deepcopy(config), seed=seed, evaluation=context)
            else:
                runtime = self.adapter.restore(deepcopy(checkpoint), deepcopy(config), seed=seed, evaluation=context)
                if operation == 'train':
                    self.adapter.train(runtime, deepcopy(config), evaluation=context)
                elif operation == 'evaluate':
                    value = self.adapter.evaluate(runtime, evaluation=context)
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError('Every population repetition must have a finite scalar score')
                    return float(value)
            return self._checkpoint(runtime, config, context, seed)

        return self._call(key, request, perform)

    def run(self):
        """Resume committed calls; a failed/lost call is terminal, never retried."""
        with Path(str(self.path)+'.coordinator.lock').open('a') as coordinator, self._lock():
            fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._state, self._cursor = self._read(), 0
            try:
                self._execute()
            except PopulationExecutionError:
                return self._report(self._state)
            if self._cursor != len(self._state['events']):
                raise ValueError('Unexpected trailing population events')
            self._state['status'] = 'complete'
            self._write(self._state)
            return self._report(self._state)

    def _execute(self):
        tuning = self._replicas('tuning')
        members = {name: dict(config=deepcopy(config), checkpoints=[], schedule=[], policy='INITIAL')
                   for name, config in sorted(self.contract['members'].items())}
        for name, member in members.items():
            member['checkpoints'] = [self._action(f'init:{name}:{i}', 'initialize', name,
                member['config'], context, seed) for i, (context, seed) in enumerate(tuning)]
        for block in range(self.contract['rounds']):
            scores = {}
            for name, member in members.items():
                for i, (context, seed) in enumerate(tuning):
                    for step in range(self.contract['updates']):
                        member['checkpoints'][i] = self._action(f'train:{block}:{name}:{i}:{step}',
                            'train', name, member['config'], context, seed, member['checkpoints'][i])
                values = [self._action(f'score:{block}:{name}:{i}', 'evaluate', name,
                    member['config'], context, seed, member['checkpoints'][i])
                    for i, (context, seed) in enumerate(tuning)]
                scores[name] = fmean(values)  # complete matching cohort only
                member['schedule'].append(dict(config=deepcopy(member['config']),
                    updates=self.contract['updates'], optimizer_policy=member['policy']))
                member['policy'] = 'KEEP'
            sign = 1 if self.declaration.objectives[0].direction == 'min' else -1
            ranking = sorted(members, key=lambda name: (sign * scores[name], name))
            if block == self.contract['rounds'] - 1:
                break
            parent, child = ranking[0], ranking[-1]
            teacher, student = members[parent], members[child]
            choice_key = f"{self.contract['seed']}:{block}".encode()
            choice_index = int.from_bytes(hashlib.sha256(choice_key).digest()[:8], 'big') % len(
                self.contract['exploration'])
            config = deepcopy(self.contract['exploration'][choice_index])
            checkpoints = [self._action(f'transfer:{block}:{child}:{i}', 'transfer', child,
                config, context, seed, teacher['checkpoints'][i], source_config=teacher['config'],
                parent=parent, optimizer_policy=self.contract['optimizer_policy'])
                for i, (context, seed) in enumerate(tuning)]
            student.update(config=config, checkpoints=checkpoints,
                           schedule=deepcopy(teacher['schedule']), policy=self.contract['optimizer_policy'])
        winner = ranking[0]
        frozen = dict(member=winner, schedule=members[winner]['schedule'], tuning_mean=scores[winner])
        frozen = self._call('freeze', dict(operation='freeze', role='tuning', scores=scores,
            schedules={name: m['schedule'] for name, m in members.items()}), lambda: frozen)
        if frozen != dict(member=winner, schedule=members[winner]['schedule'], tuning_mean=scores[winner]):
            raise ValueError('Frozen selection differs from tuning reconstruction')
        final_scores = []
        for i, (context, seed) in enumerate(self._replicas('final')):
            schedule = frozen['schedule']
            config = schedule[0]['config']
            checkpoint = self._action(f'final:init:{i}', 'initialize', winner, config, context, seed)
            for block, row in enumerate(schedule):
                if block and row['optimizer_policy'] != 'KEEP':
                    checkpoint = self._action(f'final:transfer:{i}:{block}', 'transfer', winner,
                        row['config'], context, seed, checkpoint, source_config=config,
                        parent='frozen_schedule', optimizer_policy=row['optimizer_policy'])
                config = row['config']
                for step in range(row['updates']):
                    checkpoint = self._action(f'final:train:{i}:{block}:{step}', 'train', winner,
                                              config, context, seed, checkpoint)
            final_scores.append(self._action(f'final:score:{i}', 'evaluate', winner, config,
                                             context, seed, checkpoint))
        sealed = dict(final_records=final_scores, final_mean=fmean(final_scores))
        replayed = self._call('seal', dict(operation='seal', role='final',
            selection_sha256=_digest(frozen), final_records=final_scores), lambda: sealed)
        if replayed != sealed:
            raise ValueError('Final score seal differs from deterministic reconstruction')

    def _report(self, state):
        events = state['events']
        training = [e for e in events if e['request']['operation'] == 'train']
        freeze = next((e['result'] for e in events if e['key'] == 'freeze' and e['status'] == 'committed'), None)
        seal = next((e['result'] for e in events if e['key'] == 'seal' and e['status'] == 'committed'), None)
        return dict(status=state['status'], selection=deepcopy(freeze),
            final_mean=seal['final_mean'] if state['status'] == 'complete' and seal else None,
            final_records=deepcopy(seal['final_records']) if state['status'] == 'complete' and seal else [],
            accounting=dict(work_unit=self.contract['work_unit'],
                lower=sum(e['status'] == 'committed' for e in training), upper=len(training),
                allocated=self.contract['allocated_updates'],
                calls={op: dict(committed=sum(e['status'] == 'committed' for e in events
                        if e['request']['operation'] == op),
                    uncertain=sum(e['status'] != 'committed' for e in events
                        if e['request']['operation'] == op))
                    for op in ('initialize', 'train', 'evaluate', 'transfer')}),
            lineage=[deepcopy(e) for e in events if e['request']['operation'] == 'transfer'
                     and e['request']['role'] == 'tuning'], events=deepcopy(events))

    def snapshot(self):
        with self._lock():
            return self._report(self._read())
