"""Actual local Ray assignment; missing service is a failure, never a skip."""
import os
import time
import ray
from hponas import RayExecutor,ResourceSpec
from hponas.types import Trial,Config


def test_actual_ray_resources_and_context():
    ray.init(num_cpus=2,num_gpus=0,include_dashboard=False,object_store_memory=100*1024*1024)
    try:
        executor=RayExecutor(2,max_retries=0,resources=ResourceSpec(),timeout=40)
        def objective(config,execution):
            import torch
            time.sleep(.1)
            return {'value':config['x']**2,'metadata':{'worker':execution.to_dict(),
                'pid':os.getpid(),'threads':torch.get_num_threads()}}
        results=executor.execute_batch([Trial(Config({'x':i}),str(i)) for i in range(4)],objective)
        assert [r.objective_value for r in results]==[0,1,4,9],[r.metadata for r in results]
        assert len({r.metadata['pid'] for r in results})==2
        assert all(r.metadata['threads']==1 and r.metadata['worker']['device']=='cpu' for r in results)
        executor.shutdown()
        assert ray.is_initialized()
    finally:ray.shutdown()
