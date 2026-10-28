"""Policy-independent action-value checks; never substitutes hard Q for soft Q."""
import math
import numpy as np
import torch
from hponas_rl_lqr_scalar.reference import LQRSpec,riccati,sample_policy
from hponas_rl_lqr_scalar.scoring import action_rows
from .adapter import Actor

def q_values(member,obs,u):
    m=member.module;b={'obs':obs,'actions':u}
    a=m._qf_forward_train_helper(b,m.qf_encoder,m.qf)
    c=m._qf_forward_train_helper(b,m.qf_twin_encoder,m.qf_twin)
    return a,c,torch.minimum(a,c)

def terminal_q(obs,u):
    x=obs[:,0];y=.92*x+u.sum(-1)/math.sqrt(3)
    return -x.square()-.1*u.square().sum(-1)-.99*(y.square()+.025**2)

def diagnostics(member):
    actor=Actor(member.module).eval()
    grid=torch.tensor([[x,(30-t)/30] for t in (0,15,29) for x in (-.5,-.1,0.,.1,.5)])
    with torch.no_grad():actions=actor(grid)
    obs=torch.tensor([[x,1/30] for x in np.linspace(-.5,.5,9)],dtype=torch.float32)
    u=torch.tensor([[.2,-.3,.1],[.4,.4,.4],[-.2,0.,.3]]*3,dtype=torch.float32,requires_grad=True)
    projection=u.mean(-1,keepdim=True).expand_as(u);perp=u-projection
    old=q_values(member,obs,u);new=q_values(member,obs,projection);exact=.1*perp.square().sum(-1)
    stats=[]
    for label,q,qp in zip(('q1','q2','min'),old,new):
        grad=torch.autograd.grad(q.sum(),u,retain_graph=True)[0];gn=grad-grad.mean(-1,keepdim=True)
        stats.append(dict(critic=label,projection_error_max=float((qp-q-exact).detach().abs().max()),
            null_gradient_error_max=float((gn+.2*perp).detach().abs().max()),
            wrong_rankings=int(((qp-q<0)&(exact>1e-8)).sum()),
            terminal_rmse=float((q-terminal_q(obs,u)).detach().square().mean().sqrt())))
    return dict(critics=stats,grid_actions=actions.tolist(),zero_action_bias=float(actions[[2,7,12]].square().mean().sqrt()),
                odd_error_max=float((actions.reshape(3,5,3)+actions.reshape(3,5,3).flip(1)).abs().max()))

def evaluate(member,count=4096,seed=1080001):
    actor=Actor(member.module).eval()
    return sample_policy(lambda x,t:action_rows(actor,x,t),spec=LQRSpec(),count=count,seed=seed)

def replace(incumbent,candidate,donor=None):
    values=[incumbent,candidate]+([] if donor is None else [donor])
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):return False
    return candidate<incumbent and (donor is None or candidate<=donor)
