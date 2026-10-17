"""Identity-bound process guard whose cleanup does not depend on free storage.

Run with /usr/bin/python3. The old guard is immutable; only its reviewed
identity/handshake helpers are reused. Emergency slots contain valid pending
JSON until finalized; missing, pending or damaged receipts cannot pass.
"""
import argparse
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path("/home/ubuntu/workspace/hponas")
OLD = ROOT / 'docs/program/evidence/2026-10-06/stylized-refresh-repair-01/guarded_process.py'
spec = importlib.util.spec_from_file_location('prior_guard', OLD)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
guard = prior.guard
read, identity, alive = prior.read, prior.identity, prior.alive
SLOT_BYTES = 1024 * 1024
RESERVE_BYTES = 4 * 1024 * 1024
DEFAULT_STORAGE = dict(preflight_free_gib=32, stop_below_free_gib=16)


def verify_host_identity(plan):
    if (plan['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            or plan['pid_namespace'] != os.readlink('/proc/self/ns/pid')):
        raise ValueError('Guard boot or PID namespace differs from launch')


def preallocate(path, size, payload=None):
    with path.open('xb', buffering=0) as handle:
        os.posix_fallocate(handle.fileno(), 0, size)
        if payload is not None:
            raw = json.dumps(payload).encode()
            handle.write(raw + b' ' * (size - len(raw) - 1) + b'\n')
        os.fsync(handle.fileno())


def slot(path, payload):
    """Overwrite already allocated blocks; no new file or directory is needed."""
    raw = json.dumps(payload, allow_nan=False).encode()
    if len(raw) >= SLOT_BYTES:
        raise ValueError('Emergency receipt exceeds its reserved capacity')
    with path.open('r+b', buffering=0) as handle:
        handle.write(raw + b' ' * (SLOT_BYTES - len(raw) - 1) + b'\n')
        os.fsync(handle.fileno())


def release_reserve(path):
    # Only this invocation's explicitly allocated scratch reserve is truncated.
    # Evidence slots and all scientific outputs are preserved.
    try:
        with path.open('r+b') as handle:
            handle.truncate(0)
            os.fsync(handle.fileno())
    except OSError:
        pass


def free_gib(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize / 2**30


def inventory(plan, root, tracked):
    """Keep descendants through reparenting, with exact PID/start-time checks."""
    rows = guard.process_table()
    found = guard.owned(rows, identity(root))
    # The supervisor is a subreaper and spawns only the root and this monitor.
    # Thus even a short-lived intermediate cannot orphan an unobserved worker.
    supervisor = rows.get(plan['supervisor']['pid'])
    if supervisor and identity(supervisor) == identity(plan['supervisor']):
        for row in rows.values():
            if (row['parent'] == supervisor['pid']
                    and row['pid'] != plan.get('monitor_pid')):
                found.extend(guard.owned(rows, identity(row)))
    for item in found:
        tracked[identity(item)] = item
    return {key: rows[item['pid']] for key, item in tracked.items()
            if item['pid'] in rows and identity(rows[item['pid']]) == key
            and rows[item['pid']]['state'] != 'Z'}


def stop_owned(plan, root, tracked):
    """Stop exact owned processes before any evidence write is attempted."""
    handles, signals, errors = {}, [], []
    try:
        # Stop parents before expanding to quiesce forks, then stop descendants.
        for _ in range(5):
            tracked = inventory(plan, root, tracked)
            new = False
            for key, row in tracked.items():
                if key in handles:
                    continue
                fd = guard.verified_pidfd(row)
                if fd is not None:
                    handles[key] = (fd, row)
                    guard.signal_owned(fd, row, signal.SIGSTOP, signals)
                    new = True
            if not new:
                break
            time.sleep(.02)
        for fd, row in handles.values():
            guard.signal_owned(fd, row, signal.SIGTERM, signals)
            guard.signal_owned(fd, row, signal.SIGCONT, signals)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and any(guard.is_alive(fd) for fd, _ in handles.values()):
            time.sleep(.05)
        # Catch descendants spawned by graceful termination handlers as well.
        tracked = inventory(plan, root, tracked)
        for key, row in tracked.items():
            if key not in handles:
                fd = guard.verified_pidfd(row)
                if fd is not None:
                    handles[key] = (fd, row)
        for fd, row in handles.values():
            guard.signal_owned(fd, row, signal.SIGKILL, signals)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(guard.is_alive(fd) for fd, _ in handles.values()):
            time.sleep(.05)
        survivors = [row for fd, row in handles.values() if guard.is_alive(fd)]
    except BaseException as exc:
        errors.append(type(exc).__name__ + ': ' + str(exc))
        # Attempt every retained pidfd even if a preceding cleanup step failed.
        for fd, row in handles.values():
            try:
                guard.signal_owned(fd, row, signal.SIGKILL, signals)
            except OSError as error:
                errors.append(str(error))
        survivors = [row for fd, row in handles.values() if guard.is_alive(fd)]
    finally:
        for fd, _ in handles.values():
            os.close(fd)
    return dict(signals=signals, survivors=survivors, errors=errors)


def write_health(path, observation, fault):
    if fault == 'monitor_health_enospc':
        raise OSError(errno.ENOSPC, 'controlled monitor write failure')
    with path.open('a') as handle:
        handle.write(json.dumps(observation) + '\n')
        handle.flush()


def monitor_exited_while_active(child, monitor_child):
    # The command can exit between the loop's first poll and this monitor poll.
    # Reap/check it again before calling a clean monitor termination a failure.
    return monitor_child.poll() is not None and child.poll() is None


def monitor(plan, out):
    target = out / 'guard'
    started, last = time.monotonic(), -float('inf')
    root, tracked, cleanup = None, {}, None
    error, reason = None, None
    observation = None
    status = 'guard_failed'
    try:
        verify_host_identity(plan)
        root = prior.attach(plan, out)
        plan['monitor_pid'] = os.getpid()
        guard.write(target / 'start.json', dict(utc=guard.utc(), root=root,
                    plan=guard.bind(out / 'plan.json'), driver=guard.bind(Path(__file__))))
        while True:
            tracked = inventory(plan, root, tracked)
            if not tracked:
                status = 'root_and_owned_processes_exited'
                break
            mem = {line.split(':')[0]: int(line.split()[1])
                   for line in Path('/proc/meminfo').read_text().splitlines()}
            available = mem['MemAvailable'] / 2**20
            disk = free_gib(out)
            if plan.get('control_fault') == 'low_disk_after_launch' and (out / 'permit.json').exists():
                disk = 0
            reason = guard.decision(plan, list(tracked.values()), available)
            if disk < plan['storage_policy']['stop_below_free_gib']:
                reason = 'filesystem_headroom_exhausted'
            if not alive(plan['supervisor']):
                reason = 'supervisor_exited'
            if time.monotonic() - started > plan['maximum_monitor_seconds']:
                reason = 'registered_process_deadline_exceeded'
            if not alive(root):
                # Root exit can occur after the first process-table read.
                # Refresh exact owned identities before classifying a leak.
                tracked = inventory(plan, root, tracked)
                if not tracked and reason is None:
                    status = 'root_and_owned_processes_exited'
                    break
                if tracked and reason is None:
                    reason = 'owned_descendants_outlived_root'
            observation = dict(utc=guard.utc(), reason=reason, available_gib=available,
                free_disk_gib=disk, owned_rss_gib=sum(r['rss_kib'] for r in tracked.values()) / 2**20,
                processes=list(tracked.values()))
            if reason:
                break
            if (plan.get('control_fault') == 'monitor_health_enospc'
                    and (out / 'permit.json').exists() and time.monotonic() - started >= 2):
                write_health(target / 'health.jsonl', observation, 'monitor_health_enospc')
            if time.monotonic() - last >= plan['health_record_seconds']:
                write_health(target / 'health.jsonl', observation, None)
                last = time.monotonic()
            time.sleep(plan['poll_seconds'])
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        reason = 'guard_error'
    finally:
        if reason:
            status = 'interrupted_for_resource_or_supervisor_failure'
            if root is not None:
                cleanup = stop_owned(plan, root, tracked)
        release_reserve(target / 'emergency.reserve')
        receipt = dict(utc=guard.utc(), status=status, error=error, reason=reason,
            elapsed_seconds=time.monotonic() - started, intervened=bool(reason),
            cleanup=cleanup, terminal_observation=observation, scientific_acceptance=False)
        slot(target / 'receipt.json', receipt)
    return int(status != 'root_and_owned_processes_exited' or bool(error))


def run(command, out, maximum, environment, source, *, memory_gib=64, observe=None,
        storage_policy=None, control_fault=None):
    """A failed write, guard or terminal receipt always prevents acceptance."""
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise ValueError('Use /usr/bin/python3 for identity-safe signaling')
    if control_fault not in {None, 'monitor_health_enospc', 'low_disk_after_launch'}:
        raise ValueError('Unknown bounded control')
    out = Path(out).resolve()
    out.mkdir(exist_ok=False)
    (out / 'guard').mkdir()
    policy = dict(DEFAULT_STORAGE if storage_policy is None else storage_policy)
    assert policy['preflight_free_gib'] > policy['stop_below_free_gib'] >= 0
    gate_command = ['/usr/bin/python3', str(Path(__file__).resolve()), 'gate', str(out)]
    host_identity = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        pid_namespace=os.readlink('/proc/self/ns/pid'))
    plan = dict(command=command, gate_command=gate_command, source_digest=source,
        **host_identity,
        supervisor=guard.record(os.getpid()), maximum_monitor_seconds=maximum,
        poll_seconds=1, health_record_seconds=30, stop_if_owned_rss_gib_exceeds=memory_gib,
        stop_if_host_available_gib_below=16, low_available_requires_owned_rss_gib_at_least=8,
        storage_policy=policy, control_fault=control_fault, no_retry=True,
        scientific_acceptance=False, implementation=guard.bind(Path(__file__)),
        identity_helpers=guard.bind(OLD), signals=guard.bind(prior.ORIGINAL))
    guard.write(out / 'plan.json', plan)
    guard.write(out / 'start.json', dict(**host_identity, process=plan['supervisor'],
        utc=guard.utc(), implementation=guard.bind(Path(__file__))))
    started = time.monotonic()
    child = monitor_child = root = None
    error, terminal, cleanup = None, None, None
    tracked = {}
    for directory in [out, out / 'guard']:
        preallocate(directory / 'receipt.json', SLOT_BYTES, dict(status='pending', passed=False))
        preallocate(directory / 'emergency.reserve', RESERVE_BYTES)
    try:
        disk = free_gib(out)
        guard.write(out / 'storage-preflight.json', dict(free_disk_gib=disk, policy=policy))
        if disk < policy['preflight_free_gib']:
            raise RuntimeError('Insufficient filesystem headroom for prospective allocation')
        # Linux adopts orphaned descendants here; the independent monitor can
        # identify every adopted direct child except itself from the plan.
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot enable owned-process subreaping')
        with (out / 'command.log').open('x') as log, (out / 'monitor.log').open('x') as monitor_log:
            child = subprocess.Popen(gate_command, cwd=ROOT, env=environment,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            root = guard.record(child.pid)
            prior.wait_file(out / 'ready.json', child)
            root = read(out / 'ready.json')
            monitor_child = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).resolve()), 'monitor', str(out)],
                cwd=ROOT, stdout=monitor_log, stderr=subprocess.STDOUT)
            plan['monitor_pid'] = monitor_child.pid
            guard.write(out / 'monitor-process.json', guard.record(monitor_child.pid))
            prior.wait_file(out / 'guard/start.json', monitor_child)
            attached = read(out / 'guard/start.json')
            if attached['root'] != root or monitor_child.poll() is not None:
                raise ValueError('Guard did not attach to exact live root')
            guard.write(out / 'permit.json', dict(root=root, plan=guard.bind(out / 'plan.json')))
            last = -float('inf')
            while child.poll() is None:
                tracked = inventory(plan, root, tracked)
                if monitor_exited_while_active(child, monitor_child):
                    raise RuntimeError('Independent guard exited while command was active')
                if time.monotonic() - started > maximum + 10:
                    raise TimeoutError('Independent guard did not enforce deadline')
                if observe is not None and time.monotonic() - last >= 30:
                    observe(child, out / 'command.log', started)
                    last = time.monotonic()
                time.sleep(.2)
            monitor_child.wait(timeout=15)
            terminal = read(out / 'guard/receipt.json')
            if (monitor_child.returncode or terminal.get('error') or terminal.get('intervened')
                    or terminal.get('status') != 'root_and_owned_processes_exited'):
                raise RuntimeError('Guard refused uninterrupted completion')
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        # Neither a full filesystem nor a broken logging hook can bypass this.
        if root is not None:
            cleanup = stop_owned(plan, root, tracked)
        if child is not None:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                error += '; child failed to exit after cleanup'
    finally:
        if monitor_child is not None and monitor_child.poll() is None:
            try:
                monitor_child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor_child.kill()  # exact unreaped child, never a reused PID
                monitor_child.wait(timeout=5)
        release_reserve(out / 'emergency.reserve')
    receipt = dict(utc=guard.utc(), command=command, source_digest=source,
        returncode=child.returncode if child else None, error=error,
        elapsed_seconds=time.monotonic() - started, terminal_guard=terminal,
        guard=guard.bind(out / 'guard/receipt.json'), cleanup=cleanup,
        completed_without_intervention=error is None,
        passed=error is None and child is not None and child.returncode == 0,
        no_retry=True, storage_policy=policy)
    slot(out / 'receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['gate', 'monitor'])
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    config = read(args.output / 'plan.json')
    if args.mode == 'gate':
        prior.gate(config, args.output)
    else:
        raise SystemExit(monitor(config, args.output))
