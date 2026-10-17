"""Fixed live-backend verification with owned processes and retained receipts.

Invoked by hponas_ops only. The modes never accept test paths, DSNs or commands.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path('/home/ubuntu/workspace/hponas')
ROSTERS = {
    'postgres': (
        'tests/integration/test_postgres_backend.py',
        'tests/integration/test_postgres_operations.py',
        'tests/integration/test_postgres_workers.py',
        'tests/integration/test_declared_postgres.py',
    ),
    'ray': ('tests/integration/test_ray_streaming.py', 'tests/integration/test_declared_ray.py'),
}


def mode_from_args(args):
    if len(args) != 1 or args[0] not in ROSTERS:
        raise ValueError('Pass exactly postgres or ray; no other arguments accepted')
    return args[0]


def test_counts(path):
    cases = ET.parse(path).getroot().findall('.//testcase')
    return {'tests': len(cases), **{kind: sum(c.find(kind) is not None for c in cases)
                                  for kind in ('skipped', 'failure', 'error')}}


def main():
    try:
        mode = mode_from_args(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parent = Path(os.environ.get('HPONAS_OPERATION_DIRECTORY', ''))
    if parent.parent != ROOT/'docs/program/operations-runs' or parent.resolve() != parent or not parent.is_dir():
        raise ValueError('The fixed runner must supply its own output directory')
    out = parent/('local-'+mode)
    out.mkdir(mode=0o700,exist_ok=False)
    import psutil
    import hponas  # Fail before startup if required package dependencies are absent.
    if mode == 'postgres':
        import psycopg
    import ray
    from tools.source_identity import source_digest

    before = source_digest()
    started = time.monotonic()
    deadline = started + 275
    owned = {}
    steps = []
    server = None
    server_log = None
    counts = None
    failure = None
    private = None
    cleanup = []

    def remember():
        for process in psutil.Process().children(recursive=True):
            try:
                owned[(process.pid,process.create_time())] = process
            except psutil.NoSuchProcess:
                pass

    def run(label, command, env, seconds):
        with (out/(label+'.log')).open('x') as log:
            process = subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            limit = min(deadline,time.monotonic()+seconds)
            while True:
                remember()
                if time.monotonic() >= limit:
                    raise TimeoutError(label+' exceeded its fixed deadline')
                try:
                    code = process.wait(timeout=min(.5,max(.01,limit-time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    continue
        steps.append({'label':label,'returncode':code})
        if code:
            raise RuntimeError(label+' failed with code '+str(code))

    def interrupted(signum, frame):
        raise InterruptedError('Owned live test was interrupted')

    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    env = dict(os.environ)
    try:
        if mode == 'postgres':
            pg = ROOT/'.hponas-runtime/postgresql/root'
            binary = pg/'usr/lib/postgresql/14/bin'
            env['LD_LIBRARY_PATH'] = str(pg/'usr/lib/x86_64-linux-gnu')
            private = Path(tempfile.mkdtemp(prefix='hponas-product-pg-'))
            data = private/'data'
            run('init',[str(binary/'initdb'),'-D',str(data),'-L',str(pg/'usr/share/postgresql/14'),
                        '--auth-local=peer','--auth-host=reject','--no-locale','--encoding=UTF8'],env,30)
            with (data/'postgresql.conf').open('a') as config:
                config.write("\nlisten_addresses=''\nunix_socket_directories='"+str(private)+
                             "'\nmax_connections=16\nshared_buffers='16MB'\n")
            server_log = (out/'server.log').open('x')
            server = subprocess.Popen([str(binary/'postgres'),'-D',str(data)],env=env,
                                      stdout=server_log,stderr=subprocess.STDOUT)
            env['HPONAS_TEST_POSTGRES_DSN'] = 'host='+str(private)+' dbname=postgres'
            ready_limit = time.monotonic()+25
            while True:
                remember()
                if server.poll() is not None:
                    raise RuntimeError('Owned PostgreSQL server exited during startup')
                try:
                    with psycopg.connect(env['HPONAS_TEST_POSTGRES_DSN'],connect_timeout=1):
                        break
                except psycopg.OperationalError:
                    if time.monotonic() >= ready_limit:
                        raise TimeoutError('Owned PostgreSQL server startup')
                    time.sleep(.2)
        run('tests',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                     *ROSTERS[mode],'--junitxml='+str(out/'tests.xml')],env,235)
        counts = test_counts(out/'tests.xml')
        if not counts['tests'] or any(counts[k] for k in ('skipped','failure','error')):
            raise RuntimeError('Live verification requires executed passing tests without skips')
    except BaseException as exc:
        failure = type(exc).__name__+': '+str(exc)
        if (out/'tests.xml').exists():
            counts = test_counts(out/'tests.xml')
    finally:
        remember()
        if server is not None and server.poll() is None:
            server.send_signal(signal.SIGINT)  # PostgreSQL fast, owned shutdown.
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=2)
        living = []
        for process in owned.values():
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    living.append(process)
                    process.terminate()
            except psutil.NoSuchProcess:
                pass
        _,remaining = psutil.wait_procs(living,timeout=3)
        for process in remaining:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(remaining,timeout=3)
        for process in owned.values():
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    cleanup.append(process.pid)
            except psutil.NoSuchProcess:
                pass
        if server_log is not None:
            server_log.close()
        after = source_digest()
        passed = failure is None and not cleanup and before == after
        receipt = {'kind':'fixed_local_service_verification_v1','mode':mode,'passed':passed,
                   'source_digest':before,'end_source_digest':after,'steps':steps,'counts':counts,
                   'elapsed_seconds':time.monotonic()-started,'failure':failure,
                   'owned_processes_seen':len(owned),'remaining_live_owned_pids':cleanup,
                   'private_directory':str(private) if private else None,
                   'cpu_affinity':sorted(os.sched_getaffinity(0)),'gpu':False,
                   'scientific_acceptance':False,'separate_machine_test':False,
                   'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt,indent=2),flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
