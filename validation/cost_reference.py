"""Independent Gaussian and rational reconstruction of cost-tuning raw evidence.

No production optimizer, cost policy, workload or cost inference is imported.
The retained training examples use exact completed-duration observations.
Censored posterior checks use separate likelihood integration in conformance.
"""
from collections import Counter, defaultdict
from fractions import Fraction as Q
import math

import numpy as np


def close(actual, expected, *, atol=1e-10):
    if not math.isfinite(actual) or not math.isclose(actual, float(expected), rel_tol=1e-9, abs_tol=atol):
        raise ValueError(f'Independent cost reference differs: {actual} != {expected}')


def kernel(a, b, lengthscale):
    radius = np.abs(np.asarray(a)[:, None]-np.asarray(b)[None, :])/.6/lengthscale
    return (1+np.sqrt(5)*radius+5*radius**2/3)*np.exp(-np.sqrt(5)*radius)


def verify(raw):
    summary, snapshot = raw['summary'], raw['snapshot']
    state = snapshot['searcher_state']['legacy']
    contract = state['cost_model']['contract']
    trials, results = snapshot['trials'], snapshot['results']
    count, observed_steps = Counter(), defaultdict(list)
    for row in raw['updates']:
        ident, eta, step = row['trial_id'], row['eta'], row['step']
        if trials[ident]['config']['values'] != {'eta': eta}:
            raise ValueError('Physical training configuration differs')
        observed_steps[ident, row['replica']].append(step)
        rate = Q(eta)
        first, second = (1-rate)**step/10, (1-3*rate)**step
        close(row['value'], first**2+second**2)
        checkpoint = row['checkpoint']
        if checkpoint['iterations'] != step or checkpoint['gradient_steps'] != step or checkpoint['eta'] != eta:
            raise ValueError('Physical checkpoint identity differs')
        close(checkpoint['state'][0], Q(3, 5)*first-Q(4, 5)*second)
        close(checkpoint['state'][1], Q(4, 5)*first+Q(3, 5)*second)
        count[ident] += 1
    for ident, trial in trials.items():
        eta = trial['config']['values']['eta']
        replicas = min(3, 1+int(3*(eta-.025)/.6))
        if set(replica for tid, replica in observed_steps if tid == ident) != set(range(replicas)):
            raise ValueError('Physical replica population differs')
        for replica in range(replicas):
            if observed_steps[ident, replica] != list(range(1, 9)):
                raise ValueError('Physical trajectory omitted or repeated an update')
        if count[ident] != 8*replicas or results[ident]['fidelity'] != 1:
            raise ValueError('Physical work or assigned fidelity differs')
        close(results[ident]['cost'], count[ident])
        rate = Q(eta)
        loss = (1-rate)**16/100+(1-3*rate)**16
        close(results[ident]['objective_value'], -loss if summary['maximize'] else loss)
    if summary['evaluations'] != len(trials):
        raise ValueError('Physical evaluation count differs')
    for total in [state['spent'], summary['accounted_cost'], summary['physical_updates']]:
        close(total, sum(count.values()))
    if set(trials) != set(results) or len(state['trace']) != len(results) or state['pending'] is not None:
        raise ValueError('Completed cost ledger differs')
    xs, ys, spent, max_error, trace = [], [], 0., 0., []
    prior = math.log(contract['default_cost'])-(1+contract['observation_noise']**2)/2
    for index, row in enumerate(state['trace']):
        proposal, observation = row['proposal'], row['observation']
        if spent >= state['total_budget']:
            raise ValueError('Work admitted after cost budget was exhausted')
        ident = observation['trial_id']
        if proposal['config'] != trials[ident]['config']['values'] or observation['spent'] != count[ident]:
            raise ValueError('Proposal or cost observation differs from actual work')
        if observation['kind'] != 'complete' or observation['duration'] != observation['spent']:
            raise ValueError('Completed training duration was not modeled as complete')
        pool = [c['eta'] for c in proposal['pool']]
        if xs:
            matrix = kernel(xs, xs, contract['lengthscale'])+(contract['jitter']+contract['observation_noise']**2)*np.eye(len(xs))
            cross = kernel(pool, xs, contract['lengthscale'])
            mean = prior+cross@np.linalg.solve(matrix, np.log(ys)-prior)
            variance = 1+contract['observation_noise']**2-np.sum(cross*np.linalg.solve(matrix, cross.T).T, axis=1)
            first, second = mean+variance/2, 2*mean+2*variance
        else:
            first = np.full(len(pool), math.log(contract['default_cost']))
            second = 2*first+1+contract['observation_noise']**2
        actual = proposal['predicted']
        for name, expected in [('log_expected_cost', first), ('log_second_moment', second), ('cost_cv_squared', np.expm1(second-2*first))]:
            error = np.max(np.abs(np.asarray(actual[name])-expected))
            max_error = max(max_error, error)
            for a, b in zip(actual[name], expected): close(a, b)
        close(proposal['spent_before'], spent)
        if spent < state['initial_budget']:
            if proposal['base_source'] != 'cheap_first_warmup':
                raise ValueError('Missing cheap-first initial design')
            distances = np.min(np.abs(np.array(pool)[:, None]-xs)/.6, axis=1) if xs else np.full(len(pool), math.inf)
            for a, b in zip(proposal['distances'], distances):
                if a is None and math.isinf(b): continue
                close(a, b)
            remaining, eliminated, use_cost = list(range(len(pool))), [], True
            while len(remaining) > 1:
                victim = sorted(remaining, key=lambda j: ((-first[j] if use_cost else distances[j]), j))[0]
                eliminated.append({'index': victim, 'reason': 'most_expensive' if use_cost else 'closest_to_design'})
                remaining.remove(victim); use_cost = not use_cost
            chosen = remaining[0]
            if proposal['eliminated'] != eliminated or proposal['alpha'] != 1:
                raise ValueError('Initial-design elimination differs')
        else:
            alpha = (state['total_budget']-spent)/(state['total_budget']-state['initial_budget'])
            close(proposal['alpha'], alpha)
            base = np.array([-math.inf if s is None else s for s in proposal['base_scores']])
            chosen = int(np.argmax(base-alpha*first))
        if chosen != proposal['index'] or proposal['pool'][chosen] != proposal['config']:
            raise ValueError('Cost-aware selection differs')
        close(row['objective_observation']['value'], -abs(results[ident]['objective_value']))
        trace.append(proposal['config'])
        xs.append(proposal['config']['eta']); ys.append(count[ident]); spent += count[ident]
        close(row['spent'], spent)
        close(row['alpha_after'], min(1, max(0, (state['total_budget']-spent)/(state['total_budget']-state['initial_budget']))))
    if state['proposals'] != trace:
        raise ValueError('Proposal history differs')
    winner = (max if summary['maximize'] else min)(results, key=lambda tid: results[tid]['objective_value'])
    close(summary['best_value'], results[winner]['objective_value'])
    if summary['best_config'] != trials[winner]['config']['values']:
        raise ValueError('Reported incumbent differs')
    if summary['status'] == 'search_budget_exhausted' and spent < state['total_budget']:
        raise ValueError('Premature budget stop')
    return {'name': summary['name'], 'evaluations': len(trials), 'physical_updates': sum(count.values()),
            'cost_posteriors_reconstructed': len(state['trace']), 'maximum_moment_error': float(max_error), 'trace': trace}
