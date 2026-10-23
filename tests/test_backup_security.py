"""Authenticated artifact boundary and refusal without leaking provider material."""
import builtins
import copy
import json

import pytest

from hponas.backup_security import encrypt_backup, decrypt_backup
from hponas.local_service import ManagedStudyService, restore_events


class Keys:
    def __init__(self, key=b'k'*32): self.key = key
    def get_key(self, key_id):
        assert key_id == 'local-test-v1'
        return self.key


def test_encrypted_service_export_and_recovery_contains_no_plaintext(tmp_path):
    with ManagedStudyService.create(tmp_path/'service.db', admin='private-principal') as service:
        summary = service.export_events('private-principal', tmp_path/'encrypted.json', key_id='local-test-v1', key_provider=Keys())
    raw = (tmp_path/'encrypted.json').read_text()
    assert 'private-principal' not in raw and (b'k'*32).decode() not in raw
    restored = restore_events([tmp_path/'encrypted.json'], tmp_path/'restored.db', key_provider=Keys(), expected_head=summary['head'])
    assert restored['head'] == summary['head']
    with pytest.raises(ValueError):
        restore_events([tmp_path/'encrypted.json'], tmp_path/'wrong-key.db', key_provider=Keys(b'x'*32))
    assert not (tmp_path/'wrong-key.db').exists()


@pytest.mark.parametrize('field', ['ciphertext', 'nonce', 'head', 'key_id', 'algorithm', 'start_seq'])
def test_changed_ciphertext_or_authenticated_header_is_refused(field):
    segment = dict(history_id='history', start_seq=1, end_seq=1, previous='0'*64, head='a'*64, events=[{'secret': 'private'}])
    artifact = encrypt_backup(segment, key_id='local-test-v1', key_provider=Keys())
    changed = copy.deepcopy(artifact)
    changed[field] = 2 if field == 'start_seq' else 'altered'
    with pytest.raises(ValueError): decrypt_backup(changed, key_provider=Keys())


def test_provider_exceptions_invalid_keys_and_missing_library_fail_explicitly(monkeypatch):
    segment = dict(history_id='history', start_seq=1, end_seq=1, previous='0'*64, head='a'*64)

    class FailedProvider:
        def get_key(self, key_id): raise RuntimeError('sensitive-provider-material')

    for provider in [None, FailedProvider(), Keys(b'short'), Keys('not-bytes')]:
        with pytest.raises(ValueError) as caught:
            encrypt_backup(segment, key_id='local-test-v1', key_provider=provider)
        assert 'sensitive-provider-material' not in str(caught.value)
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name.startswith('cryptography'): raise ImportError('missing fixture')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(RuntimeError, match=r'hponas\[security\]'):
        encrypt_backup(segment, key_id='local-test-v1', key_provider=Keys())


def test_scheduled_provider_failure_is_redacted_retained_and_not_retried(tmp_path):
    class FailedProvider:
        calls = 0

        def get_key(self, key_id):
            self.calls += 1
            raise RuntimeError('sensitive-provider-material')

    provider, clock = FailedProvider(), lambda: 20
    with ManagedStudyService.create(tmp_path/'service.db', admin='admin', clock=clock) as service:
        service.configure_schedule('admin', event_id='schedule', schedule_id='encrypted',
            kind='backup', interval_us=10, start_us=20)
        outcomes = service.tick('admin', backup_directory=tmp_path/'backups',
            key_id='local-test-v1', key_provider=provider)
        assert len(outcomes) == 1 and outcomes[0]['status'] == 'uncertain'
        assert not (tmp_path/'backups').exists()
        assert service.tick('admin', backup_directory=tmp_path/'backups',
            key_id='local-test-v1', key_provider=provider) == []
        assert provider.calls == 1
        retained = json.dumps(service.events('admin'))
        assert 'sensitive-provider-material' not in retained
        assert 'local_schedule_effect_failed' in retained
