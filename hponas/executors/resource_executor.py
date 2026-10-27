"""Persistent isolated local workers with exclusive CPU/GPU assignments.

Linux fresh-interpreter spawn. No automatic retries. Inputs are trusted Python
code, not a security sandbox. Executor ownership does not exclude other apps.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import math
import multiprocessing
import os
from pathlib import Path
from queue import Queue
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

import cloudpickle

from hponas.executors.base import BaseExecutor
from hponas.executors.resources import ResourceSpec, assignments
from hponas.types import Result


class WorkerFailure(RuntimeError):
    pass


class ResourceExecutor(BaseExecutor):
    def __init__(self, num_workers=1, *, resources=None, cpu_ids=None, gpu_ids=(), timeout=120):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('A finite positive worker deadline is required')
        self.resources = resources or ResourceSpec()
        from hponas.executors.leases import canonical_gpu_ids
        gpu_ids = canonical_gpu_ids(gpu_ids)
        self.placements = assignments(num_workers, self.resources, cpu_ids=cpu_ids, gpu_ids=gpu_ids)
        self.num_workers, self.timeout, self.max_retries = num_workers, timeout, 0
        self._workers = [None] * num_workers
        self._available = Queue()
        for i in range(num_workers):
            self._available.put(i)
        self._closed = False
        self._prepare_lock = threading.Lock()
        self._prepared = False
        self._leases = None
        # Linux parent-death signals follow the thread that spawns a child.
        # Keep that thread alive across short-lived batch collector pools.
        self._launcher = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hponas-launch')

    def _start(self, index):
        return self._launcher.submit(self._spawn, index).result()

    def _spawn(self, index):
        parent, child = multiprocessing.Pipe()
        placement = self.placements[index]
        env = os.environ.copy()
        env.update(CUDA_VISIBLE_DEVICES=','.join(placement.gpu_ids),
                   OMP_NUM_THREADS=str(placement.threads), OPENBLAS_NUM_THREADS=str(placement.threads),
                   MKL_NUM_THREADS=str(placement.threads), NUMEXPR_NUM_THREADS=str(placement.threads))
        # An installed package needs no checkout dependency; source execution
        # propagates the current import search path to the fresh interpreter.
        env['PYTHONPATH'] = os.pathsep.join(str(Path(x or os.getcwd()).resolve()) for x in sys.path)
        process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('worker_bootstrap.py')),
            str(child.fileno()), json.dumps(placement.to_dict()), str(os.getpid())], env=env,
            pass_fds=(child.fileno(),), start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        child.close()
        self._workers[index] = (process, parent)
        try:
            if not parent.poll(self.timeout) or parent.recv()[0] != 'ready':
                raise WorkerFailure('Worker startup deadline exceeded')
        except (EOFError, OSError) as exc:
            self._stop(index)
            raise WorkerFailure('Worker failed during startup') from exc
        except BaseException:
            self._stop(index)
            raise

    def _stop(self, index):
        worker = self._workers[index]
        if worker is None:
            return
        process, pipe = worker
        pipe.close()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        # Reap descendants even when the leader exited before cleanup.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._workers[index] = None

    def prepare(self):
        with self._prepare_lock:
            if self._closed:
                raise RuntimeError('Executor is closed')
            if not self._prepared:
                from hponas.executors.leases import HostLeases
                self._leases = HostLeases(self.placements)
                try:
                    for i in range(self.num_workers):
                        self._start(i)
                except BaseException:
                    for i in range(self.num_workers):
                        self._stop(i)
                    self._leases.close()
                    self._leases = None
                    raise
                self._prepared = True

    def _run(self, kind, task, function, task_id, on_report=None):
        self.prepare()
        index = self._available.get()
        started = time.monotonic()
        try:
            if self._closed:
                raise RuntimeError('Executor is closed')
            if self._workers[index] is None:
                self._start(index)
            process, pipe = self._workers[index]
            context = replace(self.placements[index], task_id=str(task_id), attempt_id=uuid4().hex).to_dict()
            pipe.send_bytes(cloudpickle.dumps((kind, task, function, context, on_report is not None)))
            while True:
                remaining = self.timeout - (time.monotonic() - started)
                if remaining <= 0 or not pipe.poll(remaining):
                    raise TimeoutError('Worker execution deadline exceeded')
                tag, payload = cloudpickle.loads(pipe.recv_bytes())
                if tag == 'progress':
                    pipe.send(on_report(payload))
                elif tag == 'error':
                    raise WorkerFailure(payload)
                elif tag == 'result':
                    return payload
                else:
                    raise WorkerFailure('Unknown worker message')
        except BaseException:
            self._stop(index)
            raise
        finally:
            self._available.put(index)

    def execute(self, trial, objective_fn, *, on_report=None):
        started = time.monotonic()
        try:
            result = self._run('trial', trial, objective_fn, trial.trial_id, on_report)
        except (WorkerFailure, TimeoutError, EOFError, OSError) as exc:
            result = Result(trial.trial_id, float('nan'), time.monotonic()-started, trial.fidelity,
                {'error': str(exc), 'execution': {'elapsed_seconds': time.monotonic()-started,
                 'accounting': 'lower_bound_after_interruption', 'attempts': 1}},
                'timeout' if isinstance(exc, TimeoutError) else 'failed')
        trial.status = result.status
        return result

    def execute_batch(self, trials, objective_fn, *, on_report=None):
        self.prepare()
        with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
            return list(pool.map(lambda t: self.execute(t, objective_fn, on_report=on_report), trials))

    def map(self, function, tasks):
        """Ordered independent tasks; function(task, ExecutionContext)."""
        self.prepare()
        with ThreadPoolExecutor(max_workers=self.num_workers) as pool:
            return list(pool.map(lambda row: self._run('task', row[1], function, row[0]), enumerate(tasks)))

    def shutdown(self):
        self._closed = True
        for i in range(self.num_workers):
            self._stop(i)
        if self._leases is not None:
            self._leases.close()
            self._leases = None
        self._launcher.shutdown(wait=True)

    def __enter__(self):
        self.prepare()
        return self

    def __exit__(self, *exc):
        self.shutdown()
