"""A small warped-GP study with exactly reconstructable gradient descent."""
import json
from pathlib import Path
import tempfile

import numpy as np

from hponas import RobustGPSearcher, SearchSpace, Knob, Study, LocalExecutor


def run(directory):
    directory = Path(directory)
    space = SearchSpace([Knob('learning_rate', 'continuous', (.025, .625))])
    searcher = RobustGPSearcher(space, seed=11, initial_random_samples=3,
        candidate_count=16, posterior_samples=32, fit_iterations=20)
    traces = []
    def objective(values, fidelity):
        state = np.array([1., 1.])
        rate = values['learning_rate']
        for step in range(1, 9):
            state -= rate*np.array([1., 3.])*state
            expected = np.array([(1-rate)**step, (1-3*rate)**step])
            np.testing.assert_allclose(state, expected, atol=2e-12, rtol=2e-10)
            traces.append({'rate': rate, 'step': step, 'state': state.tolist()})
        return {'value': float(state@state/2), 'cost': 8.}
    study = Study(searcher, LocalExecutor(), objective, budget=7, maximize=False,
                  study_name='robust-quadratic', checkpoint_dir=directory)
    result = study.run()
    summary = {'trials': result.n_trials, 'best_loss': result.best_value,
        'physical_updates': len(traces), 'accounted_updates': result.total_cost,
        'known_optimum_rate': (1+(1/3)**(1/15))/(3+(1/3)**(1/15)),
        'scope': 'finite numerical implementation; no performance ranking'}
    if summary['physical_updates'] != summary['accounted_updates']:
        raise ValueError('Physical training accounting differs')
    if directory.exists():
        (directory/'robust-example.json').write_text(json.dumps({
            'summary': summary, 'updates': traces, 'last_gp': searcher.last_diagnostics}, indent=2))
    return summary


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hponas-robust-gp-') as directory:
        print(json.dumps(run(directory), indent=2))
