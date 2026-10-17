"""Atomic replacement, durable boundaries and valid filesystem names."""

import errno
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from hponas.persistence import atomic_json


def test_every_filesystem_valid_checkpoint_basename_can_be_replaced():
    with tempfile.TemporaryDirectory(prefix="hponas-long-checkpoint-") as directory:
        root = Path(directory)
        limit = os.pathconf(root, "PC_NAME_MAX")
        assert limit >= 14
        path = root / ("x" * (limit - 5) + ".json")
        path.write_text('{"old": true}')
        atomic_json(path, {"new": [1, 2, 3]})
        assert json.loads(path.read_text()) == {"new": [1, 2, 3]}
        assert list(root.iterdir()) == [path]


def test_new_nested_checkpoint_directory_is_created_and_reused():
    with tempfile.TemporaryDirectory(prefix="hponas-nested-checkpoint-") as directory:
        path = Path(directory) / "one/two/checkpoint.json"
        atomic_json(str(path), {"step": 1})
        atomic_json(path, {"step": 2})
        assert json.loads(path.read_text()) == {"step": 2}
        assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("fault", ["serialize", "file_sync", "replace", "directory_sync"])
def test_failed_write_preserves_a_complete_old_or_committed_snapshot_and_cleans_temporary(fault):
    with tempfile.TemporaryDirectory(prefix="hponas-atomic-failure-") as directory:
        path = Path(directory) / "checkpoint.json"
        previous, updated = {"old": [1]}, {"new": [2]}
        path.write_text(json.dumps(previous))
        real_sync, real_replace = os.fsync, os.replace
        calls = []

        def sync(fd):
            calls.append("sync")
            if (fault == "file_sync" and len(calls) == 1
                    or fault == "directory_sync" and len(calls) == 3):
                raise OSError(errno.EIO, "injected durability failure")
            return real_sync(fd)

        def replace(source, target):
            calls.append("replace")
            assert json.loads(path.read_text()) == previous
            assert json.loads(Path(source).read_text()) == updated
            if fault == "replace":
                raise OSError(errno.EIO, "injected replacement failure")
            return real_replace(source, target)

        with patch("hponas.persistence.os.fsync", sync), patch("hponas.persistence.os.replace", replace):
            with pytest.raises((TypeError, OSError)):
                atomic_json(path, {"bad": object()} if fault == "serialize" else updated)
        assert json.loads(path.read_text()) == (updated if fault == "directory_sync" else previous)
        assert list(path.parent.iterdir()) == [path]


def test_replacement_uses_a_recognizable_hidden_sibling_and_durable_commit_order():
    with tempfile.TemporaryDirectory(prefix="hponas-atomic-commit-") as directory:
        path = Path(directory) / "checkpoint.json"
        path.write_text('{"old":true}')
        real_sync, real_replace = os.fsync, os.replace
        events = []

        def sync(fd):
            import stat
            events.append("directory_sync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_sync")
            return real_sync(fd)

        def replace(source, target):
            source = Path(source)
            assert source.parent == path.parent  # Same filesystem for atomic rename.
            assert source.name.startswith(".") and source.suffix == ".tmp"
            assert len(source.name.encode()) <= os.pathconf(path.parent, "PC_NAME_MAX")
            assert json.loads(path.read_text()) == {"old": True}
            assert json.loads(source.read_text()) == {"new": True}
            events.append("replace")
            return real_replace(source, target)

        with patch("hponas.persistence.os.fsync", sync), patch("hponas.persistence.os.replace", replace):
            atomic_json(path, {"new": True})
        assert events == ["file_sync", "replace", "directory_sync"]
        assert json.loads(path.read_text()) == {"new": True}
        assert list(path.parent.iterdir()) == [path]
