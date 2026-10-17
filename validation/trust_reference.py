"""Independent linear-algebra and training reconstruction for trust diagnostics.

No maintained GP, kernel, controller, geometry or training function is called.
These diagnostics declare one numerical coordinate. General mixed geometry is
covered separately by its algebraic conformance fixtures.
"""
from collections import Counter
from fractions import Fraction as Q
import math

import numpy as np
import torch


def close(actual, expected, *, atol=1e-10, rtol=1e-8):
    if not np.all(np.isfinite(actual)) or not np.allclose(actual, expected, atol=atol, rtol=rtol):
        raise ValueError('Independent trust reference differs')


def known_value(eta, step):
    eta = Q(eta)
    return (1-eta)**(2*step)/100+(1-3*eta)**(2*step)


def posterior(fit, rows, targets):
    """Gaussian conditioning using explicit Matérn-5/2 covariance matrices."""
    weights = fit['parameters']
    length = float(np.logaddexp(0, weights['covar_module.base_kernel.numeric.raw_lengthscale'])[0][0])
    output = float(np.logaddexp(0, weights['covar_module.raw_outputscale']))
    raw_noise = float(weights['likelihood.noise_covar.raw_noise'][0])
    # Match the declared float64 Interval buffers (constructed in float32 by GPyTorch).
    noise = float(np.float32(1e-6))+(float(np.float32(.1))-float(np.float32(1e-6)))/(1+math.exp(-raw_noise))
    mean = float(weights['mean_module.raw_constant'])
    x = np.array([p[0] for p in rows])
    y = np.array([p[1] for p in rows])
    locations = np.array(targets)
    def covariance(a, b):
        radius = np.abs(a[:, None]-b[None, :])/length
        return output*(1+math.sqrt(5)*radius+5*radius*radius/3)*np.exp(-math.sqrt(5)*radius)
    k = covariance(x, x)+noise*np.eye(len(x))
    cross = covariance(locations, x)
    mu = mean+cross@np.linalg.solve(k, y-mean)
    cov = covariance(locations, locations)-cross@np.linalg.solve(k, cross.T)+noise*np.eye(len(locations))
    return mu, cov


def verify(raw):
    summary, snap = raw['summary'], raw['snapshot']
    state = snap['searcher_state']
    trials, results = snap['trials'], snap['results']
    if summary['maximize'] != state['maximize'] or snap['maximize'] != state['maximize']:
        raise ValueError('Direction identity differs')
    knobs = state['contract']['space']['knobs']
    if len(knobs) != 1 or knobs[0]['name'] not in {'eta', 'eta_index'}:
        raise ValueError('Reference expects the declared one-coordinate quadratic')
    knob = knobs[0]
    def eta(config):
        return config['eta_index']/40 if 'eta_index' in config else config['eta']
    def coordinate(config):
        v = config[knob['name']]
        low, high = knob['bounds']
        if knob['transform'] == 'log':
            return (math.log(v)-math.log(low))/(math.log(high)-math.log(low))
        return (v-low)/(high-low)
    sign = -1 if state['maximize'] else 1
    counts = Counter()
    for update in raw['updates']:
        tid, step = update['trial_id'], update['step']
        config = trials[tid]['config']['values']
        rate = eta(config)
        if update['eta'] != rate or step != counts[tid]+1 or step > 8:
            raise ValueError('Physical training order/configuration differs')
        exact = Q(config['eta_index'], 40) if 'eta_index' in config else Q(rate)
        close(update['value'], float(known_value(exact, step)), atol=1e-13, rtol=1e-10)
        saved = update['checkpoint']
        if saved['iterations'] != step or saved['gradient_steps'] != step or saved['eta'] != rate:
            raise ValueError('Training checkpoint work/configuration differs')
        a, b = (1-exact)**step/10, (1-3*exact)**step
        close(saved['state'], [float(3*a/5-4*b/5), float(4*a/5+3*b/5)], atol=1e-13, rtol=1e-10)
        counts[tid] += 1
    if set(counts) != set(trials) or set(results) != set(trials) or any(n != 8 for n in counts.values()):
        raise ValueError('A complete training job is missing or repeated')
    for tid, result in results.items():
        config = trials[tid]['config']['values']
        exact = Q(config['eta_index'], 40) if 'eta_index' in config else Q(eta(config))
        close(result['objective_value'], sign*float(known_value(exact, 8)), atol=1e-13, rtol=1e-10)
        if (result['cost'] != 8 or result['fidelity'] != 1 or result['status'] != 'completed'
                or result['metadata']['training_steps'] != 8):
            raise ValueError('Endpoint work/fidelity/status differs')
    if (summary['evaluations'] != len(results) or summary['accounted_cost'] != sum(counts.values())
            or summary['physical_updates'] != sum(counts.values())):
        raise ValueError('Physical work summary differs')
    best = min(results, key=lambda tid: sign*results[tid]['objective_value'])
    if summary['best_config'] != trials[best]['config']['values']:
        raise ValueError('Best configuration differs')
    close(summary['best_value'], results[best]['objective_value'])
    proposals = state['proposals']
    if len(proposals) != len(results) or len({str(p['config']) for p in proposals}) != len(proposals):
        raise ValueError('Repeated or missing proposal')
    decoded_means = []
    sample_error = 0.
    for position, proposal in enumerate(proposals):
        if proposal['config'] != trials[proposal['trial_id']]['config']['values']:
            raise ValueError('Proposal configuration differs from trial')
        selection = proposal['selection']
        if selection is None:
            if proposal['kind'] != 'initial':
                raise ValueError('Guided proposal has no posterior evidence')
            continue
        if proposal['kind'] != 'thompson':
            raise ValueError('Initial design claims a guided proposal')
        fit = state['fits'][selection['fit_index']]
        previous = [p for p in proposals[:position] if p['generation'] == proposal['generation']]
        if fit['train_ids'] != [p['trial_id'] for p in previous]:
            raise ValueError('Local GP uses wrong or future generation history')
        values = [sign*results[p['trial_id']]['objective_value'] for p in previous]
        center = previous[int(np.argmin(values))]['config']
        if selection['center'] != center:
            raise ValueError('Center differs from current-generation raw incumbent')
        median, scale = float(np.median(values)), float(np.std(values))
        scale = 1. if scale < 1e-6 else scale
        close([fit['median'], fit['scale']], [median, scale])
        rows = [(coordinate(p['config']), (v-median)/scale) for p, v in zip(previous, values)]
        candidates = selection['candidates']
        if (not candidates or len(candidates) > state['contract']['candidate_count']
                or any(c in [p['config'] for p in proposals[:position]] for c in candidates)
                or len({str(c) for c in candidates}) != len(candidates)):
            raise ValueError('Illegal/repeated posterior candidate set')
        targets = [coordinate(c) for c in candidates]
        lo, hi = selection['region']['numeric_bounds'][knob['name']]
        if any(u < lo-1e-14 or u > hi+1e-14 for u in targets):
            raise ValueError('Candidate lies outside the recorded numeric region')
        mean, covariance = posterior(fit, rows, targets)
        close(selection['posterior_mean'], mean)
        # A separate CPU Generator reproduces standard normal innovations without
        # using GP distribution code or changing the caller's global RNG.
        generator = torch.Generator(device='cpu').manual_seed(selection['sampling_seed'])
        z = torch.randn((len(candidates), 1), dtype=torch.double, generator=generator).numpy().reshape(-1)
        sample = mean+np.linalg.cholesky(covariance)@z
        close(selection['sample'], sample, atol=2e-8, rtol=2e-7)
        sample_error = max(sample_error, float(np.max(np.abs(sample-selection['sample']))))
        if selection['index'] != int(np.argmin(sample)) or proposal['config'] != candidates[selection['index']]:
            raise ValueError('Choice differs from correlated posterior Thompson sample')
        decoded_means.append(mean.tolist())
    options = state['contract']['controller_options']
    center = best_value = None
    length = options['initial_length']
    successes = failures = 0
    pending = None
    generation = -1
    status = 'needs_initialization'
    used = set()
    for row in state['controller']['payload']['journal']:
        action = row['action']
        if action == 'initialize':
            if status not in {'needs_initialization', 'needs_restart'} or pending is not None:
                raise ValueError('Illegal controller initialization')
            generation += 1
            design_generation = int(row['trial_id'].removeprefix('trust-initial-'))
            initial = [p for p in proposals if p['generation'] == design_generation and p['kind'] == 'initial']
            initial_best = min(initial, key=lambda p: sign*results[p['trial_id']]['objective_value'])
            close(row['value'], sign*results[initial_best['trial_id']]['objective_value'])
            close(row['point'], [coordinate(initial_best['config'])])
            center, best_value = row['point'], row['value']
            length, successes, failures = options['initial_length'], 0, 0
            status = 'active'
        elif action == 'propose':
            if status != 'active' or pending is not None or row['trial_id'] in used:
                raise ValueError('Controller pending identity differs')
            p = next(p for p in proposals if p['draw_id'] == row['trial_id'])
            close(row['point'], [coordinate(p['config'])])
            region = p['selection']['region']['numeric_bounds'][knob['name']]
            close(region, [max(0., center[0]-length/2), min(1., center[0]+length/2)])
            pending = {'trial_id': row['trial_id'], 'point': row['point'], 'generation': generation}
            used.add(row['trial_id'])
        elif action == 'observe':
            if not pending or pending['trial_id'] != row['trial_id']:
                raise ValueError('Controller observed an unowned trial')
            p = next(p for p in proposals if p['draw_id'] == row['trial_id'])
            close(row['value'], sign*results[p['trial_id']]['objective_value'])
            success = row['value'] < best_value-options['relative_improvement']*abs(best_value)
            if row['value'] < best_value:
                center, best_value = pending['point'], row['value']
            successes, failures = (successes+1, 0) if success else (0, failures+1)
            if successes == options['success_tolerance']:
                length = min(options['maximum_length'], 2*length)
                successes = failures = 0
            elif failures == options['failure_tolerance']:
                length /= 2
                successes = failures = 0
            if length < options['minimum_length']:
                status = 'needs_restart'
            pending = None
        elif action == 'retire':
            if status != 'active' or pending is not None or row['reason'] != 'empty_typed_region':
                raise ValueError('Illegal empty-region retirement')
            status = 'needs_restart'
        else:
            raise ValueError('Unsupported controller action in noiseless successful reference')
    expected = {'status': status, 'generation': generation, 'best': best_value, 'center': center,
                'length': length, 'successes': successes, 'failures': failures, 'pending': pending}
    if state['controller']['payload']['snapshot'] != expected:
        raise ValueError('Controller snapshot differs from independent recurrence')
    if summary['generations'] != len(state['generations']):
        raise ValueError('Restart summary differs')
    if summary['finite_stop']:
        if ({p['config']['eta_index'] for p in proposals} != set(range(1, 26))
                or summary['status'] != 'search_space_exhausted' or not state['exhausted']):
            raise ValueError('Exhaustion lacks complete finite coverage')
    elif summary['status'] != 'completed' or len(results) != summary['budget']:
        raise ValueError('Study terminal disposition differs')
    if knob['name'] == 'eta_index':
        optimum = min(range(1, 26), key=lambda i: known_value(Q(i, 40), 8))
        optimum_config = {'eta_index': optimum}
        optimum_value = float(known_value(Q(optimum, 40), 8))
    else:
        ratio = (1/300)**(1/15)
        optimum_rate = (1+ratio)/(3+ratio)
        optimum_config = {'eta': optimum_rate}
        optimum_value = float(known_value(Q(optimum_rate), 8))
    regret = sign*summary['best_value']-optimum_value
    if regret < -1e-12:
        raise ValueError('Reported optimum beats the independent mathematical lower bound')
    return {'name': summary['name'], 'physical_updates': sum(counts.values()),
            'posterior_draws_reconstructed': len(decoded_means), 'maximum_sample_error': sample_error,
            'known_optimum': optimum_config, 'known_optimal_loss': optimum_value,
            'descriptive_regret': regret,
            'generations': len(state['generations']), 'trace': [p['config'] for p in proposals]}
