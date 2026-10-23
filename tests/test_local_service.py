"""Local service behavior over real Study checkpoints, not a parallel toy store."""
import copy
from contextlib import closing
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3

import pytest

from hponas import Knob, SearchSpace, SobolSearcher, Study, LocalExecutor
from hponas.backup_security import canonical
from hponas.local_service import (ManagedStudyService, DirectoryAlertSink,
    import_legacy_store, migrate_service, rollback_migration, restore_events)
from hponas.operations import WorkBudgetExceeded, database_inventory
from hponas.store import Store, Study as StudyRecord


class Clock:
    def __init__(self, at=10):
        self.at = at

    def __call__(self):
        return self.at


def quota(service, *, subject='alice', quota_id='period', **changes):
    declaration = dict(quota_id=quota_id, subject=subject, period_id='day-1',
        start_us=0, end_us=1000, device='cpu', device_limit_us=100,
        currency='USD', cost_limit_micros=100, price_id='price-1',
        price_micros_per_hour=3_600_000_000, max_active_studies=10)
    declaration.update(changes)
    service.configure_quota('admin', event_id='quota-' + quota_id, **declaration)
    return declaration


@pytest.fixture
def service(tmp_path):
    with ManagedStudyService.create(tmp_path/'service.db', admin='admin', clock=Clock()) as result:
        result.project('admin', 'one', owner='alice', event_id='one-project')
        result.project('admin', 'two', owner='bob', event_id='two-project')
        yield result


def _business(service):
    tables = ('studies', 'trials', 'study_snapshots', 'service_members',
              'service_reservations', 'service_schedules', 'service_occurrences', 'service_alerts')
    return {table: service._conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
            for table in tables}


def test_roles_denied_side_effects_and_scoped_reads_are_audited(service, tmp_path):
    service.grant('alice', 'one', 'colleague', 'collaborator', event_id='collaborator')
    service.grant('alice', 'one', 'reader', 'viewer', event_id='viewer')
    facade = service.store('colleague', 'one')
    space = SearchSpace([Knob('x', 'continuous', (0., 1.))])
    Study(SobolSearcher(space, seed=1), LocalExecutor(), lambda c: c['x']**2,
          store=facade, study_name='one', budget=1,
          legacy_reason='Role-policy fixture; no scientific selection claim').run()
    assert service.store('reader', 'one').read_trials('one')[0].status == 'completed'
    snapshot = facade.load_study_snapshot('one')
    before = _business(service)
    sink_calls = []

    class Sink:
        def send(self, *args):
            sink_calls.append(args)

    attempts = [
        lambda: service.store('reader', 'one').save_study_snapshot(snapshot),
        lambda: service.store('reader', 'one').read_study('two'),
        lambda: service.store('admin', 'two').read_artifacts('one_trial_0'),
        lambda: service.store('bob', 'one').read_trials('one'),
        lambda: service.grant('colleague', 'one', 'intruder', 'viewer', event_id='bad-grant'),
        lambda: service.events('reader'),
        lambda: service.export_events('alice', tmp_path/'forbidden'/'events.json'),
        lambda: service.tick('reader', backup_directory=tmp_path/'forbidden', alert_sink=Sink()),
    ]
    for attempt in attempts:
        with pytest.raises(PermissionError):
            attempt()
    assert _business(service) == before
    assert not (tmp_path/'forbidden').exists() and not sink_calls
    denied = [row for row in service.audit('admin') if not row['allowed']]
    assert len(denied) == len(attempts)
    for event in service._events():
        if event['action'] == 'denied':
            assert set(event['data']) == {'attempted_action'}
    # Trial identity cannot be moved between projects by a checkpoint write.
    redirected = copy.deepcopy(snapshot); redirected['study_name'] = 'two'
    with pytest.raises(ValueError, match='Trial identity'):
        service.store('bob', 'two').save_study_snapshot(redirected)
    assert _business(service) == before


def test_mutation_failure_rolls_back_store_and_journal_together(service, monkeypatch):
    import hponas.local_service as module

    before, events = _business(service), service._events()
    real_insert = module._insert_event

    def fail(connection, event):
        real_insert(connection, event)
        raise RuntimeError('injected journal failure')

    monkeypatch.setattr(module, '_insert_event', fail)
    with pytest.raises(RuntimeError):
        service.project('admin', 'third', owner='alice', event_id='third')
    assert _business(service) == before and service._events() == events


def test_subject_quotas_prices_uncertainty_overruns_and_periods(service):
    quota(service)
    assert service.reserve('alice', 'one', event_id='r1', quota_id='period', device_us=60) is True
    assert service.reserve('alice', 'one', event_id='r1', quota_id='period', device_us=60) is False
    with pytest.raises(ValueError, match='Conflicting'):
        service.reserve('alice', 'one', event_id='r1', quota_id='period', device_us=61)
    report = service.quota_report('alice', 'period')
    assert report['actual_device_us'] == 0 and report['uncertain_device_us'] == 60
    with pytest.raises(PermissionError):
        service.quota_report('bob', 'period')
    with pytest.raises(WorkBudgetExceeded):
        service.reserve('alice', 'one', event_id='over', quota_id='period', device_us=41)
    service.finish('alice', 'one', event_id='f1', reservation_id='r1', status='failed',
                   measured_device_us=20, measurement_id='cpu-sample-1')
    report = service.quota_report('alice', 'period')
    assert (report['actual_device_us'], report['uncertain_device_us'], report['charged_cost_micros']) == (20, 40, 60)
    service.reserve('alice', 'one', event_id='r2', quota_id='period', device_us=40)
    service.finish('alice', 'one', event_id='f2', reservation_id='r2', status='completed',
                   measured_device_us=70, measurement_id='cpu-sample-2')
    report = service.quota_report('alice', 'period')
    assert report['charged_device_us'] == report['charged_cost_micros'] == 130
    assert report['price_id'] == 'price-1' and report['currency'] == 'USD'
    with pytest.raises(WorkBudgetExceeded):
        service.reserve('alice', 'one', event_id='r3', quota_id='period', device_us=1)
    # A new price/period cannot rewrite earlier charges.
    quota(service, quota_id='next-period', start_us=1000, end_us=2000,
          price_id='price-2', price_micros_per_hour=1)
    service.clock.at = 1000
    with pytest.raises(WorkBudgetExceeded):
        service.reserve('alice', 'one', event_id='expired', quota_id='period', device_us=1)
    service.reserve('alice', 'one', event_id='next', quota_id='next-period', device_us=2)
    assert service.quota_report('alice', 'next-period')['charged_cost_micros'] == 1
    assert service.quota_report('alice', 'period')['charged_cost_micros'] == 130


def test_quota_active_studies_and_measurement_identity(service):
    quota(service, max_active_studies=1)
    with pytest.raises(WorkBudgetExceeded):
        service.project('admin', 'third', owner='alice', event_id='new-project')
    service.reserve('alice', 'one', event_id='r1', quota_id='period', device_us=10)
    with pytest.raises(ValueError, match='actual'):
        service.finish('alice', 'one', event_id='bad-complete', reservation_id='r1', status='completed')
    service.close_project('alice', 'one', event_id='closed')
    # Closing does not prevent recording measurements of already admitted work.
    service.finish('alice', 'one', event_id='f1', reservation_id='r1', status='completed',
                   measured_device_us=8, measurement_id='unique-sample')
    with pytest.raises(PermissionError):
        service.reserve('alice', 'one', event_id='closed-reserve', quota_id='period', device_us=1)
    service.project('admin', 'third', owner='alice', event_id='new-project')
    service.reserve('alice', 'third', event_id='r2', quota_id='period', device_us=10)
    with pytest.raises(sqlite3.IntegrityError):
        service.finish('alice', 'third', event_id='f2', reservation_id='r2', status='completed',
                       measured_device_us=8, measurement_id='unique-sample')
    assert service.quota_report('alice', 'period')['uncertain_device_us'] == 10


def _race_reserve(path, index, ready, release, result):
    with ManagedStudyService(path, clock=Clock()) as service:
        ready.set(); release.wait(20)
        try:
            admitted = service.reserve('alice', 'one', event_id=f'race-{index}', quota_id='period', device_us=60)
        except WorkBudgetExceeded:
            admitted = False
        Path(result).write_text(json.dumps(admitted))


def _crash_reservation(path):
    with ManagedStudyService(path, clock=Clock()) as service:
        assert service.reserve('alice', 'one', event_id='lost-reservation', quota_id='period', device_us=60)
        os._exit(17)


def test_concurrent_admission_and_killed_writer_never_refund_or_redispatch(service, tmp_path):
    quota(service)
    ctx = multiprocessing.get_context('spawn')
    ready, release = [ctx.Event() for _ in range(2)], ctx.Event()
    processes = [ctx.Process(target=_race_reserve,
        args=(str(service.path), i, ready[i], release, str(tmp_path/f'result-{i}'))) for i in range(2)]
    try:
        for process in processes: process.start()
        assert all(event.wait(30) for event in ready)
        release.set()
        for process in processes: process.join(30)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive(): process.kill(); process.join()
    assert sum(json.loads((tmp_path/f'result-{i}').read_text()) for i in range(2)) == 1
    assert service.quota_report('alice', 'period')['charged_device_us'] == 60
    # A separate fresh allocation makes the crash debit observable by itself.
    # The crash worker uses a new owned service and never edits a prior debit.
    other = tmp_path/'crash.db'
    with ManagedStudyService.create(other, admin='admin', clock=Clock()) as second:
        second.project('admin', 'one', owner='alice', event_id='project')
        quota(second)
    process = ctx.Process(target=_crash_reservation, args=(str(other),))
    process.start(); process.join(30)
    if process.is_alive(): process.kill(); process.join()
    assert process.exitcode == 17
    with ManagedStudyService(other, clock=Clock()) as second:
        assert second.reserve('alice', 'one', event_id='lost-reservation', quota_id='period', device_us=60) is False
        assert second.quota_report('alice', 'period')['uncertain_device_us'] == 60


def test_legacy_import_service_upgrade_and_verified_predecessor_rollback(tmp_path):
    source = tmp_path/'legacy.db'
    with closing(Store(source)) as store:
        store.write_study(StudyRecord('old', '{}', 'minimize', 1, 4.))
    original = database_inventory(source)
    first = import_legacy_store(source, tmp_path/'v1.db', tmp_path/'backup0', admin='admin', clock=Clock())
    assert database_inventory(source) == original
    assert hashlib.sha256((tmp_path/'v1.db').read_bytes()).hexdigest() == first['destination_sha256']
    with ManagedStudyService(tmp_path/'v1.db', clock=Clock()) as service:
        assert service.version == 1 and service.store('admin', 'old').read_study('old').budget == 4.
    second = migrate_service(tmp_path/'v1.db', tmp_path/'v2.db', tmp_path/'backup1', actor='admin', clock=Clock())
    with ManagedStudyService(tmp_path/'v2.db', clock=Clock()) as service:
        assert service.version == 2
    rollback_migration(second, tmp_path/'rolled-v1.db', expected_manifest_sha256=hashlib.sha256(canonical(second)).hexdigest())
    rollback_migration(first, tmp_path/'rolled-v0.db')
    assert database_inventory(tmp_path/'rolled-v0.db') == original
    assert database_inventory(tmp_path/'rolled-v1.db') == second['backup']['inventory']
    changed = copy.deepcopy(second); changed['backup_directory'] = str(tmp_path/'backup0')
    with pytest.raises(ValueError): rollback_migration(changed, tmp_path/'wrong.db')
    with pytest.raises(ValueError): rollback_migration(second, tmp_path/'wrong.db', expected_manifest_sha256='0'*64)
    assert not (tmp_path/'wrong.db').exists()


def test_incremental_history_replays_migration_and_fences_each_recovery_copy(tmp_path):
    legacy = tmp_path/'legacy.db'
    with closing(Store(legacy)) as store:
        store.write_study(StudyRecord('old', '{}', 'minimize', 1, 4.))
    import_legacy_store(legacy, tmp_path/'v1.db', tmp_path/'backup0', admin='admin', clock=Clock())
    migrate_service(tmp_path/'v1.db', tmp_path/'v2.db', tmp_path/'backup1', actor='admin', clock=Clock())
    with ManagedStudyService(tmp_path/'v2.db', clock=Clock()) as service:
        service.project('admin', 'work', owner='alice', event_id='project')
        quota(service)
        first = service.export_events('admin', tmp_path/'first.json')
    restore_events([tmp_path/'first.json'], tmp_path/'copy1.db', expected_head=first['head'])
    with ManagedStudyService(tmp_path/'copy1.db', clock=Clock()) as service:
        assert service.version == 2
        assert service.store('admin', 'old').read_study('old').budget == 4.
        with pytest.raises(WorkBudgetExceeded):
            service.reserve('alice', 'work', event_id='before-ack', quota_id='period', device_us=1)
        service.acknowledge_recovery('admin', event_id='ack', evidence_id='first-copy-reconciled',
            writers_fenced=True, later_reservations_reconciled=True)
        assert service.reserve('alice', 'work', event_id='paid', quota_id='period', device_us=7)
        second = service.export_events('admin', tmp_path/'second.json', after_seq=first['end_seq'])
    restore_events([tmp_path/'first.json', tmp_path/'second.json'], tmp_path/'copy2.db', expected_head=second['head'])
    with ManagedStudyService(tmp_path/'copy2.db', clock=Clock()) as service:
        assert service.version == 2
        assert service.quota_report('alice', 'period')['uncertain_device_us'] == 7
        # Replaying a historical acknowledgement cannot grant a new copy work.
        with pytest.raises(WorkBudgetExceeded):
            service.reserve('alice', 'work', event_id='copy-work', quota_id='period', device_us=1)


@pytest.mark.parametrize('fault', ['manifest', 'publication', 'conversion'])
def test_migration_failures_preserve_predecessor_and_do_not_publish(tmp_path, monkeypatch, fault):
    import hponas.local_service as module

    source = tmp_path/'legacy.db'
    Store(source).close()
    before = source.read_bytes()
    target = {'manifest': '_write_new', 'publication': '_publish_database', 'conversion': '_initialize'}[fault]

    def fail(*args, **kwargs):
        raise OSError('injected bounded migration failure')

    monkeypatch.setattr(ManagedStudyService if fault == 'conversion' else module, target, fail)
    with pytest.raises(OSError):
        import_legacy_store(source, tmp_path/'new.db', tmp_path/'backup', admin='admin', clock=Clock())
    assert source.read_bytes() == before and not (tmp_path/'new.db').exists()
    assert (tmp_path/'backup'/'manifest.json').is_file()
    if fault == 'publication':
        prepared = json.loads((tmp_path/'backup'/'migration.json').read_text())
        assert prepared['publication'] == 'prepared_record_requires_matching_destination'
        rollback_migration(prepared, tmp_path/'recovered-predecessor.db')
    assert not list(tmp_path.glob('.migrate-*'))


@pytest.mark.parametrize('change', ['version', 'schema', 'event_index', 'audit'])
def test_unknown_or_inconsistent_service_is_refused_without_repair(tmp_path, change):
    path = tmp_path/'service.db'
    ManagedStudyService.create(path, admin='admin', clock=Clock()).close()
    with sqlite3.connect(path) as connection:
        if change == 'version': connection.execute('PRAGMA user_version=99')
        elif change == 'schema': connection.execute('CREATE TABLE unexpected(secret TEXT)')
        elif change == 'event_index': connection.execute('UPDATE service_events SET at=999 WHERE seq=1')
        else: connection.execute('UPDATE service_audit SET allowed=0 WHERE seq=1')
    before = path.read_bytes()
    with pytest.raises(ValueError): ManagedStudyService(path, clock=Clock())
    assert path.read_bytes() == before


def test_incremental_pitr_restores_actual_pending_study_without_rerunning_prefix(tmp_path):
    clock, calls = Clock(), []
    path = tmp_path/'service.db'
    space = SearchSpace([Knob('eta', 'continuous', (.05, .25))])

    class Interrupted(KeyboardInterrupt):
        pass

    with ManagedStudyService.create(path, admin='admin', clock=clock) as service:
        service.project('admin', 'recover', owner='alice', event_id='project')
        quota(service)

        def objective(config, trial_id):
            assert service.reserve('alice', 'recover', event_id='work-' + trial_id, quota_id='period', device_us=10)
            calls.append(trial_id)
            service.finish('alice', 'recover', event_id='done-' + trial_id,
                reservation_id='work-' + trial_id, status='completed',
                measured_device_us=7, measurement_id='sample-' + trial_id)
            return {'value': (1-config['eta'])**2, 'cost': 1.}

        def interrupted(config, trial_id):
            if trial_id.endswith('_1'): raise Interrupted()
            return objective(config, trial_id)

        def make(current, fn):
            return Study(SobolSearcher(space, seed=9), LocalExecutor(), fn,
                store=current.store('alice', 'recover'), study_name='recover', budget=3,
                legacy_reason='Incremental-recovery fixture; evaluation isolation tested separately')

        clock.at = 20
        with pytest.raises(Interrupted): make(service, interrupted).run()
        snapshot = service.store('alice', 'recover').load_study_snapshot('recover')
        boundary = service._events()[-1]['seq']
        assert list(snapshot['results']) == ['recover_trial_0']
        assert snapshot['pending'] == ['recover_trial_1']
        clock.at = 21
        first = service.export_events('admin', tmp_path/'part-1.json')
        clock.at = 22
        current = make(service, objective); current.load_checkpoint(); full = current.run()
        full_configs = {key: trial.config.values for key, trial in current.trials.items()}
        clock.at = 23
        last = service.export_events('admin', tmp_path/'part-2.json', after_seq=first['end_seq'])
    segments = [tmp_path/'part-1.json', tmp_path/'part-2.json']
    restored = restore_events(segments, tmp_path/'restored.db', through_sequence=boundary, expected_head=last['head'])
    restore_events(segments, tmp_path/'by-time.db', through_time_us=20, expected_head=last['head'])
    assert database_inventory(tmp_path/'by-time.db') == database_inventory(tmp_path/'restored.db')
    calls[:] = calls[:1]
    with ManagedStudyService(tmp_path/'restored.db', clock=Clock(24)) as service:
        assert service.store('alice', 'recover').load_study_snapshot('recover') == snapshot
        with pytest.raises(WorkBudgetExceeded):
            service.reserve('alice', 'recover', event_id='new', quota_id='period', device_us=1)
        with pytest.raises(ValueError):
            service.acknowledge_recovery('admin', event_id='bad-ack', evidence_id='evidence',
                writers_fenced='yes', later_reservations_reconciled=True)
        service.acknowledge_recovery('admin', event_id='ack', evidence_id='test-original-writer-closed-and-work-reconciled',
            writers_fenced=True, later_reservations_reconciled=True)
        current = make(service, objective); current.load_checkpoint(); recovered = current.run()
        assert calls == [f'recover_trial_{i}' for i in range(3)]
        assert [row.trial_id for row in recovered.history] == [row.trial_id for row in full.history]
        assert [row.objective_value for row in recovered.history] == pytest.approx(
            [row.objective_value for row in full.history])
        assert {key: trial.config.values for key, trial in current.trials.items()} == full_configs
        assert recovered.history[0] == full.history[0]
        assert [(row.cost, row.fidelity, row.status) for row in recovered.history] == [
            (row.cost, row.fidelity, row.status) for row in full.history]
        assert service.quota_report('alice', 'period')['charged_device_us'] == 21
    assert restored['dispatch'] == 'requires_fencing_and_reservation_reconciliation'


@pytest.mark.parametrize('change', ['gap', 'reverse', 'tamper_later', 'truncated', 'before_genesis', 'past_end'])
def test_pitr_validates_entire_supplied_history_before_cutoff_publication(service, tmp_path, change):
    first = service.export_events('admin', tmp_path/'part1')
    last = service.export_events('admin', tmp_path/'part2', after_seq=first['end_seq'])
    segments = [tmp_path/'part1', tmp_path/'part2']
    kwargs = {'through_sequence': 1, 'expected_head': last['head']}
    if change == 'gap': segments = segments[1:]
    elif change == 'reverse': segments.reverse()
    elif change == 'tamper_later':
        payload = json.loads(segments[1].read_text()); payload['events'][-1]['actor'] = 'altered'
        segments[1].write_text(json.dumps(payload))
    elif change == 'truncated': segments.pop()
    elif change == 'before_genesis': kwargs = {'through_time_us': 0}
    else: kwargs['through_sequence'] = 10_000
    with pytest.raises(ValueError): restore_events(segments, tmp_path/'refused.db', **kwargs)
    assert not (tmp_path/'refused.db').exists() and not list(tmp_path.glob('.replay-*'))


def test_backup_schedules_are_incremental_and_alerts_are_idempotent(service, tmp_path):
    service.configure_schedule('admin', event_id='backup-schedule', schedule_id='backups', kind='backup', interval_us=10, start_us=20)
    service.configure_schedule('admin', event_id='monitor-schedule', schedule_id='monitoring', kind='monitor', interval_us=10, start_us=20)
    sink = DirectoryAlertSink(tmp_path/'alerts')
    assert service.tick('admin', backup_directory=tmp_path/'backups') == []
    service.clock.at = 20
    sample = {'disk_fraction': {'value': .9, 'unit': 'fraction', 'measurement_id': 'disk-20'}}
    first = service.tick('admin', backup_directory=tmp_path/'backups', measurements=sample, alert_sink=sink)
    assert [row['status'] for row in first] == ['completed', 'completed']
    assert len(list((tmp_path/'alerts').iterdir())) == 1
    assert service.tick('admin', backup_directory=tmp_path/'backups', measurements=sample, alert_sink=sink) == []
    service.clock.at = 30
    second = service.tick('admin', backup_directory=tmp_path/'backups', measurements={}, alert_sink=sink)
    backups = [row for row in first + second if 'end_seq' in row['details']]
    assert backups[1]['details']['start_seq'] == backups[0]['details']['end_seq'] + 1
    paths = [tmp_path/'backups'/(row['occurrence_id'] + '.json') for row in backups]
    restore_events(paths, tmp_path/'replayed.db', expected_head=backups[-1]['details']['head'])
    with ManagedStudyService(tmp_path/'replayed.db', clock=Clock(30)) as copy_service:
        with pytest.raises(WorkBudgetExceeded): copy_service.tick('admin', backup_directory=tmp_path/'copy-backups')
    assert not (tmp_path/'copy-backups').exists()


def _race_tick(path, backup_directory, ready, release, result):
    with ManagedStudyService(path, clock=Clock(20)) as service:
        ready.set()
        if not release.wait(30):
            raise RuntimeError('Owned scheduler race was not released')
        outcomes = service.tick('admin', backup_directory=backup_directory)
        Path(result).write_text(json.dumps(outcomes))


def test_concurrent_scheduler_processes_publish_one_due_backup(service, tmp_path):
    service.configure_schedule('admin', event_id='schedule', schedule_id='backups',
        kind='backup', interval_us=10, start_us=20)
    ctx = multiprocessing.get_context('spawn')
    ready, release = [ctx.Event(), ctx.Event()], ctx.Event()
    processes = [ctx.Process(target=_race_tick, args=(str(service.path), str(tmp_path/'backups'),
        ready[i], release, str(tmp_path/f'tick-{i}.json'))) for i in range(2)]
    try:
        for process in processes: process.start()
        assert all(event.wait(30) for event in ready)
        release.set()
        for process in processes: process.join(30)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive(): process.kill(); process.join()
    outcomes = [row for i in range(2) for row in json.loads((tmp_path/f'tick-{i}.json').read_text())]
    assert len(outcomes) == 1 and outcomes[0]['status'] == 'completed'
    backups = list((tmp_path/'backups').iterdir())
    assert len(backups) == 1
    assert len(service._occurrences()) == 1
    restore_events(backups, tmp_path/'concurrent-copy.db', expected_head=outcomes[0]['details']['head'])


def test_failed_or_unacknowledged_effects_are_retained_and_never_repeated(service, tmp_path):
    class FailedSink:
        def __init__(self): self.calls = 0
        def send(self, *args):
            self.calls += 1
            raise RuntimeError('private-key-must-not-be-retained')

    service.monitor('admin', {'error_rate': {'value': .2, 'unit': 'fraction', 'measurement_id': 'errors'}}, occurrence_id='manual')
    sink = FailedSink()
    service.deliver_alerts('admin', sink); service.deliver_alerts('admin', sink)
    assert sink.calls == 1
    assert service._conn.execute('SELECT payload FROM service_alerts').fetchone()[0].find('uncertain') >= 0
    service.configure_schedule('admin', event_id='schedule', schedule_id='backups', kind='backup', interval_us=10, start_us=20)
    service.clock.at = 20
    blocked = tmp_path/'blocked'; blocked.write_text('a file, not a backup directory')
    assert service.tick('admin', backup_directory=blocked)[0]['status'] == 'uncertain'
    service.clock.at = 100
    assert service.tick('admin', backup_directory=tmp_path/'never-dispatched') == []
    assert not (tmp_path/'never-dispatched').exists()
    assert 'private-key-must-not-be-retained' not in canonical(service._events()).decode()
    # A durable claim followed by a crash has no completion acknowledgement.
    service.configure_schedule('admin', event_id='monitor', schedule_id='monitor', kind='monitor', interval_us=10, start_us=100)
    schedule = service._json_row('service_schedules', 'schedule_id', 'monitor')
    occurrence, _ = service._claim('admin', schedule)
    assert occurrence is not None and service._claim('admin', schedule) == (None, None)
    assert service.tick('admin', backup_directory=tmp_path/'never-dispatched') == []


@pytest.mark.parametrize('sample', [1.1, -1, float('nan'), True])
def test_invalid_monitoring_values_make_no_alerts(service, sample):
    with pytest.raises(ValueError):
        service.monitor('admin', {'disk_fraction': {'value': sample, 'unit': 'fraction', 'measurement_id': 'sample'}}, occurrence_id='manual')
    assert service._conn.execute('SELECT COUNT(*) FROM service_alerts').fetchone()[0] == 0

