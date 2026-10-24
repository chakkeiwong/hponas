"""Live trained neural promotion and interrupted momentum-state restoration."""
from contextlib import closing
from pathlib import Path
import numpy as np
import torch
from hponas import Study,StudyDeclaration,EvaluationFold,EvaluationObjective,SearchSpace,Knob,RandomSearcher,LocalExecutor,StudyBudget
from hponas.schedulers import ASHAConfig,ASHAScheduler
from hponas.store import Store
from models import generate,Network,save_net,restore_net,nas_loss
from studies import save,canonical,scientific_projection

class Stream:
    def __init__(self):
        self.records,self.ids=generate('nas',401);self.calls=[]
        self.declaration=StudyDeclaration(objective_id='app01-nas-stream',model_id='momentum-mlp',data_id='app01-nas-401',protocol_id='app01-rungs-40-120',objectives=(EvaluationObjective('loss','min','squared_error'),),
            tuning_folds=(EvaluationFold('validation',tuple(self.ids['train']),tuple(self.ids['validation'])),),final_folds=(EvaluationFold('final',tuple(self.ids['train']+self.ids['validation']),tuple(self.ids['final'])),),tuning_seeds=(0,1),final_seeds=(1000,1001),streaming_steps=(40.,120.))
    def __call__(self,config,fidelity,seed,evaluation,reporter,checkpoint=None,resume_from=0.):
        identity=[seed,evaluation.fold.name,evaluation.role,config];self.calls.append({'identity':identity,'from':resume_from,'to':fidelity})
        cfg={'width':config['width'],'depth':1,'activation':'tanh','learning_rate':config['learning_rate']}
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(4010000+seed);net=Network(cfg,2)
            velocity=[torch.zeros_like(p) for p in net.parameters()]
            if resume_from:
                if checkpoint['identity']!=identity or checkpoint['epoch']!=resume_from:raise ValueError('Different checkpoint role')
                net=restore_net(cfg,checkpoint['layers'],2);velocity=[torch.tensor(v,dtype=torch.float64) for v in checkpoint['momentum']]
            train=torch.tensor([self.records[k]['x'] for k in evaluation.fold.train_ids],dtype=torch.float64,requires_grad=True);score=torch.tensor([self.records[k]['x'] for k in evaluation.fold.score_ids],dtype=torch.float64,requires_grad=True)
            for epoch in range(int(resume_from)+1,int(fidelity)+1):
                net.zero_grad();nas_loss(net,train)[0].sum().backward()
                with torch.no_grad():
                    for p,v in zip(net.parameters(),velocity):v.mul_(.9).add_(p.grad);p.add_(v,alpha=-cfg['learning_rate'])
                if epoch in (40,120):
                    value=float(nas_loss(net,score)[0].sum().detach());state={'layers':save_net(net),'momentum':[v.tolist() for v in velocity],'epoch':epoch,'identity':identity};work=epoch-int(resume_from)
                    reporter(epoch,value,cost=work,checkpoint=state,metadata={'resource':{'work':work,'unit':'gradient_updates'}})
            return {'value':value,'cost':work,'checkpoint':state,'metadata':{'resource':{'work':work,'unit':'gradient_updates'}}}

def build(directory,store,fn=None):
    objective=Stream();space=SearchSpace([Knob('width','categorical',[2,4,8]),Knob('learning_rate','categorical',[.01,.03])])
    study=Study(RandomSearcher(space,seed=71),LocalExecutor(),fn or objective,budget=4,maximize=False,study_name='app01-stream',checkpoint_dir=directory,store=store,declaration=objective.declaration,continuation='resume',architecture_coordinates=('width',),
        scheduler=ASHAScheduler(ASHAConfig(r_min=40,r_max=120,eta=3,promotion_policy='legacy_bootstrap')),resource_budget=StudyBudget(4,'gradient_updates',2500,480,120))
    return study,objective

def execute_streaming(directory):
    directory=Path(directory);directory.mkdir(exist_ok=True);baseline=directory/'uninterrupted';recovery=directory/'recovered';baseline.mkdir(exist_ok=True);recovery.mkdir(exist_ok=True)
    with closing(Store(baseline/'study.sqlite')) as store:
        full,obj=build(baseline,store);expected=full.run();projection=scientific_projection(full);save(baseline/'report.json',full.report());save(baseline/'result.json',expected.to_dict());save(baseline/'calls.json',obj.calls)
    with closing(Store(recovery/'study.sqlite')) as store:
        fn=Stream();calls=[]
        def crash(config,fidelity,seed,evaluation,reporter,checkpoint=None,resume_from=0.):
            calls.append([seed,evaluation.role,fidelity,resume_from])
            if len(calls)==3:raise KeyboardInterrupt('Before third streamed repetition')
            return fn(config,fidelity,seed,evaluation,reporter,checkpoint,resume_from)
        first,_=build(recovery,store,crash)
        try:first.run()
        except KeyboardInterrupt:pass
        else:raise AssertionError('Missing deliberate interruption')
        restored,obj=build(recovery,store);restored.load_checkpoint();actual=restored.run();save(recovery/'report.json',restored.report());save(recovery/'result.json',actual.to_dict());save(recovery/'calls.json',obj.calls)
        if scientific_projection(restored)!=projection:raise AssertionError('Streaming recovery differs')
        if actual.evaluation['selection']!=expected.evaluation['selection']:raise AssertionError('Streaming selection changed')
        if not any(c['from']==40 for c in obj.calls):raise AssertionError('No promoted checkpoint continuation')
        complete,_=build(recovery,store);complete.load_checkpoint();again=complete.run()
        if again.evaluation!=actual.evaluation:raise AssertionError('Streaming completed resume differs')
        result={'passed':True,'projection_matches':True,'momentum_checkpoint_promoted':True,'complete_resume':True,'pre_interruption_calls':calls,'resources':restored.resource_report(),'scope':'SGD streaming is a separate recovery exercise; not pooled with Adam endpoint comparisons'}
        save(directory/'summary.json',result);return result
