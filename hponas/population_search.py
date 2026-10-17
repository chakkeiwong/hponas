"""Recoverable local PBT with truncation selection and multiplicative exploration.

The declared logical population is trained serially by this CPU reference
controller. It establishes no distributed speedup or PB2/BG-PBT equivalence.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import math
from pathlib import Path
import random

from hponas.persistence import atomic_json
from hponas.population import _digest, restore_member


class LocalPBT:
    def __init__(self, path, population, *, seed=0, quantile=0.25,
                 learning_rate_bounds=(0.001, 1.0), factors=(0.8, 1.2), explorer=None):
        self.path, self.population = Path(path), population
        self.explorer = explorer
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('PBT seed must be an unsigned 32-bit integer')
        if isinstance(quantile, bool) or not math.isfinite(quantile) or not 0 < quantile <= 0.5:
            raise ValueError('Truncation quantile must be in (0,0.5]')
        lo, hi = learning_rate_bounds
        if not 0 < lo <= hi <= 1 or not factors or any(not math.isfinite(f) or f <= 0 for f in factors):
            raise ValueError('Invalid exploration bounds or factors')
        state = population.snapshot()
        self.options = {'method': 'local_pbt_truncation_v1', 'seed': seed, 'quantile': quantile,
                        'learning_rate_bounds': list(learning_rate_bounds), 'factors': list(factors),
                        'objective': population.identity, 'initial_members': _digest(state['initial_members']),
                        'max_updates': state['max_updates']}
        if explorer is not None:
            lower, upper = population.objective.return_bounds
            if explorer.contract['increment_bound'] + 1e-12 < upper-lower:
                raise ValueError('Explorer gain bound is smaller than the analytic objective range')
            lo, hi = explorer.contract['learning_rate_bounds']
            for member in state['members'].values():
                options = member['optimizer']
                if not lo <= options['learning_rate'] <= hi or options['momentum'] not in explorer.contract['momenta']:
                    raise ValueError('Population optimizer is outside the explorer contract')
            self.options['explorer'] = explorer.contract
        with self._lock():
            if self.path.exists():
                self._read()
            else:
                if state['events']:
                    raise ValueError('A new controller requires an unused population')
                self._write({'options': self.options, 'rounds': []})

    @contextmanager
    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix+'.lock').open('a') as handle:
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
                or _digest(envelope['payload']) != envelope['sha256']
                or envelope['payload']['options'] != self.options):
            raise ValueError('PBT checkpoint checksum or options differ')
        return envelope['payload']

    def _scores(self):
        scores = {}
        for ident, member in self.population.snapshot()['members'].items():
            model, _ = restore_member(member)
            model.eval()
            result = self.population.objective.components(model, model, 0)
            scores[ident] = float(result['return'].detach())
        return scores

    def run(self, rounds, *, updates_per_round):
        if type(rounds) is not int or not 1 <= rounds <= 128:
            raise ValueError('Rounds must be in [1,128]')
        if type(updates_per_round) is not int or not 1 <= updates_per_round <= 1024:
            raise ValueError('Updates per round must be in [1,1024]')
        if self.explorer is not None:
            members = len(self.population.snapshot()['initial_members'])
            pending = max(1, math.floor(members * self.options['quantile']))
            if rounds * members + pending > 512:
                raise ValueError('Full population schedule exceeds observed-plus-pending GP envelope')
            if rounds > self.explorer.contract.get('horizon', 128):
                raise ValueError('Full population schedule exceeds the categorical bandit horizon')
        with self._lock():
            state = self._read()
            if len(state['rounds']) > rounds or any(r['updates'] != updates_per_round for r in state['rounds']):
                raise ValueError('Cannot shrink or change a retained PBT schedule')
            for index in range(rounds):
                if index == len(state['rounds']):
                    needed = len(self.population.snapshot()['members']) * updates_per_round
                    if self.population.accounting()['upper'] + needed > self.options['max_updates']:
                        raise ValueError('PBT round exceeds remaining update budget')
                    scores_before = self._scores()
                    members_before = self.population.snapshot()['members']
                    state['rounds'].append({'index': index, 'updates': updates_per_round,
                                            'status': 'training', 'plan': None,
                                            'training_inputs': {name: {'score': scores_before[name],
                                                'optimizer': value['optimizer'],
                                                'architecture': value['architecture']} for name, value in members_before.items()}})
                    self._write(state)
                row = state['rounds'][index]
                if row['status'] == 'complete':
                    continue
                if row['status'] == 'blocked':
                    return deepcopy(state)
                if row['status'] == 'training':
                    for member in sorted(self.population.snapshot()['members']):
                        result = self.population.train(f'pbt:{index}:train:{member}', member, updates_per_round)
                        if result['status'] != 'committed':
                            row.update(status='blocked', reason=result['status'])
                            self._write(state)
                            return deepcopy(state)
                    scores = self._scores()
                    ranking = sorted(scores, key=lambda name: (-scores[name], name))
                    count = max(1, math.floor(len(ranking) * self.options['quantile']))
                    top, bottom = ranking[:count], ranking[-count:]
                    generator = random.Random(f"{self.options['seed']}:{index}")
                    snapshot = self.population.snapshot()
                    plan = []
                    for child in bottom:
                        parent = generator.choice(top)
                        teacher = snapshot['members'][parent]
                        factor = generator.choice(self.options['factors'])
                        lo, hi = self.options['learning_rate_bounds']
                        optimizer = {**teacher['optimizer'], 'learning_rate':
                                     min(hi, max(lo, teacher['optimizer']['learning_rate'] * factor))}
                        plan.append({'event_id': f'pbt:{index}:exploit:{child}',
                                     'parent': parent, 'child': child, 'mode': 'COPY',
                                     'optimizer_policy': 'COPY', 'architecture': teacher['architecture'],
                                     'optimizer': optimizer, 'factor': factor})
                    if self.explorer is not None:
                        plan, diagnostics = self.explorer.plan(state['rounds'], scores, snapshot, top, bottom)
                        row['exploration'] = diagnostics
                    row.update(status='exploiting', scores=scores, plan=plan)
                    self._write(state)
                for action in row['plan']:
                    result = self.population.exploit(**{k: v for k, v in action.items() if k != 'factor'})
                    if result['status'] != 'committed':
                        row.update(status='blocked', reason=result['status'])
                        self._write(state)
                        return deepcopy(state)
                row['status'] = 'complete'
                self._write(state)
            return deepcopy(state)
