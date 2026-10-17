"""Prospective finite cost/quality contract and independent physical-work oracle.

This module imports no production searcher, cost model or numerical workload.
Finite conformance supplies no statistical superiority or default claim.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction as Q
import math


POLICY = {
    'entry': 'V-COST', 'version': 1, 'claim': 'finite_cost_quality_conformance_v1',
    'methods': ['cost_gp', 'gp', 'random', 'sobol'], 'seeds': [731021, 731022],
    'profiles': {'constant': [2, 2, 2], 'cost_decreases': [3, 2, 1], 'cost_increases': [1, 2, 3]},
    'eta_bounds': [.025, .625], 'breakpoints': [.225, .425], 'steps': 8,
    'work_budget': 72, 'max_trials_per_study': 9, 'study_count': 24,
    'max_physical_updates': 2048, 'initial_budget': 9, 'candidate_count': 16,
    'default_cost': 16, 'gp': {'n_fantasies': 32, 'raw_samples': 32, 'n_restarts': 2},
    'cost_unit': 'gradient_updates', 'generation_seconds': 300, 'reconstruction_seconds': 300,
    'cpu_threads': 1, 'gpu': False,
    'inference': 'none_exposed_finite_corpus_no_superiority_or_noninferiority_test',
    'performance_disposition': 'report_every_fixed_slot_at_common_work_budget_no_ranking_threshold',
    'default_activation': False,
}


def contract():
    return deepcopy(POLICY)


def slots():
    return [(profile, seed, method) for profile in POLICY['profiles']
            for seed in POLICY['seeds'] for method in POLICY['methods']]


def optimum():
    """Unique minimizer from f'=0; f''>0 on the declared stable interval."""
    with localcontext() as ctx:
        ctx.prec = 70
        ratio = (-Decimal(300).ln()/15).exp()
        eta = (1+ratio)/(3+ratio)
        loss = (1-eta)**16/100+(1-3*eta)**16
        return {'eta': float(eta), 'value': float(loss), 'decimal_eta': str(eta), 'decimal_value': str(loss)}


def exact_loss(eta, step=8):
    rate = Q(eta)
    return (1-rate)**(2*step)/100+(1-3*rate)**(2*step)


def replicas(profile, eta):
    if profile not in POLICY['profiles'] or type(eta) not in (int, float) or not math.isfinite(eta) or not .025 <= eta <= .625:
        raise ValueError('Unknown cost profile or learning-rate domain')
    index = sum(eta >= b for b in POLICY['breakpoints'])
    return POLICY['profiles'][profile][index]


def close(actual, expected):
    # At most 3 replicas of eight stable 2D matrix updates and squared norms.
    # gamma4096 is a conservative binary64 engineering envelope, fixed before
    # evaluation. It is not an optimizer-effect margin or a probability bound.
    epsilon = 2.**-52
    tolerance = 4096*epsilon/(1-4096*epsilon)*max(1., abs(float(expected)))
    if type(actual) not in (float, int) or not math.isfinite(actual) or abs(actual-float(expected)) > tolerance:
        raise ValueError('Independent known-answer numerical value differs')


def verify_observation(profile, row):
    if not isinstance(row, dict) or set(row) != {'config', 'value', 'cost', 'replicas'}:
        raise ValueError('Incomplete physical observation')
    if type(row['config']) is not dict or set(row['config']) != {'eta'}:
        raise ValueError('Observation configuration differs')
    eta = row['config']['eta']; size = replicas(profile, eta)
    if (type(row['cost']) is not int or row['cost'] != 8*size
            or type(row['replicas']) is not list or len(row['replicas']) != size):
        raise ValueError('Observation work or replica count differs')
    for trace in row['replicas']:
        if not isinstance(trace, list) or len(trace) != 8:
            raise ValueError('A physical trajectory is incomplete')
        for step, update in enumerate(trace, 1):
            if (type(update) is not dict or set(update) != {'iteration', 'state', 'value'}
                    or type(update['iteration']) is not int or update['iteration'] != step):
                raise ValueError('Physical update identity differs')
            if not isinstance(update['state'], list) or len(update['state']) != 2:
                raise ValueError('Physical state dimension differs')
            first, second = (1-Q(eta))**step/10, (1-3*Q(eta))**step
            close(update['state'][0], Q(3, 5)*first-Q(4, 5)*second)
            close(update['state'][1], Q(4, 5)*first+Q(3, 5)*second)
            close(update['value'], first**2+second**2)
    close(row['value'], exact_loss(eta))
    return row['cost']


def summarize(profile, observations, *, work_budget=None):
    """Completion-time incumbent loss and its left-continuous work integral.

    All physical work is paid; an over-budget completion cannot improve the
    incumbent at the common budget. Initial loss at work zero is exactly 101/100.
    """
    budget = POLICY['work_budget'] if work_budget is None else work_budget
    if type(budget) is not int or budget <= 0 or not isinstance(observations, list):
        raise ValueError('Positive integer work budget and observation list required')
    spent, incumbent, area, inside = 0, Q(101, 100), Q(0), 0
    for row in observations:
        if spent >= budget:
            raise ValueError('Work admitted after the budget was exhausted')
        cost = verify_observation(profile, row)
        completion = spent+cost
        area += max(0, min(completion, budget)-spent)*incumbent
        spent = completion
        if completion <= budget:
            inside += 1
            incumbent = min(incumbent, exact_loss(row['config']['eta']))
    if spent < budget:
        area += (budget-spent)*incumbent
    answer = optimum(); floor = answer['value']; scale = 1.01-floor
    # Fractions keep the integral exact until the independently computed
    # algebraic optimum enters descriptive normalization.
    return {'status': 'complete' if spent >= budget else 'incomplete',
            'work_budget': budget, 'physical_updates': spent, 'overrun': max(0, spent-budget),
            'completed_within_budget': inside, 'final_loss': float(incumbent),
            'integrated_loss': float(area), 'optimal_loss': floor,
            'normalized_final_regret': (float(incumbent)-floor)/scale,
            'normalized_regret_auc': (float(area)/budget-floor)/scale,
            'performance_superiority': False, 'automatic_default': False}


def verify_slots(runs):
    """Validate numerical data only; method identity needs separate replay.

    A PASS here is not an acceptance verdict. A frozen source/runtime, method
    replay and the registered protocol audit must also be verified.
    """
    if not isinstance(runs, list): raise ValueError('Fixed run roster required')
    if any(type(r) is not dict or not {'profile', 'seed', 'method', 'observations', 'summary'} <= set(r)
           or type(r['seed']) is not int or type(r['observations']) is not list for r in runs):
        raise ValueError('Malformed cost run')
    actual = [(r['profile'], r['seed'], r['method']) for r in runs]
    if actual != slots(): raise ValueError('Cost campaign slot roster differs')
    rebuilt = []
    for run in runs:
        if len(run['observations']) > POLICY['max_trials_per_study']:
            raise ValueError('Trial cap exceeded')
        report = summarize(run['profile'], run['observations'])
        if run.get('error') is not None:
            report['status'] = 'incomplete'
        if run['summary'] != report:
            raise ValueError('Stored cost/quality summary differs from raw reconstruction')
        rebuilt.append(report)
    if sum(r['physical_updates'] for r in rebuilt) > POLICY['max_physical_updates']:
        raise ValueError('Physical work envelope exceeded')
    return {'status': 'PASS' if all(r['status'] == 'complete' for r in rebuilt) else 'INCONCLUSIVE',
            'scope': 'numerical_data_only', 'runs': rebuilt, 'method_identity_verified': False,
            'scientific_acceptance': False, 'superiority_claim': False, 'default_activation': False}
