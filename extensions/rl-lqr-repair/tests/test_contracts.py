import json,math
from pathlib import Path
import numpy as np
import pytest
import torch
from hponas_rl_lqr_repair.adapter import SACMember,Actor,digest
from hponas_rl_lqr_repair.catalog import StructuredEncoder
from hponas_rl_lqr_repair.diagnostics import q_values,terminal_q,replace
from hponas_rl_lqr_repair.experiments import CONFIG,ROOT
from hponas_rl_lqr_scalar.adapter import SACMember as Original

@pytest.mark.parametrize('terminal',[False,True])
def test_informed_exact_projection_gradient(terminal):
    torch.manual_seed(21);m=StructuredEncoder([16,16],3,'informed').double()
    with torch.no_grad():
        for p in m.parameters():p.add_(torch.randn_like(p)*.2)
    obs=torch.randn(64,2,dtype=torch.float64);obs[:,-1]=1/30 if terminal else .5
    u=torch.rand(64,3,dtype=torch.float64,requires_grad=True)*2-1
    perp=u-u.mean(-1,keepdim=True);proj=u-perp
    q=m({'obs':obs,'actions':u})['encoder_out'][:,0]
    qp=m({'obs':obs,'actions':proj})['encoder_out'][:,0]
    assert torch.max(abs(qp-q-.1*perp.square().sum(-1)))<1e-13
    g=torch.autograd.grad(q.sum(),u)[0];assert torch.max(abs(g-g.mean(-1,keepdim=True)+.2*perp))<1e-13
    if terminal:assert torch.max(abs(q-terminal_q(obs,u)))<1e-13
    eps=1e-5;direction=torch.randn_like(u)
    qp=m({'obs':obs,'actions':u+eps*direction})['encoder_out'][:,0]
    qm=m({'obs':obs,'actions':u-eps*direction})['encoder_out'][:,0]
    assert torch.max(abs((qp-qm)/(2*eps)-(g*direction).sum(-1)))<1e-9

def test_quadratic_even_and_concave():
    m=StructuredEncoder([8,8],3,'quadratic').double()
    obs=torch.tensor([[.3,.5]],dtype=torch.float64);u=torch.tensor([[.1,-.2,.3]],dtype=torch.float64,requires_grad=True)
    def q(v):return m({'obs':obs,'actions':v})['encoder_out'].sum()
    opposite=obs.clone();opposite[:,0]*=-1
    assert abs(q(u)-m({'obs':opposite,'actions':-u})['encoder_out'].sum())<1e-14
    h=torch.autograd.functional.hessian(q,u).reshape(3,3)
    assert torch.linalg.eigvalsh(h).max()<0

def test_plain_matches_predecessor_and_checkpoint():
    old=Original(CONFIG,10891);new=SACMember(CONFIG,10891)
    assert digest(old.module.state_dict())==digest(new.module.state_dict())
    old.train(320);new.train(320)
    assert digest(old.module.state_dict())==digest(new.module.state_dict())
    restored=SACMember.restore(new.state());new.train(32);restored.train(32)
    assert SACMember.identity(new.state())==SACMember.identity(restored.state())

@pytest.mark.parametrize('method',['quadratic','informed'])
def test_structured_actor_pairing_and_continuation(method):
    plain=SACMember(CONFIG,10892);m=SACMember(CONFIG,10892,method=method)
    assert digest(Actor(plain.module).state_dict())==digest(Actor(m.module).state_dict())
    assert torch.equal(plain.torch_rng,m.torch_rng)
    m.train(320);restored=SACMember.restore(m.state());m.train(32);restored.train(32)
    assert SACMember.identity(m.state())==SACMember.identity(restored.state())

def test_replace_refuses_missing_nonfinite_worse_and_ties():
    assert replace(2.,1.,1.5)
    for v in [None,float('nan'),float('inf'),2.,3.]:assert not replace(2.,v,1.5)
    assert not replace(2.,1.7,1.5)

def test_historical_replacements():
    path=ROOT/'docs/program/evidence/2026-10-28/rl-lqr-07/20261027T164854Z-diagnose-e084a525/diagnose-result.json'
    r=json.loads(path.read_text())
    # Use recorded recipient and child values; no replay training or counterfactual claim.
    rows=r['population']
    events=[event for row in rows for event in row['replacements']]
    assert len(events)==18
    assert sum(e['new_cost']>e['old_cost'] for e in events)==10
    assert all(min(e['old_cost'],e['new_cost'])<=e['old_cost'] for e in events)
    assert sum(not replace(e['old_cost'],e['new_cost']) for e in events)==10
