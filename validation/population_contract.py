"""Exposed finite local population conformance; no optimizer ranking claim."""
from copy import deepcopy

CLAIM = 'finite_local_population_conformance_v1'


def contract():
    return deepcopy({
        'version': 1, 'entry': 'V08', 'claim': CLAIM,
        'slots': [
            {'id': 'mdp-algebra', 'kind': 'algebra'},
            {'id': 'temporal-kernels', 'kind': 'gp'},
            {'id': 'categorical-bandit', 'kind': 'bandit'},
            {'id': 'on-policy-transfer', 'kind': 'transfer'},
            {'id': 'unknown-update', 'kind': 'interruption'},
            {'id': 'pbt', 'kind': 'population', 'method': 'pbt', 'rounds': 2, 'recovery': False},
            {'id': 'pbt-acknowledgement', 'kind': 'population', 'method': 'pbt', 'rounds': 2, 'recovery': True},
            {'id': 'pb2-mix', 'kind': 'population', 'method': 'pb2_mix', 'rounds': 2, 'recovery': False},
            {'id': 'bg-restart', 'kind': 'population', 'method': 'bgpbt', 'rounds': 3, 'recovery': False},
            {'id': 'bg-generations', 'kind': 'generations'},
        ],
        'models': 'CPU float64 tanh dense networks, widths 1/2/3, depths 1/2, no normalization, shared policy/value trunk',
        'tasks': 'one-state terminal control and two-state two-step control; exact enumerated expectations',
        'seeds': {'members': [5, 6], 'controller': 7, 'transfer': 11, 'bandit': 17},
        'independent_reference': 'NumPy forward/backprop, enumerated MDP paths, direct GP inverse and bandit probability identities; no production math imports',
        'identity_replay': 'same-runtime complete producer replay, explicitly not an independent proof of optimizer design',
        'numerical_envelope': {'absolute': 2e-10, 'relative': 2e-9,
                               'scope': 'engineering tolerance, not rigorous floating-point error proof'},
        'decision': 'all fixed slots complete, independently conform and reproduce method/seed/options/recovery identity',
        'missingness': 'retain every start/error/partial artifact; no replacement; incomplete is INCONCLUSIVE',
        'release': 'finite local opt-in capability only; no default, superiority, simulation-adapter or distributed acceptance',
        'wall_seconds_per_process': 300, 'cpu_affinity_count': 1, 'numerical_threads': 1, 'gpu': False,
        'maximum_generations': 1, 'maximum_reconstructions': 3,
        'maximum_gradient_updates_per_generation': 32,
        'maximum_unknown_gradient_updates_per_generation': 1,
    })
