"""APP-01 trained application models; independent of sibling repositories."""
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_ndtr, ndtr, ndtri, softmax
import torch

DESIGN=json.loads(Path(__file__).with_name('design.json').read_text())
STATES=np.array([-1.,0.,1.])
P=softmax(-(STATES[None,None,:]-(.6*STATES[:,None,None]+.5*np.arange(2)[None,:,None]))**2,axis=-1)
R=.3*STATES[:,None]+np.arange(2)[None,:]*(.2-.5*STATES[:,None])
INITIAL=np.array([.25,.5,.25]); LOGGER=np.array([.2,.5,.8]); DISCOUNT=.95

def generate(name,replicate):
    rng=np.random.default_rng(replicate); sizes=DESIGN['rows'][name]; records={}; ids={}
    if name=='forecast':
        n=sum(sizes); x=rng.normal(size=n+4); auxiliary=rng.normal(size=n+4)
        state=rng.normal(scale=math.sqrt(.15/(1-.6**2))); rows=[]
        for t in range(n):
            index=t+3; release=3*((index-2)//3); features=[x[index-j] for j in (1,2,3)]+[auxiliary[release]]
            state=.6*state+rng.normal(scale=math.sqrt(.15))
            y=.6*features[0]-.3*features[1]+.2*features[3]+state+rng.normal(scale=math.sqrt(.4))
            rows.append({'time':t,'x':features,'y':None if t%7==0 else y,'feature_times':[t-j for j in (1,2,3)]+[release-3],'release_times':[t-j+1 for j in (1,2,3)]+[release-1]})
    else: rows=None
    cursor=0
    for role,n in zip(('train','validation','final'),sizes):
        ids[role]=[]
        for i in range(n):
            if name=='forecast': row=rows[cursor];cursor+=1
            elif name=='wallet':
                x=rng.uniform(-1,1); z=.3+.7*x-.2*x*x+.6*rng.normal();row={'x':x,'wallet':float(np.expm1(max(z,0)))}
            elif name=='policy':
                s=int(rng.choice(3,p=INITIAL));trajectory=[]
                for t in range(3):
                    a=int(rng.binomial(1,LOGGER[s])); reward=float(R[s,a]+.1*rng.normal()); next_s=int(rng.choice(3,p=P[s,a]))
                    trajectory.append([s,a,reward,next_s,float(LOGGER[s])]);s=next_s
                row={'trajectory':trajectory}
            elif name=='nas':row={'x':[float(rng.uniform(-.5,.5)),float(rng.uniform(.2,.6))]}
            elif name=='transport':
                z=rng.normal(size=2);row={'x':[float(z[0]),float(z[1]+.35*(z[0]**2-1))]}
            else:raise ValueError(name)
            key=role+'_'+str(i);records[key]=row;ids[role].append(key)
    return records,ids

def forecast_features(rows,lag):
    if any(max(r['release_times'])>r['time'] for r in rows):raise ValueError('Future feature release')
    return np.array([[1.,*r['x'][:lag],r['x'][3]] for r in rows])

def forecast_fit(config,rows):
    observed=[r for r in rows if r['y'] is not None];x=forecast_features(observed,config['lag']);y=np.array([r['y'] for r in observed])
    penalty=np.diag([0.]+[config['ridge']]*(x.shape[1]-1))
    w=np.linalg.solve(x.T@x+penalty,x.T@y)
    return {'weights':w.tolist(),'lag':config['lag'],'variance':config['variance'],'ridge':config['ridge']}

def forecast_score(model,train,score):
    rows=train+score;means=forecast_features(rows,model['lag'])@np.array(model['weights']);m=0.;v=.15/(1-.6**2);trace=[];loss=[]
    for i,row in enumerate(rows):
        if i:m*=.6;v=.36*v+.15
        innovation=None; nll=0.; predicted=m+means[i]; predicted_var=v+model['variance']
        if row['y'] is not None:
            innovation=row['y']-predicted;nll=.5*(math.log(2*math.pi*predicted_var)+innovation**2/predicted_var)
            k=v/predicted_var;m+=k*innovation;v*=model['variance']/predicted_var
            if i>=len(train):loss.append(nll)
        trace.append({'time':row['time'],'mean':float(predicted),'variance':float(predicted_var),'nll':float(nll),'observed':row['y'] is not None})
    if not loss:raise ValueError('No scored observations')
    return float(np.mean(loss)),{'trace':trace,'scored_observations':len(loss)}

def wallet_features(rows,degree):return np.array([[r['x']**j for j in range(degree+1)] for r in rows])

def wallet_objective(w,x,z,sigma,ridge):
    mu=x@w;positive=z>0;u=-mu/sigma
    ll=np.where(positive,-.5*((z-mu)/sigma)**2-math.log(sigma*math.sqrt(2*math.pi))-z,log_ndtr(u))
    d=np.empty_like(mu);d[positive]=(mu[positive]-z[positive])/sigma**2
    d[~positive]=np.exp(-.5*u[~positive]**2-.5*math.log(2*math.pi)-log_ndtr(u[~positive]))/sigma
    loss=-ll.mean()+.5*ridge*np.dot(w[1:],w[1:]);grad=x.T@d/len(x)+ridge*np.r_[0.,w[1:]]
    return float(loss),grad

def wallet_fit(config,rows):
    x=wallet_features(rows,config['degree']);z=np.log1p([r['wallet'] for r in rows]);w=np.linalg.lstsq(x,z,rcond=None)[0]
    result=minimize(wallet_objective,w,args=(x,z,config['sigma'],config['ridge']),jac=True,method='BFGS',options={'gtol':1e-9,'maxiter':1000})
    residual=float(np.max(np.abs(result.jac)))
    if residual>DESIGN['wallet']['stationarity_tolerance']:raise ValueError('Wallet numerical fit failed: '+str(residual))
    return {'weights':result.x.tolist(),**config,'gradient_norm':residual,'iterations':int(result.nit)}

def wallet_score(model,rows):
    x=wallet_features(rows,model['degree']);mu=x@model['weights'];s=model['sigma'];z=np.log1p([r['wallet'] for r in rows])
    nll=-np.where(z>0,-.5*((z-mu)/s)**2-math.log(s*math.sqrt(2*math.pi))-z,log_ndtr(-mu/s))
    mean=np.exp(mu+s*s/2)*ndtr((mu+s*s)/s)-ndtr(mu/s)
    return float(nll.mean()),{'location':mu.tolist(),'zero_probability':ndtr(-mu/s).tolist(),'mean':mean.tolist(),'q90':np.maximum(np.expm1(mu+s*ndtri(.9)),0).tolist()}

def actions(config):return (STATES[None,:]>config['threshold']+config['time_slope']*np.arange(3)[:,None]).astype(int)

def policy_fit(config,rows):
    k=config['smoothing'];counts=np.full((3,2,3),k/3);sums=np.zeros((3,2));n=np.full((3,2),k)
    for row in rows:
        for s,a,r,ns,q in row['trajectory']:
            counts[s,a,ns]+=1;sums[s,a]+=r;n[s,a]+=1
    return {'transition':(counts/counts.sum(axis=-1,keepdims=True)).tolist(),'reward':(sums/n).tolist(),'actions':actions(config).tolist(),'config':config}

def policy_dp(transition,reward,acts):
    transition=np.asarray(transition);reward=np.asarray(reward);values=np.zeros((4,3));qs=np.zeros((3,3,2))
    for t in range(2,-1,-1):
        qs[t]=reward+DISCOUNT*(transition@values[t+1]);values[t]=qs[t,np.arange(3),acts[t]]
    return values,qs

def policy_score(model,rows):
    acts=np.asarray(model['actions']);v,qhat=policy_dp(model['transition'],model['reward'],acts);est=[];max_weight=0.
    for row in rows:
        trajectory=row['trajectory'];value=v[0,trajectory[0][0]];weight=1.
        for t,(s,a,reward,ns,q) in enumerate(trajectory):
            if not 0<q<1:raise ValueError('Logger violates overlap')
            weight*=float(a==acts[t,s])/(q if a else 1-q);max_weight=max(max_weight,weight)
            value+=DISCOUNT**t*weight*(reward+DISCOUNT*v[t+1,ns]-qhat[t,s,a])
        est.append(float(value))
    true,_=policy_dp(P,R,acts);optimal=np.zeros(3)
    for _ in range(3):optimal=np.max(R+DISCOUNT*(P@optimal),axis=1)
    return -float(np.mean(est)),{'contributions':est,'true_value':float(INITIAL@true[0]),'optimal_value':float(INITIAL@optimal),'policy_regret':float(INITIAL@(optimal-true[0])),'maximum_weight':max_weight}

class Network(torch.nn.Module):
    def __init__(self,config,inputs):
        super().__init__();layers=[];size=inputs
        for _ in range(config['depth']):
            layers.extend([torch.nn.Linear(size,config['width'],dtype=torch.float64),torch.nn.Tanh() if config['activation']=='tanh' else torch.nn.SiLU()]);size=config['width']
        layers.append(torch.nn.Linear(size,1,dtype=torch.float64));self.net=torch.nn.Sequential(*layers)
    def forward(self,x):return self.net(x).squeeze(-1)

def save_net(net):return [{'weight':l.weight.detach().tolist(),'bias':l.bias.detach().tolist()} for l in net.net if isinstance(l,torch.nn.Linear)]

def restore_net(config,layers,inputs):
    net=Network(config,inputs)
    with torch.no_grad():
        for l,s in zip((l for l in net.net if isinstance(l,torch.nn.Linear)),layers):l.weight.copy_(torch.tensor(s['weight'],dtype=torch.float64));l.bias.copy_(torch.tensor(s['bias'],dtype=torch.float64))
    return net

def nas_loss(net,x):
    target=torch.exp(-x[:,0]*x[:,1]); y=net(x);jac=torch.autograd.grad(y.sum(),x,create_graph=True)[0]
    reference=torch.stack((-x[:,1]*target,-x[:,0]*target),dim=1)
    losses=torch.cat(((y-target).square()[:,None],(jac-reference).square()),dim=1).mean(0)
    return losses, y,jac,reference

def neural_fit(name,config,rows,seed):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed);net=Network(config,2 if name=='nas' else 1);x=torch.tensor([r['x'] for r in rows],dtype=torch.float64,requires_grad=name=='nas')
        scale=torch.nn.Parameter(torch.tensor(0.,dtype=torch.float64));params=list(net.parameters())+([scale] if name=='transport' else [])
        optimizer=torch.optim.Adam(params,lr=config['learning_rate']);curve=[]
        for epoch in range(1,DESIGN['epochs']+1):
            optimizer.zero_grad()
            if name=='nas':loss=nas_loss(net,x)[0].sum()
            else:
                e=(x[:,1]-net(x[:,:1]))*torch.exp(-scale);loss=(.5*(x[:,0].square()+e.square())+scale+math.log(2*math.pi)).mean()
            if not torch.isfinite(loss):raise ValueError('Nonfinite neural fit')
            loss.backward();optimizer.step()
            if epoch in (1,40,120):curve.append([epoch,float(loss.detach())])
        return {'layers':save_net(net),'config':config,'parameters':sum(p.numel() for p in params),'log_scale':float(scale.detach()),'epochs':DESIGN['epochs'],'curve':curve}

def neural_score(name,model,rows):
    net=restore_net(model['config'],model['layers'],2 if name=='nas' else 1);x=torch.tensor([r['x'] for r in rows],dtype=torch.float64,requires_grad=name=='nas')
    if name=='nas':
        losses,y,jac,ref=nas_loss(net,x);maximum=(jac-ref).abs().max(0).values
        return float(losses.sum().detach()),{'losses':losses.detach().tolist(),'y':y.detach().tolist(),'jacobian':jac.detach().tolist(),'dx_max':float(maximum[0].detach()),'da_max':float(maximum[1].detach()),'parameters':model['parameters']}
    mu=net(x[:,:1]);s=model['log_scale'];z2=(x[:,1]-mu)*math.exp(-s);nll=.5*(x[:,0].square()+z2.square())+s+math.log(2*math.pi)
    return float(nll.mean().detach()),{'shift':mu.detach().tolist(),'latent':torch.stack((x[:,0],z2),dim=1).detach().tolist(),'nll':nll.detach().tolist(),'log_jacobian':s}

def fit_score(name,config,train,score,seed):
    if name=='forecast':model=forecast_fit(config,train);loss,metrics=forecast_score(model,train,score)
    elif name=='wallet':model=wallet_fit(config,train);loss,metrics=wallet_score(model,score)
    elif name=='policy':model=policy_fit(config,train);loss,metrics=policy_score(model,score)
    else:model=neural_fit(name,config,train,seed);loss,metrics=neural_score(name,model,score)
    if not math.isfinite(loss):raise ValueError('Nonfinite score')
    work=(DESIGN['epochs']*len(train)*model['parameters'] if name in ('nas','transport') else (model.get('iterations',1)+1)*len(train))+len(score)
    return model,loss,metrics,work
