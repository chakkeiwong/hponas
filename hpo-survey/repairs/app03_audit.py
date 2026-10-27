"""Read-only independent APP-03 reconstruction. No optimizer or fitting calls."""
import copy, itertools, json, math, sys
import numpy as np
from common import BASE,ROOT,read,save,binding,canon,reject
from references import close,forecast_reference,policy_reference,policy_truth,enumerate_value

CONTROLS={}
LIMITS={'dx':.25*.6**2*math.exp(.3),'da':.25*.5**2*math.exp(.3)}

def check_binding(row):
    assert binding(ROOT/row['path'])==row, 'Changed bound file: '+row['path']

def roster(actual,expected):
    assert len(actual)==len(expected) and len(set(actual))==len(actual) and set(actual)==set(expected),'Incomplete/duplicate roster'

def receipts(manifest):
    total=0; directories={}
    for item in manifest['operation_receipts']:
        check_binding(item); r=read(ROOT/item['path']); m=read(ROOT/r['manifest']['path']);check_binding(r['manifest'])
        assert r['inputs']==m['inputs'] and r['source_digest']==manifest['source_digest']==r['end_source_digest']
        assert r['inputs_unchanged'] and not r['remaining_owned_pids']
        for x in r['inputs']+r['outputs']:check_binding(x);total+=1
        d=ROOT/r['directory']; actual=[str(x.relative_to(ROOT)) for x in d.rglob('*') if x.is_file() and x.name not in ('receipt.json','intent.json','process.json','progress.json')]
        roster(actual,[x['path'] for x in r['outputs']]); assert r['passed']==(r['operation']!='nas-repair')
        if r['passed']:assert r['returncode']==0 and r['stop_reason'] is None and read(d/'result.json')['mechanics_passed']
        else:assert 'Independent reconstruction differs' in (d/'execution.log').read_text()
        directories[r['operation']]=d
    assert set(directories)=={'wallet','nas-repair','nas-repair-v2','nas-confirm','transport','policy','forecast','documentation'}
    bad=copy.deepcopy(manifest['operation_receipts'][0]);bad['sha256']='0'*64
    CONTROLS['changed_hash']=reject(lambda:check_binding(bad))
    return directories,total

def role_record(rec,decl):
    assert rec['role'] in ('tuning','final')
    folds=decl['tuning_folds'] if rec['role']=='tuning' else decl['final_folds']
    name=rec.get('fold','validation' if rec['role']=='tuning' else 'final')
    fold=next((x for x in folds if x['name']==name),None);assert fold is not None
    assert rec['train_ids']==fold['train_ids'] and rec['score_ids']==fold['score_ids']
    assert len(set(rec['train_ids']))==len(rec['train_ids']) and len(set(rec['score_ids']))==len(rec['score_ids'])
    assert not set(rec['train_ids'])&set(rec['score_ids'])
    final=set().union(*(set(f['score_ids']) for f in decl['final_folds']))
    if rec['role']=='tuning':assert not final&(set(rec['train_ids'])|set(rec['score_ids']))
    return fold

def study(directory,records,n,score,maximize,work):
    decl=read(directory/'declaration.json');result=read(directory/'result.json');report=read(directory/'report.json')
    assert report['declaration']==decl==result['evaluation']['contract']
    identity=__import__('hashlib').sha256(json.dumps(decl,sort_keys=True,allow_nan=False).encode()).hexdigest()
    assert identity==result['evaluation']['identity']==report['evaluation']['identity']
    tune=[x for x in records if x['role']=='tuning'];final=[x for x in records if x['role']=='final']
    idx=lambda x:x.get('index',x.get('config',{}).get('index'))
    roster([(idx(x),x.get('fold','validation')) for x in tune],list(itertools.product(range(n),[f['name'] for f in decl['tuning_folds']])))
    assert len(final)==1 and result['status']=='completed' and result['n_trials']==n and len(result['history'])==n
    means=[float(np.mean([x[score] for x in tune if idx(x)==i])) for i in range(n)]
    selected=int(np.argmax(means) if maximize else np.argmin(means));assert result['best_config']['values']['index']==selected==idx(final[0]);close(result['best_value'],means[selected])
    for rec in records:role_record(rec,decl)
    seen=set();expected_work={r:0 for r in ('tuning','final')}
    calls=[(x['metadata']['evaluation']['records'],'tuning',i) for i,x in enumerate(result['history'])]
    calls += [(x['records'],'final',selected) for x in result['evaluation']['final']]
    for events,role,index in calls:
        for e in events:
            res=e['result'];assert res['status']=='completed' and e['seed']==(0 if role=='tuning' else 1000)
            path=Path(res['metadata']['artifacts']['model']);assert path.parent==directory/'models';rec=read(path);assert rec in records
            assert idx(rec)==index and rec['role']==role and path.name not in seen;seen.add(path.name)
            close(res['objective_value'],rec[score]);charge=work(rec);close(res['metadata']['resource']['work'],charge);expected_work[role]+=charge
    assert len(seen)==len(records)
    for role in expected_work:
        close(report['resources'][role]['measured_work'],expected_work[role]);close(report['resources'][role]['charged_work'],expected_work[role]);assert report['resources'][role]['contract_breaches']==0
    return selected,final[0],decl

from pathlib import Path

def wallet_point(model,point):
    c=model['config'];t=model['theta'];v=[1.]
    if c['mean']!='intercept':v.extend(point)
    if c['mean']=='quadratic':v.extend([point[0]**2,point[0]*point[1],point[1]**2])
    k=len(v);sv=[1.,point[0]] if c['scale']=='linear' else [1.];j=k+len(sv)
    mu=math.fsum(a*b for a,b in zip(v,t[:k]));sig=math.exp(math.fsum(a*b for a,b in zip(sv,t[k:j])));p=1/(1+math.exp(-math.fsum(a*b for a,b in zip([1.,*point],t[j:])))) if c['incidence']=='mixture' else 1.
    return mu,sig,p

def wallet_values(model,x,w):
    cdf=lambda z:.5*math.erfc(-z/math.sqrt(2));aa=[];ll=[];uu=[]
    for point,observed in zip(x,w):
        m,s,p=wallet_point(model,point);choices=[0.]
        for cap,fee in zip([.5,1.5,3.],[.015,.06,.15]):
            a=-m/s;b=(math.log1p(cap)-m)/s
            choices.append(p*(math.exp(m+s*s/2)*(cdf(b-s)-cdf(a-s))-cdf(b)+cdf(a)+cap*cdf(-b))-fee)
        action=int(np.argmax(choices));aa.append(action);uu.append(min(observed,[0.,.5,1.5,3.][action])-[0.,.015,.06,.15][action])
        ll.append(-math.log(1-p+p*cdf(-m/s)) if observed==0 else -math.log(p)+math.log(s)+.5*math.log(2*math.pi)+.5*((math.log1p(observed)-m)/s)**2+math.log1p(observed))
    return aa,float(np.mean(uu)),float(np.mean(ll))

def wallet_record(rec,data,decl):
    role_record(rec,decl);d=data['validation' if rec['role']=='tuning' else 'final'];keep=np.array(d['observed'],bool);x=np.array(d['x'])[keep];w=np.array(d['wallet'])[keep]
    grid=[dict(zip(('mean','scale','incidence','ridge'),v)) for v in itertools.product(('intercept','linear','quadratic'),('constant','linear'),('censored','mixture'),(0.,.01))]
    assert rec['model']['config']==grid[rec['index']]
    train=data['train'];assert rec['train_ids']==[i for i,ok in zip(train['ids'],train['observed']) if ok]
    if rec['new_fit']:
        assert rec['model']['work']==sum(t['evaluations'] for t in rec['model']['traces'])*len(rec['train_ids'])
        assert rec['model']['projected_gradient']<2e-7
    ids=[i for i,ok in zip(d['ids'],d['observed']) if ok];assert rec['score_ids']==ids
    a,u,l=wallet_values(rec['model'],x,w);assert a==rec['actions'];close(u,rec['utility']);close(l,rec['nll']);assert rec['new_fit']==(rec['role']=='tuning')

def wallet(directory):
    result=read(directory/'result.json');assert result['fits']==72;count=0
    for seed in (5301,5302,5303):
        d=directory/str(seed);data=read(d/'data.json');decl=read(d/'declaration.json');rows=[read(x) for x in sorted((d/'models').glob('*.json'))];assert len(rows)==25
        for x in rows:wallet_record(x,data,decl);count+=1
        selected,final,_=study(d,rows,24,'utility',True,lambda x:x['model']['work'] if x['new_fit'] else len(x['score_ids']))
        tune=sorted([x for x in rows if x['role']=='tuning'],key=lambda x:x['index']);assert final['model']==tune[selected]['model'];summary=read(d/'summary.json');assert summary==next(x for x in result['studies'] if x['seed']==seed)
        assert summary['selected']==selected and summary['new_fits']==24 and not summary['final_refit'];means=np.array([x['utility'] for x in tune]);close(means,summary['candidate_utilities'])
        likelihood=int(np.argmin([x['nll'] for x in tune]));assert likelihood==summary['likelihood_selected'];f=data['final'];keep=np.array(f['observed'],bool)
        _,comp,_=wallet_values(tune[likelihood]['model'],np.array(f['x'])[keep],np.array(f['wallet'])[keep]);close(comp,summary['likelihood_final_utility']);close(final['utility'],summary['final_utility']);close(final['utility']-comp,summary['final_utility_difference'])
        n=len(tune[0]['score_ids']);assert summary['observed_validation_rows']==n
        for level in (.90,.95,.99):
            radius=3.15*math.sqrt(math.log(48/(1-level))/(2*n));close(summary['simultaneous_intervals'][str(level)],np.column_stack((np.maximum(-.15,means-radius),np.minimum(3.,means+radius))))
        assert summary['certified_above_no_action_95']==(summary['simultaneous_intervals']['0.95'][selected][0]>0)
    bad=copy.deepcopy(rows[0]);bad['utility']+=.01;CONTROLS['wallet_false_utility']=reject(lambda:wallet_record(bad,data,decl))
    bad=copy.deepcopy(final);bad['role']='tuning';CONTROLS['final_role_leakage']=reject(lambda:role_record(bad,decl))
    CONTROLS['wallet_missing_model']=reject(lambda:study(d,rows[:-1],24,'utility',True,lambda x:0))
    witness=result['identification'];close(witness['sharp_population_interval'],[.75,1.5]);assert not witness['point_identified_without_missingness_assumption']
    worlds=[[(.75,True,1.),(.25,False,missing)] for missing in (0.,3.)]
    project=lambda law:[(prob,seen,y if seen else None) for prob,seen,y in law]
    assert project(worlds[0])==project(worlds[1]);means=[sum(prob*y for prob,seen,y in law) for law in worlds]
    close(means,witness['sharp_population_interval']);assert means[0]!=means[1]
    return {'records':count,'fits':72,'status':result['scientific_status'],'certified_gain':False}

def network(model,points):
    # Independent directional derivatives, with one forward pass per coordinate.
    x=np.asarray(points,float);values=None;derivatives=[]
    for axis in range(x.shape[1]):
        a=x.copy();d=np.zeros_like(a);d[:,axis]=1
        for i,l in enumerate(model['layers']):
            w=np.array(l['weight']);z=np.dot(a,w.T)+l['bias'];dz=np.dot(d,w.T)
            if i<len(model['layers'])-1:
                if model['config']['activation']=='tanh':a=np.tanh(z);d=(1-a*a)*dz
                else:
                    sig=1/(1+np.exp(-z));a=z*sig;d=(sig+z*sig*(1-sig))*dz
            else:a=z;d=dz
        values=a[:,0];derivatives.append(d[:,0])
    return values,np.column_stack(derivatives)

def mesh(n):return np.array(list(itertools.product(np.linspace(-.5,.5,n),np.linspace(.2,.6,n))))

def nas_score(model,points,record):
    y,j=network(model,points);truth=np.exp(-points[:,0]*points[:,1]);e=np.abs(j-np.column_stack((-points[:,1]*truth,-points[:,0]*truth)))
    losses=np.r_[np.mean((y-truth)**2),np.mean(e*e,axis=0)];ratios=e/[LIMITS['dx'],LIMITS['da']];row,col=np.unravel_index(np.argmax(ratios),ratios.shape)
    close(record['loss'],sum(losses));close(record['losses'],losses);close([record['dx_max'],record['da_max']],e.max(0));close(record['max_limit_ratio'],ratios.max());close(record['worst_point'],points[row])
    assert record['feasible']==bool(ratios.max()<=1) and record['violating_points']==int(np.any(ratios>1,axis=1).sum());assert record['worst_derivative']==('dx','da')[col]

def nas(development,confirmation):
    rows=[read(x) for x in development.glob('*.json') if x.name[0].isdigit()];roster([(r['seed'],r['width'],r['geometry'],r['recipe']) for r in rows],list(itertools.product((6401,6402),(4,8),('random','tensor'),('raw','normalized','polish'))))
    for r in rows:
        m=r['model'];assert m['seed']==r['seed'] and m['config']['width']==r['width'] and m['epochs']==480 and 480<=m['closure_calls']<=580
        nas_score(m,np.array(r['train_points']),r['train']);nas_score(m,mesh(41),r['validation'])
        assert len(r['train_points'])==81
        if r['geometry']=='tensor':close(r['train_points'],mesh(9))
        else:
            points=np.random.default_rng(r['seed']).uniform([-.5,.2],[.5,.6],(81,2));points[:8]=[[-.5,.2],[-.5,.6],[.5,.2],[.5,.6],[0.,.2],[0.,.6],[-.5,.4],[.5,.4]];close(points,r['train_points'])
    result=read(development/'result.json');groups=[]
    for w,g,p in itertools.product((4,8),('random','tensor'),('raw','normalized','polish')):
        same=[r for r in rows if (r['width'],r['geometry'],r['recipe'])==(w,g,p)]
        groups.append({'width':w,'geometry':g,'recipe':p,'all_validation_feasible':all(r['validation']['feasible'] for r in same),'worst_validation_ratio':max(r['validation']['max_limit_ratio'] for r in same),'mean_validation_loss':np.mean([r['validation']['loss'] for r in same]),'parameters':sum(np.size(l['weight'])+len(l['bias']) for l in same[0]['model']['layers'])})
    assert groups==result['groups'];feasible=[x for x in groups if x['all_validation_feasible']];selected=min(feasible,key=lambda x:(x['parameters'],x['worst_validation_ratio'],x['mean_validation_loss']))
    assert selected==result['selected'] and not result['final_data_seen'];close(list(result['limits'].values()),list(LIMITS.values()))
    final=[read(x) for x in confirmation.glob('confirmation-*.json')];roster([r['seed'] for r in final],list(range(7401,7407)))
    for r in final:
        m=r['model'];assert (m['config']['width'],m['geometry'],m['recipe'])==(selected['width'],selected['geometry'],selected['recipe']);nas_score(m,np.array(r['train_points']),r['train']);nas_score(m,mesh(81),r['final_mesh']);nas_score(m,np.array(r['final_points']),r['final_random'])
        close(r['final_points'],np.random.default_rng(r['seed']+100000).uniform([-.5,.2],[.5,.6],(512,2)))
    summary=read(confirmation/'result.json');assert summary['selected']==selected and summary['fits']==6
    assert summary['mesh_feasible']==sum(r['final_mesh']['feasible'] for r in final)==6 and summary['random_feasible']==sum(r['final_random']['feasible'] for r in final)==6
    close(summary['worst_mesh_ratio'],max(r['final_mesh']['max_limit_ratio'] for r in final));assert summary['scientific_status']=='finite_confirmation_pass' and not summary['continuous_domain_certified'] and not summary['all_seed_guarantee']
    failed=next(r for r in rows if not r['validation']['feasible']);bad=copy.deepcopy(failed['validation']);bad['feasible']=True;CONTROLS['false_NAS_success']=reject(lambda:nas_score(failed['model'],mesh(41),bad))
    CONTROLS['missing_NAS_confirmation']=reject(lambda:roster([r['seed'] for r in final[:-1]],list(range(7401,7407))))
    return {'development_fits':24,'confirmation_fits':6,'feasible':6,'worst_ratio':summary['worst_mesh_ratio'],'continuous_proof':False}

def transport_law(q,kind,model):
    if kind=='identity':shift=np.zeros(len(q));dshift=np.zeros(len(q));scale=1.
    elif kind=='exact':shift=.35*(q[:,0]*q[:,0]-1);dshift=.7*q[:,0];scale=1.
    else:shift,j=network(model,q[:,:1]);dshift=j[:,0];scale=math.exp(model['log_scale'])
    original=np.column_stack((q[:,0],scale*q[:,1]+shift));residual=original[:,1]-.35*(q[:,0]**2-1)
    return -.5*(q[:,0]**2+residual**2)+math.log(scale),np.column_stack((-q[:,0]-residual*(dshift-.7*q[:,0]),-residual*scale)),original

def transport_record(r,replay=True):
    lengths=r['lengths'];cost=sum(l+1 for l in lengths);assert r['gradient_work_per_chain']==cost<=8192 and r['unused_budget_per_chain']==8192-cost;assert r['transitions']==4*len(lengths)
    assert all(l in ([1] if r['policy']=='short' else [8,12]) for l in lengths)
    draws=np.asarray(r['draws']);n=int(sum(v>2048 for v in np.cumsum(np.array(lengths)+1)));assert draws.shape==(4,n,2)
    half=n//2;splits=np.array([piece for chain in draws for piece in (chain[:half],chain[-half:])]);within=splits.var(1,ddof=1).mean(0);between=half*splits.mean(1).var(0,ddof=1)
    rh=np.sqrt(((half-1)*within/half+between/half)/within);bl=n//16;batches=np.array([[np.mean(c[j*bl:(j+1)*bl],axis=0) for j in range(16)] for c in draws]);mcse=np.sqrt(batches.var(1,ddof=1).mean(0)/64);ess=draws.reshape(-1,2).var(0,ddof=1)/mcse**2
    d=r['diagnostics'];close(d['mean'],draws.mean((0,1)));close(d['second_moment'],np.mean(draws**2,axis=(0,1)));close(d['split_rhat'],rh);close(d['batch_means_mcse'],mcse);close(d['batch_means_ess'],ess);close(d['ess_per_gradient'],ess/32768);assert d['retained_per_chain']==n and d['batch_length']==bl
    if not replay:return
    model=None
    if r['source']:
        check_binding(r['source']);payload=read(ROOT/r['source']['path']);assert __import__('hashlib').sha256(canon(payload['payload']).encode()).hexdigest()==payload['sha256'];model=payload['payload']['model']
    kind=r['map'] if model is None else 'learned';rng=np.random.default_rng(r['seed']);lrng=np.random.default_rng(r['seed']+100000);q=rng.normal(size=(4,2));spent=0;accepted=0;kept=[]
    for length in lengths:
        assert length==(1 if r['policy']=='short' else int(lrng.choice([8,12])))
        momentum=rng.normal(size=q.shape);logu=np.log(rng.random(4));lp,g,old=transport_law(q,kind,model);old_energy=lp-np.sum(momentum**2,axis=1)/2
        newq=q.copy();newp=momentum+.075*g
        for step in range(length):
            newq=newq+.15*newp
            if step+1<length:newp=newp+.15*transport_law(newq,kind,model)[1]
        nlp,ng,new=transport_law(newq,kind,model);newp=newp+.075*ng;accept=logu<np.minimum(0,nlp-np.sum(newp**2,axis=1)/2-old_energy);q=np.where(accept[:,None],newq,q);old=np.where(accept[:,None],new,old);accepted+=int(sum(accept));spent+=length+1
        if spent>2048:kept.append(old)
    nextlength=1 if r['policy']=='short' else int(lrng.choice([8,12]));assert spent+nextlength+1>8192;close(r['draws'],np.stack(kept,axis=1));close(r['acceptance'],accepted/(4*len(lengths)))

def transport(directory):
    result=read(directory/'result.json');rows=[read(directory/f"{m}-{p}-{s}.json") for m,p,s in itertools.product(('identity','exact','learned-401','learned-502','learned-603'),('short','randomized'),(8501,8502))]
    expected=list(itertools.product(('identity','exact','learned-401','learned-502','learned-603'),('short','randomized'),(8501,8502)));roster([(r['map'],r['policy'],r['seed']) for r in result['pairs']],expected)
    for r in rows:
        transport_record(r);assert {k:v for k,v in r.items() if k not in ('draws','lengths')}==next(x for x in result['pairs'] if (x['map'],x['policy'],x['seed'])==(r['map'],r['policy'],r['seed']))
    assert sum(r['transitions'] for r in rows)==result['total_transitions']<=200240 and result['gradient_budget']==655360
    for x,ts in zip(result['exact_flow_reference'],([.15],[1.2,1.8])):
        rho=sum(math.cos(t) for t in ts)/len(ts);close(x['exact_flow_rho'],rho);close(x['exact_flow_iact'],(1+rho)/(1-rho))
    bad=copy.deepcopy(rows[0]);bad['gradient_work_per_chain']-=1;CONTROLS['altered_sampler_work']=reject(lambda:transport_record(bad,False))
    bad=copy.deepcopy(rows[0]);bad['diagnostics']['split_rhat'][0]+=.1;CONTROLS['altered_sampler_diagnostic']=reject(lambda:transport_record(bad,False))
    keys=[(r['map'],r['policy'],r['seed']) for r in rows];CONTROLS['missing_sampler_cell']=reject(lambda:roster(keys[:-1],expected));CONTROLS['duplicated_sampler_cell']=reject(lambda:roster(keys[:-1]+[keys[0]],expected))
    return {'pairs':20,'replayed_transitions':result['total_transitions'],'gradient_budget':655360,'convergence_certified':False}

def policy_record(rec,data,decl):
    role_record(rec,decl);cfg=rec['physical'];assert rec['model']['config']==cfg;acts=[]
    grid=[dict(zip(('direction','threshold','time_slope','smoothing'),v)) for v in itertools.product(('greater','less'),(-1.5,-.5,.5,1.5),(0.,.3),(.1,1.,10.))];assert cfg==grid[rec['config']['index']]
    for t in range(3):acts.append([int(s>cfg['threshold']+cfg['time_slope']*t) if cfg['direction']=='greater' else int(s<cfg['threshold']+cfg['time_slope']*t) for s in (-1,0,1)])
    assert acts==rec['model']['actions'];counts=np.full((3,2,3),cfg['smoothing']/3);reward=np.zeros((3,2));den=np.full((3,2),cfg['smoothing'])
    for key in rec['train_ids']:
        for s,a,y,ns,p in data[key]['trajectory']:assert 0<p<1;counts[s,a,ns]+=1;reward[s,a]+=y;den[s,a]+=1
    close(rec['model']['transition'],counts/counts.sum(2,keepdims=True));close(rec['model']['reward'],reward/den)
    value,contrib,truth=policy_reference(rec['model'],[data[i] for i in rec['score_ids']]);close(value,rec['loss']);close(contrib,rec['metrics']['contributions']);close(truth,rec['metrics']['true_value'])

def policy(directory):
    result=read(directory/'result.json');p,r=policy_truth();oracle=max(enumerate_value(p,r,np.array(x).reshape(3,3)) for x in itertools.product((0,1),repeat=9));close(oracle,result['oracle']);count=0;fits=0
    for seed in (9601,9602,9603):
        d=directory/str(seed);data=read(d/'data.json');decl=read(d/'declaration.json');rows=[read(x) for x in (d/'models').glob('*.json')];assert len(rows)==97
        for x in rows:policy_record(x,data,decl);count+=1
        selected,final,_=study(d,rows,48,'loss',False,lambda x:3*(len(x['train_ids']) if x['new_nuisance_fit'] else 0)+3*len(x['score_ids']))
        unique={(x['fold'],x['physical']['smoothing']) for x in rows};new=[(x['fold'],x['physical']['smoothing']) for x in rows if x['new_nuisance_fit']];roster(new,list(unique));assert len(new)==7;fits+=len(new)
        f0,f1=decl['tuning_folds'];assert f0['train_ids']==f1['score_ids'] and f1['train_ids']==f0['score_ids'];assert set(decl['final_folds'][0]['train_ids'])==set(f0['train_ids']+f1['train_ids'])
        summary=read(d/'summary.json');assert summary==next(x for x in result['studies'] if x['seed']==seed);assert summary['selected']['index']==selected and summary['physical']==final['physical'];close(summary['exact_regret'],oracle-final['metrics']['true_value']);close(summary['exact_value'],oracle);close(summary['final_value_estimate'],-final['loss']);close(summary['final_iid_standard_error'],np.std(final['metrics']['contributions'],ddof=1)/math.sqrt(len(final['score_ids'])))
    bad=copy.deepcopy(rows[0]);bad['loss']+=.1;CONTROLS['altered_DR_score']=reject(lambda:policy_record(bad,data,decl))
    from app03_policy import admissible
    bad_data=copy.deepcopy(next(iter(data.values())));bad_data['trajectory'][0][4]=0;CONTROLS['zero_overlap']=reject(lambda:admissible([bad_data],'known_randomized_logger'));CONTROLS['unknown_identification']=reject(lambda:admissible([next(iter(data.values()))],'unknown'))
    assert result['nuisance_fits']==fits==21 and result['evaluations']==count==291 and not result['real_bank_recommendation'];assert result['confounding_witness']['world1_ATE']==1 and result['confounding_witness']['world2_ATE']==0
    worlds=[[(.5,u,(u if world==1 else u)) for u in (0,1)] for world in (1,2)];assert worlds[0]==worlds[1]
    potential=[[(u,[0,1] if world==1 else [u,u]) for u in (0,1)] for world in (1,2)]
    assert [sum(.5*(v[1]-v[0]) for u,v in law) for law in potential]==[1.,0.]
    return {'nuisance_fits':fits,'evaluations':count,'oracle':oracle,'selected_optima':3,'identification_required':True}

def forecast_record(rec,data,decl):
    f=role_record(rec,decl);train=[data[i] for i in rec['train_ids']];score=[data[i] for i in rec['score_ids']];gap=rec['gap_rows']
    expected=sorted([copy.deepcopy(x) for x in data.values() if f['train_until']<x['time']<f['score_from']],key=lambda x:x['time'])
    for x in expected:x['y']=None
    assert expected==gap and len(gap)==2
    assert [x['time'] for x in train]==list(range(int(f['train_until'])+1)) and [x['time'] for x in score]==list(range(int(f['score_from']),int(f['score_until'])+1))
    m=rec['model'];cfg=rec['physical'];assert all(m[k]==cfg[k] for k in ('lag','ridge','variance'));obs=[x for x in train if x['y'] is not None]
    grid=[{'lag':l,'ridge':r,'variance':.4} for l,r in itertools.product((1,2),(.01,1.))];assert cfg==grid[rec['config']['index']]
    features=np.array([[1.,*x['x'][:m['lag']],x['x'][3]] for x in obs]);reg=np.diag(np.sqrt([0.]+[m['ridge']]*(m['lag']+1)));weights=np.linalg.lstsq(np.vstack((features,reg)),np.r_[[x['y'] for x in obs],np.zeros(m['lag']+2)],rcond=None)[0];close(weights,m['weights'])
    loss,trace=forecast_reference(m,train+gap,score);close(loss,rec['loss']);assert len(trace)==len(rec['trace'])
    for a,b in zip(trace,rec['trace']):
        assert a['time']==b['time'] and a['observed']==b['observed']
        for k in ('mean','variance','nll'):close(a[k],b[k])

def forecast(directory):
    result=read(directory/'result.json');count=0
    for seed in (10701,10702,10703):
        d=directory/str(seed);data=read(d/'data.json');decl=read(d/'declaration.json');rows=[read(x) for x in (d/'models').glob('*.json')];assert len(rows)==9
        for x in rows:forecast_record(x,data,decl);count+=1
        selected,final,_=study(d,rows,4,'loss',False,lambda x:len(x['train_ids'])+len(x['gap_rows'])+len(x['score_ids']))
        summary=next(x for x in result['studies'] if x['seed']==seed);assert summary['selected']==final['physical'];close(summary['final_nll'],final['loss'])
    bad=copy.deepcopy(rows[0]);bad['gap_rows'][0]['y']=100.;CONTROLS['unmasked_embargo']=reject(lambda:forecast_record(bad,data,decl))
    bad=copy.deepcopy(rows[0]);bad['loss']+=.1;CONTROLS['altered_forecast_score']=reject(lambda:forecast_record(bad,data,decl))
    from models import forecast_features
    from hponas import EvaluationFold,StudyDeclaration,EvaluationObjective
    future=copy.deepcopy(next(iter(data.values())));future['release_times'][0]=future['time']+1
    CONTROLS['future_feature']=reject(lambda:forecast_features([future],1));CONTROLS['temporal_gap']=reject(lambda:EvaluationFold('bad',('a',),('b',),mode='temporal',train_until=2,score_from=3,score_until=4,gap=1));CONTROLS['entity_overlap']=reject(lambda:EvaluationFold('bad',('a',),('b',),mode='grouped',train_groups=('same',),score_groups=('same',)));CONTROLS['final_exposure']=reject(lambda:StudyDeclaration(objective_id='x',model_id='x',data_id='x',protocol_id='x',objectives=(EvaluationObjective('x','min','x'),),tuning_folds=(EvaluationFold('train',('a',),('b',)),),final_folds=(EvaluationFold('final',('a',),('b',)),)))
    assert result['fits']==count==27
    return {'fits':count,'rolling_folds':2,'datasets':3,'real_bank_effectiveness':False}

def run(out):
    manifest=read(BASE/'audit-manifest.json');dirs,hashes=receipts(manifest);results={}
    for name,fn,args in [('wallet',wallet,[dirs['wallet']]),('nas',nas,[dirs['nas-repair-v2'],dirs['nas-confirm']]),('transport',transport,[dirs['transport']]),('policy',policy,[dirs['policy']]),('forecast',forecast,[dirs['forecast']])]:
        results[name]=fn(*args);print(canon({'reconstructed':name,'result':results[name]}),flush=True)
    doc=read(dirs['documentation']/'result.json');check_binding(doc['pdf']);assert doc['pages']==141 and doc['build_passes']==4;results['documentation']={'pages':doc['pages'],'predecessor_preserved':True}
    p=read(ROOT/'docs/program/program.json');obligations=[x['id'] for x in p['requirements'] if x['id'].startswith('APPREPAIR-')];roster(obligations,['APPREPAIR-0'+str(i) for i in range(1,7)])
    mapping=dict(zip(obligations,['wallet','nas','transport','policy','forecast','documentation']));assert all(v in results for v in mapping.values()) and len(CONTROLS)>=17 and all(CONTROLS.values())
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'scoped_repairs_independently_reconstructed_with_limits_retained','new_fits':0,'operation_receipts':len(dirs),'bound_files_checked':hashes,'families':results,'requirements':mapping,'negative_controls':CONTROLS,'qualified_source_unchanged':manifest['source_digest'],'remaining_limits':['Wallet superiority and useful precision unestablished.','Unknown MNAR and causal identification cannot be solved by optimization.','NAS continuous-domain and all-seed guarantee not established.','Sampler diagnostics are not convergence proofs or ranking objectives.','Real-bank effectiveness and production readiness not qualified.'],'terminal_GAP_audit_required':True})
if __name__=='__main__':run(Path(sys.argv[1]))
