"""Actual variable-size quadratic evaluations for the prospective cost protocol."""
from workloads.tuning_models import quadratic


PROFILES = {'constant': (2, 2, 2), 'cost_decreases': (3, 2, 1), 'cost_increases': (1, 2, 3)}


def evaluate(profile, config):
    if profile not in PROFILES or type(config) is not dict or set(config) != {'eta'}:
        raise ValueError('Unknown quadratic cost task')
    eta = config['eta']
    if type(eta) not in (int, float) or not .025 <= eta <= .625:
        raise ValueError('Learning rate outside the declared cost task')
    size = PROFILES[profile][0 if eta < .225 else 1 if eta < .425 else 2]
    outputs = [quadratic(eta, 8) for _ in range(size)]
    return {'config': dict(config), 'value': sum(o['value'] for o in outputs)/size,
            'cost': sum(o['incremental_steps'] for o in outputs),
            'replicas': [o['trace'] for o in outputs]}
