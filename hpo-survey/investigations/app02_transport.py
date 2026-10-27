"""Fixed length intervention and analytic exact-transport autocorrelation reference."""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from references import net_numpy,close
from app02_trace import TRANSPORT,payload,binding

def shift(kind,model,q):
    if kind=='exact':return .35*(q*q-1),.7*q,1.
    if kind=='identity':return 0.,0.,1.
    v,j=net_numpy(model,np.array([[q]]));return float(v[0]),float(j[0,0]),math.exp(model['log_scale'])

def target(kind,model,q):
    u,j,s=shift(kind,model,q[0]);res=s*q[1]+u-.35*(q[0]*q[0]-1)
    return -.5*(q[0]*q[0]+res*res)+math.log(s),np.array([-q[0]-res*(j-.7*q[0]),-res*s])

def lf(kind,model,q,p,h,length):
    q=q.copy();p=p.copy();p+=h/2*target(kind,model,q)[1]
    for j in range(length):
        q+=h*p
        if j<length-1:p+=h*target(kind,model,q)[1]
    p+=h/2*target(kind,model,q)[1];return q,p

def original(kind,model,q):
    u,j,s=shift(kind,model,q[0]);return np.array([q[0],s*q[1]+u])

def simulate(kind,model,length,seed):
    rng=np.random.default_rng(seed);all_draws=[];accepted=0;lag=[];moves=[]
    for chain in range(2):
        q=rng.normal(size=2);draws=[]
        for t in range(320):
            p=rng.normal(size=2);logu=math.log(rng.uniform());old=q.copy();qn,pn=lf(kind,model,q,p,.15,length)
            loga=min(0.,target(kind,model,qn)[0]-.5*float(pn@pn)-target(kind,model,q)[0]+.5*float(p@p))
            if logu<loga:q=qn;accepted+=1
            if t>=64:draws.append(original(kind,model,q));moves.append(float(np.sum((original(kind,model,q)-original(kind,model,old))**2)))
        draws=np.array(draws);all_draws.append(draws);lag.append(float(np.corrcoef(draws[:-1,0],draws[1:,0])[0,1]))
    flat=np.concatenate(all_draws);return dict(draws=[d.tolist() for d in all_draws],acceptance=accepted/640,
       mean=flat.mean(0).tolist(),second_moment=(flat*flat).mean(0).tolist(),
       max_mean_error=float(np.max(np.abs(flat.mean(0)))),max_moment_error=float(np.max(np.abs((flat*flat).mean(0)-[1.,1.245]))),
       x1_lag1=float(np.mean(lag)),mean_squared_jump=float(np.mean(moves)),gradient_evaluations=640*(length+1))

def run(out):
    maps=[('identity',None,None),('exact',None,None)]
    for rep in (401,502,603):
        path=next((TRANSPORT/str(rep)/'gp/models').glob('*_final_0.json'));maps.append((f'learned-{rep}',payload(path)['model'],binding(path)))
    numerical=[];rows=[]
    for label,model,source in maps:
        kind=label if model is None else 'learned'
        for length in (1,8):
            q=np.array([.3,-.2]);p=np.array([-.1,.7]);value,grad=target(kind,model,q);eps=1e-5
            fd=np.array([(target(kind,model,q+np.eye(2)[j]*eps)[0]-target(kind,model,q-np.eye(2)[j]*eps)[0])/(2*eps) for j in range(2)]);close(grad,fd,tol=1e-6)
            qn,pn=lf(kind,model,q,p,.15,length);qr,pr=lf(kind,model,qn,-pn,.15,length);close(qr,q);close(pr,-p)
            state=np.r_[q,p];columns=[]
            for j in range(4):
                delta=np.eye(4)[j]*eps;a=state+delta;b=state-delta
                columns.append((np.concatenate(lf(kind,model,a[:2],a[2:],.15,length))-np.concatenate(lf(kind,model,b[:2],b[2:],.15,length)))/(2*eps))
            volume=float(np.linalg.det(np.array(columns).T));close(volume,1.,tol=2e-5)
            numerical.append(dict(map=label,length=length,gradient_error=float(max(abs(grad-fd))),volume=volume))
            for seed in (3101,3102,3103):
                result=simulate(kind,model,length,seed);row=dict(map=label,length=length,seed=seed,source=source,**result);rows.append(row)
                with (out/f'{label}-{length}-{seed}.json').open('x') as f:json.dump(row,f,allow_nan=False)
        print(json.dumps({'map':label,'comparisons_complete':len(rows)}),flush=True)
    groups=[]
    for label,_,_ in maps:
        for length in (1,8):
            group=[r for r in rows if r['map']==label and r['length']==length]
            groups.append(dict(map=label,length=length,**{k:float(np.mean([r[k] for r in group])) for k in ('acceptance','max_mean_error','max_moment_error','x1_lag1','mean_squared_jump','gradient_evaluations')}))
    analytic=[]
    for T in (.05,.15,1.2):
        rho=math.cos(T);analytic.append(dict(integration_time=T,rho=rho,stationary_iact=(1+rho)/(1-rho),
                  finite_256_mean_variance=(256+2*sum((256-k)*rho**k for k in range(1,256)))/256**2))
    result=dict(passed=True,stage='APP-02/TRANSPORT',fixed_step_size=.15,retained_draws_per_chain=256,warmup=64,
          groups=groups,numerical_controls=numerical,exact_flow_gaussian_reference=analytic,
          explanation='For exact Gaussian Hamiltonian flow with refreshed independent momentum, q_next=cos(T)*q+sin(T)*p. High acceptance can coexist with near-unit correlation. Leapfrog with Metropolis is separately checked empirically; its correlation is not asserted exactly equal to cos(T).',
          limitations=['Length8 consumes more gradients per transition; raw error improvement is not equal-cost superiority.','Three fixed RNG replicates,short chains and lag1 summaries do not certify convergence.','No sampler selected from posterior discrepancy; all declared pairs retained.'])
    with (out/'transport.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'groups':groups,'analytic':analytic}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
