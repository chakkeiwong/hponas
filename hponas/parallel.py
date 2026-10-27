"""Independent study replicas for methods whose proposal updates are sequential."""
from copy import deepcopy
from hponas.executors.base import BaseExecutor, evaluate_trial


class AssignedExecutor(BaseExecutor):
    """Execute serially inside an already assigned worker, without nested pools."""
    def __init__(self, execution):self.execution=execution
    def execute(self, trial, objective_fn, *, on_report=None):
        from dataclasses import replace
        context=replace(self.execution,task_id=trial.trial_id)
        result=evaluate_trial(trial,objective_fn,on_report,execution_context=context)
        result.metadata.setdefault('execution',{})['worker']=context.to_dict()
        return result
    def shutdown(self):pass


def run_replicas(executor, factory, seeds):
    """Run factory(seed, assigned_executor) independently in persistent workers.

    The factory returns its own study/controller result and owns an independent
    checkpoint path per seed. Results remain separate: this function does not
    select a winner using protected final evaluations or imply batch BO.
    """
    seeds=tuple(seeds)
    if not seeds or any(type(s) is not int or not 0<=s<2**32 for s in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('Distinct unsigned 32-bit replica seeds required')
    def run(seed,execution):
        return factory(seed,AssignedExecutor(execution))
    return executor.map(run,seeds)
