#!/usr/bin/python3 -I
"""Install only the reviewed HPO-NAS rule file; no caller-supplied paths/commands."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

BASE = Path('/home/ubuntu/workspace/hponas/program_operations')
CANDIDATE = BASE / 'hponas-program.rules'
DESTINATION = Path('/home/ubuntu/.codex/rules/hponas-program.rules')
RECEIPTS = BASE.parent / 'docs/program/operations-runs'
EXPECTED_SHA256 = 'ae75b1cc31bd03227d002680fc2acf05bd5e43410f98d72be23aca570b3c0b48'
CHECKER_SHA256 = '86ce9e3e19d9392a6cfa0cfcabe710712ed435e32a901284b761b1f3c3811322'
HELPER_SHA256 = '08ffe178467ab6e77800939d16948e79ceb9451419bca2768af3650c666a965f'
SERVICES_SHA256 = '6f6da004422a7f29823c8914fda0c273154c9bf70a83f84f6b3aa65a0d1e8602'


def verified_payload():
    for path, expected in [(CANDIDATE, EXPECTED_SHA256),
                           (BASE / 'check_approval_rules.py', CHECKER_SHA256),
                           (BASE / 'hponas_ops.py', HELPER_SHA256),
                           (BASE / 'local_services.py', SERVICES_SHA256)]:
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Unreviewed installation input: ' + str(path))
    spec = importlib.util.spec_from_file_location('hponas_rule_check', BASE / 'check_approval_rules.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checked = checker.check()
    payload = CANDIDATE.read_bytes()
    if checked['sha256'] != EXPECTED_SHA256 or hashlib.sha256(payload).hexdigest() != EXPECTED_SHA256:
        raise ValueError('Candidate changed during verification')
    return payload, len(checked['cases'])


def write_pinned(payload, destination):
    """Atomic create/idempotent readback; refuse any different existing file."""
    if destination.is_symlink() or destination.parent.resolve() != destination.parent:
        raise ValueError('Destination must not contain symlinks')
    previous = destination.read_bytes() if destination.exists() else None
    if previous is not None and previous != payload:
        raise ValueError('Unreviewed predecessor: refusing replacement')
    if previous == payload:
        return 'already_installed'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.hponas-rules-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Link creation fails atomically if another process installed anything meanwhile.
        os.link(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if destination.read_bytes() != payload:
        raise ValueError('Installed readback differs')
    return 'installed'


def main():
    if len(sys.argv) != 1:
        print('This installer accepts no arguments.', file=sys.stderr)
        return 2
    payload, count = verified_payload()
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    with (RECEIPTS / '.rules-install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = write_pinned(payload, DESTINATION)
    receipt = {'status': status, 'destination': str(DESTINATION), 'sha256': EXPECTED_SHA256,
               'checker_sha256': CHECKER_SHA256, 'helper_sha256': HELPER_SHA256,
               'validated_cases': count, 'host_live_reload_verified': False,
               'default_rules_modified': False, 'sandbox_configuration_modified': False}
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-rules-install-' + uuid4().hex[:8] + '.json'
    output = RECEIPTS / name
    with output.open('x') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    print(json.dumps({**receipt, 'receipt': str(output.relative_to(BASE.parent))}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
