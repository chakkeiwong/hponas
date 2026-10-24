"""Independent NumPy/scalar references; never imports trained-model code."""
import itertools
import math
import numpy as np
from scipy.integrate import quad

def close(a,b,tol=1e-8):
    a,b=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a,b,rtol=tol,atol=tol):
        raise AssertionError('Independent reconstruction differs')

def normal_cdf(x):return .5*math.erfc(-x/math.sqrt(2))

def net_numpy(model,x):
    x=np.asarray(x,dtype=float);n,d=x.shape;j=np.broadcast_to(np.eye(d),(n,d,d)).copy();a=x
    for index,layer in enumerate(model['layers']):
        w=np.array(layer['weight']);a=a@w.T+layer['bias'];j=np.einsum('ij,njk->nik',w,j)
        if index<len(model['layers'])-1:
            if model['config']['activation']=='tanh':a=np.tanh(a);derivative=1-a*a
            else:
                sigmoid=1/(1+np.exp(-a));derivative=sigmoid+a*sigmoid*(1-sigmoid);a=a*sigmoid
            j*=derivative[:,:,None]
    return a[:,0],j[:,0,:]

def forecast_reference(model,train,score):
    rows=train+score;lag=model['lag'];features=np.array([[1.,*r['x'][:lag],r['x'][3]] for r in rows]);means=features@model['weights']
    time=np.arange(len(rows));cov=.15/(1-.6**2)*.6**np.abs(time[:,None]-time[None,:])+model['variance']*np.eye(len(rows))
    observed=[];residuals=[];trace=[];loss=[]
    for i,row in enumerate(rows):
        if any(t>row['time'] for t in row['release_times']):raise ValueError('Future release')
        m=means[i];v=cov[i,i]
        if observed:
            c=cov[i,observed];inv=np.linalg.solve(cov[np.ix_(observed,observed)],np.column_stack((residuals,c)))
            m+=c@inv[:,0];v-=c@inv[:,1]
        nll=0.
        if row['y'] is not None:
            nll=.5*(math.log(2*math.pi*v)+(row['y']-m)**2/v);observed.append(i);residuals.append(row['y']-means[i])
            if i>=len(train):loss.append(nll)
        trace.append({'time':row['time'],'mean':float(m),'variance':float(v),'nll':float(nll),'observed':row['y'] is not None})
    return float(np.mean(loss)),trace

def wallet_reference(model,rows):
    w=model['weights'];s=model['sigma'];nll=[];means=[];zero=[];mu=[]
    for row in rows:
        loc=math.fsum(c*row['x']**j for j,c in enumerate(w));z=math.log1p(row['wallet']);mu.append(loc)
        nll.append(-math.log(normal_cdf(-loc/s)) if z==0 else .5*((z-loc)/s)**2+math.log(s*math.sqrt(2*math.pi))+z)
        zero.append(normal_cdf(-loc/s));means.append(math.exp(loc+s*s/2)*normal_cdf((loc+s*s)/s)-normal_cdf(loc/s))
    return math.fsum(nll)/len(nll),{'location':mu,'zero_probability':zero,'mean':means}

def wallet_mean_quad(mu,sigma):
    # Finite 12-sigma truncation has negligible Gaussian tail at these scales.
    lo=max(0.,mu-12*sigma);hi=max(0.,mu+12*sigma)
    return quad(lambda z:math.expm1(z)*math.exp(-.5*((z-mu)/sigma)**2)/(sigma*math.sqrt(2*math.pi)),lo,hi,epsabs=1e-12,epsrel=1e-12)[0]

def policy_truth():
    states=[-1,0,1];transition=[];reward=[]
    for s in states:
        t=[];r=[]
        for action in (0,1):
            v=[math.exp(-(next_s-(.6*s+.5*action))**2) for next_s in states];t.append([x/math.fsum(v) for x in v]);r.append(.3*s+action*(.2-.5*s))
        transition.append(t);reward.append(r)
    return np.array(transition),np.array(reward)

def enumerate_value(transition,reward,acts,start=None,time=0):
    if time==3:return 0.
    initial=[.25,.5,.25] if start is None else [float(i==start) for i in range(3)];value=0.
    for path in itertools.product(range(3),repeat=4-time):
        probability=initial[path[0]];cash=0.
        for j in range(3-time):
            t=time+j;s=path[j];a=acts[t][s];cash+=.95**j*reward[s][a];probability*=transition[s][a][path[j+1]]
        value+=probability*cash
    return value

def policy_reference(model,rows):
    acts=model['actions'];p=model['transition'];r=model['reward'];v=np.zeros((4,3));q=np.zeros((3,3,2))
    for t in range(3):
        for s in range(3):v[t,s]=enumerate_value(p,r,acts,start=s,time=t)
    for t in range(3):
        for s in range(3):
            for a in range(2):q[t,s,a]=r[s][a]+.95*math.fsum(p[s][a][j]*v[t+1,j] for j in range(3))
    contributions=[]
    for row in rows:
        value=v[0,row['trajectory'][0][0]];weight=1.
        for t,(s,a,cash,ns,propensity) in enumerate(row['trajectory']):
            if not 0<propensity<1:raise ValueError('No overlap')
            weight*=float(a==acts[t][s])/(propensity if a else 1-propensity)
            value+=.95**t*weight*(cash+.95*v[t+1,ns]-q[t,s,a])
        contributions.append(float(value))
    tp,tr=policy_truth();return -float(np.mean(contributions)),contributions,enumerate_value(tp,tr,acts)

def neural_reference(name,model,rows):
    x=np.array([r['x'] for r in rows]);y,jac=net_numpy(model,x if name=='nas' else x[:,:1])
    if name=='nas':
        exact=np.exp(-x[:,0]*x[:,1]);der=np.column_stack((-x[:,1]*exact,-x[:,0]*exact));losses=np.mean(np.column_stack(((y-exact)**2,(jac-der)**2)),axis=0)
        return float(sum(losses)),{'losses':losses.tolist(),'y':y.tolist(),'jacobian':jac.tolist(),'dx_max':float(max(abs(jac[:,0]-der[:,0]))),'da_max':float(max(abs(jac[:,1]-der[:,1])))}
    s=model['log_scale'];z2=(x[:,1]-y)*math.exp(-s);losses=.5*(x[:,0]**2+z2**2)+s+math.log(2*math.pi)
    return float(losses.mean()),{'shift':y.tolist(),'latent':np.column_stack((x[:,0],z2)).tolist(),'nll':losses.tolist(),'log_jacobian':s}

def verify_payload(payload,records):
    name=payload['name'];m=payload['model'];train=[records[k] for k in payload['train_ids']];score=[records[k] for k in payload['score_ids']];metrics=payload['metrics']
    if set(payload['train_ids']) & set(payload['score_ids']):raise AssertionError('Role leakage')
    if name=='forecast':
        actual,trace=forecast_reference(m,train,score)
        for a,b in zip(trace,metrics['trace']):
            for key in ('mean','variance','nll'):close(a[key],b[key])
        lag=m['lag'];rows=[r for r in train if r['y'] is not None];x=np.array([[1.,*r['x'][:lag],r['x'][3]] for r in rows]);y=np.array([r['y'] for r in rows]);reg=np.diag(np.sqrt([0.]+[m['ridge']]*(lag+1)))
        expected=np.linalg.lstsq(np.vstack((x,reg)),np.r_[y,np.zeros(lag+2)],rcond=None)[0];close(expected,m['weights'])
    elif name=='wallet':
        actual,expected=wallet_reference(m,score)
        for key in expected:close(metrics[key],expected[key])
        x=np.array([[r['x']**j for j in range(m['degree']+1)] for r in train]);mu=x@m['weights'];z=np.log1p([r['wallet'] for r in train]);s=m['sigma'];d=[]
        for a,b in zip(mu,z):d.append((a-b)/s**2 if b>0 else math.exp(-.5*(a/s)**2)/(math.sqrt(2*math.pi)*s*normal_cdf(-a/s)))
        gradient=x.T@d/len(train)+m['ridge']*np.r_[0.,m['weights'][1:]]
        if max(abs(gradient))>2e-7:raise AssertionError('Wallet KKT residual')
    elif name=='policy':
        actual,contributions,value=policy_reference(m,score);close(metrics['contributions'],contributions);close(metrics['true_value'],value)
    else:
        actual,expected=neural_reference(name,m,score)
        for key in expected:close(metrics[key],expected[key])
    close(payload['loss'],actual);return actual
