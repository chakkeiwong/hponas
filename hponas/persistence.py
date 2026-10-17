"""Atomic JSON snapshots; a completed write survives process termination."""

from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile


def snapshot_artifacts(state, trial_id):
    """Project every committed repetition, including an unfinished group."""
    evaluation = state.get('evaluation')
    if evaluation is None:
        return list(state['results'].get(trial_id, {}).get('metadata', {}).get('artifacts', {}).items())
    return [
        (('final:' if role == 'final' else '') + row['result']['trial_id'] + ':' + kind, path)
        for role in ('tuning', 'final')
        for row in evaluation[role].get(trial_id, [])
        for kind, path in row['result'].get('metadata', {}).get('artifacts', {}).items()
    ]


def atomic_json(path, value):
    """Commit via a hidden .tmp sibling independent of target-name length.

    A bounded temporary basename supports every valid target basename. The
    sibling stays recognizable as uncommitted if a process stops before rename.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
