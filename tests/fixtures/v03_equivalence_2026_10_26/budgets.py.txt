"""Declared endpoint resource reservations and measured/uncertain attempt ledger."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math


def finite(value, *, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


@dataclass(frozen=True)
class StudyBudget:
    """Independent tuning/final work pools, in one caller-declared work unit.

    Each call promises a maximum work amount. Returned meters are checked;
    arbitrary objective code is not a hard resource sandbox. Elapsed limits
    prevent further endpoint dispatch, with reported last-call overshoot.
    """
    configurations: int
    work_unit: str
    tuning_work: float
    final_work: float
    max_work_per_call: float
    worker_capacity: int = 1
    tuning_seconds: float | None = None
    final_seconds: float | None = None
    full_run_work: float | None = None

    def __post_init__(self):
        for key in ('configurations', 'worker_capacity'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError('Positive integer ' + key + ' required')
        if not isinstance(self.work_unit, str) or not self.work_unit.strip():
            raise ValueError('Explicit work unit required')
        for key in ('tuning_work', 'max_work_per_call'):
            if not finite(getattr(self, key), positive=True):
                raise ValueError('Positive finite ' + key + ' required')
        if not finite(self.final_work) or self.tuning_work < self.max_work_per_call:
            raise ValueError('Invalid work reservation')
        for key in ('tuning_seconds', 'final_seconds', 'full_run_work'):
            value = getattr(self, key)
            if value is not None and not finite(value, positive=True):
                raise ValueError('Positive finite ' + key + ' required')

    @property
    def contract(self):
        return {'version': 1, **asdict(self)}

    def validate_study(self, declaration, vector, workers):
        if declaration is None:
            raise ValueError('StudyBudget requires a declared endpoint evaluation workflow')
        if workers > self.worker_capacity:
            raise ValueError('Study concurrency exceeds declared worker capacity')
        candidates = self.configurations if vector else 1
        calls = max(1, len(declaration.streaming_steps))
        required = candidates * len(declaration.final_folds) * len(declaration.final_seeds) * calls * self.max_work_per_call
        if self.final_work < required:
            raise ValueError('Final work reserve cannot cover the maximum frozen selection')


class ResourceController:
    def __init__(self, budget):
        if not isinstance(budget, StudyBudget):
            raise TypeError('resource_budget must be a StudyBudget')
        self.budget = budget
        self.state = {'version': 2, 'contract': budget.contract, 'attempts': [], 'events': []}

    def usage(self, role):
        attempts = [a for a in self.state['attempts'] if a['role'] == role]
        measured = math.fsum(a['work'] for a in attempts if a['work'] is not None)
        charged = math.fsum(a['work'] if a['work'] is not None else self.budget.max_work_per_call for a in attempts)
        elapsed = math.fsum(a['elapsed'] for a in attempts if a['elapsed'] is not None)
        return {'measured_work': measured, 'charged_work': charged, 'elapsed_seconds': elapsed,
                'work_exact': all(a['work'] is not None for a in attempts),
                'elapsed_exact': all(a['elapsed'] is not None for a in attempts),
                'attempts': len(attempts), 'lost_attempts': sum(a['state'] == 'lost' for a in attempts),
                'contract_breaches': sum(a['breach'] is not None for a in attempts)}

    def abandon_inflight(self):
        for i, a in enumerate(self.state['attempts']):
            if a['state'] == 'inflight':
                a['state'] = 'lost'
                self.state['events'].append({'kind': 'lost', 'index': i})

    def refusal(self, role):
        if role not in ('tuning', 'final'):
            raise ValueError('Unknown resource role')
        usage = self.usage(role)
        if usage['contract_breaches']:
            return role + '_resource_contract_breach'
        if usage['charged_work'] + self.budget.max_work_per_call > getattr(self.budget, role + '_work'):
            return role + '_work_exhausted'
        seconds = getattr(self.budget, role + '_seconds')
        unknown = any(a['role'] == role and a['state'] == 'lost' and a['elapsed'] is None for a in self.state['attempts'])
        if seconds is not None and (unknown or usage['elapsed_seconds'] >= seconds):
            return role + ('_elapsed_unknown' if unknown else '_seconds_exhausted')
        return None

    def begin(self, tid, role):
        if (self.refusal(role) or sum(a['state'] == 'inflight' for a in self.state['attempts']) >= self.budget.worker_capacity
                or any(a['state'] == 'inflight' and a['trial_id'] == tid for a in self.state['attempts'])):
            raise ValueError('Resource reservation unavailable')
        self.state['attempts'].append({'trial_id': tid, 'role': role, 'state': 'inflight',
                                       'work': None, 'elapsed': None, 'breach': None})
        self.state['events'].append({'kind': 'begin', 'index': len(self.state['attempts'])-1})

    def meter(self, result, spec):
        if spec is not None:
            vector = spec.validate_result(result)
            if vector is not None and spec.contract['work_unit'] == self.budget.work_unit:
                return vector['work']
            return None
        payload = result.metadata.get('resource', {})
        if not isinstance(payload, dict) or set(payload) != {'work', 'unit'}:
            return None
        if payload['unit'] != self.budget.work_unit or not finite(payload['work']):
            return None
        return payload['work']

    def complete(self, result, spec):
        matching = [(i,a) for i,a in enumerate(self.state['attempts']) if a['state'] == 'inflight' and a['trial_id'] == result.trial_id]
        if len(matching) != 1:
            raise ValueError('Resource attempt identity differs')
        index, attempt = matching[0]
        work = self.meter(result, spec)
        breach = ('missing_or_invalid_work_meter' if work is None else
                  'work_exceeds_declared_call_bound' if work > self.budget.max_work_per_call else None)
        elapsed = result.metadata.get('streaming_attempt', {}).get('elapsed_seconds', result.metadata['execution']['elapsed_seconds'])
        attempt.update(state='committed', work=work, elapsed=elapsed, breach=breach)
        self.state['events'].append({'kind': 'complete', 'index': index})
        result.metadata['resource_attempt'] = index
        if breach:
            result.metadata['resource_refusal'] = {'reason': breach, 'original_status': result.status}
            result.status = 'failed'

    def report(self):
        roles = {}
        for role in ('tuning', 'final'):
            u = self.usage(role)
            seconds = getattr(self.budget, role + '_seconds')
            u.update(work_limit=getattr(self.budget, role + '_work'), seconds_limit=seconds,
                     seconds_overshoot=max(0., u['elapsed_seconds'] - seconds) if seconds else 0.,
                     full_run_equivalents=u['measured_work'] / self.budget.full_run_work if self.budget.full_run_work else None)
            roles[role] = u
        return {'mode': 'declared_endpoint_reservations', 'contract': self.budget.contract,
                **roles, 'attempts': deepcopy(self.state['attempts']),
                'enforcement': 'dispatch reservations under the declared per-call work bound; endpoint time caps can overshoot',
                'uncertainty': 'lost or unmetered attempts consume a whole work reservation; measured work is a lower bound'}

    def restore(self, saved, evaluation, spec):
        if isinstance(saved, dict) and saved.get('version') == 1:
            return self._restore_v1(saved, evaluation, spec)
        if (not isinstance(saved, dict) or set(saved) != set(self.state) or saved.get('version') != 2
                or saved.get('contract') != self.budget.contract or not isinstance(saved.get('attempts'), list)
                or not isinstance(saved.get('events'), list)):
            raise ValueError('Checkpoint resource contract differs')
        raw = evaluation.resource_records()
        active = evaluation.state['inflight']
        active_rows = active if isinstance(active, list) else ([] if active is None else [active])
        candidate = ResourceController(self.budget)
        committed = set()
        for event in saved['events']:
            if (not isinstance(event, dict) or set(event) != {'kind', 'index'}
                    or type(event['index']) is not int or not 0 <= event['index'] < len(saved['attempts'])):
                raise ValueError('Invalid resource event')
            i = event['index']; attempt = saved['attempts'][i]
            if (not isinstance(attempt, dict) or set(attempt) != {'trial_id', 'role', 'state', 'work', 'elapsed', 'breach'}):
                raise ValueError('Invalid resource attempt')
            tid, role = attempt['trial_id'], attempt['role']
            if (not isinstance(tid, str) or not tid or role not in ('tuning', 'final')
                    or not (evaluation.resource_role(tid) == role or any(a['trial_id'] == tid and a['role'] == role for a in active_rows))):
                raise ValueError('Unknown resource attempt')
            if event['kind'] == 'begin':
                if i != len(candidate.state['attempts']) or tid in committed:
                    raise ValueError('Resource admission order differs')
                candidate.begin(tid, role)
            elif event['kind'] in ('complete', 'lost'):
                if i >= len(candidate.state['attempts']) or candidate.state['attempts'][i]['state'] != 'inflight':
                    raise ValueError('Resource completion precedes admission or is repeated')
                if event['kind'] == 'complete':
                    if tid not in raw or tid in committed or raw[tid][0] != role:
                        raise ValueError('Resource attempt lacks unique raw repetition')
                    from hponas.types import Result
                    result = Result(**deepcopy(raw[tid][1]))
                    if type(result.metadata.get('resource_attempt')) is not int or result.metadata['resource_attempt'] != i:
                        raise ValueError('Resource attempt index differs')
                    original_status = result.status
                    candidate.complete(result, spec)
                    if candidate.state['attempts'][i]['breach'] is not None and original_status != 'failed':
                        raise ValueError('Resource breach cannot be successful')
                    committed.add(tid)
                else:
                    if tid not in evaluation.state['uncertain']:
                        raise ValueError('Lost work lacks evaluation uncertainty')
                    candidate.state['attempts'][i]['state'] = 'lost'
                    candidate.state['events'].append(deepcopy(event))
            else:
                raise ValueError('Unknown resource event')
        if candidate.state != saved:
            raise ValueError('Resource event replay differs from saved accounting')
        for attempt in candidate.state['attempts']:
            if attempt['state'] == 'inflight' and not any(a['trial_id'] == attempt['trial_id'] and a['role'] == attempt['role'] for a in active_rows):
                raise ValueError('Inflight resource and repetition ledgers differ')
        for tid, (_, row) in raw.items():
            if row['metadata']['execution']['accounting'] != 'not_dispatched' and tid not in committed:
                raise ValueError('Dispatched repetition lacks a resource attempt')
        self.state = deepcopy(saved)

    def _restore_v1(self, saved, evaluation, spec):
        if (not isinstance(saved, dict) or set(saved) != {'version', 'contract', 'attempts'} or saved['version'] != 1
                or saved['contract'] != self.budget.contract or not isinstance(saved['attempts'], list)):
            raise ValueError('Checkpoint resource contract differs')
        raw = evaluation.resource_records()
        committed = set()
        candidate = ResourceController(self.budget)
        for i, attempt in enumerate(saved['attempts']):
            if (not isinstance(attempt, dict) or set(attempt) != {'trial_id', 'role', 'state', 'work', 'elapsed', 'breach'}
                    or attempt['role'] not in {'tuning', 'final'} or attempt['state'] not in {'inflight', 'committed', 'lost'}):
                raise ValueError('Invalid resource attempt')
            tid, role = attempt['trial_id'], attempt['role']
            active = evaluation.state['inflight']
            active_rows = active if isinstance(active,list) else ([] if active is None else [active])
            known = evaluation.resource_role(tid) == role or any(a['trial_id'] == tid and a['role'] == role for a in active_rows)
            if not isinstance(tid, str) or not tid or not known or tid in committed or candidate.refusal(role):
                raise ValueError('Resource attempt exceeds admission contract')
            if attempt['state'] == 'committed':
                if tid not in raw or tid in committed or raw[tid][0] != role:
                    raise ValueError('Resource attempt lacks unique raw repetition')
                from hponas.types import Result
                result = Result(**raw[tid][1])
                if type(result.metadata.get('resource_attempt')) is not int or result.metadata['resource_attempt'] != i:
                    raise ValueError('Resource attempt index differs')
                candidate.begin(tid, role)
                candidate.complete(deepcopy(result), spec)
                if candidate.state['attempts'][-1] != attempt:
                    raise ValueError('Resource meter/accounting differs from raw repetition')
                if attempt['breach'] is not None and result.status != 'failed':
                    raise ValueError('Resource breach cannot be successful')
                committed.add(tid)
            else:
                if attempt['work'] is not None or attempt['elapsed'] is not None or attempt['breach'] is not None:
                    raise ValueError('Uncommitted work must remain unknown')
                candidate.state['attempts'].append(deepcopy(attempt))
                candidate.state['events'].append({'kind': 'begin', 'index': i})
                if attempt['state'] == 'lost':
                    candidate.state['events'].append({'kind': 'lost', 'index': i})
                if attempt['state'] == 'inflight':
                    if (not any(a['trial_id'] == tid and a['role'] == role for a in active_rows)
                            or sum(a['state']=='inflight' for a in candidate.state['attempts']) > self.budget.worker_capacity):
                        raise ValueError('Inflight resource and repetition ledgers differ')
                elif tid not in evaluation.state['uncertain']:
                    raise ValueError('Lost work lacks evaluation uncertainty')
        for tid, (_, row) in raw.items():
            if row['metadata']['execution']['accounting'] != 'not_dispatched' and tid not in committed:
                raise ValueError('Dispatched repetition lacks a resource attempt')
        self.state = deepcopy(candidate.state)
