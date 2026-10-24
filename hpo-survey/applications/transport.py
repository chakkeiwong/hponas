"""Fixed-map nonlinear HMC; numerical handoff separate from posterior assessment."""
import itertools
import math
from pathlib import Path
import numpy as np
from references import net_numpy,close
from studies import save,load_model

def transform(model,z):
    z=np.atleast_2d(z);u,_=net_numpy(model,z[:,:1]);return np.column_stack((z[:,0],math.exp(model['log_scale'])*z[:,1]+u))

def logp_grad(model,z):
    z=np.array(z,dtype=float);u,j=net_numpy(model,z[None,:1]);scale=math.exp(model['log_scale']);r=scale*z[1]+u[0]-.35*(z[0]**2-1)
    return -.5*(z[0]**2+r*r)-math.log(2*math.pi)+model['log_scale'],np.array([-z[0]-r*(j[0,0]-.7*z[0]),-r*scale])

def independent_logp(model,z):
    x=transform(model,z)[0];r=x[1]-.35*(x[0]**2-1);return -.5*(x[0]**2+r*r)-math.log(2*math.pi)+model['log_scale']

def leapfrog(model,q,p,h,length):
    q=np.array(q,dtype=float).copy();p=np.array(p,dtype=float).copy()
    for _ in range(length):
        p+=h/2*logp_grad(model,q)[1];q+=h*p;p+=h/2*logp_grad(model,q)[1]
    return q,p

def candidate_checks(model,h,length,states):
    records=[];eps=1e-5
    for state in states:
        q,p=np.asarray(state[:2]),np.asarray(state[2:]);v,g=logp_grad(model,q);numerical=[]
        for j in range(2):
            d=np.eye(2)[j]*eps;numerical.append((independent_logp(model,q+d)-independent_logp(model,q-d))/(2*eps))
        close(g,numerical,tol=1e-6);qn,pn=leapfrog(model,q,p,h,length);qr,pr=leapfrog(model,qn,-pn,h,length);close(qr,q);close(pr,-p)
        columns=[]
        for j in range(4):
            d=np.eye(4)[j]*eps;a=np.r_[q,p]+d;b=np.r_[q,p]-d
            columns.append((np.concatenate(leapfrog(model,a[:2],a[2:],h,length))-np.concatenate(leapfrog(model,b[:2],b[2:],h,length)))/(2*eps))
        determinant=float(np.linalg.det(np.array(columns).T));close(determinant,1.,tol=2e-5)
        loga=min(0.,logp_grad(model,qn)[0]-.5*float(pn@pn)-v+.5*float(p@p));records.append({'state':state.tolist(),'proposal':np.r_[qn,pn].tolist(),'log_acceptance':loga,'volume':determinant,'gradient':g.tolist()})
    return records

def sample(model,h,length,seed):
    rng=np.random.default_rng(seed);chains=[]
    for chain in range(2):
        q=rng.normal(size=2);records=[];draws=[]
        for i in range(160):
            p=rng.normal(size=2);logu=math.log(rng.uniform());initial=q.copy();qn,pn=leapfrog(model,q,p,h,length);loga=min(0.,logp_grad(model,qn)[0]-.5*float(pn@pn)-logp_grad(model,q)[0]+.5*float(p@p))
            accept=logu<loga
            if accept:q=qn
            if not np.isfinite(q).all():raise ValueError('Nonfinite HMC')
            records.append({'q':initial.tolist(),'p':p.tolist(),'proposal':qn.tolist(),'proposal_p':pn.tolist(),'logu':logu,'loga':loga,'accepted':bool(accept)})
            if i>=32:draws.append(transform(model,q)[0].tolist())
        chains.append({'records':records,'draws':draws})
    flat=np.array([d for c in chains for d in c['draws']]);iid=rng.normal(size=(len(flat),2));iid[:,1]+=.35*(iid[:,0]**2-1)
    return {'chains':chains,'assessment':{'mean':flat.mean(0).tolist(),'second_moment':(flat**2).mean(0).tolist(),'true_mean':[0.,0.],'true_second_moment':[1.,1.245],'iid_mean':iid.mean(0).tolist(),'iid_second_moment':(iid**2).mean(0).tolist(),'convergence_claim':False,'used_for_candidate_selection':False}}

def verify_selected_transports(root):
    outcomes=[]
    for rep in (401,502,603):
        for method in ('random','sobol','gp','tpe'):
            files=list((root/str(rep)/method/'models').glob('*_final_0.json'))
            if len(files)!=1:raise AssertionError('One selected final seed-zero artifact required')
            payload=load_model(files[0]);model=payload['model'];rng=np.random.default_rng(rep+9000);development=rng.normal(scale=.5,size=(2,4));fresh=rng.normal(scale=.5,size=(3,4));rows=[];verified=[]
            for index,(h,length) in enumerate(itertools.product((.05,.15,.35),(1,4,8))):
                row={'step_size':h,'leapfrog_steps':length}
                try:
                    row['development']=candidate_checks(model,h,length,development);row['fresh']=candidate_checks(model,h,length,fresh);row['status']='verified';verified.append([h,length])
                except (AssertionError,ValueError,OverflowError,FloatingPointError) as exc:row.update(status='rejected',reason=str(exc))
                if row['status']=='verified':row['posterior']=sample(model,h,length,rep*1000+index)
                rows.append(row)
            result={'replicate':rep,'method':method,'model_path':str(files[0]),'verified_pairs':verified,'selection_policy':'retain_all_freshly_verified_pairs','candidates':rows,'posterior_used_for_selection':False,'target':'banana-Gaussian-exact-v1'}
            save(root/str(rep)/method/'handoff.json',result);outcomes.append({'replicate':rep,'method':method,'verified_pairs':len(verified),'rejected_pairs':9-len(verified)})
    return outcomes
