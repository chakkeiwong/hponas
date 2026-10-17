#!/usr/bin/python3 -I
"""Verify a dedicated candidate with Codex's installed argv rule evaluator."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = Path('/home/ubuntu/workspace/hponas/program_operations')
HELPER = str(BASE / 'hponas_ops.py')
INSTALLER = str(BASE / 'install_approval_rules.py')
CANDIDATE = BASE / 'hponas-program.rules'
DESTINATION = Path('/home/ubuntu/.codex/rules/hponas-program.rules')
CODEX = '/home/ubuntu/.nvm/versions/node/v24.19.0/bin/codex'
NODE = '/home/ubuntu/.nvm/versions/node/v24.19.0/bin/node'
OPERATIONS = ('status', 'checks', 'test-study', 'test-search', 'test-store', 'test-schedulers',
              'check-rules', 'test-operations')


def cases():
    result = []
    for argv in [[HELPER, op] for op in OPERATIONS] + [[INSTALLER]]:
        result.append((argv, True))
        for flag in ('-c', '-lc'):
            result.append((['/bin/bash', flag, ' '.join(argv)], True))
    result.extend((argv, False) for argv in [
        ['python', '-c', 'print(1)'], ['/usr/bin/python3', '-c', 'print(1)'],
        ['/bin/bash', '-c', 'echo unrelated'], ['git', 'push'],
        [HELPER, 'execute-python', 'arbitrary.py'], [HELPER, 'run-campaign'],
        [HELPER, 'test-everything'], [HELPER],
        ['/bin/bash', '-c', HELPER + ' checks; git push'],
        ['/bin/bash', '-lc', INSTALLER + '; git push'],
        ['/bin/bash', '-c', 'env EXTRA=1 ' + HELPER + ' checks'],
        ['/usr/bin/env', 'EXTRA=1', HELPER, 'checks'],
        ['/usr/bin/python3', HELPER, 'checks'],
    ])
    return result


def check(rules=CANDIDATE):
    before = rules.read_bytes()
    rows = []
    for argv, expected in cases():
        result = subprocess.run([NODE, CODEX, 'execpolicy', 'check', '--rules', str(rules), '--', *argv],
                                cwd=BASE.parent, capture_output=True, text=True, timeout=15, check=True)
        evaluated = json.loads(result.stdout)
        allowed = evaluated.get('decision') == 'allow'
        if allowed != expected:
            raise ValueError(f'Rule match differs for {argv}: {evaluated}')
        rows.append({'argv': argv, 'expected_allow': expected, 'result': evaluated})
    if rules.read_bytes() != before:
        raise ValueError('Rules changed during verification')
    return {'passed': True, 'rules': str(rules), 'sha256': hashlib.sha256(before).hexdigest(),
            'cases': rows, 'host_live_reload_verified': False,
            'scope': 'Dedicated file only; existing global rules and managed approval controls remain authoritative.'}


def main():
    if len(sys.argv) != 1:
        print('This checker accepts no arguments.', file=sys.stderr)
        return 2
    result = check()
    result['installed_bytes_match'] = DESTINATION.is_file() and DESTINATION.read_bytes() == CANDIDATE.read_bytes()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
