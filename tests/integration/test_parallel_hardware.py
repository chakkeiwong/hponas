"""Bounded actual CUDA placement and BG-PBT device equivalence."""
import json
import os
from pathlib import Path
import time
import numpy as np
import pytest
from hponas import ResourceExecutor, ResourceSpec
from hponas.types import Trial,Config


def devices():
    ids=os.environ.get('HPONAS_PARALLEL_GPU_IDS','').split(',')
    if len(ids)!=2 or any(not x for x in ids):
        pytest.fail('Two actual GPU identities are required; absence is not a pass')
    return ids


def tensor_objective(config,execution):
    import torch
    x=torch.arange(64*64,dtype=torch.float64,device=execution.device).reshape(64,64)/4096
    start=time.perf_counter()
    for _ in range(32): y=x @ x.T
    torch.cuda.synchronize()
    return {'value':float(y.sum().cpu()),'cost':32.,'metadata':{
        'physical_ids':list(execution.gpu_ids),'visible':torch.cuda.device_count(),
        'device':str(y.device),'pid':os.getpid(),'start':start,'end':time.perf_counter(),
        'peak_bytes':torch.cuda.max_memory_allocated()}}


def test_actual_two_gpu_assignment_reference_and_timing():
    import torch
    ids=devices();trials=[Trial(Config({}),str(i)) for i in range(4)]
    reference=np.arange(4096,dtype=np.float64).reshape(64,64)/4096
    expected=float((reference @ reference.T).sum())
    timings={};outputs={}
    for workers in (1,2):
        with ResourceExecutor(workers,resources=ResourceSpec(gpus=1),gpu_ids=ids[:workers],timeout=60) as executor:
            executor.execute_batch(trials,tensor_objective) # unmeasured warmup
            start=time.perf_counter();results=executor.execute_batch(trials,tensor_objective)
            timings[workers]=time.perf_counter()-start
            assert all(r.status=='completed' for r in results),[r.metadata for r in results]
            assert all(abs(r.objective_value-expected)<=1e-9+1e-7*abs(expected) for r in results)
            assert len({r.metadata['physical_ids'][0] for r in results})==workers
            assert all(r.metadata['visible']==1 and r.metadata['device']=='cuda:0' for r in results)
            outputs[workers]=[r.to_dict() for r in results]
    output=Path(os.environ['HPONAS_PARALLEL_OUTPUT'])/'gpu-timing.json'
    output.write_text(json.dumps({'wall_seconds':timings,'speedup':timings[1]/timings[2],
        'efficiency':timings[1]/(2*timings[2]),'reference':expected,'records':outputs,
        'interpretation':'Tiny correctness fixture, no speedup acceptance threshold'},indent=2))


def test_actual_gpu_bgpbt_matches_cpu_and_restores_portably(tmp_path):
    from tests.unit.test_bg_population import task,config,members
    from hponas.bg_pbt import LocalBGPBT
    from hponas.population import restore_member
    initial=members();pool=[config(w,d) for w,d in [(1,1),(2,1),(3,1),(2,2)]]
    kwargs=dict(increment_bound=1,generations=2,max_rounds=1,patience=1,updates_per_round=1,
        distillation_rungs=(1,2),seed=7,max_updates=10,fit_iterations=1)
    cpu=LocalBGPBT(tmp_path/'cpu',task(),initial,pool,**kwargs).run()
    with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=60) as executor:
        engine=LocalBGPBT(tmp_path/'gpu',task(),initial,pool,executor=executor,**kwargs)
        gpu=engine.run();assert gpu['status']=='complete'
        assert gpu['accounting']==cpu['accounting']
        assert engine.run()==gpu
    for name,member in gpu['final_members'].items():
        model,_=restore_member(member)
        assert str(next(model.parameters()).device)=='cpu'
        assert member['architecture']==cpu['final_members'][name]['architecture']
        for key,value in member['tensors'].items():
            np.testing.assert_allclose(value,cpu['final_members'][name]['tensors'][key],atol=1e-9,rtol=1e-7)


def test_gpu_oom_is_retained_without_retry():
    def oom(config,execution):
        import torch
        torch.ones(1,device=execution.device)
        raise torch.cuda.OutOfMemoryError('injected OOM after real CUDA allocation')
    with ResourceExecutor(1,resources=ResourceSpec(gpus=1),gpu_ids=devices()[:1],timeout=60) as executor:
        result=executor.execute(Trial(Config({}),'oom'),oom)
        assert result.status=='failed' and 'OutOfMemoryError' in result.metadata['traceback']
        assert executor.execute(Trial(Config({}),'healthy'),tensor_objective).status=='completed'


def test_finite_mdp_buffer_gpu_student_and_cpu_teacher():
    def evaluate(config, execution):
        import torch
        from workloads.finite_mdp import FiniteMDP
        class Table(torch.nn.Module):
            def __init__(self, device):
                super().__init__()
                self.register_buffer('value', torch.tensor([[0., 0., .25]],
                    dtype=torch.float64, device=device, requires_grad=True))
            def forward(self, observations):
                assert observations.device == self.value.device
                return self.value
        student, teacher = Table(execution.device), Table('cpu')
        objective = FiniteMDP([1.], [[[0.], [0.]]], [[1., 0.]], horizon=1)
        result = objective.components(student, teacher, 0.)
        assert result['loss'].is_cuda
        result['loss'].backward()
        assert teacher.value.grad is None
        return {'value': float(result['return'].cpu()), 'cost': 1.,
                'metadata': {'gradient': student.value.grad.detach().cpu().tolist()[0]}}
    with ResourceExecutor(2, resources=ResourceSpec(gpus=1), gpu_ids=devices(), timeout=60) as executor:
        results = executor.execute_batch([Trial(Config({}), str(i)) for i in range(2)], evaluate)
        assert all(r.status == 'completed' for r in results), [r.metadata for r in results]
        for result in results:
            assert result.objective_value == pytest.approx(.5, abs=1e-14)
            assert result.metadata['gradient'] == pytest.approx([-.25, .25, 0.], abs=1e-14)


def test_scalar_family_replicas_execute_actual_cuda_objectives():
    from hponas import run_replicas,LocalExecutor
    from tests.integration.test_parallel_methods import run_case
    methods=('random','sobol','tpe','gp','cma','robust','trust','cost','asha','pasha',
             'priorband','dehb','finite-prior','categorical-priorband','pibo','warm')
    rows=[]
    with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=90) as executor:
        for method in methods:
            actual=run_replicas(executor,lambda seed,ex:run_case(method,seed,ex,require_cuda=True),(7,11))
            for seed,trace in zip((7,11),actual):
                expected=run_case(method,seed,LocalExecutor())
                assert len(trace)==len(expected)
                for a,b in zip(expected,trace):
                    assert a[0]==pytest.approx(b[0],abs=1e-9,rel=1e-7)
                    assert a[1:]==pytest.approx(b[1:],abs=1e-9,rel=1e-7)
                rows.append({'method':method,'seed':seed,'evaluations':len(trace),'cuda_objective':True})
    (Path(os.environ['HPONAS_PARALLEL_OUTPUT'])/'gpu-methods.json').write_text(json.dumps(rows,indent=2))


@pytest.mark.parametrize('method',['random','qlognehvi','chebyshev','nsgaii'])
def test_vector_family_actual_cuda(method):
    from tests.integration.test_parallel_methods import run_vector_case
    with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=60) as executor:
        run_vector_case(method,executor,require_cuda=True)


def test_rgpe_declared_repetitions_actual_cuda(tmp_path):
    from contextlib import closing
    from hponas.store import Store
    from tests.integration.test_declared_rgpe import source,target,objective
    def cuda_objective(config,seed,evaluation,execution):
        import torch
        result=objective(config,seed,evaluation)
        tensor=torch.tensor(result['value'],dtype=torch.float64,device=execution.device)
        assert tensor.is_cuda
        result['value']=float(tensor.cpu())
        return result
    with closing(Store(tmp_path/'rgpe.sqlite')) as store:
        source(store)
        with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=60) as executor:
            study=target(store,fn=cuda_objective,executor=executor,evaluation_workers=2,max_concurrent=1)
            result=study.run()
            assert result.best_value==8 and result.evaluation['selection']==['target_trial_0']


@pytest.mark.parametrize('method',['pbt','pb2'])
def test_pbt_pb2_gpu_population_matches_cpu(tmp_path,method):
    from tests.unit.test_bg_population import task,members
    from hponas.population import PopulationCheckpoint
    from hponas.population_search import LocalPBT
    from hponas.pb2_mix import PB2MixExplorer
    def run(path,executor):
        population=PopulationCheckpoint(path/'population.json',task(),members(),max_updates=8)
        explorer=PB2MixExplorer(increment_bound=1,fit_iterations=1,horizon=2) if method=='pb2' else None
        LocalPBT(path/'controller.json',population,explorer=explorer,executor=executor).run(2,updates_per_round=2)
        return population.snapshot(),population.accounting()
    cpu,expected_work=run(tmp_path/'cpu',None)
    with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=60) as executor:
        gpu,work=run(tmp_path/'gpu',executor)
    assert work==expected_work
    for name,member in gpu['members'].items():
        for key,value in member['tensors'].items():
            np.testing.assert_allclose(value,cpu['members'][name]['tensors'][key],atol=1e-9,rtol=1e-7)


def test_caller_adapter_actual_cuda_and_portable_checkpoint(tmp_path):
    from examples.population_adapters import LinearSGDAdapter
    from tests.integration.test_population_adapter import engine,declaration,linear,linear_data
    from hponas import ParallelAdapterPopulation
    class CudaLinear(LinearSGDAdapter):
        def initialize(self,config,*,seed,evaluation,execution):
            return self.restore(super().initialize(config,seed=seed,evaluation=evaluation),config,
                seed=seed,evaluation=evaluation,execution=execution)
        def restore(self,checkpoint,config,*,seed,evaluation,execution):
            import torch
            state=super().restore(checkpoint,config,seed=seed,evaluation=evaluation)
            for k in ('w','velocity'):state[k]=torch.tensor(state[k],dtype=torch.float64,device=execution.device)
            assert state['w'].is_cuda
            return state
        def checkpoint(self,runtime):
            return {k:(float(v.cpu()) if k in ('w','velocity') else v) for k,v in runtime.items()}
        def train(self,runtime,config,*,evaluation,execution):
            import torch
            rows=torch.tensor([self.data[k] for k in evaluation.fold.train_ids],dtype=torch.float64,device=execution.device)
            gradient=(2*rows[:,0]*(runtime['w']*rows[:,0]-rows[:,1])).mean()
            runtime['velocity']=config['momentum']*runtime['velocity']+gradient
            runtime['w']-=config['lr']*runtime['velocity'];runtime['updates']+=1
        def evaluate(self,runtime,*,evaluation,execution):
            import torch
            rows=torch.tensor([self.data[k] for k in evaluation.fold.score_ids],dtype=torch.float64,device=execution.device)
            return float(((runtime['w']*rows[:,0]-rows[:,1]).square().mean()).cpu())
        def transfer(self,checkpoint,source_config,target_config,*,optimizer_policy,seed,evaluation,execution):
            value=dict(checkpoint)
            if optimizer_policy=='RESET':value['velocity']=0.
            elif optimizer_policy!='COPY':raise ValueError('Optimizer policy')
            return value
    expected=engine(tmp_path/'reference').run()
    with ResourceExecutor(2,resources=ResourceSpec(gpus=1),gpu_ids=devices(),timeout=60) as executor:
        actual=ParallelAdapterPopulation(tmp_path/'cuda.json',CudaLinear(linear_data()),declaration(),
            {'a':linear(.05),'b':linear(.1)},exploration_configs=[linear(.2)],max_updates=12,executor=executor).run()
    assert actual['status']=='complete' and actual['selection']==expected['selection']
    assert actual['accounting']==expected['accounting']
    assert actual['final_mean']==pytest.approx(expected['final_mean'],abs=1e-9,rel=1e-7)
