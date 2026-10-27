"""Ray assignment verification for the opt-in ResourceSpec contract."""
from contextlib import contextmanager
import os
from uuid import uuid4
from hponas.executors.resources import ExecutionContext


@contextmanager
def assigned_context(trial_id, spec):
    import ray
    import torch
    from threadpoolctl import threadpool_limits
    runtime = ray.get_runtime_context()
    ids = tuple(str(x) for x in runtime.get_accelerator_ids().get('GPU', []))
    assigned = runtime.get_assigned_resources()
    if len(ids) != spec.gpus or assigned.get('CPU', 0) < spec.cpu_cores:
        raise RuntimeError('Ray assignment differs from requested ResourceSpec')
    if spec.gpus and (not torch.cuda.is_available() or torch.cuda.device_count() != spec.gpus):
        raise RuntimeError('Ray CUDA visibility differs from assigned GPUs')
    if not spec.gpus and os.environ.get('CUDA_VISIBLE_DEVICES', '') not in ('', '-1'):
        raise RuntimeError('CPU Ray task unexpectedly exposes CUDA')
    previous = torch.get_num_threads()
    torch.set_num_threads(spec.threads)
    context = ExecutionContext(str(runtime.get_worker_id()), uuid4().hex, trial_id,
        tuple(sorted(os.sched_getaffinity(0))), ids, spec.threads, 'cuda:0' if ids else 'cpu')
    try:
        with threadpool_limits(limits=spec.threads):
            yield context
    finally:
        torch.set_num_threads(previous)


def evaluate_assigned(trial, objective, spec, report=None):
    from hponas.executors.base import evaluate_trial
    with assigned_context(trial.trial_id, spec) as context:
        result = evaluate_trial(trial, objective, report, execution_context=context)
        result.metadata.setdefault('execution', {})['worker'] = context.to_dict()
        result.metadata['execution']['cpu_placement'] = 'ray_logical_reservation_not_exclusive_affinity'
        return result
