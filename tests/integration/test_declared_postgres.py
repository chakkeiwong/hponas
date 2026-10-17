"""Declared workflow and complete artifact recovery on a real local server."""
import json
from pathlib import Path

import pytest

psycopg = pytest.importorskip('psycopg')
from psycopg import sql
from tests.integration.test_postgres_backend import database
from tests.integration.test_declared_evaluation import declaration
from hponas import Study, RandomSearcher, SearchSpace, Knob, LocalExecutor
from hponas.postgres import PostgresStore, CoordinatorBusy, RecoveryRequired
from hponas.postgres_operations import backup_postgres, restore_postgres


def test_declared_live_report_order_recovery_and_all_role_artifact_backup(database, tmp_path):
    dsn, schema = database
    calls = []

    def objective(config, seed, evaluation, trial_id):
        calls.append(trial_id)
        artifact = tmp_path / (trial_id + '.json')
        artifact.write_text(json.dumps({'x': config['x'], 'seed': seed, 'role': evaluation.role}))
        return {'value': config['x']**2, 'artifacts': {'model': str(artifact)}}

    def make(store):
        return Study(RandomSearcher(SearchSpace([Knob('x','ordinal',(0,20))]),seed=3),
                     LocalExecutor(),objective,budget=12,maximize=False,
                     study_name='declared_pg',declaration=declaration(),store=store)

    with PostgresStore(dsn, schema=schema) as owner, PostgresStore(dsn, schema=schema) as monitor:
        study = make(owner)
        study.run()
        report = study.report()
        assert monitor.read_report('declared_pg') == report
        assert owner.read_study('declared_pg').status == 'completed'
        assert [r['last_trial_id'] for r in report['tuning_trajectory']['rows']] == [
            'declared_pg_trial_'+str(i) for i in range(12)]
        paths = {row['path'] for trial in report['trials'] for row in owner.read_artifacts(trial['trial_id'])}
        assert paths == {row['path'] for row in report['artifacts']}
        assert len(paths) == 50  # 12 * 2 folds * 2 seeds + 2 final repetitions
        with pytest.raises(CoordinatorBusy):
            monitor.load_study_snapshot('declared_pg')
    before = list(calls)
    with PostgresStore(dsn, schema=schema) as store:
        restored = make(store)
        restored.load_checkpoint()
        restored.run()
        assert restored.report() == report and calls == before

    receipt = backup_postgres(dsn, tmp_path/'backup', schema=schema, artifact_root=tmp_path)
    assert receipt['artifact_count'] == len(paths)
    manifest = json.loads((tmp_path/'backup/backup.json').read_text())
    assert {row['original_path'] for row in manifest['artifacts']} == paths
    for row in manifest['artifacts']:
        assert (tmp_path/'backup'/row['filename']).read_bytes() == Path(row['original_path']).read_bytes()
    restored_schema = schema + '_history'
    try:
        restore_postgres(dsn,tmp_path/'backup',schema=restored_schema,expected_sha256=receipt['sha256'])
        with PostgresStore(dsn,schema=restored_schema) as store:
            assert store.read_report('declared_pg') == report
            with pytest.raises(RecoveryRequired):
                make(store).load_checkpoint()
    finally:
        with psycopg.connect(dsn,autocommit=True) as admin:
            admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(restored_schema)))
