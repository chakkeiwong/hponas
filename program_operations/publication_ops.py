#!/usr/bin/python3 -I
"""Fixed zero-training checks for summary-only repository publication."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.argv[1:] != ['checks']:
        raise ValueError('Only the fixed checks operation is supported')
    roster = json.loads((ROOT / 'docs/lean-checks.json').read_text())
    out = ROOT / '.local-archives' / ('publication-checks-' +
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    out.mkdir(parents=True)
    env = dict(os.environ)
    env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
               CUDA_VISIBLE_DEVICES='', PYTHONPATH=str(ROOT))
    cpus = sorted(os.sched_getaffinity(0))[:roster['cpus']]
    if len(cpus) < roster['cpus']:
        raise ValueError('Two CPUs are required for the resource-partition test')
    os.sched_setaffinity(0, set(cpus))
    python = '/home/ubuntu/miniforge3/bin/python'
    commands = [[python, str(ROOT / 'program_operations/publication_guard.py')],
                [python, '-m', 'pytest', *roster['tests'], '-q', '-p', 'no:cacheprovider']]
    results = []
    for i, cmd in enumerate(commands):
        with (out / f'{i}.log').open('w') as log:
            try:
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=roster['timeout_seconds'])
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        results.append(dict(command=cmd, returncode=code))
        if code:
            break
    receipt = dict(passed=all(x['returncode'] == 0 for x in results),
                   new_training=0, scope=roster['scope'], checks=results)
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(passed=receipt['passed'], receipt=str(out / 'receipt.json'))))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
