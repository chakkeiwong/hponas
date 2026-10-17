"""Numerical PriorBand diagnostics on actual finite and continuous quadratic training."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile

from hponas import (Knob, LocalExecutor, PriorBandScheduler, ProductPriorBandSearcher,
                    SearchSpace, Study)
from examples.prior_tuning import run_one
from validation.multifidelity_reference import value
from workloads.tuning_models import quadratic


class ContinuousQuadratic:
    def __init__(self):
        self.updates=[]

    def __call__(self, config, fidelity, trial_id, reporter, resume_from, checkpoint):
        state=checkpoint
        for step in range(int(resume_from)+1,int(fidelity)+1):
            result=quadratic(config['eta'],step,state)
            if result['incremental_steps']!=1:
                raise ValueError('Expected one physical gradient update')
            state=result['checkpoint']
            self.updates.append({'trial_id':trial_id,'eta':config['eta'],'step':step,
                                 'value':result['value'],'checkpoint':deepcopy(state)})
            reporter(step,result['value'],cost=step-resume_from,checkpoint=state)
        return {'value':result['value'],'cost':fidelity-resume_from,'checkpoint':state}


def continuous(directory, transform):
    name='continuous-'+transform
    target=directory/name
    target.mkdir()
    space=SearchSpace([Knob('eta','continuous',(.025,.625),transform=transform)])
    searcher=ProductPriorBandSearcher(space,{'eta':.6},rungs=[1,2,4,8],eta=2,seed=0)
    workload=ContinuousQuadratic()
    executor=LocalExecutor()
    study=Study(searcher,executor,workload,budget=21,maximize=False,study_name=name,
                scheduler=PriorBandScheduler(rungs=[1,2,4,8],eta=2,default_at_target=True),
                continuation='resume',checkpoint_dir=target)
    try:
        result=study.run()
    finally:
        executor.shutdown()
    summary={'name':name,'distribution':name,'default':.6,'physical_updates':len(workload.updates),
             'accounted_cost':result.total_cost,'evaluations':result.n_trials,'best_value':result.best_value}
    with (target/'raw.json').open('x') as out:
        json.dump({'summary':summary,'updates':workload.updates,'snapshot':study._snapshot(),
                   'endpoints':[{'trial':study.trials[r.trial_id].to_dict(),'result':r.to_dict()}
                                for r in result.history]},out,indent=2,allow_nan=False)
        out.write('\n')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('runs'))
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='product-prior-',dir=args.output_dir))
    best=min(range(1,26),key=lambda i:value(i,8))
    worst=max(range(1,26),key=lambda i:value(i,8))
    runs=[]
    for transform in ['none','log']:
        for label,default in [('good',best),('wrong',worst)]:
            runs.append(run_one(directory,'integer-'+transform+'-'+label,default,product_transform=transform))
        runs.append(continuous(directory,transform))
    with (directory/'summary.json').open('x') as out:
        json.dump({'scope':'numerical product conformance diagnostics','V11_accepted':False,'runs':runs},out,indent=2)
        out.write('\n')
    print(json.dumps({'directory':str(directory),'cases':len(runs),'physical_updates':sum(r['physical_updates'] for r in runs),
                      'V11_accepted':False}))


if __name__=='__main__':
    main()
