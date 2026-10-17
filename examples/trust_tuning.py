"""Bounded trust-region tuning of actual quadratic training with known answers."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile

from hponas import Knob, LocalExecutor, SearchSpace, Study, TrustRegionSearcher
from hponas.events import EventLog
from hponas.trust_controller import Controller, Options
from workloads.tuning_models import quadratic


class FullQuadratic:
    """One fixed-fidelity evaluation executes eight physical gradient updates."""
    def __init__(self, *, maximize=False):
        self.maximize = maximize
        self.updates = []

    def __call__(self, config, trial_id):
        eta = config['eta_index']/40 if 'eta_index' in config else config['eta']
        state = None
        for step in range(1, 9):
            actual = quadratic(eta, step, state)
            if actual['incremental_steps'] != 1:
                raise ValueError('Expected one actual gradient update')
            state = actual['checkpoint']
            self.updates.append({'trial_id': trial_id, 'eta': eta, 'step': step,
                                 'value': actual['value'], 'checkpoint': deepcopy(state)})
        return {'value': -actual['value'] if self.maximize else actual['value'], 'cost': 8,
                'metadata': {'work_unit': 'gradient_updates', 'training_steps': 8}}


def run_one(directory, name, *, transform=None, recovery=None, maximize=False, finite_stop=False):
    target = directory/name
    target.mkdir()
    space = (SearchSpace([Knob('eta_index', 'integer', (1, 25))]) if transform is None else
             SearchSpace([Knob('eta', 'continuous', (.025, .625), transform=transform)]))
    # Explicit short-region diagnostic exercises restart; it is not a tuned default.
    options = Options(1, .5, .25, 1., 3, 1, relative_improvement=.001, geometry='typed_product_v1')
    def make(seed):
        return TrustRegionSearcher(space, seed=seed, initial_random=3, candidate_count=32,
                                   fit_steps=20, controller=Controller(options), maximize=maximize)
    workload = FullQuadratic(maximize=maximize)
    event_log = EventLog(target/'events.jsonl')
    budget = 30 if finite_stop else 12
    study = Study(make(0), LocalExecutor(), workload, budget=budget, study_name=name,
                  maximize=maximize, checkpoint_dir=target, event_log=event_log)
    boundary = None
    if recovery:
        for _ in range(6):
            study._new_trial()
            tid = study._pending[0]
            study._accept(study.executor.execute(study.trials[tid], workload))
        if recovery == 'pending':
            study._new_trial()
        study.save_checkpoint()
        boundary = deepcopy(study._snapshot())
        study.executor.shutdown()
        resumed = Study(make(987), LocalExecutor(), workload, budget=budget, study_name=name,
                        maximize=maximize, checkpoint_dir=target, event_log=event_log)
        resumed.load_checkpoint(target/(name+'_checkpoint.json'))
        if resumed.searcher.get_state() != study.searcher.get_state():
            raise ValueError('Checkpoint changed trust state')
        study = resumed
    result = study.run()
    summary = {'name': name, 'transform': transform, 'recovery': recovery, 'maximize': maximize,
               'finite_stop': finite_stop, 'budget': budget, 'evaluations': result.n_trials,
               'physical_updates': len(workload.updates), 'accounted_cost': result.total_cost,
               'best_config': result.best_config.values, 'best_value': result.best_value,
               'generations': len(study.searcher._generations), 'status': result.status}
    with (target/'raw.json').open('x') as handle:
        json.dump({'summary': summary, 'updates': workload.updates, 'recovery_boundary': boundary,
                   'snapshot': study._snapshot()}, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('runs'))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='trust-', dir=args.output_dir))
    cases = [('integer', {}), ('integer-pending', {'recovery': 'pending'}),
             ('integer-restart', {'recovery': 'restart'}), ('maximize', {'maximize': True}),
             ('continuous-linear', {'transform': 'none'}), ('continuous-log', {'transform': 'log'}),
             ('finite-exhaustion', {'finite_stop': True})]
    runs = [run_one(directory, name, **options) for name, options in cases]
    with (directory/'summary.json').open('x') as handle:
        json.dump({'scope': 'trust implementation conformance; no V04-T1 acceptance', 'runs': runs}, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'directory': str(directory), 'cases': len(runs),
                      'physical_updates': sum(r['physical_updates'] for r in runs), 'V04_T1_accepted': False}))


if __name__ == '__main__':
    main()
