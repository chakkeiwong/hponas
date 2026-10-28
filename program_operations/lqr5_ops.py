#!/usr/bin/python3 -I
"""Fixed no-training RL-LQR-02 operations; no arbitrary arguments."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path('/home/ubuntu/workspace/hponas')
BASE = ROOT/'docs/program/evidence/2026-10-27/rl-lqr-02'
EXT = ROOT/'extensions/rl-lqr5'
OPERATIONS = {'preflight': 'RL-LQR-02/PREFLIGHT', 'audit': 'RL-LQR-02/AUDIT',
              'master-audit': 'GAP-01/FINAL-AUDIT'}


def binding(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n'); temp.replace(path)


def helpers():
    spec = importlib.util.spec_from_file_location('lqr_owned_processes', ROOT/'program_operations/rl_lqr_ops.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        raise ValueError('Exactly one fixed LQR5 operation: preflight, audit, master-audit')
    op = sys.argv[1]; stage = OPERATIONS[op]; utility = helpers()
    program = json.loads((ROOT/'docs/program/program.json').read_text())
    steps = {s['id']: s for s in program['continuation']['steps']}
    if program['active_work_item'] != stage.split('/')[0] or steps[stage]['state'] != 'in_progress':
        raise ValueError('Operation is not the active reviewed stage')
    if any(steps[s]['state'] != 'complete' for s in steps[stage]['dependencies']):
        raise ValueError('Operation predecessor incomplete')
    manifest_path = BASE/(op+'-manifest.json'); manifest = json.loads(manifest_path.read_text())
    if manifest['operation'] != op or manifest['runner'] != binding(Path(__file__)):
        raise ValueError('Reviewed operation/runner differs')
    if manifest['core_source'] != utility.source() or manifest['training_transitions'] != 0:
        raise ValueError('Core source or zero-training allocation differs')
    bound = [manifest['runner'], *manifest['inputs']]
    if any(binding(ROOT/r['path']) != r for r in bound):
        raise ValueError('Reviewed source/input changed')
    if shutil.disk_usage(ROOT).free < 4*1024**3:
        raise ValueError('Insufficient disk headroom')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+op+'-'+uuid4().hex[:8])
        out.mkdir(); shutil.copyfile(manifest_path, out/'manifest.json')
        for item in bound:
            dest = out/'inputs'/item['path']; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/item['path'], dest)
        env = {key: os.environ[key] for key in ('HOME', 'USER', 'LOGNAME', 'LANG') if key in os.environ}
        env.update(PATH='/home/ubuntu/miniforge3/bin:/usr/bin:/bin', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
            MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1',
            PYTHONHASHSEED='0', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', RLLIB_TEST_NO_TF_IMPORT='1',
            RLLIB_TEST_NO_JAX_IMPORT='1', MPLBACKEND='Agg')
        env['PYTHONPATH'] = os.pathsep.join(str(p) for p in (EXT, ROOT/'.hponas-runtime/rl-lqr-deps',
            ROOT/'.hponas-runtime/spec-deps', ROOT/'.hponas-runtime/postgres-deps', ROOT))
        os.sched_setaffinity(0, {max(os.sched_getaffinity(0))})
        command = ['/home/ubuntu/miniforge3/bin/python', str(EXT/'run_operation.py'), op, str(out)]
        receipt = {'kind': 'lqr5_no_training_v1', 'operation': op, 'stage': stage, 'passed': False,
            'manifest': binding(manifest_path), 'core_source': utility.source(),
            'directory': str(out.relative_to(ROOT)), 'training_transitions': 0,
            'limits': {'seconds': 300, 'cpu_cores': 1, 'gpus': 0, 'host_rss_bytes': 8*1024**3,
                       'output_bytes': 128*1024**2}}
        write(out/'intent.json', receipt); start = time.monotonic(); peak = 0; reason = None
        with (out/'execution.log').open('x') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            table = utility.process_table(); owned = {child.pid: table[child.pid][1]} if child.pid in table else {}
            write(out/'process.json', {'pid': child.pid, 'command': command, 'started': time.time()})
            while child.poll() is None:
                live = utility.tracked(owned); rss = sum(r[3] for r in live.values()); peak = max(peak, rss)
                elapsed = time.monotonic()-start
                size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
                write(out/'progress.json', {'seconds': elapsed, 'owned_pids': sorted(live), 'rss_bytes': rss, 'bytes': size})
                if elapsed > 300: reason = 'wall_time_limit'
                elif rss > 8*1024**3: reason = 'owned_rss_limit'
                elif size > 128*1024**2: reason = 'output_size_limit'
                elif shutil.disk_usage(ROOT).free < 4*1024**3: reason = 'disk_floor'
                if reason:
                    for pid in live:
                        try: os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: pass
                    for pid in utility.tracked(owned):
                        try: os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                    break
                time.sleep(.5)
            code = child.wait()
        survivors = utility.tracked(owned)
        for pid in survivors:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        same = all(binding(ROOT/r['path']) == r for r in bound)
        receipt.update(returncode=code, stop_reason=reason, seconds=time.monotonic()-start,
            peak_rss_bytes=peak, remaining_children=sorted(survivors), inputs_unchanged=same,
            end_core_source=utility.source(), log=binding(out/'execution.log'))
        receipt['passed'] = code == 0 and reason is None and not survivors and same and receipt['end_core_source'] == receipt['core_source']
        write(out/'receipt.json', receipt); print(json.dumps(receipt, indent=2))
        return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
