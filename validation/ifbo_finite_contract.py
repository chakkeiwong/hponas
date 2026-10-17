"""Prospective finite reference feasibility, with rejection before integration."""
from copy import deepcopy

CLAIM = 'finite_pretrained_ifbo_feasibility_v1'


def contract():
    return deepcopy({
        'entry':'V15a','version':1,'claim':CLAIM,
        'slots':[{'id':f'{name}-seed-{seed}','initial':initial,'seed':seed}
                 for name,initial in [('late',[.1,1.]),('early',[1.,.1]),('balanced',[1.,1.])]
                 for seed in [0,1]],
        'reference_commit':'421ff96986c8efbe92bd2ab64a4bab49b0dd46fb',
        'weights_sha256':'3703bd004be662794717c857ecb91006768198834e10699ada939fd593f72dc9',
        'reference_boundary':'unchanged upstream component bodies in an explicitly bound small continuous-space harness; not historical benchmark-stack reproduction',
        'model':'rotated diag(1,3) quadratic; eta=1/40+3x/5, x in [0,1]',
        'work_per_arm':{'optimization_updates':24,'certification_updates':8},
        'comparator':'ASHA syne_tune_0_13_0 promotion; eta=2,rungs=1,2,4,8; uniform continuous proposals; no median rule',
        'selection':'minimum latest normalized loss, then minimum numeric configuration ID',
        'decision':'all identities and independent conformance; ifBO certification loss <= ASHA certification loss in every fixed case within floating-point envelope',
        'absolute_tolerance':2e-12,'relative_tolerance':2e-10,'pi_absolute_tolerance':5e-6,
        'inference':'none; six exposed finite comparisons, no general effectiveness or calibration',
        'pass':'permit separately frozen exact finite V15b parity preparation only',
        'fail':'cancel owned ifBO integration and V15b; retain result without favorable rerun',
        'inconclusive':'cancel owned ifBO integration and V15b; no integration budget',
        'allocation':{'generation':1,'reconstructions':3,'processes':2,'wall_seconds_per_process':300,
                      'maximum_phase_seconds':600,'cpu_affinity_count':1,'numerical_threads':1,
                      'gpu':False,'maximum_gradient_updates_including_replays':1536},
    })
