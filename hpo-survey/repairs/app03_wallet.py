"""Decision-aligned finite wallet selection with bounded uncertainty and MNAR witness."""
from contextlib import closing
import math,sys
import numpy as np
from scipy.special import ndtr,expit
from common import *
from wallet_model import GRID,generate,observed_rows,fit,empirical_loss,capped_mean,parameters,CAPS,FEES,population_metrics
from wallet_preflight import scalar_nll
from references import close,normal_cdf
SEEDS=(5301,5302,5303)
def actions(model,x):
    parts=parameters(np.array(model['theta']),x,model['config'])
    return np.column_stack((np.zeros(len(x)),np.column_stack([capped_mean(parts,c) for c in CAPS])-FEES)).argmax(1)
def utilities(action,w):
    return np.minimum(w,np.r_[0.,CAPS][action])-np.r_[0.,FEES][action]
def scalar_actions(model,x):
    mu,sig,eta=parameters(np.array(model['theta']),x,model['config']);chosen=[]
    for m,s,e in zip(mu,sig,eta):
        vals=[0.]
        for cap,fee in zip(CAPS,FEES):
            t0=-m/s;t1=(math.log1p(cap)-m)/s
            v=expit(e)*(math.exp(m+s*s/2)*(normal_cdf(t1-s)-normal_cdf(t0-s))-normal_cdf(t1)+normal_cdf(t0)+cap*normal_cdf(-t1))-fee
            vals.append(v)
        chosen.append(int(np.argmax(vals)))
    return np.array(chosen)
def intervals(means,n,alpha):
    # Every policy utility lies in [-max fee, max cap-min fee]. Use conservative [-.15,3].
    radius=3.15*math.sqrt(math.log(2*24/alpha)/(2*n))
    return np.column_stack((np.maximum(-.15,means-radius),np.minimum(3.,means+radius)))
def identification():
    # Same observed distribution: probability observed=.75, observed mean1.
    # Unobserved capped wallets0 or3 are observationally indistinguishable.
    low=.75;high=.75+.25*3
    assert low!=high
    for missing_mean in (0.,.5,2.,3.):assert low<=.75+.25*missing_mean<=high
    return {'observation_probability':.75,'observed_capped_mean':1.,'sharp_population_interval':[low,high],
            'two_laws_observed_distribution_equal':True,'point_identified_without_missingness_assumption':False,
            'interpretation':'Bounds for cap3; MCAR identifies observed mean, unknown MNAR does not. No generic real-wallet identification claim.'}
class Objective:
    def __init__(self,data,seed,out):
        self.data=data;self.out=out;self.models={};self.records=[]
        self.space=SearchSpace([Knob('index','categorical',list(range(24)))])
        ids={r:tuple(i for i,ok in zip(d['ids'],d['observed']) if ok) for r,d in data.items()}
        self.declaration=StudyDeclaration(objective_id='wallet-observed-decision-utility',model_id='frozen-training-only-wallet',data_id=str(seed),protocol_id='app03-wallet-v1',
          objectives=(EvaluationObjective('utility','max','capped_wallet_less_fee'),),tuning_folds=(EvaluationFold('validation',ids['train'],ids['validation']),),
          final_folds=(EvaluationFold('final',ids['train'],ids['final']),),tuning_seeds=(0,),final_seeds=(1000,))
    def __call__(self,config,seed,evaluation,trial_id):
        i=config['index'];role=evaluation.role;fold=self.declaration.tuning_folds[0] if role=='tuning' else self.declaration.final_folds[0]
        assert evaluation.declaration_identity==self.declaration.identity and evaluation.fold==fold and role in ('tuning','final')
        assert seed==(0 if role=='tuning' else 1000)
        if role=='tuning':
            assert i not in self.models
            x,y=observed_rows(self.data,('train',));self.models[i]=fit(GRID[i],x,y);work=self.models[i]['work']
        else:assert i in self.models;work=len(fold.score_ids)
        model=self.models[i];x,w=observed_rows(self.data,('validation' if role=='tuning' else 'final',))
        a=actions(model,x);assert np.array_equal(a,scalar_actions(model,x));u=utilities(a,w);nll=empirical_loss(model,x,w)
        close(nll,scalar_nll(np.array(model['theta']),x,w,model['config']))
        record={'index':i,'role':role,'model':model,'train_ids':list(fold.train_ids),'score_ids':list(fold.score_ids),'actions':a.tolist(),'utility':float(u.mean()),'nll':nll,'new_fit':role=='tuning'}
        path=self.out/'models'/(trial_id+'.json');save(path,record);self.records.append(record)
        return {'value':float(u.mean()),'artifacts':{'model':str(path)},'metadata':{'resource':{'work':work,'unit':'likelihood_or_score_rows'}}}
def run(out):
    rows=[]
    for seed in SEEDS:
        data=generate(seed);directory=out/str(seed);directory.mkdir();save(directory/'data.json',{r:{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in d.items()} for r,d in data.items()})
        obj=Objective(data,seed,directory);grid=[{'index':i} for i in range(24)]
        with closing(Store(directory/'study.sqlite')) as store:
            study=Study(Enumeration(obj.space,grid),LocalExecutor(),obj,maximize=True,budget=24,study_name='decision_'+str(seed),checkpoint_dir=directory,store=store,declaration=obj.declaration,
                resource_budget=StudyBudget(configurations=24,work_unit='likelihood_or_score_rows',tuning_work=24*20000000,final_work=20000000,max_work_per_call=20000000))
            result=study.run();save(directory/'result.json',result.to_dict());save(directory/'report.json',study.report());save(directory/'declaration.json',obj.declaration.contract)
        tune=sorted([r for r in obj.records if r['role']=='tuning'],key=lambda r:r['index']);final=[r for r in obj.records if r['role']=='final'];assert len(tune)==24 and len(final)==1
        selected=result.best_config.values['index'];likelihood=min(tune,key=lambda r:r['nll'])['index'];close(result.best_value,max(r['utility'] for r in tune))
        means=np.array([r['utility'] for r in tune]);n=len(tune[0]['score_ids']);bands={str(level):intervals(means,n,1-level).tolist() for level in (.90,.95,.99)}
        vx,vw=observed_rows(data,('final',));la=actions(obj.models[likelihood],vx);likelihood_final=float(utilities(la,vw).mean())
        pop={str(i):population_metrics(obj.models[i],96) for i in {selected,likelihood}}
        row={'seed':seed,'selected':selected,'likelihood_selected':likelihood,'final_utility':final[0]['utility'],'likelihood_final_utility':likelihood_final,
             'final_utility_difference':final[0]['utility']-likelihood_final,'candidate_utilities':means.tolist(),'simultaneous_intervals':bands,'observed_validation_rows':n,
             'certified_above_no_action_95':bool(bands['0.95'][selected][0]>0),'population':pop,'new_fits':24,'final_refit':False}
        rows.append(row);save(directory/'summary.json',row);print(canon({'seed':seed,'difference':row['final_utility_difference'],'certified':row['certified_above_no_action_95']}),flush=True)
    negative=reject(lambda:close(utilities(np.array([0]),np.array([100.])),np.array([1.])))
    summary={'mechanics_passed':True,'scientific_status':'decision_objective_alignment_verified; empirical_comparison_retained_without_superiority_claim',
       'fits':72,'studies':rows,'identification':identification(),'controls':{'false_no_action_utility_rejected':negative},
       'limits':['Simultaneous bounds require independent MCAR validation conditional on training; no pointwise guarantee.','Intervals do not apply to unbounded NLL.','No refit after selection: the certified policies are frozen training-only models.','MCAR is simulated; real missingness remains an assumption.']}
    save(out/'result.json',summary)
if __name__=='__main__':run(Path(sys.argv[1]))
