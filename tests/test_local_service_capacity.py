"""Bounded measurement of real local Study/checkpoint throughput and limits."""
import json
import math
import multiprocessing
import os
from pathlib import Path
import resource
import time

import pytest

from hponas import ManagedStudyService, Knob, SearchSpace, SobolSearcher, LocalExecutor, Study
from hponas.operations import backup_database


def _capacity_worker(path, index, output):
    rows, latencies = [], []
    started = time.perf_counter()
    with ManagedStudyService(path) as service:
        for study_index in range(2):
            sid, actor = f'capacity-{index}-{study_index}', f'worker-{index}'
            raw_store, starts, seen = service.store(actor, sid), {}, set()

            class MeasuredStore:
                def save_study_snapshot(self, state):
                    raw_store.save_study_snapshot(state)
                    completed = time.perf_counter()
                    for tid, result in state['results'].items():
                        if tid not in seen:
                            assert result['status'] == 'completed'
                            latencies.append(completed-starts[tid])
                            seen.add(tid)

                def load_study_snapshot(self, name):
                    return raw_store.load_study_snapshot(name)

            def objective(config, trial_id):
                starts[trial_id] = time.perf_counter()
                assert service.reserve(actor, sid, event_id='work-' + trial_id,
                    quota_id=actor, device_us=1_000_000)
                cpu_started = time.thread_time_ns()
                # Known closed-form finite training recurrence.
                value = 1.
                for _ in range(8): value *= 1-config['eta']
                measured = max(1, math.ceil((time.thread_time_ns()-cpu_started)/1000))
                service.finish(actor, sid, event_id='done-' + trial_id,
                    reservation_id='work-' + trial_id, status='completed',
                    measured_device_us=measured, measurement_id='cpu-' + trial_id)
                return {'value': value**2, 'cost': 1.}

            study = Study(SobolSearcher(SearchSpace([Knob('eta', 'continuous', (.05, .25))]), seed=index),
                LocalExecutor(), objective, store=MeasuredStore(), study_name=sid, budget=32,
                legacy_reason='Bounded local capacity fixture; not statistical or production qualification')
            result = study.run()
            for row in result.history:
                expected = (1-study.trials[row.trial_id].config.values['eta'])**16
                assert row.objective_value == pytest.approx(expected)
            assert len(result.history) == len(seen) == 32
            rows.append({'study_id': sid, 'trials': len(result.history),
                         'values': [row.objective_value for row in result.history]})
        accounting = service.quota_report(actor, actor)
    Path(output).write_text(json.dumps({'worker': index, 'studies': rows,
        'latencies_seconds': latencies, 'accounting': accounting,
        'wall_seconds': time.perf_counter()-started,
        'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}, indent=2)+'\n')


def test_four_local_workers_eight_studies_record_capacity_without_extrapolation(tmp_path):
    path = tmp_path/'capacity.db'
    start_us = time.time_ns()//1000
    with ManagedStudyService.create(path, admin='admin') as service:
        for worker in range(4):
            actor = f'worker-{worker}'
            service.configure_quota('admin', event_id='quota-' + actor,
                quota_id=actor, subject=actor, period_id='capacity-fixture',
                start_us=start_us, end_us=start_us+300_000_000, device='cpu',
                device_limit_us=64_000_000, currency='USD', cost_limit_micros=1000,
                price_id='declared-test-price', price_micros_per_hour=1,
                max_active_studies=2)
            for study in range(2):
                sid = f'capacity-{worker}-{study}'
                service.project('admin', sid, owner=actor, event_id='project-' + sid)
    ctx = multiprocessing.get_context('spawn')
    processes = [ctx.Process(target=_capacity_worker, args=(str(path), i, str(tmp_path/f'worker-{i}.json'))) for i in range(4)]
    started = time.perf_counter()
    try:
        for process in processes: process.start()
        for process in processes: process.join(90)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive(): process.kill(); process.join()
    elapsed = time.perf_counter()-started
    workers = [json.loads((tmp_path/f'worker-{i}.json').read_text()) for i in range(4)]
    latencies = sorted(value for worker in workers for value in worker['latencies_seconds'])
    assert len(latencies) == 256 and all(value > 0 for value in latencies)
    with ManagedStudyService(path) as service:
        assert service._conn.execute('SELECT COUNT(*) FROM studies').fetchone()[0] == 8
        assert service._conn.execute("SELECT COUNT(*) FROM trials WHERE status='completed'").fetchone()[0] == 256
        head = service._events()[-1]['digest']
    original_targets = {'concurrent_studies': 100, 'trials_per_study': 1000,
        'distributed_workers': 50, 'trials_per_second_min': 10,
        'latency_p99_seconds_max': 60, 'memory_gb_per_worker_max': 8,
        'scenarios': [[100,100],[10,1000],[1,10000]]}
    summary = {'kind': 'bounded_local_study_capacity_v1', 'workers': 4, 'studies': 8,
        'trials_per_study': 32, 'trials': 256, 'cpu_affinity': sorted(os.sched_getaffinity(0)),
        'gpu': False, 'wall_seconds_including_process_startup': elapsed,
        'trials_per_second_including_process_startup': 256/elapsed,
        'latency_definition': 'objective_entry_to_durable_completed_checkpoint; excludes pre-dispatch queue',
        'latency_p99_seconds': latencies[math.ceil(.99*len(latencies))-1],
        'peak_rss_bytes_per_worker': [row['peak_rss_bytes'] for row in workers],
        'original_targets': original_targets, 'history_head': head,
        'original_scale_qualified': False, 'production_capacity_qualified': False,
        'limitations': ['four local processes share one CPU; not distributed workers',
            'eight studies of 32 trials do not meet original concurrency or trial counts',
            'throughput and latency depend on this tiny recurrence and trusted local storage',
            'CPU meters cover only the declared objective recurrence; framework overhead is separate'],
        'raw_workers': workers}
    # The fixed runner supplies a fresh retained directory. Ordinary pytest can
    # still run the same test without writing into the program evidence tree.
    output = Path(os.environ.get('HPONAS_OPERATION_DIRECTORY', tmp_path))/'local-service-capacity'
    output.mkdir(exist_ok=False)
    (output/'measurement.json').write_text(json.dumps(summary, indent=2)+'\n')
    backup_database(path, output/'database')

