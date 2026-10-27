"""Fixed HMC policies compared by charged gradient work, not posterior selection."""
import math,sys
import numpy as np
from common import *
from references import net_numpy,close
from app02_trace import TRANSPORT,payload
def law(q,kind,model):
    if kind=='identity':u=np.zeros(len(q));j=u;s=1.
    elif kind=='exact':u=.35*(q[:,0]**2-1);j=.7*q[:,0];s=1.
    else:u,jj=net_numpy(model,q[:,:1]);j=jj[:,0];s=math.exp(model['log_scale'])
    residual=s*q[:,1]+u-.35*(q[:,0]**2-1)
    lp=-.5*(q[:,0]**2+residual**2)+math.log(s)
    grad=np.column_stack((-q[:,0]-residual*(j-.7*q[:,0]),-residual*s))
    original=np.column_stack((q[:,0],s*q[:,1]+u));return lp,grad,original
def diagnostics(draws):
    chains,n,d=draws.shape;half=n//2;splits=np.concatenate((draws[:,:half],draws[:,-half:]),axis=0)
    within=np.mean(np.var(splits,axis=1,ddof=1),axis=0);between=half*np.var(splits.mean(1),axis=0,ddof=1)
    rhat=np.sqrt(((half-1)/half*within+between/half)/within)
    k=16;length=n//k;batch=draws[:,:length*k].reshape(chains,k,length,d).mean(2)
    mcse=np.sqrt(np.var(batch,axis=1,ddof=1).mean(0)/(chains*k));variance=np.var(draws.reshape(-1,d),axis=0,ddof=1);ess=variance/(mcse**2)
    return {'mean':draws.mean((0,1)).tolist(),'second_moment':(draws*draws).mean((0,1)).tolist(),'split_rhat':rhat.tolist(),'batch_means_mcse':mcse.tolist(),'batch_means_ess':ess.tolist(),'ess_per_gradient':(ess/(4*8192)).tolist(),'retained_per_chain':n,'batch_length':length}
def simulate(kind,model,policy,seed):
    rng=np.random.default_rng(seed);length_rng=np.random.default_rng(seed+100000);q=rng.normal(size=(4,2));work=0;accepted=0;attempted=0;draws=[];lengths=[]
    while True:
        length=1 if policy=='short' else int(length_rng.choice([8,12]));cost=length+1
        if work+cost>8192:break
        momentum=rng.normal(size=(4,2));logu=np.log(rng.random(4));oldlp,oldgrad,original=law(q,kind,model);initial=oldlp-.5*(momentum*momentum).sum(1)
        qn=q.copy();pn=momentum.copy();pn+=.075*oldgrad
        for t in range(length):
            qn+=.15*pn
            if t<length-1:pn+=.15*law(qn,kind,model)[1]
        lp,grad,proposal_original=law(qn,kind,model);pn+=.075*grad
        valid=logu<np.minimum(0,lp-.5*(pn*pn).sum(1)-initial);q[valid]=qn[valid];accepted+=int(valid.sum());attempted+=4;work+=cost;lengths.append(length)
        original[valid]=proposal_original[valid]
        if work>2048:draws.append(original)
    array=np.stack(draws,axis=1);assert work<=8192
    return {'draws':array.tolist(),'lengths':lengths,'gradient_work_per_chain':work,'unused_budget_per_chain':8192-work,'transitions':attempted,'acceptance':accepted/attempted,'diagnostics':diagnostics(array)}
def run(out):
    maps=[('identity',None,None),('exact',None,None)]
    for rep in (401,502,603):
        path=next((TRANSPORT/str(rep)/'gp/models').glob('*_final_0.json'));maps.append((f'learned-{rep}',payload(path)['model'],binding(path)))
    rows=[]
    for label,model,source in maps:
        kind=label if model is None else 'learned'
        q=np.array([[.2,-.3]]);_,gradient,_=law(q,kind,model);eps=1e-6
        fd=np.array([(law(q+np.eye(2)[j]*eps,kind,model)[0][0]-law(q-np.eye(2)[j]*eps,kind,model)[0][0])/(2*eps) for j in range(2)]);close(gradient[0],fd,tol=1e-6)
        for policy in ('short','randomized'):
            for seed in (8501,8502):
                row={'map':label,'source':source,'policy':policy,'seed':seed,**simulate(kind,model,policy,seed)};save(out/f'{label}-{policy}-{seed}.json',row);rows.append(row)
                print(canon({'map':label,'policy':policy,'seed':seed,'work':row['gradient_work_per_chain'],'rhat':row['diagnostics']['split_rhat']}),flush=True)
    analytic=[]
    for name,ts in [('short',[.15]),('randomized',[1.2,1.8])]:
        rho=float(np.mean(np.cos(ts)));iact=(1+rho)/(1-rho);analytic.append({'policy':name,'exact_flow_rho':rho,'exact_flow_iact':iact,'interpretation':'Stationary exact harmonic flow with independent refreshed momentum and iid integration times; not the Metropolized leapfrog kernel.'})
    summary=[{k:v for k,v in x.items() if k not in ('draws','lengths')} for x in rows]
    assert len(rows)==20 and sum(x['transitions'] for x in rows)<=200240
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'equal_gradient_comparison_reported_without_convergence_or_superiority_certificate','pairs':summary,'exact_flow_reference':analytic,'total_transitions':sum(x['transitions'] for x in rows),'gradient_budget':655360,'candidate_selection':'none; all frozen map/policy pairs retained','diagnostics_scope':'Basic split-Rhat and batch means only; not rank-normalized or a proof. Budget includes warmup and unused remainder. Poor diagnostics stay visible.'})
if __name__=='__main__':run(Path(sys.argv[1]))
