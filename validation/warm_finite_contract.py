"""Prospective fixed mathematical warm-start scope, independent of service load."""

CLAIM = 'finite_ranked_warm_start_conformance_v1'


def contract():
    return {'entry': 'V12', 'version': 2, 'claim': CLAIM,
        'slots': [
            {'id': 'matching', 'history_curvature': 2., 'target_curvature': 2., 'eligible': True, 'maximize': False, 'scale': 1.},
            {'id': 'shifted', 'history_curvature': 3., 'target_curvature': 1., 'eligible': True, 'maximize': False, 'scale': 1.},
            {'id': 'cold', 'history_curvature': 2., 'target_curvature': 2., 'eligible': False, 'maximize': False, 'scale': 1.},
            {'id': 'ties', 'history_curvature': 0., 'target_curvature': 2., 'eligible': True, 'maximize': False, 'scale': 1.},
            {'id': 'maximize', 'history_curvature': 2., 'target_curvature': 2., 'eligible': True, 'maximize': True, 'scale': 1.},
            {'id': 'scale', 'history_curvature': 2., 'target_curvature': 2., 'eligible': True, 'maximize': False, 'scale': 100.}],
        'space': {'eta': [.125, .875]}, 'history_seeds': [3, 3, 5, 7, 9, 11],
        'history_names': ['A', 'B', 'C', 'held-out', 'wrong-space', 'future'],
        'history_trials': 4, 'target_trials': 6, 'target_seed': 13,
        'selected_seeds': 3, 'updates_per_trial': 4,
        'model': 'w0=1; gradient h*w; w[k]=(1-eta*h)^k; value=sign*(offset+scale*w[4]^2)',
        'reference': 'independent powers, pairwise rational midranks and uniform RNG coordinates',
        'selection': 'within-study exact midrank; study/trial tie break; physical configuration deduplication',
        'eligibility': 'held-out task, transformed space, future cutoff and incompatible family excluded',
        'recovery': 'interrupt warm target after two commits before trial 2 work; exact Store checkpoint and pending suggestion',
        'absolute_tolerance': 2e-12, 'relative_tolerance': 2e-10,
        'inference': 'finite conformance only; no empirical speedup, default or distributed service claim',
        'decision': 'all six complete cases agree in selection, provenance, actual work, recovery and mathematical outcomes',
        'allocation': {'generation': 1, 'reconstructions': 3, 'processes': 2,
            'wall_seconds_per_process': 300, 'maximum_phase_seconds': 600,
            'cpu_affinity_count': 1, 'numerical_threads': 1, 'gpu': False,
            'maximum_gradient_updates': 864, 'reconstruction_gradient_updates': 0},
        'pass': 'Finite opt-in ranked seeding only; empirical improvement/default/service remain unestablished.',
        'fail': 'Withhold finite warm acceptance; retain raw failure and repair prospectively.',
        'inconclusive': 'Withhold acceptance and retain incomplete work; never replace a consumed run.'}
