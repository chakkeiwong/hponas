"""Bounded APP-02 wallet search; real public Study calls, no cached objectives."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path('/home/ubuntu/workspace/hponas')
sys.path.insert(0,str(ROOT))
from hponas import (Study, StudyDeclaration, EvaluationFold, EvaluationObjective, StudyBudget,
                    SearchSpace, Knob, LocalExecutor, RandomSearcher, SobolSearcher, GPSearcher)
from hponas.searchers_tpe import TPESearcher
from hponas.store import Store
from wallet_model import GRID, fit, generate, observed_rows, empirical_loss, population_metrics

def canonical(x):return json.dumps(x,sort_keys=True,allow_nan=False,separators=(',',':'))
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(obj,f,indent=2,allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()

class WalletObjective:
    def __init__(self,data,seed,out):
        self.data=data;self.seed=seed;self.out=out;self.records=[]
        self.space=SearchSpace([Knob('mean','categorical',['intercept','linear','quadratic']),
                               Knob('scale','categorical',['constant','linear']),
                               Knob('incidence','categorical',['censored','mixture']),
                               Knob('ridge','categorical',[0.,.01])])
        ids={r:tuple(i for i,ok in zip(d['ids'],d['observed']) if ok) for r,d in data.items()}
        self.declaration=StudyDeclaration(objective_id='app02-wallet-nll',model_id='nested-wallet-v1',
             data_id=digest({r:{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in d.items()} for r,d in data.items()}),
             protocol_id=hashlib.sha256((ROOT/'docs/program/evidence/2026-10-25/app-02/wallet-design-01.json').read_bytes()).hexdigest(),
             objectives=(EvaluationObjective('loss','min','negative_log_likelihood'),),
             tuning_folds=(EvaluationFold('validation',ids['train'],ids['validation']),),
             final_folds=(EvaluationFold('final',ids['train']+ids['validation'],ids['final']),),
             tuning_seeds=(0,),final_seeds=(1000,))
    def __call__(self,config,seed,evaluation,trial_id):
        if config not in GRID:raise ValueError('Unknown candidate')
        if evaluation.declaration_identity!=self.declaration.identity:raise ValueError('Declaration mismatch')
        final=evaluation.role=='final';fold=self.declaration.final_folds[0] if final else self.declaration.tuning_folds[0]
        if evaluation.role not in ('tuning','final') or evaluation.fold!=fold or seed!=(1000 if final else 0):raise ValueError('Wrong fold/seed')
        tx,ty=observed_rows(self.data,('train','validation') if final else ('train',))
        sx,sy=observed_rows(self.data,('final',) if final else ('validation',))
        model=fit(config,tx,ty);value=empirical_loss(model,sx,sy)
        record=dict(trial=trial_id,role=evaluation.role,seed=seed,model=model,loss=value,
                    train_ids=list(fold.train_ids),score_ids=list(fold.score_ids))
        path=self.out/'models'/(trial_id+'.json');save(path,record);self.records.append(record)
        return dict(value=value,artifacts={'model':str(path)},metadata={'resource':{'work':model['work'],'unit':'likelihood_row_evaluations'}})

def run(out):
    all_results=[];all_grids=[];fit_count=0
    for seed in (711,812,913):
        base=out/str(seed);data=generate(seed)
        save(base/'data.json',{r:{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in d.items()} for r,d in data.items()})
        tx,ty=observed_rows(data,('train',));vx,vy=observed_rows(data,('validation',));grid=[];begin=time.monotonic()
        for i,cfg in enumerate(GRID):
            model=fit(cfg,tx,ty);fit_count+=1;grid.append(dict(index=i,model=model,validation=empirical_loss(model,vx,vy)))
        grid_time=time.monotonic()-begin;minimum=min(g['validation'] for g in grid)
        save(base/'grid.json',dict(rows=grid,minimum=minimum,seconds=grid_time));all_grids.append((seed,grid,grid_time))
        print(canonical(dict(seed=seed,grid_seconds=grid_time,grid_minimum=minimum)),flush=True)
        for method in ('random','sobol','gp','tpe'):
            directory=base/method;obj=WalletObjective(data,seed,directory)
            searcher={'random':lambda:RandomSearcher(obj.space,seed=seed),
                      'sobol':lambda:SobolSearcher(obj.space,seed=seed,scramble=True),
                      'gp':lambda:GPSearcher(obj.space,seed=seed,initial_random_samples=4,num_restarts=2,maximize=False),
                      'tpe':lambda:TPESearcher(obj.space,seed=seed)}[method]()
            directory.mkdir(parents=True);start=time.monotonic()
            with closing(Store(directory/'study.sqlite')) as store:
                study=Study(searcher,LocalExecutor(),obj,maximize=False,budget=32,study_name=f'wallet2_{seed}_{method}',
                            checkpoint_dir=directory,store=store,declaration=obj.declaration,
                            resource_budget=StudyBudget(configurations=32,work_unit='likelihood_row_evaluations',
                                                        tuning_work=32*20000000,final_work=20000000,max_work_per_call=20000000))
                result=study.run();elapsed=time.monotonic()-start;save(directory/'report.json',study.report())
                save(directory/'result.json',result.to_dict());save(directory/'declaration.json',obj.declaration.contract)
                tune=[r for r in obj.records if r['role']=='tuning'];final=[r for r in obj.records if r['role']=='final']
                assert len(tune)==32 and len(final)==1
                expected=min(r['loss'] for r in tune);assert abs(expected-result.best_value)<1e-10
                assert all(abs(r['loss']-next(g['validation'] for g in grid if g['model']['config']==r['model']['config']))<1e-10 for r in tune)
                chosen=next(r for r in tune if r['model']['config']==result.best_config.values)
                row=dict(seed=seed,method=method,best_config=result.best_config.values,best_validation=result.best_value,
                         finite_minimum=minimum,search_regret=result.best_value-minimum,unique=len({canonical(r['model']['config']) for r in tune}),
                         proposals=32,failed=sum(r.status!='completed' for r in result.history),
                         search_seconds=elapsed,fit_seconds=sum(r['model']['seconds'] for r in obj.records),grid_seconds=grid_time,
                         before=chosen['model'],after=final[0]['model'],final_sample_nll=final[0]['loss'],resources=study.resource_report())
                all_results.append(row);fit_count+=len(obj.records)
                save(directory/'selection.json',row);print(canonical({k:row[k] for k in ('seed','method','search_regret','unique','search_seconds')}),flush=True)
    # Compute population/decision diagnostics only after every search and final fit is frozen.
    grid_diagnostics=[]
    for seed,grid,seconds in all_grids:
        rows=[dict(index=g['index'],config=g['model']['config'],validation=g['validation'],population=population_metrics(g['model'],48)) for g in grid]
        grid_diagnostics.append(dict(seed=seed,seconds=seconds,rows=rows))
    for row in all_results:
        row['population_before']=population_metrics(row['before'],48);row['population_after']=population_metrics(row['after'],48)
        lower=population_metrics(row['after'],24)
        row['quadrature_difference']={k:abs(lower[k]-row['population_after'][k]) for k in lower}
        assert row['quadrature_difference']['expected_nll']<1e-7
    assert fit_count==468
    save(out/'results.json',dict(passed=True,fits=fit_count,studies=all_results,grids=grid_diagnostics,
                                interpretation='Descriptive synthetic comparison; no global optimization, universal superiority or real-data claim.'))
    print(canonical(dict(passed=True,fits=fit_count,studies=len(all_results))),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
