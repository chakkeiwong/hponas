"""Public HPO-NAS declared workflows for the frozen APP-01 design."""
from contextlib import closing
import hashlib
import itertools
import json
import math
import shutil
from pathlib import Path
import time
import numpy as np
import torch
from hponas import (Study,StudyDeclaration,EvaluationFold,EvaluationObjective,EvaluationContext,StudyBudget,SearchSpace,Knob,LocalExecutor,RandomSearcher,SobolSearcher,GPSearcher,MultiObjectiveStudy,MultiObjectiveRandomSearcher)
from hponas.searchers_tpe import TPESearcher
from hponas.store import Store
from hponas import IncompleteStudyError
from models import DESIGN,generate,fit_score

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);content=canonical(value)+chr(10)
    if path.exists():
        if path.is_symlink() or path.read_text()!=content:raise ValueError('Consumed output differs: '+str(path))
    else:
        with path.open('x') as f:f.write(content)
def load_model(path):
    row=json.loads(Path(path).read_text())
    if set(row)!={'payload','sha256'} or digest(row['payload'])!=row['sha256']:raise ValueError('Model hash differs')
    return row['payload']

class Objective:
    def __init__(self,name,replicate,directory,vector=False):
        self.name=name;self.replicate=replicate;self.directory=Path(directory);self.vector=vector;self.calls=[]
        self.records,self.ids=generate(name,replicate);self.grid=DESIGN['grids'][name];self.axes=list(self.grid)
        self.space=SearchSpace([Knob(a,'ordinal',(0,len(self.grid[a])-1)) for a in self.axes])
        objectives=(EvaluationObjective('loss','min','nats_or_negative_value_or_squared_error'),)
        if vector:objectives=(EvaluationObjective('error','min','squared_value'),EvaluationObjective('size','min','parameters'))
        self.declaration=StudyDeclaration(objective_id='app01:'+name+(':vector' if vector else ':scalar'),model_id='app01-fit-v1:'+name,data_id=digest(self.records),protocol_id=digest(DESIGN),objectives=objectives,
            tuning_folds=(EvaluationFold('validation',tuple(self.ids['train']),tuple(self.ids['validation'])),),
            final_folds=(EvaluationFold('final',tuple(self.ids['train']+self.ids['validation']),tuple(self.ids['final'])),),
            tuning_seeds=tuple(DESIGN['tuning_seeds']),final_seeds=tuple(DESIGN['final_seeds']))
    @property
    def configurations(self):return [dict(zip(self.axes,v)) for v in itertools.product(*(range(len(self.grid[a])) for a in self.axes))]
    def physical(self,config):
        if set(config)!=set(self.axes) or any(type(config[a]) is not int or not 0<=config[a]<len(self.grid[a]) for a in self.axes):raise ValueError('Invalid finite configuration')
        return {a:self.grid[a][config[a]] for a in self.axes}
    def __call__(self,config,seed,evaluation,trial_id):
        self.calls.append(trial_id)
        if evaluation.declaration_identity!=self.declaration.identity:raise ValueError('Different declaration')
        folds=self.declaration.tuning_folds if evaluation.role=='tuning' else self.declaration.final_folds if evaluation.role=='final' else ()
        seeds=DESIGN['tuning_seeds'] if evaluation.role=='tuning' else DESIGN['final_seeds']
        if evaluation.fold not in folds or seed not in seeds:raise ValueError('Invalid role or seed')
        train=[self.records[k] for k in evaluation.fold.train_ids];score=[self.records[k] for k in evaluation.fold.score_ids]
        cfg=self.physical(config);model,loss,metrics,work=fit_score(self.name,cfg,train,score,self.replicate*10000+seed)
        payload={'name':self.name,'replicate':self.replicate,'config':config,'physical':cfg,'seed':seed,'role':evaluation.role,'train_ids':list(evaluation.fold.train_ids),'score_ids':list(evaluation.fold.score_ids),'model':model,'loss':loss,'metrics':metrics,'work':work,'declaration_identity':self.declaration.identity}
        path=self.directory/'models'/(trial_id+'.json');save(path,{'payload':payload,'sha256':digest(payload)})
        if self.vector:return {'objectives':{'error':metrics['losses'][0],'size':model['parameters']},'constraints':{'dx':metrics['dx_max'],'da':metrics['da_max']},'work':work,'artifacts':{'model':str(path)}}
        return {'value':loss,'artifacts':{'model':str(path)},'metadata':{'resource':{'work':work,'unit':'declared_fit_work_proxy'}}}

def method_searcher(method,space,replicate):
    if method=='random':return RandomSearcher(space,seed=replicate)
    if method=='sobol':return SobolSearcher(space,seed=replicate,scramble=True)
    if method=='gp':return GPSearcher(space,seed=replicate,initial_random_samples=4,num_restarts=2,maximize=False)
    if method=='tpe':return TPESearcher(space,seed=replicate)
    raise ValueError(method)

def make_study(name,replicate,method,directory,store,vector=False,budget=None):
    obj=Objective(name,replicate,directory,vector);budget=budget or DESIGN['budget'];max_work=10000000
    options=dict(budget=budget,study_name=name+'_'+method+'_'+str(replicate)+('_vector' if vector else ''),checkpoint_dir=directory,store=store,declaration=obj.declaration,architecture_coordinates=('width','depth','activation') if name in ('nas','transport') else (),
        resource_budget=StudyBudget(configurations=budget,work_unit='declared_fit_work_proxy',tuning_work=(budget*2+2)*max_work,final_work=budget*2*max_work,max_work_per_call=max_work))
    if vector:
        contract={'objectives':[{'name':'error','direction':'min','lower':0.,'upper':4.},{'name':'size','direction':'min','lower':0.,'upper':200.}],
                  'constraints':{'dx':.25*.6**2*math.exp(.3),'da':.25*.5**2*math.exp(.3)},'work_unit':'declared_fit_work_proxy'}
        study=MultiObjectiveStudy(MultiObjectiveRandomSearcher(obj.space,seed=replicate,**contract),LocalExecutor(),obj,**contract,**options)
    else:study=Study(method_searcher(method,obj.space,replicate),LocalExecutor(),obj,maximize=False,**options)
    return study,obj

def scientific_projection(study):
    return [(r.trial_id,study.trials[r.trial_id].config.values,r.fidelity,r.objective_value,r.status) for r in study.get_history()]

def completed_resume(study,obj,name,replicate,method,directory,store,vector=False,budget=None):
    before=canonical(store.read_report(study.study_name));new,new_obj=make_study(name,replicate,method,directory,store,vector,budget);new.load_checkpoint();run_result(new,vector)
    if new_obj.calls or canonical(store.read_report(study.study_name))!=before:raise AssertionError('Completed resume changed result')
    return True

def run_result(study,allow_infeasible=False):
    try:return study.run()
    except IncompleteStudyError as exc:
        if not allow_infeasible or exc.result.reason!='no_feasible_full_fidelity_result':raise
        if len(exc.result.history)!=DESIGN['budget'] or any(r.status!='completed' for r in exc.result.history):raise
        return exc.result

def recovery(name,replicate,base,reference):
    directory=base/'recovery';directory.mkdir()
    with closing(Store(directory/'study.sqlite')) as store:
        study,obj=make_study(name,replicate,'random',directory,store);calls=[]
        def interrupt(config,seed,evaluation,trial_id):
            calls.append(trial_id)
            if len(calls)==3:raise KeyboardInterrupt('APP-01 deliberate pre-evaluation interruption')
            return obj(config,seed,evaluation,trial_id)
        study.objective_fn=interrupt
        try:study.run()
        except KeyboardInterrupt:pass
        else:raise AssertionError('Interruption absent')
        snapshot=store.load_study_snapshot(study.study_name);committed=[r['result']['trial_id'] for group in snapshot['evaluation']['tuning'].values() for r in group]
        resumed,resumed_obj=make_study(name,replicate,'random',directory,store);resumed.load_checkpoint();result=resumed.run()
        if set(committed)&set(resumed_obj.calls):raise AssertionError('Committed fit repeated')
        if scientific_projection(resumed)!=reference:raise AssertionError('Recovered search differs')
        save(directory/'report.json',resumed.report());save(directory/'result.json',result.to_dict());save(directory/'interruption.json',{'committed':committed,'calls_before':calls,'calls_after':resumed_obj.calls,'projection_matches':True,'resources':resumed.resource_report()})
    return {'projection_matches':True,'committed_calls_not_repeated':len(committed)}

def run_family(name,destination):
    root=Path(destination);root.mkdir(parents=True,exist_ok=False);out=[];started=time.perf_counter()
    recovery_manifest=Path(__file__).with_name('recovery.json')
    if recovery_manifest.exists() and name in json.loads(recovery_manifest.read_text()):
        source=json.loads(recovery_manifest.read_text())[name];receipt=Path(source['receipt'])
        if hashlib.sha256(receipt.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Recovery predecessor changed')
        prior=json.loads(receipt.read_text())
        if prior['passed']:raise ValueError('Cannot repeat passing family')
        shutil.copytree(receipt.parent/'results',root,dirs_exist_ok=True);save(root/('inherited-'+receipt.parent.name+'.json'),source)
    save(root/'design.json',DESIGN)
    for rep in DESIGN['replicates']:
        base=root/str(rep);obj=Objective(name,rep,base/'grid');save(base/'data.json',obj.records);save(base/'declaration.json',obj.declaration.contract);grid=[];begin=time.perf_counter()
        if (base/'grid.json').exists():
            retained=json.loads((base/'grid.json').read_text());grid=retained['rows'];minimum=retained['minimum'];grid_seconds=retained['seconds']
        else:
            for i,config in enumerate(obj.configurations):
                values=[];artifacts=[]
                for seed in DESIGN['tuning_seeds']:
                    result=obj(config,seed,EvaluationContext('tuning',obj.declaration.tuning_folds[0],obj.declaration.identity),f'grid_{i}_{seed}');values.append(result['value']);artifacts.append(result['artifacts']['model'])
                grid.append({'config':config,'losses':values,'mean':float(np.mean(values)),'artifacts':artifacts})
            minimum=min(x['mean'] for x in grid);grid_seconds=time.perf_counter()-begin;save(base/'grid.json',{'rows':grid,'minimum':minimum,'seconds':grid_seconds})
        for method in DESIGN['methods']:
            directory=base/method
            if (directory/'summary.json').exists():
                out.append(json.loads((directory/'summary.json').read_text()));print(canonical({'inherited_completed':str(directory)}),flush=True);continue
            directory.mkdir()
            with closing(Store(directory/'study.sqlite')) as store:
                study,fn=make_study(name,rep,method,directory,store);begin=time.perf_counter();result=study.run();seconds=time.perf_counter()-begin
                save(directory/'report.json',study.report());save(directory/'result.json',result.to_dict());completed_resume(study,fn,name,rep,method,directory,store)
                raw=[load_model(p) for p in sorted((directory/'models').glob('*.json'))];final=[r for r in raw if r['role']=='final'];tuning=[r for r in raw if r['role']=='tuning']
                if len(tuning)!=DESIGN['budget']*2 or len(final)!=2:raise AssertionError('Incomplete repetition ledger')
                summary={'name':name,'replicate':rep,'method':method,'best_config':result.best_config.values,'physical':fn.physical(result.best_config.values),'best_tuning':result.best_value,'reference_minimum':minimum,'tuning_regret':result.best_value-minimum,'final_mean':float(np.mean([r['loss'] for r in final])),'final_metrics':[r['metrics'] for r in final],'proposals':result.n_trials,'unique':len({canonical(study.trials[r.trial_id].config.values) for r in result.history}),'failed':sum(r.status!='completed' for r in result.history),'seconds':seconds,'grid_seconds':grid_seconds,'resources':study.resource_report(),'completed_resume':True}
                if rep==DESIGN['replicates'][0] and method=='random':summary['interrupted_resume']=recovery(name,rep,base,scientific_projection(study))
                save(directory/'summary.json',summary);out.append(summary);print(canonical({k:summary[k] for k in ('name','replicate','method','tuning_regret','final_mean','seconds')}),flush=True)
        if name=='nas':
            directory=base/'vector';directory.mkdir(exist_ok=True)
            if (directory/'result.json').exists():continue
            with closing(Store(directory/'study.sqlite')) as store:
                study,fn=make_study(name,rep,'random',directory,store,vector=True)
                if list(directory.glob('*checkpoint.json')):study.load_checkpoint()
                result=run_result(study,True);save(directory/'report.json',study.report());save(directory/'result.json',result.to_dict());completed_resume(study,fn,name,rep,'random',directory,store,True)
    extra={}
    if name=='nas':
        from streaming import execute_streaming
        extra['streaming']=execute_streaming(root/'streaming')
    if name=='transport':
        from transport import verify_selected_transports
        extra['sampling']=verify_selected_transports(root)
    summary={'name':name,'rows':out,'extra':extra,'elapsed_seconds':time.perf_counter()-started,'claim':'Finite descriptive application validation; no universal superiority or production claim'};save(root/'summary.json',summary);return summary
