"""Rolling-origin independent forecasts with explicit information gaps."""
from contextlib import closing
import copy,itertools,sys
import numpy as np
from common import *
from models import generate,forecast_fit,forecast_score,forecast_features
from references import forecast_reference,close
GRID=[{'lag':l,'ridge':r,'variance':.4} for l,r in itertools.product((1,2),(.01,1.))]
class Objective:
    def __init__(self,seed,out):
        self.data,_=generate('forecast',seed);self.ids=sorted(self.data,key=lambda i:self.data[i]['time']);self.out=out;self.records=[]
        def fold(name,end,start,stop):return EvaluationFold(name,tuple(self.ids[:end]),tuple(self.ids[start:stop]),mode='temporal',train_until=end-1,score_from=start,score_until=stop-1,gap=1.)
        self.declaration=StudyDeclaration(objective_id='rolling-one-step-forecast',model_id='ridge-linear-Gaussian',data_id=str(seed),protocol_id='app03-forecast-v1',
           objectives=(EvaluationObjective('nll','min','predictive_nll'),),tuning_folds=(fold('rolling1',32,34,48),fold('rolling2',48,50,64)),final_folds=(fold('final',72,74,96),),tuning_seeds=(0,),final_seeds=(1000,))
        self.space=SearchSpace([Knob('index','categorical',list(range(4)))])
    def __call__(self,config,seed,evaluation,trial_id):
        role=evaluation.role;fold=evaluation.fold;cfg=GRID[config['index']]
        assert evaluation.declaration_identity==self.declaration.identity and fold in (self.declaration.tuning_folds if role=='tuning' else self.declaration.final_folds)
        assert seed==(0 if role=='tuning' else 1000)
        train=[self.data[i] for i in fold.train_ids];score=[self.data[i] for i in fold.score_ids];model=forecast_fit(cfg,train)
        # Missing observations propagate state through embargo without exposing gap outcomes.
        gap=[copy.deepcopy(self.data[i]) for i in self.ids if fold.train_until<self.data[i]['time']<fold.score_from]
        for row in gap:row['y']=None
        history=train+gap;loss,metrics=forecast_score(model,history,score);reference,trace=forecast_reference(model,history,score);close(loss,reference)
        for a,b in zip(metrics['trace'],trace):
            for k in ('mean','variance','nll'):close(a[k],b[k])
        observed=[r for r in train if r['y'] is not None];x=forecast_features(observed,cfg['lag']);y=np.array([r['y'] for r in observed]);regularizer=np.diag(np.sqrt([0.]+[cfg['ridge']]*(x.shape[1]-1)))
        close(np.linalg.lstsq(np.vstack((x,regularizer)),np.r_[y,np.zeros(x.shape[1])],rcond=None)[0],model['weights'])
        rec={'config':config,'physical':cfg,'role':role,'fold':fold.name,'train_ids':list(fold.train_ids),'score_ids':list(fold.score_ids),'gap_rows':gap,'model':model,'loss':loss,'trace':trace}
        path=self.out/'models'/(trial_id+'.json');save(path,rec);self.records.append(rec)
        return {'value':loss,'artifacts':{'model':str(path)},'metadata':{'resource':{'work':len(history)+len(score),'unit':'time_rows'}}}
def run(out):
    summaries=[]
    for seed in (10701,10702,10703):
        directory=out/str(seed);directory.mkdir();obj=Objective(seed,directory);save(directory/'data.json',obj.data);save(directory/'declaration.json',obj.declaration.contract)
        with closing(Store(directory/'study.sqlite')) as store:
            study=Study(Enumeration(obj.space,[{'index':i} for i in range(4)]),LocalExecutor(),obj,maximize=False,budget=4,study_name='rolling_'+str(seed),checkpoint_dir=directory,store=store,declaration=obj.declaration,
              resource_budget=StudyBudget(configurations=4,work_unit='time_rows',tuning_work=1000,final_work=200,max_work_per_call=200))
            result=study.run();save(directory/'result.json',result.to_dict());save(directory/'report.json',study.report())
        tune=[x for x in obj.records if x['role']=='tuning'];final=[x for x in obj.records if x['role']=='final'];assert len(tune)==8 and len(final)==1
        means=[np.mean([x['loss'] for x in tune if x['config']['index']==i]) for i in range(4)];close(min(means),result.best_value)
        row={'seed':seed,'selected':GRID[result.best_config.values['index']],'validation_nll':result.best_value,'final_nll':final[0]['loss'],'fits':9};summaries.append(row);print(canon(row),flush=True)
    future=copy.deepcopy(next(iter(obj.data.values())));future['release_times'][0]=future['time']+1
    controls={'future_feature':reject(lambda:forecast_features([future],1)),
       'gap_violation':reject(lambda:EvaluationFold('bad',('a',),('b',),mode='temporal',train_until=2,score_from=3,score_until=4,gap=1)),
       'entity_overlap':reject(lambda:EvaluationFold('bad',('a',),('b',),mode='grouped',train_groups=('same',),score_groups=('same',))),
       'final_exposure':reject(lambda:StudyDeclaration(objective_id='x',model_id='x',data_id='x',protocol_id='x',objectives=(EvaluationObjective('x','min','x'),),tuning_folds=(EvaluationFold('train',('a',),('b',)),),final_folds=(EvaluationFold('final',('a',),('b',)),)))}
    save(out/'result.json',{'mechanics_passed':True,'scientific_status':'rolling_origin_information_controls_verified','fits':27,'studies':summaries,'controls':controls,'scope':'Synthetic one-step sequential forecast: each observed score updates state for the next score. Gap outcomes masked; preprocessing trained per fold. Grouped refusal tested separately; no real-bank or simultaneous grouped-temporal effectiveness claim.'})
if __name__=='__main__':run(Path(sys.argv[1]))
