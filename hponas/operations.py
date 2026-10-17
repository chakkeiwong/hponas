"""Local work admission, SQLite backup and operational status.

These primitives do not certify a distributed service. Costly operations must
cooperate with the ledger: a replayed debit never grants another execution.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from urllib.parse import quote

from hponas.persistence import atomic_json


class WorkBudgetExceeded(RuntimeError):
    """No work was admitted because the durable capacity is exhausted."""


def _integer(value, name, *, positive=True):
    if type(value) is not int or not (int(positive) <= value < 2**63):
        raise ValueError(name+' must be a bounded integer')
    return value


def _identity(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError('A nonempty bounded event/study/unit identity is required')
    return value


class LocalWorkLedger:
    """Atomic prepaid work bound across studies on one local filesystem.

    ``charge`` returns True exactly once per event. Only True permits executing
    that event's costly operation. False means the identity was already spent;
    it never means permission to rerun. A crash after charge leaves conservative
    uncertain consumption. Capacity cannot be changed by reopening the ledger.
    """
    APPLICATION_ID = 0x48504F4C
    VERSION = 1

    def __init__(self, path, *, capacity, unit='gradient_update'):
        _integer(capacity, 'capacity')
        _identity(unit)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError('Ledger symlinks are unsupported')
        self.connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            with self._transaction():
                version = self.connection.execute('PRAGMA user_version').fetchone()[0]
                application = self.connection.execute('PRAGMA application_id').fetchone()[0]
                tables = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not tables and version == application == 0:
                    self.connection.execute('CREATE TABLE settings (capacity INTEGER NOT NULL, unit TEXT NOT NULL)')
                    self.connection.execute('CREATE TABLE charges (event_id TEXT PRIMARY KEY, study_id TEXT NOT NULL, units INTEGER NOT NULL CHECK(units>0), completed INTEGER NOT NULL CHECK(completed IN (0,1)))')
                    self.connection.execute('INSERT INTO settings VALUES (?,?)', (capacity, unit))
                    self.connection.execute(f'PRAGMA application_id={self.APPLICATION_ID}')
                    self.connection.execute(f'PRAGMA user_version={self.VERSION}')
                elif (application != self.APPLICATION_ID or version != self.VERSION
                      or tables != {'settings', 'charges'}):
                    raise ValueError('Unsupported ledger database identity/schema')
                rows = self.connection.execute('SELECT capacity,unit FROM settings').fetchall()
                if rows != [(capacity, unit)]:
                    raise ValueError('Ledger capacity/unit contract differs')
        except BaseException:
            self.connection.close()
            raise

    @contextmanager
    def _transaction(self):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def charge(self, event_id, study_id, units=1):
        _identity(event_id); _identity(study_id); _integer(units, 'units')
        with self._transaction():
            prior = self.connection.execute('SELECT study_id,units FROM charges WHERE event_id=?', (event_id,)).fetchone()
            if prior is not None:
                if prior != (study_id, units):
                    raise ValueError('Conflicting work event identity')
                return False
            capacity = self.connection.execute('SELECT capacity FROM settings').fetchone()[0]
            spent = self.connection.execute('SELECT COALESCE(SUM(units),0) FROM charges').fetchone()[0]
            if units > capacity-spent:
                raise WorkBudgetExceeded('Durable work capacity exhausted before dispatch')
            self.connection.execute('INSERT INTO charges VALUES (?,?,?,0)', (event_id, study_id, units))
        return True

    def complete(self, event_id):
        _identity(event_id)
        with self._transaction():
            row = self.connection.execute('SELECT completed FROM charges WHERE event_id=?', (event_id,)).fetchone()
            if row is None:
                raise ValueError('Cannot acknowledge an uncharged event')
            self.connection.execute('UPDATE charges SET completed=1 WHERE event_id=?', (event_id,))

    def metrics(self):
        # One read transaction prevents mixing counters from separate commits.
        with self._transaction():
            capacity, unit = self.connection.execute('SELECT capacity,unit FROM settings').fetchone()
            total, done, count = self.connection.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(units*completed),0),COUNT(*) FROM charges').fetchone()
        return {'capacity': capacity, 'unit': unit, 'charged_units': total,
            'completed_units': done, 'uncertain_units': total-done,
            'remaining_units': capacity-total, 'events': count}

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _read_only(path):
    return sqlite3.connect('file:'+quote(str(Path(path).resolve()), safe='/')+'?mode=ro', uri=True)


def database_inventory(path, *, max_seconds=30):
    """Read integrity and version metadata without creating an absent database."""
    _integer(max_seconds, 'inventory time limit')
    started = time.monotonic()
    with closing(_read_only(path)) as connection:
        connection.execute(f'PRAGMA busy_timeout={min(max_seconds, 5)*1000}')
        connection.set_progress_handler(lambda: time.monotonic()-started >= max_seconds, 1000)
        connection.execute('BEGIN')
        integrity = connection.execute('PRAGMA integrity_check').fetchall()
        if integrity != [('ok',)]:
            raise ValueError('Database integrity check failed')
        schema = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()
        counts = {}
        for kind, name, _ in schema:
            if kind == 'table':
                identifier = '"'+name.replace('"', '""')+'"'
                counts[name] = connection.execute('SELECT COUNT(*) FROM '+identifier).fetchone()[0]
        return {'user_version': connection.execute('PRAGMA user_version').fetchone()[0],
            'application_id': connection.execute('PRAGMA application_id').fetchone()[0],
            'schema_sha256': hashlib.sha256(json.dumps(schema).encode()).hexdigest(),
            'table_counts': counts, 'integrity': 'ok'}


def _sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def backup_database(database, directory, *, max_seconds=30):
    """Online SQLite snapshot. Referenced external artifacts are not copied."""
    directory = Path(directory)
    _integer(max_seconds, 'backup time limit')
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    target = directory/'database.sqlite3'
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic()-started >= max_seconds:
            raise TimeoutError('Online backup exceeded its time limit')
    with closing(_read_only(database)) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination, pages=256, progress=progress, sleep=.01)
        # A source in WAL mode transfers the WAL mode to the destination. Close
        # the snapshot as a standalone database before hashing it; publishing a
        # database with an untracked sidecar would make the manifest incomplete.
        destination.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        destination.execute('PRAGMA journal_mode=DELETE')
        destination.commit()
    with target.open('rb') as handle:
        os.fsync(handle.fileno())
    manifest = {'schema': 'sqlite_backup_v1', 'filename': target.name,
        'sha256': _sha(target), 'inventory': database_inventory(target),
        'scope': 'database_only_external_artifacts_require_separate_retention'}
    atomic_json(directory/'manifest.json', manifest)
    return manifest


def ledger_status(path):
    """Observe an existing ledger without creating files or changing its limit."""
    with closing(_read_only(path)) as connection:
        connection.execute('BEGIN')
        if (connection.execute('PRAGMA application_id').fetchone()[0] != LocalWorkLedger.APPLICATION_ID
                or connection.execute('PRAGMA user_version').fetchone()[0] != LocalWorkLedger.VERSION):
            raise ValueError('Unsupported ledger identity/schema')
        settings = connection.execute('SELECT capacity,unit FROM settings').fetchall()
        if len(settings) != 1:
            raise ValueError('Ledger capacity is ambiguous')
        capacity, unit = settings[0]
        _integer(capacity, 'capacity'); _identity(unit)
        charged, completed, count = connection.execute('SELECT COALESCE(SUM(units),0),COALESCE(SUM(units*completed),0),COUNT(*) FROM charges').fetchone()
        if not 0 <= completed <= charged <= capacity:
            raise ValueError('Ledger conservation is violated')
        return {'capacity': capacity, 'unit': unit, 'charged_units': charged,
            'completed_units': completed, 'uncertain_units': charged-completed,
            'remaining_units': capacity-charged, 'events': count,
            'status': 'uncertain_work_requires_reconciliation' if charged != completed else 'ok'}


def restore_database(directory, destination):
    """Verify before exclusive publication; never replace an existing database."""
    directory, destination = Path(directory), Path(destination)
    manifest_path = directory/'manifest.json'
    source = directory/'database.sqlite3'
    if directory.is_symlink() or manifest_path.is_symlink() or source.is_symlink():
        raise ValueError('Backup symlinks are unsupported')
    # A backup is a closed database. Sidecars can change query results without
    # changing the database file checksum or its schema/table counts.
    if any(os.path.lexists(str(source)+suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Backup requires a database without journal sidecars')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if any(os.path.lexists(str(destination)+suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Restore destination has orphan journal sidecars')
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('schema') != 'sqlite_backup_v1' or manifest.get('filename') != source.name
            or manifest.get('sha256') != _sha(source) or manifest.get('inventory') != database_inventory(source)):
        raise ValueError('Backup identity, bytes or inventory differs')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.restore-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush(); os.fsync(output.fileno())
        if (_sha(temporary) != manifest['sha256']
                or database_inventory(temporary) != manifest['inventory']):
            raise ValueError('Backup changed during restore')
        os.link(temporary, destination)  # atomic refusal if another writer won
        parent = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        os.unlink(temporary)
    return manifest
