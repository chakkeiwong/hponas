"""Supervised local Study operations with committed-event recovery.

The caller authenticates principal names. SQLite and the operating-system owner
remain trusted; this facade is application policy, not hostile-user isolation.
One connection belongs to one thread/process. All physical work must cooperate
with reservations; historical recovery copies start with dispatch disabled.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import uuid

from .backup_security import canonical, decrypt_backup, encrypt_backup
from .operations import WorkBudgetExceeded, backup_database, restore_database, _read_only
from .store import Store, Study as StudyRecord, Trial as TrialRecord

APPLICATION_ID = 0x48504F53
ZERO = '0' * 64
HOUR_US = 3_600_000_000
BASE_TABLES = ('studies', 'trials', 'trial_observations', 'artifacts',
               'study_snapshots', 'trial_objectives', 'warm_history', 'sqlite_sequence')
ROLES = {'owner', 'collaborator', 'viewer'}
READS = {'load_study_snapshot', 'read_study', 'read_trials', 'read_observations',
         'read_artifacts', 'read_evaluation', 'read_report', 'read_rung_diagnostics'}
WRITES = {'save_study_snapshot', 'write_study', 'write_trial', 'write_observation',
          'write_objectives', 'write_artifact'}


class _ClaimUnavailable(ValueError):
    """Another tick has advanced or is still handling this schedule."""


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:@/-]{1,180}', value):
        raise ValueError('A bounded principal, study or event identifier is required')
    return value


def _number(value, name='microseconds', *, positive=False):
    if type(value) is not int or not int(positive) <= value < 2**63:
        raise ValueError(name + ' must be a bounded nonnegative integer')
    return value


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _write_new(path, value):
    """Publish exclusively after all bytes are durable; trusted local parent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value) + b'\n'
    fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.unlink(temporary)


def _fresh(path):
    path = Path(path)
    if os.path.lexists(path):
        raise FileExistsError(path)
    if any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Destination has orphan journal sidecars')
    return path


def _schema(connection):
    return connection.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()


def _legacy_schema():
    with closing(sqlite3.connect(':memory:')) as connection:
        store = Store.__new__(Store); store._conn = connection
        store._init_schema()
        return _schema(connection)


def _service_schema(version):
    with closing(sqlite3.connect(':memory:')) as connection:
        store = Store.__new__(Store); store._conn = connection
        store._init_schema()
        _install(connection, history_id='schema-reference', admin='schema-reference', version=version)
        return _schema(connection)


def _tables(connection):
    return {name: connection.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall()
            for name in BASE_TABLES}


def _install(connection, *, history_id, admin, version=1, recovery=False):
    connection.execute('CREATE TABLE service_meta (history_id TEXT NOT NULL, admin TEXT NOT NULL, recovery INTEGER NOT NULL)')
    connection.execute('INSERT INTO service_meta VALUES (?,?,?)', (history_id, admin, int(recovery)))
    connection.execute('CREATE TABLE service_events (seq INTEGER PRIMARY KEY, at INTEGER NOT NULL, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, digest TEXT UNIQUE NOT NULL)')
    connection.execute('CREATE TABLE service_members (study_id TEXT NOT NULL, principal TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(study_id,principal))')
    connection.execute('CREATE TABLE service_audit (seq INTEGER PRIMARY KEY, at INTEGER NOT NULL, actor TEXT NOT NULL, study_id TEXT, action TEXT NOT NULL, allowed INTEGER NOT NULL)')
    connection.execute('CREATE TABLE service_quotas (quota_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    connection.execute('CREATE TABLE service_reservations (reservation_id TEXT PRIMARY KEY, payload TEXT NOT NULL, measurement_id TEXT UNIQUE)')
    connection.execute('CREATE TABLE service_schedules (schedule_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    connection.execute('CREATE TABLE service_occurrences (occurrence_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    connection.execute('CREATE TABLE service_alerts (alert_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
    connection.execute('PRAGMA user_version=1')
    if version == 2:
        connection.execute('CREATE INDEX idx_service_events_at ON service_events(at,seq)')
        connection.execute('PRAGMA user_version=2')


class _DeferredConnection:
    """Underlying Store writes participate in the service's outer transaction."""
    def __init__(self, connection):
        self.raw = connection

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ManagedStudyService:
    """Versioned local application service over the actual SQLite Study schema.

    Use ``create`` for a fresh store and ``import_legacy_store`` for an offline
    legacy Store. Neither opening nor creating silently migrates an old schema.
    ``store(actor, study_id)`` supplies the public Study checkpoint interface.
    """
    def __init__(self, path, *, clock=None):
        self.path = Path(path)
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError('An existing owned service database is required')
        self.clock = clock or (lambda: time.time_ns() // 1000)
        self._conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            self.version = self._conn.execute('PRAGMA user_version').fetchone()[0]
            if (self.version not in (1, 2)
                    or self._conn.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                    or self._conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]
                    or _schema(self._conn) != _service_schema(self.version)):
                raise ValueError('Unsupported service identity, schema or integrity')
            rows = self._conn.execute('SELECT history_id,admin,recovery FROM service_meta').fetchall()
            if len(rows) != 1:
                raise ValueError('Ambiguous service identity')
            self.history_id, self.admin, recovery = rows[0]
            _id(self.admin)
            if str(uuid.UUID(self.history_id)) != self.history_id or recovery not in (0, 1):
                raise ValueError('Invalid service history or recovery identity')
            with self._transaction():
                events = self._events()
                _verify_events(events, self.history_id)
                expected_audit = [(e['seq'], e['at'], e['actor'], e['study_id'],
                                   e['action'], int(e['action'] != 'denied')) for e in events]
                if self._conn.execute('SELECT * FROM service_audit ORDER BY seq').fetchall() != expected_audit:
                    raise ValueError('Access audit differs from committed history')
            self._store = Store.__new__(Store)
            self._store.db_path = self.path
            self._store._conn = _DeferredConnection(self._conn)
        except BaseException:
            self._conn.close()
            raise

    @classmethod
    def create(cls, path, *, admin, clock=None, schema_version=2):
        _id(admin)
        if type(schema_version) is not int or schema_version not in (1, 2):
            raise ValueError('Unsupported service schema version')
        path = _fresh(path); path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.service-', dir=path.parent); os.close(fd)
        try:
            legacy = Store(temporary); legacy.close()
            cls._initialize(temporary, admin=admin, clock=clock, schema_version=schema_version)
            _publish_database(temporary, path)
        finally:
            _remove_temporary(temporary)
        return cls(path, clock=clock)

    @classmethod
    def _initialize(cls, path, *, admin, clock=None, schema_version=1):
        at = _number((clock or (lambda: time.time_ns() // 1000))())
        with closing(sqlite3.connect(path, isolation_level=None)) as connection:
            if (_schema(connection) != _legacy_schema()
                    or connection.execute('PRAGMA user_version').fetchone()[0] != 0
                    or connection.execute('PRAGMA application_id').fetchone()[0] != 0):
                raise ValueError('Only the exact legacy Study schema can be imported')
            baseline = _tables(connection)
            connection.execute('BEGIN IMMEDIATE')
            try:
                history_id = str(uuid.uuid4())
                _install(connection, history_id=history_id, admin=admin, version=schema_version)
                for row in baseline['studies']:
                    connection.execute('INSERT INTO service_members VALUES (?,?,?,1)', (row[0], admin, 'owner'))
                body = {'seq': 1, 'at': at, 'event_id': 'genesis', 'action': 'genesis',
                        'actor': admin, 'study_id': None, 'history_id': history_id,
                        'previous': ZERO, 'data': {'admin': admin, 'version': schema_version,
                                                   'tables': baseline}}
                _insert_event(connection, {**body, 'digest': _digest(body)})
                connection.commit()
            except BaseException:
                connection.rollback(); raise

    @contextmanager
    def _transaction(self):
        self._conn.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self._conn.rollback(); raise
        else:
            self._conn.commit()

    def _allowed(self, actor, study_id, action, data):
        # A scoped facade cannot widen its project, even for the service admin.
        if action.startswith('read:') and action[5:] in READS:
            method, args = action[5:], data['args']
            if method in ('read_observations', 'read_artifacts'):
                row = self._conn.execute('SELECT study_id FROM trials WHERE trial_id=?', (args[0],)).fetchone()
                if row is None or row[0] != study_id:
                    return False
            elif args != [study_id]:
                return False
        if actor == self.admin:
            return True
        if action == 'read:quota':
            quota = self._json_row('service_quotas', 'quota_id', data.get('quota_id'))
            return quota is not None and actor == quota['subject']
        if study_id is None:
            return False
        row = self._conn.execute('SELECT role,active FROM service_members WHERE study_id=? AND principal=?', (study_id, actor)).fetchone()
        if row is None:
            return False
        if action.startswith('read:'):
            return action[5:] in READS
        if action == 'finish':
            return row[0] in ('owner', 'collaborator')
        if not row[1]:
            return False
        if action == 'grant' or action == 'close_project':
            return row[0] == 'owner'
        return row[0] in ('owner', 'collaborator') and (action.startswith('write:') or action in ('reserve', 'finish'))

    def _perform(self, actor, study_id, action, data, *, event_id=None):
        _id(actor)
        if study_id is not None:
            _id(study_id)
        event_id = _id(event_id or 'access-' + uuid.uuid4().hex)
        # Canonicalize before starting a transaction or retaining any data.
        data = json.loads(canonical(data))
        denied = False
        with self._transaction():
            last = self._conn.execute('SELECT seq,at,digest FROM service_events ORDER BY seq DESC LIMIT 1').fetchone()
            at = _number(self.clock())
            if at < last[1]:
                raise ValueError('The explicit service clock moved backwards')
            if not self._allowed(actor, study_id, action, data):
                # Retain only access identity, never a denied request's payload.
                action, data, denied = 'denied', {'attempted_action': action}, True
            previous = self._conn.execute('SELECT payload FROM service_events WHERE event_id=?', (event_id,)).fetchone()
            if previous:
                retained = json.loads(previous[0])
                if any(retained[k] != v for k, v in {'actor': actor, 'study_id': study_id, 'action': action, 'data': data}.items()):
                    raise ValueError('Conflicting committed event identity')
                result = False
            else:
                body = {'seq': last[0] + 1, 'at': at, 'event_id': event_id, 'action': action,
                        'actor': actor, 'study_id': study_id, 'history_id': self.history_id,
                        'previous': last[2], 'data': data}
                event = {**body, 'digest': _digest(body)}
                result = self._apply(event)
                _insert_event(self._conn, event)
        if denied:
            raise PermissionError('Study operation denied by application policy')
        return result

    def _events(self):
        events = []
        for seq, at, identity, payload, digest in self._conn.execute('SELECT * FROM service_events ORDER BY seq'):
            event = json.loads(payload)
            if (event.get('seq'), event.get('at'), event.get('event_id'), event.get('digest')) != (seq, at, identity, digest):
                raise ValueError('Event index differs from its committed payload')
            events.append(event)
        return events

    def events(self, actor):
        """Admin-only, audited history; may include protected final records."""
        return self._perform(actor, None, 'read:events', {})

    def _json_row(self, table, key, value):
        row = self._conn.execute('SELECT payload FROM ' + table + ' WHERE ' + key + '=?', (value,)).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, table, key, value, payload):
        self._conn.execute('INSERT OR REPLACE INTO ' + table + ' (' + key + ',payload) VALUES (?,?)', (value, canonical(payload).decode()))

    def _apply(self, event):
        action, data, actor, sid = (event[k] for k in ('action', 'data', 'actor', 'study_id'))
        if action != 'denied' and not self._allowed(actor, sid, action, data):
            raise ValueError('Event is not authorized by the preceding policy')
        if action in ('denied', 'export', 'read:audit', 'read:metrics'):
            return None
        if action == 'read:events':
            return self._events()
        if action == 'read:quota':
            quota = self._json_row('service_quotas', 'quota_id', data['quota_id'])
            if quota is None:
                raise ValueError('Unknown quota')
            return self._usage(quota)
        if action == 'project':
            _id(sid); _id(data['owner'])
            if self._conn.execute('SELECT 1 FROM service_members WHERE study_id=?', (sid,)).fetchone():
                raise ValueError('Project already exists')
            active = self._conn.execute("SELECT COUNT(*) FROM service_members WHERE principal=? AND role='owner' AND active=1", (data['owner'],)).fetchone()[0]
            for quota in self._quotas():
                if quota['subject'] == data['owner'] and quota['start_us'] <= event['at'] < quota['end_us'] and active >= quota['max_active_studies']:
                    raise WorkBudgetExceeded('Active study quota exhausted before project creation')
            self._conn.execute('INSERT INTO service_members VALUES (?,?,?,1)', (sid, data['owner'], 'owner'))
        elif action == 'grant':
            _id(data['principal'])
            if data['role'] not in ROLES:
                raise ValueError('Unknown study role')
            owner = self._conn.execute("SELECT principal FROM service_members WHERE study_id=? AND role='owner'", (sid,)).fetchone()
            if owner is None or data['principal'] == owner[0] or data['role'] == 'owner':
                raise ValueError('Owner transfer requires a separate explicit contract')
            if not self._conn.execute('SELECT 1 FROM service_members WHERE study_id=? AND active=1', (sid,)).fetchone():
                raise ValueError('Closed projects cannot acquire new active members')
            self._conn.execute('INSERT OR REPLACE INTO service_members VALUES (?,?,?,1)', (sid, data['principal'], data['role']))
        elif action == 'close_project':
            if not self._conn.execute('SELECT 1 FROM service_members WHERE study_id=?', (sid,)).fetchone():
                raise ValueError('Unknown project')
            self._conn.execute('UPDATE service_members SET active=0 WHERE study_id=?', (sid,))
        elif action.startswith('write:'):
            self._apply_store(action[6:], sid, data)
        elif action.startswith('read:'):
            method = action[5:]
            if method not in READS:
                raise ValueError('Unknown store read')
            return getattr(self._store, method)(*data['args'])
        elif action == 'quota':
            self._apply_quota(data)
        elif action == 'reserve':
            return self._reserve(event)
        elif action == 'finish':
            self._finish(event)
        elif action == 'schedule':
            self._configure_schedule(data)
        elif action == 'claim':
            schedule = self._json_row('service_schedules', 'schedule_id', data['schedule_id'])
            if schedule is None or schedule['next_us'] != data['due_us'] or event['at'] < data['due_us']:
                raise _ClaimUnavailable('Schedule occurrence is no longer due')
            self._require_dispatch_enabled()
            if any(o['schedule_id'] == data['schedule_id'] and o['status'] != 'completed'
                   for o in self._occurrences()):
                raise _ClaimUnavailable('A preceding occurrence requires reconciliation')
            if data['occurrence_id'] != _digest({'history_id': self.history_id,
                    'schedule_id': data['schedule_id'], 'due_us': data['due_us']}):
                raise ValueError('Schedule occurrence identity differs')
            occurrence = {**data, 'status': 'claimed', 'kind': schedule['kind'], 'details': None}
            if self._json_row('service_occurrences', 'occurrence_id', data['occurrence_id']):
                raise ValueError('Schedule occurrence already claimed')
            schedule['next_us'] += schedule['interval_us']
            _number(schedule['next_us'])
            self._put('service_schedules', 'schedule_id', data['schedule_id'], schedule)
            self._put('service_occurrences', 'occurrence_id', data['occurrence_id'], occurrence)
        elif action == 'occurrence_done':
            occurrence = self._json_row('service_occurrences', 'occurrence_id', data['occurrence_id'])
            if occurrence is None or occurrence['status'] != 'claimed' or data['status'] not in ('completed', 'uncertain'):
                raise ValueError('Occurrence is not awaiting completion')
            occurrence.update(status=data['status'], details=data['details'])
            self._put('service_occurrences', 'occurrence_id', data['occurrence_id'], occurrence)
            if occurrence['kind'] == 'backup' and data['status'] == 'completed':
                schedule = self._json_row('service_schedules', 'schedule_id', occurrence['schedule_id'])
                schedule['after_seq'] = data['details']['end_seq']
                self._put('service_schedules', 'schedule_id', occurrence['schedule_id'], schedule)
        elif action == 'alert':
            if self._json_row('service_alerts', 'alert_id', data['alert_id']):
                raise ValueError('Alert identity already exists')
            self._put('service_alerts', 'alert_id', data['alert_id'], data)
        elif action == 'deliver':
            self._require_dispatch_enabled()
            alert = self._json_row('service_alerts', 'alert_id', data['alert_id'])
            if alert is None or alert['status'] != 'pending':
                raise ValueError('Alert cannot be dispatched again')
            alert['status'] = 'delivering'
            self._put('service_alerts', 'alert_id', data['alert_id'], alert)
            return True
        elif action == 'delivered':
            alert = self._json_row('service_alerts', 'alert_id', data['alert_id'])
            if alert is None or alert['status'] != 'delivering' or data['status'] not in ('completed', 'uncertain'):
                raise ValueError('Alert is not awaiting acknowledgement')
            alert['status'] = data['status']
            self._put('service_alerts', 'alert_id', data['alert_id'], alert)
        elif action == 'reconcile':
            if (data.get('writers_fenced') is not True
                    or data.get('later_reservations_reconciled') is not True):
                raise ValueError('Recovery dispatch requires fencing and reconciliation evidence')
            _id(data.get('evidence_id'))
            self._conn.execute('UPDATE service_meta SET recovery=0')
        elif action == 'migrate':
            if self._conn.execute('PRAGMA user_version').fetchone()[0] != 1 or data != {'from': 1, 'to': 2}:
                raise ValueError('Unsupported service migration')
            self._conn.execute('CREATE INDEX idx_service_events_at ON service_events(at,seq)')
            self._conn.execute('PRAGMA user_version=2')
        else:
            raise ValueError('Unknown committed service operation')
        return True

    def _apply_store(self, method, sid, data):
        if method not in WRITES:
            raise ValueError('Unknown store mutation')
        project = self._conn.execute('SELECT active FROM service_members WHERE study_id=? LIMIT 1', (sid,)).fetchone()
        if project is None or not project[0]:
            raise ValueError('Study project is absent or closed')
        args = data['args']
        if method == 'save_study_snapshot':
            state = args[0]
            if state['study_name'] != sid:
                raise ValueError('Snapshot belongs to another project')
            tids = list(state['trials'])
        elif method == 'write_study':
            if args[0]['study_id'] != sid:
                raise ValueError('Study belongs to another project')
            args = [StudyRecord(**args[0])]; tids = []
        elif method == 'write_trial':
            if args[1] != sid:
                raise ValueError('Trial belongs to another project')
            tids = [args[0]['trial_id']]
            args = [TrialRecord(**args[0]), sid]
        else:
            tids = [args[0]]
            row = self._conn.execute('SELECT study_id FROM trials WHERE trial_id=?', (args[0],)).fetchone()
            if row is None or row[0] != sid:
                raise ValueError('Trial does not belong to this project')
        for tid in tids:
            row = self._conn.execute('SELECT study_id FROM trials WHERE trial_id=?', (tid,)).fetchone()
            if row is not None and row[0] != sid:
                raise ValueError('Trial identity belongs to another project')
        getattr(self._store, method)(*args, **data.get('kwargs', {}))

    def _require_dispatch_enabled(self):
        if self._conn.execute('SELECT recovery FROM service_meta').fetchone()[0]:
            raise WorkBudgetExceeded('Historical recovery is observation-only until reconciled')

    def project(self, actor, study_id, *, owner, event_id):
        return self._perform(actor, study_id, 'project', {'owner': _id(owner)}, event_id=event_id)

    def grant(self, actor, study_id, principal, role, *, event_id):
        return self._perform(actor, study_id, 'grant', {'principal': _id(principal), 'role': role}, event_id=event_id)

    def close_project(self, actor, study_id, *, event_id):
        return self._perform(actor, study_id, 'close_project', {}, event_id=event_id)

    def store(self, actor, study_id):
        return ScopedStudyStore(self, _id(actor), _id(study_id))

    def _quotas(self):
        return [json.loads(row[0]) for row in self._conn.execute('SELECT payload FROM service_quotas ORDER BY quota_id')]

    def _apply_quota(self, data):
        expected = {'quota_id', 'subject', 'period_id', 'start_us', 'end_us', 'device',
                    'device_limit_us', 'currency', 'cost_limit_micros', 'price_id',
                    'price_micros_per_hour', 'max_active_studies'}
        if set(data) != expected:
            raise ValueError('Quota must declare period, device, currency and price')
        for key in ('quota_id', 'subject', 'period_id', 'device', 'currency', 'price_id'):
            _id(data[key])
        for key in expected - {'quota_id', 'subject', 'period_id', 'device', 'currency', 'price_id'}:
            _number(data[key], key)
        if data['end_us'] <= data['start_us'] or not re.fullmatch('[A-Z]{3}', data['currency']):
            raise ValueError('Quota requires a half-open period and currency code')
        for prior in self._quotas():
            if prior['quota_id'] == data['quota_id']:
                raise ValueError('Quota/price identity is immutable')
            if (prior['subject'] == data['subject'] and prior['device'] == data['device']
                    and max(prior['start_us'], data['start_us']) < min(prior['end_us'], data['end_us'])):
                raise ValueError('Accounting periods overlap for this subject/device')
        self._put('service_quotas', 'quota_id', data['quota_id'], data)

    def configure_quota(self, actor, *, event_id, **declaration):
        return self._perform(actor, None, 'quota', declaration, event_id=event_id)

    @staticmethod
    def _cost(device_us, quota):
        return (device_us * quota['price_micros_per_hour'] + HOUR_US - 1) // HOUR_US

    def _usage(self, quota):
        result = {'actual_device_us': 0, 'uncertain_device_us': 0, 'actual_cost_micros': 0,
                  'uncertain_cost_micros': 0, 'reservations': 0, 'missing_measurements': 0}
        for row in self._conn.execute('SELECT payload FROM service_reservations'):
            record = json.loads(row[0])
            if record['quota_id'] != quota['quota_id']:
                continue
            actual = record.get('measured_device_us')
            if actual is None:
                result['missing_measurements'] += 1
            actual = actual or 0
            upper = max(actual, record['device_us']) if record['status'] != 'completed' else actual
            result['actual_device_us'] += actual
            result['uncertain_device_us'] += upper - actual
            result['actual_cost_micros'] += self._cost(actual, quota)
            result['uncertain_cost_micros'] += self._cost(upper, quota) - self._cost(actual, quota)
            result['reservations'] += 1
        result.update(quota_id=quota['quota_id'], period_id=quota['period_id'], device=quota['device'],
                      currency=quota['currency'], price_id=quota['price_id'])
        result['charged_device_us'] = result['actual_device_us'] + result['uncertain_device_us']
        result['charged_cost_micros'] = result['actual_cost_micros'] + result['uncertain_cost_micros']
        return result

    def _reserve(self, event):
        data, actor, sid = event['data'], event['actor'], event['study_id']
        quota = self._json_row('service_quotas', 'quota_id', data['quota_id'])
        units = _number(data['device_us'], positive=True)
        self._require_dispatch_enabled()
        if (quota is None or quota['subject'] != actor
                or not quota['start_us'] <= event['at'] < quota['end_us']):
            raise WorkBudgetExceeded('No matching current user/device accounting period')
        membership = self._conn.execute('SELECT active FROM service_members WHERE study_id=? AND principal=?', (sid, actor)).fetchone()
        if membership is None or not membership[0]:
            raise WorkBudgetExceeded('Project is not active for this caller')
        usage = self._usage(quota)
        if (units > quota['device_limit_us'] - usage['charged_device_us']
                or self._cost(units, quota) > quota['cost_limit_micros'] - usage['charged_cost_micros']):
            raise WorkBudgetExceeded('Device-time or currency quota exhausted before dispatch')
        reservation = {**data, 'subject': actor, 'study_id': sid, 'status': 'reserved',
                       'measured_device_us': None, 'measurement_id': None,
                       'quota_binding': _digest(quota)}
        self._conn.execute('INSERT INTO service_reservations VALUES (?,?,NULL)', (event['event_id'], canonical(reservation).decode()))
        return True

    def reserve(self, actor, study_id, *, event_id, quota_id, device_us):
        """Only True authorizes dispatch. False is a spent, non-repeatable ID."""
        return self._perform(actor, study_id, 'reserve', {'quota_id': quota_id, 'device_us': device_us}, event_id=event_id)

    def _finish(self, event):
        data = event['data']
        record = self._json_row('service_reservations', 'reservation_id', data['reservation_id'])
        if (record is None or record['subject'] != event['actor']
                or record['study_id'] != event['study_id'] or record['status'] != 'reserved'):
            raise ValueError('Reservation is not awaiting this caller completion')
        if data['status'] not in ('completed', 'failed', 'lost'):
            raise ValueError('Unknown reservation completion status')
        measured = data['measured_device_us']
        if measured is None:
            if data['status'] == 'completed' or data['measurement_id'] is not None:
                raise ValueError('Successful completion needs an actual device-time measurement')
        else:
            _number(measured); _id(data['measurement_id'])
        record.update(status=data['status'], measured_device_us=measured, measurement_id=data['measurement_id'])
        # Actual overruns are retained; later admission sees the overdrawn quota.
        self._conn.execute('UPDATE service_reservations SET payload=?,measurement_id=? WHERE reservation_id=?',
                           (canonical(record).decode(), data['measurement_id'], data['reservation_id']))

    def finish(self, actor, study_id, *, event_id, reservation_id, status,
               measured_device_us=None, measurement_id=None):
        return self._perform(actor, study_id, 'finish', {'reservation_id': reservation_id,
            'status': status, 'measured_device_us': measured_device_us,
            'measurement_id': measurement_id}, event_id=event_id)

    def quota_report(self, actor, quota_id):
        return self._perform(actor, None, 'read:quota', {'quota_id': _id(quota_id)})

    def audit(self, actor):
        self._perform(actor, None, 'read:audit', {})
        return [dict(zip(('seq', 'at', 'actor', 'study_id', 'action', 'allowed'), row))
                for row in self._conn.execute('SELECT * FROM service_audit ORDER BY seq')]

    def acknowledge_recovery(self, actor, *, event_id, evidence_id,
                             writers_fenced, later_reservations_reconciled):
        return self._perform(actor, None, 'reconcile', {'evidence_id': evidence_id,
            'writers_fenced': writers_fenced, 'later_reservations_reconciled': later_reservations_reconciled}, event_id=event_id)

    def export_events(self, actor, destination, *, after_seq=0, key_id=None, key_provider=None):
        _number(after_seq, 'after sequence')
        if (key_id is None) != (key_provider is None):
            raise ValueError('Encrypted backup needs both key identifier and provider')
        self._perform(actor, None, 'export', {'after_seq': after_seq})
        with self._transaction():
            events = self._events()
            if after_seq >= len(events):
                raise ValueError('Incremental backup must include at least one new commit')
            previous = events[after_seq - 1]['digest'] if after_seq else ZERO
            segment = {'format': 'hponas_events_v1', 'history_id': self.history_id,
                       'start_seq': after_seq + 1, 'end_seq': len(events), 'previous': previous,
                       'head': events[-1]['digest'], 'events': events[after_seq:]}
        artifact = encrypt_backup(segment, key_id=key_id, key_provider=key_provider) if key_id else segment
        _write_new(destination, artifact)
        return {k: segment[k] for k in ('history_id', 'start_seq', 'end_seq', 'previous', 'head')}

    def _configure_schedule(self, data):
        if set(data) != {'schedule_id', 'kind', 'interval_us', 'next_us', 'after_seq'}:
            raise ValueError('Schedule declaration differs')
        _id(data['schedule_id']); _number(data['interval_us'], positive=True); _number(data['next_us'])
        if data['kind'] not in ('backup', 'monitor') or data['after_seq'] != 0:
            raise ValueError('Unsupported schedule kind or initial backup cursor')
        if self._json_row('service_schedules', 'schedule_id', data['schedule_id']):
            raise ValueError('Schedule identity is immutable')
        self._put('service_schedules', 'schedule_id', data['schedule_id'], data)

    def configure_schedule(self, actor, *, event_id, schedule_id, kind, interval_us, start_us):
        return self._perform(actor, None, 'schedule', {'schedule_id': schedule_id, 'kind': kind,
            'interval_us': interval_us, 'next_us': start_us, 'after_seq': 0}, event_id=event_id)

    def _occurrences(self):
        return [json.loads(row[0]) for row in self._conn.execute('SELECT payload FROM service_occurrences')]

    def _claim(self, actor, schedule):
        schedule_id = schedule['schedule_id']
        occurrence_id = _digest({'history_id': self.history_id, 'schedule_id': schedule_id, 'due_us': schedule['next_us']})
        data = {'schedule_id': schedule_id, 'due_us': schedule['next_us'], 'occurrence_id': occurrence_id}
        try:
            new = self._perform(actor, None, 'claim', data, event_id='claim-' + occurrence_id)
        except _ClaimUnavailable:
            return None, None
        return (occurrence_id, schedule) if new else (None, None)

    def tick(self, actor, *, backup_directory, measurements=None, alert_sink=None,
             key_id=None, key_provider=None, max_occurrences=20):
        """Process bounded due work; claimed/uncertain effects are never repeated."""
        _number(max_occurrences, positive=True)
        if max_occurrences > 100:
            raise ValueError('One tick is bounded to 100 occurrences')
        # Authorize before directory creation, claims or sink invocations.
        self._perform(actor, None, 'read:metrics', {})
        self._require_dispatch_enabled()
        outcomes = []
        for _ in range(max_occurrences):
            now = _number(self.clock())
            with self._transaction():
                schedules = [json.loads(row[0]) for row in self._conn.execute('SELECT payload FROM service_schedules')]
                blocked = {o['schedule_id'] for o in self._occurrences() if o['status'] != 'completed'}
            due = sorted((s for s in schedules if s['next_us'] <= now and s['schedule_id'] not in blocked),
                         key=lambda s: (s['next_us'], s['schedule_id']))
            if not due:
                break
            occurrence_id, schedule = self._claim(actor, due[0])
            if occurrence_id is None:
                continue
            try:
                if schedule['kind'] == 'backup':
                    details = self.export_events(actor, Path(backup_directory)/(occurrence_id + '.json'),
                                                 after_seq=schedule['after_seq'], key_id=key_id, key_provider=key_provider)
                else:
                    details = self.monitor(actor, measurements or {}, occurrence_id=occurrence_id)
                status = 'completed'
            except Exception:
                # A callback exception can contain credentials. Retain a fixed
                # disposition, not an untrusted exception string.
                status, details = 'uncertain', {'reason': 'local_schedule_effect_failed'}
            self._perform(actor, None, 'occurrence_done', {'occurrence_id': occurrence_id,
                'status': status, 'details': details}, event_id='done-' + occurrence_id)
            outcomes.append({'occurrence_id': occurrence_id, 'status': status, 'details': details})
        if alert_sink is not None:
            self.deliver_alerts(actor, alert_sink, limit=max_occurrences)
        return outcomes

    def monitor(self, actor, measurements, *, occurrence_id):
        """Evaluate explicitly supplied measurements; no inferred CPU/GPU meter."""
        self._perform(actor, None, 'read:metrics', {})
        _id(occurrence_id)
        if not isinstance(measurements, dict):
            raise ValueError('Monitoring measurements must be a mapping')
        rules = {'error_rate': (.1, 'fraction'), 'latency_p99_seconds': (60, 'seconds'),
                 'queue_depth': (1000, 'count'), 'disk_fraction': (.8, 'fraction')}
        if set(measurements) - set(rules):
            raise ValueError('Unknown monitoring metric or unit')
        alerts = []
        # Validate the entire sample before adding any alert to the outbox.
        for metric, sample in sorted(measurements.items()):
            threshold, unit = rules[metric]
            if (not isinstance(sample, dict) or set(sample) != {'value', 'unit', 'measurement_id'}
                    or sample['unit'] != unit or type(sample['value']) not in (int, float)
                    or not 0 <= sample['value'] < float('inf')):
                raise ValueError('A finite measured value, unit and identity are required')
            if unit == 'fraction' and sample['value'] > 1 or unit == 'count' and type(sample['value']) is not int:
                raise ValueError('Fraction/count monitoring units differ')
            _id(sample['measurement_id'])
        for metric, sample in sorted(measurements.items()):
            threshold, _ = rules[metric]
            if sample['value'] > threshold:
                alert_id = _digest({'occurrence_id': occurrence_id, 'metric': metric})
                data = {'alert_id': alert_id, 'status': 'pending', 'metric': metric,
                        'sample': sample, 'threshold': threshold, 'occurrence_id': occurrence_id}
                self._perform(actor, None, 'alert', data, event_id='alert-' + alert_id)
                alerts.append(alert_id)
        return {'alerts': alerts, 'measurement_ids': [s['measurement_id'] for s in measurements.values()]}

    def deliver_alerts(self, actor, sink, *, limit=20):
        self._perform(actor, None, 'read:metrics', {})
        self._require_dispatch_enabled()
        _number(limit, positive=True)
        if limit > 100:
            raise ValueError('Alert delivery is bounded')
        rows = [json.loads(row[0]) for row in self._conn.execute('SELECT payload FROM service_alerts ORDER BY alert_id')]
        for alert in [r for r in rows if r['status'] == 'pending'][:limit]:
            aid = alert['alert_id']
            if not self._perform(actor, None, 'deliver', {'alert_id': aid}, event_id='deliver-' + aid):
                continue
            try:
                sink.send(aid, alert)
                status = 'completed'
            except Exception:
                status = 'uncertain'
            self._perform(actor, None, 'delivered', {'alert_id': aid, 'status': status}, event_id='delivered-' + aid)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ScopedStudyStore:
    """Policy-checked checkpoint Store for a single caller and study."""
    def __init__(self, service, actor, study_id):
        self._service, self._actor, self._study_id = service, actor, study_id

    def save_study_snapshot(self, state):
        return self._service._perform(self._actor, self._study_id, 'write:save_study_snapshot', {'args': [state]})

    def load_study_snapshot(self, study_id):
        return self._read('load_study_snapshot', study_id)

    def _read(self, method, identity):
        return self._service._perform(self._actor, self._study_id, 'read:' + method, {'args': [identity]})

    def __getattr__(self, name):
        if name in READS:
            return lambda identity: self._read(name, identity)
        raise AttributeError(name)


class DirectoryAlertSink:
    """Local idempotent sink. No network, email or external delivery."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def send(self, occurrence_id, payload):
        if not re.fullmatch('[a-f0-9]{64}', occurrence_id):
            raise ValueError('Invalid local alert occurrence identity')
        destination = self.directory/(occurrence_id + '.json')
        if destination.exists():
            if destination.is_symlink() or json.loads(destination.read_text()) != payload:
                raise ValueError('Conflicting local alert receipt')
            return
        _write_new(destination, payload)


def _insert_event(connection, event):
    connection.execute('INSERT INTO service_events VALUES (?,?,?,?,?)',
                       (event['seq'], event['at'], event['event_id'], canonical(event).decode(), event['digest']))
    connection.execute('INSERT INTO service_audit VALUES (?,?,?,?,?,?)',
                       (event['seq'], event['at'], event['actor'], event['study_id'], event['action'], int(event['action'] != 'denied')))


def _verify_events(events, history_id):
    previous, at, identities = ZERO, 0, set()
    expected = {'seq', 'at', 'event_id', 'action', 'actor', 'study_id', 'history_id', 'previous', 'data', 'digest'}
    if not events:
        raise ValueError('Committed history is empty')
    for seq, event in enumerate(events, 1):
        if (not isinstance(event, dict) or set(event) != expected
                or type(event['seq']) is not int or event['seq'] != seq
                or event['previous'] != previous or event['history_id'] != history_id
                or _number(event['at']) < at or event['event_id'] in identities
                or event['digest'] != _digest({k: v for k, v in event.items() if k != 'digest'})):
            raise ValueError('Committed event integrity or ordering differs')
        _id(event['event_id']); _id(event['actor'])
        _id(event['action'])
        if event['study_id'] is not None:
            _id(event['study_id'])
        if not isinstance(event['data'], dict):
            raise ValueError('Committed operation data must be a mapping')
        if (seq == 1) != (event['action'] == 'genesis'):
            raise ValueError('Committed history requires exactly one leading genesis')
        identities.add(event['event_id']); previous, at = event['digest'], event['at']


def _remove_temporary(path):
    for suffix in ('', '-wal', '-shm', '-journal'):
        try:
            os.unlink(str(path) + suffix)
        except FileNotFoundError:
            pass


def _prepare_database(temporary):
    with closing(sqlite3.connect(temporary)) as connection:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        connection.execute('PRAGMA journal_mode=DELETE')
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Reconstructed database integrity failed')
    with open(temporary, 'rb') as stream:
        os.fsync(stream.fileno())


def _publish_database(temporary, destination):
    _fresh(destination)
    _prepare_database(temporary)
    os.link(temporary, destination)
    descriptor = os.open(Path(destination).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def import_legacy_store(source, destination, backup_directory, *, admin, clock=None):
    """Offline exact-schema 0-to-1 migration; the source remains untouched."""
    _id(admin); destination = _fresh(destination)
    with closing(_read_only(source)) as connection:
        if (_schema(connection) != _legacy_schema()
                or connection.execute('PRAGMA user_version').fetchone()[0] != 0
                or connection.execute('PRAGMA application_id').fetchone()[0] != 0):
            raise ValueError('Unsupported legacy schema or identity')
    return _migrate(source, destination, backup_directory, admin=admin, clock=clock, legacy=True)


def migrate_service(source, destination, backup_directory, *, actor, clock=None):
    """Offline explicit service-schema 1-to-2 migration with verified rollback."""
    destination = _fresh(destination)
    with ManagedStudyService(source, clock=clock) as service:
        if actor != service.admin:
            raise PermissionError('Only the service owner may migrate')
        if service.version != 1:
            raise ValueError('Only service schema 1-to-2 is supported')
    return _migrate(source, destination, backup_directory, admin=actor, clock=clock, legacy=False)


def _migrate(source, destination, backup_directory, *, admin, clock, legacy):
    backup = backup_database(source, backup_directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.migrate-', dir=destination.parent); os.close(fd); os.unlink(temporary)
    try:
        restore_database(backup_directory, temporary)
        if legacy:
            ManagedStudyService._initialize(temporary, admin=admin, clock=clock)
        else:
            with ManagedStudyService(temporary, clock=clock) as service:
                service._perform(admin, None, 'migrate', {'from': 1, 'to': 2}, event_id='schema-1-to-2')
        with ManagedStudyService(temporary, clock=clock) as service:
            manifest = {'format': 'hponas_service_migration_v1', 'from_version': 0 if legacy else 1,
                        'to_version': 1 if legacy else 2, 'backup': backup,
                        'backup_directory': str(Path(backup_directory).resolve()),
                        'destination': str(destination.resolve()),
                        'publication': 'prepared_record_requires_matching_destination',
                        'history_id': service.history_id, 'head': service._events()[-1]['digest']}
        _prepare_database(temporary)
        manifest['destination_sha256'] = hashlib.sha256(Path(temporary).read_bytes()).hexdigest()
        # A crash may leave this prepared record without a destination. It must
        # never leave a published migration without its durable predecessor record.
        _write_new(Path(backup_directory)/'migration.json', manifest)
        _publish_database(temporary, destination)
        return manifest
    finally:
        _remove_temporary(temporary)


def rollback_migration(manifest, destination, *, expected_manifest_sha256=None):
    if (manifest.get('format') != 'hponas_service_migration_v1'
            or (manifest.get('from_version'), manifest.get('to_version')) not in ((0, 1), (1, 2))):
        raise ValueError('Unsupported migration manifest')
    directory = Path(manifest['backup_directory'])
    if (directory.is_symlink() or (directory/'migration.json').is_symlink()
            or json.loads((directory/'migration.json').read_text()) != manifest
            or json.loads((directory/'manifest.json').read_text()) != manifest['backup']
            or expected_manifest_sha256 is not None and _digest(manifest) != expected_manifest_sha256):
        raise ValueError('Migration predecessor binding differs')
    inventory = manifest['backup']['inventory']
    if (inventory['user_version'] != manifest['from_version']
            or inventory['application_id'] != (0 if manifest['from_version'] == 0 else APPLICATION_ID)):
        raise ValueError('Migration predecessor version differs')
    return restore_database(directory, destination)


def restore_events(segments, destination, *, through_sequence=None, through_time_us=None,
                   expected_head=None, key_provider=None):
    """Verify the full supplied history, then publish an inclusive prefix.

    ``expected_head`` must come from separately retained evidence if truncation
    detection is required. A recovered copy cannot grant new physical work until
    writers and any later reservations have been explicitly reconciled.
    """
    destination = _fresh(destination)
    if through_sequence is not None and through_time_us is not None:
        raise ValueError('Choose exactly one sequence or time cutoff')
    if through_sequence is not None:
        _number(through_sequence, 'sequence cutoff', positive=True)
    if through_time_us is not None:
        _number(through_time_us, 'time cutoff')
    events, history_id, previous = [], None, ZERO
    for path in segments:
        path = Path(path)
        if path.is_symlink():
            raise ValueError('Backup symlinks are unsupported')
        segment = json.loads(path.read_text())
        if not isinstance(segment, dict):
            raise ValueError('Incremental backup must be a mapping')
        if segment.get('format') == 'hponas_encrypted_events_v1':
            segment = decrypt_backup(segment, key_provider=key_provider)
        if (set(segment) != {'format', 'history_id', 'start_seq', 'end_seq', 'previous', 'head', 'events'}
                or segment['format'] != 'hponas_events_v1' or not segment['events']
                or segment['start_seq'] != len(events) + 1
                or segment['end_seq'] != len(events) + len(segment['events'])
                or segment['previous'] != previous
                or segment['head'] != segment['events'][-1]['digest']
                or history_id is not None and history_id != segment['history_id']):
            raise ValueError('Incremental segment identity, gap or ordering differs')
        history_id = segment['history_id']; previous = segment['head']
        events.extend(segment['events'])
    _verify_events(events, history_id)
    if expected_head is not None and previous != expected_head:
        raise ValueError('Supplied committed history is truncated or has a different head')
    if through_sequence is not None:
        if through_sequence > len(events):
            raise ValueError('Sequence cutoff exceeds retained committed history')
        selected = events[:through_sequence]
    elif through_time_us is not None:
        selected = [event for event in events if event['at'] <= through_time_us]
    else:
        selected = events
    if not selected:
        raise ValueError('Recovery cutoff precedes the genesis commit')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.replay-', dir=destination.parent); os.close(fd)
    try:
        store = Store(temporary); store.close()
        genesis = selected[0]
        if (genesis['data'].get('version') not in (1, 2)
                or set(genesis['data'].get('tables', {})) != set(BASE_TABLES)
                or genesis['actor'] != genesis['data'].get('admin')):
            raise ValueError('Unsupported genesis state')
        with closing(sqlite3.connect(temporary, isolation_level=None)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            for table in BASE_TABLES:
                connection.execute('DELETE FROM "' + table + '"')
                for row in genesis['data']['tables'][table]:
                    connection.execute('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in row) + ')', row)
            # Isolated replay checks the original admission decisions; it cannot
            # dispatch physical work. The published copy is fenced below.
            _install(connection, history_id=history_id, admin=genesis['actor'], version=genesis['data']['version'])
            for row in genesis['data']['tables']['studies']:
                connection.execute('INSERT INTO service_members VALUES (?,?,?,1)', (row[0], genesis['actor'], 'owner'))
            _insert_event(connection, genesis)
            connection.commit()
        with ManagedStudyService(temporary, clock=lambda: selected[-1]['at']) as service:
            with service._transaction():
                for event in selected[1:]:
                    service._apply(event)
                    _insert_event(service._conn, event)
                # Replaying a past reconciliation must not authorize a new copy.
                service._conn.execute('UPDATE service_meta SET recovery=1')
        _publish_database(temporary, destination)
    finally:
        _remove_temporary(temporary)
    return {'history_id': history_id, 'through_sequence': selected[-1]['seq'],
            'through_time_us': selected[-1]['at'], 'head': selected[-1]['digest'],
            'dispatch': 'requires_fencing_and_reservation_reconciliation'}
