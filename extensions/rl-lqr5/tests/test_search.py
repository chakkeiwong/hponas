from copy import deepcopy
import numpy as np
import pytest

from hponas_rl_lqr5.search import (search_space, encode, decode, validate,
                                  capability_report, require_bgpbt_support)


def test_conditional_widths_all_depths_and_continuous_rate_sampling():
    space = search_space(); rng = np.random.default_rng(73)
    rows = [space.sample_config(rng) for _ in range(512)]
    configs = [decode(row) for row in rows]
    assert all(encode(c) == r for c, r in zip(configs, rows))
    assert {(len(c['actor_hiddens']), len(c['critic_hiddens'])) for c in configs} == {
        (a, b) for a in (2, 3, 4) for b in (2, 3, 4)}
    assert {w for c in configs for side in ('actor', 'critic') for w in c[side+'_hiddens']} == set(range(8, 65))
    assert len({c['actor_lr'] for c in configs}) == len(configs)
    assert len({c['critic_lr'] for c in configs}) == len(configs)
    assert any(c['actor_lr'] != c['critic_lr'] for c in configs)
    # Geometric midpoint of each log-scale rate coordinate.
    from hponas.encoding import SpaceEncoder
    midpoint = decode(SpaceEncoder(space).decode(np.full(space.dim, .5), sampling=True))
    assert np.isclose(midpoint['actor_lr'], np.sqrt(1e-5*1e-2))


def test_exact_boundary_shapes_rates_and_inactive_width_refusal():
    c = {'actor_hiddens': [8, 64], 'critic_hiddens': [64, 37, 8, 16],
         'actor_lr': 1e-5, 'critic_lr': 1e-2}
    assert decode(encode(c)) == c
    row = encode(c); row['actor_d3_w1'] = 8
    with pytest.raises(ValueError, match='must not'):
        decode(row)
    for key, value in [('actor_hiddens', [8]), ('critic_hiddens', [8]*5),
                       ('actor_hiddens', [7, 16]), ('critic_hiddens', [64, 65]),
                       ('actor_hiddens', [8., 16]), ('actor_lr', 0.),
                       ('critic_lr', float('nan')), ('critic_lr', .011)]:
        bad = deepcopy(c); bad[key] = value
        with pytest.raises(ValueError):
            validate(bad)


def test_capability_cannot_imply_existing_sac_bgpbt_support():
    report = capability_report()
    assert report['architectures_per_network'] == 10744443
    assert report['actor_critic_architecture_pairs'] == 10744443**2
    assert not report['current_local_bgpbt_sac_supported']
    with pytest.raises(NotImplementedError, match='adapter'):
        require_bgpbt_support()
