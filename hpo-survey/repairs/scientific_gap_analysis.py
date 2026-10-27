"""SCI-01 saved-artifact analysis: no training, model forwards or new chains."""
from pathlib import Path
from fractions import Fraction
import hashlib, importlib.util, itertools, json, math, sys, time
import numpy as np
import mpmath as mp
from scipy.special import ndtri
from scipy.stats import rankdata

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-25/scientific-gap-trace-01'
APP=ROOT/'docs/program/evidence/2026-10-25/app-03'
sys.path.insert(0,str(ROOT/'hpo-survey/investigations'))
from wallet_model import parameters,capped_mean,population_metrics
WALLET=APP/'20261025T053718Z-wallet-57088ed0'
NAS=APP/'20261025T054110Z-nas-confirm-51c52263'
TRANSPORT=APP/'20261025T054310Z-transport-f3c572fb'
IFBO=ROOT/'validation/artifacts/V15a/20261008_finite_ifbo_01'
def read(p):return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def close(a,b,tol=1e-9):
    assert np.shape(a)==np.shape(b) and np.all(np.isfinite(a)) and np.allclose(a,b,rtol=tol,atol=tol)
def reject(fn):
    try:fn()
    except (AssertionError,ValueError):return True
    raise AssertionError('False result accepted')

def wallet_actions(m,x):
    p=parameters(np.asarray(m['theta']),x,m['config'])
    return np.column_stack([np.zeros(len(x)),*[capped_mean(p,c)-fee for c,fee in zip((.5,1.5,3.),(.015,.06,.15))]]).argmax(1)
def utility(a,w):return np.minimum(w,np.array([0.,.5,1.5,3.])[a])-np.array([0.,.015,.06,.15])[a]
def bernstein(x,width,alpha,family=9):
    # Two-sided empirical Bernstein, union bound over all 9 declared means.
    n=len(x);v=float(np.var(x,ddof=1));z=math.log(4*family/alpha)
    rad=math.sqrt(2*v*z/n)+7*width*z/(3*(n-1))
    return [float(np.mean(x)-rad),float(np.mean(x)+rad)]
def wallet(out):
    rows=[]
    for seed in (5301,5302,5303):
        d=WALLET/str(seed);summary=read(d/'summary.json');data=read(d/'data.json')
        tune={r['index']:r for p in (d/'models').glob('*.json') if (r:=read(p))['role']=='tuning'}
        chosen=tune[summary['selected']]['model'];comp=tune[summary['likelihood_selected']]['model']
        f=data['final'];assert all(f['observed']) and len(f['ids'])==512
        x=np.array(f['x']);w=np.array(f['wallet']);a=wallet_actions(chosen,x);b=wallet_actions(comp,x)
        ua,ub=utility(a,w),utility(b,w);delta=ua-ub;close(delta.mean(),summary['final_utility_difference'])
        # Action utility has exact range [-.15,2.85]. Paired differences are
        # bounded by the greatest difference across the four action payoffs.
        # Use the conservative difference range [-3,3], independent of samples.
        bands={str(level):{'selected':bernstein(ua,3.,1-level),'likelihood':bernstein(ub,3.,1-level),'paired_difference':bernstein(delta,6.,1-level)} for level in (.90,.95,.99)}
        refined={}
        for order in (96,192):
            c=population_metrics(chosen,order);l=population_metrics(comp,order)
            refined[str(order)]={'selected_regret':c['allocation_decision_regret'],'likelihood_regret':l['allocation_decision_regret'],'population_utility_difference':l['allocation_decision_regret']-c['allocation_decision_regret']}
        rows.append({'seed':seed,'selected':summary['selected'],'likelihood_selected':summary['likelihood_selected'],'n_final':512,'action_disagreements':int(np.sum(a!=b)),'paired_sd':float(np.std(delta,ddof=1)),'final_means':[float(ua.mean()),float(ub.mean())],'difference':float(delta.mean()),'intervals':bands,'population_quadrature':refined,'selection_search_regret':0.})
    result={'rows':rows,'interpretation':'Retrospective diagnostic of exposed final records; not fresh confirmation or a changed APP-03 verdict. Exact enumeration already exhausts24 validation candidates, so more search cannot fix sampling/model/decision uncertainty.','interval_contract':'Two-sided empirical Bernstein; simultaneously9 means (selected,likelihood,paired for3 datasets), independent final rows conditional on training/selection;90/95/99% individually reported, not jointly over levels.','quadrature_scope':'Order refinement is a numerical diagnostic; discontinuous action boundaries mean it is not a rigorous integral enclosure.','prospective_closure':'Freeze paired final assessment and a baseline before fresh evaluation. Test usefulness via decision regret and cost, not a universal demand for utility selection to beat likelihood selection.'}
    save(out/'wallet.json',result);return result

def basic_rhat(x):
    n=x.shape[1];w=np.var(x,axis=1,ddof=1).mean();b=n*np.var(x.mean(1),ddof=1)
    return float(math.sqrt(((n-1)*w/n+b/n)/w))
def transport(out):
    rows=[]
    for f in sorted(TRANSPORT.glob('*.json')):
        if f.name in ('intent.json','process.json','progress.json','receipt.json','result.json'):continue
        r=read(f);draws=np.asarray(r['draws']);n=draws.shape[1]//2;values=[]
        for j in range(2):
            split=np.concatenate((draws[:,:n,j],draws[:,-n:,j]),axis=0)
            ranks=rankdata(split,method='average');z=ndtri((ranks-3/8)/(split.size+1/4)).reshape(split.shape)
            folded=np.abs(split-np.median(split));fr=rankdata(folded,method='average');fz=ndtri((fr-3/8)/(split.size+1/4)).reshape(split.shape)
            values.append({'rank_normalized_split_rhat':basic_rhat(z),'folded_rank_normalized_split_rhat':basic_rhat(fz),'maximum':max(basic_rhat(z),basic_rhat(fz))})
        rows.append({'map':r['map'],'policy':r['policy'],'seed':r['seed'],'diagnostics':values})
    assert len(rows)==20
    exact=[]
    for name,ts in [('short',[.15]),('randomized',[1.2,1.8]),('quarter_period',[math.pi/2])]:
        c=np.cos(ts);rho=float(c.mean());rho2=float((c*c).mean());exact.append({'policy':name,'linear_rho':rho,'linear_IACT':(1+rho)/(1-rho),'Hermite_L2_contraction_bound':max(abs(rho),rho2)})
    result={'retained_diagnostics':rows,'exact_gaussian_flow':exact,'mathematics':'For exact Gaussian harmonic flow with refreshed iid normal momenta, z_next=cos(T)z+sin(T)p. Hermite eigenvalues are E[cos(T)^k]; all k>=2 bounded by E[cos(T)^2]. T=pi/2 gives an independent exact draw. Apply x2=z2+.35*(z1^2-1) for the analytic banana target.','scope':'This is a solvable-reference route. It is not a convergence theorem for the saved Metropolized leapfrog chains or arbitrary learned maps. Rank diagnostics cannot prove convergence or rank native-tuner candidates.','prospective_closure':'Use exact transformed draws as known-answer reference. Certify target/Jacobian/reversibility separately; assess all frozen candidates with rank and tail diagnostics. General targets need explicit assumptions for rate bounds.'}
    save(out/'transport.json',result);return result

def ifbo(out):
    spec=importlib.util.spec_from_file_location('retained_reference',ROOT/'validation/ifbo_finite_reference.py');ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
    rows=[];all_details=[]
    for case in range(6):
        raw=read(IFBO/f'raw-{case:02d}.json');initial=raw['slot']['initial'];a=ref.verify_updates(initial,raw['ifbo']);b=ref.verify_updates(initial,raw['asha']);ref.verify_asha(initial,raw['slot']['seed'],raw['asha'])
        history=[];errors64=[];errors32=[];argmax_same=0
        for index,record in enumerate(raw['ifbo']['trace']):
            if index:
                rng=np.random.RandomState(42)
                for _ in range(index):rng.uniform(-4,-1);rng.randint(1,51)
                threshold=min(history)*(1-10**rng.uniform(-4,-1));path=IFBO/f'case-{case:02d}'/record['tensors']['path']
                assert bind(path)['sha256']==record['tensors']['sha256']
                with np.load(path,allow_pickle=False) as t:
                    logits=t['logits'].astype(float);borders=t['borders'].astype(float);width=np.diff(borders)
                mass=np.exp(logits-logits.max(1,keepdims=True));mass/=mass.sum(1,keepdims=True)
                factor64=1-np.clip(((1-threshold)-borders[:-1])/width,0,1)
                # Isolate upstream's float32 incumbent/subtraction and bin arithmetic,
                # keeping softmax at float64 to separate sources of error.
                border32=borders.astype(np.float32);best32=np.float32(1)-np.float32(threshold)
                factor32=(np.float32(1)-np.clip((best32-border32[:-1])/np.diff(border32),np.float32(0),np.float32(1))).astype(float)
                predicted64=mass@factor64;predicted32=mass@factor32;actual=np.asarray(record['probabilities'])
                e64=float(max(abs(predicted64-actual)));e32=float(max(abs(predicted32-actual)));errors64.append(e64);errors32.append(e32)
                same=int(np.argmax(predicted64))==int(np.argmax(actual));argmax_same+=same
                all_details.append({'case':case,'index':index,'error_double_threshold':e64,'error_float32_threshold':e32,'threshold_cast_error':abs(float(best32)-(1-threshold)),'narrowest_bin':float(min(width)),'argmax_unchanged_double':same})
            history.append(record['update']['loss'])
        rows.append({'slot':raw['slot']['id'],'ifbo_loss':a,'asha_loss':b,'loss_ratio':a/b,'difference':a-b,'ifbo_no_worse':a<=b+2e-12+2e-10*abs(b),'pi_max_error_double_threshold':max(errors64),'pi_max_error_float32_threshold':max(errors32),'double_argmax_matches':argmax_same,'calls':23})
    result={'cases':rows,'PI_details':all_details,'new_training_updates':0,'new_model_forwards':0,'all_saved_training_and_ASHA_traces_reconstructed':True,'original_FAIL_unchanged':True,'complete_pretrained_identity_verified':False,'interpretation':'Saved recommendation losses can be reconstructed without qualifying upstream method identity. Numerical PI mismatch and performance are separate gates. A corrected numerical reconstruction cannot change recorded losses; cancellation is not reversed.'}
    save(out/'ifbo.json',result);return result

# Rigorous outward interval arithmetic over the saved mathematical network.
# Every binary64 weight is an exact dyadic constant. The rectangle is rational.
iv=mp.iv;iv.dps=35
def endpoint(v,upper):
    return mp.mpf(v._mpi_[1 if upper else 0])
def magnitude(v):return max(abs(endpoint(v,False)),abs(endpoint(v,True)))
def interval(a,b=None):
    def cast(x):
        if isinstance(x,Fraction):return iv.mpf(x.numerator)/x.denominator
        return iv.mpf(x)
    if b is None:return cast(a)
    return iv.mpf([cast(a).a,cast(b).b])
def prepared(model):
    return [([[interval(w) for w in row] for row in l['weight']],[interval(b) for b in l['bias']]) for l in model['layers']]
def jet(layers,box,hessian):
    a=[interval(box[0],box[1]),interval(box[2],box[3])]
    j=[[interval(1),interval(0)],[interval(0),interval(1)]]
    h=[[interval(0) for _ in range(3)] for _ in range(2)]
    for index,(weights,biases) in enumerate(layers):
        aa=[];jj=[];hh=[]
        for ws,bias in zip(weights,biases):
            z=bias+sum(w*v for w,v in zip(ws,a))
            dz=[sum(w*v[k] for w,v in zip(ws,j)) for k in range(2)]
            hz=[sum(w*v[k] for w,v in zip(ws,h)) for k in range(3)] if hessian else []
            if index+1<len(layers):
                sig=1/(1+iv.exp(-z));d=sig+z*sig*(1-sig);d2=sig*(1-sig)*(2+z*(1-2*sig))
                aa.append(z*sig);jj.append([d*v for v in dz])
                if hessian:hh.append([d*hz[k]+d2*dz[i]*dz[jj_] for k,(i,jj_) in enumerate(((0,0),(0,1),(1,1)))])
            else:aa.append(z);jj.append(dz);hh.append(hz)
        a,j,h=aa,jj,hh
    return a[0],j[0],h[0] if hessian else []
def box_for(path):
    box=[Fraction(-1,2),Fraction(1,2),Fraction(1,5),Fraction(3,5)]
    for depth,c in enumerate(path):
        axis=2*(depth%2);mid=(box[axis]+box[axis+1])/2
        box[axis+(0 if c=='1' else 1)]=mid
    return box
def domain_bound(layers,path):
    box=box_for(path);x=interval(box[0],box[1]);a=interval(box[2],box[3]);target=iv.exp(-x*a)
    _,j,h=jet(layers,box,True);th=[a*a*target,(a*x-1)*target,x*x*target];eh=[u-v for u,v in zip(h,th)]
    center=[(box[0]+box[1])/2]*2+[(box[2]+box[3])/2]*2
    _,cj,_=jet(layers,center,False);cx=interval(center[0]);ca=interval(center[2]);ct=iv.exp(-cx*ca)
    ce=[cj[0]+ca*ct,cj[1]+cx*ct];r=[interval((box[1]-box[0])/2),interval((box[3]-box[2])/2)]
    # Use interval absolute values and upper endpoints throughout, including
    # the final Taylor sum. No ordinary-float rounding enters acceptance.
    bounds=[abs(ce[0])+abs(eh[0])*r[0]+abs(eh[1])*r[1],abs(ce[1])+abs(eh[1])*r[0]+abs(eh[2])*r[1]]
    limits=[interval(.12148729268184028),interval(.0843661754735002)]
    ratios=[u/v for u,v in zip(bounds,limits)]
    ok=all(u.b<=1 for u in ratios)
    return ok,[str(endpoint(u,True)) for u in ratios]
def cover(paths):
    assert len(set(paths))==len(paths)
    leaves=set(paths);prefixes={p[:i] for p in paths for i in range(len(p))}
    def visit(p):
        if p in leaves:assert p not in prefixes;return
        assert p in prefixes
        visit(p+'0');visit(p+'1')
    visit('');assert sum(Fraction(1,2**len(p)) for p in paths)==1
def nas(out):
    mp.mp.dps=50;rows=[]
    # Controls use an exactly constant network and a noncompliant constant
    # derivative perturbation. Whole-domain success cannot arise from emptiness.
    zero={'layers':[{'weight':[[0.,0.]],'bias':[0.]}]}
    assert not domain_bound(prepared(zero),'')[0]
    rejected_empty=reject(lambda:cover([]))
    for seed in range(7401,7407):
        source=NAS/f'confirmation-{seed}.json';row=read(source);layers=prepared(row['model']);todo=[''];leaves=[];count=0;start=time.monotonic()
        while todo and count<8192 and time.monotonic()-start<33:
            path=todo.pop();ok,bounds=domain_bound(layers,path);count+=1
            if ok:leaves.append({'path':path,'upper_limit_ratios':bounds})
            elif len(path)<24:todo.extend((path+'1',path+'0'))
            else:todo.append(path);break
        complete=not todo
        if complete:cover([x['path'] for x in leaves])
        proof={'seed':seed,'source':bind(source),'complete_partition':complete,'verified_leaf_count':len(leaves),'tested_boxes':count,'unresolved_boxes':len(todo),'leaves':leaves,'pending_paths':todo,'seconds':time.monotonic()-start,'scope':'Exact saved binary64 weights as real constants; rational rectangle [-1/2,1/2]x[1/5,3/5]; mathematical SiLU network derivatives; not floating point inference evaluation error or unseen seeds.'}
        save(out/f'nas-domain-{seed}.json',proof);rows.append({k:v for k,v in proof.items() if k not in ('leaves','pending_paths')});print(json.dumps({'nas_seed':seed,'complete':complete,'boxes':count}),flush=True)
    controls={'empty_cover_rejected':rejected_empty,'zero_network_not_certified':True}
    full=next((r for r in rows if r['complete_partition']),None)
    if full:
        leaves=read(out/f"nas-domain-{full['seed']}.json")['leaves'];controls['omitted_leaf_rejected']=reject(lambda:cover([x['path'] for x in leaves[:-1]]))
    result={'rows':rows,'complete_models':sum(r['complete_partition'] for r in rows),'interval_precision_decimal_digits':35,'controls':controls,'status':'candidate_domain_certificates_require_independent_review','method':'Interval automatic first/second derivatives plus mean-value theorem over a complete dyadic partition. All arithmetic including exponentials uses mpmath interval directed rounding; recorded upper bounds rounded only for presentation.','all_seed_guarantee':False}
    save(out/'nas.json',result);return result

def run(out):
    results={}
    for name,fn in [('wallet',wallet),('transport',transport),('ifbo',ifbo),('nas',nas)]:
        results[name]=fn(out);print(json.dumps({'finished':name}),flush=True)
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'gap_mechanisms_and_closure_routes_analyzed','new_fits':0,'new_chains':0,'new_pretrained_forwards':0,'files':{name:bind(out/(name+'.json')) for name in results},'nas_candidate_domain_certificates':results['nas']['complete_models'],'ifbo_saved_comparisons_no_worse':sum(x['ifbo_no_worse'] for x in results['ifbo']['cases']),'limitations':['Retrospective wallet bounds are diagnostic, not fresh confirmation.','NAS interval proofs need independent review before claiming certified domain behavior.','Exact Gaussian flow mathematics does not qualify the previous leapfrog kernel.','Unknown identification and real-bank data are external assumptions/evidence, not optimizer fixes.','Original failures remain unchanged.']})
if __name__=='__main__':run(Path(sys.argv[1]))
