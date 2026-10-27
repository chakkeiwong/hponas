from copy import deepcopy
import pytest
from hponas import ResourceExecutor
from hponas.bg_pbt import LocalBGPBT
from hponas.population import PopulationCheckpoint
from hponas.population_search import LocalPBT
from hponas.pb2_mix import PB2MixExplorer
from hponas.population_parallel import train_batch, run_batch
from tests.unit.test_bg_population import task, config, members


@pytest.mark.parametrize('method',['pbt','pb2','bg'])
def test_population_parallel_matches_serial_and_resumes(tmp_path,method):
    initial=members()
    with ResourceExecutor(2,timeout=40) as executor:
        if method=='bg':
            pool=[config(w,d) for w,d in [(1,1),(2,1),(3,1),(2,2)]]
            kwargs=dict(increment_bound=1,generations=2,max_rounds=1,patience=1,updates_per_round=1,
                distillation_rungs=(1,2),seed=7,max_updates=10,fit_iterations=1)
            serial=LocalBGPBT(tmp_path/'serial',task(),initial,pool,**kwargs).run()
            engine=LocalBGPBT(tmp_path/'parallel',task(),initial,pool,executor=executor,**kwargs)
            parallel=engine.run()
            assert parallel==serial
            assert engine.run()==parallel
        else:
            def run(path,ex):
                population=PopulationCheckpoint(path/'population.json',task(),initial,max_updates=8)
                explorer=PB2MixExplorer(increment_bound=1,fit_iterations=1,horizon=2) if method=='pb2' else None
                engine=LocalPBT(path/'controller.json',population,explorer=explorer,executor=ex)
                result=engine.run(2,updates_per_round=2)
                assert engine.run(2,updates_per_round=2)==result
                return result,population.snapshot(),population.accounting()
            assert run(tmp_path/'serial',None)==run(tmp_path/'parallel',executor)


@pytest.mark.parametrize('boundary',['computed','population','ack'])
def test_parallel_commit_recovery_is_idempotent(tmp_path,monkeypatch,boundary):
    from hponas import population_parallel as module
    class Crash(BaseException):pass
    population=PopulationCheckpoint(tmp_path/'population.json',task(),members(),max_updates=4)
    with ResourceExecutor(2,timeout=40) as executor:
        original=module.write_journal
        write_population=population._write
        def journal(path,value):
            original(path,value)
            if value['status']==('computed' if boundary=='computed' else 'committed') and boundary!='population':
                raise Crash()
        def pop_write(state):
            write_population(state)
            if boundary=='population':raise Crash()
        monkeypatch.setattr(module,'write_journal',journal)
        monkeypatch.setattr(population,'_write',pop_write)
        with pytest.raises(Crash):train_batch(population,'round:',2,executor)
        monkeypatch.setattr(module,'write_journal',original)
        monkeypatch.setattr(population,'_write',write_population)
        result=train_batch(population,'round:',2,executor)
        assert all(r['status']=='committed' for r in result)
        assert population.accounting()['upper']==4
        assert train_batch(population,'round:',2,executor)==result


def test_unknown_worker_work_remains_reserved(tmp_path):
    class FailedExecutor:
        def map(self,*args):raise RuntimeError('worker lost')
    population=PopulationCheckpoint(tmp_path/'population.json',task(),members(),max_updates=4)
    before=population.snapshot()
    with pytest.raises(RuntimeError,match='worker lost'):train_batch(population,'round:',2,FailedExecutor())
    assert population.snapshot()==before
    assert population.accounting()=={'work_unit':'finite_expectation_gradient_update','lower':0,'upper':4}
    with pytest.raises(ValueError,match='reservation'):population.train('new','0',1)


def test_duplicate_target_and_dependency_refused(tmp_path):
    population=PopulationCheckpoint(tmp_path/'population.json',task(),members(),max_updates=4)
    request=dict(event_id='x',parent='0',child='0',architecture=members()['0']['architecture'],
        optimizer=members()['0']['optimizer'],mode='TRAIN',optimizer_policy='COPY',weights=[0])
    with pytest.raises(ValueError,match='unique'):run_batch(population,[request,request],None)
    other={**request,'event_id':'y','parent':'0','child':'1'}
    with pytest.raises(ValueError,match='barrier'):run_batch(population,[request,other],None)


def test_parallel_caller_adapter_known_answer_and_resume(tmp_path):
    from hponas import ParallelAdapterPopulation
    from tests.integration.test_population_adapter import engine, declaration, linear, linear_data
    from examples.population_adapters import LinearSGDAdapter
    reference=engine(tmp_path/'serial').run()
    with ResourceExecutor(2,timeout=40) as executor:
        adapter=ParallelAdapterPopulation(tmp_path/'parallel.json',LinearSGDAdapter(linear_data()),
            declaration(),{'a':linear(.05),'b':linear(.1)},exploration_configs=[linear(.2)],
            max_updates=12,executor=executor)
        actual=adapter.run()
        assert actual['status']=='complete'
        for key in ['selection','final_mean','final_records','accounting','lineage']:
            assert actual[key]==reference[key]
        assert adapter.run()==actual


def test_parallel_adapter_failed_calls_are_charged(tmp_path):
    from hponas import ParallelAdapterPopulation
    from tests.integration.test_population_adapter import declaration, linear, linear_data
    from examples.population_adapters import LinearSGDAdapter
    class Failing(LinearSGDAdapter):
        def train(self,*args,**kwargs):raise ValueError('training failure')
    with ResourceExecutor(2,timeout=40) as executor:
        adapter=ParallelAdapterPopulation(tmp_path/'parallel.json',Failing(linear_data()),
            declaration(),{'a':linear(.05),'b':linear(.1)},exploration_configs=[linear(.2)],max_updates=12,executor=executor)
        actual=adapter.run()
        assert actual['status']=='failed' and actual['accounting']['upper']==4
        assert actual['accounting']['lower']==0 and adapter.run()==actual


def test_partial_parallel_adapter_commit_crash_is_explicitly_uncertain(tmp_path,monkeypatch):
    from hponas import ParallelAdapterPopulation
    from tests.integration.test_population_adapter import declaration, linear, linear_data
    from examples.population_adapters import LinearSGDAdapter
    class Crash(BaseException):pass
    with ResourceExecutor(2,timeout=40) as executor:
        engine=ParallelAdapterPopulation(tmp_path/'adapter.json',LinearSGDAdapter(linear_data()),declaration(),
            {'a':linear(.05),'b':linear(.1)},exploration_configs=[linear(.2)],max_updates=12,executor=executor)
        original=engine._write
        def write(state):
            original(state)
            trains=[e for e in state['events'] if e['request']['operation']=='train']
            if trains and trains[0]['status']=='committed' and any(e['status']=='pending' for e in trains):raise Crash()
        monkeypatch.setattr(engine,'_write',write)
        with pytest.raises(Crash):engine.run()
        monkeypatch.setattr(engine,'_write',original)
        result=engine.run()
        assert result['status']=='failed' and result['accounting']['lower']==1 and result['accounting']['upper']==4


def test_stale_parallel_commit_cannot_overwrite_newer_members(tmp_path,monkeypatch):
    from hponas import population_parallel as module
    from hponas.population import _digest
    class Crash(BaseException):pass
    pop=PopulationCheckpoint(tmp_path/'pop.json',task(),members(),max_updates=4)
    with ResourceExecutor(2,timeout=40) as executor:
        original=module.write_journal
        def write(path,value):
            original(path,value)
            if value['status']=='computed':raise Crash()
        monkeypatch.setattr(module,'write_journal',write)
        with pytest.raises(Crash):train_batch(pop,'r:',2,executor)
        monkeypatch.setattr(module,'write_journal',original)
        state=pop.snapshot();state['max_updates']=5;pop._write(state)
        with pytest.raises(ValueError,match='Stale'):train_batch(pop,'r:',2,executor)
        assert pop.snapshot()==state
