"""Implementation of the fixed RL-LQR-01 operation roster."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def runtime(out):
    overlay = ROOT/'.hponas-runtime/rl-lqr-deps'
    if overlay.exists():
        raise ValueError('Runtime overlay already exists; inspect rather than overwrite')
    wheels = out/'wheels'
    wheels.mkdir()
    packages = ['gymnasium==1.2.2', 'farama-notifications==0.0.4', 'lz4>=4.3,<5', 'ormsgpack>=1.7,<2']
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
                    '--only-binary=:all:', '--no-deps', '--dest', str(wheels), *packages],
                   check=True, timeout=180)
    artifacts = sorted(wheels.glob('*.whl'))
    if len(artifacts) != 4 or sum(p.stat().st_size for p in artifacts) > 250*1024**2:
        raise ValueError('Wheel roster/size differs from allocation')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-index', '--no-deps', '--target', str(overlay),
                    *map(str, artifacts)], check=True, timeout=120)
    script = ('import ray, torch, gymnasium, lz4, ormsgpack; '
              'from ray.rllib.algorithms.sac import SACConfig; '
              'from ray.rllib.algorithms.ppo import PPOConfig; '
              'print("RLlib SAC/PPO imports verified", ray.__version__, torch.__version__)')
    subprocess.run([sys.executable, '-c', script], check=True, timeout=120)
    packages = ('ray', 'torch', 'numpy', 'scipy', 'gymnasium', 'farama-notifications', 'lz4', 'ormsgpack')
    # The process started before the overlay existed; refresh import metadata's search path.
    sys.path.insert(0, str(overlay))
    lock = {'versions': {name: importlib.metadata.version(name) for name in packages},
            'overlay': str(overlay.relative_to(ROOT)),
            'wheels': [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in artifacts],
            'files': {str(p.relative_to(overlay)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(overlay.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}}
    write(out/'runtime-lock.json', lock)
    print(json.dumps({'runtime_ready': True, 'versions': lock['versions']}))


def main():
    if len(sys.argv) != 3:
        raise ValueError('Fixed operation and owned output directory required')
    op, out = sys.argv[1], Path(sys.argv[2])
    if not out.resolve().is_relative_to(ROOT/'docs/program/evidence/2026-10-27/rl-lqr-01'):
        raise ValueError('Output must be inside the owned evidence directory')
    if op != 'runtime':
        lock = json.loads((ROOT/'extensions/rl-lqr/runtime-lock.json').read_text())
        for name, expected in lock['versions'].items():
            if importlib.metadata.version(name) != expected:
                raise ValueError('Runtime version changed: '+name)
        overlay = ROOT/lock['overlay']
        for name, expected in lock['files'].items():
            if hashlib.sha256((overlay/name).read_bytes()).hexdigest() != expected:
                raise ValueError('Runtime overlay bytes changed: '+name)
    if op == 'runtime':
        runtime(out)
    elif op == 'oracle':
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                        '--junitxml='+str(out/'tests.xml'),
                        str(ROOT/'extensions/rl-lqr/tests/test_reference.py')],
                       check=True, timeout=270)
        from hponas_rl_lqr.reference import oracle_report
        write(out/'oracle.json', oracle_report())
        print(json.dumps(oracle_report(), indent=2))
    elif op in ('learner', 'joint', 'hardware', 'joint-replay'):
        if op == 'learner':
            subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                            '--junitxml='+str(out/'tests.xml'),
                            str(ROOT/'extensions/rl-lqr/tests/test_learner_contract.py')],
                           check=True, timeout=180)
        from hponas_rl_lqr.experiment import execute
        execute(op, out)
    elif op == 'build':
        from hponas_rl_lqr.delivery import build
        build(out)
    elif op == 'audit':
        from hponas_rl_lqr.delivery import audit
        audit(out)
    elif op == 'master-audit':
        from hponas_rl_lqr.delivery import master_audit
        master_audit(out)
    else:
        raise ValueError('Operation implementation not yet reviewed: '+op)


if __name__ == '__main__':
    main()
