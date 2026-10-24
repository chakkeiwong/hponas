"""Pre-allocation mathematical and adversarial controls."""
from copy import deepcopy
import itertools
import math
from pathlib import Path
import tempfile
import numpy as np
import torch
from models import (DESIGN,generate,fit_score,wallet_objective,wallet_features,policy_dp,P,R,INITIAL,actions,neural_fit,neural_score)
from references import (close,verify_payload,forecast_reference,wallet_reference,wallet_mean_quad,policy_truth,enumerate_value,net_numpy)
from studies import Objective,save,load_model,digest
from hponas import EvaluationContext,EvaluationFold

def refuses(fn):
    try:fn()
    except (ValueError,AssertionError):return
    raise AssertionError('Invalid input accepted')

def run_controls():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='app01-controls-') as temp:
        for name in DESIGN['grids']:
            obj=Objective(name,401,Path(temp)/name);config=obj.configurations[0];context=EvaluationContext('tuning',obj.declaration.tuning_folds[0],obj.declaration.identity)
            row=obj(config,0,context,'control');payload=load_model(row['artifacts']['model']);verify_payload(payload,obj.records)
            altered=deepcopy(payload);altered['loss']+=.01;refuses(lambda:verify_payload(altered,obj.records))
            bad=deepcopy(payload);bad['score_ids']=bad['train_ids'];refuses(lambda:verify_payload(bad,obj.records))
            wrong=EvaluationContext('final',obj.declaration.tuning_folds[0],obj.declaration.identity);refuses(lambda:obj(config,1000,wrong,'leak'))
            invalid=dict(config);invalid[next(iter(invalid))]=-1;refuses(lambda:obj.physical(invalid))
            # Hash validation is distinct from mathematical reconstruction.
            corrupted={'payload':altered,'sha256':digest(payload)};path=Path(temp)/(name+'-corrupt.json');save(path,corrupted);refuses(lambda:load_model(path))
            checks.append(name+': independent score, altered value, overlap, role, configuration and artifact controls')
        rows,ids=generate('forecast',401);train=[rows[k] for k in ids['train']];score=[rows[k] for k in ids['validation']];config={'lag':2,'ridge':.1,'variance':.4}
        model,loss,metrics,_=fit_score('forecast',config,train,score,1);close(loss,forecast_reference(model,train,score)[0]);future=deepcopy(train);future[0]['release_times'][0]=1;refuses(lambda:fit_score('forecast',config,future,score,1))
        no_observations=deepcopy(score)
        for row in no_observations:row['y']=None
        refuses(lambda:fit_score('forecast',config,train,no_observations,1));checks.append('forecast: future release and all-missing scoring refused')
        rows,ids=generate('wallet',401);train=[rows[k] for k in ids['train']];x=wallet_features(train,3);z=np.log1p([r['wallet'] for r in train]);w=np.array([.3,.7,-.2,0.]);value,grad=wallet_objective(w,x,z,.6,.01)
        for h in (1e-5,5e-6):
            numerical=[(wallet_objective(w+np.eye(4)[j]*h,x,z,.6,.01)[0]-wallet_objective(w-np.eye(4)[j]*h,x,z,.6,.01)[0])/(2*h) for j in range(4)];close(grad,numerical,tol=1e-7)
        for mu in (-1.,0.,1.):
            m={'weights':[mu],'degree':0,'sigma':.6};_,ref=wallet_reference(m,[{'x':0.,'wallet':0.}]);close(ref['mean'][0],wallet_mean_quad(mu,.6),tol=1e-10)
        checks.append('wallet: gradient halving and mean quadrature')
        from scipy.special import ndtri
        from scipy.optimize import brentq
        from references import normal_cdf
        for mu in (-1.,0.,1.):
            sigma=.6;zero=normal_cdf(-mu/sigma)
            for probability in (.001,.1,.5,.9,.999):
                quantile=max(0.,math.expm1(mu+sigma*float(ndtri(probability))))
                if probability<=zero:close(quantile,0.)
                else:
                    root=brentq(lambda z:normal_cdf((z-mu)/sigma)-probability,0.,mu+12*sigma,xtol=1e-13)
                    close(quantile,math.expm1(root),tol=1e-10)
                    close(normal_cdf((math.log1p(quantile)-mu)/sigma),probability,tol=1e-10)
        checks.append('wallet: zero-mass quantiles and positive-tail CDF inversion')
        from verification import verification_negative_controls
        checks.extend(verification_negative_controls()['rejected'])
        tp,tr=policy_truth();close(P,tp);close(R,tr)
        for threshold,slope in itertools.product(DESIGN['grids']['policy']['threshold'],DESIGN['grids']['policy']['time_slope']):
            acts=actions({'threshold':threshold,'time_slope':slope});v,_=policy_dp(P,R,acts);close(INITIAL@v[0],enumerate_value(tp,tr,acts))
        obj=Objective('policy',401,Path(temp)/'policy');bad=deepcopy(obj.records);bad['validation_0']['trajectory'][0][4]=0.;obj.records=bad;context=EvaluationContext('tuning',obj.declaration.tuning_folds[0],obj.declaration.identity);refuses(lambda:obj(obj.configurations[0],0,context,'no-overlap'));checks.append('policy: exhaustive path value and missing overlap refusal')
        for name in ('nas','transport'):
            records,ids=generate(name,401);train=[records[k] for k in ids['train']];cfg={'width':4,'depth':2,'activation':'silu','learning_rate':.01};m=neural_fit(name,cfg,train,123)
            points=np.array([r['x'] for r in train[:4]]);points=points if name=='nas' else points[:,:1];y,jac=net_numpy(m,points)
            for h in (1e-5,5e-6):
                for axis in range(points.shape[1]):
                    d=np.eye(points.shape[1])[axis]*h;close(jac[:,axis],(net_numpy(m,points+d)[0]-net_numpy(m,points-d)[0])/(2*h),tol=1e-7)
            checks.append(name+': independent network derivatives at two step sizes')
            if name=='transport':
                from transport import transform,logp_grad,independent_logp,candidate_checks,sample
                z=np.array([[.2,-.4],[-.5,.7]]);transformed=transform(m,z);shift,_=net_numpy(m,transformed[:,:1]);inverse=np.column_stack((transformed[:,0],(transformed[:,1]-shift)*math.exp(-m['log_scale'])));close(z,inverse)
                candidate_checks(m,.15,4,np.array([[.2,-.4,.3,.1],[-.5,.7,-.2,.4]]));draw=sample(m,.15,1,123)
                for chain in draw['chains']:
                    for r in chain['records']:
                        before=-independent_logp(m,r['q'])+.5*np.dot(r['p'],r['p']);after=-independent_logp(m,r['proposal'])+.5*np.dot(r['proposal_p'],r['proposal_p']);close(r['loga'],min(0.,before-after));assert r['accepted']==(r['logu']<r['loga'])
                checks.append('transport: exact inverse, finite volume/reversibility, Hamiltonian acceptance sign')
    return {'passed':True,'checks':checks,'qualification':'Companion numerical/workflow controls only; no scientific superiority gate'}
