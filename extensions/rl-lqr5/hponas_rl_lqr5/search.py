"""Conditional per-layer width search and independent continuous SAC rates."""
import math

from hponas import Knob, SearchSpace


RATE_BOUNDS = (1e-5, 1e-2)
ARCHITECTURES_PER_NETWORK = sum(57**depth for depth in (2, 3, 4))


def search_space():
    knobs = []
    for side in ('actor', 'critic'):
        knobs.append(Knob(side+'_depth', 'categorical', [2, 3, 4]))
        for depth in (2, 3, 4):
            knobs.extend(Knob(f'{side}_d{depth}_w{i+1}', 'ordinal', (8, 64),
                              condition=(side+'_depth', depth)) for i in range(depth))
        knobs.append(Knob(side+'_lr', 'continuous', RATE_BOUNDS, transform='log'))
    return SearchSpace(knobs)


def validate(config):
    if not isinstance(config, dict) or set(config) != {'actor_hiddens', 'critic_hiddens', 'actor_lr', 'critic_lr'}:
        raise ValueError('Explicit actor/critic architectures and continuous learning rates required')
    for side in ('actor', 'critic'):
        shape = config[side+'_hiddens']; lr = config[side+'_lr']
        if not isinstance(shape, (list, tuple)) or not 2 <= len(shape) <= 4 or any(
                type(w) is not int or not 8 <= w <= 64 for w in shape):
            raise ValueError('Each network needs 2-4 hidden layers with integer widths 8-64')
        if isinstance(lr, bool) or not isinstance(lr, (int, float)) or not math.isfinite(lr) or not RATE_BOUNDS[0] <= lr <= RATE_BOUNDS[1]:
            raise ValueError('Learning rate must be continuous within the declared range')
    return {side+suffix: list(config[side+suffix]) if suffix == '_hiddens' else float(config[side+suffix])
            for side in ('actor', 'critic') for suffix in ('_hiddens', '_lr')}


def decode(row):
    space = search_space()
    if set(row)-{knob.name for knob in space.knobs}:
        raise ValueError('Unknown search coordinate')
    space.validate_config(row)
    config = {}
    for side in ('actor', 'critic'):
        depth = row[side+'_depth']
        if type(depth) is not int:
            raise ValueError('Depth must be an integer')
        config[side+'_hiddens'] = [row[f'{side}_d{depth}_w{i+1}'] for i in range(depth)]
        config[side+'_lr'] = row[side+'_lr']
    return validate(config)


def encode(config):
    config = validate(config); row = {}
    for side in ('actor', 'critic'):
        shape = config[side+'_hiddens']; row[side+'_depth'] = len(shape)
        row[side+'_lr'] = config[side+'_lr']
        row.update({f'{side}_d{len(shape)}_w{i+1}': width for i, width in enumerate(shape)})
    search_space().validate_config(row)
    return row


def capability_report():
    return {'method_suitable_in_principle': True, 'current_local_bgpbt_sac_supported': False,
            'architectures_per_network': ARCHITECTURES_PER_NETWORK,
            'actor_critic_architecture_pairs': ARCHITECTURES_PER_NETWORK**2,
            'learning_rates': {'actor': list(RATE_BOUNDS), 'critic': list(RATE_BOUNDS),
                              'kind': 'independent_continuous_log'},
            'required_extensions': ['RLlib SAC population state/optimizer/replay adapter',
                'conditional actor/critic architecture and two-rate Bayesian exploration',
                'Gaussian policy and twin soft-Q distillation with explicit target/Adam policy',
                'charged transfer, recovery, parallel population and fresh-confirmation evidence'],
            'training_transitions': 0, 'global_optimality_claim': False}


def require_bgpbt_support():
    raise NotImplementedError('LocalBGPBT currently supports shared finite-MDP policy/value models; '
                              'RLlib SAC population transfer and this conditional search need an adapter')
