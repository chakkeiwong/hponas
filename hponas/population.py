"""Local transactional checkpoint transfer for CoordinateMLP populations.

This is a single-writer CPU substrate, not a PB2/BG-PBT method controller.
The objective owns the policy/value loss and its declared work unit. Candidate
updates become authoritative only at final commit. Each in-flight update is
marked durably before computation so recovery never silently repeats it.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import math
from pathlib import Path

import torch

from hponas.architecture import build, compatible
from hponas.persistence import atomic_json


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _configuration(config):
    defaults = dict(width=64, depth=2, activation='relu', normalization='none',
                    input_dim=4, output_dim=1)
    if not isinstance(config, dict) or set(config) - set(defaults):
        raise ValueError('Only explicit architecture coordinates are accepted')
    result = {**defaults, **config}
    for key in ('width', 'depth', 'input_dim', 'output_dim'):
        if type(result[key]) is not int or result[key] < 1:
            raise ValueError('Architecture dimensions must be positive integers')
    if result['width'] > 512 or result['depth'] > 4 or max(result['input_dim'], result['output_dim']) > 65:
        raise ValueError('Architecture exceeds the local population contract')
    if result['activation'] not in {'relu', 'tanh', 'elu', 'gelu', 'swish'}:
        raise ValueError('Unsupported activation')
    if result['normalization'] not in {'none', 'layer_norm', 'spectral_norm'}:
        raise ValueError('Unsupported normalization')
    return result


def _options(options):
    if not isinstance(options, dict) or set(options) != {'learning_rate', 'momentum'}:
        raise ValueError('Explicit SGD learning_rate and momentum are required')
    lr, beta = options['learning_rate'], options['momentum']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lr, beta)):
        raise ValueError('Finite optimizer options required')
    if not 0 < lr <= 1 or not 0 <= beta < 1:
        raise ValueError('Optimizer options outside the local contract')
    return {'learning_rate': float(lr), 'momentum': float(beta)}


def _model(config, seed=0):
    # Construction must not consume the process-global training generator.
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        return build(config).double().cpu()


def _arrays(state):
    return {name: tensor.detach().cpu().tolist() for name, tensor in state.items()}


def _restore_arrays(values, template):
    if not isinstance(values, dict) or set(values) != set(template):
        raise ValueError('Checkpoint tensor names differ')
    restored = {}
    for name, expected in template.items():
        tensor = torch.as_tensor(values[name], dtype=expected.dtype)
        if tensor.shape != expected.shape or not torch.isfinite(tensor).all():
            raise ValueError('Checkpoint tensor shape or finiteness differs')
        restored[name] = tensor.clone()
    return restored


def make_member(config, optimizer, *, seed=0):
    config, optimizer = _configuration(config), _options(optimizer)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Seed must be an unsigned 32-bit integer')
    model = _model(config, seed)
    return {'architecture': config, 'optimizer': optimizer,
            'tensors': _arrays(model.state_dict()),
            'velocity': _arrays({k: torch.zeros_like(v) for k, v in model.named_parameters()}),
            'updates': 0}


def restore_member(member):
    if not isinstance(member, dict) or set(member) != {'architecture', 'optimizer', 'tensors', 'velocity', 'updates'}:
        raise ValueError('Malformed population member')
    if type(member['updates']) is not int or member['updates'] < 0:
        raise ValueError('Invalid member update count')
    model = _model(_configuration(member['architecture']))
    _options(member['optimizer'])
    model.load_state_dict(_restore_arrays(member['tensors'], model.state_dict()), strict=True)
    velocity = _restore_arrays(member['velocity'], dict(model.named_parameters()))
    return model, velocity


class PopulationCheckpoint:
    """Atomic local transfer journal. All public operations acquire one lock."""
    def __init__(self, path, objective, members=None, *, max_updates=None):
        self.path = Path(path)
        self.objective = objective
        self.identity = objective.identity
        if max_updates is not None and (type(max_updates) is not int or not 1 <= max_updates <= 65536):
            raise ValueError('Update budget must be an integer in [1,65536]')
        with self._lock():
            if self.path.exists():
                if members is not None:
                    raise ValueError('An existing population cannot be reinitialized')
                state = self._read()
                if max_updates is not None and max_updates != state['max_updates']:
                    raise ValueError('Existing population budget differs')
            else:
                if (not isinstance(members, dict) or not 2 <= len(members) <= 32
                        or any(not isinstance(k, str) or not k for k in members)):
                    raise ValueError('A new population requires 2 to 32 named members')
                for member in members.values():
                    self._check_member(member)
                self._write({'schema': 'local_population_checkpoint_v1', 'objective': self.identity,
                             'max_updates': 1024 if max_updates is None else max_updates,
                             'initial_members': deepcopy(members), 'members': deepcopy(members),
                             'events': {}, 'lineage': []})

    @contextmanager
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix+'.lock').open('a') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _check_member(self, member):
        model, _ = restore_member(member)
        config = member['architecture']
        if (config['input_dim'] != self.objective.observations.shape[1]
                or config['output_dim'] != self.objective.actions + 1):
            raise ValueError('Member architecture differs from objective')
        return model

    def _write(self, state):
        atomic_json(self.path, {'payload': state, 'sha256': _digest(state)})

    def _read(self):
        if self.objective.identity != self.identity:
            raise ValueError('Objective changed after population construction')
        envelope = json.loads(self.path.read_text())
        if set(envelope) != {'payload', 'sha256'} or _digest(envelope['payload']) != envelope['sha256']:
            raise ValueError('Population checksum differs')
        state = envelope['payload']
        if (set(state) != {'schema', 'objective', 'initial_members', 'members', 'events', 'lineage', 'max_updates'}
                or state['schema'] != 'local_population_checkpoint_v1' or state['objective'] != self.identity):
            raise ValueError('Population schema or objective differs')
        if type(state['max_updates']) is not int or not 1 <= state['max_updates'] <= 65536:
            raise ValueError('Invalid population update budget')
        for member in state['members'].values():
            self._check_member(member)
        replayed = deepcopy(state['initial_members'])
        for event in state['events'].values():
            if (event['status'] not in {'pending', 'committed', 'failed', 'interrupted'}
                    or type(event['completed_updates']) is not int
                    or not 0 <= event['completed_updates'] <= len(event['request']['weights'])
                    or type(event['inflight']) is not bool):
                raise ValueError('Invalid event accounting')
            if _digest(event['teacher']) != event['teacher_sha256']:
                raise ValueError('Teacher checkpoint differs')
            if (len(event['trace']) != event['completed_updates']
                    or event['request']['parent'] not in state['members']
                    or event['request']['child'] not in state['members']
                    or (event['request']['parent'] == event['request']['child']
                        and event['request']['mode'] != 'TRAIN')):
                raise ValueError('Event lineage or trace differs')
            if (event['teacher'] != replayed[event['request']['parent']]
                    or event['child_before_sha256'] != _digest(replayed[event['request']['child']])):
                raise ValueError('Event parent or child differs from lineage replay')
            if (event['status'] == 'committed' and
                    (event['inflight'] or event['completed_updates'] != len(event['request']['weights'])
                     or _digest(event['candidate']) != event['result_sha256'])):
                raise ValueError('Committed transfer is incomplete')
            if event['status'] == 'committed':
                replayed[event['request']['child']] = deepcopy(event['candidate'])
        if replayed != state['members']:
            raise ValueError('Member checkpoints differ from committed lineage replay')
        expected_lineage = [
            {'event': ident, 'parent': event['request']['parent'], 'child': event['request']['child'],
             'teacher_sha256': event['teacher_sha256'], 'result_sha256': event['result_sha256']}
            for ident, event in state['events'].items() if event['status'] == 'committed']
        if state['lineage'] != expected_lineage:
            raise ValueError('Population lineage differs from committed events')
        if sum(e['completed_updates'] + int(e['inflight']) for e in state['events'].values()) > state['max_updates']:
            raise ValueError('Population work exceeds its hard update budget')
        return state

    def snapshot(self):
        with self._lock():
            return self._read()

    def accounting(self):
        """Gradient updates only; unknown work is an interval, never free."""
        events = self.snapshot()['events'].values()
        lower = upper = 0
        for event in events:
            lower += event['completed_updates']
            upper += event['completed_updates'] + int(event['inflight'])
        return {'work_unit': 'finite_expectation_gradient_update', 'lower': lower, 'upper': upper}

    def exploit(self, event_id, parent, child, *, architecture, optimizer,
                mode, optimizer_policy, weights=(), seed=0, advance_to=None):
        """Retry one event, resume committed steps, or refuse an unknown step.

        COPY keeps parent's tensors and optionally SGD momentum. RESET is
        mandatory for a changed function/architecture. DISTILL uses a fresh
        candidate and the explicit imitation-to-RL schedule. Parent selection
        and exploration belong to the population method, not this store.
        """
        if not isinstance(event_id, str) or not event_id or (parent == child and mode != 'TRAIN'):
            raise ValueError('A unique event and distinct parent/child are required')
        architecture, optimizer = _configuration(architecture), _options(optimizer)
        if mode not in {'COPY', 'RESTART', 'DISTILL', 'TRAIN'} or optimizer_policy not in {'COPY', 'RESET'}:
            raise ValueError('Explicit supported transfer and optimizer policies required')
        weights = list(weights)
        if advance_to is not None and (type(advance_to) is not int or not 0 <= advance_to <= len(weights)):
            raise ValueError('Transfer continuation must stay within its fixed schedule')
        if mode == 'DISTILL':
            if (not 2 <= len(weights) <= 1024 or weights[0] != 1 or weights[-1] != 0
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) or not 0 <= v <= 1 for v in weights)
                    or any(a < b for a, b in zip(weights, weights[1:]))):
                raise ValueError('Distillation must anneal monotonically from 1 to 0')
        elif mode == 'TRAIN':
            if parent != child or optimizer_policy != 'COPY' or not 1 <= len(weights) <= 1024 or any(type(w) is not int or w != 0 for w in weights):
                raise ValueError('Training requires same member, copied momentum and pure RL steps')
        elif weights:
            raise ValueError('Non-distillation transfer cannot contain updates')
        if mode not in {'COPY', 'TRAIN'} and optimizer_policy != 'RESET':
            raise ValueError('Architecture transfer must reset optimizer state')
        candidate = make_member(architecture, optimizer, seed=seed)
        self._check_member(candidate)
        request = {'parent': parent, 'child': child, 'architecture': architecture,
                   'optimizer': optimizer, 'mode': mode, 'optimizer_policy': optimizer_policy,
                   'weights': weights, 'seed': seed}
        with self._lock():
            state = self._read()
            if parent not in state['members'] or child not in state['members']:
                raise ValueError('Unknown population member')
            if event_id in state['events']:
                event = state['events'][event_id]
                if event['request'] != request:
                    raise ValueError('Event identity reused for a different request')
                if event['status'] != 'pending':
                    return deepcopy(event)
                if event['inflight']:
                    event['status'] = 'interrupted'
                    event['error'] = 'One update may have executed without a committed checkpoint; child rolled back.'
                    self._write(state)
                    return deepcopy(event)
            else:
                if any(e['status'] == 'pending' for e in state['events'].values()):
                    raise ValueError('Recover the pending event before starting another')
                used = sum(e['completed_updates'] + int(e['inflight']) for e in state['events'].values())
                if used + len(weights) > state['max_updates']:
                    raise ValueError('Transfer exceeds remaining update budget')
                teacher = deepcopy(state['members'][parent])
                if mode in {'COPY', 'TRAIN'}:
                    if not compatible(teacher['architecture'], architecture):
                        raise ValueError('Incompatible tensor copy requires restart or distillation')
                    candidate['tensors'] = deepcopy(teacher['tensors'])
                    candidate['updates'] = teacher['updates']
                    if optimizer_policy == 'COPY':
                        if teacher['architecture'] != architecture:
                            raise ValueError('Changed model function must reset optimizer momentum')
                        candidate['velocity'] = deepcopy(teacher['velocity'])
                    self._check_member(candidate)
                event = {'request': request, 'status': 'pending', 'teacher': teacher,
                         'teacher_sha256': _digest(teacher),
                         'child_before_sha256': _digest(state['members'][child]),
                         'candidate': candidate, 'completed_updates': 0, 'inflight': False,
                         'trace': []}
                state['events'][event_id] = event
                self._write(state)
            target_updates = len(weights) if advance_to is None else advance_to
            if target_updates < event['completed_updates']:
                raise ValueError('Transfer cannot move backwards')
            try:
                student, velocity = restore_member(event['candidate'])
                teacher, _ = restore_member(event['teacher'])
                teacher.eval()
                for parameter in teacher.parameters():
                    parameter.requires_grad_(False)
                teacher_tensors = _arrays(teacher.state_dict())
                for weight in weights[event['completed_updates']:target_updates]:
                    event['inflight'] = True
                    self._write(state)
                    student.zero_grad(set_to_none=True)
                    result = self.objective.components(student, teacher, weight)
                    if self.objective.identity != self.identity:
                        raise ValueError('Objective changed during transfer')
                    result['loss'].backward()
                    with torch.no_grad():
                        for name, parameter in student.named_parameters():
                            if parameter.grad is None or not torch.isfinite(parameter.grad).all():
                                raise ValueError('Missing or nonfinite gradient')
                            velocity[name] = optimizer['momentum'] * velocity[name] + parameter.grad
                            parameter.add_(velocity[name], alpha=-optimizer['learning_rate'])
                    if _arrays(teacher.state_dict()) != teacher_tensors:
                        raise ValueError('Distillation mutated the teacher')
                    candidate = {**event['candidate'], 'tensors': _arrays(student.state_dict()),
                                 'velocity': _arrays(velocity), 'updates': event['candidate']['updates'] + 1}
                    self._check_member(candidate)
                    event['candidate'] = candidate
                    event['completed_updates'] += 1
                    event['inflight'] = False
                    event['trace'].append({key: float(result[key].detach()) for key in
                                           ('loss', 'policy_kl', 'value_error', 'return')})
                    self._write(state)
                if event['completed_updates'] < len(weights):
                    return deepcopy(event)
                if (_digest(state['members'][child]) != event['child_before_sha256']
                        or _digest(state['members'][parent]) != event['teacher_sha256']):
                    raise ValueError('Population changed while transfer was pending')
                event['status'] = 'committed'
                event['result_sha256'] = _digest(event['candidate'])
                state['members'][child] = deepcopy(event['candidate'])
                state['lineage'].append({'event': event_id, 'parent': parent, 'child': child,
                                         'teacher_sha256': event['teacher_sha256'],
                                         'result_sha256': event['result_sha256']})
                self._write(state)
                return deepcopy(event)
            except Exception as exc:
                # Reload the last durable state: a write can fail after rename.
                durable = self._read()
                recorded = durable['events'][event_id]
                if recorded['status'] == 'committed':
                    return deepcopy(recorded)
                recorded['status'] = 'failed'
                recorded['error'] = type(exc).__name__ + ': ' + str(exc)
                self._write(durable)
                return deepcopy(recorded)

    def train(self, event_id, member, updates):
        """Advance a member under its exact objective with durable SGD state."""
        if type(updates) is not int or not 1 <= updates <= 1024:
            raise ValueError('Updates must be an integer in [1,1024]')
        snapshot = self.snapshot()
        if member not in snapshot['members']:
            raise ValueError('Unknown population member')
        # Retrying after later exploits must use the original request options.
        old = snapshot['events'].get(event_id)
        config = old['request']['architecture'] if old else snapshot['members'][member]['architecture']
        optimizer = old['request']['optimizer'] if old else snapshot['members'][member]['optimizer']
        return self.exploit(event_id, member, member, architecture=config, optimizer=optimizer,
                            mode='TRAIN', optimizer_policy='COPY', weights=[0]*updates)

    def cancel(self, event_id, reason):
        """Stop a checkpointed candidate after a halving decision; retain work."""
        if not isinstance(reason, str) or not reason:
            raise ValueError('A concrete cancellation reason is required')
        with self._lock():
            state = self._read()
            event = state['events'][event_id]
            if event['status'] != 'pending':
                return deepcopy(event)
            event.update(status='failed', error='Cancelled: '+reason)
            self._write(state)
            return deepcopy(event)
