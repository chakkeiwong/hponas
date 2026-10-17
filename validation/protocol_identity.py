"""Canonical exact entry IDs, including case-sensitive split suffixes."""
import json
from pathlib import Path


def canonical_id(value):
    if not isinstance(value,str):
        raise ValueError('Validation ID must be a string')
    normalized=value.upper().replace('_','-')
    entries=json.loads((Path(__file__).parent/'protocols.json').read_text())['entries']
    matches=[key for key in entries if key.upper()==normalized]
    if len(matches)!=1:
        raise ValueError('Unknown exact validation entry: '+value)
    return matches[0]


def protocol_path(value):
    ident=canonical_id(value)
    return Path(__file__).parent/'protocols'/f"{ident.lower().replace('-','_')}_protocol.md"
