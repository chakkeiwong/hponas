"""Reconstruct retained application outputs without repeating fitting."""
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np
from references import close,verify_payload,net_numpy,enumerate_value,policy_truth

ROOT=Path('/home/ubuntu/workspace/hponas')
BASE=ROOT/'docs/program/evidence/2026-10-24/app-01'
def read(p):return json.loads(Path(p).read_text())
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)

def require_families(rows):
    names=[row['name'] for row in rows]
    if len(names)!=5 or set(names)!={'forecast','wallet','policy','nas','transport'}:raise AssertionError('Missing or duplicate family')

def check_regret(reported,observed,minimum):
    expected=min(observed)-minimum
    close(reported,expected)
    if expected < -1e-8:raise AssertionError('Negative grid regret')

def check_front(reported,feasible):
    expected=[tid for tid,values in feasible if not any(np.all(other<=values) and np.any(other<values) for oid,other in feasible if oid!=tid)]
    actual=[row['trial_id'] for row in reported]
    if len(actual)!=len(set(actual)) or set(expected)!=set(actual):raise AssertionError('Pareto front differs')
    return expected

def vector_values(payloads):
    objectives={'error':float(np.mean([p['metrics']['losses'][0] for p in payloads])),'size':float(np.mean([p['model']['parameters'] for p in payloads]))}
    constraints={k:max(p['metrics'][k+'_max'] for p in payloads) for k in ('dx','da')}
    feasible=constraints['dx']<=.25*.6**2*math.exp(.3) and constraints['da']<=.25*.5**2*math.exp(.3)
    return objectives,constraints,feasible

def check_feasibility(reported,constraints):
    expected=constraints['dx']<=.25*.6**2*math.exp(.3) and constraints['da']<=.25*.5**2*math.exp(.3)
    if reported!=expected:raise AssertionError('False vector feasibility')
    return expected

def verification_negative_controls():
    checks=[]
    def rejects(name,fn):
        try:fn()
        except AssertionError:checks.append(name);return
        raise AssertionError('Negative control escaped: '+name)
    check_regret(.2,[.3,.4],.1)
    rejects('altered finite regret',lambda:check_regret(0.,[.3,.4],.1))
    rejects('omitted family',lambda:require_families([{'name':x} for x in ('forecast','wallet','policy','nas')]))
    rejects('duplicate family',lambda:require_families([{'name':'nas'}]*5))
    feasible=[('a',np.array([1.,2.])),('b',np.array([2.,3.]))]
    check_front([{'trial_id':'a'}],feasible)
    rejects('omitted Pareto point',lambda:check_front([],feasible))
    rejects('dominated Pareto point',lambda:check_front([{'trial_id':'a'},{'trial_id':'b'}],feasible))
    rejects('false final feasibility',lambda:check_feasibility(True,{'dx':1.,'da':1.}))
    return {'passed':True,'rejected':checks}
def model(p):
    row=read(p)
    if hashlib.sha256(canonical(row['payload']).encode()).hexdigest()!=row['sha256']:raise AssertionError('Model digest differs')
    return row['payload']
def successful(operation):
    paths=[p.parent for p in BASE.glob('*-'+operation+'-*/receipt.json') if read(p)['passed']]
    if len(paths)!=1:raise ValueError('Need one successful '+operation+' allocation')
    return paths[0]

def independent_target(model,z):
    x=np.atleast_2d(z);shift,j=net_numpy(model,x[:,:1]);scale=math.exp(model['log_scale']);r=x[:,1]*scale+shift-.35*(x[:,0]**2-1)
    logp=-.5*(x[:,0]**2+r*r)-math.log(2*math.pi)+model['log_scale']
    grad=np.column_stack((-x[:,0]-r*(j[:,0]-.7*x[:,0]),-r*scale));return logp,grad

def independent_leapfrog(m,q,p,h,length):
    q=np.atleast_2d(q).copy();p=np.atleast_2d(p).copy()
    for _ in range(length):
        p+=h/2*independent_target(m,q)[1];q+=h*p;p+=h/2*independent_target(m,q)[1]
    return q,p

def verify_handoff(path):
    handoff=read(path);payload=model(handoff['model_path']);m=payload['model'];verified=[];transitions=0
    if payload['role']!='final' or payload['seed']!=1000:raise AssertionError('Sampler map not frozen final seed')
    expected=list(itertools.product((.05,.15,.35),(1,4,8)))
    if [(r['step_size'],r['leapfrog_steps']) for r in handoff['candidates']]!=expected:raise AssertionError('Sampler candidate omitted or reordered')
    rng=np.random.default_rng(handoff['replicate']+9000);states={'development':rng.normal(scale=.5,size=(2,4)),'fresh':rng.normal(scale=.5,size=(3,4))}
    for candidate in handoff['candidates']:
        if candidate['status']!='verified':
            if candidate['status']!='rejected' or not candidate.get('reason'):raise AssertionError('Unexplained sampler refusal')
            continue
        h=candidate['step_size'];length=candidate['leapfrog_steps'];verified.append([h,length]);all_draws=[]
        for phase in ('development','fresh'):
            checks=candidate[phase];close([r['state'] for r in checks],states[phase])
            q=states[phase][:,:2];p=states[phase][:,2:];qn,pn=independent_leapfrog(m,q,p,h,length)
            close(np.column_stack((qn,pn)),[r['proposal'] for r in checks]);close(independent_target(m,q)[1],[r['gradient'] for r in checks])
            qr,pr=independent_leapfrog(m,qn,-pn,h,length);close(qr,q);close(pr,-p)
            loga=np.minimum(0.,independent_target(m,qn)[0]-.5*np.sum(pn*pn,axis=1)-independent_target(m,q)[0]+.5*np.sum(p*p,axis=1));close(loga,[r['log_acceptance'] for r in checks])
            for epsilon in (1e-5,5e-6):
                numerical=[]
                for axis in range(2):
                    d=np.eye(2)[axis]*epsilon;numerical.append((independent_target(m,q+d)[0]-independent_target(m,q-d)[0])/(2*epsilon))
                close(np.array(numerical).T,independent_target(m,q)[1],tol=1e-6)
                columns=[]
                for axis in range(4):
                    d=np.eye(4)[axis]*epsilon;plus=states[phase]+d;minus=states[phase]-d
                    qa,pa=independent_leapfrog(m,plus[:,:2],plus[:,2:],h,length);qb,pb=independent_leapfrog(m,minus[:,:2],minus[:,2:],h,length)
                    columns.append((np.column_stack((qa,pa))-np.column_stack((qb,pb)))/(2*epsilon))
                determinants=np.linalg.det(np.stack(columns,axis=2));close(determinants,np.ones(len(checks)),tol=2e-5)
                if epsilon==1e-5:close(determinants,[r['volume'] for r in checks],tol=2e-5)
        if len(candidate['posterior']['chains'])!=2:raise AssertionError('Missing sampler chain')
        for chain in candidate['posterior']['chains']:
            if len(chain['records'])!=160 or len(chain['draws'])!=128:raise AssertionError('Incomplete sampler trajectory')
            rows=chain['records'];q=np.array([r['q'] for r in rows]);p=np.array([r['p'] for r in rows]);qn=q.copy();pn=p.copy()
            for _ in range(length):
                pn+=h/2*independent_target(m,qn)[1];qn+=h*pn;pn+=h/2*independent_target(m,qn)[1]
            close(qn,[r['proposal'] for r in rows]);close(pn,[r['proposal_p'] for r in rows])
            loga=np.minimum(0.,independent_target(m,qn)[0]-.5*np.sum(pn*pn,axis=1)-independent_target(m,q)[0]+.5*np.sum(p*p,axis=1));close(loga,[r['loga'] for r in rows])
            accepted=np.array([r['logu'] for r in rows])<loga
            if accepted.tolist()!=[r['accepted'] for r in rows]:raise AssertionError('Metropolis decisions differ')
            state=np.where(accepted[:,None],qn,q);close(state[:-1],q[1:]);shift,_=net_numpy(m,state[32:,:1]);draws=np.column_stack((state[32:,0],math.exp(m['log_scale'])*state[32:,1]+shift));close(draws,chain['draws']);all_draws.extend(draws.tolist());transitions+=len(rows)
        a=candidate['posterior']['assessment'];flat=np.array(all_draws);close(a['mean'],flat.mean(0));close(a['second_moment'],(flat*flat).mean(0));close(a['true_mean'],[0.,0.]);close(a['true_second_moment'],[1.,1.+2*.35**2]);assert not a['used_for_candidate_selection'] and not a['convergence_claim']
    if verified!=handoff['verified_pairs'] or handoff['posterior_used_for_selection']:raise AssertionError('Sampler candidate policy differs')
    return transitions

def verify_family(root):
    root=Path(root);design=read(root/'design.json');name=read(root/'summary.json')['name'];cache={};models=0;studies=0;vector_count=0;transitions=0;adverse=[]
    if design!=read(ROOT/'hpo-survey/applications/design.json'):raise AssertionError('Frozen design differs')
    family_rows=read(root/'summary.json')['rows'];expected_rows={(rep,method) for rep in design['replicates'] for method in design['methods']}
    if len(family_rows)!=len(expected_rows) or {(r['replicate'],r['method']) for r in family_rows}!=expected_rows:raise AssertionError('Missing family study summary')
    for rep in design['replicates']:
        base=root/str(rep);records=read(base/'data.json');grid=read(base/'grid.json');choices=design['grids'][name];axes=list(choices);expected={canonical(dict(zip(axes,v))) for v in itertools.product(*(range(len(choices[a])) for a in axes))}
        actual={canonical(row['config']) for row in grid['rows']}
        if actual!=expected or len(grid['rows'])!=len(expected):raise AssertionError('Incomplete reference grid')
        raw={};raw_by_content={}
        for path in sorted(base.glob('*/models/*.json')):
            payload=model(path);raw[str(path.resolve())]=payload;raw_by_content[canonical(payload)]=payload;models+=1
            role=payload['role'];train_ids=[k for k in records if k.startswith('train_')]+([] if role=='tuning' else [k for k in records if k.startswith('validation_')]);score_ids=[k for k in records if k.startswith('validation_' if role=='tuning' else 'final_')]
            if set(payload['train_ids'])!=set(train_ids) or set(payload['score_ids'])!=set(score_ids):raise AssertionError('Data role differs')
            if payload['seed'] not in design['tuning_seeds' if role=='tuning' else 'final_seeds']:raise AssertionError('Seed role differs')
            physical={a:choices[a][payload['config'][a]] for a in axes}
            if physical!=payload['physical']:raise AssertionError('Config mapping differs')
            key=canonical({k:payload[k] for k in ('name','replicate','physical','role','train_ids','score_ids','model','metrics','loss')})
            if key not in cache:cache[key]=verify_payload(payload,records)
            else:close(payload['loss'],cache[key])
        def get_raw(path):
            path=str(Path(path).resolve())
            if path in raw:return raw[path]
            inherited=model(path)
            key=canonical(inherited)
            if key not in raw_by_content:raise AssertionError('Unbound inherited artifact')
            return raw_by_content[key]
        for row in grid['rows']:
            losses=[get_raw(p)['loss'] for p in row['artifacts']];close(losses,row['losses']);close(np.mean(losses),row['mean'])
        minimum=min(row['mean'] for row in grid['rows']);close(grid['minimum'],minimum);lookup={canonical(r['config']):r['mean'] for r in grid['rows']}
        for method in design['methods']:
            directory=base/method;result=read(directory/'result.json');summary=read(directory/'summary.json');report=read(directory/'report.json');history=result['history'];observed=[]
            if summary!=next(r for r in family_rows if r['replicate']==rep and r['method']==method):raise AssertionError('Family aggregate summary differs')
            if len(history)!=design['budget'] or result['evaluation']['outcome']!='completed':raise AssertionError('Incomplete scalar study')
            cp=read(next(directory.glob('*checkpoint.json')))
            for row in history:
                records_eval=row['metadata']['evaluation']['records'];payloads=[get_raw(record['result']['metadata']['artifacts']['model']) for record in records_eval]
                if {r['seed'] for r in payloads}!=set(design['tuning_seeds']) or any(r['role']!='tuning' for r in payloads):raise AssertionError('Tuning barrier differs')
                value=float(np.mean([r['loss'] for r in payloads]));close(row['objective_value'],value);close(value,lookup[canonical(payloads[0]['config'])]);observed.append(value)
            close(result['best_value'],min(observed));check_regret(summary['tuning_regret'],observed,minimum)
            final=[p for path,p in raw.items() if Path(path).parent==directory.resolve()/'models' and p['role']=='final']
            if len(final)!=2 or {canonical(p['config']) for p in final}!={canonical(result['best_config']['values'])}:raise AssertionError('Final selection differs')
            close(summary['final_mean'],np.mean([p['loss'] for p in final]));close(result['evaluation']['final'][0]['objectives']['loss']['mean'],summary['final_mean'])
            for role in ('tuning','final'):
                work=sum(p['work'] for path,p in raw.items() if Path(path).parent==directory.resolve()/'models' and p['role']==role);close(report['resources'][role]['measured_work'],work)
            if not summary['completed_resume'] or summary['failed']:raise AssertionError('Missing completed resume or failed scalar evaluations')
            if name=='policy':adverse.append({'replicate':rep,'method':method,'final_policy_regret':final[0]['metrics']['policy_regret']})
            studies+=1
        rec=base/'recovery'
        if rep==design['replicates'][0]:
            event=read(rec/'interruption.json');assert event['projection_matches'] and not set(event['committed'])&set(event['calls_after']);a=read(rec/'result.json');b=read(base/'random/result.json')
            if a['best_config']!=b['best_config']:raise AssertionError('Recovery selection differs')
            close([r['objective_value'] for r in a['history']],[r['objective_value'] for r in b['history']])
        if name=='nas':
            directory=base/'vector';result=read(directory/'result.json');rows=result['history'];feasible=[];limits={'dx':.25*.6**2*math.exp(.3),'da':.25*.5**2*math.exp(.3)}
            if len(rows)!=design['budget'] or any(r['status']!='completed' for r in rows):raise AssertionError('Incomplete vector study')
            for row in rows:
                ps=[get_raw(x['result']['metadata']['artifacts']['model']) for x in row['metadata']['evaluation']['records']];v=row['metadata']['multi_objective'];obj,cons,is_ok=vector_values(ps)
                if len(ps)!=2 or {p['seed'] for p in ps}!=set(design['tuning_seeds']) or any(p['role']!='tuning' for p in ps):raise AssertionError('Vector tuning barrier differs')
                for k in obj:close(v['objectives'][k],obj[k])
                for k in cons:close(v['constraints'][k],cons[k])
                check_feasibility(v['feasible'],cons)
                if is_ok:feasible.append((row['trial_id'],np.array([obj['error'],obj['size']])))
            front=check_front(result['front'],feasible)
            if not front and (result['reason']!='no_feasible_full_fidelity_result' or result['evaluation']['final']):raise AssertionError('Infeasible outcome fabricated finals')
            if len(result['evaluation']['final'])!=len(front):raise AssertionError('Missing vector final evaluation')
            final_ok=[]
            for final,selected in zip(result['evaluation']['final'],result['front']):
                ps=[get_raw(x['result']['metadata']['artifacts']['model']) for x in final['records']]
                if len(ps)!=2 or {p['seed'] for p in ps}!=set(design['final_seeds']) or any(p['role']!='final' or p['config']!=selected['config'] for p in ps):raise AssertionError('Vector final barrier differs')
                obj,cons,is_ok=vector_values(ps)
                for key in obj:close(obj[key],final['objectives'][key]['mean'])
                check_feasibility(final['feasible'],cons);final_ok.append(is_ok)
            if final_ok and not all(final_ok) and result['reason']!='final_evaluation_infeasible':raise AssertionError('Adverse final result concealed')
            report=read(directory/'report.json')
            for role in ('tuning','final'):
                work=sum(p['work'] for path,p in raw.items() if Path(path).parent==directory.resolve()/'models' and p['role']==role);close(report['resources'][role]['measured_work'],work)
            vector_count+=1
        if name=='transport':
            for method in design['methods']:transitions+=verify_handoff(base/method/'handoff.json')
    if name=='nas':
        stream=read(root/'streaming/summary.json');assert stream['passed'] and stream['projection_matches'];a=read(root/'streaming/uninterrupted/result.json');b=read(root/'streaming/recovered/result.json');close([r['objective_value'] for r in a['history']],[r['objective_value'] for r in b['history']])
    return {'passed':True,'name':name,'models_reconstructed':models,'independent_unique_reconstructions':len(cache),'scalar_studies':studies,'vector_studies':vector_count,'hmc_transitions_replayed':transitions,'adverse_assessments':adverse}

def verify_all():
    results=[]
    for name in ('forecast','wallet','policy','nas','transport'):
        eligible=[p.parent for p in BASE.glob('*-'+name+'-*/receipt.json') if read(p)['passed']]
        if eligible:results.append(verify_family(eligible[0]/'results'))
    if not results:raise ValueError('No completed family to verify')
    return {'passed':True,'families':results,'scope':'Only listed completed families reconstructed; missing families remain pending.'}
