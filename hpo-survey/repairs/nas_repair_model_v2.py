"""Controlled MLP training repair; target and derivative limits remain inherited."""
import itertools,time
import numpy as np
import torch
from common import *
from models import Network,nas_loss,save_net
from references import close,net_numpy
from app02_trace import score,LIMITS
BOUNDARY=np.array([[-.5,.2],[-.5,.6],[.5,.2],[.5,.6],[0.,.2],[0.,.6],[-.5,.4],[.5,.4]])
def mesh(n):return np.array(list(itertools.product(np.linspace(-.5,.5,n),np.linspace(.2,.6,n))))
def train_points(seed,geometry):
    if geometry=='tensor':return mesh(9)
    p=np.random.default_rng(seed).uniform([-.5,.2],[.5,.6],(81,2));p[:8]=BOUNDARY;return p
def evaluate(model,points):
    s=score(model,points);net=Network(model['config'],2)
    with torch.no_grad():
        for layer,saved in zip((l for l in net.net if isinstance(l,torch.nn.Linear)),model['layers']):layer.weight.copy_(torch.tensor(saved['weight'],dtype=torch.float64));layer.bias.copy_(torch.tensor(saved['bias'],dtype=torch.float64))
    x=torch.tensor(points,dtype=torch.float64,requires_grad=True);loss,y,jac,ref=nas_loss(net,x)
    close(float(loss.sum().detach()),s['loss']);close((jac-ref).abs().max(0).values.detach().numpy(),[s['dx_max'],s['da_max']]);return s
def train(seed,width,geometry,recipe):
    start=time.monotonic();torch.set_num_threads(1);torch.manual_seed(seed)
    cfg={'width':width,'depth':2,'activation':'silu','learning_rate':.03};net=Network(cfg,2)
    points=train_points(seed,geometry);x=torch.tensor(points,dtype=torch.float64,requires_grad=True)
    weights=torch.tensor([1.,1/LIMITS['dx']**2,1/LIMITS['da']**2],dtype=torch.float64) if recipe!='raw' else torch.ones(3,dtype=torch.float64)
    opt=torch.optim.Adam(net.parameters(),lr=.03);curve=[];calls=0
    for epoch in range(480):
        opt.zero_grad();x.grad=None;loss=(nas_loss(net,x)[0]*weights).sum();assert torch.isfinite(loss);loss.backward();opt.step();calls+=1
        if epoch in (0,119,479):curve.append({'epoch':epoch+1,'loss':float(loss.detach())})
    if recipe=='polish':
        opt=torch.optim.LBFGS(net.parameters(),lr=.5,max_iter=80,max_eval=100,tolerance_grad=1e-10,tolerance_change=1e-13,line_search_fn=None)
        n=[0]
        def closure():
            opt.zero_grad();x.grad=None;loss=(nas_loss(net,x)[0]*weights).sum();assert torch.isfinite(loss);loss.backward();n[0]+=1;assert n[0]<=100;return loss
        opt.step(closure);calls+=n[0]
    model={'config':cfg,'layers':save_net(net),'parameters':sum(v.numel() for v in net.parameters()),'epochs':480,'recipe':recipe,'geometry':geometry,'seed':seed,'curve':curve,'closure_calls':calls}
    return {'model':model,'train_points':points.tolist(),'train':evaluate(model,points),'seconds':time.monotonic()-start}
