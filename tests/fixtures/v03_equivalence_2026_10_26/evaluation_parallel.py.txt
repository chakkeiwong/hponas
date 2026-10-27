"""Coordinator-owned parallel endpoint batches with a durable inflight ledger."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import math
import time

from hponas.evaluation import EvaluationController, EvaluationContext, _RoleObjective
from hponas.types import Config, Trial, Result


class ParallelEvaluationController(EvaluationController):
    def __init__(self, *args, workers, **kwargs):
        super().__init__(*args, **kwargs)
        self.workers = workers
        self.state['version'] = 2
        self.state['inflight'] = []

    def run_group(self, study, trial, role):
        self.run_groups(study, [trial], role)
        if role == 'tuning':
            return self.aggregate(trial, self.state[role][trial.trial_id],
                                  cancelled=trial.root_trial_id in study._cancel_requested)

    def run_groups(self, study, trials, role):
        # Any previously dispatched but uncommitted tasks remain charged/lost.
        for old in self.state['inflight']:
            if old['trial_id'] not in self.state['uncertain']:
                self.state['uncertain'].append(old['trial_id'])
        if study._resources is not None:
            study._resources.abandon_inflight()
        self.state['inflight'] = []
        tasks=[]
        for trial in trials:
            rows=self.state[role].setdefault(trial.trial_id, [])
            tasks.extend((trial,i,fold,seed,tid) for i,(fold,seed,tid) in enumerate(self.tasks(trial,role)) if i>=len(rows))
        if hasattr(study.executor,'prepare'):
            study.executor.prepare()
        for start in range(0,len(tasks),self.workers):
            batch=tasks[start:start+self.workers];dispatch=[];results={}
            for trial,i,fold,seed,tid in batch:
                resources=study._resources
                refusal=resources.refusal(role) if resources else None
                cancelled=role=='tuning' and trial.root_trial_id in study._cancel_requested
                if role=='tuning':
                    refusal=('cancel_requested' if cancelled else study._stop_reason or refusal or
                             ('compute_budget_exhausted' if study._cap_reached() else None))
                if refusal:
                    if role=='tuning' and not cancelled:study._stop_reason=study._stop_reason or refusal
                    results[tid]=Result(tid,math.nan,0.,trial.fidelity,{'stop_reason':refusal,
                        'execution':{'elapsed_seconds':0.,'accounting':'not_dispatched'}},'cancelled')
                    continue
                checkpoint=None
                if role=='tuning' and trial.resume_from>0:
                    previous=self.state['tuning'].get(trial.parent_trial_id,[])
                    if i>=len(previous) or previous[i]['result']['metadata'].get('checkpoint') is None:
                        raise ValueError('Promotion requires every repetition checkpoint')
                    checkpoint=previous[i]['result']['metadata']['checkpoint']
                child=Trial(Config(deepcopy(trial.config.values)),tid,seed=seed,fidelity=trial.fidelity,
                    root_trial_id=tid,continuation=trial.continuation if role=='tuning' else 'restart',
                    resume_from=trial.resume_from if role=='tuning' else 0.,checkpoint=checkpoint)
                fn=_RoleObjective(study.objective_fn,EvaluationContext(role,fold,self.declaration.identity,
                    resources.budget.max_work_per_call if resources else None,resources.budget.work_unit if resources else None))
                if resources:resources.begin(tid,role)
                self.state['inflight'].append({'role':role,'parent':trial.trial_id,'index':i,'trial_id':tid})
                dispatch.append((child,fn))
            study.save_checkpoint()  # all reservations precede all execution

            def execute(row):
                child,fn=row;began=time.monotonic()
                result=(study.executor.execute_async(child,fn).result() if getattr(study.executor,'mode',None)=='async'
                        else study.executor.execute(child,fn))
                execution=result.metadata.setdefault('execution',{})
                execution.setdefault('elapsed_seconds',time.monotonic()-began)
                execution.setdefault('accounting','lower_bound_after_interruption')
                return result

            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                # Results are collected in dispatch order; workers cannot mutate the ledger.
                for result in pool.map(execute,dispatch):results[result.trial_id]=result
            for trial,i,fold,seed,tid in batch:
                result=results[tid]
                self.validate_record(result,tid,trial.fidelity)
                dispatched=result.metadata['execution']['accounting']!='not_dispatched'
                if dispatched:
                    if result.metadata['execution']['accounting']=='lower_bound_after_interruption' and tid not in self.state['uncertain']:
                        self.state['uncertain'].append(tid)
                    if tid in self.state['uncertain']:result.metadata['execution']['accounting']='lower_bound_after_interruption'
                    if study._resources:study._resources.complete(result,self.spec)
                self.state[role][trial.trial_id].append({'fold':fold.name,'seed':seed,'result':deepcopy(result.to_dict())})
                self.state['inflight']=[x for x in self.state['inflight'] if x['trial_id']!=tid]
                study.save_checkpoint()

    def finish(self, study):
        # The parent freezes selection and invokes run_group for selected rows;
        # each selected candidate's final folds/seeds share the same bounded pool.
        return super().finish(study)
