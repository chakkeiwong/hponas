"""Fresh-interpreter persistent worker. Device environment precedes imports."""
import json
import os
import sys
from multiprocessing.connection import Connection


def main():
    # A crashed coordinator must not leave numerical workers using devices
    # after its cooperative leases are released by the operating system.
    import ctypes
    import signal
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGTERM,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'Cannot install worker parent-death signal')
    if os.getppid()!=int(sys.argv[3]):
        return
    connection = Connection(int(sys.argv[1]))
    placement = json.loads(sys.argv[2])
    os.sched_setaffinity(0, placement['cpu_ids'])
    # stdout belongs to objective logs, never to the transport connection.
    import cloudpickle
    import torch
    torch.set_num_threads(placement['threads'])
    torch.set_num_interop_threads(1)
    from threadpoolctl import threadpool_limits
    from hponas.executors.resources import ExecutionContext
    from hponas.executors.base import evaluate_trial
    with threadpool_limits(limits=placement['threads']):
        connection.send(('ready', {'pid': os.getpid(), 'cpus': sorted(os.sched_getaffinity(0))}))
        while True:
            packet = connection.recv_bytes()
            if packet == b'STOP':
                break
            try:
                kind, task, function, context, streaming = cloudpickle.loads(packet)
                context['cpu_ids']=tuple(context['cpu_ids'])
                context['gpu_ids']=tuple(context['gpu_ids'])
                execution = ExecutionContext(**context)
                if execution.gpu_ids:
                    if not torch.cuda.is_available() or torch.cuda.device_count() != len(execution.gpu_ids):
                        raise RuntimeError('Assigned CUDA devices are unavailable in worker')
                    torch.cuda.set_device(0)
                if kind == 'trial':
                    def report(progress):
                        connection.send(('progress', progress))
                        return connection.recv()
                    result = evaluate_trial(task, function, report if streaming else None,
                                            execution_context=execution)
                    result.metadata.setdefault('execution', {}).update(worker=execution.to_dict(), pid=os.getpid())
                else:
                    result = function(task, execution)
                if execution.gpu_ids:
                    torch.cuda.synchronize()
                connection.send_bytes(cloudpickle.dumps(('result', result)))
            except BaseException as exc:
                connection.send_bytes(cloudpickle.dumps(('error', type(exc).__name__ + ': ' + str(exc))))
    connection.close()


if __name__ == '__main__':
    main()
