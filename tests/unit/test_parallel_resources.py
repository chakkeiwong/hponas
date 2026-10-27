import os
import pytest
from hponas.executors.resources import ResourceSpec, assignments


@pytest.mark.parametrize('kwargs', [{'threads':0},{'cpu_cores':True},{'cpu_cores':0},{'gpus':.5},{'gpus':-1},{'threads':2}])
def test_invalid_resource_requests(kwargs):
    with pytest.raises(ValueError): ResourceSpec(**kwargs)


def test_exclusive_partition_and_context():
    cpus=sorted(os.sched_getaffinity(0))
    assert len(cpus)>=2
    a,b=assignments(2,ResourceSpec(gpus=1),cpu_ids=cpus[:2],gpu_ids=('GPU-a','GPU-b'))
    assert set(a.cpu_ids).isdisjoint(b.cpu_ids)
    assert a.gpu_ids==('GPU-a',) and b.gpu_ids==('GPU-b',)
    assert a.device=='cuda:0' and a.to_dict()['threads']==1


def test_infeasible_and_duplicate_assignments_refused():
    cpu=min(os.sched_getaffinity(0))
    for kwargs in [dict(cpu_ids=[cpu]),dict(gpu_ids=['0','0']),dict(gpu_ids=['0']),dict(cpu_ids=[cpu,cpu])]:
        with pytest.raises(ValueError):assignments(2,ResourceSpec(gpus=1),**kwargs)
    with pytest.raises(ValueError):assignments(1,ResourceSpec(),gpu_ids=['0'])
