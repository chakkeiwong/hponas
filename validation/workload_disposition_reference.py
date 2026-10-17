"""Independent rational/analytic checks for small finance and transport models."""
from fractions import Fraction
import math

import numpy as np


def close(actual, expected, label, tolerance=2e-11):
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.allclose(a, b, rtol=tolerance, atol=tolerance):
        raise ValueError('Known-answer workload differs: '+label)


def finance(row):
    identity = row['task']
    preference = Fraction(str(identity['return_preference']))
    rate = Fraction(str(identity['learning_rate']))
    weight = Fraction(1, 4)
    trace = {}
    for index in range(1, row['total_updates']+1):
        gradient = 10*weight-8+preference
        weight = max(0, min(1, weight-rate*gradient))
        trace[index] = {'weight': weight, 'gradient': gradient}
    for observation in row['trace']:
        expected = trace[observation['update']]
        close(observation['weight'], float(expected['weight']), 'portfolio iterate')
        close(observation['gradient'], float(expected['gradient']), 'portfolio gradient')
    variance = weight**2+4*(1-weight)**2
    mean = 2-weight
    close(row['weights'], [float(weight), float(1-weight)], 'portfolio allocation')
    close(row['variance'], float(variance), 'portfolio risk')
    close(row['expected_return'], float(mean), 'portfolio return')
    close(row['objectives'], [float(variance), -float(mean)], 'portfolio vector')
    close(row['training_mean'], [1, 2], 'training means')
    close(row['training_covariance'], [[1, 0], [0, 4]], 'training covariance')
    if row['incremental_updates'] != len(row['trace']):
        raise ValueError('Portfolio incremental accounting differs')
    optimum = max(0, min(1, (8-preference)/10))
    regret = variance-preference*mean-(optimum**2+4*(1-optimum)**2-preference*(2-optimum))
    if regret < 0:
        raise ValueError('Negative exact convex regret')
    return {'status': 'PASS', 'exact_optimal_weight': str(optimum), 'exact_regret': str(regret)}


def transport(row):
    identity = row['task']
    a, rate, initial = [identity[k] for k in ['target_amplitude', 'learning_rate', 'initial_amplitude']]
    curvature = 2*math.tanh(1)**2/3
    def amplitude(index):
        return a+(initial-a)*(1-rate*curvature)**index
    for observation in row['trace']:
        before = amplitude(observation['update']-1)
        close(observation['loss_before'], 2/3+curvature*(before-a)**2/2, 'transport loss')
        close(observation['gradient'], curvature*(before-a), 'transport gradient')
        close(observation['amplitude'], amplitude(observation['update']), 'learned parameter')
    b = amplitude(row['total_updates'])
    close(row['amplitude'], b, 'final learned parameter')
    close(row['loss'], 2/3+curvature*(b-a)**2/2, 'final transport loss')
    expected = [[x, y+b*math.tanh(x)] for x in [-1, 0, 1] for y in [-1, 0, 1]]
    close(row['transformed_points'], expected, 'learned forward transform')
    if len(row['trace']) != row['incremental_updates']:
        raise ValueError('Transport work accounting differs')
    return {'status': 'PASS', 'known_optimal_amplitude': a, 'parameter_error': abs(b-a)}


def transported_gradient(position, amplitude, target_amplitude):
    x, y = position
    delta = amplitude-target_amplitude
    residual = y+delta*math.tanh(x)
    return np.array([x+residual*delta*(1-math.tanh(x)**2), residual])


def transport_transition(position, momentum, *, amplitude, target_amplitude, step_size, steps):
    q, p = np.array(position, dtype=float), np.array(momentum, dtype=float)
    for _ in range(steps):
        p -= step_size*transported_gradient(q, amplitude, target_amplitude)/2
        q += step_size*p
        p -= step_size*transported_gradient(q, amplitude, target_amplitude)/2
    return q, p
