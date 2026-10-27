"""Fixed mathematical controls and three-fit profile for APP-02 wallet."""
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from scipy.integrate import quad
from scipy.special import ndtr
from wallet_model import (GRID, TRUE_CONFIG, truth, truth_theta, parameters, objective,
                         expected_nll, capped_mean, fit, generate, observed_rows, population_metrics)

def phi(z): return math.exp(-.5*z*z)/math.sqrt(2*math.pi)
def sigmoid(z): return 1/(1+math.exp(-z))

def scalar_nll(theta, x, wallet, cfg):
    # Separate scalar feature construction and elementary mixed-measure law.
    result = 0.
    for point, w in zip(x, wallet):
        v = [1.]
        if cfg['mean'] != 'intercept': v += list(point)
        if cfg['mean'] == 'quadratic': v += [point[0]**2, point[0]*point[1], point[1]**2]
        j = len(v); scale_v = [1., point[0]] if cfg['scale']=='linear' else [1.]
        k = j+len(scale_v); mu = sum(a*b for a,b in zip(v,theta[:j]))
        sigma = math.exp(sum(a*b for a,b in zip(scale_v,theta[j:k])))
        p = sigmoid(sum(a*b for a,b in zip([1.,*point],theta[k:]))) if cfg['incidence']=='mixture' else 1.
        if w == 0: result -= math.log(1-p+p*.5*math.erfc(mu/(sigma*math.sqrt(2))))
        else:
            z = math.log1p(w); result += -math.log(p)+math.log(sigma)+.5*math.log(2*math.pi)+.5*((z-mu)/sigma)**2+z
    return result/len(x)

def run(out):
    checks=[];x=np.array([[-.8,.2],[.3,-.6],[.9,.9],[-.4,-.3],[0.,0.]])
    y=np.array([0.,.3,1.8,0.,.9]);max_grad=0.;max_risk=0.;max_allocation=0.
    for cfg in GRID:
        # Nonzero coefficients exercise every derivative, including penalty.
        from wallet_model import features
        d,s,a=features(x,cfg);theta=np.linspace(-.25,.35,d.shape[1]+s.shape[1]+a.shape[1]);theta[d.shape[1]]=-.4
        value,gradient=objective(theta,x,y,cfg);raw=objective(theta,x,y,cfg,False)[0]
        assert abs(raw-scalar_nll(theta,x,y,cfg))<1e-11
        numerical=[]
        for i in range(len(theta)):
            delta=np.zeros(len(theta));delta[i]=1e-5
            numerical.append((objective(theta+delta,x,y,cfg)[0]-objective(theta-delta,x,y,cfg)[0])/2e-5)
        error=float(np.max(np.abs(gradient-numerical)));max_grad=max(max_grad,error);assert error<2e-7
    checks += ['all24 scalar likelihoods','all24 central-difference gradients']
    for mt,st,pt,mu,sigma,p in [(.2,.7,.6,.4,.5,.7),(-.5,.5,.3,.1,.8,.4),(.8,.9,.8,.7,.6,.9)]:
        et=math.log(pt/(1-pt));eta=math.log(p/(1-p));q0=1-pt+pt*ndtr(-mt/st);q=1-p+p*ndtr(-mu/sigma)
        numerical=-q0*math.log(q)+quad(lambda z:pt*phi((z-mt)/st)/st*(-math.log(p)+math.log(sigma)+.5*math.log(2*math.pi)+.5*((z-mu)/sigma)**2+z),0,np.inf,epsabs=1e-11,epsrel=1e-11)[0]
        analytic=float(expected_nll(tuple(np.array([z]) for z in (mu,sigma,eta)),tuple(np.array([z]) for z in (mt,st,et)))[0])
        error=abs(analytic-numerical);max_risk=max(max_risk,error);assert error<1e-9
        for cap in (.5,1.5,3.):
            threshold=math.log1p(cap)
            exact=pt*(quad(lambda z:math.expm1(z)*phi((z-mt)/st)/st,0,threshold,epsabs=1e-12)[0]+cap*quad(lambda z:phi((z-mt)/st)/st,threshold,np.inf,epsabs=1e-12)[0])
            actual=float(capped_mean(tuple(np.array([z]) for z in (mt,st,et)),cap)[0]);error=abs(exact-actual);max_allocation=max(max_allocation,error);assert error<1e-9
    checks += ['conditional expected NLL vs adaptive integration','capped allocation vs independent integration']
    oracle=dict(theta=truth_theta().tolist(),config=TRUE_CONFIG);oracle_metrics=population_metrics(oracle)
    assert max(abs(oracle_metrics[k]) for k in ('excess_nll','allocation_mae','allocation_decision_regret'))<1e-12
    bad=dict(theta=truth_theta().copy(),config=TRUE_CONFIG);bad['theta'][0]+=.5
    assert population_metrics(bad)['excess_nll']>1e-3
    # Controls establish that missing zero incidence/Jacobian changes the reference.
    mu,sigma,eta=truth(x);zero_true=1-1/(1+np.exp(-eta))+1/(1+np.exp(-eta))*ndtr(-mu/sigma)
    assert np.max(np.abs(zero_true-ndtr(-mu/sigma)))>.1
    assert abs(scalar_nll(truth_theta(),x,y,TRUE_CONFIG)-(scalar_nll(truth_theta(),x,y,TRUE_CONFIG)-np.log1p(y).mean()))>.1
    checks += ['truth zero risk/regret','perturbed-law negative control','missing incidence/Jacobian negative controls']
    data=generate(211);tx,ty=observed_rows(data,('train',));profiles=[]
    for index in (0,16,22):
        model=fit(GRID[index],tx,ty);m24=population_metrics(model,24);m48=population_metrics(model,48)
        differences={k:abs(m24[k]-m48[k]) for k in m24}
        assert differences['expected_nll']<1e-7 and differences['allocation_mae']<2e-3 and differences['allocation_decision_regret']<2e-3
        row=dict(index=index,model=model,metrics=m48,quadrature_differences=differences);profiles.append(row)
        print(json.dumps({'profile':index,'seconds':model['seconds'],'gradient':model['projected_gradient'],'risk':m48['excess_nll']}),flush=True)
    result=dict(passed=True,checks=checks,max_gradient_error=max_grad,max_conditional_risk_error=max_risk,
                max_allocation_error=max_allocation,training_observed=len(tx),profiles=profiles,
                max_fit_seconds=max(v['model']['seconds'] for v in profiles),
                limits=['Finite numerical tests, not a global likelihood optimum proof.','Synthetic mechanism coverage, not real SMEwallet calibration.'])
    with (out/'preflight.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='profiles'}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
