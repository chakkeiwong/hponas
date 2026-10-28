import numpy as np
import torch
from .adapter import Actor
from .reference import sample_policy,linear_cost,riccati
from hponas_rl_lqr_scalar.scoring import action_rows

def evaluate(member,count=4096,seed=1090001):
    actor=Actor(member.module).eval()
    return sample_policy(lambda x,t:action_rows(actor,x,t),spec=member.specification,count=count,seed=seed)

def greedy_report(member):
    spec=member.specification;result=[];optimal=riccati(spec)['optimal_cost']
    for label,encoder in [('q1',member.module.qf_encoder),('q2',member.module.qf_twin_encoder)]:
        with torch.no_grad():p,c=encoder.continuation(torch.tensor([[(30-t)/30] for t in range(30)],dtype=torch.float32))
        p=p.double().numpy();gains=np.array([np.linalg.solve(spec.R+spec.gamma*spec.B.T@v@spec.B,spec.gamma*spec.B.T@v@spec.A) for v in p])
        coefficients=spec.initial_scale*np.eye(spec.states);bounds=[]
        for k in gains:
            bounds.append(float(abs(k@coefficients).sum(1).max()))
            coefficients=np.column_stack(((spec.A-spec.B@k)@coefficients,spec.noise_vector))
        feasible=max(bounds)<=spec.action_limit
        exact=linear_cost(gains,spec) if feasible else None
        result.append(dict(critic=label,gains=gains.tolist(),max_action_bound=max(bounds),feasible=feasible,
            exact_cost=exact,relative_gap_percent=100*(exact-optimal)/optimal if feasible else None,
            qualification='Exact real-arithmetic covariance expectation for feasible learned linear controller; not neural actor or optimal gain labels.'))
    return result

def probes(member):
    spec=member.specification;d=spec.states;m=spec.actions;rng=np.random.default_rng(10999)
    grid=np.column_stack((rng.uniform(-.5,.5,(64,d)),np.tile([1.,.5,1/30,1.],16))).astype(np.float32)
    obs=torch.tensor(grid);ref=obs.clone();ref[:,:-1]*=-1;actor=Actor(member.module).eval()
    with torch.no_grad():
        actions=actor(obs);opposite=actor(ref);z=actor(torch.tensor(np.column_stack((np.zeros((30,d)),np.arange(30,0,-1)/30)),dtype=torch.float32))
    terminal=obs.clone();terminal[:,-1]=1/30;u=torch.tensor(rng.uniform(-.5,.5,(64,m)),dtype=torch.float32,requires_grad=True)
    x=terminal[:,:d];A=torch.tensor(spec.A,dtype=torch.float32);B=torch.tensor(spec.B,dtype=torch.float32)
    y=x@A.T+u@B.T;truth=-x.square().sum(-1)-.1*u.square().sum(-1)-.99*(y.square().sum(-1)+float(spec.noise_vector@spec.noise_vector))
    errors=[]
    for enc in [member.module.qf_encoder,member.module.qf_twin_encoder]:
        q=enc({'obs':terminal,'actions':u})['encoder_out'][:,0];g=torch.autograd.grad(q.sum(),u,retain_graph=True)[0]
        gt=torch.autograd.grad(truth.sum(),u,retain_graph=True)[0]
        item=dict(terminal_value_max_error=float((q-truth).detach().abs().max()),terminal_gradient_max_error=float((g-gt).detach().abs().max()))
        if d==1:
            v=u.mean(-1,keepdim=True).expand_as(u);perp=u-v
            q=enc({'obs':obs,'actions':u})['encoder_out'][:,0];qp=enc({'obs':obs,'actions':v})['encoder_out'][:,0]
            grad=torch.autograd.grad(q.sum(),u)[0]
            item.update(null_value_max_error=float((qp-q-.1*perp.square().sum(-1)).detach().abs().max()),null_gradient_max_error=float((grad-grad.mean(-1,keepdim=True)+.2*perp).detach().abs().max()))
        errors.append(item)
    return dict(odd_action_max_error=float((actions+opposite).abs().max()),zero_action_max_abs=float(z.abs().max()),critics=errors)
