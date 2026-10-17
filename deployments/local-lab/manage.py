#!/usr/bin/env python3
"""Create and control the project's private, loopback-only PostgreSQL/Ray lab."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import configparser
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1]
PRIVATE = ROOT / '.hponas-runtime/deployments/local-lab'
INSTALL = ROOT / 'docs/program/evidence/2026-10-08/service-repair-01/integrated-repair-installation-01'
PYTHON = INSTALL / 'py313/bin/python'
PG = ROOT / '.hponas-runtime/postgresql/root'
BIN = PG / 'usr/lib/postgresql/14/bin'
DATA = PRIVATE / 'data'
SOURCE = 'bc131050672ad7a77e17535358400a22940ec35f09e54ab88f197242572d8c19'
DEADLINE = None


def write(path, value, *, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        if private:
            os.fchmod(handle.fileno(), 0o600)
        if isinstance(value, (dict, list)):
            json.dump(value, handle, indent=2)
            handle.write('\n')
        else:
            handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def identity(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def environment():
    env = dict(os.environ)
    for name in ['PYTHONPATH', 'PGHOST', 'PGPORT', 'PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE', 'RAY_ADDRESS']:
        env.pop(name, None)
    env.update(PYTHONPATH=str(INSTALL / 'outside-checkout'), PYTHONNOUSERSITE='1',
               PGSERVICEFILE=str(PRIVATE / 'pg_service.conf'),
               LD_LIBRARY_PATH=str(PG / 'usr/lib/x86_64-linux-gnu'),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='')
    return env


def run(command, log, *, limit=60, env=None):
    if DEADLINE is not None:
        limit = min(limit, DEADLINE - time.monotonic())
        if limit <= 0:
            raise TimeoutError('Deployment watchdog exhausted')
    with log.open('x') as output:
        process = subprocess.Popen(list(map(str, command)), cwd=LAB,
            env=environment() if env is None else env, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
    if code:
        raise RuntimeError('Owned command failed; see ' + str(log) + '; exit=' + str(code))


@contextmanager
def lifecycle():
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if PRIVATE.is_symlink() or PRIVATE.stat().st_uid != os.getuid():
        raise ValueError('Private deployment directory ownership differs')
    PRIVATE.chmod(0o700)
    with (PRIVATE / 'lifecycle.lock').open('a') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def verify_source():
    sys.path.insert(0, str(ROOT))
    from tools.source_identity import source_digest
    actual = source_digest()
    receipt = json.loads((INSTALL / 'receipt.json').read_text())
    if actual != SOURCE or receipt['source_digest'] != actual or receipt['status'] != 'PASS':
        raise ValueError('Source or installed package changed; refresh the deployment binding')
    return actual


def owner():
    record = json.loads((PRIVATE / 'owner.json').read_text())
    if (record['uid'] != os.getuid() or record['data_directory'] != str(DATA)
            or record['postgres_binary'] != str(BIN / 'postgres')):
        raise ValueError('Deployment owner record differs')
    return record


def active_pid():
    owner()
    path = DATA / 'postmaster.pid'
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    pid = int(lines[0])
    if lines[1] != str(DATA):
        raise ValueError('PostgreSQL data directory differs')
    proc = Path('/proc') / str(pid)
    if not proc.exists():
        raise ValueError('Stale PostgreSQL PID; inspect before recovery')
    args = (proc / 'cmdline').read_bytes().split(b'\0')
    if str(DATA).encode() not in args or (proc / 'exe').resolve() != (BIN / 'postgres').resolve():
        raise ValueError('PID no longer identifies our PostgreSQL server')
    return pid


def prepare(out):
    verify_source()
    if (PRIVATE / 'ready.json').exists():
        owner()
        return
    if DATA.exists() or (PRIVATE / 'owner.json').exists():
        raise ValueError('Partial setup retained; inspect it before retrying')
    sockdir = Path(tempfile.mkdtemp(prefix='hponas-local-lab-'))
    sockdir.chmod(0o700)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    credentials = {name: secrets.token_urlsafe(32) for name in ['runtime', 'monitor']}
    write(PRIVATE / 'credentials.json', credentials, private=True)
    write(PRIVATE / 'owner.json', dict(uid=os.getuid(), data_directory=str(DATA),
        postgres_binary=str(BIN / 'postgres'), socket_directory=str(sockdir), port=port,
        deployment_name='hponas-local-lab', source_digest=SOURCE), private=True)
    tls = PRIVATE / 'tls'
    tls.mkdir(mode=0o700)
    openssl = shutil.which('openssl')
    if not openssl:
        raise ValueError('openssl is required')
    run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30',
         '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
         '-keyout', tls / 'server.key', '-out', tls / 'server.crt'], out / 'certificate.log')
    (tls / 'server.key').chmod(0o600)
    run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '30',
         '-subj', '/CN=untrusted-local-test-ca', '-keyout', tls / 'wrong-ca.key',
         '-out', tls / 'wrong-ca.crt'], out / 'wrong-ca.log')
    (tls / 'wrong-ca.key').chmod(0o600)
    run([BIN / 'initdb', '-D', DATA, '-L', PG / 'usr/share/postgresql/14',
         '--auth-local=peer', '--auth-host=scram-sha-256', '--no-locale', '--encoding=UTF8'], out / 'init.log')
    with (DATA / 'postgresql.conf').open('a') as handle:
        handle.write("\nlisten_addresses='127.0.0.1'\nport=" + str(port) +
            "\nunix_socket_directories='" + str(sockdir) + "'\nmax_connections=16\nshared_buffers='16MB'\n" +
            "password_encryption='scram-sha-256'\nssl=on\nssl_cert_file='" + str(tls / 'server.crt') +
            "'\nssl_key_file='" + str(tls / 'server.key') + "'\n")
    (DATA / 'pg_hba.conf').write_text(
        'local all all peer\n'
        'hostssl postgres hponas_runtime,hponas_monitor 127.0.0.1/32 scram-sha-256\n'
        'host all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n')
    config = configparser.ConfigParser(interpolation=None)
    for role in ['runtime', 'monitor']:
        config['hponas_local_' + role] = dict(host='localhost', hostaddr='127.0.0.1',
            port=str(port), dbname='postgres', user='hponas_' + role,
            password=credentials[role], sslmode='verify-full', sslrootcert=str(tls / 'server.crt'),
            connect_timeout='5')
    config['hponas_local_maintenance'] = dict(host=str(sockdir), port=str(port), dbname='postgres',
        user=__import__('pwd').getpwuid(os.getuid()).pw_name, sslmode='disable', connect_timeout='5')
    with (PRIVATE / 'pg_service.conf').open('x') as handle:
        os.fchmod(handle.fileno(), 0o600)
        config.write(handle, space_around_delimiters=False)
    (PRIVATE / 'artifacts').mkdir(mode=0o700)
    profiles = {
        'postgres-runtime': dict(service='hponas_local_runtime', service_file=str(PRIVATE / 'pg_service.conf'), role='runtime'),
        'postgres-monitor': dict(service='hponas_local_monitor', service_file=str(PRIVATE / 'pg_service.conf'), role='monitor'),
        'postgres-maintenance': dict(service='hponas_local_maintenance', service_file=str(PRIVATE / 'pg_service.conf'), role='local_peer_owner'),
        'tls': dict(host='localhost', address='127.0.0.1', sslmode='verify-full', certificate=str(tls / 'server.crt')),
        'ray': dict(mode='owned_local_cluster_per_verification', address='127.0.0.1', cpus=2, object_store_bytes=104857600),
        'artifacts': dict(root=str(PRIVATE / 'artifacts'), immutable_publication='write_once_and_retained_sha256', shared_remote_storage=False),
        'hosts': dict(host=platform.node(), host_count=1, worker_processes=2, independent_hosts=False),
        'fault-cleanup': dict(scope='owned_postgresql_and_ray_only', stop='python deployments/local-lab/manage.py stop', remote_faults=False),
        'monitor': dict(command='python deployments/local-lab/manage.py status', notifications='local_output_only', unattended_alert_service=False),
        'retention': dict(policy='retain_evidence_and_private_database_until_explicit_user_cleanup', automatic_gc=False),
    }
    for name, value in profiles.items():
        write(LAB / 'profiles' / (name + '.json'), value)
    write(LAB / 'deployment.json', dict(deployment_name='hponas-local-lab',
        source_digest=SOURCE, installed_python=str(PYTHON), scope='trusted_single_host_development',
        operator='Current authorized execution session; no unattended operations',
        profiles={n: str(LAB / 'profiles' / (n + '.json')) for n in profiles},
        physical_hosts=1, distributed_service_accepted=False))
    write(PRIVATE / 'ready.json', dict(prepared=True, source_digest=SOURCE), private=True)


def start(out, label='start'):
    prepare(out)
    if active_pid() is None:
        run([BIN / 'pg_ctl', '-D', DATA, '-l', PRIVATE / 'server.log', '-w', '-t', '30', 'start'], out / (label + '.log'))
    if not (PRIVATE / 'roles-ready.json').exists():
        run([PYTHON, LAB / 'client.py', 'initialize', PRIVATE], out / 'roles.log')
        write(PRIVATE / 'roles-ready.json', dict(initialized=True), private=True)


def stop(out):
    if (PRIVATE / 'owner.json').exists() and active_pid() is not None:
        run([BIN / 'pg_ctl', '-D', DATA, '-m', 'fast', '-w', '-t', '20', 'stop'], out / 'stop.log', limit=30)


def main():
    global DEADLINE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'status', 'stop', 'verify'])
    parser.add_argument('--run-label')
    args = parser.parse_args()
    if args.run_label and (Path(args.run_label).name != args.run_label or args.run_label in ['.', '..']):
        parser.error('Simple run label required')
    os.umask(0o077)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    label = args.run_label or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = LAB / 'receipts' / label
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    DEADLINE = started + 260 if args.action == 'verify' else None
    status = 'FAIL'
    error = None
    owned_verification = False
    with lifecycle():
        try:
            if args.action in ['prepare', 'start', 'verify']:
                verify_source()
            if args.action in ['prepare', 'start', 'verify']:
                prepare(out)
            if args.action in ['start', 'verify']:
                if args.action == 'verify' and active_pid() is not None:
                    raise ValueError('Stop the existing lab before its destructive owned restart check')
                owned_verification = args.action == 'verify'
                start(out)
            if args.action == 'status':
                if not (PRIVATE / 'owner.json').exists() or active_pid() is None:
                    write(out / 'status.json', dict(status='stopped', deployment_name='hponas-local-lab'))
                else:
                    run([PYTHON, LAB / 'client.py', 'status', PRIVATE], out / 'status.log')
            if args.action == 'stop':
                stop(out)
            if args.action == 'verify':
                left = 300 - (time.monotonic() - started) - 35
                if left <= 0:
                    raise TimeoutError('Preparation exhausted the development watchdog')
                run([PYTHON, LAB / 'client.py', 'verify', PRIVATE, out], out / 'verify.log', limit=left)
                run([BIN / 'pg_ctl', '-D', DATA, '-m', 'immediate', '-w', '-t', '20', 'stop'], out / 'crash.log', limit=25)
                start(out, label='restart')
                run([PYTHON, LAB / 'client.py', 'reconstruct', PRIVATE, out], out / 'reconstruct.log', limit=25)
            status = 'PASS'
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        finally:
            if owned_verification:
                try:
                    DEADLINE = started + 292
                    stop(out)
                except Exception as exc:
                    status = 'FAIL'
                    error = 'Cleanup failure: ' + type(exc).__name__
            receipt = dict(action=args.action, status=status, source_digest=SOURCE,
                elapsed_seconds=time.monotonic() - started, output_directory=str(out),
                physical_hosts=1, scientific_campaigns=0, mutation_runs=0,
                distributed_service_accepted=False, error=error,
                scripts=[identity(Path(__file__)), identity(LAB / 'client.py')])
            write(out / 'receipt.json', receipt)
            print(json.dumps(receipt, indent=2))
    return int(status != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
