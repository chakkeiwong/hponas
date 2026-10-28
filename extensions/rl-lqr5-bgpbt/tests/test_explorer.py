import math
import numpy as np

from hponas_rl_bgpbt.explorer import Explorer, point, sample_config
from hponas_rl_lqr5.search import validate


def test_full_conditional_domain_and_inactive_slots():
    rng=np.random.default_rng(90); configs=[sample_config(rng) for _ in range(300)]
    for side in ('actor','critic'):
        assert {len(c[side+'_hiddens']) for c in configs}=={2,3,4}
        assert {w for c in configs for w in c[side+'_hiddens']}==set(range(8,65))
        assert len({c[side+'_lr'] for c in configs})==300
    c=configs[0]; p=point(c,1,4)
    assert len(p)==14
    for side,offset in [('actor',3),('critic',7)]:
        assert p[offset+len(c[side+'_hiddens']):offset+4]==[0.]*(4-len(c[side+'_hiddens']))


def test_temporal_gp_continuous_refinement_and_state_replay():
    e=Explorer(25); c=sample_config(np.random.default_rng(1))
    for i in range(6): e.observe(c,i,5.,5.-.1*i)
    state=e.state(); configs,record=e.propose(c,6,4.)
    twin=Explorer.restore(state); again,other=twin.propose(c,6,4.)
    assert configs==again and record==other
    assert record['fit'] and record['refinement'] and not record['global_optimum']
    assert configs[0]['actor_hiddens']==c['actor_hiddens']
    assert configs[0]['critic_hiddens']==c['critic_hiddens']
    assert record['kernel']['family']=='bgpbt'
    validate(configs[0])


def test_architecture_generation_and_trust_region_restart():
    e=Explorer(17); c=sample_config(np.random.default_rng(4))
    for i in range(12): e.observe(c,i,4.,4.1)
    configs,record=e.propose(c,13,4.1,architecture=True,count=4)
    assert record['restart'] and len(configs)==4
    assert len({tuple(c['actor_hiddens']) for c in record['candidates']})>32
    assert all(validate(c) for c in configs)
