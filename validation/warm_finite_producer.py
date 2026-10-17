"""Real tiny training studies for the finite ranked-history contract."""
from copy import deepcopy
import json
from pathlib import Path
import time

from hponas import Knob, LocalExecutor, RandomSearcher, SearchSpace, Study
from hponas.operations import backup_database
from hponas.persistence import atomic_json
from hponas.store import Store
from hponas.warm_history import target_context
from hponas.warm_start import RankedWarmStartSearcher
from validation.warm_finite_contract import contract


class PlannedInterruption(KeyboardInterrupt):
    """Stop before physical work at a fixed recovery boundary."""


def space(transform='none'):
    return SearchSpace([Knob('eta', 'continuous', (.125, .875), transform=transform)])


def execute_slot(slot, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    store = Store(directory/'store.db')
    records = []
    sequence = 0

    def train(sid, searcher, curvature, scale=1., offset=0., recover=False):
        nonlocal sequence
        updates = []
        interrupted = False
        recovery = None

        def objective(config, trial_id):
            nonlocal sequence, interrupted
            if recover and not interrupted and trial_id == sid+'_trial_2':
                interrupted = True
                raise PlannedInterruption()
            state = 1.
            for step in range(1, 5):
                state -= config['eta']*curvature*state
                update = {'trial_id': trial_id, 'eta': config['eta'], 'step': step, 'state': state}
                # Preserve partial work if the process terminates before raw.json.
                with (directory/'physical-updates.jsonl').open('a') as handle:
                    handle.write(json.dumps({'sequence': sequence, 'study': sid, **update})+'\n')
                    handle.flush()
                sequence += 1
                updates.append(update)
            value = offset+scale*state**2
            return {'value': -value if slot['maximize'] else value, 'cost': 4.}

        def make(candidate):
            return Study(candidate, LocalExecutor(), objective,
                budget=6 if sid in {'target', 'cold'} else 4,
                maximize=slot['maximize'], study_name=sid, store=store)
        study = make(searcher)
        if recover:
            try:
                study.run()
            except PlannedInterruption:
                before = store.load_study_snapshot(sid)
                atomic_json(directory/'recovery-before.json', before)
                replacement = RankedWarmStartSearcher(RandomSearcher(space(), seed=13), searcher.selection)
                study = make(replacement)
                study.load_checkpoint()
                after = json.loads(json.dumps(study._snapshot()))
                atomic_json(directory/'recovery-after.json', after)
                recovery = {'before': before, 'after': after}
            else:
                raise ValueError('Fixed warm recovery boundary was not exercised')
        result = study.run()
        row = {'study_id': sid, 'curvature': curvature, 'scale': scale, 'offset': offset,
            'space': study.searcher.search_space.to_dict(), 'seed': study.searcher.seed,
            'updates': updates, 'result': result.to_dict(),
            'snapshot': json.loads(json.dumps(study._snapshot())), 'recovery': recovery}
        records.append(row)
        atomic_json(directory/(sid+'-training.json'), row)
        return row

    try:
        histories = []
        cutoff = None
        for index, name in enumerate(contract()['history_names']):
            if name == 'future':
                cutoff = time.time()
            source_space = space('log' if name == 'wrong-space' else 'none')
            train(name, RandomSearcher(source_space, seed=contract()['history_seeds'][index]),
                  slot['history_curvature'], scale=slot['scale']*(3. if name == 'B' else 1.),
                  offset=100. if name == 'B' else 0.)
            history = store.freeze_warm_history(name,
                task_id='evaluation' if name == 'held-out' else 'history-'+name,
                model_family='scalar-quadratic' if slot['eligible'] else 'other-family',
                task_domain='gradient-tuning', objective_key='endpoint-squared-error')
            histories.append(history)
        context = target_context(space(), study_id='target', task_id='evaluation',
            model_family='scalar-quadratic', task_domain='gradient-tuning',
            objective_key='endpoint-squared-error', direction='maximize' if slot['maximize'] else 'minimize',
            history_cutoff=cutoff)
        warm = RankedWarmStartSearcher.from_store(RandomSearcher(space(), seed=13), store, context=context, n=3)
        selection = deepcopy(warm.selection)
        initial = warm.get_state()
        train('target', warm, slot['target_curvature'], recover=True)
        train('cold', RandomSearcher(space(), seed=13), slot['target_curvature'])
        backup = backup_database(directory/'store.db', directory/'store-backup')
        return {'slot': slot, 'histories': histories, 'context': context,
            'selection': selection, 'initial_warm': initial, 'studies': records,
            'physical_updates': sequence, 'backup': backup}
    finally:
        store.close()
