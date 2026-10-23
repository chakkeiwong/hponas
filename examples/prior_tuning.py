"""PriorBand on actual quadratic training with an exactly known tuning optimum.

Run: python -m examples.prior_tuning --output-dir /tmp/prior-tuning
Every run retains configurations, physical updates, frozen mixtures and recovery
state. These small diagnostic traces make no V11 performance claim.
"""
import argparse
import json
from pathlib import Path
import tempfile

from hponas import (CategoricalPriorBandSearcher, FinitePriorSearcher, Knob,
                    LocalExecutor, PriorBandScheduler, PriorPendingError,
                    ProductPriorBandSearcher, SearchSpace, Study)
from hponas.events import EventLog
from hponas.store import Store
from validation.multifidelity_reference import value
from workloads.streaming_quadratic import StreamingQuadratic


def run_one(directory, name, default, *, cap=16, continuation='resume', uniform=False,
            product_transform=None):
    directory=directory/name
    directory.mkdir()
    space=SearchSpace([Knob('eta_index','categorical',list(range(1,26)))
                       if product_transform is None else
                       Knob('eta_index','integer',(1,25),transform=product_transform)])
    workload=StreamingQuadratic()
    store=Store(directory/'study.sqlite')
    log=EventLog(directory/'events.jsonl')
    pending=0
    try:
        for attempt in range(400):
            if uniform:
                searcher=FinitePriorSearcher(space,[{'eta_index':i} for i in range(1,26)],
                                              [1]*25,0,seed=0,max_proposals=cap)
            elif product_transform is None:
                searcher=CategoricalPriorBandSearcher(space,{'eta_index':default},
                    rungs=[1,2,4,8],eta=2,seed=0,max_proposals=cap)
            else:
                searcher=ProductPriorBandSearcher(space,{'eta_index':default},
                    rungs=[1,2,4,8],eta=2,seed=0)
            executor=LocalExecutor()
            study=Study(searcher,executor,workload,budget=21,study_name=name,maximize=False,
                scheduler=PriorBandScheduler(rungs=[1,2,4,8],eta=2,default_at_target=True),
                continuation=continuation,store=store,event_log=log, legacy_reason='Exposed deterministic tutorial fixture; no protected performance claim')
            try:
                if attempt:
                    study.load_checkpoint()
                result=study.run()
            except PriorPendingError:
                pending+=1
                with (directory/f'pending-{pending:03d}.json').open('x') as out:
                    json.dump(store.load_study_snapshot(name),out,indent=2)
                continue
            finally:
                executor.shutdown()
            break
        else:
            raise RuntimeError('Bounded diagnostic ended with a pending draw; evidence retained')
        snapshot=study._snapshot()
    finally:
        store.close()
    full=sorted({study.trials[r.trial_id].config['eta_index'] for r in result.history
                 if r.status=='completed' and r.fidelity==8})
    optimum=min(range(1,26),key=lambda i:value(i,8))
    summary={'name':name,'default':None if uniform else default,'uniform':uniform,
             'distribution':'categorical' if product_transform is None else 'integer-'+product_transform,
             'proposal_cap':cap,'continuation':continuation,'pending_recoveries':pending,
             'roots':21,'evaluations':result.n_trials,'physical_updates':len(workload.updates),
             'accounted_cost':result.total_cost,'full_fidelity_indices':full,
             'best_index':min(full,key=lambda i:value(i,8)),'best_value':result.best_value,
             'exact_optimal_index':optimum,'optimum_reached':optimum in full}
    raw={'summary':summary,'updates':workload.updates,'calls':workload.calls,
         'endpoints':[{'trial':study.trials[r.trial_id].to_dict(),'result':r.to_dict()}
                      for r in result.history], 'snapshot':snapshot}
    with (directory/'raw.json').open('x') as out:
        json.dump(raw,out,indent=2,allow_nan=False)
        out.write('\n')
    return summary


def run(directory):
    best=min(range(1,26),key=lambda i:value(i,8))
    worst=max(range(1,26),key=lambda i:value(i,8))
    runs=[run_one(directory,'good',best),run_one(directory,'wrong',worst),
          run_one(directory,'central',13),run_one(directory,'wrong-pending',worst,cap=1),
          run_one(directory,'wrong-restart',worst,continuation='restart'),
          run_one(directory,'uniform',None,uniform=True)]
    with (directory/'summary.json').open('x') as out:
        json.dump({'scope':'categorical finite integration diagnostics','V11_accepted':False,
                   'runs':runs},out,indent=2)
        out.write('\n')
    return runs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('runs'))
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='prior-',dir=args.output_dir))
    runs=run(directory)
    print(json.dumps({'directory':str(directory),'cases':len(runs),
                      'physical_updates':sum(r['physical_updates'] for r in runs),'V11_accepted':False}))


if __name__=='__main__':
    main()
