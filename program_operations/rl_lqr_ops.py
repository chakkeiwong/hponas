#!/usr/bin/python3 -I
"""Fixed, bounded RL-LQR-01 operations. No arbitrary commands or destinations."""
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
BASE = ROOT / 'docs/program/evidence/2026-10-27/rl-lqr-01'
EXT = ROOT / 'extensions/rl-lqr'
PYTHON = '/home/ubuntu/miniforge3/bin/python'
OPERATIONS = {
    'runtime': ('RUNTIME', 600), 'oracle': ('ORACLE', 300),
    'learner': ('LEARNER', 600), 'joint': ('JOINT', 3600),
    'hardware': ('HARDWARE', 600), 'build': ('DOCUMENTATION', 600),
    'audit': ('AUDIT', 600),
    'joint-replay': ('JOINT', 600),
    'master-audit': ('FINAL-AUDIT', 600),
}


def binding(path):
    return {'path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def source():
    spec = importlib.util.spec_from_file_location('core_identity', ROOT/'tools/source_identity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_digest(ROOT)


def process_table():
    result = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path/'stat').read_text().rsplit(')', 1)[1].split()
            result[int(path.name)] = (int(fields[1]), fields[19], fields[0],
                                      int((path/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return result


def tracked(owned):
    table = process_table()
    while True:
        added = {pid: row[1] for pid, row in table.items()
                 if row[0] in owned and row[0] in table and table[row[0]][1] == owned[row[0]]
                 and pid not in owned}
        if not added:
            break
        owned.update(added)
    return {pid: table[pid] for pid, born in owned.items()
            if pid in table and table[pid][1] == born and table[pid][2] != 'Z'}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print('Exactly one fixed RL-LQR-01 operation required: '+', '.join(OPERATIONS))
        return 2
    op = sys.argv[1]
    stage, seconds = OPERATIONS[op]
    program = json.loads((ROOT/'docs/program/program.json').read_text())
    steps = {s['id']: s for s in program['continuation']['steps']}
    work = 'GAP-01' if op == 'master-audit' else 'RL-LQR-01'
    row = steps[work+'/'+stage]
    if program['active_work_item'] != work or row['state'] not in ('in_progress', 'complete'):
        raise ValueError('Operation is not the active reviewed stage')
    if any(steps[s]['state'] != 'complete' for s in row['dependencies']):
        raise ValueError('An operation prerequisite is incomplete')
    manifest_path = BASE/(op+'-manifest.json')
    manifest = json.loads(manifest_path.read_text())
    if manifest['operation'] != op or manifest['runner'] != binding(Path(__file__)):
        raise ValueError('Operation or reviewed runner differs')
    if manifest['core_source'] != source():
        raise ValueError('Core differs from the reviewed qualified source')
    for item in manifest['inputs']:
        if binding(ROOT/item['path']) != item:
            raise ValueError('Reviewed input changed: '+item['path'])
    if shutil.disk_usage(ROOT).free < 4*1024**3:
        raise ValueError('Insufficient disk headroom')
    with (BASE/'operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if op == 'joint' and any(BASE.glob('*-joint-*/fits/*/fit-result.json')):
            raise ValueError('Joint work exists; inspect/replay it, never repeat consumed fits')
        if op in ('learner', 'joint', 'hardware'):
            for old in BASE.glob('*-'+op+'-*/receipt.json'):
                if json.loads(old.read_text()).get('passed'):
                    raise ValueError('Successful allocation exists; automatic repetition refused')
        out = BASE/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+op+'-'+uuid4().hex[:8])
        out.mkdir()
        shutil.copyfile(manifest_path, out/'manifest.json')
        for item in [manifest['runner'], *manifest['inputs']]:
            dest = out/'inputs'/item['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/item['path'], dest)
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='0,1' if op == 'hardware' else '',
                   PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
                   RLLIB_TEST_NO_TF_IMPORT='1', RLLIB_TEST_NO_JAX_IMPORT='1',
                   RAY_DEDUP_LOGS='1', MPLBACKEND='Agg')
        env['PYTHONPATH'] = os.pathsep.join(str(p) for p in (
            ROOT/'.hponas-runtime/rl-lqr-deps', EXT, ROOT/'.hponas-runtime/spec-deps',
            ROOT/'.hponas-runtime/postgres-deps', ROOT))
        env['HPO_LQR_OUTPUT'] = str(out)
        os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[-4:]))
        command = [PYTHON, str(EXT/'run_operation.py'), op, str(out)]
        receipt = {'kind': 'rl_lqr_operation_v1', 'operation': op, 'stage': work+'/'+stage,
                   'passed': False, 'manifest': binding(manifest_path), 'core_source': source(),
                   'limits': {'seconds': seconds, 'cpu_cores': 4, 'gpus': 2 if op == 'hardware' else 0,
                              'host_rss_bytes': 16*1024**3, 'output_bytes': 2*1024**3},
                   'directory': str(out.relative_to(ROOT))}
        write(out/'intent.json', receipt)
        start = time.monotonic()
        reason = None
        peak = 0
        with (out/'execution.log').open('x') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            table = process_table()
            owned = {child.pid: table[child.pid][1]} if child.pid in table else {}
            write(out/'process.json', {'pid': child.pid, 'command': command, 'started': time.time()})
            while child.poll() is None:
                live = tracked(owned)
                rss = sum(r[3] for r in live.values())
                peak = max(peak, rss)
                elapsed = time.monotonic()-start
                size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
                write(out/'progress.json', {'seconds': elapsed, 'owned_pids': sorted(live),
                                            'rss_bytes': rss, 'peak_rss_bytes': peak, 'bytes': size})
                if elapsed > seconds:
                    reason = 'wall_time_limit'
                elif rss > receipt['limits']['host_rss_bytes']:
                    reason = 'owned_rss_limit'
                elif size > receipt['limits']['output_bytes']:
                    reason = 'output_size_limit'
                elif shutil.disk_usage(ROOT).free < 4*1024**3:
                    reason = 'disk_floor'
                if reason:
                    for pid in live:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    for pid in tracked(owned):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    break
                time.sleep(.5)
            code = child.wait()
        survivors = tracked(owned)
        for pid in survivors:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        same = all(binding(ROOT/r['path']) == r for r in [manifest['runner'], *manifest['inputs']])
        receipt.update(returncode=code, stop_reason=reason, seconds=time.monotonic()-start,
                       peak_rss_bytes=peak, remaining_children=sorted(survivors), inputs_unchanged=same,
                       end_core_source=source(), log=binding(out/'execution.log'))
        receipt['passed'] = (code == 0 and reason is None and not survivors and same
                             and receipt['end_core_source'] == receipt['core_source'])
        write(out/'receipt.json', receipt)
        print(json.dumps(receipt, indent=2))
        return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
