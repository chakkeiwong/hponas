"""No new fitting: audit immutable evidence and reconstruct NAS/HMC/policy."""
import copy,hashlib,itertools,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from references import close,net_numpy,policy_truth,enumerate_value,policy_reference
from app02_trace import LIMITS,payload
BASE=ROOT/'docs/program/evidence/2026-10-25/app-02'

def read(p):return json.loads(Path(p).read_text())
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def roster(actual,expected):
    assert len(actual)==len(expected) and len(set(actual))==len(actual) and set(actual)==set(expected)

def validate_nas_groups(summary,models):
    roster([(g['arm'],g['training_rows'],g['epoch']) for g in summary['groups']],
           list(itertools.product(('random','boundary'),(48,80),(120,480))))
    for g in summary['groups']:
        chosen=[next(c for c in row['checkpoints'] if c['epoch']==g['epoch']) for row in models
                if row['arm']==g['arm'] and row['training_rows']==g['training_rows']]
        assert len(chosen)==g['fits']
        assert sum(c['scores']['mesh']['feasible'] for c in chosen)==g['mesh_feasible']
        assert sum(c['scores']['final']['feasible'] for c in chosen)==g['final_feasible']
        close(max(c['scores']['mesh']['max_limit_ratio'] for c in chosen),g['worst_ratio'])
        close(np.mean([c['scores']['mesh']['loss'] for c in chosen]),g['mean_mesh_loss'])

def reject(label,fn,controls):
    try:fn()
    except (AssertionError,ValueError):controls.append(label)
    else:raise AssertionError('False evidence accepted: '+label)

def policy_actions(config):
    delta=np.array([-1.,0.,1.])[None,:]-config['threshold']-config['time_slope']*np.arange(3)[:,None]
    return (delta>0 if config['direction']=='greater' else delta<0).astype(int)

def policy_grid(repaired):
    return [dict(direction=d,threshold=t,time_slope=s,smoothing=k) for d,t,s,k in itertools.product(
        ('greater','less') if repaired else ('greater',),(-1.5,-.5,.5,1.5),(0.,.3),(.1,1.,10.))]

def policy_record(row,data,declaration):
    assert row['role'] in ('tuning','final')
    fold=declaration['tuning_folds' if row['role']=='tuning' else 'final_folds'][0]
    assert row['train_ids']==fold['train_ids'] and row['score_ids']==fold['score_ids']
    assert not set(row['train_ids'])&set(row['score_ids'])
    close(row['model']['actions'],policy_actions(row['config']))
    loss,contributions,value=policy_reference(row['model'],[data[i] for i in row['score_ids']])
    close(loss,row['loss']);close(contributions,row['metrics']['contributions']);close(value,row['metrics']['true_value'])
    return loss,value

def reconstruct_hmc(label,model,length,seed):
    def law(q):
        if label=='identity':u,j,s=0.,0.,1.
        elif label=='exact':u,j,s=.35*(q[0]**2-1),.7*q[0],1.
        else:
            v,jac=net_numpy(model,q[None,:1]);u,j,s=v[0],jac[0,0],math.exp(model['log_scale'])
        x=np.array([q[0],s*q[1]+u]);res=x[1]-.35*(x[0]**2-1)
        return -.5*(x[0]**2+res**2)+math.log(s),np.array([-x[0]-res*(j-.7*x[0]),-res*s]),x
    rng=np.random.default_rng(seed);chains=[];accepted=0;moves=[]
    for chain in range(2):
        q=rng.normal(size=2);draws=[]
        for t in range(320):
            p=rng.normal(size=2);logu=math.log(rng.uniform());old=law(q)[2];initial=law(q)[0]-.5*float(p@p);qn=q.copy();pn=p.copy()
            for k in range(length):
                pn+=.075*law(qn)[1];qn+=.15*pn;pn+=.075*law(qn)[1]
            loga=min(0.,law(qn)[0]-.5*float(pn@pn)-initial)
            if logu<loga:q=qn;accepted+=1
            if t>=64:draws.append(law(q)[2]);moves.append(float(np.sum((law(q)[2]-old)**2)))
        chains.append(np.array(draws))
    return np.array(chains),accepted/640,float(np.mean(moves))

def run(out):
    manifest=read(BASE/'final-audit-manifest-01.json');runs={k:ROOT/v for k,v in manifest['runs'].items()}
    receipt_checks=[]
    for name,path in runs.items():
        receipt=read(path/'receipt.json');assert receipt['passed'] and receipt['inputs_unchanged']
        assert receipt['source_digest']==receipt['end_source_digest']==manifest['source_digest']
        assert receipt['remaining_owned_pids']==[] and receipt['returncode']==0 and receipt['stop_reason'] is None
        for item in receipt['inputs']:assert bind(ROOT/item['path'])==item
        assert bind(ROOT/receipt['manifest']['path'])==receipt['manifest'];assert bind(ROOT/receipt['log']['path'])==receipt['log']
        receipt_checks.append(name)
    wallet=read(runs['wallet-review']/'review.json');wallet_close=read(runs['wallet-close']/'closure.json')
    assert wallet['checked_model_records']==468 and wallet_close['reconstructed_fresh_fits']==294
    assert len(wallet['controls'])==3 and wallet_close['maximum_moment_formula_error']<1e-9
    refit=read(runs['refit']/'refit.json');nas=[];mesh=np.array(list(itertools.product(np.linspace(-.5,.5,81),np.linspace(.2,.6,81))))
    expected=set(itertools.product((2201,2202,2203),(4,8),(48,80),(17,29),('random','boundary')))
    keys=[];verified=0
    for path in sorted(runs['refit'].glob('fit-*.json')):
        row=read(path);keys.append(tuple(row[k] for k in ('replicate','width','training_rows','seed','arm')))
        data=read(runs['refit']/('data-'+str(row['replicate'])+'.json'))
        train=np.array(data['raw'][:row['training_rows']])
        if row['arm']=='boundary':train[:8]=np.array(data['boundary'])
        assert [c['epoch'] for c in row['checkpoints']]==[120,480]
        for c in row['checkpoints']:
            for role,points in [('train',train),('final',np.array(data['final'])),('mesh',mesh)]:
                y,jac=net_numpy(c['model'],points);target=np.exp(-points[:,0]*points[:,1]);reference=np.column_stack((-points[:,1]*target,-points[:,0]*target));errors=np.abs(jac-reference)
                maximum=errors.max(0);ratio=float(max(maximum/np.array([LIMITS['dx'],LIMITS['da']])));s=c['scores'][role]
                close(maximum,[s['dx_max'],s['da_max']]);close(ratio,s['max_limit_ratio']);assert s['feasible']==(ratio<=1)
                close(np.mean((y-target)**2)+np.mean(errors**2,axis=0).sum(),s['loss'])
            verified+=1
        nas.append(row)
    roster(keys,expected);assert verified==96
    validate_nas_groups(refit,nas)
    tr=read(runs['transport']/'transport.json');transport=[];transitions=0
    for path in sorted(runs['transport'].glob('*.json')):
        row=read(path)
        if not isinstance(row,dict) or not {'map','length','seed','draws'}<=set(row):continue
        if row['source']:assert bind(ROOT/row['source']['path'])==row['source']
        model=payload(ROOT/row['source']['path'])['model'] if row['source'] else None
        draws,acceptance,jump=reconstruct_hmc(row['map'],model,row['length'],row['seed']);close(draws,row['draws'],tol=1e-8);close(acceptance,row['acceptance'])
        flat=draws.reshape(-1,2);close(flat.mean(0),row['mean']);close((flat*flat).mean(0),row['second_moment'])
        close(np.abs(flat.mean(0)).max(),row['max_mean_error']);close(np.abs((flat*flat).mean(0)-[1.,1.245]).max(),row['max_moment_error'])
        close(np.mean([np.corrcoef(d[:-1,0],d[1:,0])[0,1] for d in draws]),row['x1_lag1']);close(jump,row['mean_squared_jump'])
        assert row['gradient_evaluations']==640*(row['length']+1)
        transport.append(row);transitions+=640
    transport_keys=[(r['map'],r['length'],r['seed']) for r in transport]
    expected_transport=list(itertools.product(('identity','exact','learned-401','learned-502','learned-603'),(1,8),(3101,3102,3103)))
    roster(transport_keys,expected_transport);assert transitions==19200
    roster([(g['map'],g['length']) for g in tr['groups']],list(itertools.product(('identity','exact','learned-401','learned-502','learned-603'),(1,8))))
    for group in tr['groups']:
        rows=[x for x in transport if x['map']==group['map'] and x['length']==group['length']];assert len(rows)==3
        for k in ('acceptance','max_mean_error','max_moment_error','x1_lag1','mean_squared_jump'):close(np.mean([r[k] for r in rows]),group[k])
    for row in tr['exact_flow_gaussian_reference']:
        rho=math.cos(row['integration_time']);close(rho,row['rho']);close((1+rho)/(1-rho),row['stationary_iact'])
        covariance=rho**np.abs(np.arange(256)[:,None]-np.arange(256)[None,:]);close(covariance.mean(),row['finite_256_mean_variance'])
    policy=read(runs['policy']/'policy.json');tp,rew=policy_truth()
    oracle=max(enumerate_value(tp,rew,np.array(bits).reshape(3,3)) for bits in itertools.product((0,1),repeat=9))
    close(oracle,policy['oracle']);close(policy['repaired_best'],oracle);assert policy['legacy_best']<oracle
    close(max(enumerate_value(tp,rew,policy_actions(c)) for c in policy_grid(False)),policy['legacy_best'])
    close(max(enumerate_value(tp,rew,policy_actions(c)) for c in policy_grid(True)),policy['repaired_best'])
    roster([(r['replicate'],r['repaired']) for r in policy['studies']],list(itertools.product((4201,4202,4203),(False,True))))
    policy_fits=0;policy_context=None
    for summary in policy['studies']:
        directory=runs['policy']/str(summary['replicate'])/('repaired' if summary['repaired'] else 'legacy')
        data=read(directory/'data.json');declaration=read(directory/'declaration.json');result=read(directory/'result.json')
        models=[read(p) for p in sorted((directory/'models').glob('*.json'))]
        tune=[r for r in models if r['role']=='tuning'];final=[r for r in models if r['role']=='final']
        assert len(final)==1 and len(models)==len(tune)+1
        canonical=lambda c:json.dumps(c,sort_keys=True)
        roster([canonical(r['config']) for r in tune],[canonical(c) for c in policy_grid(summary['repaired'])])
        for row in models:policy_record(row,data,declaration);policy_fits+=1
        close(min(r['loss'] for r in tune),result['best_value']);close(result['best_value'],summary['best_validation'])
        assert final[0]['config']==result['best_config']['values']==summary['best_config']
        assert any(r['config']==summary['best_config'] and abs(r['loss']-result['best_value'])<1e-12 for r in tune)
        close(-final[0]['loss'],summary['final_estimated_value']);close(final[0]['metrics']['true_value'],summary['exact_selected_policy_value'])
        close(oracle-summary['exact_selected_policy_value'],summary['exact_policy_regret'])
        assert summary['models']==len(models)
        policy_context=(models[0],data,declaration)
    assert policy_fits==policy['fits_independently_rescored']==222
    controls=[]
    bad=copy.deepcopy(refit);bad['groups'][0]['mesh_feasible']+=1
    reject('false NAS count rejected',lambda:validate_nas_groups(bad,nas),controls)
    reject('omitted NAS cell rejected',lambda:roster(keys[:-1],expected),controls)
    reject('duplicate transport cell rejected',lambda:roster(transport_keys[:-1]+[transport_keys[0]],expected_transport),controls)
    row,data,declaration=policy_context;bad=copy.deepcopy(row);bad['loss']+=.1
    reject('altered policy score rejected',lambda:policy_record(bad,data,declaration),controls)
    bad=copy.deepcopy(row);bad['score_ids'][0]=bad['train_ids'][0]
    reject('policy role leakage rejected',lambda:policy_record(bad,data,declaration),controls)
    result=dict(passed=True,stage='APP-02/FINAL-REVIEW',qualified_core_unchanged=True,receipts_verified=receipt_checks,
                wallet_prior_independent_reconstructions_verified=762,nas_checkpoints_reconstructed=verified,transport_transitions_replayed=transitions,
                exact_policies_recomputed=512,policy_fits_independently_scored=policy_fits,negative_controls=controls,
                open_limits=['NAS full repair remains unestablished despite paired boundary improvement.','Wallet CV is mixed; no method/default promotion.','Short-chain diagnostics do not establish sampler convergence or equal-cost superiority.','Synthetic mechanism coverage is not full sibling-project/real-bank or general neural-NAS coverage.'],
                conclusion='APP-02 bounded investigations completed with adverse outcomes and unsupported claims explicitly retained; no universal scientific success inferred.')
    with (out/'audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
