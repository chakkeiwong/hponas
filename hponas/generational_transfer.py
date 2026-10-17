"""On-policy architecture generations with immutable teachers and halving.

Candidate checkpoints live in isolated local stores; the outgoing population
is immutable. A complete successor is published only after all halving rungs.
This substrate accepts explicit architecture proposals. BG-PBT's architecture
BO and stagnation controller choose when and which proposals to supply.
"""
from copy import deepcopy
import fcntl
import json
from pathlib import Path

from hponas.persistence import atomic_json
from hponas.population import PopulationCheckpoint, _digest, make_member, restore_member


class ArchitectureGeneration:
    def __init__(self, directory, objective, teacher, proposals, *, survivors, rungs,
                 seed=0, max_updates):
        self.directory = Path(directory)
        self.objective = objective
        if (not isinstance(proposals, list) or not 1 <= survivors <= len(proposals) <= 32
                or type(survivors) is not int or len(rungs) < 1
                or any(type(v) is not int or not 1 <= v <= 1024 for v in rungs)
                or list(rungs) != sorted(set(rungs)) or rungs[-1] < 2):
            raise ValueError('Explicit bounded architecture proposals and increasing halving rungs required')
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('Generation seed must be an unsigned 32-bit integer')
        alive, previous, allocation = len(proposals), 0, 0
        for rung in rungs:
            allocation += alive*(rung-previous)
            previous = rung
            alive = max(survivors, (alive+1)//2)
        if type(max_updates) is not int or allocation > max_updates:
            raise ValueError('Halving allocation exceeds the declared generation budget')
        # Constant RL coefficient is an explicit prerequisite of this route.
        if objective.rl_weight is None:
            raise ValueError('Generational distillation requires independent RL and imitation weights')
        restore_member(teacher)
        candidates = [teacher]
        for index, architecture in enumerate(proposals):
            candidates.append(make_member(architecture, teacher['optimizer'], seed=(seed+index) % 2**32))
        for member in candidates:
            config = member['architecture']
            if config['input_dim'] != objective.observations.shape[1] or config['output_dim'] != objective.actions+1:
                raise ValueError('Transfer architecture dimensions differ from the objective')
        self.contract = {'schema': 'architecture_generation_v1', 'objective': objective.identity,
                         'teacher': deepcopy(teacher), 'proposals': deepcopy(proposals),
                         'survivors': survivors, 'rungs': list(rungs), 'seed': seed,
                         'max_updates': max_updates, 'allocated_updates': allocation,
                         'annealing': 'linear imitation multiplier 1 to 0; independent constant RL coefficient'}
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'generation.json'
        with (self.directory/'generation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                self._read()
            else:
                self._write({'contract': self.contract, 'rungs': [], 'status': 'pending', 'survivors': None})

    def _write(self, state):
        atomic_json(self.path, {'payload': state, 'sha256': _digest(state)})

    def _read(self):
        value = json.loads(self.path.read_text())
        if (_digest(value['payload']) != value['sha256'] or value['payload']['contract'] != self.contract
                or self.objective.identity != self.contract['objective']):
            raise ValueError('Generation identity or checkpoint checksum differs')
        return value['payload']

    def _store(self, index):
        path = self.directory/f'candidate-{index}.json'
        members = None
        if not path.exists():
            members = {'teacher': self.contract['teacher'], 'student': make_member(self.contract['proposals'][index],
                       self.contract['teacher']['optimizer'], seed=(self.contract['seed']+index) % 2**32)}
        return PopulationCheckpoint(path, self.objective, members,
                                    max_updates=self.contract['rungs'][-1])

    def _request(self, index, target):
        total = self.contract['rungs'][-1]
        return dict(event_id='distill', parent='teacher', child='student',
                    architecture=self.contract['proposals'][index], optimizer=self.contract['teacher']['optimizer'],
                    mode='DISTILL', optimizer_policy='RESET', weights=[1-i/(total-1) for i in range(total)],
                    seed=(self.contract['seed']+index) % 2**32, advance_to=target)

    def accounting(self):
        lower = upper = 0
        for index in range(len(self.contract['proposals'])):
            if (self.directory/f'candidate-{index}.json').exists():
                row = self._store(index).accounting()
                lower += row['lower']; upper += row['upper']
        return {'lower': lower, 'upper': upper, 'allocated': self.contract['allocated_updates']}

    def run(self):
        with (self.directory/'generation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self._read()
            if state['status'] in {'complete', 'blocked'}:
                return deepcopy(state)
            alive = list(range(len(self.contract['proposals'])))
            for position, target in enumerate(self.contract['rungs']):
                if position < len(state['rungs']):
                    row = state['rungs'][position]
                    for index in row['eliminated']:
                        self._store(index).cancel('distill', f'halving at update {target}')
                    alive = row['survivors']
                    continue
                scores = {}
                for index in alive:
                    store = self._store(index)
                    outcome = store.exploit(**self._request(index, target))
                    if outcome['status'] not in {'pending', 'committed'}:
                        state.update(status='blocked', reason=f'candidate {index}: {outcome["status"]}')
                        self._write(state)
                        return deepcopy(state)
                    model, _ = restore_member(outcome['candidate'])
                    model.eval()
                    scores[index] = float(self.objective.components(model, model, 0)['return'].detach())
                count = self.contract['survivors'] if position == len(self.contract['rungs'])-1 else max(self.contract['survivors'], (len(alive)+1)//2)
                winners = sorted(alive, key=lambda i: (-scores[i], i))[:count]
                eliminated = [index for index in alive if index not in winners]
                state['rungs'].append({'target': target, 'scores': {str(k): v for k, v in scores.items()},
                                       'survivors': winners, 'eliminated': eliminated})
                self._write(state)
                for index in eliminated:
                    self._store(index).cancel('distill', f'halving at update {target}')
                alive = winners
            successors = {str(index): self._store(index).snapshot()['members']['student'] for index in alive}
            state.update(status='complete', survivors=successors, accounting=self.accounting(),
                         teacher_sha256=_digest(self.contract['teacher']))
            assert state['accounting']['upper'] <= self.contract['allocated_updates']
            self._write(state)
            return deepcopy(state)
