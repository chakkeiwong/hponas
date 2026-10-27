"""Real method routes on independent analytic objectives; no superiority claims."""
import math
import os
import pytest
from hponas import (ResourceExecutor, ResourceSpec, run_replicas, Study, LocalExecutor,
    RandomSearcher, SobolSearcher, GPSearcher, CMAESSearcher, RobustGPSearcher, SearchSpace, Knob)


def run_case(case,seed,executor,require_cuda=False):
    from hponas.searchers_tpe import TPESearcher
    from hponas.schedulers import ASHAConfig, ASHAScheduler, PASHAConfig, PASHAScheduler
    from hponas import ProductPriorBandSearcher, PriorBandScheduler, DEHBController
    from tests.integration.test_trust_searcher import searcher as trust
    from tests.integration.test_cost_searcher import search as cost
    space=SearchSpace([Knob('x','continuous',(.05,.95))])
    scheduler=None;budget=5
    def objective(config,fidelity=1,execution=None):
        x=float(next(iter(config.values())))
        if require_cuda:
            import torch
            assert execution is not None and execution.device=='cuda:0' and len(execution.gpu_ids)==1
            value=(torch.tensor(x,dtype=torch.float64,device=execution.device)-.375).square()+1/fidelity
            assert value.is_cuda
            return {'value':float(value.cpu()),'cost':fidelity}
        return {'value':(x-.375)**2+1/fidelity,'cost':fidelity}
    if case=='random':searcher=RandomSearcher(space,seed=seed)
    elif case=='sobol':searcher=SobolSearcher(space,seed=seed)
    elif case=='tpe':searcher=TPESearcher(space,seed=seed)
    elif case=='gp':searcher=GPSearcher(space,seed=seed,initial_random_samples=2,num_restarts=1)
    elif case=='cma':searcher=CMAESSearcher(space,seed=seed,maximize=False);budget=8
    elif case=='robust':searcher=RobustGPSearcher(space,seed=seed,initial_random_samples=2,candidate_count=4,posterior_samples=4,fit_iterations=1)
    elif case=='trust':searcher=trust(seed=seed);budget=5
    elif case=='cost':searcher=cost(seed=seed);budget=4
    elif case=='finite-prior':
        from fractions import Fraction
        from hponas import FinitePriorSearcher
        searcher=FinitePriorSearcher(space,[{'x':.25},{'x':.75}],[3,1],Fraction(1,2),seed=seed,max_proposals=1000)
    elif case=='categorical-priorband':
        from hponas import CategoricalPriorBandSearcher
        space=SearchSpace([Knob('x','categorical',[.25,.5,.75])])
        searcher=CategoricalPriorBandSearcher(space,{'x':.5},rungs=[1,2,4],eta=2,seed=seed,max_proposals=1000)
        scheduler=PriorBandScheduler(rungs=[1,2,4],eta=2,default_at_target=True);budget=8
    elif case=='pibo':
        from hponas.searchers_gp import GPqLogEISearcher
        searcher=GPqLogEISearcher(space,seed=seed,prior_fn=lambda c:math.exp(-(c['x']-.4)**2),prior_beta=1.)
        budget=4
    elif case=='warm':
        from hponas.warm_start import WarmStartSearcher
        from hponas.legacy_searchers import SobolSearcher as LegacySobol
        searcher=WarmStartSearcher(LegacySobol(space,seed=seed),[{'x':.25},{'x':.75}])
    elif case in ('asha','pasha'):
        searcher=RandomSearcher(space,seed=seed);budget=6
        scheduler=(ASHAScheduler(ASHAConfig(r_min=1,r_max=4,eta=2)) if case=='asha' else
                   PASHAScheduler(PASHAConfig(r_min=1,r_max=4,eta=2)))
    elif case=='priorband':
        searcher=ProductPriorBandSearcher(space,{'x':.5},rungs=[1,2,4],eta=2,seed=seed)
        scheduler=PriorBandScheduler(rungs=[1,2,4],eta=2,default_at_target=True);budget=8
    elif case=='dehb':
        controller=DEHBController(space,seed=seed,min_fidelity=1,max_fidelity=4,eta=2)
        trace=[]
        for _ in range(12):
            trial=controller.ask()
            result=executor.execute(trial,objective)
            controller.tell(result);trace.append([trial.config.values,result.objective_value,result.fidelity])
        return trace
    else:raise ValueError(case)
    study=Study(searcher,executor,objective,budget=budget,maximize=False,study_name='case-'+case,
                max_concurrent=1,scheduler=scheduler,legacy_reason='Analytic parallel method conformance; protected declarations tested separately')
    result=study.run()
    return [[study.trials[r.trial_id].config.values,r.objective_value,r.fidelity] for r in result.history]


@pytest.fixture(scope='module')
def pool():
    with ResourceExecutor(2,timeout=90) as executor:yield executor


@pytest.mark.parametrize('case',['random','sobol','tpe','gp','cma','robust','trust','cost','asha','pasha','priorband','dehb',
    'finite-prior','categorical-priorband','pibo','warm'])
def test_independent_method_replicas_match_same_seed_serial(case,pool):
    serial=[run_case(case,seed,LocalExecutor()) for seed in (7,11)]
    parallel=run_replicas(pool,lambda seed,ex:run_case(case,seed,ex),(7,11))
    for expected,actual in zip(serial,parallel):
        assert len(expected)==len(actual)
        for a,b in zip(expected,actual):
            assert a[0]==pytest.approx(b[0],abs=1e-9,rel=1e-7)
            assert a[1:]==pytest.approx(b[1:],abs=1e-9,rel=1e-7)


def test_rgpe_declared_parallel_repetitions(pool,tmp_path):
    from contextlib import closing
    from hponas.store import Store
    from tests.integration.test_declared_rgpe import source,target
    from hponas.executors.base import BaseExecutor
    class BorrowedExecutor(BaseExecutor):
        num_workers=2
        def prepare(self):pool.prepare()
        def execute(self,*args,**kwargs):return pool.execute(*args,**kwargs)
        def shutdown(self):pass
    with closing(Store(tmp_path/'history.sqlite')) as store:
        source(store)
        run=target(store,executor=BorrowedExecutor(),evaluation_workers=2,max_concurrent=1)
        result=run.run()
        assert result.best_value==8 and result.evaluation['selection']==['target_trial_0']


def test_ranked_warm_parallel_replicas_preserve_frozen_history(pool,tmp_path):
    from contextlib import closing
    from hponas.store import Store
    from hponas.warm_start import RankedWarmStartSearcher
    from hponas.warm_history import select
    from tests.unit.test_ranked_warm_history import add_history,context
    space=SearchSpace([Knob('x','continuous',(1.,8.))])
    with closing(Store(tmp_path/'warm.sqlite')) as store:
        add_history(store,space,'A',[.1,.2,.3],[1.,2.,3.])
        selection=select(store.read_warm_histories(),context(space),space,2)
    def run(seed,executor):
        search=RankedWarmStartSearcher(RandomSearcher(space,seed=seed),selection)
        result=Study(search,executor,lambda c:(c['x']-3)**2,budget=4,maximize=False,study_name='target',
            legacy_reason='Frozen-history replica regression').run()
        return [[search.trials[r.trial_id].values,r.objective_value] for r in result.history]
    assert run_replicas(pool,run,(7,11))==[run(seed,LocalExecutor()) for seed in (7,11)]


def run_vector_case(method,executor,require_cuda=False):
    from hponas import MultiObjectiveRandomSearcher,MultiObjectiveBayesSearcher,WrappedNSGAIISearcher,MultiObjectiveStudy
    space=SearchSpace([Knob('x','continuous',(0.,1.))])
    objectives=[{'name':name,'direction':'min','lower':0.,'upper':1.} for name in ('a','b')]
    if method=='random':search=MultiObjectiveRandomSearcher(space,objectives=objectives,seed=7)
    elif method in ('qlognehvi','chebyshev'):search=MultiObjectiveBayesSearcher(space,objectives=objectives,seed=7,n_initial=2,method=method,candidate_count=8,mc_samples=8,fit_maxiter=4)
    else:search=WrappedNSGAIISearcher(space,objectives=objectives,seed=7,population_size=2)
    def objective(c,execution):
        if require_cuda:
            import torch
            x=torch.tensor(c['x'],dtype=torch.float64,device=execution.device)
            assert x.is_cuda
            a,b=float(x.square().cpu()),float((1-x).square().cpu())
        else:
            assert execution.device=='cpu';a,b=c['x']**2,(1-c['x'])**2
        return {'objectives':{'a':a,'b':b},'constraints':{},'work':1,'cost':1}
    result=MultiObjectiveStudy(search,executor,objective,objectives=objectives,budget=4,max_concurrent=2,
        legacy_reason='Finite vector parallel conformance').run()
    assert result.n_trials==4 and len(result.front)>0
    return result


@pytest.mark.parametrize('method',['random','qlognehvi','chebyshev','nsgaii'])
def test_vector_methods_on_parallel_cpu(method):
    with ResourceExecutor(2,cpu_ids=sorted(os.sched_getaffinity(0))[-2:],timeout=60) as executor:
        run_vector_case(method,executor)
