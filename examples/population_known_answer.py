"""Ten charged gradient updates across two local architecture generations.

Run in the declared single-CPU environment. This is a finite one-state control
with optimal return 1, not an optimizer-superiority benchmark or a service.
"""
from pathlib import Path
import json
import tempfile

from hponas.bg_pbt import LocalBGPBT
from hponas.population import make_member
from workloads.finite_mdp import FiniteMDP


def run(directory):
    task = FiniteMDP([1], [[[0], [0]]], [[1, 0]], horizon=1,
                     rl_weight=1, policy_weight=5, value_weight=0)
    pool = [dict(width=width, depth=depth, input_dim=1, output_dim=3, activation='tanh')
            for width, depth in [(1, 1), (2, 1), (3, 1), (2, 2)]]
    members = {str(i): make_member(pool[i], {'learning_rate': 0.1, 'momentum': 0.25}, seed=i+5)
               for i in range(2)}
    lower, upper = task.return_bounds
    result = LocalBGPBT(directory, task, members, pool, increment_bound=upper-lower,
                       generations=2, max_rounds=1, patience=1, updates_per_round=1,
                       distillation_rungs=(1, 2), max_updates=10, seed=7, fit_iterations=1).run()
    return {'status': result['status'], 'accounting': result['accounting'],
            'known_optimal_return': 1, 'generations': len(result['generations'])}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='hponas-population-') as directory:
        print(json.dumps(run(Path(directory)), indent=2))
