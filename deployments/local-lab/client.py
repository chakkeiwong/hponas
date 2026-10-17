"""Run against the verified installed wheel using private service profiles."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys

import psycopg
from psycopg import sql

from hponas.postgres import PostgresStore, PostgresWorkLedger, RecoveryRequired, initialize_postgres
from hponas.postgres_operations import backup_postgres, postgres_status, restore_postgres

RUNTIME = 'service=hponas_local_runtime'
MONITOR = 'service=hponas_local_monitor'
OWNER = 'service=hponas_local_maintenance'


def write(path, data):
    with path.open('x') as handle:
        json.dump(data, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def role_setup(private):
    secrets = json.loads((private / 'credentials.json').read_text())
    with psycopg.connect(OWNER, autocommit=True) as admin:
        for role in ['runtime', 'monitor']:
            admin.execute(sql.SQL(
                'CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}'
            ).format(sql.Identifier('hponas_' + role), sql.Literal(secrets[role])))
    print(json.dumps(dict(roles_created=['runtime', 'monitor'], passwords_logged=False)))


def grant(schema):
    with psycopg.connect(OWNER, autocommit=True) as admin:
        for role in ['hponas_runtime', 'hponas_monitor']:
            admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(role)))
            admin.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO hponas_runtime').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO hponas_runtime').format(sql.Identifier(schema)))
        admin.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE ON {}.identity FROM hponas_runtime').format(sql.Identifier(schema)))


def refused_connection(**kwargs):
    try:
        connection = psycopg.connect(RUNTIME, connect_timeout=3, **kwargs)
    except psycopg.OperationalError:
        return True
    else:
        connection.close()
        raise AssertionError('Invalid transport/authentication was accepted')


def verify(private, out):
    import ray
    import hponas
    import examples.postgres_known_answer as example

    root = Path(hponas.__file__).resolve().parent.parent
    if not root.is_relative_to(Path(sys.prefix).resolve()):
        raise AssertionError('Product loaded outside the installed environment')
    schema = 'lab_' + hashlib.sha256(str(out).encode()).hexdigest()[:12]
    initialize_postgres(OWNER, schema=schema)
    grant(schema)
    controls = {}
    with psycopg.connect(RUNTIME, autocommit=True) as connection:
        tls = connection.execute(
            'SELECT ssl,version,cipher FROM pg_stat_ssl WHERE pid=pg_backend_pid()'
        ).fetchone()
        assert tls[0]
        controls['verified_tls'] = dict(enabled=tls[0], version=tls[1], cipher=tls[2])
        try:
            connection.execute(sql.SQL('UPDATE {}.identity SET dispatch_enabled=FALSE').format(sql.Identifier(schema)))
        except psycopg.errors.InsufficientPrivilege:
            controls['runtime_identity_write_refused'] = True
        else:
            raise AssertionError('Runtime can modify identity')
        try:
            connection.execute(sql.SQL('CREATE TABLE {}.forbidden(x INTEGER)').format(sql.Identifier(schema)))
        except psycopg.errors.InsufficientPrivilege:
            controls['runtime_schema_write_refused'] = True
        else:
            raise AssertionError('Runtime can create schema objects')
    controls['wrong_hostname_refused'] = refused_connection(host='incorrect.local')
    controls['untrusted_certificate_refused'] = refused_connection(sslrootcert=str(private / 'tls/wrong-ca.crt'))
    controls['plaintext_refused'] = refused_connection(sslmode='disable')
    controls['wrong_password_refused'] = refused_connection(password='intentionally-invalid')
    with psycopg.connect(MONITOR, autocommit=True) as connection:
        try:
            connection.execute(sql.SQL('DELETE FROM {}.trials').format(sql.Identifier(schema)))
        except psycopg.errors.InsufficientPrivilege:
            controls['monitor_write_refused'] = True
        else:
            raise AssertionError('Monitor can modify trials')

    # Never join or shut down an unrelated cluster. Ray's loopback binding and
    # exact two-CPU resources are explicit for this finite local envelope.
    assert not ray.is_initialized()
    ray.cloudpickle.register_pickle_by_value(example)
    artifact_dir = private / 'artifacts' / out.name
    try:
        ray.init(address='local', num_cpus=2, include_dashboard=False,
                 object_store_memory=100 * 1024 * 1024, _node_ip_address='127.0.0.1')
        resources = ray.cluster_resources()
        assert resources['CPU'] == 2
        nodes = [dict(node_id=node['NodeID'], address=node['NodeManagerAddress'])
                 for node in ray.nodes() if node['Alive']]
        result = example.run(RUNTIME, schema, artifact_dir, use_ray=True)
    finally:
        ray.shutdown()
    assert result['gradient_updates'] == 24 and result['passed']
    original = postgres_status(MONITOR, schema=schema)
    assert original['status'] == 'ok'
    trials = sorted(artifact_dir.glob('*.jsonl'))
    assert len(trials) == 6
    with PostgresStore(RUNTIME, schema=schema) as store:
        for trace in trials:
            store.write_artifact(trace.stem, 'training_trace', str(trace),
                                 {'sha256': hashlib.sha256(trace.read_bytes()).hexdigest()})
    receipt = backup_postgres(OWNER, out / 'backup', schema=schema,
                              artifact_root=private / 'artifacts')
    restored_schema = schema + '_restored'
    restored = restore_postgres(OWNER, out / 'backup', schema=restored_schema,
                                expected_sha256=receipt['sha256'], max_bytes=receipt['total_bytes'])
    assert restored['dispatch_enabled'] is False
    grant(restored_schema)
    study_id = 'quadratic-' + out.name
    with PostgresWorkLedger(RUNTIME, schema=restored_schema,
            allocation=study_id + '-updates', capacity=24) as ledger:
        try:
            ledger.charge('illegal_after_restore', study_id)
        except RecoveryRequired:
            controls['historical_restore_dispatch_refused'] = True
        else:
            raise AssertionError('Historical restore admitted work')
    assert postgres_status(MONITOR, schema=restored_schema)['status'] == 'historical_restore_fenced'
    write(out / 'expected-state.json', dict(schema=schema, state=original, restored_schema=restored_schema))
    write(private / ('last-schema-' + out.name + '.json'), dict(schema=schema))
    write(out / 'verification.json', dict(passed=True, controls=controls, known_answer=result,
        backup=receipt, restored=restored, ray_nodes=nodes, ray_cpus=resources['CPU'],
        installed_origin=str(root), python=sys.version.split()[0], psycopg=importlib.metadata.version('psycopg'),
        physical_hosts=1, independent_host_fault_tested=False, service_accepted=False,
        ended_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(passed=True, controls=list(controls), gradient_updates=24,
                         independent_hosts=False)))


def reconstruct(out):
    record = json.loads((out / 'expected-state.json').read_text())
    current = postgres_status(MONITOR, schema=record['schema'])
    assert current == record['state']
    assert current['allocations'][0]['charged_units'] == 24
    assert current['allocations'][0]['uncertain_units'] == 0
    assert postgres_status(MONITOR, schema=record['restored_schema'])['status'] == 'historical_restore_fenced'
    write(out / 'restart.json', dict(passed=True, exact_state=current,
        additional_gradient_updates=0, historical_restore_stays_fenced=True))
    print(json.dumps(dict(passed=True, additional_gradient_updates=0)))


def main():
    # A bounded supervisor interruption must run Ray's finally cleanup.
    def interrupted(signum, frame):
        raise TimeoutError('Owned verification interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    action, private = sys.argv[1], Path(sys.argv[2])
    if action == 'initialize':
        role_setup(private)
    elif action == 'verify':
        verify(private, Path(sys.argv[3]))
    elif action == 'reconstruct':
        reconstruct(Path(sys.argv[3]))
    elif action == 'status':
        schemas = []
        for path in sorted(private.glob('last-schema-*.json')):
            schema = json.loads(path.read_text())['schema']
            schemas.append(dict(schema=schema, **postgres_status(MONITOR, schema=schema)))
        healthy = all(row['status'] == 'ok' for row in schemas)
        print(json.dumps(dict(status='running' if healthy else 'needs_review', schemas=schemas)))
        return 0 if healthy else 1
    else:
        raise ValueError('Unknown installed-client action')


if __name__ == '__main__':
    try:
        raise SystemExit(main() or 0)
    except Exception as exc:
        # Query/driver messages may contain authentication details. Keep only
        # the exception type in the public command log; retained DB logs are private.
        print(json.dumps(dict(passed=False, error_type=type(exc).__name__)))
        raise SystemExit(1)
