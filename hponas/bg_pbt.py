"""Bounded local BG-PBT orchestration on exact finite policy/value workloads.

Generations retain contextual temporal exploration, stagnation/max-age triggers,
architecture BO plus random proposals and charged on-policy halving. Separate
policy/value architectures, PPO simulators and distributed workers require
adapters; this module's supported model is the shared CoordinateMLP trunk.
"""
from copy import deepcopy
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import random

from hponas.bg_population import ACTIVATIONS, NORMALIZATIONS, BGPopulationExplorer
from hponas.generational_transfer import ArchitectureGeneration
from hponas.persistence import atomic_json
from hponas.population import PopulationCheckpoint, _configuration, _digest, restore_member
from hponas.population_gp import TemporalOptions, TemporalPopulationGP
from hponas.population_search import LocalPBT


class LocalBGPBT:
    def __init__(self, directory, objective, members, architecture_pool, *, increment_bound,
                 generations=2, max_rounds=4, patience=2, updates_per_round=1,
                 distillation_rungs=(1, 2, 4), seed=0, max_updates, fit_iterations=4, executor=None):
        self.directory, self.objective = Path(directory), objective
        self.executor = executor
        for value, bound in [(generations, 16), (max_rounds, 128), (patience, 128), (updates_per_round, 1024)]:
            if type(value) is not int or not 1 <= value <= bound:
                raise ValueError('Bounded integer generation and training schedule required')
        if not isinstance(members, dict) or not 2 <= len(members) <= 16:
            raise ValueError('The local generational contract requires 2 to 16 members')
        pool = [_configuration(config) for config in architecture_pool]
        if not 2*len(members) <= len(pool) <= 32 or len({_digest(config) for config in pool}) != len(pool):
            raise ValueError('Architecture pool must contain distinct proposals for oversampling')
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('Generation seed must be an unsigned 32-bit integer')
        explorer = BGPopulationExplorer(increment_bound=increment_bound, fit_iterations=fit_iterations)
        if objective.rl_weight is None:
            raise ValueError('Independent constant RL coefficient is required')
        lower, upper = objective.return_bounds
        if increment_bound + 1e-12 < upper-lower:
            raise ValueError('Gain bound is smaller than the analytic objective range')
        for member in members.values():
            restore_member(member)
            options = member['optimizer']
            lo, hi = explorer.contract['learning_rate_bounds']
            if not lo <= options['learning_rate'] <= hi or options['momentum'] not in explorer.contract['momenta']:
                raise ValueError('Initial optimizer is outside the explorer contract')
        if any(not isinstance(name, str) or not name for name in members):
            raise ValueError('Population members require nonempty string identities')
        for config in [*pool, *(member['architecture'] for member in members.values())]:
            if config['input_dim'] != objective.observations.shape[1] or config['output_dim'] != objective.actions+1:
                raise ValueError('Architecture dimensions differ from the objective')
        if max_rounds*len(members) + max(1, len(members)//4) > 512:
            raise ValueError('Full population schedule exceeds observed-plus-pending GP envelope')
        if max_rounds*len(members)*updates_per_round > 65536:
            raise ValueError('Generation schedule exceeds the local checkpoint update envelope')
        # Exact prospective upper allocation for all logical training and halving.
        alive, previous, transfer = 2*len(members), 0, 0
        if (not distillation_rungs or list(distillation_rungs) != sorted(set(distillation_rungs))
                or any(type(r) is not int or not 1 <= r <= 1024 for r in distillation_rungs) or distillation_rungs[-1] < 2):
            raise ValueError('Increasing distillation rungs required')
        for rung in distillation_rungs:
            transfer += alive*(rung-previous)
            previous = rung; alive = max(len(members), (alive+1)//2)
        allocated = generations*max_rounds*len(members)*updates_per_round + (generations-1)*transfer
        if type(max_updates) is not int or max_updates < allocated:
            raise ValueError('Full bounded generational schedule exceeds update budget')
        self.contract = {'schema': 'local_bgpbt_v1', 'objective': objective.identity, 'members': deepcopy(members),
                         'architecture_pool': pool, 'generations': generations, 'max_rounds': max_rounds,
                         'patience': patience, 'updates_per_round': updates_per_round,
                         'distillation_rungs': list(distillation_rungs), 'seed': seed,
                         'max_updates': max_updates, 'allocated_updates': allocated,
                         'generation_transfer_updates': transfer, 'explorer': explorer.contract}
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'program.json'
        with (self.directory/'program.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists():
                self._read()
            else:
                self._write({'contract': self.contract, 'generations': [], 'status': 'pending'})

    def _write(self, value):
        atomic_json(self.path, {'payload': value, 'sha256': _digest(value)})

    def _read(self):
        value = json.loads(self.path.read_text())
        if (_digest(value['payload']) != value['sha256'] or value['payload']['contract'] != self.contract
                or self.objective.identity != self.contract['objective']):
            raise ValueError('BG-PBT checkpoint checksum or identity differs')
        return value['payload']

    def _explorer(self):
        c = self.contract['explorer']
        return BGPopulationExplorer(increment_bound=c['increment_bound'], fit_iterations=c['fit_iterations'])

    def _population(self, index, initial):
        path = self.directory/f'generation-{index}/population.json'
        return PopulationCheckpoint(path, self.objective, None if path.exists() else initial,
            max_updates=self.contract['max_rounds']*len(self.contract['members'])*self.contract['updates_per_round'])

    @staticmethod
    def _architecture_point(architecture):
        return [0, architecture['width']/512, architecture['depth']/4,
                ACTIVATIONS.index(architecture['activation']), NORMALIZATIONS.index(architecture['normalization'])]

    def _proposals(self, state, index):
        best = {}
        for row in state['generations']:
            for observed in row.get('architecture_observations', []):
                key = _digest(observed['architecture'])
                if key not in best or observed['score'] > best[key]['score']:
                    best[key] = observed
        observations = list(best.values())
        gp = TemporalPopulationGP([0, 1], [2, 3], TemporalOptions(family='bgpbt', decay=0))
        gp.observe([self._architecture_point(row['architecture']) for row in observations],
                   [row['score']/self.contract['explorer']['increment_bound'] for row in observations])
        fit = gp.fit(self.contract['explorer']['fit_iterations'])
        pool = self.contract['architecture_pool']
        count = len(self.contract['members'])
        candidates = [self._architecture_point(config) for config in pool]
        bo = gp.suggest_finite(candidates, max(1, count//2))
        remaining = [i for i in range(len(pool)) if i not in bo]
        generator = random.Random(f"{self.contract['seed']}:architecture:{index}")
        random_indices = generator.sample(remaining, 2*count-len(bo))
        indices = bo+random_indices
        return [pool[i] for i in indices], {'bo_indices': bo, 'random_indices': random_indices,
                                           'fit': fit, 'observations': observations,
                                           'gp_options': asdict(gp.options)}

    def run(self):
        with (self.directory/'program.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self._read()
            if state['status'] in {'complete', 'blocked'}:
                return deepcopy(state)
            total_lower = total_upper = 0
            for index in range(self.contract['generations']):
                if index == 0:
                    initial = self.contract['members']
                else:
                    previous = state['generations'][index-1]
                    initial = previous['successors']
                    total_lower += previous['transfer_accounting']['lower']
                    total_upper += previous['transfer_accounting']['upper']
                if index == len(state['generations']):
                    state['generations'].append({'index': index, 'status': 'training', 'best': None,
                                                'failures': 0, 'rounds': 0, 'architecture_observations': []})
                    self._write(state)
                row = state['generations'][index]
                population = self._population(index, initial)
                controller = LocalPBT(self.directory/f'generation-{index}/pbt.json', population,
                                       seed=(self.contract['seed']+index) % 2**32, explorer=self._explorer(), executor=self.executor)
                while row['status'] == 'training':
                    trained = controller.run(row['rounds']+1, updates_per_round=self.contract['updates_per_round'])
                    latest = trained['rounds'][-1]
                    if latest['status'] != 'complete':
                        state.update(status='blocked', reason=latest.get('reason', latest['status']))
                        self._write(state); return deepcopy(state)
                    current = max(latest['scores'].values())
                    if row['best'] is None or current > row['best']:
                        row.update(best=current, failures=0)
                    else:
                        row['failures'] += 1
                    row['rounds'] += 1
                    row['architecture_observations'].extend([
                        {'architecture': latest['training_inputs'][name]['architecture'], 'score': value}
                        for name, value in latest['scores'].items()])
                    if row['failures'] >= self.contract['patience'] or row['rounds'] >= self.contract['max_rounds']:
                        row.update(status='transfer' if index+1 < self.contract['generations'] else 'complete',
                                   trigger='stagnation' if row['failures'] >= self.contract['patience'] else 'maximum_age')
                    self._write(state)
                if row['status'] == 'transfer':
                    if 'proposals' not in row:
                        scores = controller._scores()
                        teacher_id = min(scores, key=lambda name: (-scores[name], name))
                        row['teacher'] = population.snapshot()['members'][teacher_id]
                        row['proposals'], row['architecture_search'] = self._proposals(state, index+1)
                        self._write(state)
                    transfer = ArchitectureGeneration(self.directory/f'transfer-{index}', self.objective,
                        row['teacher'], row['proposals'], survivors=len(initial),
                        rungs=self.contract['distillation_rungs'], seed=(self.contract['seed']+index+1) % 2**32,
                        max_updates=self.contract['generation_transfer_updates'], executor=self.executor)
                    outcome = transfer.run()
                    if outcome['status'] != 'complete':
                        state.update(status='blocked', reason=outcome.get('reason', outcome['status']))
                        self._write(state); return deepcopy(state)
                    row.update(status='complete', successors={str(i): value for i, value in enumerate(outcome['survivors'].values())},
                               transfer_accounting=outcome['accounting'], teacher_sha256=outcome['teacher_sha256'])
                    self._write(state)
                accounting = population.accounting()
                total_lower += accounting['lower']; total_upper += accounting['upper']
            state.update(status='complete', accounting={'lower': total_lower, 'upper': total_upper,
                         'allocated': self.contract['allocated_updates']}, final_members=population.snapshot()['members'])
            if total_upper > self.contract['allocated_updates']:
                raise ValueError('BG-PBT spent work exceeds its allocation')
            self._write(state)
            return deepcopy(state)
