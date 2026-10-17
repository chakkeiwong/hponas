"""Prospective cost protocol method runner and same-runtime identity replay.

Numerical and physical-work truth is checked independently by cost_acceptance.
Replay checks the declared production method, seed and observation delivery; it
is not an independent proof of the optimizer algorithm. This is preparation,
not a registered acceptance entry or permission to launch an official campaign.
"""
from copy import deepcopy
import hashlib
import json
import time

from validation.cost_acceptance import POLICY, slots, summarize, verify_observation


METHODS = {
    'cost_gp': 'hponas.cost_searcher.CostAwareProposalSearcher',
    'gp': 'hponas.searchers_gp.GPqLogEISearcher',
    'random': 'hponas.legacy_searchers.RandomSearcher',
    'sobol': 'hponas.legacy_searchers.SobolSearcher',
}


def make_searcher(method, seed):
    from hponas.space import Knob, SearchSpace
    from hponas.cost_searcher import CostAwareProposalSearcher
    from hponas.searchers_gp import GPqLogEISearcher
    from hponas.legacy_searchers import RandomSearcher, SobolSearcher

    if method not in METHODS or type(seed) is not int or seed not in POLICY['seeds']:
        raise ValueError('Undeclared cost method or seed')
    space = SearchSpace([Knob('eta', 'continuous', tuple(POLICY['eta_bounds']))])
    if method in {'random', 'sobol'}:
        return (RandomSearcher if method == 'random' else SobolSearcher)(space, seed=seed)
    base = GPqLogEISearcher(space, seed=seed, **POLICY['gp'])
    if method == 'gp':
        return base
    return CostAwareProposalSearcher(space, base, total_budget=POLICY['work_budget'],
        initial_budget=POLICY['initial_budget'], candidate_count=POLICY['candidate_count'],
        default_cost=POLICY['default_cost'], cost_unit='declared_work_units', seed=seed)


def state_hash(searcher):
    return hashlib.sha256(json.dumps(searcher.state_dict(), sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def observe(searcher, row):
    # The proposal API maximizes. The physical model returns a loss.
    searcher.observe({'config': deepcopy(row['config']), 'value': -row['value'],
                     'cost': row['cost'], 'status': 'completed'})


def run_slot(profile, seed, method):
    """Execute one declared slot, retaining every completed physical evaluation.

    The caller supplies the process deadline and retains the returned record.
    Any failed attempt makes the slot incomplete, even after enough work was
    spent. Unknown partial work cannot be silently accepted as zero.
    """
    from workloads.cost_quadratic import evaluate

    if (profile, seed, method) not in slots() or type(seed) is not int:
        raise ValueError('Undeclared cost slot')
    record = {'profile': profile, 'seed': seed, 'method': method,
              'method_class': METHODS[method], 'observations': [], 'timings': [],
              'error': None, 'failed_attempt': None, 'final_state_sha256': None}
    searcher = make_searcher(method, seed)
    spent, phase, config = 0, 'proposal', None
    try:
        for _ in range(POLICY['max_trials_per_study']):
            if spent >= POLICY['work_budget']:
                break
            phase, config = 'proposal', None
            before = time.monotonic()
            config = searcher.propose(1)[0]
            proposed = time.monotonic()
            phase = 'objective'
            row = evaluate(profile, config)
            evaluated = time.monotonic()
            record['observations'].append(row)
            spent += row['cost']
            phase = 'observation_delivery'
            observe(searcher, row)
            record['timings'].append({'proposal_seconds': proposed-before,
                'objective_seconds': evaluated-proposed, 'observation_seconds': time.monotonic()-evaluated})
        record['final_state_sha256'] = state_hash(searcher)
    except Exception as exc:
        record['error'] = type(exc).__name__+': '+str(exc)
        record['failed_attempt'] = {'phase': phase, 'config': deepcopy(config),
                                    'physical_work_unknown': phase == 'objective'}
    record['summary'] = summarize(profile, record['observations'])
    if record['error'] is not None:
        record['summary']['status'] = 'incomplete'
    return record


def replay_run(run):
    """Reject method relabeling, seed changes, omitted work and state changes."""
    expected = {'profile', 'seed', 'method', 'method_class', 'observations', 'timings',
                'error', 'failed_attempt', 'final_state_sha256', 'summary'}
    if (type(run) is not dict or set(run) != expected
            or type(run['seed']) is not int
            or (run['profile'], run['seed'], run['method']) not in slots()
            or run['method_class'] != METHODS[run['method']]):
        raise ValueError('Cost method identity differs')
    if run['error'] is not None or run['failed_attempt'] is not None:
        return {'status': 'INCONCLUSIVE', 'method_identity_verified': False}
    if (type(run['observations']) is not list
            or len(run['observations']) > POLICY['max_trials_per_study']):
        raise ValueError('Cost trial cap or observation schema differs')
    report = summarize(run['profile'], run['observations'])
    if report != run['summary']:
        raise ValueError('Cost summary differs')
    if report['status'] != 'complete':
        return {'status': 'INCONCLUSIVE', 'method_identity_verified': False}
    if type(run['timings']) is not list or len(run['timings']) != len(run['observations']):
        raise ValueError('Timing ledger differs')
    import math
    for timing in run['timings']:
        if (type(timing) is not dict or set(timing) != {'proposal_seconds', 'objective_seconds', 'observation_seconds'}
                or any(type(t) not in (float, int) or not math.isfinite(t) or t < 0 for t in timing.values())):
            raise ValueError('Invalid measured timing')
    searcher = make_searcher(run['method'], run['seed'])
    for row in run['observations']:
        verify_observation(run['profile'], row)
        config = searcher.propose(1)[0]
        if config != row['config']:
            raise ValueError('Method/seed replay proposal differs')
        observe(searcher, row)
    if state_hash(searcher) != run['final_state_sha256']:
        raise ValueError('Method replay terminal state differs')
    return {'status': 'PASS', 'method_identity_verified': True,
            'proposals_replayed': len(run['observations']), 'scientific_acceptance': False}
