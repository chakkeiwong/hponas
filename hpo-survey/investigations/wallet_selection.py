"""Fresh bounded holdout/CV comparison; finite enumeration through public Study."""
from contextlib import closing
import copy
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path('/home/ubuntu/workspace/hponas');sys.path.insert(0,str(ROOT))
from hponas import Study, StudyDeclaration, EvaluationFold, EvaluationObjective, StudyBudget, LocalExecutor
from hponas.types import Config
from hponas.searchers.base import BaseSearcher, SearchSpaceExhaustedError
from hponas.capabilities import SearcherCapabilities, MIXED
from hponas.store import Store
from wallet_model import GRID, generate, fit, empirical_loss, population_metrics
from wallet_preflight import scalar_nll
from wallet_study import WalletObjective, save, digest, canonical

class FiniteEnumeration(BaseSearcher):
    """Local benchmark adapter; exact declared order, checkpointable cursor."""
    support=SearcherCapabilities(MIXED)
    def __init__(self,space):super().__init__(space,0);self.cursor=0
    def suggest(self):
        if self.cursor==len(GRID):raise SearchSpaceExhaustedError('Declared wallet domain consumed')
        cfg=Config(values=dict(GRID[self.cursor]));self.cursor+=1;return cfg
    def get_state(self):return {**super().get_state(),'cursor':self.cursor,'grid_digest':digest(GRID)}
    def set_state(self,state):
        if state['grid_digest']!=digest(GRID) or type(state['cursor']) is not int or not 0<=state['cursor']<=len(GRID):raise ValueError('Invalid finite cursor')
        super().set_state(state);self.cursor=state['cursor']

class CrossValidationObjective:
    def __init__(self,data,seed,out,mode):
        proto=WalletObjective(data,seed,out);self.space=proto.space;self.out=out;self.records=[];self.mode=mode
        self.rows={}
        for r,d in data.items():
            for ident,x,w,ok in zip(d['ids'],d['x'],d['wallet'],d['observed']):
                if ok:self.rows[ident]=(x,float(w))
        train=list(proto.declaration.tuning_folds[0].train_ids);validation=list(proto.declaration.tuning_folds[0].score_ids);development=train+validation
        if mode=='holdout':folds=proto.declaration.tuning_folds
        else:
            permutation=np.random.default_rng(seed+100000).permutation(len(development))
            parts=[tuple(development[i] for i in indices) for indices in np.array_split(permutation,3)]
            folds=tuple(EvaluationFold('cv'+str(k),tuple(i for i in development if i not in set(parts[k])),parts[k]) for k in range(3))
        self.declaration=StudyDeclaration(objective_id='app02-wallet-selection-'+mode,model_id='nested-wallet-v1',
                 data_id=proto.declaration.data_id,protocol_id='wallet-selection-prospective-v1',
                 objectives=(EvaluationObjective('loss','min','negative_log_likelihood'),),tuning_folds=folds,
                 final_folds=proto.declaration.final_folds,tuning_seeds=(0,),final_seeds=(1000,))
    def __call__(self,config,seed,evaluation,trial_id):
        folds=self.declaration.tuning_folds if evaluation.role=='tuning' else self.declaration.final_folds if evaluation.role=='final' else ()
        if config not in GRID or evaluation.fold not in folds or evaluation.declaration_identity!=self.declaration.identity:raise ValueError('Fold/config mismatch')
        if seed!=(0 if evaluation.role=='tuning' else 1000):raise ValueError('Seed mismatch')
        fold=evaluation.fold;train=[self.rows[i] for i in fold.train_ids];score=[self.rows[i] for i in fold.score_ids]
        x=np.array([r[0] for r in train]);y=np.array([r[1] for r in train]);sx=np.array([r[0] for r in score]);sy=np.array([r[1] for r in score])
        model=fit(config,x,y);loss=empirical_loss(model,sx,sy)
        # Independent scalar score reconstructed for every fit.
        assert abs(loss-scalar_nll(np.array(model['theta']),sx,sy,config))<1e-10
        rec=dict(trial=trial_id,role=evaluation.role,fold=fold.name,train_ids=list(fold.train_ids),score_ids=list(fold.score_ids),model=model,loss=loss)
        path=self.out/'models'/(trial_id+'.json');save(path,rec);self.records.append(rec)
        return dict(value=loss,artifacts={'model':str(path)},metadata={'resource':{'work':model['work'],'unit':'likelihood_row_evaluations'}})

def controls(space):
    a=FiniteEnumeration(space);seen=[a.suggest().values for _ in range(7)];state=a.get_state();b=FiniteEnumeration(space);b.set_state(state)
    expected=[a.suggest().values for _ in range(17)];actual=[b.suggest().values for _ in range(17)];assert expected==actual and seen+actual==list(GRID)
    try:b.suggest()
    except SearchSpaceExhaustedError:pass
    else:raise AssertionError('Finite domain overrun')
    bad=copy.deepcopy(state);bad['grid_digest']='bad'
    try:b.set_state(bad)
    except ValueError:pass
    else:raise AssertionError('Changed finite domain accepted')
    return ['exact24 unique candidates','cursor resume equality','exhaustion refusal','changed-grid refusal']

def run(out):
    result=[];total=0;control_results=None
    for seed in (1721,1822,1923):
        data=generate(seed);base=out/str(seed);save(base/'data.json',{r:{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in d.items()} for r,d in data.items()})
        for mode in ('holdout','cv3'):
            directory=base/mode;directory.mkdir();obj=CrossValidationObjective(data,seed,directory,mode)
            if control_results is None:control_results=controls(obj.space)
            searcher=FiniteEnumeration(obj.space);start=time.monotonic()
            with closing(Store(directory/'study.sqlite')) as store:
                study=Study(searcher,LocalExecutor(),obj,maximize=False,budget=24,study_name=f'wallet_selection_{seed}_{mode}',checkpoint_dir=directory,store=store,declaration=obj.declaration,
                            resource_budget=StudyBudget(configurations=24,work_unit='likelihood_row_evaluations',tuning_work=72*20000000,final_work=20000000,max_work_per_call=20000000))
                selected=study.run();elapsed=time.monotonic()-start;report=study.report();save(directory/'report.json',report);save(directory/'result.json',selected.to_dict());save(directory/'declaration.json',obj.declaration.contract)
                nfolds=3 if mode=='cv3' else 1;tuning=[r for r in obj.records if r['role']=='tuning'];final=[r for r in obj.records if r['role']=='final']
                assert len(tuning)==24*nfolds and len(final)==1
                means={canonical(cfg):float(np.mean([r['loss'] for r in tuning if r['model']['config']==cfg])) for cfg in GRID}
                assert abs(min(means.values())-selected.best_value)<1e-10
                assert abs(means[canonical(selected.best_config.values)]-selected.best_value)<1e-10
                final_model=final[0]['model'];assert final_model['config']==selected.best_config.values
                row=dict(seed=seed,mode=mode,best_config=selected.best_config.values,selection_score=selected.best_value,
                         final_model=final_model,final_sample_nll=final[0]['loss'],seconds=elapsed,models=len(obj.records),unique=24,
                         fold_candidate_scores=means,fit_seconds=sum(r['model']['seconds'] for r in obj.records))
                result.append(row);total+=len(obj.records);save(directory/'selection.json',row)
                print(canonical({k:row[k] for k in ('seed','mode','best_config','seconds','models')}),flush=True)
    assert total==294
    for row in result:
        row['population']=population_metrics(row['final_model'],96);low=population_metrics(row['final_model'],48)
        row['resolution_change']={k:abs(low[k]-row['population'][k]) for k in low};assert row['resolution_change']['expected_nll']<1e-7
    contrasts=[]
    for seed in (1721,1822,1923):
        a=next(r for r in result if r['seed']==seed and r['mode']=='holdout');b=next(r for r in result if r['seed']==seed and r['mode']=='cv3')
        contrasts.append(dict(seed=seed,cv_minus_holdout={k:b['population'][k]-a['population'][k] for k in a['population']}))
    save(out/'selection-results.json',dict(passed=True,fits=total,controls=control_results,studies=result,contrasts=contrasts,
       limits=['Fresh exploratory comparison, not powered superiority confirmation.','CV uses different fold training samples and more fitting; no pure variance-only causal claim.','All comparisons retain adverse results; no replacement of prior evidence.']))
    print(canonical(dict(passed=True,fits=total,contrasts=contrasts)),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
