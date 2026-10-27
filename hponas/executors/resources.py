"""Explicit physical worker resources, separate from scientific work budgets."""
from dataclasses import asdict, dataclass
import os


@dataclass(frozen=True)
class ResourceSpec:
    cpu_cores: int = 1
    threads: int = 1
    gpus: int = 0

    def __post_init__(self):
        if any(type(x) is not int for x in (self.cpu_cores, self.threads, self.gpus)):
            raise ValueError('Resource counts must be integers; fractional GPUs are unsupported')
        if self.cpu_cores < 1 or not 1 <= self.threads <= self.cpu_cores or self.gpus < 0:
            raise ValueError('Positive CPU/thread counts and nonnegative whole GPUs required')


@dataclass(frozen=True)
class ExecutionContext:
    worker_id: str
    attempt_id: str
    task_id: str
    cpu_ids: tuple[int, ...]
    gpu_ids: tuple[str, ...]
    threads: int
    device: str

    def to_dict(self):
        return {**asdict(self), 'cpu_ids': list(self.cpu_ids), 'gpu_ids': list(self.gpu_ids)}


def assignments(workers, resources, *, cpu_ids=None, gpu_ids=()):
    """Validate and partition an explicitly owned host allocation without sharing."""
    if type(workers) is not int or workers < 1 or not isinstance(resources, ResourceSpec):
        raise ValueError('Positive worker count and ResourceSpec required')
    available = tuple(sorted(os.sched_getaffinity(0)))
    cpus = available if cpu_ids is None else tuple(cpu_ids)
    gpus = tuple(str(x) for x in gpu_ids)
    if (not cpus or any(type(c) is not int for c in cpus)
            or len(set(cpus)) != len(cpus) or not set(cpus) <= set(available)):
        raise ValueError('CPU IDs must be distinct available affinity IDs')
    if len(set(gpus)) != len(gpus) or any(not g or ',' in g or g.startswith('-') for g in gpus):
        raise ValueError('GPU IDs must be distinct nonempty CUDA identifiers')
    if len(cpus) < workers * resources.cpu_cores or len(gpus) < workers * resources.gpus:
        raise ValueError('Requested workers exceed the explicit CPU/GPU capacity')
    if resources.gpus == 0 and gpus:
        raise ValueError('CPU-only allocation must not specify GPUs')
    return tuple(ExecutionContext(str(i), '', '',
        cpus[i*resources.cpu_cores:(i+1)*resources.cpu_cores],
        gpus[i*resources.gpus:(i+1)*resources.gpus], resources.threads,
        'cuda:0' if resources.gpus else 'cpu') for i in range(workers))
