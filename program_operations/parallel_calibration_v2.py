#!/usr/bin/python3 -I
"""One source-bound PAR-QUAL-01 calibration; never launches a full campaign."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

ROOT = Path('/home/ubuntu/workspace/hponas')
BASE = ROOT / 'docs/program/evidence/2026-10-26/parallel-admission-02'
sys.path[:0] = [str(ROOT), str(BASE)]
from preparation import bind, read, verify_binding
from tools.source_identity import source_digest

def main():
    if sys.argv[1:]:
        raise ValueError('No arguments accepted')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Calibration stopped')))
    assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
    manifest = read(BASE / 'calibration-manifest.json')
    assert manifest['runner'] == bind(Path(__file__))
    assert manifest['source_digest'] == source_digest()
    assert manifest['limits'] == dict(workers=24, owned_rss_gib=64, inner_wall_seconds=2700, outer_wall_seconds=2850, gpu=False)
    for ref in manifest['inputs']:
        verify_binding(ref)
    p = read(ROOT / 'docs/program/program.json')
    stages = {s['id']: s for s in p['continuation']['steps']}
    assert p['active_work_item'] == 'PAR-QUAL-01'
    assert stages['PAR-QUAL-01/PREPARE']['state'] == 'in_progress'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
    env = dict(os.environ, **manifest['environment'])
    checked = subprocess.run(['/home/ubuntu/miniforge3/bin/python', str(BASE / 'review_preparation.py')],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True, timeout=180)
    review = json.loads(checked.stdout)
    assert review['passed'] and review['source_digest'] == manifest['source_digest']
    guard_path = ROOT / 'program_operations/storage_guard.py'
    spec = importlib.util.spec_from_file_location('parallel_calibration_guard', guard_path)
    guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
    cpus = sorted(os.sched_getaffinity(0))[:24]
    assert len(cpus) == 24
    os.sched_setaffinity(0, set(cpus))
    out = BASE / 'calibration-01'
    out.mkdir(exist_ok=False)
    inputs = manifest['inputs'] + [bind(BASE / 'calibration-manifest.json')]
    plan = dict(kind='v03_bounded_admission_calibration_v1', source_digest=source_digest(),
        calibration_wall_seconds=2700, outer_wall_seconds=2850, cpu_affinity=cpus,
        owned_rss_gib=64, gpu=False, inputs=inputs, storage_policy=guard.DEFAULT_STORAGE,
        scientific_acceptance=False, official_campaigns=0, no_retry=True,
        resource_authorization='approved_parallel_extension_master_execution')
    with (out / 'allocation.json').open('x') as handle:
        json.dump(plan, handle, indent=2); handle.write(chr(10)); handle.flush(); os.fsync(handle.fileno())
    def observe(*_args):
        assert source_digest() == plan['source_digest']
        for ref in inputs:
            verify_binding(ref)
    result = guard.run(['/home/ubuntu/miniforge3/bin/python', str(BASE / 'calibration_child.py')],
        out / 'guarded-execution', 2850, env, plan['source_digest'], observe=observe)
    print(json.dumps({k: result[k] for k in ('passed', 'error', 'returncode', 'elapsed_seconds')}), flush=True)
    return int(not result['passed'])

if __name__ == '__main__':
    raise SystemExit(main())
