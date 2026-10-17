"""Serial DEHB over native Trial/Result interfaces, with transcript recovery.

Derived from the DEHB v0.1.2 numerical algorithm, Apache-2.0; see
licenses/DEHB-Apache-2.0.txt. This owned implementation omits the upstream
benchmark, Dask, ConfigSpace and logging stack. Only rand1/binomial evolution,
random boundary repair and serial, complete restart evaluations are supported.
The unit-cube trace follows the reference; mixed-space decoding is HPO-NAS's
explicit encoder and does not claim ConfigSpace equivalence.
"""
from copy import deepcopy
import math

import numpy as np

from hponas.encoding import SpaceEncoder
from hponas.types import Config, Trial, Result


class DEHBController:
    """Minimize an objective with one outstanding trial and explicit fidelity.

    ``ask`` reissues the same pending identity until ``tell`` commits it. Calling
    code owns dispatch and physical resource accounting: retrying a pending
    identity must not be interpreted as a free or exactly-once evaluation.
    ``best`` defaults to full-fidelity reports, unlike the reference's internal
    incumbent across fidelities. No performance-backed default is implied.
    """
    def __init__(self, space, *, min_fidelity=1, max_fidelity=9, eta=3,
                 mutation_factor=.5, crossover_probability=.5, seed=0):
        self.encoder = SpaceEncoder(deepcopy(space))
        self.search_space = self.encoder.space
        if not 1 <= self.search_space.dim <= 64:
            raise ValueError('DEHB requires 1 to 64 coordinates')
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError('Seed must be an unsigned 32-bit integer')
        for value in [min_fidelity, max_fidelity, eta, mutation_factor, crossover_probability]:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('DEHB controls must be finite numbers')
        if not 0 < min_fidelity < max_fidelity or eta <= 1:
            raise ValueError('Require 0 < min_fidelity < max_fidelity and eta > 1')
        if not 0 <= mutation_factor <= 2 or not 0 <= crossover_probability <= 1:
            raise ValueError('Mutation factor must be in [0,2] and crossover probability in [0,1]')
        ratio = min_fidelity / max_fidelity
        if ratio == 0:
            raise ValueError('Fidelity ratio is outside the supported numerical range')
        levels = -np.log(ratio) / np.log(eta)
        if not math.isfinite(levels) or levels >= 10:
            raise ValueError('Require 2 to 10 fidelity rungs')
        count = int(levels) + 1
        if not 2 <= count <= 10:
            raise ValueError('Require 2 to 10 fidelity rungs')
        self.options = dict(min_fidelity=min_fidelity, max_fidelity=max_fidelity, eta=eta,
                            mutation_factor=mutation_factor, crossover_probability=crossover_probability, seed=seed)
        self.fidelities = (max_fidelity * np.power(eta, -np.linspace(count - 1, 0, count))).tolist()
        sizes = {f: 0 for f in self.fidelities}
        for bracket in range(count):
            for n, f in zip(*self.bracket_schedule(bracket)):
                sizes[f] = max(n, sizes[f])
        if sum(sizes.values()) > 4096:
            raise ValueError('DEHB population exceeds the supported local envelope')
        rng = np.random.default_rng(seed)
        seeds = rng.integers(0, 2**32 - 1, size=count)
        self.populations = {}
        self._next_config_id = 0
        for f, child_seed in zip(self.fidelities, seeds):
            child = np.random.default_rng(int(child_seed))
            n = sizes[f]
            self.populations[f] = {'rng': child, 'vectors': child.uniform(size=(n, self.search_space.dim)),
                'fitness': np.full(n, np.inf), 'ids': np.arange(self._next_config_id, self._next_config_id + n),
                'parent': 0, 'promotion': []}
            self._next_config_id += n
        self.bracket = -1
        self._rung = 0
        self._remaining = []
        self._levels = []
        self._counts = []
        self.pending = None
        self.history = []

    def bracket_schedule(self, index):
        if type(index) is not int or index < 0:
            raise ValueError('Bracket index must be a nonnegative integer')
        count = len(self.fidelities)
        s = count - 1 - index % count
        eta = self.options['eta']
        n0 = int(np.floor(count / (s + 1)) * eta**s)
        return [max(int(n0 * eta**(-i)), 1) for i in range(s + 1)], self.fidelities[-s - 1:]

    def _mutant(self, pop, target, rng):
        pool = np.asarray(pop)
        if len(pool) > 1:
            matches = np.flatnonzero(np.all(pool == target, axis=1))
            if len(matches):
                pool = np.delete(pool, matches[0], axis=0)
        if len(pool) < 3:
            pool = np.concatenate((pool, rng.uniform(size=(3 - len(pool), self.search_space.dim))))
        a, b, c = pool[rng.choice(np.arange(len(pool)), 3, replace=False)]
        return a + self.options['mutation_factor'] * (b - c)

    def _evolve(self, pop, target, rng):
        if len(pop) < 3:
            filler = 4 - len(pop)
            # The reference consumes this initialization before replacing it.
            extra = rng.uniform(size=(filler, self.search_space.dim))
            full = np.concatenate([p['vectors'] for p in self.populations.values()])
            for i in range(filler):
                extra[i] = self._mutant(full, target, rng)
            pop = np.concatenate((pop, extra))
        mutant = self._mutant(pop, target, rng)
        mask = rng.random(self.search_space.dim) < self.options['crossover_probability']
        if not mask.any():
            mask[rng.integers(0, self.search_space.dim)] = True
        vector = np.where(mask, mutant, target)
        outside = np.flatnonzero((vector < 0) | (vector > 1))
        vector[outside] = rng.uniform(size=len(outside))
        return vector

    def _promoted(self, low, high, n):
        source, dest = self.populations[low], self.populations[high]
        evaluated = np.flatnonzero(np.isfinite(source['fitness']))
        ordered = evaluated[np.argsort(source['fitness'][evaluated])]
        if not len(ordered):
            raise RuntimeError('No finite lower-rung report is available for promotion')
        if not dest['promotion']:
            dest['promotion'] = [
                (source['vectors'][i].copy(), int(source['ids'][i])) for i in ordered
                if not np.any(np.all(source['vectors'][i] == dest['vectors'], axis=1))][:n]
        if dest['promotion']:
            return dest['promotion'].pop(0)
        # Use the actual evaluated index; upstream's rare fallback indexes the
        # unfiltered array. They agree for every successful serial trajectory.
        i = ordered[0]
        return source['vectors'][i].copy(), int(source['ids'][i])

    def ask(self):
        if self.pending is not None:
            return self._trial(self.pending)
        if not any(self._remaining):
            self.bracket += 1
            self._counts, self._levels = self.bracket_schedule(self.bracket)
            self._remaining = self._counts.copy()
            self._rung = 0
        while not self._remaining[self._rung]:
            self._rung += 1
        f = self._levels[self._rung]
        low = self._levels[max(0, self._rung - 1)]
        pop = self.populations[f]
        parent = pop['parent']
        target = pop['vectors'][parent]
        n = self._counts[self._rung]
        if self.bracket < len(self.fidelities) and self._rung:
            vector, ident = self._promoted(low, f, n)
        else:
            source = self.populations[low]
            donors = source['vectors'][np.argsort(source['fitness'])[:n]]
            vector = self._evolve(donors, target, pop['rng'])
            ident = self._next_config_id
            self._next_config_id += 1
        pop['parent'] = (parent + 1) % len(pop['vectors'])
        self._remaining[self._rung] -= 1
        self.pending = {'trial_id': f"dehb_{self.options['seed']}_{len(self.history)}",
            'config': vector.tolist(), 'config_id': ident, 'fidelity': f,
            'parent_id': parent, 'bracket_id': self.bracket,
            'values': self.encoder.decode(vector, sampling=True)}
        return self._trial(self.pending)

    def _trial(self, job):
        return Trial(Config(deepcopy(job['values']), str(job['config_id'])), job['trial_id'],
            seed=self.options['seed'] + len(self.history), fidelity=job['fidelity'],
            root_trial_id=job['trial_id'], continuation='restart')

    def tell(self, result):
        if not isinstance(result, Result):
            raise TypeError('DEHB requires a native Result')
        if (result.status != 'completed' or not math.isfinite(result.objective_value)
                or not math.isfinite(result.cost) or result.cost < 0):
            raise ValueError('Only finite completed reports are accepted; failed work remains pending')
        report = dict(trial_id=result.trial_id, objective_value=float(result.objective_value),
                      cost=float(result.cost), fidelity=float(result.fidelity), status=result.status)
        for row in self.history:
            if row['result']['trial_id'] == result.trial_id:
                if row['result'] != report:
                    raise ValueError('Conflicting duplicate DEHB result')
                return
        if self.pending is None or result.trial_id != self.pending['trial_id'] or result.fidelity != self.pending['fidelity']:
            raise ValueError('Result does not match the outstanding DEHB trial and fidelity')
        pop = self.populations[result.fidelity]
        parent = self.pending['parent_id']
        if result.objective_value <= pop['fitness'][parent]:
            pop['vectors'][parent] = self.pending['config']
            pop['ids'][parent] = self.pending['config_id']
            pop['fitness'][parent] = result.objective_value
        self.history.append({'job': deepcopy(self.pending), 'result': report})
        self.pending = None

    def best(self, *, full_fidelity=True):
        rows = [r for r in self.history if not full_fidelity or r['job']['fidelity'] == self.fidelities[-1]]
        return deepcopy(min(rows, key=lambda r: r['result']['objective_value'])) if rows else None

    def state_dict(self):
        return deepcopy({'schema': 'serial_dehb_v1', 'space': self.search_space.to_dict(),
            'options': self.options, 'history': self.history, 'pending': self.pending})

    def load_state_dict(self, state):
        if (not isinstance(state, dict) or set(state) != {'schema', 'space', 'options', 'history', 'pending'}
                or state['schema'] != 'serial_dehb_v1' or state['options'] != self.options
                or state['space'] != self.search_space.to_dict() or not isinstance(state['history'], list)):
            raise ValueError('DEHB checkpoint contract differs')
        restored = type(self)(self.search_space, **self.options)
        for record in state['history']:
            restored.ask()
            if record['job'] != restored.pending:
                raise ValueError('DEHB history does not reproduce the seeded method')
            restored.tell(Result(**record['result']))
        if state['pending'] is not None:
            restored.ask()
            if restored.pending != state['pending']:
                raise ValueError('DEHB pending identity differs from replay')
        self.__dict__.update(restored.__dict__)
