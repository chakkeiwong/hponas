"""Bounded cost-aware tuning with physical quadratic updates and known answers."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time

from hponas import CostAwareProposalSearcher, Knob, LocalExecutor, SearchSpace, Study
from hponas.events import EventLog
from hponas.searchers_gp import GPqLogEISearcher
from hponas.store import Store
from workloads.tuning_models import quadratic


class ReplicatedQuadratic:
    """A varying-size quadratic job: all replicas have the same exact endpoint.

    Three equal eta intervals have one, two and three independently executed
    replicas. Each replica performs eight updates; the objective is their mean
    terminal loss. This isolates known evaluation cost from objective quality.
    """
    def __init__(self, *, maximize=False):
        self.maximize, self.updates = maximize, []

    def __call__(self, config, trial_id):
        eta = config['eta']
        replicas = min(3, 1+int(3*(eta-.025)/.6))
        values = []
        for replica in range(replicas):
            checkpoint = None
            for step in range(1, 9):
                result = quadratic(eta, step, checkpoint)
                checkpoint = result['checkpoint']
                self.updates.append({'trial_id': trial_id, 'replica': replica, 'step': step,
                                     'eta': eta, 'value': result['value'], 'checkpoint': deepcopy(checkpoint)})
            values.append(result['value'])
        value = sum(values)/len(values)
        return {'value': -value if self.maximize else value, 'cost': 8*replicas,
                'metadata': {'work_unit': 'gradient_updates', 'replicas': replicas, 'steps_per_replica': 8}}


def run_one(directory, name, *, recovery=False, maximize=False, total_budget=200):
    target = directory/name
    target.mkdir()
    space = SearchSpace([Knob('eta', 'continuous', (.025, .625))])
    def make(seed):
        base = GPqLogEISearcher(space, seed=seed, n_fantasies=32, raw_samples=16, n_restarts=2)
        return CostAwareProposalSearcher(space, base, total_budget=total_budget, initial_budget=24,
                                         candidate_count=8, default_cost=16, seed=seed)
    workload = ReplicatedQuadratic(maximize=maximize)
    store = Store(target/'store.db')
    kwargs = dict(budget=7, maximize=maximize, study_name=name, checkpoint_dir=target,
                  event_log=EventLog(target/'events.jsonl'), store=store)
    study = Study(make(13), LocalExecutor(), workload, **kwargs)
    start, boundary = time.monotonic(), None
    if recovery:
        for _ in range(2):
            study._new_trial(); tid = study._pending[0]
            study._accept(study.executor.execute(study.trials[tid], workload))
        study._new_trial(); study.save_checkpoint()
        boundary = deepcopy(study._snapshot())
        restored = Study(make(987), LocalExecutor(), workload, **kwargs)
        restored.load_checkpoint(target/(name+'_checkpoint.json'))
        if restored.searcher.get_state() != study.searcher.get_state():
            raise ValueError('Cost checkpoint changed pending or fitted state')
        study.executor.shutdown()
        study = restored
    result = study.run()
    elapsed = time.monotonic()-start
    measured = sum(r.metadata['execution']['elapsed_seconds'] for r in result.history)
    summary = {'name': name, 'maximize': maximize, 'recovery': recovery,
               'evaluations': result.n_trials, 'physical_updates': len(workload.updates),
               'accounted_cost': result.total_cost, 'total_budget': total_budget,
               'elapsed_seconds': elapsed, 'evaluation_seconds': measured,
               'other_seconds': elapsed-measured, 'best_config': result.best_config.values,
               'best_value': result.best_value, 'status': result.status}
    with (target/'raw.json').open('x') as handle:
        json.dump({'summary': summary, 'updates': workload.updates, 'snapshot': study._snapshot(),
                   'recovery_boundary': boundary}, handle, indent=2, allow_nan=False)
        handle.write('\n')
    store.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('runs'))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='cost-', dir=args.output_dir))
    cases = [('complete', {}), ('pending-recovery', {'recovery': True}),
             ('maximize', {'maximize': True}), ('budget-stop', {'total_budget': 40})]
    results = [run_one(directory, name, **options) for name, options in cases]
    with (directory/'summary.json').open('x') as handle:
        json.dump({'scope': 'method implementation; no scientific cost-performance acceptance', 'runs': results}, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'directory': str(directory), 'cases': len(results),
                      'physical_updates': sum(r['physical_updates'] for r in results), 'scientific_acceptance': False}))


if __name__ == '__main__':
    main()
