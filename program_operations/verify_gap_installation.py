"""Fixed offline wheel/caller verification, invoked only by gap_ops test-adapters.

No arbitrary commands, paths or interpreter arguments are accepted by the CLI.
All children inherit the parent operation's process group and CPU affinity.
"""
from pathlib import Path
import base64
import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path('/home/ubuntu/workspace/hponas')
RUNTIMES = ('py312', 'py313')
TOTAL_SECONDS = 270
PROCESS_SECONDS = 60
BUILD_DISTRIBUTIONS = ('setuptools-84.0.0.dist-info', 'wheel-0.45.1.dist-info')


def parse_args(args):
    if args:
        raise ValueError('This fixed installation helper accepts no arguments')


def operation_directory(value):
    path = Path(value)
    if (path.parent != ROOT / 'docs/program/operations-runs'
            or path.resolve() != path or not path.is_dir()):
        raise ValueError('The fixed runner must supply its own output directory')
    return path


def binding(path):
    return {'path': str(path.relative_to(ROOT)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def stage_build_prerequisites(retained, destination):
    """Copy the two retained, RECORD-verified build tools into a fresh venv."""
    retained, destination = Path(retained), Path(destination)
    if retained.is_symlink() or retained.resolve() != retained:
        raise ValueError('Build prerequisites must be a real retained directory')
    records = {}
    for distribution in BUILD_DISTRIBUTIONS:
        record = retained / distribution / 'RECORD'
        with record.open(newline='') as stream:
            for name, digest, size in csv.reader(stream):
                relative = Path(name)
                path = retained / relative
                if (relative.is_absolute() or '..' in relative.parts
                        or path.resolve() != path or not path.is_file()):
                    raise ValueError('Unsafe or missing retained build file: ' + name)
                data = path.read_bytes()
                if digest:
                    algorithm, expected = digest.split('=', 1)
                    if algorithm != 'sha256':
                        raise ValueError('Unexpected retained build digest: ' + name)
                    actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                    if actual != expected or size != str(len(data)):
                        raise ValueError('Retained build file integrity failed: ' + name)
                elif path != record or size:
                    raise ValueError('Unhashed retained build file: ' + name)
                if name in records:
                    raise ValueError('Duplicate retained build file: ' + name)
                records[name] = hashlib.sha256(data).hexdigest()
    actual = {str(p.relative_to(retained)) for p in retained.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts}
    auxiliary = []
    lock = retained / '.lock'
    if lock.exists():
        if lock.resolve() != lock or not lock.is_file():
            raise ValueError('Unsafe retained build lock')
        auxiliary.append({'path': '.lock', 'sha256': hashlib.sha256(lock.read_bytes()).hexdigest()})
        actual.discard('.lock')
    if set(records) != actual:
        raise ValueError('Retained build inventory differs from RECORD files')
    copied = []
    for name, digest in sorted(records.items()):
        # Generated launchers use their old interpreter; backend imports need
        # only the verified package and metadata, never these bin scripts.
        if Path(name).parts[0] == 'bin':
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write((retained / name).read_bytes())
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Build prerequisite copy changed: ' + name)
        copied.append({'path': name, 'sha256': digest})
    return {'distributions': list(BUILD_DISTRIBUTIONS), 'retained_directory': str(retained),
            'retained_files': [{'path': n, 'sha256': h} for n, h in sorted(records.items())],
            'copied_files': copied, 'nonimported_auxiliary_files': auxiliary}


class BoundedRun:
    """Serial logged steps with a shared deadline and owned-descendant cleanup."""

    def __init__(self, out, outside, env, *, seconds=TOTAL_SECONDS):
        import psutil
        self.psutil = psutil
        self.out, self.outside, self.env = out, outside, env
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.steps, self.owned = [], {}

    def check_time(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Installation exceeded its fixed total deadline')

    def remember(self):
        for process in self.psutil.Process().children(recursive=True):
            try:
                self.owned[(process.pid, process.create_time())] = process
            except self.psutil.NoSuchProcess:
                pass

    def cleanup(self):
        self.remember()
        living = []
        for process in self.owned.values():
            try:
                if process.is_running() and process.status() != self.psutil.STATUS_ZOMBIE:
                    living.append(process)
                    process.terminate()
            except self.psutil.NoSuchProcess:
                pass
        _, remaining = self.psutil.wait_procs(living, timeout=2)
        for process in remaining:
            try:
                process.kill()
            except self.psutil.NoSuchProcess:
                pass
        self.psutil.wait_procs(remaining, timeout=2)
        leftovers = []
        for process in self.owned.values():
            try:
                if process.is_running() and process.status() != self.psutil.STATUS_ZOMBIE:
                    leftovers.append(process.pid)
            except self.psutil.NoSuchProcess:
                pass
        return leftovers

    def run(self, label, command, *, seconds=PROCESS_SECONDS):
        self.check_time()
        began = time.monotonic()
        code, failure = None, None
        log_path = self.out / (label + '.log')
        stderr_path = self.out / (label + '.stderr.log')
        child = None
        try:
            with log_path.open('x') as log, stderr_path.open('x') as errors:
                # Inherit the operation group: the outer timeout can retire
                # this helper AND uv/build/Python descendants together.
                child = subprocess.Popen(list(map(str, command)), cwd=self.outside,
                                         env=self.env, stdout=log, stderr=errors)
                limit = min(self.deadline, began + seconds)
                while True:
                    self.remember()
                    if time.monotonic() >= limit:
                        raise TimeoutError(label + ' exceeded its fixed deadline')
                    try:
                        code = child.wait(timeout=min(.2, max(.001, limit - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        pass
            if code:
                raise RuntimeError(label + ' failed with code ' + str(code))
        except BaseException as exc:
            failure = type(exc).__name__ + ': ' + str(exc)
            self.cleanup()
            if child is not None:
                child.wait(timeout=3)
            raise
        finally:
            if child is not None:
                code = child.returncode
            self.steps.append({'step': label, 'command': list(map(str, command)),
                               'returncode': code, 'failure': failure,
                               'elapsed_seconds': time.monotonic() - began,
                               'log': str(log_path), 'stderr': str(stderr_path)})
            print(json.dumps(self.steps[-1]), flush=True)


MANIFEST_CODE = """import importlib.metadata as m,json,sys
assert sys.version_info[:2] == tuple(map(int,sys.argv[1].split('.')))
print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()
                 if d.metadata['Name'].lower()!='hponas'},sort_keys=True))
"""

ORIGIN_CODE = """import importlib,json,pathlib,sys,zipfile
import hponas
root=pathlib.Path(hponas.__file__).resolve().parent.parent
assert root.is_relative_to(pathlib.Path(sys.prefix).resolve())
for name in ('evaluation_streaming','population_adapter','local_service','backup_security','rgpe','quickstart'):
    module=importlib.import_module('hponas.'+name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root)
with zipfile.ZipFile(sys.argv[1]) as wheel:
    files=[n for n in wheel.namelist() if n.split('/')[0] in ('hponas','workloads','tools','validation') and not n.endswith('/')]
    assert all((root/n).read_bytes()==wheel.read(n) for n in files)
assert not pathlib.Path.cwd().is_relative_to(pathlib.Path(sys.argv[2]).resolve())
print(json.dumps({'origin':str(root),'matched_files':len(files),'cwd':str(pathlib.Path.cwd())}))
"""


def main():
    try:
        parse_args(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parent = operation_directory(os.environ.get('HPONAS_OPERATION_DIRECTORY', ''))
    out = parent / 'installation'
    out.mkdir(mode=0o700, exist_ok=False)
    outside = Path(tempfile.mkdtemp(prefix='hponas-gap-wheel-'))
    assert not outside.is_relative_to(ROOT)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'LANG') if k in os.environ}
    env.update(PATH='/home/ubuntu/miniforge3/bin:/usr/bin:/bin',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1',
               PYTHONDONTWRITEBYTECODE='1', UV_OFFLINE='1',
               UV_CACHE_DIR=str(ROOT / '.hponas-runtime/uv-cache'))
    sys.path.insert(0, str(ROOT))
    from tools.source_identity import source_digest
    before = source_digest()
    runner = BoundedRun(out, outside, env)
    failure, leftovers, wheel_binding = None, [], None
    retained_manifests, examples, build_prerequisites = {}, [], None

    def interrupted(signum, frame):
        raise InterruptedError('Owned installation verification was interrupted')

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    try:
        source = out / 'source'
        source.mkdir()
        for folder in ('hponas', 'workloads', 'validation', 'tools', 'tests', 'examples', 'licenses'):
            shutil.copytree(ROOT / folder, source / folder, ignore=shutil.ignore_patterns(
                '__pycache__', '.pytest_cache', '.hypothesis', 'artifacts', 'results'))
            runner.check_time()
        for name in ('pyproject.toml', 'requirements.txt', 'README.md'):
            shutil.copyfile(ROOT / name, source / name)
        for license_file in ROOT.glob('LICENSE*'):
            if license_file.is_file():
                shutil.copyfile(license_file, source / license_file.name)
        assert source_digest(source) == before
        uv = ROOT / '.hponas-runtime/package-tools/bin/uv'
        build_environment = out / 'build-environment'
        runner.run('build-venv', [uv, 'venv', '--offline', '--python',
            ROOT / '.hponas-runtime/installation/py313/bin/python', build_environment])
        build_site, = (build_environment / 'lib').glob('python*/site-packages')
        build_prerequisites = stage_build_prerequisites(
            ROOT / '.hponas-runtime/build-prerequisites', build_site)
        runner.check_time()
        runner.run('build', [uv, 'build', '--offline', '--no-build-isolation', '--python',
            build_environment / 'bin/python', '--wheel', '--out-dir', out / 'wheel', source])
        wheel, = (out / 'wheel').glob('*.whl')
        wheel_binding = binding(wheel)
        with zipfile.ZipFile(wheel) as archive:
            files = {n for n in archive.namelist() if n.endswith('.py')}
            assert all(archive.read(n) == (source / n).read_bytes() for n in files)
            assert {'hponas/' + name + '.py' for name in (
                'evaluation_streaming', 'population_adapter', 'local_service',
                'backup_security', 'rgpe', 'quickstart')} <= files
        for runtime, version in zip(RUNTIMES, ('3.12', '3.13')):
            retained = ROOT / '.hponas-runtime/installation' / runtime
            venv = out / runtime
            runner.run(runtime + '-venv', [uv, 'venv', '--offline', '--python', retained / 'bin/python', venv])
            python = venv / 'bin/python'
            runner.run(runtime + '-manifest', [retained / 'bin/python', '-c', MANIFEST_CODE, version])
            expected = json.loads((out / (runtime + '-manifest.log')).read_text())
            assert 'cryptography' in {n.lower() for n in expected}
            retained_manifests[runtime] = expected
            constraints = out / (runtime + '-constraints.txt')
            constraints.write_text(''.join(n + '==' + v + '\n' for n, v in sorted(expected.items())
                                           if n.lower() not in ('hponas', 'brax')))
            old_site, = (retained / 'lib').glob('python*/site-packages')
            new_site, = (venv / 'lib').glob('python*/site-packages')

            def link_dependency(src, dst):
                runner.check_time()
                return os.link(src, dst)

            shutil.copytree(old_site, new_site, dirs_exist_ok=True, copy_function=link_dependency,
                ignore=shutil.ignore_patterns('__pycache__', '_virtualenv.py', '_virtualenv.pth',
                    'hponas', 'hponas-*.dist-info', 'workloads', 'validation', 'tools'))
            runner.run(runtime + '-install', [uv, 'pip', 'install', '--offline', '--python', python,
                '--find-links', ROOT / '.hponas-runtime/postgres-wheels',
                '--find-links', ROOT / '.hponas-runtime/wheelhouse', '--constraint', constraints,
                str(wheel) + '[validation,cmaes,postgres,security]'])
            runner.run(runtime + '-dependencies', [uv, 'pip', 'check', '--python', python])
            runner.run(runtime + '-origins', [python, '-c', ORIGIN_CODE, wheel, ROOT])
            for model in ('hinge', 'allocation'):
                directory = outside / (runtime + '-' + model)
                command = [python, '-m', 'hponas.quickstart', '--model', model, '--output', directory]
                runner.run(runtime + '-' + model, command)
                first = json.loads((out / (runtime + '-' + model + '.log')).read_text())
                assert first['evaluation'] == 'completed'
                assert abs(first['reference']['search_regret']) < 1e-12
                runner.run(runtime + '-' + model + '-resume', command + ['--resume'])
                resumed = json.loads((out / (runtime + '-' + model + '-resume.log')).read_text())
                assert first == resumed
                examples.append({'runtime': runtime, 'model': model,
                                 'outcome': first, 'completed_resume_unchanged': True})
            runner.run(runtime + '-base-api', [python, '-m', 'tools.check_installed', '--extras',
                                              '--output', out / (runtime + '-base-api.json')])
        assert before == source_digest()
        runner.check_time()
    except BaseException as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    finally:
        leftovers = runner.cleanup()
        after = source_digest()
        passed = failure is None and not leftovers and before == after
        steps = []
        for step in runner.steps:
            item = dict(step)
            for stream in ('log', 'stderr'):
                path = Path(item[stream])
                item[stream] = binding(path) if path.is_file() else {'path': str(path), 'missing': True}
            steps.append(item)
        receipt = {'kind': 'offline_gap_installation_v1', 'status': 'PASS' if passed else 'FAIL',
            'source_digest': before, 'end_source_digest': after, 'steps': steps, 'failure': failure,
            'elapsed_seconds': time.monotonic() - runner.started, 'offline': True,
            'scientific_acceptance': False, 'outside_directory': str(outside),
            'runtimes': list(RUNTIMES), 'retained_dependency_manifests': retained_manifests,
            'examples': examples, 'wheel': wheel_binding, 'leftover_owned_pids': leftovers,
            'build_prerequisites': build_prerequisites,
            'limits': {'total_seconds': TOTAL_SECONDS, 'seconds_per_process': PROCESS_SECONDS,
                       'cpu_count': 1, 'gpu': False, 'inherits_operation_process_group': True},
            'driver': binding(Path(__file__))}
        with (out / 'receipt.json').open('x') as output:
            json.dump(receipt, output, indent=2)
            output.write('\n')
        print(json.dumps({'status': receipt['status'], 'receipt': binding(out / 'receipt.json'),
                          'failure': failure}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
