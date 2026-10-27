"""Finite policy cross-fitting and explicit identification/overlap abstention."""
from contextlib import closing
import copy,itertools,sys
import numpy as np
from common import *
from models import generate,policy_fit,policy_score
from references import close,policy_reference,policy_truth,enumerate_value
from app02_policy import configurations,actions
def admissible(rows,identification):
    if identification!='known_randomized_logger':raise ValueError('Unsupported identification: no point policy value')
    for row in rows:
        if any(not 0<t[4]<1 for t in row['trajectory']):raise ValueError('Unsupported overlap')
def nuisance(cfg,rows):
    model=policy_fit(cfg,rows);k=cfg['smoothing'];counts=np.ones((3,2,3))*k/3;rewards=np.zeros((3,2));n=np.ones((3,2))*k
    for row in rows:
        for s,a,y,ns,_ in row['trajectory']:counts[s,a,ns]+=1;rewards[s,a]+=y;n[s,a]+=1
    close(model['transition'],counts/counts.sum(2,keepdims=True));close(model['reward'],rewards/n);return model
class Objective:
    def __init__(self,seed,out):
        self.data,self.ids=generate('policy',seed);self.out=out;self.cache={};self.records=[];self.fits=0
        dev=self.ids['train']+self.ids['validation'];order=np.random.default_rng(seed+10000).permutation(len(dev));halves=[tuple(dev[i] for i in x) for x in np.array_split(order,2)]
        self.space=SearchSpace([Knob('index','categorical',list(range(48)))]);self.grid=configurations(True)
        self.declaration=StudyDeclaration(objective_id='crossfit-DR-policy',model_id='twofold-tabular-nuisance',data_id=str(seed),protocol_id='app03-policy-v1',
            objectives=(EvaluationObjective('loss','min','negative_DR_value'),),tuning_folds=tuple(EvaluationFold('crossfit'+str(j),halves[1-j],halves[j]) for j in range(2)),
            final_folds=(EvaluationFold('final',tuple(dev),tuple(self.ids['final'])),),tuning_seeds=(0,),final_seeds=(1000,))
    def __call__(self,config,seed,evaluation,trial_id):
        cfg=self.grid[config['index']];role=evaluation.role;fold=evaluation.fold
        assert evaluation.declaration_identity==self.declaration.identity and fold in (self.declaration.tuning_folds if role=='tuning' else self.declaration.final_folds)
        assert seed==(0 if role=='tuning' else 1000)
        train=[self.data[i] for i in fold.train_ids];score=[self.data[i] for i in fold.score_ids];admissible(train+score,'known_randomized_logger')
        key=(fold.name,cfg['smoothing']);new=key not in self.cache
        if new:self.cache[key]=nuisance(cfg,train);self.fits+=1
        model=copy.deepcopy(self.cache[key]);model['config']=cfg;model['actions']=actions(cfg).tolist()
        loss,metrics=policy_score(model,score);independent,contributions,value=policy_reference(model,score);close(loss,independent);close(metrics['contributions'],contributions);close(metrics['true_value'],value)
        record={'config':config,'physical':cfg,'role':role,'fold':fold.name,'train_ids':list(fold.train_ids),'score_ids':list(fold.score_ids),'model':model,'loss':loss,'metrics':metrics,'new_nuisance_fit':new}
        path=self.out/'models'/(trial_id+'.json');save(path,record);self.records.append(record)
        return {'value':loss,'artifacts':{'model':str(path)},'metadata':{'resource':{'work':3*(len(train) if new else 0)+3*len(score),'unit':'trajectory_steps'}}}
def run(out):
    summaries=[];fits=0;tp,tr=policy_truth();oracle=max(enumerate_value(tp,tr,np.array(bits).reshape(3,3)) for bits in itertools.product((0,1),repeat=9))
    for seed in (9601,9602,9603):
        directory=out/str(seed);directory.mkdir();obj=Objective(seed,directory);save(directory/'data.json',obj.data);save(directory/'declaration.json',obj.declaration.contract)
        with closing(Store(directory/'study.sqlite')) as store:
            study=Study(Enumeration(obj.space,[{'index':i} for i in range(48)]),LocalExecutor(),obj,maximize=False,budget=48,study_name='crossfit_policy_'+str(seed),checkpoint_dir=directory,store=store,declaration=obj.declaration,
               resource_budget=StudyBudget(configurations=48,work_unit='trajectory_steps',tuning_work=200000,final_work=10000,max_work_per_call=10000))
            result=study.run();save(directory/'result.json',result.to_dict());save(directory/'report.json',study.report())
        tune=[x for x in obj.records if x['role']=='tuning'];final=[x for x in obj.records if x['role']=='final'];assert len(tune)==96 and len(final)==1 and obj.fits==7
        means=[np.mean([x['loss'] for x in tune if x['config']['index']==i]) for i in range(48)];close(min(means),result.best_value)
        c=final[0]['metrics']['contributions'];estimate=-final[0]['loss'];se=float(np.std(c,ddof=1)/np.sqrt(len(c)))
        summary={'seed':seed,'selected':result.best_config.values,'physical':final[0]['physical'],'final_value_estimate':estimate,'final_iid_standard_error':se,'exact_value':final[0]['metrics']['true_value'],'exact_regret':oracle-final[0]['metrics']['true_value'],'nuisance_fits':obj.fits,'evaluations':97,'standard_error_scope':'Conditional on frozen selected policy and independently fitted nuisance; finite sample SE, not a coverage guarantee.'}
        summaries.append(summary);fits+=obj.fits;save(directory/'summary.json',summary);print(canon(summary),flush=True)
    bad=copy.deepcopy(obj.data[obj.ids['final'][0]]);bad['trajectory'][0][4]=0
    controls={'overlap_refusal':reject(lambda:admissible([bad],'known_randomized_logger')),'unknown_identification_refusal':reject(lambda:admissible([bad],'unknown'))}
    # Y=A observationally in both worlds. World1:Y(a)=a; World2:Y(a)=U,A=U.
    observed1=[(.5,0,0),(.5,1,1)];observed2=[(.5,0,0),(.5,1,1)];assert observed1==observed2
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'crossfit_workflow_and_identification_abstention_verified','nuisance_fits':fits,'evaluations':291,'oracle':oracle,'studies':summaries,'controls':controls,'confounding_witness':{'same_observed_law':observed1,'world1_ATE':1,'world2_ATE':0,'conclusion':'Observational law alone cannot identify causal policy benefit.'},'real_bank_recommendation':False})
if __name__=='__main__':run(Path(sys.argv[1]))
