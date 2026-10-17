"""Prospective exposed finite Tier-1 corpus; no inferential/default claims."""
from copy import deepcopy

ENTRIES = ('V04-T1', 'V06', 'V09', 'V10', 'V11a', 'V11b', 'V13', 'V-COST')
CLAIM = 'tier1_finite_known_answer_v1'


def slots(entry):
    if entry == 'V04-T1':
        return [{'id': name, 'kind': 'trust', **kw} for name, kw in [
            ('integer', {}), ('integer-pending', {'recovery': 'pending'}),
            ('integer-restart', {'recovery': 'restart'}), ('maximize', {'maximize': True}),
            ('continuous-linear', {'transform': 'none'}), ('continuous-log', {'transform': 'log'}),
            ('finite-exhaustion', {'finite_stop': True})]]
    if entry == 'V06':
        rows = [{'id': 'full', 'kind': 'multifidelity', 'order': 'ascending',
                 'policy': 'resume', 'median': False, 'full': True}]
        for order in ['ascending', 'descending', 'alternating']:
            for median in [False, True]:
                for policy in ['resume', 'restart']:
                    rows.append({'id': f'{order}-{policy}-median{int(median)}',
                                 'kind': 'multifidelity', 'order': order, 'policy': policy, 'median': median})
        rows.append({'id': 'crash-resume', 'kind': 'multifidelity', 'order': 'ascending',
                     'policy': 'resume', 'median': False, 'crash': True})
        return rows
    if entry == 'V09':
        return [{'id': method, 'kind': 'vector', 'method': method, 'seed': 13, 'trials': 6}
                for method in ['random', 'qlognehvi', 'chebyshev', 'nsgaii']]
    if entry == 'V10':
        return [{'id': 'advisory-reversal', 'kind': 'advisory', 'restore': False},
                {'id': 'advisory-recovery', 'kind': 'advisory', 'restore': True}]
    if entry in {'V11a', 'V11b'}:
        good = entry == 'V11a'
        # Quadratic T=8 finite optimum and worst point follow from exact enumeration.
        default = 18 if good else 1
        rows = [{'id': 'categorical', 'kind': 'priorband', 'default': default},
                {'id': 'uniform', 'kind': 'priorband', 'default': None, 'uniform': True}]
        rows += [{'id': 'integer-'+t, 'kind': 'priorband', 'default': default,
                  'product_transform': t} for t in ['none', 'log']]
        rows += [{'id': label, 'kind': 'pibo', 'advice': advice, 'seed': 731031,
                  'trials': 6, 'center': .45 if good else .025}
                 for label, advice in [('pibo', 'good' if good else 'wrong'), ('gp', 'none')]]
        if not good:
            rows += [{'id': 'wrong-pending', 'kind': 'priorband', 'default': default, 'cap': 1},
                     {'id': 'wrong-restart', 'kind': 'priorband', 'default': default, 'continuation': 'restart'}]
        return rows
    if entry == 'V13':
        return [{'id': name, 'kind': 'gaussian', **kw} for name, kw in [
            ('stable', {'step_size': .5, 'steps': 3, 'frequency': 1.}),
            ('scaled', {'step_size': .25, 'steps': 3, 'frequency': 2.}),
            ('resume', {'step_size': .5, 'steps': 3, 'frequency': 1., 'resume': True}),
            ('resonance', {'step_size': 1., 'steps': 3, 'frequency': 1.}),
            ('unstable', {'step_size': 3., 'steps': 4, 'frequency': 1.}),
        ]] + [{'id': 'diagnostic-boundaries', 'kind': 'diagnostics'}]
    if entry == 'V-COST':
        from validation.cost_acceptance import slots as cost_slots
        return [{'id': f'{profile}-{seed}-{method}', 'kind': 'cost',
                 'profile': profile, 'seed': seed, 'method': method}
                for profile, seed, method in cost_slots()]
    raise ValueError('Unknown finite Tier-1 entry')


def contract(entry):
    spec = {'version': 1, 'claim': CLAIM, 'entry': entry, 'slots': slots(entry),
            'wall_seconds_per_process': 300, 'maximum_reconstructions': 3,
            'cpu_affinity_count': 1, 'numerical_threads': 1, 'gpu': False,
            'missingness': 'retain_all_slots_no_replacement_incomplete_is_inconclusive',
            'decision': 'all_frozen_slots_independently_conform_and_production_identity_replays',
            'replay_scope': 'same_runtime_identity_only_not_independent_algorithm_proof',
            'release': 'finite_opt_in_capability_only_no_default_or_population_inference',
            'numerics': 'fixed_reference_engineering_tolerances_not_rigorous_error_bounds',
            'fixture_source': ['validation/tier1_producers.py', 'validation/tier1_reference.py',
                               'examples', 'workloads', 'validation/*_reference.py']}
    if entry == 'V-COST':
        from validation.cost_acceptance import contract as cost_contract
        spec['cost_contract'] = cost_contract()
    if entry == 'V13':
        spec['sampler'] = {'seed': 12, 'draws': 32, 'warmup': 8,
                           'initial_positions': [-3., -1., 1., 3.],
                           'scope': 'ordinary_univariate_Gaussian_HMC_no_SBC_or_general_calibration'}
    return deepcopy(spec)
