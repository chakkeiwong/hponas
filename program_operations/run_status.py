"""Bounded read-only liveness evidence; file presence never proves a live run."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def host_identity():
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'pid_namespace': os.readlink('/proc/self/ns/pid')}


def process_identity(pid):
    try:
        # comm may contain spaces and parentheses; fields after its final ')'
        # start at field 3. Linux field 22 is the start tick on this boot.
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def last_health(path):
    """Read at most 64 KiB; no mutation/source/proof reconstruction on polling."""
    with path.open('rb') as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 65536))
        data = handle.read()
    if not data.strip() or not data.endswith(b'\n'):
        raise ValueError('Missing or incomplete heartbeat')
    return json.loads(data.splitlines()[-1])


def classify(start, health, terminal, *, now, current_host, process):
    result = {'running': False, 'scientific_acceptance': False}
    if terminal and terminal.get('status') != 'pending':
        status = terminal.get('status')
        if status == 'COMPLETE' or terminal.get('passed') is True:
            return dict(result, status='terminal_completion_recorded')
        return dict(result, status='terminal_failure_recorded')
    if not start:
        return dict(result, status='not_started_or_start_record_missing')
    if start.get('boot_id') and start['boot_id'] != current_host['boot_id']:
        return dict(result, status='interrupted_by_reboot')
    if not health:
        return dict(result, status='heartbeat_missing')
    try:
        age = (now - datetime.fromisoformat(health['utc'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return dict(result, status='heartbeat_unreadable')
    result['heartbeat_age_seconds'] = round(age, 1)
    if age < -5 or age > 90:
        return dict(result, status='heartbeat_stale_or_clock_changed')
    if health.get('reason'):
        return dict(result, status='guard_intervention', reason=health['reason'])
    if not start.get('boot_id') or not start.get('pid_namespace'):
        return dict(result, status='legacy_identity_unverified')
    if start['pid_namespace'] != current_host['pid_namespace']:
        return dict(result, status='process_namespace_not_visible')
    expected = start.get('process', {})
    actual = process(expected.get('pid')) if type(expected.get('pid')) is int else None
    ticks = expected.get('start_ticks', expected.get('starttime'))
    if not actual or actual.get('start_ticks') != ticks or actual.get('state') == 'Z':
        return dict(result, status='supervisor_not_live')
    return dict(result, status='live_observed', running=True)


def observe(directory):
    """Observe a registered controller or an exact guarded operation."""
    def read(path):
        return json.loads(path.read_text()) if path.is_file() else None
    try:
        start = read(directory/'start.json')
        health_path = directory/'guard/health.jsonl'
        # Serial controllers keep the heartbeat of their current guarded job.
        if not health_path.is_file():
            candidates = list(directory.glob('*/guard/health.jsonl'))
            health_path = max(candidates, key=lambda p:p.stat().st_mtime) if candidates else health_path
        health = last_health(health_path) if health_path.is_file() else None
        terminal = read(directory/'receipt.json')
        return classify(start,health,terminal,now=datetime.now(timezone.utc),
                        current_host=host_identity(),process=process_identity)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'running':False,'status':'evidence_unreadable',
                'error':type(exc).__name__+': '+str(exc),'scientific_acceptance':False}
