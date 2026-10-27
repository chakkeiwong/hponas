"""Local policy-class successor: both directions, exact oracle, public Study."""
from contextlib import closing
import itertools,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hpo-survey/applications'))
from models import generate,policy_fit,policy_score,policy_dp,P,R,INITIAL,STATES
from references import policy_truth,enumerate_value,policy_reference,close
from hponas import Study,StudyDeclaration,EvaluationFold,EvaluationObjective,StudyBudget,SearchSpace,Knob,LocalExecutor
from hponas.types import Config
from hponas.searchers.base import BaseSearcher,SearchSpaceExhaustedError
from hponas.capabilities import SearcherCapabilities,MIXED
from hponas.store import Store

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(obj,f,indent=2,allow_nan=False)

def configurations(repaired):
    return [dict(direction=d,threshold=t,time_slope=s,smoothing=k) for d,t,s,k in itertools.product(
       ('greater','less') if repaired else ('greater',),(-1.5,-.5,.5,1.5),(0.,.3),(.1,1.,10.))]

def actions(cfg):
    compare=STATES[None,:]-cfg['threshold']-cfg['time_slope']*np.arange(3)[:,None]
    return (compare>0 if cfg['direction']=='greater' else compare<0).astype(int)

class Enumeration(BaseSearcher):
    support=SearcherCapabilities(MIXED)
    def __init__(self,space,grid):super().__init__(space,0);self.grid=grid;self.cursor=0
    def suggest(self):
        if self.cursor>=len(self.grid):raise SearchSpaceExhaustedError('Finite policy grid consumed')
        c=Config(values=dict(self.grid[self.cursor]));self.cursor+=1;return c
    def get_state(self):return {**super().get_state(),'grid':self.grid,'cursor':self.cursor}
    def set_state(self,state):
        if state['grid']!=self.grid or type(state['cursor']) is not int or not 0<=state['cursor']<=len(self.grid):raise ValueError('Changed policy enumeration')
        super().set_state(state);self.cursor=state['cursor']

class Objective:
    def __init__(self,rep,repaired,out):
        self.data,self.ids=generate('policy',rep);self.grid=configurations(repaired);self.out=out;self.records=[]
        self.space=SearchSpace([Knob('direction','categorical',['greater','less']),Knob('threshold','categorical',[-1.5,-.5,.5,1.5]),Knob('time_slope','categorical',[0.,.3]),Knob('smoothing','categorical',[.1,1.,10.])])
        self.declaration=StudyDeclaration(objective_id='policy-direction-repair',model_id='dr-policy-finite',data_id='policy-fresh-'+str(rep),protocol_id='app02-policy-direction-v1',
          objectives=(EvaluationObjective('loss','min','negative_DR_value'),),tuning_folds=(EvaluationFold('validation',tuple(self.ids['train']),tuple(self.ids['validation'])),),
          final_folds=(EvaluationFold('final',tuple(self.ids['train']+self.ids['validation']),tuple(self.ids['final'])),),tuning_seeds=(0,),final_seeds=(1000,))
    def __call__(self,config,seed,evaluation,trial_id):
        if config not in self.grid or evaluation.declaration_identity!=self.declaration.identity:raise ValueError('Configuration/declaration')
        folds=self.declaration.tuning_folds if evaluation.role=='tuning' else self.declaration.final_folds if evaluation.role=='final' else ()
        if evaluation.fold not in folds or seed!=(0 if evaluation.role=='tuning' else 1000):raise ValueError('Role mismatch')
        fold=evaluation.fold;train=[self.data[i] for i in fold.train_ids];score=[self.data[i] for i in fold.score_ids]
        model=policy_fit(config,train);model['actions']=actions(config).tolist();loss,metrics=policy_score(model,score)
        independent,contributions,value=policy_reference(model,score);close(loss,independent);close(metrics['true_value'],value)
        record=dict(config=config,role=evaluation.role,train_ids=list(fold.train_ids),score_ids=list(fold.score_ids),model=model,loss=loss,metrics=metrics)
        path=self.out/'models'/(trial_id+'.json');save(path,record);self.records.append(record)
        return dict(value=loss,artifacts={'model':str(path)},metadata={'resource':{'work':len(train)*3,'unit':'trajectory_steps'}})

def run(out):
    tp,tr=policy_truth();close(tp,P);close(tr,R);all_values=[]
    for bits in itertools.product((0,1),repeat=9):
        a=np.array(bits).reshape(3,3);v=enumerate_value(tp,tr,a);dp=policy_dp(P,R,a)[0];close(v,float(INITIAL@dp[0]));all_values.append((v,a.tolist()))
    oracle=max(v for v,a in all_values);old=max(enumerate_value(tp,tr,actions(c)) for c in configurations(False));new=max(enumerate_value(tp,tr,actions(c)) for c in configurations(True))
    close(new,oracle);assert old<oracle-1e-3
    unique_old=len({tuple(actions(c).reshape(-1)) for c in configurations(False)});unique_new=len({tuple(actions(c).reshape(-1)) for c in configurations(True)})
    runs=[];count=0
    for rep,repaired in itertools.product((4201,4202,4203),(False,True)):
        directory=out/str(rep)/('repaired' if repaired else 'legacy');obj=Objective(rep,repaired,directory);search=Enumeration(obj.space,obj.grid);directory.mkdir(parents=True)
        save(directory/'data.json',obj.data);save(directory/'declaration.json',obj.declaration.contract);start=time.monotonic()
        with closing(Store(directory/'study.sqlite')) as store:
            study=Study(search,LocalExecutor(),obj,maximize=False,budget=len(obj.grid),study_name=f'policy_{rep}_{repaired}',checkpoint_dir=directory,store=store,declaration=obj.declaration,
              resource_budget=StudyBudget(configurations=len(obj.grid),work_unit='trajectory_steps',tuning_work=48*10000,final_work=10000,max_work_per_call=10000))
            result=study.run();save(directory/'report.json',study.report());save(directory/'result.json',result.to_dict())
        tune=[r for r in obj.records if r['role']=='tuning'];final=[r for r in obj.records if r['role']=='final'];assert len(tune)==len(obj.grid) and len(final)==1
        close(min(r['loss'] for r in tune),result.best_value);assert final[0]['config']==result.best_config.values
        row=dict(replicate=rep,repaired=repaired,best_config=result.best_config.values,best_validation=result.best_value,final_estimated_value=-final[0]['loss'],
          exact_selected_policy_value=final[0]['metrics']['true_value'],exact_policy_regret=oracle-final[0]['metrics']['true_value'],seconds=time.monotonic()-start,models=len(obj.records))
        runs.append(row);count+=len(obj.records);print(json.dumps(row),flush=True)
    assert count==222
    result=dict(passed=True,stage='APP-02/POLICY',enumerated_policies=512,oracle=oracle,legacy_best=old,repaired_best=new,unique_legacy_policies=unique_old,unique_repaired_policies=unique_new,
      fits_independently_rescored=count,studies=runs,conclusion='The original increasing-threshold class excludes the exact optimum; adding the decreasing direction includes it. Finite noisy DR selection can still miss the best policy; repaired class support is not a statistical performance guarantee.',
      scope='Local synthetic successor only; originalAPP-01 source and evidence unchanged. No real-bank policy recommendation.')
    save(out/'policy.json',result);print(json.dumps({k:v for k,v in result.items() if k!='studies'}),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
