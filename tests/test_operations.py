"""Actual cross-process admission, crash conservatism and restore controls."""
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3

import pytest

from hponas.operations import (LocalWorkLedger, WorkBudgetExceeded, backup_database,
                               restore_database, database_inventory, ledger_status)


def _worker(path, index, out):
    with LocalWorkLedger(path, capacity=7) as ledger:
        value, steps = 1., 0
        for step in range(6):
            event = f'{index}:{step}'
            try:
                new = ledger.charge(event, str(index))
            except WorkBudgetExceeded:
                break
            if new:
                value -= .25*value
                steps += 1
                ledger.complete(event)
        Path(out).write_text(json.dumps({'steps': steps, 'value': value}))


def _crash_after_debit(path):
    ledger = LocalWorkLedger(path, capacity=3)
    assert ledger.charge('lost-ack', 'study')
    os._exit(13)


def test_concurrent_studies_cannot_launch_work_beyond_global_bound(tmp_path):
    path = tmp_path/'ledger.db'
    with LocalWorkLedger(path, capacity=7):
        pass
    ctx = multiprocessing.get_context('spawn')
    processes = [ctx.Process(target=_worker, args=(str(path), i, str(tmp_path/f'worker-{i}.json'))) for i in range(2)]
    for process in processes: process.start()
    for process in processes:
        process.join(45)
        if process.is_alive(): process.kill(); process.join()
        assert process.exitcode == 0
    results = [json.loads((tmp_path/f'worker-{i}.json').read_text()) for i in range(2)]
    assert sum(row['steps'] for row in results) == 7
    for row in results:
        assert row['value'] == .75**row['steps']
    assert ledger_status(path)['charged_units'] == ledger_status(path)['completed_units'] == 7


def test_killed_writer_keeps_uncertain_debit_and_cannot_redispatch(tmp_path):
    path = tmp_path/'ledger.db'
    ctx = multiprocessing.get_context('spawn')
    process = ctx.Process(target=_crash_after_debit, args=(str(path),))
    process.start(); process.join(45)
    if process.is_alive(): process.kill(); process.join()
    assert process.exitcode == 13
    with LocalWorkLedger(path, capacity=3) as ledger:
        assert ledger.charge('lost-ack', 'study') is False
        assert ledger.metrics()['uncertain_units'] == 1
        assert ledger.charge('new-attempt', 'study', 2)
        with pytest.raises(WorkBudgetExceeded): ledger.charge('too-much', 'other')
    assert ledger_status(path)['status'] == 'uncertain_work_requires_reconciliation'


def test_conflicting_identities_and_capacity_changes_are_refused(tmp_path):
    path = tmp_path/'ledger.db'
    with LocalWorkLedger(path, capacity=10) as ledger:
        ledger.charge('event', 'one', 2)
        before = ledger.metrics()
        for study, units in [('two', 2), ('one', 3)]:
            with pytest.raises(ValueError): ledger.charge('event', study, units)
        with pytest.raises(ValueError): ledger.complete('unknown')
        assert ledger.metrics() == before
        ledger.complete('event'); ledger.complete('event')
        assert ledger.metrics()['completed_units'] == 2
    with pytest.raises(ValueError): LocalWorkLedger(path, capacity=11)
    with pytest.raises(ValueError): LocalWorkLedger(path, capacity=10, unit='seconds')


def test_online_wal_backup_excludes_uncommitted_writes_and_restores_exact_inventory(tmp_path):
    path = tmp_path/'source.db'
    source = sqlite3.connect(path)
    source.execute('PRAGMA journal_mode=WAL')
    source.execute('CREATE TABLE records (key TEXT PRIMARY KEY, value REAL)')
    source.execute('INSERT INTO records VALUES (?,?)', ('committed', 4.)); source.commit()
    source.execute('INSERT INTO records VALUES (?,?)', ('pending', 9.))
    before = backup_database(path, tmp_path/'backup')
    source.commit(); source.close()
    assert database_inventory(path)['table_counts']['records'] == 2
    assert before['inventory']['table_counts']['records'] == 1
    restore_database(tmp_path/'backup', tmp_path/'restored.db')
    assert database_inventory(tmp_path/'restored.db') == before['inventory']
    connection = sqlite3.connect(tmp_path/'restored.db')
    assert connection.execute('SELECT * FROM records').fetchall() == [('committed', 4.)]
    connection.close()
    with pytest.raises(FileExistsError): restore_database(tmp_path/'backup', path)
    assert database_inventory(path)['table_counts']['records'] == 2


@pytest.mark.parametrize('change', ['bytes', 'hash', 'path', 'version', 'symlink'])
def test_corrupt_or_redirected_backup_cannot_publish(change, tmp_path):
    path = tmp_path/'ledger.db'
    with LocalWorkLedger(path, capacity=3): pass
    directory = tmp_path/'backup'
    backup_database(path, directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if change == 'bytes':
        with (directory/'database.sqlite3').open('ab') as handle: handle.write(b'changed')
    elif change == 'hash': manifest['sha256'] = '0'*64
    elif change == 'path': manifest['filename'] = '../ledger.db'
    elif change == 'version': manifest['schema'] = 'sqlite_backup_v100'
    else:
        (directory/'database.sqlite3').rename(directory/'original.sqlite3')
        (directory/'database.sqlite3').symlink_to(directory/'original.sqlite3')
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError): restore_database(directory, tmp_path/'fresh.db')
    assert not (tmp_path/'fresh.db').exists()


def test_future_ledger_schema_is_refused_without_rewriting_it(tmp_path):
    path = tmp_path/'ledger.db'
    with LocalWorkLedger(path, capacity=3): pass
    connection = sqlite3.connect(path)
    connection.execute('PRAGMA user_version=99'); connection.close()
    before = path.read_bytes()
    with pytest.raises(ValueError): LocalWorkLedger(path, capacity=3)
    assert path.read_bytes() == before


def test_probe_does_not_create_absent_databases(tmp_path):
    with pytest.raises(sqlite3.OperationalError): database_inventory(tmp_path/'missing.db')
    with pytest.raises(sqlite3.OperationalError): ledger_status(tmp_path/'missing-ledger.db')
    assert not list(tmp_path.iterdir())


def test_public_known_answer_example_recovers_store_and_study(tmp_path):
    from examples.operations_known_answer import run

    summary = run(tmp_path)
    assert summary['trials'] == 3
    assert summary['physical_updates'] == summary['accounted_updates'] == 12
    assert summary['ledger']['status'] == 'ok'
    assert summary['database_inventory'] == summary['restored_inventory']
    assert summary['known_endpoint_optimum_eta'] == .25
    assert summary['scientific_acceptance'] is False
    assert summary['distributed_service_acceptance'] is False


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_orphan_destination_journals_refuse_publication(tmp_path, suffix):
    with LocalWorkLedger(tmp_path/'source.db', capacity=2):
        pass
    backup_database(tmp_path/'source.db', tmp_path/'backup')
    destination = tmp_path/'restored.db'
    Path(str(destination)+suffix).write_bytes(b'orphan journal')
    with pytest.raises(ValueError, match='orphan'):
        restore_database(tmp_path/'backup', destination)
    assert not destination.exists()


def test_store_backup_restores_pending_proposal_and_artifact_without_repeating_prefix(tmp_path):
    import hashlib
    from hponas import Knob, SearchSpace, SobolSearcher, Study, LocalExecutor
    from hponas.store import Store

    class Interruption(KeyboardInterrupt):
        pass

    space = SearchSpace([Knob('eta', 'continuous', (.05, .25))])
    calls = []
    artifact = tmp_path/'weights.json'
    artifact.write_text(json.dumps({'state': [.75, .5]}))
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()

    def objective(config, trial_id):
        calls.append(trial_id)
        return {'value': (1-config['eta'])**2, 'cost': 1.,
                'artifacts': {'checkpoint': str(artifact)},
                'metadata': {'checkpoint_sha256': artifact_hash}}

    def interrupted(config, trial_id):
        if trial_id.endswith('_1'):
            raise Interruption()
        return objective(config, trial_id)

    def make(store, fn):
        return Study(SobolSearcher(space, seed=9), LocalExecutor(), fn,
                     store=store, budget=3, maximize=False, study_name='recover', legacy_reason='Protocol-only regression fixture; protected evaluation tested separately')

    original = Store(tmp_path/'source.db')
    try:
        with pytest.raises(Interruption):
            make(original, interrupted).run()
        snapshot = original.load_study_snapshot('recover')
        artifacts = original.read_artifacts('recover_trial_0')
        assert len(snapshot['results']) == 1 and snapshot['pending'] == ['recover_trial_1']
        backup_database(tmp_path/'source.db', tmp_path/'backup')
    finally:
        original.close()
    restore_database(tmp_path/'backup', tmp_path/'restored.db')
    restored = Store(tmp_path/'restored.db')
    try:
        assert restored.load_study_snapshot('recover') == snapshot
        assert restored.read_artifacts('recover_trial_0') == artifacts
        study = make(restored, objective)
        study.load_checkpoint()
        result = study.run()
        assert calls == [f'recover_trial_{i}' for i in range(3)]
        assert result.history[0].to_dict() == snapshot['results']['recover_trial_0']
        assert result.total_cost == 3.
        reference = SobolSearcher(space, seed=9)
        for row in result.history:
            expected = reference.suggest().values
            assert study.trials[row.trial_id].config.values == expected
            assert row.objective_value == (1-expected['eta'])**2
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_hash
    finally:
        restored.close()
