"""Two-asset allocation tuning with exact train/evaluation moments.

This finite deterministic model is a numerical workload, not market evidence.
Population covariance uses divisor N; coordinates are long-only simplex weights.
"""
from numbers import Real

import numpy as np


def _real(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError('Finite real finance coordinate required')
    return float(value)


def evaluate(config, iterations=8, checkpoint=None):
    if not isinstance(config, dict) or set(config) != {'learning_rate', 'return_preference'}:
        raise ValueError('Explicit learning_rate and return_preference required')
    rate, preference = (_real(config[key]) for key in ['learning_rate', 'return_preference'])
    if not 0 < rate < 0.2 or not 0 <= preference <= 12:
        raise ValueError('Finance coordinates exceed the stable finite envelope')
    if type(iterations) is not int or not 0 <= iterations <= 32:
        raise ValueError('Finance fidelity must be an integer in [0,32]')
    training = np.array([[2, 4], [0, 4], [2, 0], [0, 0]], dtype=float)
    mean = training.mean(axis=0)
    centered = training-mean
    covariance = centered.T@centered/len(training)
    offset = np.sqrt(2)
    evaluation = mean+np.array([[offset, 0], [-offset, 0], [0, 2*offset], [0, -2*offset]])
    identity = {'schema': 'two_asset_portfolio_v1', 'learning_rate': rate,
                'return_preference': preference, 'initial_weight': 0.25,
                'training_rows': training.tolist(), 'evaluation_rows': evaluation.tolist(),
                'objective': 'population_variance_minus_preference_times_mean',
                'work_unit': 'one projected full-gradient update'}
    completed, weight = 0, 0.25
    if checkpoint is not None:
        if (not isinstance(checkpoint, dict) or set(checkpoint) != {'identity', 'updates', 'weight'}
                or checkpoint['identity'] != identity or type(checkpoint['updates']) is not int
                or not 0 <= checkpoint['updates'] <= iterations):
            raise ValueError('Finance checkpoint identity or fidelity differs')
        completed, weight = checkpoint['updates'], _real(checkpoint['weight'])
        # The exact piecewise-linear iteration checks coherent checkpoint edits.
        expected = 0.25
        for _ in range(completed):
            expected = min(1.0, max(0.0, expected-rate*(10*expected-8+preference)))
        if not 0 <= weight <= 1 or abs(weight-expected) > 2e-12:
            raise ValueError('Finance checkpoint differs from its declared trajectory')
    trace = []
    for step in range(completed, iterations):
        allocation = np.array([weight, 1-weight])
        gradient = np.array([1., -1.])@(2*covariance@allocation-preference*mean)
        weight = float(np.clip(weight-rate*gradient, 0, 1))
        trace.append({'update': step+1, 'weight': weight, 'gradient': float(gradient)})
    allocation = np.array([weight, 1-weight])
    returns = evaluation@allocation
    expected_return = float(returns.mean())
    variance = float(np.mean((returns-expected_return)**2))
    return {'method': 'projected_gradient_mean_variance', 'task': identity,
            'weights': allocation.tolist(), 'expected_return': expected_return, 'variance': variance,
            'objectives': [variance, -expected_return], 'directions': ['minimize', 'minimize'],
            'training_mean': mean.tolist(), 'training_covariance': covariance.tolist(),
            'evaluation_returns': returns.tolist(), 'trace': trace,
            'incremental_updates': iterations-completed, 'total_updates': iterations,
            'checkpoint': {'identity': identity, 'updates': iterations, 'weight': weight},
            'scientific_acceptance': False}
