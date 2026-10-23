"""Authenticated local backup artifacts with a caller-owned key provider.

This boundary protects an exported artifact. It does not encrypt a live database,
authenticate a remote caller, or protect against a process that already owns
the host or key provider. Keys and provider exceptions are never serialized.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Protocol


class BackupKeyProvider(Protocol):
    def get_key(self, key_id: str) -> bytes:
        """Return the 32-byte AES key for a non-secret, stable identifier."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _cipher(provider, key_id):
    if not isinstance(key_id, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', key_id):
        raise ValueError('A non-secret bounded key identifier is required')
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError('Encrypted backups require hponas[security]') from None
    try:
        key = provider.get_key(key_id)
        if type(key) is not bytes or len(key) != 32:
            raise ValueError()
        return AESGCM(key)
    except Exception:
        raise ValueError('Backup key unavailable or unsupported') from None


def encrypt_backup(segment, *, key_id, key_provider):
    """Encrypt one JSON segment, binding its identity as authenticated metadata."""
    cipher = _cipher(key_provider, key_id)
    metadata = {k: segment[k] for k in ('history_id', 'start_seq', 'end_seq', 'previous', 'head')}
    header = {'format': 'hponas_encrypted_events_v1', 'algorithm': 'AES-256-GCM',
              'key_id': key_id, **metadata}
    nonce = os.urandom(12)
    ciphertext = cipher.encrypt(nonce, canonical(segment), canonical(header))
    return {**header, 'nonce': base64.b64encode(nonce).decode('ascii'),
            'ciphertext': base64.b64encode(ciphertext).decode('ascii')}


def decrypt_backup(artifact, *, key_provider):
    """Fail before returning any plaintext on a wrong key or altered artifact."""
    keys = {'format', 'algorithm', 'key_id', 'history_id', 'start_seq', 'end_seq',
            'previous', 'head', 'nonce', 'ciphertext'}
    if (not isinstance(artifact, dict) or set(artifact) != keys
            or artifact['format'] != 'hponas_encrypted_events_v1'
            or artifact['algorithm'] != 'AES-256-GCM'):
        raise ValueError('Unsupported encrypted backup format')
    cipher = _cipher(key_provider, artifact['key_id'])
    header = {k: v for k, v in artifact.items() if k not in ('nonce', 'ciphertext')}
    try:
        nonce = base64.b64decode(artifact['nonce'], validate=True)
        ciphertext = base64.b64decode(artifact['ciphertext'], validate=True)
        if len(nonce) != 12:
            raise ValueError()
        segment = json.loads(cipher.decrypt(nonce, ciphertext, canonical(header)))
        if any(segment[k] != header[k] for k in ('history_id', 'start_seq', 'end_seq', 'previous', 'head')):
            raise ValueError()
    except Exception:
        raise ValueError('Encrypted backup authentication failed') from None
    return segment
